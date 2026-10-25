"""Stable immutable domain contracts for inspection clients."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from .json_types import JSONDocument, JSONObject, JSONValue


def _freeze(value: JSONValue) -> JSONValue:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _plain(value: JSONValue) -> JSONValue:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
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
    context: JSONObject = field(default_factory=dict)
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
    metadata: JSONObject = field(default_factory=dict)

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

    def to_dict(self) -> JSONDocument:
        return {
            "source": self.source,
            "schema_version": self.schema_version,
            "summary": dict(self.summary),
            "ok": self.ok,
            "assets": [
                {
                    "path": a.path,
                    "kind": a.kind,
                    "spine_version": a.spine_version,
                    "byte_size": a.byte_size,
                    "asset_id": a.asset_id,
                    "source_id": a.source_id,
                    "filename": a.filename,
                    "extension": a.extension,
                    "checksum": a.checksum,
                    "metadata": _plain(a.metadata),
                }
                for a in self.assets
            ],
            "bundles": [
                {
                    "bundle_id": b.bundle_id,
                    "skeletons": list(b.skeletons),
                    "atlases": list(b.atlases),
                    "texture_pages": list(b.texture_pages),
                    "source_location": b.source_location,
                    "versions": list(b.versions),
                    "validation_state": b.validation_state,
                    "dependencies": [_dependency_dict(d) for d in b.dependencies],
                }
                for b in self.bundles
            ],
            "dependencies": [_dependency_dict(d) for d in self.dependencies],
            "diagnostics": [
                {
                    "code": d.code,
                    "severity": d.severity.value,
                    "message": d.message,
                    "path": d.path,
                    "context": _plain(d.context),
                    "suggestion": d.suggestion,
                }
                for d in self.diagnostics
            ],
        }


def _dependency_dict(dependency: Dependency) -> JSONDocument:
    return {
        "owner": dependency.owner,
        "requested": dependency.requested,
        "resolved": dependency.resolved,
        "kind": dependency.kind,
        "status": dependency.status,
    }
