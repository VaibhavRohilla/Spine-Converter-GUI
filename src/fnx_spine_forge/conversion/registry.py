"""Single authority for exact-patch conversion routes."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class MigrationKind(StrEnum):
    SPINE_38_TO_LEGACY = "spine_38_to_legacy"
    SPINE_38_TO_MODERN = "spine_38_to_modern"
    SPINE_35_TO_36 = "spine_35_to_36"
    SPINE_36_TO_35 = "spine_36_to_35"
    SPINE_36_TO_37 = "spine_36_to_37"
    SPINE_37_TO_36 = "spine_37_to_36"
    SPINE_37_TO_38 = "spine_37_to_38"
    SPINE_40_TO_38 = "spine_40_to_38"
    SPINE_40_TO_41 = "spine_40_to_41"
    SPINE_41_TO_40 = "spine_41_to_40"
    SPINE_41_TO_42 = "spine_41_to_42"
    SPINE_42_TO_41 = "spine_42_to_41"
    SPINE_42_TO_43 = "spine_42_to_43"
    SPINE_43_TO_42 = "spine_43_to_42"


@dataclass(frozen=True, slots=True)
class MigrationRoute:
    source: str
    target: str
    kind: MigrationKind
    atlas_supported: bool = True


def _route(source: str, target: str, kind: MigrationKind) -> MigrationRoute:
    return MigrationRoute(source, target, kind)


_ROUTES = (
    *(
        _route(source, target, MigrationKind.SPINE_38_TO_LEGACY)
        for source in ("3.8.75", "3.8.99")
        for target in ("3.5.51", "3.6.53", "3.7.94")
    ),
    *(
        _route(source, target, MigrationKind.SPINE_38_TO_MODERN)
        for source in ("3.8.75", "3.8.99")
        for target in ("4.0.31", "4.1.56", "4.2.43", "4.3.13")
    ),
    _route("3.5.51", "3.6.53", MigrationKind.SPINE_35_TO_36),
    _route("3.6.53", "3.5.51", MigrationKind.SPINE_36_TO_35),
    _route("3.6.53", "3.7.94", MigrationKind.SPINE_36_TO_37),
    _route("3.7.94", "3.6.53", MigrationKind.SPINE_37_TO_36),
    _route("3.7.94", "3.8.99", MigrationKind.SPINE_37_TO_38),
    _route("4.0.31", "3.8.99", MigrationKind.SPINE_40_TO_38),
    _route("4.0.31", "4.1.56", MigrationKind.SPINE_40_TO_41),
    _route("4.1.56", "4.0.31", MigrationKind.SPINE_41_TO_40),
    _route("4.1.56", "4.2.43", MigrationKind.SPINE_41_TO_42),
    _route("4.2.43", "4.1.56", MigrationKind.SPINE_42_TO_41),
    _route("4.2.43", "4.3.13", MigrationKind.SPINE_42_TO_43),
    _route("4.3.13", "4.2.43", MigrationKind.SPINE_43_TO_42),
)

MIGRATION_ROUTES: tuple[MigrationRoute, ...] = _ROUTES
ROUTES_BY_PATCH: dict[tuple[str, str], MigrationRoute] = {
    (route.source, route.target): route for route in MIGRATION_ROUTES
}
EXACT_ROUTE_PAIRS: frozenset[tuple[str, str]] = frozenset(ROUTES_BY_PATCH)
SUPPORTED_PATCH_VERSIONS: frozenset[str] = frozenset(
    version for route in MIGRATION_ROUTES for version in (route.source, route.target)
)

# Patch-scoped operational capabilities that are not route edges. Keep these
# policy sets here so recognition, conversion, atlas handling, and CLI reports
# do not grow independent patch lists.
KNOWN_EXPORT_ISSUE_PATCHES: frozenset[str] = frozenset({"3.8.75"})
RUNTIME_EXTENSION_LOADER_PATCHES = frozenset({"4.0.31"})
RUNTIME_SMOKE_PATCHES: frozenset[str] = frozenset({"4.0.31", "4.1.56", "4.2.43", "4.3.13"})
ATLAS_42_SCHEMA_PATCHES: frozenset[str] = frozenset({"4.2.43", "4.3.13"})
ATLAS_40_SCHEMA_PATCHES: frozenset[str] = frozenset({"4.0.31", "4.1.56"})
ATLAS_41_PATCHES: frozenset[str] = frozenset({"4.1.56"})


def require_route(kind: MigrationKind, source_version: str, target_version: str) -> MigrationRoute:
    """Admit one exact registered edge to its owning writer."""
    from .errors import MigrationError

    route = ROUTES_BY_PATCH.get((source_version, target_version))
    if route is None or route.kind is not kind:
        raise MigrationError(
            f"No registered {kind.value} edge for {source_version} -> {target_version}"
        )
    return route


_BONE_INHERITANCE_PATCHES = frozenset({"4.2.43", "4.3.13"})


def bone_mode_field(version: str) -> Literal["transform", "inherit"]:
    if version not in SUPPORTED_PATCH_VERSIONS:
        raise ValueError(f"No exact bone schema for {version!r}")
    return "inherit" if version in _BONE_INHERITANCE_PATCHES else "transform"
