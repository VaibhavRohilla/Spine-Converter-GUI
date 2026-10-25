"""Headless bundle jobs over B1 discovery and B2 asset-set conversion.

Publication is per job. A request selecting several bundles is all-or-nothing;
independent requests have independent destinations and qualification results.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from enum import StrEnum
from hashlib import file_digest, sha256
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import cast
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

from .binary import BinaryCodecRegistry, BinaryError
from .conversion.asset_set import AssetSetConverter, AssetSetResult
from .conversion.models import SourceRiskPolicy
from .conversion.planner import ConversionPlanner
from .conversion.qualification import QualificationService, SourceFeature, inspect_features
from .conversion.registry import KNOWN_EXPORT_ISSUE_PATCHES, SUPPORTED_PATCH_VERSIONS
from .conversion.skeleton import SkeletonConverter
from .inspection import InspectionService
from .json_types import JSONDocument, JSONValue
from .models import AssetManifest, Diagnostic, Severity
from .source import AssetSource, canonical_path
from .texture import validate_png
from .versions import VersionRegistry

SourceSelection = str | Path | tuple[Path, ...]


class JobStatus(StrEnum):
    COMPLETED = "completed"
    PLANNED = "planned"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SkeletonFormat(StrEnum):
    JSON = "json"
    BINARY = "binary"


class BundleState(StrEnum):
    READY = "READY"
    NEEDS_SELECTION = "NEEDS_SELECTION"
    INCOMPLETE = "INCOMPLETE"
    UNSUPPORTED = "UNSUPPORTED"
    INVALID = "INVALID"


class Stage(StrEnum):
    SCANNING = "SCANNING"
    DISCOVERING = "DISCOVERING"
    VALIDATING = "VALIDATING"
    PLANNING = "PLANNING"
    CONVERTING_SKELETON = "CONVERTING_SKELETON"
    CONVERTING_ATLAS = "CONVERTING_ATLAS"
    VERIFYING = "VERIFYING"
    PACKAGING = "PACKAGING"
    PUBLISHING = "PUBLISHING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class RetentionPolicy(StrEnum):
    REQUIRED_ONLY = "required_only"
    ALL = "all"


class PackageMode(StrEnum):
    VIEWER = "viewer"
    AUDIT = "audit"


@dataclass(frozen=True)
class DependencyMappings:
    atlases: Mapping[str, str] = field(default_factory=dict)
    textures: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        atlases: Mapping[str, str] = MappingProxyType(dict(self.atlases))
        textures: Mapping[tuple[str, str], str] = MappingProxyType(dict(self.textures))
        object.__setattr__(self, "atlases", atlases)
        object.__setattr__(self, "textures", textures)


@dataclass(frozen=True)
class ProgressEvent:
    stage: Stage
    asset_id: str | None = None


@dataclass
class CancellationToken:
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


@dataclass(frozen=True)
class BundleRequest:
    source: SourceSelection
    target: str
    output: Path
    bundle_ids: tuple[str, ...] = ()
    experimental_structural: bool = False
    source_risk_policy: SourceRiskPolicy = SourceRiskPolicy.REJECT_KNOWN_ISSUES
    retention: RetentionPolicy = RetentionPolicy.REQUIRED_ONLY
    package_mode: PackageMode = PackageMode.VIEWER
    mappings: DependencyMappings = field(default_factory=DependencyMappings)
    skeleton_format: SkeletonFormat = SkeletonFormat.JSON


@dataclass(frozen=True)
class BundleInspection:
    manifest: AssetManifest
    states: Mapping[str, BundleState]
    targets: Mapping[str, Mapping[str, JSONDocument]]

    def to_dict(self) -> JSONDocument:
        result = self.manifest.to_dict()
        result["binary_capabilities"] = tuple(
            c.to_dict() for c in BinaryCodecRegistry().capabilities()
        )
        result["source_state"] = (
            BundleState.INVALID.value
            if not self.manifest.ok
            else BundleState.UNSUPPORTED.value
            if not self.states
            else BundleState.READY.value
            if all(s == BundleState.READY for s in self.states.values())
            else next(s.value for s in self.states.values() if s != BundleState.READY)
        )
        result["states"] = {k: v.value for k, v in self.states.items()}
        result["targets"] = {k: dict(v) for k, v in self.targets.items()}
        result["source_risks"] = {
            a.path: "SOURCE_EXPORT_KNOWN_BUG"
            for a in self.manifest.assets
            if a.spine_version in KNOWN_EXPORT_ISSUE_PATCHES
        }
        result["required_decisions"] = tuple(
            {"asset_id": k, "code": v.value}
            for k, v in self.states.items()
            if v != BundleState.READY
        ) + tuple(
            {"asset_id": a.path, "code": "SOURCE_EXPORT_RISK_AUTHORIZATION_REQUIRED"}
            for a in self.manifest.assets
            if a.spine_version in KNOWN_EXPORT_ISSUE_PATCHES
        )
        return result


@dataclass(frozen=True)
class BundleResult:
    status: JobStatus
    published: bool
    report: JSONDocument

    def to_dict(self) -> JSONDocument:
        return {"status": self.status, "published": self.published, "report": self.report}


class _Cancelled(Exception):
    pass


@contextmanager
def _source(selection: SourceSelection) -> Iterator[str]:
    if not isinstance(selection, tuple):
        yield str(selection)
        return
    if not selection or any(not p.is_file() or p.is_symlink() for p in selection):
        raise ValueError("Explicit selection requires existing regular files")
    root = Path(os.path.commonpath([str(p.absolute().parent) for p in selection]))
    with tempfile.TemporaryDirectory(prefix="fnx-selection-") as directory:
        with AssetSource(root) as source:
            for path in selection:
                name = canonical_path(path.absolute().relative_to(root).as_posix())
                target = Path(directory) / name
                if target.exists():
                    raise ValueError("Duplicate explicit selection")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(source.read(name))
        yield directory


def _manifest_source(manifest: AssetManifest, location: str) -> AssetManifest:
    return replace(
        manifest,
        source=location,
        assets=tuple(replace(a, source_id=location) for a in manifest.assets),
        bundles=tuple(replace(b, source_location=location) for b in manifest.bundles),
    )


def _inspection(mappings: DependencyMappings) -> InspectionService:
    return InspectionService(atlas_overrides=mappings.atlases, texture_overrides=mappings.textures)


def _state(manifest: AssetManifest, bundle_id: str) -> BundleState:
    bundle = next(b for b in manifest.bundles if b.bundle_id == bundle_id)
    asset = next(a for a in manifest.assets if a.path == bundle_id)
    if VersionRegistry().family_for(asset.spine_version) is None or (
        asset.kind == "skeleton_binary" and not asset.metadata.get("binary_capability")
    ):
        return BundleState.UNSUPPORTED
    paths = {bundle_id, *bundle.atlases, *bundle.texture_pages}
    diagnostics = [d for d in manifest.diagnostics if d.path is None or d.path in paths]
    if any(d.code == "CONVERSION_SOURCE_UNSUPPORTED" for d in diagnostics):
        return BundleState.UNSUPPORTED
    if any(d.code.startswith("AMBIGUOUS") for d in diagnostics):
        return BundleState.NEEDS_SELECTION
    if any(d.code.startswith("MISSING") for d in diagnostics) or not bundle.atlases:
        return BundleState.INCOMPLETE
    if any(d.severity in (Severity.ERROR, Severity.BLOCKER) for d in diagnostics):
        return BundleState.INVALID
    return BundleState.READY


def _portable(
    files: Mapping[str, bytes],
    manifest: AssetManifest,
    ids: tuple[str, ...],
    *,
    retain_all: bool = False,
) -> dict[str, bytes]:
    """Materialize declared page paths; B1 basename lookup alone is not portable."""
    result = dict(files)
    targets: set[str] = set()
    resolved: set[str] = set()
    for bundle in manifest.bundles:
        if bundle.bundle_id not in ids:
            continue
        for dep in bundle.dependencies:
            if dep.kind != "texture_page" or dep.resolved is None:
                continue
            parts = list(PurePosixPath(dep.owner).parent.parts)
            for part in PurePosixPath(dep.requested).parts:
                if part == "..":
                    if not parts:
                        raise ValueError("Texture reference escapes package")
                    parts.pop()
                elif part != ".":
                    parts.append(part)
            name = canonical_path(PurePosixPath(*parts).as_posix())
            targets.add(name)
            resolved.add(dep.resolved)
            payload = files[dep.resolved]
            if name in result and result[name] != payload:
                raise ValueError("Texture mapping collides with another output")
            result[name] = payload
    if not retain_all:
        for name in resolved - targets:
            result.pop(name, None)
    return result


def _write_files(root: Path, files: Mapping[str, bytes]) -> None:
    seen: set[str] = set()
    for name, data in sorted(files.items()):
        safe = canonical_path(name)
        if safe.casefold() in seen:
            raise ValueError("Normalized output collision")
        seen.add(safe.casefold())
        target = root / safe
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def _validate(root: Path, ids: tuple[str, ...]) -> None:
    manifest = InspectionService().inspect(str(root))
    if not manifest.ok or any(
        not any(b.bundle_id == name and b.validation_state == "valid" for b in manifest.bundles)
        for name in ids
    ):
        raise ValueError("Final B1 package reinspection rejected dependencies")


class BundleService:
    def inspect_source(
        self, source: SourceSelection, mappings: DependencyMappings | None = None
    ) -> BundleInspection:
        try:
            return self._inspect_source(source, mappings)
        except (OSError, ValueError, UnicodeError) as exc:
            manifest = AssetManifest(
                str(source),
                (),
                (),
                (),
                (
                    Diagnostic(
                        "INPUT_ERROR", Severity.ERROR, str(exc), suggestion="Select readable assets"
                    ),
                ),
            )
            return BundleInspection(manifest, {}, {})

    def _inspect_source(
        self, source: SourceSelection, mappings: DependencyMappings | None = None
    ) -> BundleInspection:
        with _source(source) as origin:
            manifest = _inspection(mappings or DependencyMappings()).inspect(origin)
            manifest = _manifest_source(manifest, str(source))
            targets: dict[str, dict[str, JSONDocument]] = {}
            if not manifest.assets:
                return BundleInspection(manifest, {}, targets)
            with AssetSource(origin) as reader:
                texture_diagnostics: list[Diagnostic] = []
                for asset in manifest.assets:
                    if asset.kind == "texture" and asset.path.lower().endswith(".png"):
                        try:
                            validate_png(reader.read(asset.path))
                        except (OSError, ValueError) as exc:
                            texture_diagnostics.append(
                                Diagnostic("INVALID_TEXTURE", Severity.ERROR, str(exc), asset.path)
                            )
                manifest = replace(
                    manifest, diagnostics=manifest.diagnostics + tuple(texture_diagnostics)
                )
                for bundle in manifest.bundles:
                    rows: dict[str, JSONDocument] = {}
                    asset = next(a for a in manifest.assets if a.path == bundle.bundle_id)
                    if asset.kind in ("skeleton_json", "skeleton_binary") and asset.spine_version:
                        try:
                            payload = reader.read(asset.path)
                            if asset.kind == "skeleton_binary":
                                decoded = (
                                    BinaryCodecRegistry()
                                    .codec(asset.spine_version, experimental=True)
                                    .decode(payload)
                                )
                                payload = _json_bytes(decoded)
                            canonical = SkeletonConverter().read(payload)
                            features = inspect_features(canonical.semantic, canonical.document)
                            if bundle.atlases:
                                features |= {SourceFeature.ATLAS}
                            for target in sorted(SUPPORTED_PATCH_VERSIONS):
                                plan = ConversionPlanner().structural_plan(
                                    asset.spine_version, target
                                )
                                rows[target] = dict(
                                    QualificationService()
                                    .evaluate(asset.spine_version, target, plan.route, features)
                                    .to_json()
                                )
                                rows[target]["structural_route_available"] = bool(plan.route)
                                rows[target]["route"] = plan.route
                                rows[target]["source_risk_authorization_required"] = (
                                    asset.spine_version in KNOWN_EXPORT_ISSUE_PATCHES
                                )
                                rows[target]["target_formats"] = ("json",) + tuple(
                                    "binary"
                                    for c in BinaryCodecRegistry().capabilities()
                                    if c.version == target and c.encode
                                )
                        except (ValueError, UnicodeError) as exc:
                            manifest = replace(
                                manifest,
                                diagnostics=manifest.diagnostics
                                + (
                                    Diagnostic(
                                        "CONVERSION_SOURCE_UNSUPPORTED",
                                        Severity.WARNING,
                                        f"B2 source admission rejected: {exc}",
                                        asset.path,
                                        suggestion="Review source data and feature coverage",
                                    ),
                                ),
                            )
                    targets[bundle.bundle_id] = rows
            return BundleInspection(
                manifest,
                {b.bundle_id: _state(manifest, b.bundle_id) for b in manifest.bundles},
                targets,
            )

    def list_bundles(self, source: SourceSelection) -> BundleInspection:
        return self.inspect_source(source)

    def plan_conversion(self, request: BundleRequest) -> BundleResult:
        return self._run(request, dry_run=True)

    def convert_bundle(
        self,
        request: BundleRequest,
        *,
        progress: Callable[[ProgressEvent], None] | None = None,
        cancellation: CancellationToken | None = None,
    ) -> BundleResult:
        return self._run(request, progress=progress, cancellation=cancellation)

    def write_report(self, result: BundleResult, output: Path) -> None:
        """Explicit sidecar export, a separate no-overwrite atomic publication.

        The package job result remains authoritative if a caller's report export fails.
        """
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=".fnx-report-", dir=output.parent) as directory:
            staged = Path(directory) / "report.json"
            staged.write_bytes(_json_bytes(result.to_dict()))
            os.link(staged, output)

    def convert_batch(self, requests: tuple[BundleRequest, ...]) -> tuple[BundleResult, ...]:
        return tuple(self.convert_bundle(request) for request in requests)

    def _run(
        self,
        request: BundleRequest,
        *,
        dry_run: bool = False,
        progress: Callable[[ProgressEvent], None] | None = None,
        cancellation: CancellationToken | None = None,
    ) -> BundleResult:
        current = Stage.SCANNING
        asset_id: str | None = None
        report: JSONDocument = {
            "schema_version": 1,
            "input_type": (
                "explicit_files"
                if isinstance(request.source, tuple)
                else "folder"
                if Path(request.source).is_dir()
                else "zip"
            ),
            "source": str(request.source),
            "target": request.target,
            "target_format": request.skeleton_format,
            "experimental_authorized": request.experimental_structural,
            "source_risk_policy": request.source_risk_policy.value,
            "retention": request.retention.value,
            "package_mode": request.package_mode.value,
            "publication": "not_published",
            "runtime_verification": "not_run",
            "visual_verification": "not_run",
            "bundles": [],
            "structural_validation": "not_run",
            "package_integrity": "not_run",
            "output": str(request.output),
        }

        def emit(stage: Stage, name: str | None = None) -> None:
            nonlocal current, asset_id
            current, asset_id = stage, name
            if cancellation is not None and cancellation.cancelled:
                raise _Cancelled
            if progress is not None:
                try:
                    progress(ProgressEvent(stage, name))
                except Exception as exc:
                    raise ValueError("Progress callback failed") from exc
            if cancellation is not None and cancellation.cancelled:
                raise _Cancelled

        published = False
        try:
            emit(Stage.SCANNING)
            if request.skeleton_format not in ("json", "binary"):
                raise ValueError("Skeleton output format must be json or binary")
            if request.skeleton_format == "binary":
                BinaryCodecRegistry().codec(
                    request.target, experimental=request.experimental_structural
                )
            with _source(request.source) as origin:
                # Snapshot the bounded source once. Conversion and hashes consume the same bytes.
                with tempfile.TemporaryDirectory(prefix="fnx-bundle-input-") as directory:
                    snapshot = Path(directory)
                    with AssetSource(origin) as reader:
                        inputs: dict[str, bytes] = {}
                        for source_name in reader.names():
                            emit(Stage.SCANNING, source_name)
                            inputs[source_name] = reader.read(source_name)
                    _write_files(snapshot, inputs)
                    report["input_checksums"] = _hashes(inputs)
                    emit(Stage.DISCOVERING)
                    source_names: dict[str, str] = {}
                    for name in sorted(inputs):
                        if not name.lower().endswith(".skel"):
                            continue
                        if request.bundle_ids and name not in request.bundle_ids:
                            continue
                        registry = BinaryCodecRegistry()
                        version = registry.probe(inputs[name])
                        decoded = registry.codec(
                            version, experimental=request.experimental_structural
                        ).decode(inputs[name])
                        json_name = str(PurePosixPath(name).with_suffix(".json"))
                        if json_name in inputs:
                            raise ValueError("Binary to JSON filename collides with an input asset")
                        (snapshot / name).unlink()
                        (snapshot / json_name).write_bytes(_json_bytes(decoded))
                        source_names[json_name] = name
                    names_to_json = {v: k for k, v in source_names.items()}
                    mapped = DependencyMappings(
                        {names_to_json.get(k, k): v for k, v in request.mappings.atlases.items()},
                        request.mappings.textures,
                    )
                    inspection = _inspection(mapped)
                    manifest = _manifest_source(
                        inspection.inspect(str(snapshot)), str(request.source)
                    )
                    if not manifest.assets:
                        raise ValueError("Input inspection failed or no files were discovered")
                    ids = tuple(names_to_json.get(n, n) for n in request.bundle_ids) or tuple(
                        b.bundle_id for b in manifest.bundles
                    )
                    if not ids or len(ids) != len(set(ids)):
                        raise ValueError("Select at least one unique logical bundle")
                    known = {b.bundle_id for b in manifest.bundles}
                    if set(ids) - known:
                        raise ValueError("Selected bundle ID was not discovered")
                    report["source_risk_status"] = {
                        a.path: (
                            "known_export_issue"
                            if a.spine_version in KNOWN_EXPORT_ISSUE_PATCHES
                            else "no_known_issue_in_registry"
                        )
                        for a in manifest.assets
                        if a.kind in ("skeleton_json", "skeleton_binary")
                    }
                    report["dependency_mappings"] = {
                        "atlases": dict(request.mappings.atlases),
                        "textures": tuple(
                            {"atlas": k[0], "page": k[1], "replacement": v}
                            for k, v in sorted(request.mappings.textures.items())
                        ),
                    }
                    report["discovered_bundle_ids"] = tuple(
                        sorted(source_names.get(n, n) for n in known)
                    )
                    report["selected_bundle_ids"] = tuple(source_names.get(n, n) for n in ids)
                    emit(Stage.VALIDATING)
                    if any(_state(manifest, name) != BundleState.READY for name in ids):
                        report["inspection"] = manifest.to_dict()
                        raise ValueError("Resolve selected bundle dependencies before conversion")
                    emit(Stage.PLANNING)
                    outputs: dict[str, bytes] = {}
                    rows: list[JSONValue] = []
                    failed = False
                    for name in sorted(ids):
                        emit(Stage.PLANNING, name)
                        outcome = AssetSetConverter(
                            inspection=inspection,
                            stage_callback=lambda stage: emit(Stage(stage), name),
                            experimental_structural=request.experimental_structural,
                        ).convert(
                            snapshot,
                            name,
                            request.target,
                            source_risk_policy=request.source_risk_policy,
                        )
                        row = _outcome(source_names.get(name, name), outcome)
                        if name in source_names:
                            row["source_format"] = "binary"
                        row["binary_codec_verification"] = (
                            "experimental_hierarchy_only"
                            if name in source_names or request.skeleton_format == "binary"
                            else "not_applicable"
                        )
                        rows.append(row)
                        if outcome.outputs is None:
                            failed = True
                            continue
                        for path, payload in outcome.outputs.items():
                            if path in outputs and outputs[path] != payload:
                                raise ValueError(
                                    "Selected bundles produce conflicting shared assets"
                                )
                            outputs[path] = payload
                    report["bundles"] = rows
                    if failed:
                        raise ValueError(
                            "One or more selected bundles rejected conversion; no output published"
                        )
                    selected_json_ids = ids
                    selected_sources = {source_names.get(name, name) for name in ids}
                    consumed = set(selected_sources)
                    for logical in manifest.bundles:
                        if logical.bundle_id in ids:
                            consumed.update((*logical.atlases, *logical.texture_pages))
                    if request.retention == RetentionPolicy.ALL:
                        outputs = {
                            **{n: data for n, data in inputs.items() if n not in selected_sources},
                            **outputs,
                        }
                    report["excluded_files"] = (
                        tuple(sorted(set(inputs) - consumed - set(outputs)))
                        if request.retention == RetentionPolicy.REQUIRED_ONLY
                        else ()
                    )
                    outputs = _portable(
                        outputs, manifest, ids, retain_all=request.retention == RetentionPolicy.ALL
                    )
                    if request.skeleton_format == "binary":
                        codec = BinaryCodecRegistry().codec(
                            request.target, experimental=request.experimental_structural
                        )
                        output_ids: list[str] = []
                        for name in ids:
                            document = SkeletonConverter().read(outputs.pop(name)).document
                            binary_name = str(PurePosixPath(name).with_suffix(".skel"))
                            if binary_name in outputs:
                                raise ValueError("Binary output filename collision")
                            outputs[binary_name] = codec.encode(document)
                            output_ids.append(binary_name)
                        ids = tuple(output_ids)
                    report["file_renames"] = {
                        source_names.get(source_id, source_id): output_id
                        for source_id, output_id in zip(selected_json_ids, ids)
                        if source_names.get(source_id, source_id) != output_id
                    }
                    report["files_generated"] = tuple(sorted(set(outputs) - set(inputs)))
                    report["output_checksums"] = _hashes(outputs)
                    report["files_preserved"] = tuple(
                        sorted(n for n in outputs if inputs.get(n) == outputs[n])
                    )
                    report["files_transformed"] = tuple(
                        sorted(n for n in outputs if n in inputs and inputs[n] != outputs[n])
                    )
                    emit(Stage.VERIFYING)
                    for texture_path, texture_bytes in outputs.items():
                        if texture_path.lower().endswith(".png"):
                            emit(Stage.VERIFYING, texture_path)
                            validate_png(texture_bytes)
                    report["texture_integrity"] = "png_signature_chunks_crc"
                    with tempfile.TemporaryDirectory(prefix="fnx-bundle-verify-") as verify:
                        _write_files(Path(verify), outputs)
                        _validate(Path(verify), ids)
                    report["structural_validation"] = "passed"
                    if dry_run:
                        return BundleResult(JobStatus.PLANNED, False, report)
                    emit(Stage.PACKAGING)
                    destination = request.output.absolute()
                    if destination.exists() or destination.is_symlink():
                        raise FileExistsError("Output destination is occupied")
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    # Audit reports live inside audit packages; viewer packages contain assets only.
                    report["package_integrity"] = "not_run"
                    packaged = dict(outputs)
                    if request.package_mode == PackageMode.AUDIT:
                        if "fnx-conversion-report.json" in packaged:
                            raise ValueError("Audit report filename collides with an input asset")
                        snapshot_report = dict(report)
                        snapshot_report["report_scope"] = "prepublication_validation"
                        packaged["fnx-conversion-report.json"] = _json_bytes(snapshot_report)
                    report["packaged_file_checksums"] = _hashes(packaged)
                    with tempfile.TemporaryDirectory(
                        prefix=f".{destination.name}.", dir=destination.parent
                    ) as stage:
                        stage_root = Path(stage)
                        payload_root = stage_root / "payload"
                        payload_root.mkdir()
                        _write_files(payload_root, packaged)
                        _validate(payload_root, ids)
                        if destination.suffix.lower() == ".zip":
                            archive = stage_root / "package.zip"
                            with ZipFile(
                                archive, "w", compression=ZIP_DEFLATED, compresslevel=9
                            ) as writer:
                                for name, data in sorted(packaged.items()):
                                    info = ZipInfo(
                                        canonical_path(name), date_time=(1980, 1, 1, 0, 0, 0)
                                    )
                                    info.create_system = 3
                                    info.external_attr = 0o100644 << 16
                                    info.compress_type = ZIP_DEFLATED
                                    writer.writestr(info, data, compresslevel=9)
                            with ZipFile(archive) as reader_zip:
                                if reader_zip.testzip() is not None:
                                    raise ValueError("Generated ZIP failed CRC verification")
                            with AssetSource(archive) as reader:
                                if {n: reader.read(n) for n in reader.names()} != packaged:
                                    raise ValueError("Generated ZIP differs from staged assets")
                            _validate(archive, ids)
                            with archive.open("rb") as stream:
                                report["package_sha256"] = file_digest(stream, "sha256").hexdigest()
                            report["package_integrity"] = "passed"
                            emit(Stage.PUBLISHING)
                            os.link(archive, destination)  # Exclusive, atomic, no overwrite.
                        else:
                            report["package_integrity"] = "passed"
                            emit(Stage.PUBLISHING)
                            _rename_exclusive(payload_root, destination)
                        published = True
                    report["publication"] = "published"
            # Completion callbacks cannot retroactively cancel publication.
            if progress is not None:
                try:
                    progress(ProgressEvent(Stage.COMPLETED))
                except Exception:
                    report["callback_warning"] = "Completion callback failed after publication"
            return BundleResult(JobStatus.COMPLETED, True, report)
        except _Cancelled:
            if progress is not None:
                try:
                    progress(ProgressEvent(Stage.CANCELLED, asset_id))
                except Exception:
                    report["callback_warning"] = "Cancellation callback failed"
            report["diagnostic"] = {
                "code": "CANCELLED",
                "stage": current.value,
                "asset_id": asset_id,
            }
            return BundleResult(JobStatus.CANCELLED, published, report)
        except (OSError, ValueError, UnicodeError) as exc:
            if published:
                report["publication"] = "published"
            report["diagnostic"] = {
                "code": (
                    exc.code
                    if isinstance(exc, BinaryError)
                    else "OUTPUT_EXISTS"
                    if isinstance(exc, FileExistsError)
                    else "FILESYSTEM_ERROR"
                    if isinstance(exc, OSError)
                    else "BUNDLE_REJECTED"
                ),
                "stage": current.value,
                "asset_id": asset_id,
                "message": str(exc),
                "technical_details": str(exc),
                "file_path": asset_id
                or str(
                    request.output
                    if current in (Stage.PACKAGING, Stage.PUBLISHING)
                    else request.source
                ),
                "publication_status": "published" if published else "not_published",
                "suggestion": "Review dependency, qualification and output policies",
            }
            if progress is not None:
                try:
                    progress(ProgressEvent(Stage.FAILED, asset_id))
                except Exception:
                    report["callback_warning"] = "Failure callback failed"
            return BundleResult(JobStatus.FAILED, published, report)


def _outcome(name: str, result: AssetSetResult) -> JSONDocument:
    return {
        "bundle_id": name,
        "execution_success": result.outputs is not None,
        "source_format": "json",
        "source_version": result.source_version,
        "target_version": result.target_version,
        "route": result.route,
        "structural_validation": result.status.value,
        "qualification": result.qualification.to_json() if result.qualification else None,
        "diagnostics": result.diagnostics,
        "details": result.details,
    }


def _hashes(files: Mapping[str, bytes]) -> JSONDocument:
    return {name: sha256(data).hexdigest() for name, data in sorted(files.items())}


def _json_bytes(document: JSONDocument) -> bytes:
    return (json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
        "utf-8"
    )


def _rename_exclusive(source: Path, target: Path) -> None:
    """Use the OS no-replace rename primitive; fail closed on unsupported platforms."""
    import ctypes
    import sys

    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "darwin":
        rename = libc.renamex_np
        rename.argtypes = (ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint)
        result = cast(int, rename(os.fsencode(source), os.fsencode(target), 4))
    elif sys.platform.startswith("linux"):
        rename = libc.renameat2
        rename.argtypes = (
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
        )
        result = cast(int, rename(-100, os.fsencode(source), -100, os.fsencode(target), 1))
    else:
        raise ValueError("Atomic folder publication requires macOS or Linux no-replace rename")
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(target))
