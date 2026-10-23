"""Direct Spine 3.6 to 3.5 downgrade preserving runtime event-time precision."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .migrate_35_to_36 import _single_precision
from .migrate_38_to_4x import MigrationError, _curve_controls


def migrate_36_to_35(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Encode 3.6's single-precision event time in JSON read by the 3.5 loader."""
    if source_version != "3.6.53" or target_version != "3.5.51":
        raise MigrationError("Only exact Spine 3.6.53 to 3.5.51 is implemented")
    skeleton = source.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.6.53 metadata")
    target = deepcopy(source)
    animations = target.get("animations", {})
    if not isinstance(animations, dict):
        raise MigrationError("Spine 3.6 animations must be an object")
    event_frames = 0
    bezier_segments = 0
    for animation_name, animation in animations.items():
        if not isinstance(animation, dict):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        frames = animation.get("events", [])
        if not isinstance(frames, list):
            raise MigrationError(f"Animation {animation_name!r} event timeline must be an array")
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict) or "time" not in frame:
                raise MigrationError("Event timeline keyframe requires a time value")
            frame["time"] = _single_precision(
                frame["time"], f"Animation {animation_name!r} event frame {index} time"
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


__all__ = ["migrate_36_to_35"]
