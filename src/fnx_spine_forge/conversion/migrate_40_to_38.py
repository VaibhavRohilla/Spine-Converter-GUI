"""Conservative Spine 4.0.31 to 3.8.99 downgrade."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import (
    MigrationError,
    UnsupportedMigrationFeature,
    _frames,
    _map,
    _rename_exclusive,
    _validate_constraints,
    _validate_deform_group,
    _validate_top_level,
    _walk_attachments,
)


def _rename_timeline(
    frames: list[dict[str, Any]], old: str, new: str, context: str
) -> None:
    for frame in frames:
        _rename_exclusive(frame, old, new, context)


def _downgrade_animation(document: dict[str, Any], name: str) -> None:
    animation = _map(document, f"animation {name}")
    supported_groups = {
        "bones", "slots", "ik", "transform", "path", "attachments",
        "deform", "drawOrder", "draworder", "events",
    }
    extra = set(animation) - supported_groups
    if extra:
        raise MigrationError(
            f"Spine 3.8 cannot represent animation groups: {', '.join(sorted(extra))}"
        )
    if "attachments" in animation:
        if "deform" in animation:
            raise MigrationError("Animation has conflicting attachments and deform groups")
        group = _map(animation.pop("attachments"), f"animation {name}.attachments")
        deform: dict[str, Any] = {}
        for skin_name, skin_value in group.items():
            skin = _map(skin_value, f"deform skin {skin_name}")
            out_skin: dict[str, Any] = {}
            for slot_name, slot_value in skin.items():
                slot = _map(slot_value, f"deform slot {slot_name}")
                out_slot: dict[str, Any] = {}
                for attachment_name, timeline_value in slot.items():
                    timelines = _map(timeline_value, f"attachment timeline {attachment_name}")
                    if set(timelines) - {"deform"}:
                            raise UnsupportedMigrationFeature(
                                "non_deform_attachment_timelines",
                            "Spine 3.8 cannot represent non-deform attachment timelines"
                        )
                    if "deform" in timelines:
                        out_slot[attachment_name] = timelines["deform"]
                if out_slot:
                    out_skin[slot_name] = out_slot
            if out_skin:
                deform[skin_name] = out_skin
        if deform:
            animation["deform"] = deform

    for slot_name, timeline_value in _map(
        animation.get("slots", {}), f"animation {name}.slots"
    ).items():
        timelines = _map(timeline_value, f"slot timelines {slot_name}")
        _rename_exclusive(timelines, "rgba", "color", f"slot {slot_name}")
        _rename_exclusive(timelines, "rgba2", "twoColor", f"slot {slot_name}")
        unknown = set(timelines) - {"attachment", "color", "twoColor"}
        if unknown:
            raise MigrationError(
                f"Spine 3.8 cannot represent slot timeline(s): {', '.join(sorted(unknown))}"
            )
        for timeline_name, value in timelines.items():
            _frames(value, f"slot {slot_name}.{timeline_name}")

    for bone_name, timeline_value in _map(
        animation.get("bones", {}), f"animation {name}.bones"
    ).items():
        timelines = _map(timeline_value, f"bone timelines {bone_name}")
        unknown = set(timelines) - {"rotate", "translate", "scale", "shear"}
        if unknown:
            raise MigrationError(
                f"Spine 3.8 cannot represent bone timeline(s): {', '.join(sorted(unknown))}"
            )
        for timeline_name, value in timelines.items():
            frames = _frames(value, f"bone {bone_name}.{timeline_name}")
            if timeline_name == "rotate":
                _rename_timeline(frames, "value", "angle", f"{name}.{bone_name}.rotate")

    for constraint_name, frames_value in _map(
        animation.get("transform", {}), f"animation {name}.transform"
    ).items():
        frames = _frames(frames_value, f"transform timeline {constraint_name}")
        for frame in frames:
            for first, second, target_field in (
                ("mixX", "mixY", "translateMix"),
                ("mixScaleX", "mixScaleY", "scaleMix"),
            ):
                if first in frame and second in frame and frame[first] != frame[second]:
                    raise UnsupportedMigrationFeature(
                        "unequal_transform_mix_channels",
                        f"Spine 3.8 transform {target_field} cannot represent unequal "
                        f"channels in {constraint_name}",
                    )
                if first in frame:
                    _rename_exclusive(frame, first, target_field, f"transform {constraint_name}")
                frame.pop(second, None)
            for old, new in (
                ("mixRotate", "rotateMix"),
                ("mixShearY", "shearMix"),
            ):
                _rename_exclusive(frame, old, new, f"transform {constraint_name}")

    for constraint_name, timeline_value in _map(
        animation.get("path", {}), f"animation {name}.path"
    ).items():
        timelines = _map(timeline_value, f"path timelines {constraint_name}")
        for timeline_name in ("position", "spacing"):
            if timeline_name in timelines:
                frames = _frames(
                    timelines[timeline_name], f"path {constraint_name}.{timeline_name}"
                )
                _rename_timeline(frames, "value", timeline_name, f"path {constraint_name}")
        if "mix" in timelines:
            frames = _frames(timelines["mix"], f"path {constraint_name}.mix")
            for frame in frames:
                if "mixX" in frame and "mixY" in frame and frame["mixX"] != frame["mixY"]:
                    raise UnsupportedMigrationFeature(
                        "unequal_path_mix_channels",
                        "Spine 3.8 path mix cannot represent unequal translate channels: "
                        f"{constraint_name}"
                    )
                _rename_exclusive(frame, "mixRotate", "rotateMix", f"path {constraint_name}.mix")
                _rename_exclusive(frame, "mixX", "translateMix", f"path {constraint_name}.mix")
                frame.pop("mixY", None)
        unsupported = set(timelines) - {"position", "spacing", "mix"}
        if unsupported:
            raise MigrationError(
                f"Spine 3.8 cannot represent path timeline(s): {', '.join(sorted(unsupported))}"
            )

    ik_timelines = _map(animation.get("ik", {}), f"animation {name}.ik")
    for constraint_name, frames_value in ik_timelines.items():
        frames = _frames(frames_value, f"IK timeline {constraint_name}")
        allowed = {
            "time", "mix", "softness", "bendPositive", "compress", "stretch", "uniform", "curve"
        }
        for frame in frames:
            unknown = set(frame) - allowed
            if unknown:
                raise MigrationError(
                    f"Spine 3.8 cannot represent IK timeline fields: {', '.join(sorted(unknown))}"
                )
    if "events" in animation and not isinstance(animation["events"], list):
        raise MigrationError(f"Animation {name!r} events must be an array")
    for order_key in ("drawOrder", "draworder"):
        if order_key in animation and not isinstance(animation[order_key], list):
            raise MigrationError(f"Animation {name!r} {order_key} must be an array")


def migrate_40_to_38(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Downgrade the representable 4.0 subset to the 3.8 skin/timeline schema.

    Spine 4.0 stores absolute per-channel Bézier curves; 3.8 has one normalized
    curve shared by every channel. Until channel endpoints are typed per timeline,
    such segments cannot be proven representable and are rejected.
    """
    if source_version != "4.0.31" or target_version != "3.8.99":
        raise MigrationError("Only exact Spine 4.0.31 to 3.8.99 is implemented")
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not isinstance(skeleton, dict) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.0.31 metadata")
    skins = target.get("skins")
    if not isinstance(skins, list):
        raise MigrationError("Spine 4.0 skins must use the named skin array schema")
    skin_names: set[str] = set()
    _validate_top_level(target)
    for skin in skins:
        if not isinstance(skin, dict) or not isinstance(skin.get("name"), str):
            raise MigrationError("Skin name is required")
        name = skin["name"]
        if name in skin_names:
            raise MigrationError(f"Duplicate skin name {name!r}")
        skin_names.add(name)
        if any(skin.get(key) for key in ("bones", "ik", "transform", "path")):
            raise UnsupportedMigrationFeature(
                "skin_specific_constraints_or_bones",
                "Spine 3.8 cannot represent skin-specific bones or constraints",
            )
        attachments = skin.get("attachments", {})
        if not isinstance(attachments, dict):
            raise MigrationError(f"Skin {name!r} attachments must be an object")
        for slots in attachments.values():
            if not isinstance(slots, dict):
                raise MigrationError("Skin slot attachments must be an object")
            for attachment in slots.values():
                if not isinstance(attachment, dict):
                    continue
                if "sequence" in attachment:
                    raise UnsupportedMigrationFeature(
                        "attachment_sequences",
                        "Spine 3.8 cannot represent attachment sequences",
                    )
                if attachment.get("type") == "linkedmesh":
                    if "timelines" in attachment and "deform" in attachment:
                        raise MigrationError("Linked mesh contains conflicting deform flags")
                    attachment["deform"] = attachment.pop("timelines", True)

    animations = _map(target.get("animations", {}), "animations")
    for animation_name, animation in animations.items():
        stack: list[Any] = [animation]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                curve = value.get("curve")
                if isinstance(curve, list):
                    raise UnsupportedMigrationFeature(
                        "incompatible_per_channel_bezier_curves",
                        "Spine 4.0 per-channel Bézier curves are not representable by one "
                        "Spine 3.8 shared curve without channel-equivalence proof"
                    )
                if curve is not None and curve != "stepped":
                    raise MigrationError(
                        f"Unsupported curve encoding in animation {animation_name!r}"
                    )
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
        _downgrade_animation(animation, animation_name)
    # 3.8 uses the named skin record array, as does 4.0; keep setup attachment
    # semantics intact and only validate that the target-required fields exist.
    skeleton["spine"] = target_version
    _validate_top_level(target)
    _validate_constraints(target)
    _walk_attachments(target, "4.0.31")
    for animation_name, animation in animations.items():
        if isinstance(animation, dict) and "deform" in animation:
            _validate_deform_group(target, animation["deform"], animation_name)
    return target, {"bezier_segments": 0, "max_curve_error": 0.0}


__all__ = ["migrate_40_to_38"]
