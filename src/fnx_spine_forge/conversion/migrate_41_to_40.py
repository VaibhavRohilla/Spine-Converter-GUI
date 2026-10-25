"""Direct, loss-aware Spine 4.1 to 4.0 downgrade."""

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


def migrate_41_to_40(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Restore 4.0 linked-mesh and deform timeline forms for representable 4.1 data."""
    require_route(MigrationKind.SPINE_41_TO_40, source_version, target_version)
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.1.56 metadata")
    _validate_top_level(target)
    for skin in require_records(target.get("skins", []), "migrate_41_to_40 JSON field"):
        attachments = require_object(
            require_object(skin.get("attachments", {}), "migrate_41_to_40 JSON field"),
            "skin attachments",
        )
        for slot_map in attachments.values():
            for attachment in require_object(slot_map, "slot attachments").values():
                item = require_object(attachment, "attachment")
                if "sequence" in item:
                    raise MigrationError(
                        "Spine 4.0 cannot represent Spine 4.1 attachment sequences"
                    )
                if item.get("type") == "linkedmesh":
                    if "deform" in item or not isinstance(item.get("timelines", True), bool):
                        raise MigrationError("Malformed Spine 4.1 linked-mesh timelines flag")
                    item["deform"] = item.pop("timelines", True)

    for animation_name, animation_value in require_object(
        target.get("animations", {}), "migrate_41_to_40 JSON field"
    ).items():
        animation = require_object(animation_value, f"animation {animation_name}")
        if "attachments" not in animation:
            continue
        attachment_group = require_object(
            animation.pop("attachments"), f"animation {animation_name}.attachments"
        )
        deform: JSONDocument = {}
        for skin_name, skin_value in attachment_group.items():
            skin = require_object(skin_value, f"animation {animation_name} skin {skin_name}")
            deform_skin: JSONDocument = {}
            for slot_name, slot_value in skin.items():
                slot = require_object(slot_value, f"animation {animation_name} slot {slot_name}")
                deform_slot: JSONDocument = {}
                for attachment_name, attachment_value in slot.items():
                    timelines = require_object(
                        attachment_value,
                        f"animation {animation_name} attachment {attachment_name}",
                    )
                    unknown = set(timelines) - {"deform"}
                    if unknown:
                        raise MigrationError(
                            f"Spine 4.0 cannot represent attachment timeline(s): "
                            f"{', '.join(sorted(unknown))}"
                        )
                    if "deform" in timelines:
                        deform_slot[attachment_name] = timelines["deform"]
                if deform_slot:
                    deform_skin[slot_name] = deform_slot
            if deform_skin:
                deform[skin_name] = deform_skin
        if deform:
            animation["deform"] = deform

    _validate_top_level(target)
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    for animation_name, final_animation in require_object(
        target.get("animations", {}), "migrate_41_to_40 JSON field"
    ).items():
        animation = require_object(final_animation, "animation")
        if isinstance(animation, Mapping) and "deform" in animation:
            _validate_deform_group(target, animation["deform"], animation_name)
    require_object(target["skeleton"], "migrate_41_to_40 JSON field")["spine"] = target_version
    _validate_target(target, target_version)
    segments, curve_frames = _curve_statistics(target)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
        "attachments": 0,
    }


__all__ = ["migrate_41_to_40"]
