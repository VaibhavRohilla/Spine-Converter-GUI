"""Immutable selected-asset snapshots using canonical B1/B3 association."""

import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from urllib.parse import quote

from ..atomic_io import stage_files
from ..bundle import BundleService
from ..bundle_models import DependencyMappings
from ..json_types import JSONDocument, decode_json_object
from ..models import DependencyKind, DependencyStatus, FileType, Severity
from ..parsers import parse_atlas
from ..progress import CancellationToken
from ..source import AssetSource, SourceSelection
from ..texture import TextureLimits, validate_png
from .admission import admit_render_document
from .binary_policy import MAX_BINARY_BYTES, admit_binary
from .registry import RuntimeCapability, RuntimeRegistry


@dataclass(frozen=True)
class BinarySelection:
    """Explicit external export identity; verified against official parser output, never patched."""

    export_version: str
    atlas: str


@dataclass(frozen=True)
class TextureResource:
    path: str
    width: int
    height: int
    pma: bool


@dataclass(frozen=True)
class ViewerAssetSet:
    asset_id: str
    export_version: str
    runtime: RuntimeCapability
    skeleton: str
    atlas: str
    pages: Mapping[str, TextureResource]
    files: Mapping[str, bytes]
    checksums: Mapping[str, str]
    binary: bool
    source_risk: bool

    def descriptor(self, prefix: str, session_id: str) -> JSONDocument:
        return {
            "sessionId": session_id,
            "assetId": self.asset_id,
            "exportVersion": self.export_version,
            "family": self.runtime.family,
            "runtimeRevision": self.runtime.revision,
            "skeleton": prefix + quote(self.skeleton, safe=""),
            "atlas": prefix + quote(self.atlas, safe=""),
            "pages": {
                name: {
                    "url": prefix + quote(page.path, safe=""),
                    "sha256": self.checksums[page.path],
                    "width": page.width,
                    "height": page.height,
                    "pma": page.pma,
                }
                for name, page in self.pages.items()
            },
            "checksums": dict(self.checksums),
            "resourceHashes": {
                prefix + quote(path, safe=""): digest for path, digest in self.checksums.items()
            },
            "binary": self.binary,
            "sourceRisk": self.source_risk,
            "conversionQualification": "UNCHANGED_NOT_INFERRED_FROM_PLAYBACK",
        }


