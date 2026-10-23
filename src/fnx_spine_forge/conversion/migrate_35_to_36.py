"""Direct Spine 3.5 to 3.6 JSON migration, based on official versioned readers."""

from __future__ import annotations

import math
import struct
from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import MigrationError, _curve_controls


def _single_precision(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MigrationError(f"{context} must be a finite number")
    if not math.isfinite(value):
        raise MigrationError(f"{context} must be a finite number")
    try:
        rounded = float(struct.unpack("!f", struct.pack("!f", float(value)))[0])
    except OverflowError as exc:
        raise MigrationError(f"{context} exceeds Spine 3.6 single precision") from exc
    if not math.isfinite(rounded):
        raise MigrationError(f"{context} exceeds Spine 3.6 single precision")
    return rounded


def migrate_35_to_36(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Round event keyframe times as the 3.6 loader does before constructing events."""
    if source_version != "3.5.51" or target_version != "3.6.53":
        raise MigrationError("Only exact Spine 3.5.51 to 3.6.53 is implemented")
    skeleton = source.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.5.51 metadata")
    animations = source.get("animations", {})
    if not isinstance(animations, dict):
        raise MigrationError("Spine 3.5 animations must be an object")

    target = deepcopy(source)
    event_frames = 0
    bezier_segments = 0
    for animation_name, animation in target["animations"].items():
        if not isinstance(animation, dict):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        frames = animation.get("events", [])
        if not isinstance(frames, list):
            raise MigrationError(f"Animation {animation_name!r} event timeline must be an array")
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                raise MigrationError("Event timeline keyframes must be objects")
            if "time" not in frame:
                raise MigrationError("Event timeline keyframe requires time")
            frame["time"] = _single_precision(
                frame["time"], f"Animation {animation_name!r} event keyframe {index} time"
            )
            event_frames += 1
        stack: list[Any] = [animation]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                if "curve" in value:
                    controls = _curve_controls(value, f"animation {animation_name!r} curve")
                    if controls is not None:
                        bezier_segments += 1
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)

    target["skeleton"]["spine"] = target_version
    return target, {
        "bezier_segments": bezier_segments,
        "max_curve_error": 0.0,
        "attachments": 0,
        "event_frames_single_precision": event_frames,
    }


__all__ = ["migrate_35_to_36"]
