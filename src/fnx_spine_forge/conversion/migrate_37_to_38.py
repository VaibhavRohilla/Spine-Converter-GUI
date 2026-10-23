"""Direct Spine 3.7 to 3.8 skin-schema migration."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import (
    MigrationError,
    _curve_controls,
    _validate_constraints,
    _validate_deform_group,
    _validate_top_level,
    _walk_attachments,
)


def migrate_37_to_38(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Convert exact 3.7.94 object-map skins to the 3.8.99 skin array."""
    if source_version != "3.7.94" or target_version != "3.8.99":
        raise MigrationError("Only exact Spine 3.7.94 to 3.8.99 is implemented")
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.7.94 metadata")
    if any(key not in {
        "skeleton", "bones", "slots", "skins", "events", "ik", "transform", "path", "animations"
    } for key in target):
        raise MigrationError("Unsupported Spine 3.7 top-level field")
    for field in ("bones", "slots"):
        if not isinstance(target.get(field), list):
            raise MigrationError(f"Spine 3.7 skeleton requires {field} array")
    source_skins = target.get("skins")
    if not isinstance(source_skins, dict):
        raise MigrationError("Spine 3.7 skins must use the legacy object-map representation")

    skins: list[dict[str, Any]] = []
    for name, attachments in source_skins.items():
        if not isinstance(name, str) or not isinstance(attachments, dict):
            raise MigrationError("Spine 3.7 skin map must contain named attachment objects")
        skins.append({"name": name, "attachments": attachments})
    target["skins"] = skins

    valid_modes = {
        "normal": "Normal",
        "onlytranslation": "OnlyTranslation",
        "norotationorreflection": "NoRotationOrReflection",
        "noscale": "NoScale",
        "noscaleorreflection": "NoScaleOrReflection",
    }
    for bone in target["bones"]:
        if not isinstance(bone, dict):
            raise MigrationError("Bone entries must be objects")
        if "inherit" in bone or "skin" in bone:
            raise MigrationError("Spine 3.7 bone cannot contain 3.8 inherit or skin fields")
        mode = bone.get("transform")
        if mode is not None:
            normalized = valid_modes.get(str(mode).lower())
            if normalized is None:
                raise MigrationError(f"Unsupported Spine 3.7 bone transform mode {mode!r}")
            bone["transform"] = normalized

    animations = target.get("animations", {})
    if not isinstance(animations, dict):
        raise MigrationError("Spine 3.7 animations must be an object")
    bezier_segments = 0
    for animation_name, animation in animations.items():
        if not isinstance(animation, dict):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        allowed = {
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
        unknown = set(animation) - allowed
        if unknown:
            raise MigrationError(
                f"Spine 3.8 cannot represent animation group(s): {', '.join(sorted(unknown))}"
            )
        for owner_type, allowed_timelines in (
            ("bones", {"rotate", "translate", "scale", "shear"}),
            ("slots", {"attachment", "color", "twoColor"}),
        ):
            owners = animation.get(owner_type, {})
            if not isinstance(owners, dict):
                raise MigrationError(
                    f"Animation {animation_name!r} {owner_type} must be an object"
                )
            for owner_name, timeline_map in owners.items():
                if not isinstance(timeline_map, dict):
                    raise MigrationError(
                        f"Animation {animation_name!r} timeline owner "
                        f"{owner_name!r} must be an object"
                    )
                unknown_timelines = set(timeline_map) - allowed_timelines
                if unknown_timelines:
                    raise MigrationError(
                        f"Unsupported Spine 3.7 timeline type(s): "
                        f"{', '.join(sorted(unknown_timelines))}"
                    )
        stack: list[Any] = [animation]
        while stack:
            item = stack.pop()
            if isinstance(item, dict):
                if "curve" in item:
                    controls = _curve_controls(item, f"animation {animation_name} curve")
                    if controls is not None:
                        bezier_segments += 1
                stack.extend(item.values())
            elif isinstance(item, list):
                stack.extend(item)

    _validate_top_level(target)
    validation_document = deepcopy(target)
    _walk_attachments(validation_document, "4.0.31")
    _validate_constraints(validation_document)
    for animation_name, animation in validation_document.get("animations", {}).items():
        if isinstance(animation, dict) and "deform" in animation:
            _validate_deform_group(validation_document, animation["deform"], animation_name)

    target["skeleton"]["spine"] = target_version
    attachment_types: Counter[str] = Counter()
    for skin in target["skins"]:
        for slot_attachments in skin["attachments"].values():
            for attachment in slot_attachments.values():
                if isinstance(attachment, dict):
                    attachment_types[str(attachment.get("type", "region"))] += 1
    return target, {
        "bezier_segments": bezier_segments,
        "max_curve_error": 0.0,
        "attachments": sum(attachment_types.values()),
    }


__all__ = ["migrate_37_to_38"]
