"""Direct Spine 3.6 to 3.5 downgrade preserving runtime event-time precision."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument, JSONValue, is_document
from .curves import _curve_controls
from .document import require_object, require_records
from .errors import MigrationError
from .migrate_35_to_36 import _single_precision
from .registry import MigrationKind, require_route


def migrate_36_to_35(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Encode 3.6's single-precision event time in JSON read by the 3.5 loader."""
    require_route(MigrationKind.SPINE_36_TO_35, source_version, target_version)
    skeleton = source.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.6.53 metadata")
    target = deepcopy(source)
    animations = require_object(target.get("animations", {}), "migrate_36_to_35 JSON field")
    if not is_document(animations):
        raise MigrationError("Spine 3.6 animations must be an object")
    event_frames = 0
    bezier_segments = 0
    for animation_name, animation in animations.items():
        if not is_document(animation):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        frames = require_records(animation.get("events", []), "migrate_36_to_35 JSON field")
        if not isinstance(frames, list):
            raise MigrationError(f"Animation {animation_name!r} event timeline must be an array")
        for index, frame in enumerate(frames):
            if not is_document(frame) or "time" not in frame:
                raise MigrationError("Event timeline keyframe requires a time value")
            frame["time"] = _single_precision(
                frame["time"], f"Animation {animation_name!r} event frame {index} time"
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
    require_object(target["skeleton"], "migrate_36_to_35 JSON field")["spine"] = target_version
    return target, {
        "bezier_segments": bezier_segments,
        "max_curve_error": 0.0,
        "attachments": 0,
        "event_frames_single_precision": event_frames,
    }


__all__ = ["migrate_36_to_35"]
