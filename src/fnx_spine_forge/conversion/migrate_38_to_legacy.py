"""Spine 3.8 downgrades to legacy skin-map readers, based on official loaders."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument, JSONValue, is_document
from .document import require_object, require_records, require_text
from .errors import MigrationError
from .registry import MigrationKind, require_route
from .schema import (
    _validate_constraints,
    _validate_deform_group,
    _validate_top_level,
    _walk_attachments,
)


def legacy_target_profile(target_version: str) -> str:
    from .registry import MIGRATION_ROUTES

    if not any(
        route.kind is MigrationKind.SPINE_38_TO_LEGACY and route.target == target_version
        for route in MIGRATION_ROUTES
    ):
        raise MigrationError(f"No legacy target profile for {target_version!r}")
    return f"Spine {target_version} legacy skin-map schema"


def _check_timeline_map(value: JSONValue, allowed: set[str], context: str) -> None:
    if not is_document(value):
        raise MigrationError(f"{context} must be an object")
    unknown = set(value) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise MigrationError(f"{context} has unsupported timeline types: {names}")
    for timeline, frames in value.items():
        if not isinstance(frames, list) or any(
            not is_document(frame) for frame in require_records(frames, "bone timeline")
        ):
            raise MigrationError(f"{context}.{timeline} must be an array of keyframe objects")


def migrate_38_to_legacy(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Write the legacy 3.7 schema, rejecting data the 3.7 reader cannot consume."""
    require_route(MigrationKind.SPINE_38_TO_LEGACY, source_version, target_version)
    target = deepcopy(source)
    _validate_top_level(target)
    if (
        not is_document(target.get("skeleton"))
        or require_object(target["skeleton"], "migrate_38_to_legacy JSON field").get("spine")
        != source_version
    ):
        raise MigrationError("Source version does not match skeleton metadata")
    skins = target.get("skins")
    if not isinstance(skins, list):
        raise MigrationError("Spine 3.8 skins must be an array")
    skin_map: JSONDocument = {}
    for skin in skins:
        if not is_document(skin) or not isinstance(skin.get("name"), str):
            raise MigrationError("Skin name is required")
        name = require_text(skin["name"], "skin name")
        if name in skin_map:
            raise MigrationError(f"Duplicate skin name {name!r}")
        if any(skin.get(key) for key in ("bones", "ik", "transform", "path")):
            raise MigrationError(
                f"Spine 3.7 skin {name!r} cannot represent skin-specific bones or constraints"
            )
        attachments = require_object(skin.get("attachments", {}), "migrate_38_to_legacy JSON field")
        if not is_document(attachments):
            raise MigrationError(f"Skin {name!r} attachments must be an object")
        skin_map[name] = attachments

    validation_document = deepcopy(target)
    _walk_attachments(validation_document, "4.0.31")
    _validate_constraints(validation_document)
    for animation_name, animation in require_object(
        validation_document.get("animations", {}), "migrate_38_to_legacy JSON field"
    ).items():
        if is_document(animation) and "deform" in animation:
            _validate_deform_group(validation_document, animation["deform"], animation_name)

    for constraint in require_records(target.get("ik", []), "migrate_38_to_legacy JSON field"):
        if is_document(constraint) and "softness" in constraint:
            raise MigrationError("Spine 3.7 cannot represent IK softness")
    for animation_name, animation in require_object(
        target.get("animations", {}), "migrate_38_to_legacy JSON field"
    ).items():
        if not is_document(animation):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        animation_groups = {
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
        if any(key not in animation_groups for key in animation):
            raise MigrationError(
                f"Animation {animation_name!r} contains a timeline unsupported by {target_version}"
            )
        for bone_name, timelines in require_object(
            animation.get("bones", {}), "migrate_38_to_legacy JSON field"
        ).items():
            _check_timeline_map(
                timelines,
                {"rotate", "translate", "scale", "shear"},
                f"animation {animation_name!r} bone {bone_name!r}",
            )
            for frame in (
                frame
                for frames in require_object(timelines, "semantic object").values()
                for frame in require_records(frames, "bone timeline")
            ):
                if (
                    "value" in frame
                    or "angle" not in frame
                    and any(key in frame for key in ("mixRotate", "mixX", "mixY"))
                ):
                    raise MigrationError("Spine 3.7 bone timelines require legacy value fields")
        for slot_name, timelines in require_object(
            animation.get("slots", {}), "migrate_38_to_legacy JSON field"
        ).items():
            _check_timeline_map(
                timelines,
                {"attachment", "color", "twoColor"},
                f"animation {animation_name!r} slot {slot_name!r}",
            )
        for category in ("ik", "transform"):
            if category in animation and not is_document(animation[category]):
                raise MigrationError(f"animation {animation_name!r} {category} must be an object")
        if "path" in animation and not is_document(animation["path"]):
            raise MigrationError(f"animation {animation_name!r} path must be an object")
        if "events" in animation and not isinstance(animation["events"], list):
            raise MigrationError(f"animation {animation_name!r} events must be an array")
        for constraints in require_object(
            animation.get("ik", {}), "migrate_38_to_legacy JSON field"
        ).values():
            if any(
                is_document(frame) and "softness" in frame
                for frame in require_records(constraints, "IK timeline")
            ):
                raise MigrationError("Spine 3.7 cannot represent animated IK softness")

    target["skins"] = skin_map
    require_object(target["skeleton"], "migrate_38_to_legacy JSON field")["spine"] = target_version
    bezier_segments = 0
    for animation in require_object(
        target.get("animations", {}), "migrate_38_to_legacy JSON field"
    ).values():
        if not is_document(animation):
            continue
        stack: list[JSONValue] = [animation]
        while stack:
            value = stack.pop()
            if is_document(value):
                if "curve" in value:
                    curve = value["curve"]
                    if isinstance(curve, list):
                        raise MigrationError("Spine 3.7 requires normalized legacy Bézier controls")
                    if curve != "stepped" and curve is not None:
                        if not isinstance(curve, (int, float)) or isinstance(curve, bool):
                            raise MigrationError("Malformed legacy Bézier controls")
                        controls = (
                            curve,
                            value.get("c2", 0),
                            value.get("c3", 1),
                            value.get("c4", 1),
                        )
                        if any(
                            isinstance(control, bool)
                            or not isinstance(control, (int, float))
                            or not 0 <= control <= 1
                            for control in controls
                        ):
                            raise MigrationError("Malformed legacy Bézier controls")
                        bezier_segments += 1
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    return target, {
        "bezier_segments": bezier_segments,
        "max_curve_error": 0.0,
        "timeline_count": 0,
        "keyframes": 0,
    }


__all__ = ["legacy_target_profile", "migrate_38_to_legacy"]
