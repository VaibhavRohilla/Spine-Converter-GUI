"""Validated deterministic package construction, independent of conversion and UI."""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from hashlib import file_digest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .atomic_io import file_digests, publish_directory, publish_file, stage_files
from .bundle_models import BundleReport, FileDigest, PackageContainer
from .config import InspectionConfig
from .inspection import InspectionService
from .json_types import encode_json
from .parsers import AtlasInfo, parse_atlas
from .source import AssetSource, canonical_path, validate_member_paths
from .texture import PNGInfo, TextureLimits, validate_png


def validate_package(
    root: Path, ids: tuple[str, ...], config: InspectionConfig, texture_limits: TextureLimits
) -> None:
    manifest = InspectionService(config=config).inspect(str(root))
    if not manifest.ok or any(
        not any(b.bundle_id == name and b.validation_state == "valid" for b in manifest.bundles)
        for name in ids
    ):
        raise ValueError("Final B1 package reinspection rejected dependencies")

    textures: dict[str, PNGInfo] = {}
    atlases: dict[str, AtlasInfo] = {}
    with AssetSource(root, config.source_limits) as source:
        for asset in manifest.assets:
            if asset.kind == "texture" and asset.path.lower().endswith(".png"):
                textures[asset.path] = validate_png(source.read(asset.path), texture_limits)
        for dependency in manifest.dependencies:
            if dependency.kind != "texture_page" or dependency.resolved not in textures:
                continue
            atlas = atlases.get(dependency.owner)
            if atlas is None:
                atlas = parse_atlas(source.read(dependency.owner))
                atlases[dependency.owner] = atlas
            page = next(p for p in atlas.page_records if p.name == dependency.requested)
            declared = dict(page.attributes).get("size")
            if declared is None:
                continue  # Omitted dimensions are supplied by the actual texture header.
            dimensions = tuple(int(part.strip()) for part in declared.split(","))
            actual = textures[dependency.resolved]
            if dimensions != (actual.width, actual.height):
                raise ValueError(
                    f"Atlas {dependency.owner!r} page {page.name!r} dimensions "
                    f"{dimensions} disagree with PNG {dependency.resolved!r}: "
                    f"{actual.width}x{actual.height}"
                )


@dataclass(frozen=True)
class PackageSettings:
    compression_level: int = 9
    texture_limits: TextureLimits = field(default_factory=TextureLimits)

    def __post_init__(self) -> None:
        if type(self.compression_level) is not int or not 0 <= self.compression_level <= 9:
            raise ValueError("ZIP compression level must be an integer from 0 to 9")


@dataclass(frozen=True)
class PublicationReceipt:
    files: tuple[FileDigest, ...]
    package_sha256: str | None
    cleanup_warning: str | None


_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)
_ZIP_HOST_UNIX = 3
_ZIP_FILE_MODE = 0o100644 << 16


class PackageBuilder:
    def __init__(
        self,
        inspection_config: InspectionConfig | None = None,
        settings: PackageSettings | None = None,
    ):
        self.inspection_config = inspection_config or InspectionConfig()
        self.settings = settings or PackageSettings()

    def publish(
        self,
        outputs: Mapping[str, bytes],
        ids: tuple[str, ...],
        destination: Path,
        container: PackageContainer,
        *,
        audit_report: BundleReport | None = None,
        before_publish: Callable[[], None] | None = None,
    ) -> PublicationReceipt:
        if not isinstance(container, PackageContainer):
            raise TypeError("container must be PackageContainer")
        validate_member_paths(outputs)
        canonical_path(destination.name)
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Output destination is occupied")
        destination.parent.mkdir(parents=True, exist_ok=True)
        packaged = dict(outputs)
        if audit_report is not None:
            report_name = "fnx-conversion-report.json"
            if report_name.casefold() in {name.casefold() for name in outputs}:
                raise ValueError("Audit report filename collides with an input asset")
            snapshot = audit_report.to_dict()
            snapshot["report_scope"] = "prepublication_validation"
            packaged[report_name] = encode_json(snapshot)
        hashes = file_digests(packaged)
        stage = tempfile.TemporaryDirectory(prefix=f".{destination.name}.", dir=destination.parent)
        published = False
        cleanup_warning: str | None = None
        package_hash: str | None = None
        try:
            root = Path(stage.name)
            payload = root / "payload"
            payload.mkdir()
            stage_files(payload, packaged)
            validate_package(payload, ids, self.inspection_config, self.settings.texture_limits)
            if container == PackageContainer.ZIP:
                artifact = root / "package.zip"
                with ZipFile(
                    artifact,
                    "w",
                    compression=ZIP_DEFLATED,
                    compresslevel=self.settings.compression_level,
                ) as writer:
                    for name, data in sorted(packaged.items()):
                        info = ZipInfo(canonical_path(name), date_time=_ZIP_EPOCH)
                        info.create_system = _ZIP_HOST_UNIX
                        info.external_attr = _ZIP_FILE_MODE
                        info.compress_type = ZIP_DEFLATED
                        writer.writestr(info, data, compresslevel=self.settings.compression_level)
                with ZipFile(artifact) as archive:
                    if archive.testzip() is not None:
                        raise ValueError("Generated ZIP failed CRC verification")
                with AssetSource(artifact, self.inspection_config.source_limits) as reader:
                    if {n: reader.read(n) for n in reader.names()} != packaged:
                        raise ValueError("Generated ZIP differs from staged assets")
                validate_package(
                    artifact, ids, self.inspection_config, self.settings.texture_limits
                )
                with artifact.open("rb") as stream:
                    package_hash = file_digest(stream, "sha256").hexdigest()
                if before_publish is not None:
                    before_publish()
                publish_file(artifact, destination)
            else:
                if before_publish is not None:
                    before_publish()
                publish_directory(payload, destination)
            published = True
        finally:
            try:
                stage.cleanup()
            except OSError as exc:
                if not published:
                    raise
                cleanup_warning = str(exc)
        return PublicationReceipt(hashes, package_hash, cleanup_warning)
