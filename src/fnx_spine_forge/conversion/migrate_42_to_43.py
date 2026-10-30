"""Direct Spine 4.2 to 4.3 schema migration based on the official readers."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument, require_json_object
from .curves import _curve_statistics
from .document import require_object
from .errors import MigrationError
from .registry import MigrationKind, require_route
from .schema import (
    _migrate_constraint_definitions,
    _migrate_constraints_to_43,
    _validate_constraints,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)


def migrate_42_to_43(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Transform exact 4.2.43 JSON directly into the 4.3.13 schema."""
    require_route(MigrationKind.SPINE_42_TO_43, source_version, target_version)
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

    animations = require_json_object(
        require_object(target.get("animations", {}), "migrate_42_to_43 JSON field"), "animations"
    )
    for animation_name, animation_value in animations.items():
        animation = require_object(animation_value, f"animation {animation_name}")
        unsupported = set(animation) - {
            "bones",
            "slots",
            "ik",
            "transform",
            "path",
            "attachments",
            "drawOrder",
            "events",
        }
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise MigrationError(f"Spine 4.3 does not support animation group(s): {names}")
        for group_name in ("bones", "slots"):
            group = require_object(
                require_object(animation.get(group_name, {}), "migrate_42_to_43 JSON field"),
                f"animation {animation_name}.{group_name}",
            )
            for owner, timeline_group in group.items():
                require_object(timeline_group, f"animation {animation_name}.{group_name}.{owner}")

    skeleton["spine"] = target_version
    _validate_target(target, target_version)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
    }


__all__ = ["migrate_42_to_43"]
