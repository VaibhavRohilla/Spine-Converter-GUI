"""Spine 3.8 downgrades to legacy skin-map readers, based on official loaders."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import (
    MigrationError,
    _validate_constraints,
    _validate_deform_group,
    _validate_top_level,
    _walk_attachments,
)

_LEGACY_TARGETS = {
    "3.5.51": "Spine 3.5.51 legacy skin-map schema",
    "3.6.53": "Spine 3.6.53 legacy skin-map schema",
    "3.7.94": "Spine 3.7.94 legacy skin-map schema",
}


def legacy_target_profile(target_version: str) -> str:
    try:
        return _LEGACY_TARGETS[target_version]
    except KeyError as exc:
        raise MigrationError(f"No legacy target profile for {target_version!r}") from exc


def _check_timeline_map(value: Any, allowed: set[str], context: str) -> None:
    if not isinstance(value, dict):
        raise MigrationError(f"{context} must be an object")
    unknown = set(value) - allowed
    if unknown:
        names = ", ".join(sorted(unknown))
        raise MigrationError(f"{context} has unsupported timeline types: {names}")
    for timeline, frames in value.items():
        if not isinstance(frames, list) or any(not isinstance(frame, dict) for frame in frames):
            raise MigrationError(f"{context}.{timeline} must be an array of keyframe objects")


def migrate_38_to_legacy(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Write the legacy 3.7 schema, rejecting data the 3.7 reader cannot consume."""
    if source_version not in {"3.8.75", "3.8.99"} or target_version not in _LEGACY_TARGETS:
        raise MigrationError(
            "Only exact 3.8.75/3.8.99 to 3.5.51, 3.6.53, or 3.7.94 is implemented"
        )
    target = deepcopy(source)
    _validate_top_level(target)
    if (
        not isinstance(target.get("skeleton"), dict)
        or target["skeleton"].get("spine") != source_version
    ):
        raise MigrationError("Source version does not match skeleton metadata")
    skins = target.get("skins")
    if not isinstance(skins, list):
        raise MigrationError("Spine 3.8 skins must be an array")
    skin_map: dict[str, Any] = {}
    for skin in skins:
        if not isinstance(skin, dict) or not isinstance(skin.get("name"), str):
            raise MigrationError("Skin name is required")
        name = skin["name"]
        if name in skin_map:
            raise MigrationError(f"Duplicate skin name {name!r}")
        if any(skin.get(key) for key in ("bones", "ik", "transform", "path")):
            raise MigrationError(
                f"Spine 3.7 skin {name!r} cannot represent skin-specific bones or constraints"
            )
        attachments = skin.get("attachments", {})
        if not isinstance(attachments, dict):
            raise MigrationError(f"Skin {name!r} attachments must be an object")
        skin_map[name] = attachments

    validation_document = deepcopy(target)
    _walk_attachments(validation_document, "4.0.31")
    _validate_constraints(validation_document)
    for animation_name, animation in validation_document.get("animations", {}).items():
        if isinstance(animation, dict) and "deform" in animation:
            _validate_deform_group(validation_document, animation["deform"], animation_name)

    for constraint in target.get("ik", []):
        if isinstance(constraint, dict) and "softness" in constraint:
            raise MigrationError("Spine 3.7 cannot represent IK softness")
    for animation_name, animation in target.get("animations", {}).items():
        if not isinstance(animation, dict):
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
                f"Animation {animation_name!r} contains a timeline unsupported by "
                f"{target_version}"
            )
        for bone_name, timelines in animation.get("bones", {}).items():
            _check_timeline_map(
                timelines, {"rotate", "translate", "scale", "shear"},
                f"animation {animation_name!r} bone {bone_name!r}",
            )
            for frame in (frame for frames in timelines.values() for frame in frames):
                if "value" in frame or "angle" not in frame and any(
                    key in frame for key in ("mixRotate", "mixX", "mixY")
                ):
                    raise MigrationError("Spine 3.7 bone timelines require legacy value fields")
        for slot_name, timelines in animation.get("slots", {}).items():
            _check_timeline_map(
                timelines, {"attachment", "color", "twoColor"},
                f"animation {animation_name!r} slot {slot_name!r}",
            )
        for category in ("ik", "transform"):
            if category in animation and not isinstance(animation[category], dict):
                raise MigrationError(f"animation {animation_name!r} {category} must be an object")
        if "path" in animation and not isinstance(animation["path"], dict):
            raise MigrationError(f"animation {animation_name!r} path must be an object")
        if "events" in animation and not isinstance(animation["events"], list):
            raise MigrationError(f"animation {animation_name!r} events must be an array")
        for constraints in animation.get("ik", {}).values():
            if any(isinstance(frame, dict) and "softness" in frame for frame in constraints):
                raise MigrationError("Spine 3.7 cannot represent animated IK softness")

    target["skins"] = skin_map
    target["skeleton"]["spine"] = target_version
    bezier_segments = 0
    for animation in target.get("animations", {}).values():
        if not isinstance(animation, dict):
            continue
        stack: list[Any] = [animation]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
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
