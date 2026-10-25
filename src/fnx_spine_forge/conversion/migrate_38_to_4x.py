"""Exact Spine 3.8 to modern schema migration writer."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument
from .curves import (
    _color_channels,
    _curve_controls,
    _curve_error,
    _curve_fields,
)
from .document import require_array, require_number, require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route
from .schema import (
    _migrate_constraint_definitions,
    _migrate_constraints_to_43,
    _rename_exclusive,
    _validate_constraints,
    _validate_deform_group,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)


def migrate_38_to_target(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Transform supported exact 3.8 exports into a qualified later schema."""
    target = deepcopy(source)
    _validate_top_level(target)
    require_route(MigrationKind.SPINE_38_TO_MODERN, source_version, target_version)
    if (
        require_object(target["skeleton"], "migrate_38_to_4x JSON field").get("spine")
        != source_version
    ):
        raise MigrationError("Source version argument does not match skeleton metadata")
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    _migrate_constraint_definitions(target)
    if target_version == "4.3.13":
        _migrate_constraints_to_43(target)
    animations = require_object(target.get("animations", {}), "migrate_38_to_4x JSON field")
    stats = {"bezier_segments": 0, "timeline_count": 0, "keyframes": 0, "max_curve_error": 0.0}

    def add_curves(result: tuple[int, float]) -> None:
        stats["bezier_segments"] += result[0]
        stats["max_curve_error"] = max(stats["max_curve_error"], result[1])

    for animation_name, animation_value in animations.items():
        animation = require_object(animation_value, f"animation {animation_name}")
        unknown = set(animation) - {
            "slots",
            "bones",
            "ik",
            "transform",
            "path",
            "deform",
            "drawOrder",
            "draworder",
            "events",
        }
        if unknown:
            raise MigrationError(
                f"animation {animation_name!r} has unsupported timeline groups: "
                f"{', '.join(sorted(unknown))}"
            )
        _rename_exclusive(animation, "draworder", "drawOrder", f"animation {animation_name}")
        if target_version != "4.0.31":
            _rename_exclusive(animation, "deform", "attachments", f"animation {animation_name}")
        deform_group = "deform" if target_version == "4.0.31" else "attachments"
        if deform_group in animation:
            _validate_deform_group(target, animation[deform_group], animation_name)
        if target_version != "4.0.31" and "attachments" in animation:
            attachments_group = require_object(
                animation["attachments"], f"animation {animation_name}.attachments"
            )
            for skin_name, skin_value in attachments_group.items():
                skin_map = require_object(skin_value, f"deform skin {skin_name}")
                for slot_name, slot_value in skin_map.items():
                    slot_map = require_object(slot_value, f"deform slot {slot_name}")
                    for attachment_name, frames_value in list(slot_map.items()):
                        if not isinstance(frames_value, list):
                            raise MigrationError(
                                f"deform frames for {attachment_name!r} must be an array"
                            )
                        slot_map[attachment_name] = {"deform": frames_value}
        for slot_name, timeline_set_value in require_object(
            require_object(animation.get("slots", {}), "migrate_38_to_4x JSON field"),
            f"animation {animation_name}.slots",
        ).items():
            timeline_set = require_object(timeline_set_value, f"slot timelines {slot_name}")
            if slot_name not in {
                slot["name"]
                for slot in require_records(target["slots"], "migrate_38_to_4x JSON field")
            }:
                raise MigrationError(
                    f"animation {animation_name!r} references missing slot {slot_name!r}"
                )
            _rename_exclusive(timeline_set, "color", "rgba", f"slot {slot_name}")
            _rename_exclusive(timeline_set, "twoColor", "rgba2", f"slot {slot_name}")
            for name, value in timeline_set.items():
                frames = require_records(value, f"slot timeline {name}")
                if name == "attachment":
                    pass
                elif name == "rgba":
                    add_curves(
                        _color_channels(frames, ("color",), f"{animation_name}.{slot_name}.rgba")
                    )
                elif name == "rgba2":
                    add_curves(
                        _color_channels(
                            frames, ("light", "dark"), f"{animation_name}.{slot_name}.rgba2"
                        )
                    )
                else:
                    raise MigrationError(f"unsupported slot timeline {name!r}")
                stats["timeline_count"] += 1
                stats["keyframes"] += len(frames)
        for bone_name, timeline_set_value in require_object(
            require_object(animation.get("bones", {}), "migrate_38_to_4x JSON field"),
            f"animation {animation_name}.bones",
        ).items():
            timeline_set = require_object(timeline_set_value, f"bone timelines {bone_name}")
            if bone_name not in {
                bone["name"]
                for bone in require_records(target["bones"], "migrate_38_to_4x JSON field")
            }:
                raise MigrationError(
                    f"animation {animation_name!r} references missing bone {bone_name!r}"
                )
            for name, value in timeline_set.items():
                frames = require_records(value, f"bone timeline {name}")
                channels: tuple[tuple[str, float], ...]
                if name == "rotate":
                    for frame in frames:
                        _rename_exclusive(
                            frame, "angle", "value", f"{animation_name}.{bone_name}.rotate"
                        )
                    channels = (("value", 0.0),)
                elif name == "translate":
                    channels = (("x", 0.0), ("y", 0.0))
                elif name == "scale":
                    channels = (("x", 1.0), ("y", 1.0))
                elif name == "shear":
                    channels = (("x", 0.0), ("y", 0.0))
                else:
                    raise MigrationError(f"unsupported bone timeline {name!r}")
                add_curves(_curve_fields(frames, channels, f"{animation_name}.{bone_name}.{name}"))
                stats["timeline_count"] += 1
                stats["keyframes"] += len(frames)
        for category, constraint_names in (
            (
                "ik",
                {
                    c["name"]
                    for c in require_records(target.get("ik", []), "migrate_38_to_4x JSON field")
                },
            ),
            (
                "transform",
                {
                    c["name"]
                    for c in require_records(
                        target.get("transform", []), "migrate_38_to_4x JSON field"
                    )
                },
            ),
            (
                "path",
                {
                    c["name"]
                    for c in require_records(target.get("path", []), "migrate_38_to_4x JSON field")
                },
            ),
        ):
            timelines = require_object(
                require_object(animation.get(category, {}), "migrate_38_to_4x JSON field"),
                f"animation {animation_name}.{category}",
            )
            for constraint_name, values in timelines.items():
                if constraint_name not in constraint_names:
                    raise MigrationError(
                        f"animation references missing {category} constraint {constraint_name!r}"
                    )
                names = {
                    "ik": {"mix": ("mix", 1.0), "softness": ("softness", 0.0)},
                    "transform": {
                        "rotateMix": ("mixRotate", 1.0),
                        "translateMix": ("mixX", 1.0),
                        "scaleMix": ("mixScaleX", 1.0),
                        "shearMix": ("mixShearY", 1.0),
                    },
                    "path": {
                        "position": ("position", 0.0),
                        "spacing": ("spacing", 0.0),
                        "mix": ("rotateMix", 1.0),
                    },
                }[category]
                if category == "transform":
                    for frame in require_records(values, f"{category} timeline {constraint_name}"):
                        for old, new, default in (
                            ("rotateMix", "mixRotate", 1.0),
                            ("translateMix", "mixX", 1.0),
                            ("scaleMix", "mixScaleX", 1.0),
                            ("shearMix", "mixShearY", 1.0),
                        ):
                            if old in frame:
                                frame[new] = frame.pop(old)
                        if "mixX" in frame:
                            frame["mixY"] = frame["mixX"]
                        if "mixScaleX" in frame:
                            frame["mixScaleY"] = frame["mixScaleX"]
                    add_curves(
                        _curve_fields(
                            require_records(values, "transform timeline"),
                            tuple(
                                (key, default)
                                for key, default in (
                                    ("mixRotate", 1.0),
                                    ("mixX", 1.0),
                                    ("mixY", 1.0),
                                    ("mixScaleX", 1.0),
                                    ("mixScaleY", 1.0),
                                    ("mixShearY", 1.0),
                                )
                            ),
                            f"{animation_name}.{constraint_name}.transform",
                        )
                    )
                elif category == "path":
                    path_timelines = require_object(values, f"path timelines {constraint_name}")
                    if set(path_timelines) - {"position", "spacing", "mix"}:
                        unsupported_path = sorted(
                            set(path_timelines) - {"position", "spacing", "mix"}
                        )
                        raise MigrationError(
                            f"unsupported path timeline(s): {', '.join(unsupported_path)}"
                        )
                    for timeline_name, timeline_value in path_timelines.items():
                        if timeline_name == "mix":
                            for frame in require_records(timeline_value, "path mix"):
                                frame["mixRotate"] = frame.pop(
                                    "rotateMix", frame.get("mixRotate", 1.0)
                                )
                                translate = frame.pop("translateMix", frame.get("mixX", 1.0))
                                frame["mixX"] = translate
                                frame["mixY"] = translate
                            add_curves(
                                _curve_fields(
                                    require_records(timeline_value, "path mix"),
                                    (("mixRotate", 1.0), ("mixX", 1.0), ("mixY", 1.0)),
                                    f"{animation_name}.{constraint_name}.path.mix",
                                )
                            )
                        elif timeline_name in ("position", "spacing"):
                            for frame in require_records(timeline_value, timeline_name):
                                _rename_exclusive(
                                    frame,
                                    timeline_name,
                                    "value",
                                    f"{animation_name}.{constraint_name}.{timeline_name}",
                                )
                            add_curves(
                                _curve_fields(
                                    require_records(timeline_value, timeline_name),
                                    (("value", 0.0),),
                                    f"{animation_name}.{constraint_name}.{timeline_name}",
                                )
                            )
                        else:
                            raise MigrationError(f"unsupported path timeline {timeline_name!r}")
                else:
                    frames = require_records(values, f"{category} timeline {constraint_name}")
                    # The 4.2 IK reader accepts both mix and softness curves.
                    constraint_channels: tuple[tuple[str, float], ...] = tuple(
                        (field, default) for field, default in names.values()
                    )
                    add_curves(
                        _curve_fields(
                            frames,
                            constraint_channels,
                            f"{animation_name}.{constraint_name}.{category}",
                        )
                    )
                stats["timeline_count"] += (
                    len(require_object(values, "path timelines")) if category == "path" else 1
                )
                stats["keyframes"] += (
                    sum(
                        len(require_records(v, "path keyframes"))
                        for v in require_object(values, "semantic object").values()
                    )
                    if category == "path"
                    else len(require_records(values, f"{category} timeline"))
                )
        deform_group_name = "deform" if target_version == "4.0.31" else "attachments"
        for group_name in (deform_group_name, "drawOrder", "events"):
            if group_name in animation:
                group = animation[group_name]
                if group_name == deform_group_name:
                    require_object(group, f"animation {animation_name}.attachments")
                    for skin_name, skin_value in require_object(group, "semantic object").items():
                        if skin_name not in {
                            skin["name"]
                            for skin in require_records(
                                target["skins"], "migrate_38_to_4x JSON field"
                            )
                        }:
                            raise MigrationError(
                                f"deform timeline references missing skin {skin_name!r}"
                            )
                        require_object(skin_value, f"deform skin {skin_name}")
                elif not isinstance(group, list):
                    raise MigrationError(
                        f"animation {animation_name}.{group_name} must be an array"
                    )
                if group_name == deform_group_name:
                    for skin_values in require_object(group, "semantic object").values():
                        for slot_values in require_object(skin_values, "semantic object").values():
                            for attachment_frames in require_object(
                                slot_values, "semantic object"
                            ).values():
                                frame_sets = (
                                    (attachment_frames,)
                                    if target_version == "4.0.31"
                                    else tuple(
                                        require_object(
                                            attachment_frames, "semantic object"
                                        ).values()
                                    )
                                )
                                for frame_values in frame_sets:
                                    deform_frames = require_records(frame_values, "deform timeline")
                                    stats["timeline_count"] += 1
                                    stats["keyframes"] += len(deform_frames)
                                    for frame_index, frame in enumerate(deform_frames):
                                        controls = _curve_controls(frame, "deform timeline")
                                        for key in ("c2", "c3", "c4"):
                                            frame.pop(key, None)
                                        if controls is not None:
                                            if frame_index + 1 >= len(deform_frames):
                                                raise MigrationError(
                                                    "Last deform frame cannot own a curve"
                                                )
                                            time0 = require_number(
                                                frame.get("time", 0), "deform keyframe time"
                                            )
                                            time1 = require_number(
                                                deform_frames[frame_index + 1].get("time", 0),
                                                "deform next keyframe time",
                                            )
                                            if time1 <= time0:
                                                raise MigrationError(
                                                    "deform Bézier segment times must increase"
                                                )
                                            cx1, cy1, cx2, cy2 = controls
                                            error = _curve_error(controls, 0.0, 1.0, time0, time1)
                                            stats["bezier_segments"] += 1
                                            stats["max_curve_error"] = max(
                                                stats["max_curve_error"], error
                                            )
                                            frame["curve"] = [
                                                time0 + cx1 * (time1 - time0),
                                                cy1,
                                                time0 + cx2 * (time1 - time0),
                                                cy2,
                                            ]
                if group_name in {"drawOrder", "events"}:
                    stats["timeline_count"] += 1
                    stats["keyframes"] += len(require_array(group, "event/draw-order keyframes"))
    if target_version == "4.3.13":
        target.pop("ik", None)
        target.pop("path", None)
        target.pop("transform", None)
    require_object(target["skeleton"], "migrate_38_to_4x JSON field")["spine"] = target_version
    _validate_target(target, target_version)
    return target, stats
