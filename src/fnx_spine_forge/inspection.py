"""Shared deterministic inspection orchestration for CLI and future UI/API clients."""

from __future__ import annotations

import zlib
from collections.abc import Mapping
from json import JSONDecodeError, dumps, loads
from pathlib import PurePosixPath
from zipfile import BadZipFile

from .binary import BinaryCodecRegistry, BinaryError, BinaryErrorCode
from .config import InspectionConfig
from .dependencies import DependencyResolver
from .detection import TEXTURE_EXTENSIONS
from .json_types import JSONDocument
from .models import (
    Asset,
    AssetManifest,
    BundleValidation,
    Dependency,
    DependencyKind,
    DependencyStatus,
    Diagnostic,
    FileType,
    Severity,
    SpineBundle,
)
from .parsers import inspect_skeleton, parse_atlas
from .source import AssetSource
from .versions import VersionRegistry

_SOURCE_READ_ERRORS = (OSError, EOFError, RuntimeError, BadZipFile, zlib.error)


class InspectionService:
    def __init__(
        self,
        version_registry: VersionRegistry | None = None,
        config: InspectionConfig | None = None,
        *,
        atlas_overrides: Mapping[str, str] | None = None,
        texture_overrides: Mapping[tuple[str, str], str] | None = None,
    ):
        self.atlas_overrides = dict(atlas_overrides or {})
        self.texture_overrides = dict(texture_overrides or {})
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
                    kind = FileType.OTHER
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
                                    kind = FileType.SKELETON_JSON
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
                        kind = FileType.SKELETON_BINARY
                        skeletons.append(name)
                        try:
                            payload = source.read(name)
                            registry = BinaryCodecRegistry()
                            version = registry.probe(payload, limits=self.config.binary_limits)
                            versions[name] = version
                            codec = registry.codec(
                                version, experimental=True, limits=self.config.binary_limits
                            )
                            document = codec.decode(payload)
                            info = inspect_skeleton(dumps(document).encode("utf-8"))
                            if info is None:
                                raise ValueError("Decoded binary skeleton failed inspection")
                            attachment_paths_by_skeleton[name] = info.attachment_paths
                            metadata = {
                                "binary_decoded": True,
                                "binary_codec": codec.capability.to_dict(),
                                "counts": info.counts,
                                "names": info.names,
                                "attachment_paths": info.attachment_paths,
                            }
                            diagnostics.append(
                                Diagnostic(
                                    "BINARY_UNQUALIFIED",
                                    Severity.WARNING,
                                    "Binary decoding has no semantic qualification",
                                    name,
                                )
                            )
                        except BinaryError as exc:
                            diagnostics.append(
                                Diagnostic(
                                    exc.code.value,
                                    Severity.WARNING
                                    if exc.code
                                    in (
                                        BinaryErrorCode.VERSION_UNSUPPORTED,
                                        BinaryErrorCode.FEATURE_UNSUPPORTED,
                                    )
                                    else Severity.ERROR,
                                    str(exc),
                                    name,
                                    exc.to_dict(),
                                )
                            )
                        except (ValueError, *_SOURCE_READ_ERRORS) as exc:
                            diagnostics.append(
                                Diagnostic("BINARY_INVALID", Severity.ERROR, str(exc), name)
                            )
                    elif ext == ".atlas":
                        kind = FileType.ATLAS
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
                                override = self.texture_overrides.get((name, page))
                                if override is not None:
                                    if (
                                        override not in names
                                        or PurePosixPath(override).suffix.lower()
                                        not in TEXTURE_EXTENSIONS
                                    ):
                                        raise ValueError(
                                            "Texture override must select an existing texture"
                                        )
                                    resolved, ambiguous = override, False
                                deps.append(
                                    Dependency(
                                        name,
                                        page,
                                        resolved,
                                        DependencyKind.TEXTURE_PAGE,
                                        DependencyStatus.AMBIGUOUS
                                        if ambiguous
                                        else DependencyStatus.MISSING
                                        if not resolved
                                        else DependencyStatus.RESOLVED,
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
                        kind = FileType.TEXTURE
                    else:
                        kind = FileType.OTHER
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
                if set(self.atlas_overrides) - set(skeletons):
                    raise ValueError("Atlas override references an undiscovered skeleton")
                declared_pages = {(d.owner, d.requested) for d in deps if d.kind == "texture_page"}
                if set(self.texture_overrides) - declared_pages:
                    raise ValueError("Texture override references an undeclared atlas page")
                for skel in skeletons:
                    if skel in attachment_paths_by_skeleton:
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
                        override = self.atlas_overrides.get(skel)
                        if override is not None:
                            if override not in regions_by_atlas:
                                raise ValueError(
                                    "Atlas override must select a valid discovered atlas"
                                )
                            related = [override]
                        elif len(choices) == 1:
                            related = [choices[0][0]]
                        elif len(choices) > 1:
                            # A matching export stem can resolve a tie only after
                            # attachment-region evidence has narrowed the choices.
                            stem = PurePosixPath(skel).stem.casefold()
                            local_choices = [
                                atlas
                                for atlas, _ in choices
                                if PurePosixPath(atlas).parent == PurePosixPath(skel).parent
                            ]
                            stem_matches = [
                                atlas
                                for atlas, _ in choices
                                if PurePosixPath(atlas).stem.casefold() == stem
                            ]
                            if len(local_choices) == 1 and len(stem_matches) <= 1:
                                related = local_choices
                            elif len(stem_matches) == 1:
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
                        elif (
                            len(atlases) > 1
                            and not paths
                            and len(
                                [
                                    a
                                    for a in atlases
                                    if PurePosixPath(a).parent == PurePosixPath(skel).parent
                                ]
                            )
                            == 1
                        ):
                            related = [
                                a
                                for a in atlases
                                if PurePosixPath(a).parent == PurePosixPath(skel).parent
                            ]
                        elif len(atlases) > 1:
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
                            deps.append(Dependency(skel, atlas, atlas, DependencyKind.ATLAS))
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
                            BundleValidation.INVALID
                            if any(
                                d.severity in (Severity.ERROR, Severity.BLOCKER) and d.path == skel
                                for d in diagnostics
                            )
                            else BundleValidation.NOT_EVALUATED
                            if skel not in attachment_paths_by_skeleton
                            else BundleValidation.VALID,
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
