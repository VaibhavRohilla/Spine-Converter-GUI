"""Direct, loss-aware Spine 3.7 to 3.6 downgrade."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import MigrationError, _curve_controls


def migrate_37_to_36(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Drop only false 3.7 IK defaults; block audio and enabled IK options."""
    if source_version != "3.7.94" or target_version != "3.6.53":
        raise MigrationError("Only exact Spine 3.7.94 to 3.6.53 is implemented")
    skeleton = source.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.7.94 metadata")
    target = deepcopy(source)
    if not isinstance(target.get("ik", []), list):
        raise MigrationError("Spine 3.7 IK constraints must be an array")
    for constraint in target.get("ik", []):
        if not isinstance(constraint, dict):
            raise MigrationError("Spine 3.7 IK constraints must be objects")
        if any(constraint.get(name, False) for name in ("compress", "stretch", "uniform")):
            raise MigrationError("Spine 3.6 cannot represent enabled 3.7 IK constraint options")
        for name in ("compress", "stretch", "uniform"):
            constraint.pop(name, None)

    events = target.get("events", {})
    if not isinstance(events, dict):
        raise MigrationError("Spine 3.7 event definitions must be an object")
    for name, event in events.items():
        if not isinstance(event, dict):
            raise MigrationError(f"Event definition {name!r} must be an object")
        if event.get("audio") is not None:
            raise MigrationError("Spine 3.6 cannot represent audio event definitions")
        if "volume" in event and event["volume"] != 1:
            raise MigrationError("Spine 3.6 cannot represent event audio volume")
        if "balance" in event and event["balance"] != 0:
            raise MigrationError("Spine 3.6 cannot represent event audio balance")
        for field in ("audio", "volume", "balance"):
            event.pop(field, None)

    animations = target.get("animations", {})
    if not isinstance(animations, dict):
        raise MigrationError("Spine 3.7 animations must be an object")
    bezier_segments = 0
    for animation_name, animation in animations.items():
        if not isinstance(animation, dict):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        ik_timelines = animation.get("ik", {})
        if not isinstance(ik_timelines, dict):
            raise MigrationError(f"Animation {animation_name!r} IK timelines must be an object")
        for constraint_name, frames in ik_timelines.items():
            if not isinstance(frames, list):
                raise MigrationError("IK timeline frames must be an array")
            for frame in frames:
                if not isinstance(frame, dict):
                    raise MigrationError("IK timeline keyframes must be objects")
                if any(frame.get(name, False) for name in ("compress", "stretch")):
                    raise MigrationError(
                        "Spine 3.6 cannot represent enabled 3.7 IK timeline options"
                    )
                frame.pop("compress", None)
                frame.pop("stretch", None)
        for event_frame in animation.get("events", []):
            if not isinstance(event_frame, dict):
                raise MigrationError("Event timeline keyframes must be objects")
            if event_frame.get("volume", 1) != 1 or event_frame.get("balance", 0) != 0:
                raise MigrationError("Spine 3.6 cannot represent audio event timeline values")
            event_frame.pop("volume", None)
            event_frame.pop("balance", None)
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
    }


__all__ = ["migrate_37_to_36"]
