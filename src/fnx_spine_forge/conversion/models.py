"""Typed, immutable conversion contracts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class ConversionStatus(StrEnum):
    PLANNED = "planned"
    SCHEMA_CONVERTED = "schema_converted"
    STRUCTURALLY_VERIFIED = "structurally_verified"
    REJECTED = "rejected"


class SourceRiskPolicy(StrEnum):
    """Policy for source exports with an official known-defect notice."""

    REJECT_KNOWN_ISSUES = "reject_known_issues"
    ALLOW_WITH_DIAGNOSTIC = "allow_with_diagnostic"


@dataclass(frozen=True)
class CanonicalSkeleton:
    """Lossless JSON document plus typed indexes used for semantic checks."""

    version: str
    document: dict[str, Any]
    bones: tuple[str, ...]
    slots: tuple[str, ...]
    skins: tuple[str, ...]
    animations: tuple[str, ...]


@dataclass(frozen=True)
class ConversionResult:
    source_version: str | None
    target_version: str
    route: tuple[str, ...]
    output: bytes | None
    status: ConversionStatus
    diagnostics: tuple[str, ...] = ()
    statistics: dict[str, int | float] | None = None
    details: dict[str, Any] | None = None
    unsupported_features: tuple[str, ...] = ()
    runtime_verified: bool = False
    visually_verified: bool = False
    diagnostic_codes: tuple[str, ...] = ()
    provenance: dict[str, Any] | None = None
    feature_compatibility: dict[str, str] | None = None
