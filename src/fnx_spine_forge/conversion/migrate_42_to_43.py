"""Direct Spine 4.2 to 4.3 schema migration based on the official readers."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from .json_types import JSONDocument, JSONValue, require_json_object
from .migrate_38_to_4x import (
    MigrationError,
    _map,
    _migrate_constraint_definitions,
    _migrate_constraints_to_43,
    _validate_constraints,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)


def _curve_statistics(document: JSONDocument) -> tuple[int, int]:
    segments = 0
    frames = 0
    stack: list[JSONValue] = [document.get("animations", {})]
    while stack:
        value = stack.pop()
        if isinstance(value, Mapping):
            curve = value.get("curve")
            if isinstance(curve, list):
                if len(curve) % 4 or any(
                    isinstance(item, bool) or not isinstance(item, (int, float))
                    for item in curve
                ):
                    raise MigrationError("Malformed Spine 4.2 Bézier control array")
                segments += len(curve) // 4
                frames += 1
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return segments, frames


def migrate_42_to_43(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Transform exact 4.2.43 JSON directly into the 4.3.13 schema."""
    if source_version != "4.2.43" or target_version != "4.3.13":
        raise MigrationError("Only exact Spine 4.2.43 to 4.3.13 is implemented")
    target = deepcopy(source)
    skeleton = require_json_object(target.get("skeleton"), "skeleton")
    if skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.2.43 metadata")
    target["skeleton"] = skeleton
    _validate_top_level(target)

    # Spine 4.2 and 4.3 share the array skin and per-channel curve schema. The
    # actual changes are attachment source naming and the ordered constraints list.
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    _migrate_constraint_definitions(target)
    _migrate_constraints_to_43(target)
    for category in ("ik", "transform", "path"):
        target.pop(category, None)
    segments, curve_frames = _curve_statistics(target)

    animations = require_json_object(target.get("animations", {}), "animations")
    for animation_name, animation_value in animations.items():
        animation = _map(animation_value, f"animation {animation_name}")
        unsupported = set(animation) - {
            "bones", "slots", "ik", "transform", "path", "attachments", "drawOrder", "events"
        }
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise MigrationError(
                f"Spine 4.3 does not support animation group(s): {names}"
            )
        for group_name in ("bones", "slots"):
            group = _map(animation.get(group_name, {}), f"animation {animation_name}.{group_name}")
            for owner, timeline_group in group.items():
                _map(timeline_group, f"animation {animation_name}.{group_name}.{owner}")

    skeleton["spine"] = target_version
    _validate_target(target, target_version)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
    }


__all__ = ["migrate_42_to_43"]
