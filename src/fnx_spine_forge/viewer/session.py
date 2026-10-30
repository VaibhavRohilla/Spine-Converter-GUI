"""Explicit lifecycle and generation guard for asynchronous host bridges."""

from dataclasses import dataclass, field
from enum import StrEnum
from secrets import token_urlsafe


class ViewerState(StrEnum):
    CREATED = "CREATED"
    INSPECTING = "INSPECTING"
    LOADING_RUNTIME = "LOADING_RUNTIME"
    LOADING_ASSETS = "LOADING_ASSETS"
    INITIALIZING = "INITIALIZING"
    READY = "READY"
    PLAYING = "PLAYING"
    PAUSED = "PAUSED"
    STOPPED = "STOPPED"
    SEEKING = "SEEKING"
    FAILED = "FAILED"
    DISPOSING = "DISPOSING"
    DISPOSED = "DISPOSED"


_FLOW: dict[ViewerState, frozenset[ViewerState]] = {
    ViewerState.CREATED: frozenset({ViewerState.INSPECTING}),
    ViewerState.INSPECTING: frozenset({ViewerState.LOADING_RUNTIME}),
    ViewerState.LOADING_RUNTIME: frozenset({ViewerState.LOADING_ASSETS}),
    ViewerState.LOADING_ASSETS: frozenset({ViewerState.INITIALIZING}),
    ViewerState.INITIALIZING: frozenset({ViewerState.READY}),
    ViewerState.READY: frozenset({ViewerState.PLAYING, ViewerState.STOPPED, ViewerState.SEEKING}),
    ViewerState.PLAYING: frozenset({ViewerState.PAUSED, ViewerState.STOPPED, ViewerState.SEEKING}),
    ViewerState.PAUSED: frozenset({ViewerState.PLAYING, ViewerState.STOPPED, ViewerState.SEEKING}),
    ViewerState.STOPPED: frozenset({ViewerState.PLAYING, ViewerState.READY, ViewerState.SEEKING}),
    ViewerState.SEEKING: frozenset({ViewerState.PAUSED}),
    ViewerState.FAILED: frozenset({ViewerState.INSPECTING}),
    ViewerState.DISPOSING: frozenset({ViewerState.DISPOSED}),
    ViewerState.DISPOSED: frozenset(),
}


@dataclass
class ViewerSession:
    session_id: str = field(default_factory=lambda: token_urlsafe(24))
    state: ViewerState = ViewerState.CREATED
    generation: int = 0

    def transition(self, state: ViewerState, generation: int | None = None) -> None:
        if generation is not None and generation != self.generation:
            raise ValueError("VIEWER_SESSION_CANCELLED")
        allowed = set(_FLOW[self.state])
        if self.state not in (ViewerState.DISPOSING, ViewerState.DISPOSED):
            allowed.update({ViewerState.DISPOSING, ViewerState.FAILED})
        if state not in allowed:
            raise ValueError(f"Illegal viewer transition {self.state} -> {state}")
        self.state = state
        if state in (ViewerState.DISPOSING, ViewerState.INSPECTING):
            self.generation += 1


class ViewerSessionManager:
    def __init__(self) -> None:
        self.sessions: dict[str, ViewerSession] = {}

    def create(self) -> ViewerSession:
        session = ViewerSession()
        self.sessions[session.session_id] = session
        return session

    def dispose(self, session_id: str) -> None:
        session = self.sessions.pop(session_id)
        session.transition(ViewerState.DISPOSING)
        session.transition(ViewerState.DISPOSED)
