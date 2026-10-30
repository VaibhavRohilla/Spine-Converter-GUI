"""Direct, loss-aware Spine 3.7 to 3.6 downgrade."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument, JSONValue, is_document
from .curves import _curve_controls
from .document import require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route


def migrate_37_to_36(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Drop only false 3.7 IK defaults; block audio and enabled IK options."""
    require_route(MigrationKind.SPINE_37_TO_36, source_version, target_version)
    skeleton = source.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.7.94 metadata")
    target = deepcopy(source)
    if not isinstance(require_records(target.get("ik", []), "migrate_37_to_36 JSON field"), list):
        raise MigrationError("Spine 3.7 IK constraints must be an array")
    for constraint in require_records(target.get("ik", []), "migrate_37_to_36 JSON field"):
        if not is_document(constraint):
            raise MigrationError("Spine 3.7 IK constraints must be objects")
        if any(constraint.get(name, False) for name in ("compress", "stretch", "uniform")):
            raise MigrationError("Spine 3.6 cannot represent enabled 3.7 IK constraint options")
        for name in ("compress", "stretch", "uniform"):
            constraint.pop(name, None)

    events = require_object(target.get("events", {}), "migrate_37_to_36 JSON field")
    if not is_document(events):
        raise MigrationError("Spine 3.7 event definitions must be an object")
    for name, event in events.items():
        if not is_document(event):
            raise MigrationError(f"Event definition {name!r} must be an object")
        if event.get("audio") is not None:
            raise MigrationError("Spine 3.6 cannot represent audio event definitions")
        if "volume" in event and event["volume"] != 1:
            raise MigrationError("Spine 3.6 cannot represent event audio volume")
        if "balance" in event and event["balance"] != 0:
            raise MigrationError("Spine 3.6 cannot represent event audio balance")
        for field in ("audio", "volume", "balance"):
            event.pop(field, None)

    animations = require_object(target.get("animations", {}), "migrate_37_to_36 JSON field")
    if not is_document(animations):
        raise MigrationError("Spine 3.7 animations must be an object")
    bezier_segments = 0
    for animation_name, animation in animations.items():
        if not is_document(animation):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        ik_timelines = require_object(animation.get("ik", {}), "migrate_37_to_36 JSON field")
        if not is_document(ik_timelines):
            raise MigrationError(f"Animation {animation_name!r} IK timelines must be an object")
        for constraint_name, frames in ik_timelines.items():
            if not isinstance(frames, list):
                raise MigrationError("IK timeline frames must be an array")
            for frame in frames:
                if not is_document(frame):
                    raise MigrationError("IK timeline keyframes must be objects")
                if any(frame.get(name, False) for name in ("compress", "stretch")):
                    raise MigrationError(
                        "Spine 3.6 cannot represent enabled 3.7 IK timeline options"
                    )
                frame.pop("compress", None)
                frame.pop("stretch", None)
        for event_frame in require_records(
            animation.get("events", []), "migrate_37_to_36 JSON field"
        ):
            if not is_document(event_frame):
                raise MigrationError("Event timeline keyframes must be objects")
            if event_frame.get("volume", 1) != 1 or event_frame.get("balance", 0) != 0:
                raise MigrationError("Spine 3.6 cannot represent audio event timeline values")
            event_frame.pop("volume", None)
            event_frame.pop("balance", None)
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

    require_object(target["skeleton"], "migrate_37_to_36 JSON field")["spine"] = target_version
    return target, {
        "bezier_segments": bezier_segments,
        "max_curve_error": 0.0,
        "attachments": 0,
    }


__all__ = ["migrate_37_to_36"]
