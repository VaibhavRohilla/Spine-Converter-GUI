"""Headless bundle jobs over B1 discovery and B2 asset-set conversion.

Publication is per job. A request selecting several bundles is all-or-nothing;
independent requests have independent destinations and qualification results.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path, PurePosixPath
from zipfile import BadZipFile
from zlib import error as ZlibError

from .atomic_io import file_digests, publish_file, stage_files
from .binary import BinaryCapability, BinaryCodecRegistry, BinaryError
from .bundle_models import (
    BinaryOperation,
    BundleInspection,
    BundleOutcome,
    BundleReport,
    BundleRequest,
    BundleResult,
    BundleState,
    DependencyMappings,
    FileRename,
    JobDiagnostic,
    JobDiagnosticCode,
    JobStatus,
    PackageMode,
    PublicationState,
    RetentionPolicy,
    SkeletonFormat,
    SourceDescriptor,
    SourceRisk,
    TargetInspection,
    TextureVerification,
    VerificationState,
)
from .config import InspectionConfig
from .conversion.asset_set import AssetSetConverter, AssetSetResult
from .conversion.models import ConversionStatus
from .conversion.planner import ConversionPlanner
from .conversion.qualification import QualificationService, SourceFeature, inspect_features
from .conversion.registry import KNOWN_EXPORT_ISSUE_PATCHES, SUPPORTED_PATCH_VERSIONS
from .conversion.skeleton import SkeletonConverter
from .dependencies import resolve_relative_path
from .inspection import InspectionService
from .json_types import encode_json
from .models import AssetManifest, Diagnostic, Severity
from .packaging import PackageBuilder, PackageSettings, validate_package
from .progress import CancellationToken, ProgressEvent, Stage
from .source import (
    AssetSource,
    SourceLimits,
    SourceSelection,
)
from .texture import validate_png
from .versions import VersionRegistry

_JOB_ERRORS = (OSError, ValueError, UnicodeError, EOFError, RuntimeError, BadZipFile, ZlibError)


class _Cancelled(Exception):
    pass


@contextmanager
def _source(selection: SourceSelection, limits: SourceLimits) -> Iterator[str]:
    if not isinstance(selection, tuple):
        yield str(selection)
        return
    with tempfile.TemporaryDirectory(prefix="fnx-selection-") as directory:
        with AssetSource(selection, limits) as source:
            stage_files(Path(directory), {name: source.read(name) for name in source.names()})
        yield directory


def _manifest_source(manifest: AssetManifest, location: str) -> AssetManifest:
    return replace(
        manifest,
        source=location,
        assets=tuple(replace(a, source_id=location) for a in manifest.assets),
        bundles=tuple(replace(b, source_location=location) for b in manifest.bundles),
    )


def _inspection(mappings: DependencyMappings, config: InspectionConfig) -> InspectionService:
    return InspectionService(
        config=config, atlas_overrides=mappings.atlases, texture_overrides=mappings.textures
    )


def _state(manifest: AssetManifest, bundle_id: str) -> BundleState:
    bundle = next(b for b in manifest.bundles if b.bundle_id == bundle_id)
    asset = next(a for a in manifest.assets if a.path == bundle_id)
    paths = {bundle_id, *bundle.atlases, *bundle.texture_pages}
    diagnostics = [d for d in manifest.diagnostics if d.path is None or d.path in paths]
    if any(
        d.severity in (Severity.ERROR, Severity.BLOCKER)
        and not d.code.startswith(("AMBIGUOUS", "MISSING"))
        for d in diagnostics
    ):
        return BundleState.INVALID
    if VersionRegistry().family_for(asset.spine_version) is None or (
        asset.kind == "skeleton_binary" and not asset.metadata.get("binary_decoded")
    ):
        return BundleState.UNSUPPORTED
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
            name = resolve_relative_path(dep.requested, dep.owner)
            if name is None:
                raise ValueError("Texture reference escapes package or is unsafe")
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


class BundleService:
    def __init__(
        self,
        inspection_config: InspectionConfig | None = None,
        package_settings: PackageSettings | None = None,
    ) -> None:
        self.inspection_config = inspection_config or InspectionConfig()
        self.packages = PackageBuilder(self.inspection_config, package_settings)

    def inspect_source(
        self, source: SourceSelection, mappings: DependencyMappings | None = None
    ) -> BundleInspection:
        try:
            return self._inspect_source(source, mappings)
        except _JOB_ERRORS as exc:
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
        with _source(source, self.inspection_config.source_limits) as origin:
            manifest = _inspection(
                mappings or DependencyMappings(), self.inspection_config
            ).inspect(origin)
            manifest = _manifest_source(manifest, SourceDescriptor.from_selection(source).label)
            targets: dict[str, dict[str, TargetInspection]] = {}
            if not manifest.assets:
                return BundleInspection(manifest, {}, targets)
            with AssetSource(origin, self.inspection_config.source_limits) as reader:
                texture_diagnostics: list[Diagnostic] = []
                for asset in manifest.assets:
                    if asset.kind == "texture" and asset.path.lower().endswith(".png"):
                        try:
                            validate_png(
                                reader.read(asset.path), self.packages.settings.texture_limits
                            )
                        except (OSError, ValueError) as exc:
                            texture_diagnostics.append(
                                Diagnostic("INVALID_TEXTURE", Severity.ERROR, str(exc), asset.path)
                            )
                manifest = replace(
                    manifest, diagnostics=manifest.diagnostics + tuple(texture_diagnostics)
                )
                for bundle in manifest.bundles:
                    rows: dict[str, TargetInspection] = {}
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
                                payload = encode_json(decoded)
                            canonical = SkeletonConverter().read(payload)
                            features = inspect_features(canonical.semantic, canonical.document)
                            if bundle.atlases:
                                features |= {SourceFeature.ATLAS}
                            for target in sorted(SUPPORTED_PATCH_VERSIONS):
                                plan = ConversionPlanner().structural_plan(
                                    asset.spine_version, target
                                )
                                rows[target] = TargetInspection(
                                    qualification=QualificationService().evaluate(
                                        asset.spine_version, target, plan.route, features
                                    ),
                                    route=plan.route,
                                    source_risk_authorization_required=(
                                        asset.spine_version in KNOWN_EXPORT_ISSUE_PATCHES
                                    ),
                                    target_formats=(SkeletonFormat.JSON,)
                                    + tuple(
                                        SkeletonFormat.BINARY
                                        for c in BinaryCodecRegistry().capabilities()
                                        if c.version == target and c.encode
                                    ),
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
            staged.write_bytes(encode_json(result.to_dict()))
            publish_file(staged, output)

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
        report = BundleReport(
            source=SourceDescriptor.from_selection(request.source),
            target=request.target,
            target_format=request.skeleton_format,
            output=request.output.absolute(),
            experimental_authorized=request.experimental_structural,
            source_risk_policy=request.source_risk_policy,
            retention=request.retention,
            package_mode=request.package_mode,
            container=request.container,
            selected_bundle_ids=request.bundle_ids,
            bundles=tuple(BundleOutcome(n) for n in sorted(request.bundle_ids)),
        )

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
            if request.skeleton_format == SkeletonFormat.BINARY:
                BinaryCodecRegistry().codec(
                    request.target,
                    limits=self.inspection_config.binary_limits,
                    experimental=request.experimental_structural,
                )
            with _source(request.source, self.inspection_config.source_limits) as origin:
                # Snapshot the bounded source once. Conversion and hashes consume the same bytes.
                with tempfile.TemporaryDirectory(prefix="fnx-bundle-input-") as directory:
                    snapshot = Path(directory)
                    with AssetSource(origin, self.inspection_config.source_limits) as reader:
                        inputs: dict[str, bytes] = {}
                        for source_name in reader.names():
                            emit(Stage.SCANNING, source_name)
                            inputs[source_name] = reader.read(source_name)
                    stage_files(snapshot, inputs)
                    report = replace(report, input_checksums=file_digests(inputs))
                    emit(Stage.DISCOVERING)
                    source_names: dict[str, str] = {}
                    source_codecs: dict[str, BinaryCapability] = {}
                    for name in sorted(inputs):
                        if not name.lower().endswith(".skel"):
                            continue
                        if request.bundle_ids and name not in request.bundle_ids:
                            continue
                        emit(Stage.DISCOVERING, name)
                        registry = BinaryCodecRegistry()
                        version = registry.probe(
                            inputs[name], limits=self.inspection_config.binary_limits
                        )
                        decoder = registry.codec(
                            version,
                            limits=self.inspection_config.binary_limits,
                            experimental=request.experimental_structural,
                        )
                        decoded = decoder.decode(inputs[name])
                        json_name = str(PurePosixPath(name).with_suffix(".json"))
                        if json_name in inputs:
                            raise ValueError("Binary to JSON filename collides with an input asset")
                        (snapshot / name).unlink()
                        (snapshot / json_name).write_bytes(encode_json(decoded))
                        source_names[json_name] = name
                        source_codecs[json_name] = decoder.capability
                    names_to_json = {v: k for k, v in source_names.items()}
                    mapped = DependencyMappings(
                        {names_to_json.get(k, k): v for k, v in request.mappings.atlases.items()},
                        request.mappings.textures,
                    )
                    inspection = _inspection(mapped, self.inspection_config)
                    manifest = _manifest_source(
                        inspection.inspect(str(snapshot)), report.source.label
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
                    report = replace(
                        report,
                        source_risk_status=tuple(
                            SourceRisk(a.path, a.spine_version in KNOWN_EXPORT_ISSUE_PATCHES)
                            for a in manifest.assets
                            if a.kind in ("skeleton_json", "skeleton_binary")
                        ),
                        dependency_mappings=request.mappings,
                    )
                    report = replace(
                        report,
                        discovered_bundle_ids=tuple(sorted(source_names.get(n, n) for n in known)),
                    )
                    report = replace(
                        report, selected_bundle_ids=tuple(source_names.get(n, n) for n in ids)
                    )
                    rows = [BundleOutcome(source_names.get(n, n)) for n in sorted(ids)]
                    report = replace(report, bundles=tuple(rows))
                    emit(Stage.VALIDATING)
                    if any(_state(manifest, name) != BundleState.READY for name in ids):
                        report = replace(report, inspection=manifest)
                        raise ValueError("Resolve selected bundle dependencies before conversion")
                    emit(Stage.PLANNING)
                    outputs: dict[str, bytes] = {}
                    failed = False
                    for index, name in enumerate(sorted(ids)):
                        emit(Stage.PLANNING, name)
                        outcome = AssetSetConverter(
                            inspection=inspection,
                            stage_callback=lambda stage: emit(stage, name),
                            experimental_structural=request.experimental_structural,
                        ).convert(
                            snapshot,
                            name,
                            request.target,
                            source_risk_policy=request.source_risk_policy,
                        )
                        row = _outcome(source_names.get(name, name), outcome)
                        row = replace(
                            row,
                            source_format=(
                                SkeletonFormat.BINARY
                                if name in source_names
                                else SkeletonFormat.JSON
                            ),
                            binary_decode=(
                                BinaryOperation(source_codecs[name], VerificationState.PASSED)
                                if name in source_codecs
                                else None
                            ),
                            binary_encode=(
                                BinaryOperation(
                                    BinaryCodecRegistry()
                                    .codec(
                                        request.target,
                                        limits=self.inspection_config.binary_limits,
                                        experimental=request.experimental_structural,
                                    )
                                    .capability
                                )
                                if request.skeleton_format == SkeletonFormat.BINARY
                                else None
                            ),
                            execution_success=(
                                None
                                if outcome.outputs is not None
                                and request.skeleton_format == SkeletonFormat.BINARY
                                else outcome.outputs is not None
                            ),
                        )
                        rows[index] = row
                        report = replace(report, bundles=tuple(rows))
                        if outcome.outputs is None:
                            failed = True
                            continue
                        emit(Stage.VALIDATING, name)
                        for path, payload in outcome.outputs.items():
                            if path in outputs and outputs[path] != payload:
                                failed = True
                                row = replace(
                                    row,
                                    merge_diagnostic=JobDiagnostic(
                                        code=JobDiagnosticCode.SHARED_OUTPUT_CONFLICT,
                                        stage=Stage.VALIDATING,
                                        file_path=path,
                                        asset_id=row.bundle_id,
                                        message="Conflicting shared outputs from selected bundles",
                                    ),
                                )
                                rows[index] = row
                                report = replace(report, bundles=tuple(rows))
                                continue
                            outputs[path] = payload
                    report = replace(report, bundles=tuple(rows))
                    if failed:
                        raise ValueError(
                            "Selected bundles failed conversion or output merging; "
                            "no output published"
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
                    report = replace(
                        report,
                        excluded_files=tuple(sorted(set(inputs) - consumed - set(outputs)))
                        if request.retention == RetentionPolicy.REQUIRED_ONLY
                        else (),
                    )
                    outputs = _portable(
                        outputs, manifest, ids, retain_all=request.retention == RetentionPolicy.ALL
                    )
                    if request.skeleton_format == SkeletonFormat.BINARY:
                        codec = BinaryCodecRegistry().codec(
                            request.target,
                            limits=self.inspection_config.binary_limits,
                            experimental=request.experimental_structural,
                        )
                        output_ids: list[str] = []
                        row_indexes = {name: index for index, name in enumerate(sorted(ids))}
                        for name in ids:
                            emit(Stage.CONVERTING_SKELETON, source_names.get(name, name))
                            document = SkeletonConverter().read(outputs.pop(name)).document
                            binary_name = str(PurePosixPath(name).with_suffix(".skel"))
                            if binary_name in outputs:
                                raise ValueError("Binary output filename collision")
                            index = row_indexes[name]
                            try:
                                outputs[binary_name] = codec.encode(document)
                            except BinaryError as exc:
                                rows[index] = replace(
                                    rows[index],
                                    execution_success=False,
                                    structural_validation=ConversionStatus.REJECTED,
                                    binary_encode=BinaryOperation(
                                        codec.capability, VerificationState.FAILED, exc.code
                                    ),
                                    diagnostics=rows[index].diagnostics + (str(exc),),
                                )
                                report = replace(report, bundles=tuple(rows))
                                raise
                            rows[index] = replace(
                                rows[index],
                                execution_success=True,
                                binary_encode=BinaryOperation(
                                    codec.capability, VerificationState.PASSED
                                ),
                            )
                            report = replace(report, bundles=tuple(rows))
                            output_ids.append(binary_name)
                        ids = tuple(output_ids)
                    report = replace(
                        report,
                        file_renames=tuple(
                            FileRename(source_names.get(source_id, source_id), output_id)
                            for source_id, output_id in zip(selected_json_ids, ids)
                            if source_names.get(source_id, source_id) != output_id
                        ),
                    )
                    report = replace(
                        report, files_generated=tuple(sorted(set(outputs) - set(inputs)))
                    )
                    report = replace(report, output_checksums=file_digests(outputs))
                    report = replace(
                        report,
                        files_preserved=tuple(
                            sorted(n for n in outputs if inputs.get(n) == outputs[n])
                        ),
                    )
                    report = replace(
                        report,
                        files_transformed=tuple(
                            sorted(n for n in outputs if n in inputs and inputs[n] != outputs[n])
                        ),
                    )
                    emit(Stage.VERIFYING)
                    for texture_path, texture_bytes in outputs.items():
                        if texture_path.lower().endswith(".png"):
                            emit(Stage.VERIFYING, texture_path)
                            validate_png(texture_bytes, self.packages.settings.texture_limits)
                    report = replace(report, texture_integrity=TextureVerification.PNG_STRUCTURAL)
                    with tempfile.TemporaryDirectory(prefix="fnx-bundle-verify-") as verify:
                        stage_files(Path(verify), outputs)
                        validate_package(
                            Path(verify),
                            ids,
                            self.inspection_config,
                            self.packages.settings.texture_limits,
                        )
                    report = replace(report, structural_validation=VerificationState.PASSED)
                    if dry_run:
                        return BundleResult(JobStatus.PLANNED, False, report)
                    emit(Stage.PACKAGING)
                    receipt = self.packages.publish(
                        outputs,
                        ids,
                        request.output.absolute(),
                        request.container,
                        audit_report=report if request.package_mode == PackageMode.AUDIT else None,
                        before_publish=lambda: emit(Stage.PUBLISHING),
                    )
                    published = True
                    report = replace(
                        report,
                        packaged_file_checksums=receipt.files,
                        package_sha256=receipt.package_sha256,
                        cleanup_warning=receipt.cleanup_warning,
                        package_integrity=VerificationState.PASSED,
                    )
                    report = replace(report, publication=PublicationState.PUBLISHED)
            # Completion callbacks cannot retroactively cancel publication.
            if progress is not None:
                try:
                    progress(ProgressEvent(Stage.COMPLETED))
                except Exception:
                    report = replace(
                        report, callback_warning="Completion callback failed after publication"
                    )
            return BundleResult(JobStatus.COMPLETED, True, report)
        except _Cancelled:
            if progress is not None:
                try:
                    progress(ProgressEvent(Stage.CANCELLED, asset_id))
                except Exception:
                    report = replace(report, callback_warning="Cancellation callback failed")
            report = replace(
                report,
                diagnostic=JobDiagnostic(
                    code=JobDiagnosticCode.CANCELLED,
                    stage=current,
                    asset_id=asset_id,
                    message="Conversion cancelled before publication",
                    file_path=asset_id,
                ),
            )
            return BundleResult(JobStatus.CANCELLED, published, report)
        except _JOB_ERRORS as exc:
            if published:
                report = replace(
                    report, publication=PublicationState.PUBLISHED, cleanup_warning=str(exc)
                )
                if progress is not None:
                    try:
                        progress(ProgressEvent(Stage.COMPLETED))
                    except Exception:
                        report = replace(report, callback_warning="Completion callback failed")
                return BundleResult(JobStatus.COMPLETED, True, report)
            report = replace(
                report,
                diagnostic=JobDiagnostic(
                    code=exc.code
                    if isinstance(exc, BinaryError)
                    else JobDiagnosticCode.INPUT_NESTING_LIMIT
                    if isinstance(exc, RecursionError)
                    else JobDiagnosticCode.OUTPUT_EXISTS
                    if isinstance(exc, FileExistsError)
                    else JobDiagnosticCode.FILESYSTEM_ERROR
                    if isinstance(exc, OSError)
                    else JobDiagnosticCode.BUNDLE_REJECTED,
                    stage=current,
                    asset_id=asset_id,
                    message="Input exceeds supported nesting"
                    if isinstance(exc, RecursionError)
                    else str(exc),
                    technical_details=str(exc),
                    file_path=asset_id
                    or str(
                        request.output
                        if current in (Stage.PACKAGING, Stage.PUBLISHING)
                        else request.source
                    ),
                    publication_status=PublicationState.PUBLISHED
                    if published
                    else PublicationState.NOT_PUBLISHED,
                    suggestion="Review dependency, qualification and output policies",
                ),
            )
            if progress is not None:
                try:
                    progress(ProgressEvent(Stage.FAILED, asset_id))
                except Exception:
                    report = replace(report, callback_warning="Failure callback failed")
            return BundleResult(JobStatus.FAILED, published, report)


def _outcome(name: str, result: AssetSetResult) -> BundleOutcome:
    return BundleOutcome(
        bundle_id=name,
        source_format=SkeletonFormat.JSON,
        execution_success=result.outputs is not None,
        source_version=result.source_version,
        target_version=result.target_version,
        route=result.route,
        structural_validation=result.status,
        qualification=result.qualification,
        diagnostics=result.diagnostics,
        details=result.details,
    )
