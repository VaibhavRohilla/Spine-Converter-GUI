"""Direct Spine 3.6 to 3.7 JSON migration, based on official versioned readers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import MigrationError

_TOP_LEVEL = {
    "skeleton",
    "bones",
    "slots",
    "skins",
    "events",
    "ik",
    "transform",
    "path",
    "animations",
}


def migrate_36_to_37(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Write 3.7's IK flags explicitly while retaining legacy skin/timeline schemas."""
    if source_version != "3.6.53" or target_version != "3.7.94":
        raise MigrationError("Only exact Spine 3.6.53 to 3.7.94 is implemented")
    if set(source) - _TOP_LEVEL:
        raise MigrationError("Unsupported Spine 3.6 top-level field")
    skeleton = source.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.6.53 metadata")
    for field in ("bones", "slots"):
        if not isinstance(source.get(field), list):
            raise MigrationError(f"Spine 3.6 skeleton requires {field} array")
    skins = source.get("skins")
    if not isinstance(skins, dict) or any(
        not isinstance(name, str) or not isinstance(entries, dict)
        for name, entries in skins.items()
    ):
        raise MigrationError("Spine 3.6 skins must use the legacy object-map representation")

    target = deepcopy(source)
    constraints = target.get("ik", [])
    if not isinstance(constraints, list):
        raise MigrationError("Spine 3.6 IK constraints must be an array")
    for constraint in constraints:
        if not isinstance(constraint, dict):
            raise MigrationError("Spine 3.6 IK constraints must be objects")
        if {"compress", "stretch", "uniform"} & constraint.keys():
            raise MigrationError("Spine 3.6 source cannot declare Spine 3.7 IK options")
        # These fields were introduced in the 3.7 reader and default to false there.
        constraint.update(compress=False, stretch=False, uniform=False)

    animations = target.get("animations", {})
    if not isinstance(animations, dict):
        raise MigrationError("Spine 3.6 animations must be an object")
    for animation_name, animation in animations.items():
        if not isinstance(animation, dict):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        allowed_groups = {
            "bones",
            "slots",
            "ik",
            "transform",
            "path",
            "deform",
            "drawOrder",
            "draworder",
            "events",
        }
        if set(animation) - allowed_groups:
            raise MigrationError(
                f"Animation {animation_name!r} contains an unsupported timeline group"
            )
        ik_timelines = animation.get("ik", {})
        if not isinstance(ik_timelines, dict):
            raise MigrationError(f"Animation {animation_name!r} IK timelines must be an object")
        for name, frames in ik_timelines.items():
            if not isinstance(frames, list):
                raise MigrationError(
                    f"Animation {animation_name!r} IK timeline {name!r} must be an array"
                )
            for frame in frames:
                if not isinstance(frame, dict):
                    raise MigrationError("IK timeline keyframes must be objects")
                if {"compress", "stretch"} & frame.keys():
                    raise MigrationError(
                        "Spine 3.6 source cannot declare Spine 3.7 IK animation options"
                    )
                frame.update(compress=False, stretch=False)

    target["skeleton"]["spine"] = target_version
    return target, {"bezier_segments": 0, "max_curve_error": 0.0, "attachments": 0}


__all__ = ["migrate_36_to_37"]