class ViewerService:
    def __init__(self, max_bytes: int = 256 * 1024 * 1024) -> None:
        if max_bytes <= 0:
            raise ValueError("Viewer byte limit must be positive")
        self.max_bytes = max_bytes
        self.bundles = BundleService()
        self.registry = RuntimeRegistry()

    def prepare(
        self,
        source: SourceSelection,
        bundle_id: str,
        mappings: DependencyMappings | None = None,
        *,
        binary: BinarySelection | None = None,
        pma: bool | None = None,
        cancellation: CancellationToken | None = None,
    ) -> ViewerAssetSet:
        def check() -> None:
            if cancellation is not None and cancellation.cancelled:
                raise ValueError("VIEWER_SESSION_CANCELLED")

        check()
        with AssetSource(source) as reader:
            captured: dict[str, bytes] = {}
            total = 0
            for name in reader.names():
                check()
                is_binary_file = Path(name).suffix.lower() == ".skel" or (
                    binary is not None and name == bundle_id
                )
                if is_binary_file and reader.size(name) > MAX_BINARY_BYTES:
                    raise ValueError("VIEWER_RESOURCE_LIMIT_EXCEEDED: binary exceeds 32 MiB")
                data = reader.read(name, MAX_BINARY_BYTES if is_binary_file else None)
                if is_binary_file:
                    # Before B1 inspection, including unselected binary siblings.
                    admit_binary(
                        data, binary.export_version if binary and name == bundle_id else None
                    )
                total += len(data)
                if total > self.max_bytes:
                    raise ValueError("VIEWER_RESOURCE_LIMIT_EXCEEDED")
                captured[name] = data
        with tempfile.TemporaryDirectory(prefix="fnx-viewer-") as directory:
            stage_files(Path(directory), captured)
            check()
            result = self._prepare(Path(directory), bundle_id, mappings, binary, pma)
            check()
            return result

    def _prepare(
        self,
        source: SourceSelection,
        bundle_id: str,
        mappings: DependencyMappings | None,
        binary: BinarySelection | None,
        pma_override: bool | None,
    ) -> ViewerAssetSet:
        inspection = self.bundles.inspect_source(source, mappings)
        manifest = inspection.manifest
        bundle = next((b for b in manifest.bundles if b.bundle_id == bundle_id), None)
        if bundle is None:
            raise ValueError("UNSUPPORTED_SKELETON_FORMAT: explicit inspected bundle required")
        asset = next(a for a in manifest.assets if a.path == bundle_id)
        is_binary = asset.kind == FileType.SKELETON_BINARY
        if is_binary:
            # B1 intentionally cannot decode arbitrary binary attachments. The caller must
            # select a discovered atlas; its texture dependencies still come only from B1.
            if binary is None:
                raise ValueError("UNSUPPORTED_SKELETON_FORMAT: binary export identity required")
            if not any(
                a.path == binary.atlas and a.kind == FileType.ATLAS for a in manifest.assets
            ):
                raise ValueError("ATLAS_LOAD_FAILED: explicit binary atlas is not inspected")
            version, atlas = binary.export_version, binary.atlas
            if asset.spine_version and asset.spine_version != version:
                raise ValueError("RUNTIME_VERSION_MISMATCH")
        else:
            if binary is not None:
                raise ValueError("UNSUPPORTED_SKELETON_FORMAT: binary selection for JSON")
            if not asset.spine_version:
                raise ValueError("UNSUPPORTED_SKELETON_VERSION")
            version = asset.spine_version
            if len(bundle.atlases) != 1:
                raise ValueError("ATLAS_LOAD_FAILED: select one atlas using B3 mappings")
            atlas = bundle.atlases[0]
        runtime = self.registry.select(version)
        dependencies = tuple(d for d in manifest.dependencies if d.owner == atlas)
        pages: dict[str, str] = {}
        for dep in dependencies:
            if dep.status != DependencyStatus.RESOLVED:
                raise ValueError(f"TEXTURE_MISSING: {dep.requested}")
            if dep.kind == DependencyKind.TEXTURE_PAGE and dep.resolved is not None:
                pages[dep.requested] = dep.resolved
        if not pages:
            raise ValueError("TEXTURE_MISSING: no resolved atlas pages")
        selected = {bundle_id, atlas, *pages.values()}
        errors = [
            d
            for d in manifest.diagnostics
            if d.severity in (Severity.ERROR, Severity.BLOCKER)
            and (d.path is None or d.path in selected)
            # An experimental FNX binary decoder failure does not reject direct official
            # runtime loading. The official parser must accept the unchanged bytes.
            and not (is_binary and d.path == bundle_id and d.code.startswith("BINARY_"))
        ]
        if errors:
            raise ValueError("; ".join(f"{d.code}: {d.message}" for d in errors))
        with AssetSource(source) as reader:
            files = {name: reader.read(name) for name in sorted(selected)}
        if not is_binary:
            admit_render_document(
                decode_json_object(files[bundle_id].decode("utf-8-sig"), "Viewer skeleton"),
                runtime.family,
            )
        records = {page.name: page for page in parse_atlas(files[atlas]).page_records}
        textures: dict[str, TextureResource] = {}
        pixel_count = 0
        for name, path in pages.items():
            if not path.lower().endswith(".png"):
                raise ValueError("UNSUPPORTED_RENDER_FEATURE: bounded PNG texture loading only")
            info = validate_png(files[path], TextureLimits(max_dimension=8192, max_pixels=16777216))
            pixel_count += info.width * info.height
            if pixel_count > 33554432:
                raise ValueError("VIEWER_RESOURCE_LIMIT_EXCEEDED: total texture pixels")
            attributes = dict(records[name].attributes)
            value = attributes.get("pma", "false")
            if value not in ("true", "false"):
                raise ValueError("ATLAS_LOAD_FAILED: invalid pma attribute")
            pma = value == "true" if pma_override is None else pma_override
            textures[name] = TextureResource(path, info.width, info.height, pma)
        if runtime.family != "4.3" and len({t.pma for t in textures.values()}) != 1:
            raise ValueError("UNSUPPORTED_RENDER_FEATURE: mixed per-page alpha before 4.3")
        return ViewerAssetSet(
            bundle_id,
            version,
            runtime,
            bundle_id,
            atlas,
            MappingProxyType(textures),
            MappingProxyType(files),
            MappingProxyType({n: sha256(b).hexdigest() for n, b in files.items()}),
            is_binary,
            version == "3.8.75",
        )
