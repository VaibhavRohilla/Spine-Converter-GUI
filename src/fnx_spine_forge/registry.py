"""Explicit, auditable migration graph. No fictitious version support."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Protocol


def family(version: str) -> str:
    parts = version.split(".")
    if len(parts) < 2 or not all(s.isdigit() for s in parts[:2]):
        raise ValueError(f"Bad Spine version: {version}")
    return ".".join(parts[:2])


class Transformation(Protocol):
    def __call__(self, payload: bytes) -> bytes: ...


@dataclass(frozen=True)
class Migration:
    source_family: str
    target_family: str
    label: str
    transform: Transformation


class MigrationRegistry:
    def __init__(self) -> None:
        self._edges: dict[str, list[Migration]] = {}

    def register(self, migration: Migration) -> None:
        family(migration.source_family)
        family(migration.target_family)
        if any(
            m.target_family == migration.target_family
            for m in self._edges.get(migration.source_family, [])
        ):
            raise ValueError("Migration edge already registered")
        self._edges.setdefault(migration.source_family, []).append(migration)

    def plan(self, source_version: str, target_version: str) -> list[Migration]:
        start, end = family(source_version), family(target_version)
        if start == end:
            return []  # same family: no schema migration; patch policy checked elsewhere
        queue: deque[tuple[str, list[Migration]]] = deque([(start, [])])
        seen = {start}
        while queue:
            node, path = queue.popleft()
            for step in self._edges.get(node, []):
                if step.target_family == end:
                    return path + [step]
                if step.target_family not in seen:
                    seen.add(step.target_family)
                    queue.append((step.target_family, path + [step]))
        raise ValueError(f"Unsupported migration {start} -> {end}; no registered implementation")


def default_registry() -> MigrationRegistry:
    # Existing FNX v0.3.1 code was not attached. Do NOT advertise a working
    # 3.8 -> 4.2 path until its implementation is ported and verified.
    return MigrationRegistry()
