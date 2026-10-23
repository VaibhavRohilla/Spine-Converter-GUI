"""Direct, loss-aware Spine 4.1 to 4.0 downgrade."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import (
    MigrationError,
    _map,
    _validate_constraints,
    _validate_deform_group,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)
from .migrate_42_to_43 import _curve_statistics


def migrate_41_to_40(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Restore 4.0 linked-mesh and deform timeline forms for representable 4.1 data."""
    if source_version != "4.1.56" or target_version != "4.0.31":
        raise MigrationError("Only exact Spine 4.1.56 to 4.0.31 is implemented")
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.1.56 metadata")
    _validate_top_level(target)
    for skin in target.get("skins", []):
        attachments = _map(skin.get("attachments", {}), "skin attachments")
        for slot_map in attachments.values():
            for attachment in _map(slot_map, "slot attachments").values():
                item = _map(attachment, "attachment")
                if "sequence" in item:
                    raise MigrationError(
                        "Spine 4.0 cannot represent Spine 4.1 attachment sequences"
                    )
                if item.get("type") == "linkedmesh":
                    if "deform" in item or not isinstance(item.get("timelines", True), bool):
                        raise MigrationError("Malformed Spine 4.1 linked-mesh timelines flag")
                    item["deform"] = item.pop("timelines", True)

    for animation_name, animation_value in target.get("animations", {}).items():
        animation = _map(animation_value, f"animation {animation_name}")
        if "attachments" not in animation:
            continue
        attachment_group = _map(
            animation.pop("attachments"), f"animation {animation_name}.attachments"
        )
        deform: dict[str, Any] = {}
        for skin_name, skin_value in attachment_group.items():
            skin = _map(skin_value, f"animation {animation_name} skin {skin_name}")
            deform_skin: dict[str, Any] = {}
            for slot_name, slot_value in skin.items():
                slot = _map(slot_value, f"animation {animation_name} slot {slot_name}")
                deform_slot: dict[str, Any] = {}
                for attachment_name, attachment_value in slot.items():
                    timelines = _map(
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
    for animation_name, animation in target.get("animations", {}).items():
        if isinstance(animation, Mapping) and "deform" in animation:
            _validate_deform_group(target, animation["deform"], animation_name)
    target["skeleton"]["spine"] = target_version
    _validate_target(target, target_version)
    segments, curve_frames = _curve_statistics(target)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
        "attachments": 0,
    }


__all__ = ["migrate_41_to_40"]
