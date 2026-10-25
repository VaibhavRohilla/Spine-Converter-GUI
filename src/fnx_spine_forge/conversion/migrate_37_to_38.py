"""Direct Spine 3.7 to 3.8 skin-schema migration."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy

from ..json_types import JSONDocument, JSONValue, is_document
from .curves import _curve_controls
from .document import require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route
from .schema import (
    _validate_constraints,
    _validate_deform_group,
    _validate_top_level,
    _walk_attachments,
)


def migrate_37_to_38(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Convert exact 3.7.94 object-map skins to the 3.8.99 skin array."""
    require_route(MigrationKind.SPINE_37_TO_38, source_version, target_version)
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.7.94 metadata")
    if any(
        key
        not in {
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
        for key in target
    ):
        raise MigrationError("Unsupported Spine 3.7 top-level field")
    for field in ("bones", "slots"):
        if not isinstance(target.get(field), list):
            raise MigrationError(f"Spine 3.7 skeleton requires {field} array")
    source_skins = target.get("skins")
    if not is_document(source_skins):
        raise MigrationError("Spine 3.7 skins must use the legacy object-map representation")

    skins: list[JSONDocument] = []
    for name, attachments in source_skins.items():
        if not isinstance(name, str) or not is_document(attachments):
            raise MigrationError("Spine 3.7 skin map must contain named attachment objects")
        skins.append({"name": name, "attachments": attachments})
    target["skins"] = [skin for skin in skins]

    valid_modes = {
        "normal": "Normal",
        "onlytranslation": "OnlyTranslation",
        "norotationorreflection": "NoRotationOrReflection",
        "noscale": "NoScale",
        "noscaleorreflection": "NoScaleOrReflection",
    }
    for bone in require_records(target["bones"], "migrate_37_to_38 JSON field"):
        if not is_document(bone):
            raise MigrationError("Bone entries must be objects")
        if "inherit" in bone or "skin" in bone:
            raise MigrationError("Spine 3.7 bone cannot contain 3.8 inherit or skin fields")
        mode = bone.get("transform")
        if mode is not None:
            normalized = valid_modes.get(str(mode).lower())
            if normalized is None:
                raise MigrationError(f"Unsupported Spine 3.7 bone transform mode {mode!r}")
            bone["transform"] = normalized

    animations = require_object(target.get("animations", {}), "migrate_37_to_38 JSON field")
    if not is_document(animations):
        raise MigrationError("Spine 3.7 animations must be an object")
    bezier_segments = 0
    for animation_name, animation in animations.items():
        if not is_document(animation):
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
            owners = require_object(animation.get(owner_type, {}), "migrate_37_to_38 JSON field")
            if not is_document(owners):
                raise MigrationError(f"Animation {animation_name!r} {owner_type} must be an object")
            for owner_name, timeline_map in owners.items():
                if not is_document(timeline_map):
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
        stack: list[JSONValue] = [animation]
        while stack:
            item = stack.pop()
            if is_document(item):
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
    for animation_name, animation in require_object(
        validation_document.get("animations", {}), "migrate_37_to_38 JSON field"
    ).items():
        if is_document(animation) and "deform" in animation:
            _validate_deform_group(validation_document, animation["deform"], animation_name)

    require_object(target["skeleton"], "migrate_37_to_38 JSON field")["spine"] = target_version
    attachment_types: Counter[str] = Counter()
    for skin in require_records(target["skins"], "migrate_37_to_38 JSON field"):
        for slot_attachments in require_object(skin["attachments"], "semantic object").values():
            for attachment in require_object(slot_attachments, "semantic object").values():
                if is_document(attachment):
                    attachment_types[str(attachment.get("type", "region"))] += 1
    return target, {
        "bezier_segments": bezier_segments,
        "max_curve_error": 0.0,
        "attachments": sum(attachment_types.values()),
    }


__all__ = ["migrate_37_to_38"]
