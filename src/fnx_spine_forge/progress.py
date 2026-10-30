"""Shared typed lifecycle events and cooperative, thread-safe cancellation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from threading import Event


class Stage(StrEnum):
    SCANNING = "SCANNING"
    DISCOVERING = "DISCOVERING"
    VALIDATING = "VALIDATING"
    PLANNING = "PLANNING"
    CONVERTING_SKELETON = "CONVERTING_SKELETON"
    CONVERTING_ATLAS = "CONVERTING_ATLAS"
    VERIFYING = "VERIFYING"
    PACKAGING = "PACKAGING"
    PUBLISHING = "PUBLISHING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    stage: Stage
    asset_id: str | None = None


class CancellationToken:
    def __init__(self) -> None:
        self._event = Event()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def cancel(self) -> None:
        self._event.set()
