"""Recognized version families are independent of implemented converters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum


class CapabilityState(StrEnum):
    NOT_IMPLEMENTED = "not_implemented"
    EXPERIMENTAL = "experimental"
    STRUCTURALLY_VERIFIED = "structurally_verified"
    RUNTIME_VERIFIED = "runtime_verified"


@dataclass(frozen=True)
class VersionDefinition:
    family: str
    schema: str
    atlas_syntax: str
    reader: CapabilityState = CapabilityState.EXPERIMENTAL
    writer: CapabilityState = CapabilityState.NOT_IMPLEMENTED


class VersionRegistry:
    def __init__(self) -> None:
        self._definitions = {
            v: VersionDefinition(
                v,
                "historical" if v.startswith("3.") else "modern",
                "legacy" if v.startswith("3.") else "modern",
            )
            for v in ("3.5", "3.6", "3.7", "3.8", "4.0", "4.1", "4.2", "4.3")
        }

    def family_for(self, version: str | None) -> str | None:
        if not version or not re.fullmatch(r"\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?", version):
            return None
        family = ".".join(version.split(".")[:2])
        return family if family in self._definitions else None

    def definitions(self) -> tuple[VersionDefinition, ...]:
        return tuple(self._definitions[k] for k in sorted(self._definitions))
