"""Direct, loss-aware Spine 4.2 to 4.1 downgrade."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from ..json_types import JSONDocument, is_document
from .curves import _curve_statistics
from .document import require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route
from .schema import (
    _validate_constraints,
    _validate_deform_group,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)


def migrate_42_to_41(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Convert exact 4.2.43 data when 4.2 additions are absent or default-valued."""
    require_route(MigrationKind.SPINE_42_TO_41, source_version, target_version)
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.2.43 metadata")
    _validate_top_level(target)
    if skeleton.get("referenceScale", 100) != 100:
        raise MigrationError("Spine 4.1 cannot represent a non-default referenceScale")
    skeleton.pop("referenceScale", None)

    for bone in require_records(target.get("bones", []), "migrate_42_to_41 JSON field"):
        if not is_document(bone):
            raise MigrationError("Bone entries must be objects")
        if bone.get("skin", False):
            raise MigrationError("Spine 4.1 cannot represent skin-required bones")
        if "inherit" in bone:
            if "transform" in bone:
                raise MigrationError("Bone contains both inherit and transform modes")
            bone["transform"] = bone.pop("inherit")
        elif "transform" in bone:
            raise MigrationError("Spine 4.2 source bone unexpectedly contains transform mode")
        bone.pop("skin", None)

    for slot in require_records(target.get("slots", []), "migrate_42_to_41 JSON field"):
        if not is_document(slot):
            raise MigrationError("Slot entries must be objects")
        if slot.get("visible", True) is not True:
            raise MigrationError("Spine 4.1 cannot represent hidden setup slots")
        slot.pop("visible", None)

    physics = target.pop("physics", [])
    if physics:
        raise MigrationError("Spine 4.1 cannot represent physics constraints")
    for skin in require_records(target.get("skins", []), "migrate_42_to_41 JSON field"):
        if not is_document(skin):
            raise MigrationError("Skin entries must be objects")
        if skin.get("bones"):
            raise MigrationError("Spine 4.1 cannot represent skin-scoped bones")
        if any(skin.get(category) for category in ("ik", "transform", "path", "physics")):
            raise MigrationError("Spine 4.1 cannot represent skin-scoped constraints")
        skin.pop("bones", None)
        for category in ("ik", "transform", "path", "physics"):
            skin.pop(category, None)

    for animation_name, animation in require_object(
        target.get("animations", {}), "migrate_42_to_41 JSON field"
    ).items():
        if not is_document(animation):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        bone_timelines = require_object(animation.get("bones", {}), "migrate_42_to_41 JSON field")
        if isinstance(bone_timelines, Mapping) and any(
            isinstance(timelines, Mapping) and "inherit" in timelines
            for timelines in bone_timelines.values()
        ):
            raise MigrationError("Spine 4.1 cannot represent inherit timelines")
        if animation.get("physics"):
            raise MigrationError("Spine 4.1 cannot represent physics timelines")
        animation.pop("physics", None)

    _validate_top_level(target)
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    for animation_name, animation in require_object(
        target.get("animations", {}), "migrate_42_to_41 JSON field"
    ).items():
        if is_document(animation) and "attachments" in animation:
            _validate_deform_group(target, animation["attachments"], animation_name)
    require_object(target["skeleton"], "migrate_42_to_41 JSON field")["spine"] = target_version
    _validate_target(target, target_version)
    segments, curve_frames = _curve_statistics(target)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
        "attachments": 0,
    }


__all__ = ["migrate_42_to_41"]
