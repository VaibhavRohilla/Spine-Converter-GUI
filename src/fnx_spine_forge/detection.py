"""Canonical recognition of admitted JSON skeleton documents."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .json_types import JSONDocument, is_document
from .versions import valid_version

TEXTURE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".ktx", ".ktx2", ".pvr", ".tga"})


class VersionDiagnosticCode(StrEnum):
    MISSING = "SKELETON_VERSION_MISSING"
    MALFORMED = "SKELETON_VERSION_MALFORMED"


@dataclass(frozen=True)
class VersionDiagnostic:
    code: VersionDiagnosticCode
    message: str


@dataclass(frozen=True)
class SkeletonRecognition:
    version: str | None
    diagnostic: VersionDiagnostic | None = None


def recognize_skeleton(document: JSONDocument) -> SkeletonRecognition | None:
    metadata = document.get("skeleton")
    if not is_document(metadata) or not isinstance(document.get("bones"), list):
        return None
    raw = metadata.get("spine")
    if raw is None:
        return SkeletonRecognition(
            None,
            VersionDiagnostic(
                VersionDiagnosticCode.MISSING, "Skeleton has no Spine export version metadata"
            ),
        )
    if not isinstance(raw, str) or not valid_version(raw):
        return SkeletonRecognition(
            None,
            VersionDiagnostic(
                VersionDiagnosticCode.MALFORMED, f"Unrecognized Spine version: {raw!r}"
            ),
        )
    return SkeletonRecognition(raw)
