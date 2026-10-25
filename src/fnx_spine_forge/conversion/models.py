"""Typed, immutable conversion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .json_types import JSONDocument, JSONObject
from .semantic import SemanticSkeleton


class ConversionStatus(StrEnum):
    PLANNED = "planned"
    SCHEMA_CONVERTED = "schema_converted"
    STRUCTURALLY_VERIFIED = "structurally_verified"
    REJECTED = "rejected"


class SourceRiskPolicy(StrEnum):
    """Policy for source exports with an official known-defect notice."""

    REJECT_KNOWN_ISSUES = "reject_known_issues"
    ALLOW_WITH_DIAGNOSTIC = "allow_with_diagnostic"


class SemanticQualification(StrEnum):
    """Machine-readable boundary between feature checks and route qualification."""

    NOT_ASSESSED = "not_assessed"
    RESTRICTED_CHECKS_PASSED = "restricted_checks_passed"
    NOT_END_TO_END_QUALIFIED = "not_end_to_end_qualified"
    IDENTITY_ONLY = "identity_only"
    REJECTED = "rejected"


@dataclass(frozen=True)
class CanonicalSkeleton:
    """Lossless JSON document plus typed indexes used for semantic checks."""

    version: str
    document: JSONDocument
    bones: tuple[str, ...]
    slots: tuple[str, ...]
    skins: tuple[str, ...]
    animations: tuple[str, ...]
    semantic: SemanticSkeleton


@dataclass(frozen=True)
class ConversionResult:
    source_version: str | None
    target_version: str
    route: tuple[str, ...]
    output: bytes | None
    status: ConversionStatus
    diagnostics: tuple[str, ...] = ()
    statistics: dict[str, int | float] | None = None
    details: JSONObject | None = None
    unsupported_features: tuple[str, ...] = ()
    runtime_verified: bool = False
    visually_verified: bool = False
    diagnostic_codes: tuple[str, ...] = ()
    provenance: JSONObject | None = None
    feature_compatibility: dict[str, str] | None = None
    semantic_qualification: SemanticQualification = SemanticQualification.NOT_ASSESSED

    def __post_init__(self) -> None:
        if (
            self.status is ConversionStatus.REJECTED
            and self.semantic_qualification is SemanticQualification.NOT_ASSESSED
        ):
            object.__setattr__(self, "semantic_qualification", SemanticQualification.REJECTED)
