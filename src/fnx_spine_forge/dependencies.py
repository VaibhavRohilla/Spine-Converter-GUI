"""Deterministic dependency matching shared by inspection and future converters."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath


@dataclass(frozen=True)
class Match:
    resolved: str | None
    ambiguous: bool
    candidates: tuple[str, ...] = ()


class DependencyResolver:
    def __init__(self, paths: tuple[str, ...] | list[str]):
        self.paths = tuple(sorted(set(paths)))
        self._set = set(self.paths)
        self._basename: dict[str, list[str]] = {}
        for path in self.paths:
            self._basename.setdefault(PurePosixPath(path).name.casefold(), []).append(path)

    def resolve(self, requested: str, owner: str) -> Match:
        if (
            not requested
            or "\\" in requested
            or "\x00" in requested
            or requested.startswith("/")
            or re.match(r"^[A-Za-z]:", requested)
        ):
            return Match(None, False)
        base = list(PurePosixPath(owner).parent.parts)
        for part in PurePosixPath(requested).parts:
            if part in ("", "."):
                continue
            if part == "..":
                if not base:
                    return Match(None, False)
                base.pop()
            else:
                base.append(part)
        rel = PurePosixPath(*base).as_posix()
        req = PurePosixPath(requested)
        if rel in self._set:
            return Match(rel, False, (rel,))
        candidates = tuple(self._basename.get(req.name.casefold(), ()))
        if len(candidates) == 1:
            return Match(candidates[0], False, candidates)
        return Match(None, len(candidates) > 1, candidates)
