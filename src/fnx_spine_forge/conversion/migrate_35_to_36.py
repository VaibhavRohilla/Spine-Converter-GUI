"""Direct Spine 3.5 to 3.6 JSON migration, based on official versioned readers."""

from __future__ import annotations

import math
import struct
from copy import deepcopy

from ..json_types import JSONDocument, JSONValue, is_document
from .curves import _curve_controls
from .document import require_number, require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route


def _single_precision(value: JSONValue, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MigrationError(f"{context} must be a finite number")
    if not math.isfinite(require_number(value, context)):
        raise MigrationError(f"{context} must be a finite number")
    try:
        unpacked: tuple[object, ...] = struct.unpack("!f", struct.pack("!f", float(value)))
        rounded = unpacked[0]
        if not isinstance(rounded, float):
            raise MigrationError(f"{context} failed single precision decoding")
    except OverflowError as exc:
        raise MigrationError(f"{context} exceeds Spine 3.6 single precision") from exc
    if not math.isfinite(rounded):
        raise MigrationError(f"{context} exceeds Spine 3.6 single precision")
    return rounded


def migrate_35_to_36(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Round event keyframe times as the 3.6 loader does before constructing events."""
    require_route(MigrationKind.SPINE_35_TO_36, source_version, target_version)
    skeleton = source.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.5.51 metadata")
    animations = require_object(source.get("animations", {}), "migrate_35_to_36 JSON field")
    if not is_document(animations):
        raise MigrationError("Spine 3.5 animations must be an object")

    target = deepcopy(source)
    event_frames = 0
    bezier_segments = 0
    for animation_name, animation in require_object(
        target["animations"], "semantic object"
    ).items():
        if not is_document(animation):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        frames = require_records(animation.get("events", []), "migrate_35_to_36 JSON field")
        if not isinstance(frames, list):
            raise MigrationError(f"Animation {animation_name!r} event timeline must be an array")
        for index, frame in enumerate(frames):
            if not is_document(frame):
                raise MigrationError("Event timeline keyframes must be objects")
            if "time" not in frame:
                raise MigrationError("Event timeline keyframe requires time")
            frame["time"] = _single_precision(
                frame["time"], f"Animation {animation_name!r} event keyframe {index} time"
            )
            event_frames += 1
        stack: list[JSONValue] = [animation]
        while stack:
            value = stack.pop()
            if is_document(value):
                if "curve" in value:
                    controls = _curve_controls(value, f"animation {animation_name!r} curve")
                    if controls is not None:
                        bezier_segments += 1
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)

    require_object(target["skeleton"], "migrate_35_to_36 JSON field")["spine"] = target_version
    return target, {
        "bezier_segments": bezier_segments,
        "max_curve_error": 0.0,
        "attachments": 0,
        "event_frames_single_precision": event_frames,
    }


__all__ = ["migrate_35_to_36"]
