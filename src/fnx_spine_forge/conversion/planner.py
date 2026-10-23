"""Explicit route planning; recognized versions are not executable routes."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..versions import VersionRegistry
from .registry import EXACT_ROUTE_PAIRS


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
        self._routes = EXACT_ROUTE_PAIRS if routes is None else frozenset(routes)
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
        if source_version == target_version:
            return ConversionPlan(source_version, target_version, exact_route, True, ())
        if exact_route in self._routes:
            return ConversionPlan(source_version, target_version, exact_route, True, ())
        # Search only exact patch edges. Family recognition and family self-edges
        # are not migration implementations and must never create a route.
        exact_edges = {
            (left, right)
            for left, right in self._routes
            if left.count(".") == 2 and right.count(".") == 2
        }
        queue: deque[tuple[str, tuple[str, ...]]] = deque(
            [(source_version, (source_version,))]
        )
        seen = {source_version}
        while queue:
            current, path = queue.popleft()
            for left, right in sorted(exact_edges):
                if left != current or right in seen:
                    continue
                next_path = (*path, right)
                if right == target_version:
                    return ConversionPlan(
                        source_version,
                        target_version,
                        next_path,
                        False,
                        (
                            "A registered multi-hop path exists, but end-to-end feature "
                            "compatibility is not qualified",
                        ),
                    )
                seen.add(right)
                queue.append((right, next_path))
        return ConversionPlan(
            source_version,
            target_version,
            (),
            False,
            (f"No qualified migration route: {source_family} -> {target_family}",),
        )
