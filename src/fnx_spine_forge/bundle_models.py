"""Canonical strongly typed B3 contracts; JSON is a serialization boundary only."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType

from .binary import BinaryCapability, BinaryCodecRegistry, BinaryErrorCode
from .conversion.models import ConversionStatus, SourceRiskPolicy
from .conversion.qualification import QualificationResult
from .conversion.registry import KNOWN_EXPORT_ISSUE_PATCHES
from .json_types import JSONDocument, JSONObject
from .models import AssetManifest, freeze_json, plain_json
from .progress import Stage
from .source import SourceSelection

BUNDLE_SCHEMA_VERSION = 2


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


class RetentionPolicy(StrEnum):
    REQUIRED_ONLY = "required_only"
    ALL = "all"


class PackageContainer(StrEnum):
    ZIP = "zip"
    FOLDER = "folder"


class PackageMode(StrEnum):
    VIEWER = "viewer"
    AUDIT = "audit"


@dataclass(frozen=True, slots=True)
class DependencyMappings:
    atlases: Mapping[str, str] = field(default_factory=dict)
    textures: Mapping[tuple[str, str], str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        atlases: Mapping[str, str] = MappingProxyType(dict(self.atlases))
        textures: Mapping[tuple[str, str], str] = MappingProxyType(dict(self.textures))
        object.__setattr__(self, "atlases", atlases)
        object.__setattr__(self, "textures", textures)


@dataclass(frozen=True, slots=True)
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
    container: PackageContainer = PackageContainer.ZIP
    skeleton_format: SkeletonFormat = SkeletonFormat.JSON

    def __post_init__(self) -> None:
        if not isinstance(self.source, (str, Path, tuple)):
            raise TypeError("source must be a path or explicit Path tuple")
        if isinstance(self.source, tuple) and any(not isinstance(p, Path) for p in self.source):
            raise TypeError("Explicit selections must contain Path values")
        if type(self.experimental_structural) is not bool:
            raise TypeError("experimental authorization must be a boolean")
        if not isinstance(self.mappings, DependencyMappings):
            raise TypeError("mappings must be DependencyMappings")
        if not isinstance(self.container, PackageContainer):
            raise TypeError("container must be PackageContainer")
        if not isinstance(self.output, Path):
            raise TypeError("Bundle output must be a Path")
        if self.container == PackageContainer.ZIP and self.output.suffix.lower() != ".zip":
            raise ValueError("ZIP output destination must have a .zip extension")
        if not isinstance(self.skeleton_format, SkeletonFormat):
            raise TypeError("skeleton_format must be SkeletonFormat")
        if not isinstance(self.package_mode, PackageMode):
            raise TypeError("package_mode must be PackageMode")
        if not isinstance(self.retention, RetentionPolicy):
            raise TypeError("retention must be RetentionPolicy")
        if not isinstance(self.source_risk_policy, SourceRiskPolicy):
            raise TypeError("source_risk_policy must be SourceRiskPolicy")
        if not isinstance(self.bundle_ids, tuple):
            raise TypeError("bundle_ids must be a tuple of canonical asset paths")


class VerificationState(StrEnum):
    NOT_RUN = "not_run"
    PASSED = "passed"
    FAILED = "failed"


class TextureVerification(StrEnum):
    NOT_RUN = "not_run"
    PNG_STRUCTURAL = "png_header_crc_deflate_scanlines"


class PublicationState(StrEnum):
    NOT_PUBLISHED = "not_published"
    PUBLISHED = "published"


class SourceKind(StrEnum):
    EXPLICIT_FILES = "explicit_files"
    FOLDER = "folder"
    ZIP = "zip"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class SourceDescriptor:
    kind: SourceKind
    locations: tuple[Path, ...]

    @classmethod
    def from_selection(cls, selection: SourceSelection) -> SourceDescriptor:
        if isinstance(selection, tuple):
            return cls(SourceKind.EXPLICIT_FILES, tuple(path.absolute() for path in selection))
        path = Path(selection).absolute()
        kind = (
            SourceKind.FOLDER
            if path.is_dir()
            else SourceKind.ZIP
            if path.suffix.lower() == ".zip"
            else SourceKind.UNSUPPORTED
        )
        return cls(kind, (path,))

    @property
    def label(self) -> str:
        return "; ".join(str(path) for path in self.locations)


@dataclass(frozen=True, slots=True)
class FileDigest:
    path: str
    sha256: str


@dataclass(frozen=True, slots=True)
class FileRename:
    source: str
    target: str


@dataclass(frozen=True, slots=True)
class SourceRisk:
    path: str
    known_export_issue: bool


class JobDiagnosticCode(StrEnum):
    CANCELLED = "CANCELLED"
    SHARED_OUTPUT_CONFLICT = "SHARED_OUTPUT_CONFLICT"
    INPUT_NESTING_LIMIT = "INPUT_NESTING_LIMIT"
    OUTPUT_EXISTS = "OUTPUT_EXISTS"
    FILESYSTEM_ERROR = "FILESYSTEM_ERROR"
    BUNDLE_REJECTED = "BUNDLE_REJECTED"


@dataclass(frozen=True, slots=True)
class JobDiagnostic:
    code: JobDiagnosticCode | BinaryErrorCode
    stage: Stage
    message: str
    asset_id: str | None = None
    file_path: str | None = None
    technical_details: str | None = None
    suggestion: str | None = None
    publication_status: PublicationState = PublicationState.NOT_PUBLISHED

    def to_dict(self) -> JSONDocument:
        return {
            "code": self.code.value,
            "stage": self.stage.value,
            "message": self.message,
            "asset_id": self.asset_id,
            "file_path": self.file_path,
            "technical_details": self.technical_details,
            "suggestion": self.suggestion,
            "publication_status": self.publication_status.value,
        }


@dataclass(frozen=True, slots=True)
class BinaryOperation:
    capability: BinaryCapability
    verification: VerificationState = VerificationState.NOT_RUN
    error: BinaryErrorCode | None = None

    def to_dict(self) -> JSONDocument:
        return {
            "capability": self.capability.to_dict(),
            "verification": self.verification.value,
            "error": self.error.value if self.error else None,
        }


@dataclass(frozen=True, slots=True)
class BundleOutcome:
    bundle_id: str
    execution_success: bool | None = None
    structural_validation: ConversionStatus | VerificationState = VerificationState.NOT_RUN
    source_format: SkeletonFormat | None = None
    source_version: str | None = None
    target_version: str | None = None
    route: tuple[str, ...] = ()
    qualification: QualificationResult | None = None
    diagnostics: tuple[str, ...] = ()
    details: JSONObject | None = None
    binary_decode: BinaryOperation | None = None
    binary_encode: BinaryOperation | None = None
    merge_diagnostic: JobDiagnostic | None = None

    def __post_init__(self) -> None:
        if self.details is not None:
            frozen = freeze_json(self.details)
            if not isinstance(frozen, Mapping):
                raise TypeError("Outcome details must be an admitted JSON object")
            object.__setattr__(self, "details", frozen)

    def to_dict(self) -> JSONDocument:
        return {
            "bundle_id": self.bundle_id,
            "execution_success": self.execution_success,
            "structural_validation": self.structural_validation.value,
            "source_format": self.source_format.value if self.source_format else None,
            "source_version": self.source_version,
            "target_version": self.target_version,
            "route": self.route,
            "qualification": self.qualification.to_json() if self.qualification else None,
            "diagnostics": self.diagnostics,
            "details": plain_json(self.details),
            "binary_codec_verification": {
                "decode": self.binary_decode.to_dict() if self.binary_decode else None,
                "encode": self.binary_encode.to_dict() if self.binary_encode else None,
            },
            "merge_diagnostic": self.merge_diagnostic.to_dict() if self.merge_diagnostic else None,
        }


@dataclass(frozen=True, slots=True)
class TargetInspection:
    qualification: QualificationResult
    route: tuple[str, ...]
    source_risk_authorization_required: bool
    target_formats: tuple[SkeletonFormat, ...]

    def to_dict(self) -> JSONDocument:
        return {
            **self.qualification.to_json(),
            "structural_route_available": bool(self.route),
            "route": self.route,
            "source_risk_authorization_required": self.source_risk_authorization_required,
            "target_formats": tuple(f.value for f in self.target_formats),
        }


@dataclass(frozen=True, slots=True)
class BundleInspection:
    manifest: AssetManifest
    states: Mapping[str, BundleState]
    targets: Mapping[str, Mapping[str, TargetInspection]]

    def __post_init__(self) -> None:
        states: Mapping[str, BundleState] = MappingProxyType(dict(self.states))
        targets: Mapping[str, Mapping[str, TargetInspection]] = MappingProxyType(
            {name: MappingProxyType(dict(rows)) for name, rows in self.targets.items()}
        )
        object.__setattr__(self, "states", states)
        object.__setattr__(self, "targets", targets)

    @property
    def source_state(self) -> BundleState:
        if not self.states:
            return BundleState.UNSUPPORTED if self.manifest.ok else BundleState.INVALID
        # Source state must not depend on source member ordering.
        for state in (
            BundleState.INVALID,
            BundleState.NEEDS_SELECTION,
            BundleState.INCOMPLETE,
            BundleState.UNSUPPORTED,
        ):
            if state in self.states.values():
                return state
        return BundleState.READY if self.manifest.ok else BundleState.INVALID

    def to_dict(self) -> JSONDocument:
        result = self.manifest.to_dict()
        result["bundle_schema_version"] = BUNDLE_SCHEMA_VERSION
        result["binary_capabilities"] = tuple(
            c.to_dict() for c in BinaryCodecRegistry().capabilities()
        )
        result["source_state"] = self.source_state.value
        result["states"] = {k: v.value for k, v in self.states.items()}
        result["targets"] = {
            k: {target: row.to_dict() for target, row in rows.items()}
            for k, rows in self.targets.items()
        }
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


@dataclass(frozen=True, slots=True)
class BundleReport:
    source: SourceDescriptor
    target: str
    target_format: SkeletonFormat
    output: Path
    experimental_authorized: bool
    source_risk_policy: SourceRiskPolicy
    retention: RetentionPolicy
    package_mode: PackageMode
    container: PackageContainer
    publication: PublicationState = PublicationState.NOT_PUBLISHED
    runtime_verification: VerificationState = VerificationState.NOT_RUN
    visual_verification: VerificationState = VerificationState.NOT_RUN
    structural_validation: VerificationState = VerificationState.NOT_RUN
    package_integrity: VerificationState = VerificationState.NOT_RUN
    selected_bundle_ids: tuple[str, ...] = ()
    discovered_bundle_ids: tuple[str, ...] = ()
    bundles: tuple[BundleOutcome, ...] = ()
    input_checksums: tuple[FileDigest, ...] = ()
    output_checksums: tuple[FileDigest, ...] = ()
    packaged_file_checksums: tuple[FileDigest, ...] = ()
    source_risk_status: tuple[SourceRisk, ...] = ()
    dependency_mappings: DependencyMappings = field(default_factory=DependencyMappings)
    excluded_files: tuple[str, ...] = ()
    file_renames: tuple[FileRename, ...] = ()
    files_generated: tuple[str, ...] = ()
    files_preserved: tuple[str, ...] = ()
    files_transformed: tuple[str, ...] = ()
    texture_integrity: TextureVerification = TextureVerification.NOT_RUN
    package_sha256: str | None = None
    cleanup_warning: str | None = None
    callback_warning: str | None = None
    sidecar_error: str | None = None
    inspection: AssetManifest | None = None
    diagnostic: JobDiagnostic | None = None

    def to_dict(self) -> JSONDocument:
        return {
            "schema_version": BUNDLE_SCHEMA_VERSION,
            "source": self.source.label,
            "source_locations": tuple(str(p) for p in self.source.locations),
            "input_type": self.source.kind.value,
            "target": self.target,
            "target_format": self.target_format.value,
            "output": str(self.output),
            "experimental_authorized": self.experimental_authorized,
            "source_risk_policy": self.source_risk_policy.value,
            "retention": self.retention.value,
            "package_mode": self.package_mode.value,
            "container": self.container.value,
            "publication": self.publication.value,
            "runtime_verification": self.runtime_verification.value,
            "visual_verification": self.visual_verification.value,
            "structural_validation": self.structural_validation.value,
            "package_integrity": self.package_integrity.value,
            "selected_bundle_ids": self.selected_bundle_ids,
            "discovered_bundle_ids": self.discovered_bundle_ids,
            "bundles": tuple(row.to_dict() for row in self.bundles),
            "input_checksums": {f.path: f.sha256 for f in self.input_checksums},
            "output_checksums": {f.path: f.sha256 for f in self.output_checksums},
            "packaged_file_checksums": {f.path: f.sha256 for f in self.packaged_file_checksums},
            "source_risk_status": {
                r.path: "known_export_issue"
                if r.known_export_issue
                else "no_known_issue_in_registry"
                for r in self.source_risk_status
            },
            "dependency_mappings": {
                "atlases": dict(self.dependency_mappings.atlases),
                "textures": tuple(
                    {"atlas": k[0], "page": k[1], "replacement": v}
                    for k, v in sorted(self.dependency_mappings.textures.items())
                ),
            },
            "excluded_files": self.excluded_files,
            "file_renames": {r.source: r.target for r in self.file_renames},
            "files_generated": self.files_generated,
            "files_preserved": self.files_preserved,
            "files_transformed": self.files_transformed,
            "texture_integrity": self.texture_integrity.value,
            "package_sha256": self.package_sha256,
            "callback_warning": self.callback_warning,
            "sidecar_error": self.sidecar_error,
            "cleanup_warning": self.cleanup_warning,
            "inspection": self.inspection.to_dict() if self.inspection else None,
            "diagnostic": self.diagnostic.to_dict() if self.diagnostic else None,
        }


@dataclass(frozen=True, slots=True)
class BundleResult:
    status: JobStatus
    published: bool
    report: BundleReport

    def to_dict(self) -> JSONDocument:
        return {
            "status": self.status.value,
            "published": self.published,
            "report": self.report.to_dict(),
        }
