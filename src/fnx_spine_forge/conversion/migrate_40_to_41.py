"""Direct Spine 4.0 to 4.1 schema migration based on official readers."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument, is_document
from .curves import _curve_statistics
from .document import require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route
from .schema import (
    _migrate_constraint_definitions,
    _validate_constraints,
    _validate_deform_group,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)


def migrate_40_to_41(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Transform exact 4.0.31 JSON directly into the 4.1.56 schema."""
    require_route(MigrationKind.SPINE_40_TO_41, source_version, target_version)
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.0.31 metadata")
    _validate_top_level(target)
    for bone in require_records(target.get("bones", []), "migrate_40_to_41 JSON field"):
        if is_document(bone) and "inherit" in bone:
            raise MigrationError("Spine 4.0 bone schema cannot contain Spine 4.1 inherit fields")
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    _migrate_constraint_definitions(target)

    for animation_name, animation_value in require_object(
        target.get("animations", {}), "migrate_40_to_41 JSON field"
    ).items():
        animation = require_object(animation_value, f"animation {animation_name}")
        unsupported = set(animation) - {
            "bones",
            "slots",
            "ik",
            "transform",
            "path",
            "deform",
            "drawOrder",
            "events",
        }
        if unsupported:
            names = ", ".join(sorted(unsupported))
            raise MigrationError(f"Spine 4.1 does not support Spine 4.0 animation groups: {names}")
        if "deform" in animation:
            _validate_deform_group(target, animation["deform"], animation_name)
            deform = require_object(animation.pop("deform"), f"animation {animation_name}.deform")
            attachments: JSONDocument = {}
            for skin_name, skin_value in deform.items():
                skin = require_object(skin_value, f"deform skin {skin_name}")
                for slot_name, slot_value in skin.items():
                    slot = require_object(slot_value, f"deform slot {slot_name}")
                    for attachment_name, frames in slot.items():
                        slot[attachment_name] = {"deform": frames}
                attachments[skin_name] = skin
            animation["attachments"] = attachments

    segments, curve_frames = _curve_statistics(target)
    require_object(target["skeleton"], "migrate_40_to_41 JSON field")["spine"] = target_version
    _validate_target(target, target_version)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
    }


__all__ = ["migrate_40_to_41"]
