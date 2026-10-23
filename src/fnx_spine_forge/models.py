"""Stable immutable domain contracts for inspection clients."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, cast


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if is_dataclass(value):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    BLOCKER = "blocker"


class FileType(StrEnum):
    SKELETON_JSON = "skeleton_json"
    SKELETON_BINARY = "skeleton_binary"
    ATLAS = "atlas"
    TEXTURE = "texture"
    OTHER = "other"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Severity
    message: str
    path: str | None = None
    context: Mapping[str, Any] = field(default_factory=dict)
    suggestion: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "context", _freeze(self.context))


@dataclass(frozen=True)
class Asset:
    path: str
    kind: str
    spine_version: str | None = None
    byte_size: int = 0
    asset_id: str = ""
    source_id: str = ""
    filename: str = ""
    extension: str = ""
    checksum: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", _freeze(self.metadata))


@dataclass(frozen=True)
class Dependency:
    owner: str
    requested: str
    resolved: str | None
    kind: str
    status: str = "resolved"


@dataclass(frozen=True)
class SpineBundle:
    bundle_id: str
    skeletons: tuple[str, ...]
    atlases: tuple[str, ...]
    texture_pages: tuple[str, ...]
    source_location: str
    versions: tuple[str, ...] = ()
    dependencies: tuple[Dependency, ...] = ()
    validation_state: str = "unknown"


@dataclass(frozen=True)
class AssetManifest:
    source: str
    assets: tuple[Asset, ...]
    bundles: tuple[SpineBundle, ...]
    dependencies: tuple[Dependency, ...]
    diagnostics: tuple[Diagnostic, ...]
    schema_version: int = 1
    summary: Mapping[str, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _freeze(self.summary))

    @property
    def ok(self) -> bool:
        return not any(d.severity in (Severity.ERROR, Severity.BLOCKER) for d in self.diagnostics)

    def to_dict(self) -> dict[str, Any]:
        data = cast(dict[str, Any], _plain(self))
        data["ok"] = self.ok
        return data


InspectionReport = AssetManifest
