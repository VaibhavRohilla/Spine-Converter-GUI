"""Recognized version families are independent of implemented converters."""

from __future__ import annotations

import re
from dataclasses import dataclass

SPINE_VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?$")


def valid_version(version: str) -> bool:
    return SPINE_VERSION.fullmatch(version) is not None


@dataclass(frozen=True)
class VersionDefinition:
    family: str


class VersionRegistry:
    def __init__(self) -> None:
        self._definitions = {
            v: VersionDefinition(v)
            for v in ("3.5", "3.6", "3.7", "3.8", "4.0", "4.1", "4.2", "4.3")
        }

    def family_for(self, version: str | None) -> str | None:
        if not version or not valid_version(version):
            return None
        family = ".".join(version.split(".")[:2])
        return family if family in self._definitions else None

    def definitions(self) -> tuple[VersionDefinition, ...]:
        return tuple(self._definitions[k] for k in sorted(self._definitions))


# Exact wire schema implemented by the restricted B3 hierarchy codec.
BINARY_HIERARCHY_VERSION = "4.2.43"
