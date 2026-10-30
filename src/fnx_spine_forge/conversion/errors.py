"""Typed failures at migration schema boundaries."""

from __future__ import annotations


class MigrationError(ValueError):
    """A source feature cannot be represented safely in the requested schema."""


class UnsupportedMigrationFeature(MigrationError):
    """A valid source construct lacks a semantics-preserving target mapping."""

    def __init__(self, feature: str, message: str) -> None:
        super().__init__(message)
        self.feature = feature
