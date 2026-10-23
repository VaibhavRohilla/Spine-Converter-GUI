"""Explicit route planning; recognized versions are not executable routes."""

from __future__ import annotations

from dataclasses import dataclass

from ..versions import VersionRegistry


@dataclass(frozen=True)
class ConversionPlan:
    source_version: str
    target_version: str
    route: tuple[str, ...]
    executable: bool
    diagnostics: tuple[str, ...]


class ConversionPlanner:
    """Plans only routes backed by a registered, qualified implementation."""

    def __init__(self, routes: set[tuple[str, str]] | None = None) -> None:
        self._routes = routes or set()
        self._versions = VersionRegistry()

    def plan(self, source_version: str, target_version: str) -> ConversionPlan:
        source_family = self._versions.family_for(source_version)
        target_family = self._versions.family_for(target_version)
        if source_family is None or target_family is None:
            return ConversionPlan(
                source_version,
                target_version,
                (),
                False,
                ("Unrecognized source or target version family",),
            )
        exact_route = (source_version, target_version)
        if (
            exact_route in self._routes
            and source_version.count(".") == 2
            and target_version.count(".") == 2
        ):
            return ConversionPlan(source_version, target_version, exact_route, True, ())
        if (source_family, target_family) in self._routes:
            return ConversionPlan(
                source_version, target_version, (source_family, target_family), True, ()
            )
        return ConversionPlan(
            source_version,
            target_version,
            (),
            False,
            (f"No qualified migration route: {source_family} -> {target_family}",),
        )
