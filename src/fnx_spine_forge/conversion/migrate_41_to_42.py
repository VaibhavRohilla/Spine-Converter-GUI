"""Direct Spine 4.1 to 4.2 schema migration based on official readers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import (
    MigrationError,
    _migrate_constraint_definitions,
    _validate_constraints,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)
from .migrate_42_to_43 import _curve_statistics


def migrate_41_to_42(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Transform exact 4.1.56 JSON directly into the 4.2.43 schema."""
    if source_version != "4.1.56" or target_version != "4.2.43":
        raise MigrationError("Only exact Spine 4.1.56 to 4.2.43 is implemented")
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.1.56 metadata")
    _validate_top_level(target)
    for bone in target.get("bones", []):
        if isinstance(bone, dict) and ("inherit" in bone or "skin" in bone):
            raise MigrationError("Spine 4.1 bone schema cannot contain 4.2 inherit or skin fields")
    for animation_name, animation in target.get("animations", {}).items():
        if not isinstance(animation, dict):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        for bone_name, timelines in animation.get("bones", {}).items():
            if isinstance(timelines, dict) and "inherit" in timelines:
                raise MigrationError(
                    f"Spine 4.1 cannot contain an inherit timeline on bone {bone_name!r}"
                )
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    _migrate_constraint_definitions(target)
    segments, curve_frames = _curve_statistics(target)
    target["skeleton"]["spine"] = target_version
    _validate_target(target, target_version)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
    }


__all__ = ["migrate_41_to_42"]
