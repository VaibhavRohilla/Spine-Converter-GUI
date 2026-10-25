"""Shared deterministic inspection orchestration for CLI and future UI/API clients."""

from __future__ import annotations

import zlib
from json import JSONDecodeError, loads
from pathlib import PurePosixPath
from zipfile import BadZipFile

from .config import InspectionConfig
from .dependencies import DependencyResolver
from .detection import TEXTURE_EXTENSIONS
from .json_types import JSONDocument
from .models import Asset, AssetManifest, Dependency, Diagnostic, Severity, SpineBundle
from .parsers import inspect_skeleton, parse_atlas
from .source import AssetSource
from .versions import VersionRegistry

_SOURCE_READ_ERRORS = (OSError, EOFError, RuntimeError, BadZipFile, zlib.error)


class InspectionService:
    def __init__(
        self,
        version_registry: VersionRegistry | None = None,
        config: InspectionConfig | None = None,
    ):
        self.versions = version_registry or VersionRegistry()
        self.config = config or InspectionConfig()

    def inspect(self, origin: str) -> AssetManifest:
        assets = []
        deps = []
        diagnostics = []
        skeletons = []
        atlases = []
        regions_by_atlas = {}
        attachment_paths_by_skeleton: dict[str, tuple[str, ...]] = {}
        versions = {}
        try:
            with AssetSource(origin, self.config.source_limits) as source:
                names = source.names()
                resolver = DependencyResolver(names)
                for name in names:
                    ext = PurePosixPath(name).suffix.lower()
                    size = source.size(name)
                    kind = "other"
                    version = None
                    metadata: JSONDocument = {}
                    if ext == ".json":
                        if size > self.config.max_skeleton_json_bytes:
                            diagnostics.append(
                                Diagnostic(
                                    "JSON_TOO_LARGE",
                                    Severity.WARNING,
                                    "JSON exceeds configured skeleton inspection threshold",
                                    name,
                                )
                            )
                        else:
                            try:
                                payload = source.read(name)
                            except _SOURCE_READ_ERRORS as exc:
                                diagnostics.append(
                                    Diagnostic("ASSET_UNREADABLE", Severity.ERROR, str(exc), name)
                                )
                            else:
                                info = inspect_skeleton(payload)
                                if info:
                                    kind = "skeleton_json"
                                    version = info.version
                                    skeletons.append(name)
                                    attachment_paths_by_skeleton[name] = info.attachment_paths
                                    metadata = {
                                        "counts": info.counts,
                                        "names": info.names,
                                        "attachment_paths": info.attachment_paths,
                                    }
                                    for code, msg in info.diagnostics:
                                        diagnostics.append(
                                            Diagnostic(
                                                code,
                                                Severity.WARNING
                                                if code == "SKELETON_VERSION_MISSING"
                                                else Severity.ERROR,
                                                msg,
                                                name,
                                            )
                                        )
                                    if version:
                                        family = self.versions.family_for(version)
                                        versions[name] = version
                                        if family is None:
                                            diagnostics.append(
                                                Diagnostic(
                                                    "UNSUPPORTED_VERSION",
                                                    Severity.WARNING,
                                                    f"Unsupported Spine version {version}",
                                                    name,
                                                )
                                            )
                                else:
                                    try:
                                        loads(payload.decode("utf-8-sig"))
                                    except (UnicodeError, JSONDecodeError) as exc:
                                        diagnostics.append(
                                            Diagnostic(
                                                "MALFORMED_JSON",
                                                Severity.WARNING,
                                                f"JSON could not be parsed: {exc}",
                                                name,
                                            )
                                        )
                    elif ext == ".skel":
                        kind = "skeleton_binary"
                        skeletons.append(name)
                        diagnostics.append(
                            Diagnostic(
                                "BINARY_NOT_YET_SUPPORTED",
                                Severity.INFO,
                                "Binary skeleton discovered; no documented bounded version probe "
                                "is enabled",
                                name,
                            )
                        )
                    elif ext == ".atlas":
                        kind = "atlas"
                        atlases.append(name)
                        try:
                            atlas_payload = source.read(name)
                        except _SOURCE_READ_ERRORS as exc:
                            diagnostics.append(
                                Diagnostic("ASSET_UNREADABLE", Severity.ERROR, str(exc), name)
                            )
                            atlas_payload = None
                        try:
                            if atlas_payload is None:
                                raise ValueError("Atlas content could not be read")
                            atlas_info = parse_atlas(atlas_payload)
                            regions_by_atlas[name] = atlas_info.regions
                            metadata = {
                                "regions": atlas_info.regions,
                                "page_records": [
                                    {"name": page.name, "attributes": page.attributes}
                                    for page in atlas_info.page_records
                                ],
                                "region_records": [
                                    {"name": region.name, "attributes": region.attributes}
                                    for region in atlas_info.region_records
                                ],
                                "attributes": atlas_info.attributes,
                                "unknown_attributes": atlas_info.unknown_attributes,
                            }
                            if atlas_info.duplicate_regions:
                                diagnostics.append(
                                    Diagnostic(
                                        "DUPLICATE_ATLAS_REGION",
                                        Severity.ERROR,
                                        "Atlas contains duplicate region names",
                                        name,
                                        {"regions": atlas_info.duplicate_regions},
                                    )
                                )
                            for page in atlas_info.pages:
                                match = resolver.resolve(page, name)
                                resolved, ambiguous = match.resolved, match.ambiguous
                                deps.append(
                                    Dependency(
                                        name,
                                        page,
                                        resolved,
                                        "texture_page",
                                        "ambiguous"
                                        if ambiguous
                                        else "missing"
                                        if not resolved
                                        else "resolved",
                                    )
                                )
                                if not resolved:
                                    diagnostics.append(
                                        Diagnostic(
                                            "AMBIGUOUS_TEXTURE" if ambiguous else "MISSING_TEXTURE",
                                            Severity.ERROR,
                                            f"Atlas page {page!r} cannot be uniquely resolved",
                                            name,
                                            {"referenced_page": page},
                                            "Add the missing texture or correct the atlas page "
                                            "reference.",
                                        )
                                    )
                        except (ValueError, UnicodeError) as exc:
                            if atlas_payload is not None:
                                diagnostics.append(
                                    Diagnostic("INVALID_ATLAS", Severity.ERROR, str(exc), name)
                                )
                    elif ext in TEXTURE_EXTENSIONS:
                        kind = "texture"
                    else:
                        kind = "other"
                    assets.append(
                        Asset(
                            path=name,
                            kind=kind,
                            spine_version=version,
                            byte_size=size,
                            asset_id=name,
                            source_id=str(origin),
                            filename=PurePosixPath(name).name,
                            extension=ext,
                            metadata=metadata,
                        )
                    )
                for skel in skeletons:
                    if skel.lower().endswith(".json"):
                        paths = attachment_paths_by_skeleton.get(skel, ())
                        candidates = []
                        for atlas, atlas_regions in regions_by_atlas.items():
                            region_names = set(atlas_regions)
                            matched = [
                                path
                                for path in paths
                                if path in region_names or PurePosixPath(path).name in region_names
                            ]
                            if matched:
                                candidates.append((atlas, matched))
                        complete = [
                            candidate for candidate in candidates if len(candidate[1]) == len(paths)
                        ]
                        choices = complete or candidates
                        related = []
                        if len(choices) == 1:
                            related = [choices[0][0]]
                        elif len(choices) > 1:
                            # A matching export stem can resolve a tie only after
                            # attachment-region evidence has narrowed the choices.
                            stem = PurePosixPath(skel).stem.casefold()
                            stem_matches = [
                                atlas
                                for atlas, _ in choices
                                if PurePosixPath(atlas).stem.casefold() == stem
                            ]
                            if len(stem_matches) == 1:
                                related = stem_matches
                            else:
                                diagnostics.append(
                                    Diagnostic(
                                        "AMBIGUOUS_ATLAS",
                                        Severity.ERROR,
                                        "Attachment regions occur in multiple candidate atlases",
                                        skel,
                                        {"atlases": [item[0] for item in choices]},
                                    )
                                )
                        elif len(atlases) == 1:
                            related = [atlases[0]]
                        elif len(atlases) > 1 and paths:
                            diagnostics.append(
                                Diagnostic(
                                    "AMBIGUOUS_ATLAS",
                                    Severity.ERROR,
                                    "No atlas contains the skeleton attachment references",
                                    skel,
                                    {"atlases": [atlas for atlas in atlases]},
                                )
                            )
                        for atlas in related:
                            deps.append(Dependency(skel, atlas, atlas, "atlas"))
                            region_set = set(regions_by_atlas.get(atlas, ()))
                            for requested in paths:
                                region = PurePosixPath(requested).name
                                if requested not in region_set and region not in region_set:
                                    diagnostics.append(
                                        Diagnostic(
                                            "ATLAS_REGION_MISSING",
                                            Severity.ERROR,
                                            f"Attachment image path {requested!r} has no matching "
                                            "atlas region",
                                            skel,
                                            {"atlas": atlas, "reference": requested},
                                        )
                                    )

                if not skeletons:
                    diagnostics.append(
                        Diagnostic(
                            "NO_SKELETON", Severity.WARNING, "No Spine skeleton export detected"
                        )
                    )
                # Keep ambiguous global assets unassigned for explicit review.
                bundles = []
                for skel in skeletons:
                    related = [
                        d.resolved
                        for d in deps
                        if d.owner == skel and d.kind == "atlas" and d.resolved
                    ]
                    bundle_deps = tuple(d for d in deps if d.owner == skel or d.owner in related)
                    textures = tuple(
                        sorted(
                            {
                                d.resolved
                                for d in bundle_deps
                                if d.kind == "texture_page" and d.resolved
                            }
                        )
                    )
                    bundles.append(
                        SpineBundle(
                            skel,
                            (skel,),
                            tuple(related),
                            textures,
                            str(origin),
                            (versions[skel],) if skel in versions else (),
                            bundle_deps,
                            "valid"
                            if not any(
                                d.severity in (Severity.ERROR, Severity.BLOCKER) and d.path == skel
                                for d in diagnostics
                            )
                            else "invalid",
                        )
                    )
                counts = {
                    "assets": len(assets),
                    "skeletons": sum(
                        a.kind in ("skeleton_json", "skeleton_binary") for a in assets
                    ),
                    "atlases": sum(a.kind == "atlas" for a in assets),
                    "textures": sum(a.kind == "texture" for a in assets),
                }
                return AssetManifest(
                    str(origin),
                    tuple(assets),
                    tuple(bundles),
                    tuple(deps),
                    tuple(diagnostics),
                    1,
                    counts,
                )
        except (ValueError, OSError, EOFError, BadZipFile) as exc:
            diagnostics.append(Diagnostic("INPUT_ERROR", Severity.BLOCKER, str(exc)))
            return AssetManifest(
                str(origin),
                (),
                (),
                (),
                tuple(diagnostics),
                1,
                {"assets": 0, "skeletons": 0, "atlases": 0, "textures": 0},
            )
