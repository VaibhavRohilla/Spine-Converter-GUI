"""Direct Spine 4.0 to 4.1 schema migration based on official readers."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import (
    MigrationError,
    _map,
    _migrate_constraint_definitions,
    _validate_constraints,
    _validate_deform_group,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)
from .migrate_42_to_43 import _curve_statistics


def migrate_40_to_41(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Transform exact 4.0.31 JSON directly into the 4.1.56 schema."""
    if source_version != "4.0.31" or target_version != "4.1.56":
        raise MigrationError("Only exact Spine 4.0.31 to 4.1.56 is implemented")
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.0.31 metadata")
    _validate_top_level(target)
    for bone in target.get("bones", []):
        if isinstance(bone, dict) and "inherit" in bone:
            raise MigrationError("Spine 4.0 bone schema cannot contain Spine 4.1 inherit fields")
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    _migrate_constraint_definitions(target)

    for animation_name, animation_value in target.get("animations", {}).items():
        animation = _map(animation_value, f"animation {animation_name}")
        unsupported = set(animation) - {
            "bones", "slots", "ik", "transform", "path", "deform", "drawOrder", "events"
        }
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise MigrationError(f"Spine 4.1 does not support Spine 4.0 animation groups: {names}")
        if "deform" in animation:
            _validate_deform_group(target, animation["deform"], animation_name)
            deform = _map(animation.pop("deform"), f"animation {animation_name}.deform")
            attachments: dict[str, Any] = {}
            for skin_name, skin_value in deform.items():
                skin = _map(skin_value, f"deform skin {skin_name}")
                for slot_name, slot_value in skin.items():
                    slot = _map(slot_value, f"deform slot {slot_name}")
                    for attachment_name, frames in slot.items():
                        slot[attachment_name] = {"deform": frames}
                attachments[skin_name] = skin
            animation["attachments"] = attachments

    segments, curve_frames = _curve_statistics(target)
    target["skeleton"]["spine"] = target_version
    _validate_target(target, target_version)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
    }


__all__ = ["migrate_40_to_41"]
