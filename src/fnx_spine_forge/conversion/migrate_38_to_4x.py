"""Schema transformations from supported Spine 3.8 exporters to qualified 4.x targets.

Field names and timeline layouts are based on the official Spine 3.8, 4.0, 4.1,
and 4.2 TypeScript SkeletonJson readers. Target-specific writers remain exact-version
gated, and migration is structural unless the matching runtime smoke is executed.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any


class MigrationError(ValueError):
    """A source feature cannot be represented safely in the requested schema."""


class UnsupportedMigrationFeature(MigrationError):
    """A valid source construct lacks a semantics-preserving target mapping."""

    def __init__(self, feature: str, message: str) -> None:
        super().__init__(message)
        self.feature = feature


def _map(value: Any, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MigrationError(f"{context} must be an object")
    return value


def _weighted_vertex_influences(vertices: list[Any], bone_count: int, context: str) -> int:
    position = 0
    influences = 0
    while position < len(vertices):
        count = vertices[position]
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise MigrationError(f"invalid weighted bone count: {context}")
        position += 1
        end = position + count * 4
        if end > len(vertices):
            raise MigrationError(f"truncated weighted vertex data: {context}")
        for influence in range(count):
            bone_index = vertices[position + influence * 4]
            weight = vertices[position + influence * 4 + 3]
            if (
                not isinstance(bone_index, int)
                or isinstance(bone_index, bool)
                or not 0 <= bone_index < bone_count
            ):
                raise MigrationError(f"weighted attachment references invalid bone: {context}")
            if (
                not isinstance(weight, (int, float))
                or isinstance(weight, bool)
                or not 0 <= weight <= 1
            ):
                raise MigrationError(f"weighted attachment has invalid weight: {context}")
        influences += count
        position = end
    return influences


def _validate_attachment_geometry(
    item: dict[str, Any], kind: str, context: str, bone_count: int
) -> None:
    if kind in {"mesh", "boundingbox", "path", "clipping"}:
        vertices = item.get("vertices")
        if not isinstance(vertices, list) or any(
            isinstance(value, bool) or not isinstance(value, (int, float)) for value in vertices
        ):
            raise MigrationError(f"invalid vertex data at {context}")
        if kind == "mesh":
            uvs = item.get("uvs")
            if (
                not isinstance(uvs, list)
                or len(uvs) % 2
                or any(
                    isinstance(value, bool) or not isinstance(value, (int, float)) for value in uvs
                )
            ):
                raise MigrationError(f"invalid mesh UV data at {context}")
            vertex_count = len(uvs) // 2
            if len(vertices) != len(uvs):
                _weighted_vertex_influences(vertices, bone_count, context)
            hull = item.get("hull", 0)
            if not isinstance(hull, int) or isinstance(hull, bool) or not 0 <= hull <= vertex_count:
                raise MigrationError(f"invalid mesh hull at {context}")
            triangles = item.get("triangles")
            if not isinstance(triangles, list) or any(
                not isinstance(index, int)
                or isinstance(index, bool)
                or not 0 <= index < vertex_count
                for index in triangles
            ):
                raise MigrationError(f"invalid mesh triangles at {context}")
        else:
            declared_vertex_count = item.get("vertexCount")
            if (
                not isinstance(declared_vertex_count, int)
                or isinstance(declared_vertex_count, bool)
                or declared_vertex_count < 0
            ):
                raise MigrationError(f"invalid vertexCount at {context}")
            if len(vertices) != declared_vertex_count * 2:
                _weighted_vertex_influences(vertices, bone_count, context)
            if kind == "path":
                lengths = item.get("lengths")
                if not isinstance(lengths, list) or any(
                    isinstance(value, bool) or not isinstance(value, (int, float))
                    for value in lengths
                ):
                    raise MigrationError(f"invalid path lengths at {context}")
        if kind == "clipping" and item.get("end") is not None:
            if not isinstance(item["end"], str):
                raise MigrationError(f"invalid clipping end slot at {context}")


def _frames(value: Any, context: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise MigrationError(f"{context} must be an array of keyframe objects")
    return value


def _number(value: Any, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MigrationError(f"{context} must be numeric")
    return float(value)


def _curve_controls(
    frame: Mapping[str, Any], context: str
) -> tuple[float, float, float, float] | None:
    curve = frame.get("curve")
    if curve is None:
        return None
    if curve == "stepped":
        return None
    if isinstance(curve, str):
        raise MigrationError(f"{context}: malformed legacy curve marker {curve!r}")
    cx1 = _number(curve, f"{context}.curve")
    c2 = _number(frame.get("c2", 0), f"{context}.c2")
    c3 = _number(frame.get("c3", 1), f"{context}.c3")
    c4 = _number(frame.get("c4", 1), f"{context}.c4")
    controls = (cx1, c2, c3, c4)
    if any(not 0 <= value <= 1 for value in controls):
        raise MigrationError(f"{context}: normalized Bézier controls must be in [0, 1]")
    return controls


def _target_curve(
    controls: tuple[float, float, float, float],
    start: float,
    end: float,
    time0: float,
    time1: float,
) -> list[float]:
    cx1, cy1, cx2, cy2 = controls
    delta = end - start
    duration = time1 - time0
    return [
        time0 + cx1 * duration,
        start + cy1 * delta,
        time0 + cx2 * duration,
        start + cy2 * delta,
    ]


def _cubic(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    u = 1 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def _curve_error(
    controls: tuple[float, float, float, float],
    start: float,
    end: float,
    time0: float,
    time1: float,
) -> float:
    """Numerically compare normalized 3.8 and absolute 4.2 curves at fixed times."""
    cx1, cy1, cx2, cy2 = controls
    delta = end - start
    maximum = 0.0
    for sample in range(257):
        x = sample / 256
        low, high = 0.0, 1.0
        for _ in range(48):
            middle = (low + high) / 2
            if _cubic(0, cx1, cx2, 1, middle) < x:
                low = middle
            else:
                high = middle
        t = (low + high) / 2
        old_value = _cubic(start, start + cy1 * delta, start + cy2 * delta, end, t)
        target = _target_curve(controls, start, end, time0, time1)
        normalized_target_x1 = (target[0] - time0) / (time1 - time0)
        normalized_target_x2 = (target[2] - time0) / (time1 - time0)
        target_t_low, target_t_high = 0.0, 1.0
        for _ in range(48):
            target_t = (target_t_low + target_t_high) / 2
            if _cubic(0, normalized_target_x1, normalized_target_x2, 1, target_t) < x:
                target_t_low = target_t
            else:
                target_t_high = target_t
        target_value = _cubic(start, target[1], target[3], end, (target_t_low + target_t_high) / 2)
        maximum = max(maximum, abs(old_value - target_value))
    return maximum


def _curve_fields(
    frames: list[dict[str, Any]],
    channels: tuple[tuple[str, float], ...],
    context: str,
) -> tuple[int, float]:
    """Convert one 3.8 shared normalized curve to 4.2 per-channel curves."""
    count = 0
    maximum_error = 0.0
    for index, frame in enumerate(frames):
        controls = _curve_controls(frame, f"{context}[{index}]")
        for key in ("c2", "c3", "c4"):
            frame.pop(key, None)
        if controls is None:
            continue
        if index + 1 >= len(frames):
            raise MigrationError(
                f"{context}[{index}]: final keyframe cannot own an interpolation curve"
            )
        curves: list[float] = []
        for field, default in channels:
            start = _number(frame.get(field, default), f"{context}[{index}].{field}")
            end = _number(frames[index + 1].get(field, default), f"{context}[{index + 1}].{field}")
            time0 = _number(frame.get("time", 0), f"{context}[{index}].time")
            time1 = _number(frames[index + 1].get("time", 0), f"{context}[{index + 1}].time")
            if time1 <= time0:
                raise MigrationError(f"{context}[{index}]: Bézier segment times must increase")
            curves.extend(_target_curve(controls, start, end, time0, time1))
            maximum_error = max(maximum_error, _curve_error(controls, start, end, time0, time1))
        frame["curve"] = curves
        count += len(channels)
    return count, maximum_error


def _color_channels(
    frames: list[dict[str, Any]], fields: tuple[str, ...], context: str
) -> tuple[int, float]:
    # 3.8 stores one normalized curve for all color channels. Spine 4.2 stores
    # absolute per-channel curves; colors are normalized byte components.
    channel_keys: list[tuple[str, float]] = []
    for field in fields:
        first = frames[0].get(field)
        if not isinstance(first, str) or len(first) not in (6, 8):
            raise MigrationError(f"{context}: {field} must be a 6- or 8-digit hex color")
        width = len(first) // 2
        for component in range(width):
            channel_keys.append((f"__{field}_{component}", 0.0))
        for frame in frames:
            color = frame.get(field)
            if not isinstance(color, str) or len(color) != len(first):
                raise MigrationError(f"{context}: inconsistent color representation in {field}")
            try:
                frame[f"__{field}_components"] = [
                    int(color[i : i + 2], 16) / 255 for i in range(0, len(color), 2)
                ]
            except ValueError as exc:
                raise MigrationError(f"{context}: invalid {field} color {color!r}") from exc
    count = 0
    maximum_error = 0.0
    for index, frame in enumerate(frames):
        controls = _curve_controls(frame, f"{context}[{index}]")
        for key in ("c2", "c3", "c4"):
            frame.pop(key, None)
        if controls is None:
            continue
        if index + 1 >= len(frames):
            raise MigrationError(
                f"{context}[{index}]: final keyframe cannot own an interpolation curve"
            )
        curves: list[float] = []
        for field in fields:
            current = frame[f"__{field}_components"]
            following = frames[index + 1][f"__{field}_components"]
            for start, end in zip(current, following, strict=True):
                time0 = _number(frame.get("time", 0), f"{context}[{index}].time")
                time1 = _number(frames[index + 1].get("time", 0), f"{context}[{index + 1}].time")
                if time1 <= time0:
                    raise MigrationError(f"{context}[{index}]: Bézier segment times must increase")
                curves.extend(_target_curve(controls, start, end, time0, time1))
                maximum_error = max(maximum_error, _curve_error(controls, start, end, time0, time1))
        frame["curve"] = curves
        count += len(curves) // 4
    for frame in frames:
        for field in fields:
            components = frame.pop(f"__{field}_components")
            del components
    return count, maximum_error


def _rename_exclusive(obj: dict[str, Any], old: str, new: str, context: str) -> None:
    if old in obj and new in obj:
        raise MigrationError(
            f"{context}: both legacy {old!r} and target {new!r} fields are present"
        )
    if old in obj:
        obj[new] = obj.pop(old)


def _validate_top_level(document: dict[str, Any]) -> None:
    supported = {
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
    extra = sorted(set(document) - supported)
    if extra:
        raise MigrationError(f"Unsupported 3.8 top-level fields: {', '.join(extra)}")
    if not isinstance(document.get("bones"), list) or not isinstance(document.get("slots"), list):
        raise MigrationError("3.8 skeleton requires bones and slots arrays")
    if not isinstance(document.get("skins"), list):
        raise MigrationError("3.8 skins must use the versioned skin array representation")
    if not isinstance(document.get("animations", {}), dict):
        raise MigrationError("animations must be an object keyed by animation name")


def _walk_attachments(document: dict[str, Any], target_version: str) -> None:
    slot_names = {slot.get("name") for slot in document["slots"] if isinstance(slot, dict)}
    bone_names = {bone.get("name") for bone in document["bones"] if isinstance(bone, dict)}
    skin_names: set[str] = set()
    linked_meshes: list[tuple[str, str, str, dict[str, Any]]] = []
    bone_count = len(bone_names)
    for skin in document["skins"]:
        _map(skin, "skin")
        skin_name = skin.get("name")
        if not isinstance(skin_name, str):
            raise MigrationError("skin name is required")
        skin_names.add(skin_name)
        attachments = _map(skin.get("attachments", {}), f"skin {skin_name}.attachments")
        for slot_name, values in attachments.items():
            if slot_name not in slot_names:
                raise MigrationError(
                    f"skin {skin_name}: attachment references missing slot {slot_name!r}"
                )
            for attachment_name, attachment in _map(
                values, f"skin {skin_name}.{slot_name}"
            ).items():
                item = _map(attachment, f"attachment {attachment_name}")
                kind = item.get("type", "region")
                if kind not in {
                    "region",
                    "mesh",
                    "linkedmesh",
                    "boundingbox",
                    "path",
                    "point",
                    "clipping",
                }:
                    raise MigrationError(
                        f"Unsupported attachment type {kind!r} at "
                        f"{skin_name}/{slot_name}/{attachment_name}"
                    )
                if (
                    kind in {"region", "mesh", "linkedmesh"}
                    and "path" in item
                    and (not isinstance(item["path"], str) or not item["path"])
                ):
                    raise MigrationError(
                        f"attachment path must be text at {skin_name}/{slot_name}/{attachment_name}"
                    )
                _validate_attachment_geometry(
                    item, kind, f"{skin_name}/{slot_name}/{attachment_name}", bone_count
                )
                if kind == "point":
                    for field in ("x", "y", "rotation"):
                        if field in item:
                            _number(
                                item[field], f"{skin_name}/{slot_name}/{attachment_name}.{field}"
                            )
                if kind == "clipping" and item.get("end") not in (None, *slot_names):
                    raise MigrationError(
                        f"clipping attachment references missing end slot {item['end']!r}"
                    )
                if kind == "linkedmesh":
                    parent = item.get("parent")
                    if not isinstance(parent, str):
                        raise MigrationError(
                            f"linked mesh parent is missing at "
                            f"{skin_name}/{slot_name}/{attachment_name}"
                        )
                    linked_meshes.append((skin_name, slot_name, attachment_name, item))
                if kind == "linkedmesh" and target_version != "4.0.31":
                    _rename_exclusive(
                        item, "deform", "timelines", f"linked mesh {attachment_name}"
                    )
    skins_by_name = {skin["name"]: skin for skin in document["skins"]}
    for owner_skin, slot_name, attachment_name, item in linked_meshes:
        parent_skin = item.get("skin", owner_skin)
        if not isinstance(parent_skin, str) or parent_skin not in skins_by_name:
            raise MigrationError(
                f"linked mesh {attachment_name!r} references missing skin {parent_skin!r}"
            )
        parent_name = item["parent"]
        parent_attachments = skins_by_name[parent_skin].get("attachments", {})
        if (
            slot_name not in parent_attachments
            or parent_name not in parent_attachments[slot_name]
        ):
            raise MigrationError(
                f"linked mesh {attachment_name!r} has missing parent {parent_name!r}"
            )
        if target_version == "4.3.13":
            item.pop("parent")
            item["source"] = parent_name
    # Validate bone parents and slot bone references.
    for bone in document["bones"]:
        _map(bone, "bone")
        if not isinstance(bone.get("name"), str):
            raise MigrationError("bone name is required")
        if bone.get("parent") is not None and bone["parent"] not in bone_names:
            raise MigrationError(
                f"bone {bone['name']!r} references missing parent {bone['parent']!r}"
            )
        transform = bone.get("transform")
        if transform is not None:
            mode = str(transform).lower()
            modes = {
                "normal": "Normal",
                "onlytranslation": "OnlyTranslation",
                "norotationorreflection": "NoRotationOrReflection",
                "noscale": "NoScale",
                "noscaleorreflection": "NoScaleOrReflection",
            }
            if mode not in modes:
                raise MigrationError(f"unsupported bone transform mode {transform!r}")
            if target_version == "4.2.43":
                bone.pop("transform")
                bone["inherit"] = modes[mode]
            else:
                bone["transform"] = modes[mode]
    for slot in document["slots"]:
        _map(slot, "slot")
        if slot.get("bone") not in bone_names:
            raise MigrationError(
                f"slot {slot.get('name')!r} references missing bone {slot.get('bone')!r}"
            )


def _validate_constraints(document: dict[str, Any]) -> None:
    bones = {bone["name"] for bone in document["bones"]}
    slots = {slot["name"] for slot in document["slots"]}
    constraints: dict[str, set[str]] = {"ik": set(), "transform": set(), "path": set()}
    for category in constraints:
        values = document.get(category, [])
        if not isinstance(values, list):
            raise MigrationError(f"{category} constraints must be an array")
        for constraint in values:
            item = _map(constraint, f"{category} constraint")
            name = item.get("name")
            if not isinstance(name, str):
                raise MigrationError(f"{category} constraint name is required")
            constraints[category].add(name)
            targets = item.get("bones", [item.get("bone")] if item.get("bone") else [])
            if any(target not in bones for target in targets):
                raise MigrationError(f"{category} constraint {name!r} references a missing bone")
            target = item.get("target")
            if target is not None and target not in (slots if category == "path" else bones):
                raise MigrationError(
                    f"{category} constraint {name!r} references missing target {target!r}"
                )
    for skin in document["skins"]:
        for category in constraints:
            names = skin.get(category, [])
            if any(name not in constraints[category] for name in names):
                raise MigrationError(
                    f"skin {skin['name']!r} references an unknown {category} constraint"
                )


def _migrate_constraint_definitions(document: dict[str, Any]) -> None:
    for constraint in document.get("transform", []):
        _rename_exclusive(constraint, "rotateMix", "mixRotate", "transform constraint")
        _rename_exclusive(constraint, "translateMix", "mixX", "transform constraint")
        _rename_exclusive(constraint, "scaleMix", "mixScaleX", "transform constraint")
        _rename_exclusive(constraint, "shearMix", "mixShearY", "transform constraint")
        if "mixX" in constraint:
            constraint.setdefault("mixY", constraint["mixX"])
        if "mixScaleX" in constraint:
            constraint.setdefault("mixScaleY", constraint["mixScaleX"])
    for constraint in document.get("path", []):
        _rename_exclusive(constraint, "rotateMix", "mixRotate", "path constraint")
        _rename_exclusive(constraint, "translateMix", "mixX", "path constraint")
        if "mixX" in constraint:
            constraint.setdefault("mixY", constraint["mixX"])


def _migrate_constraints_to_43(document: dict[str, Any]) -> None:
    """Combine supported IK and path constraints into Spine 4.3's ordered list."""
    if document.get("transform"):
        raise MigrationError(
            "Spine 4.3 transform constraints use property mappings; this route does not "
            "currently represent them faithfully"
        )
    for skin in document["skins"]:
        if skin.get("transform"):
            raise MigrationError("Spine 4.3 transform constraints in skins are unsupported")
    for animation_name, animation in document.get("animations", {}).items():
        if animation.get("transform"):
            raise MigrationError(
                f"Spine 4.3 transform constraint timelines are unsupported in {animation_name!r}"
            )

    ordered: list[tuple[int, int, dict[str, Any]]] = []
    stable_index = 0
    for constraint_type in ("ik", "path"):
        values = document.get(constraint_type, [])
        if not isinstance(values, list):
            raise MigrationError(f"{constraint_type} constraints must be an array")
        for value in values:
            constraint = _map(value, f"{constraint_type} constraint")
            order = constraint.get("order", 0)
            if not isinstance(order, int) or isinstance(order, bool):
                raise MigrationError(f"{constraint_type} constraint order must be an integer")
            if constraint_type == "ik" and constraint.get("uniform", False):
                raise MigrationError(
                    "Spine 4.3 IK scaleY mode cannot be inferred losslessly from legacy uniform IK"
                )
            migrated = deepcopy(constraint)
            migrated.pop("order", None)
            migrated.pop("uniform", None)
            migrated["type"] = constraint_type
            ordered.append((order, stable_index, migrated))
            stable_index += 1
    ordered.sort(key=lambda entry: (entry[0], entry[1]))
    document["constraints"] = [entry[2] for entry in ordered]
def _validate_target(document: dict[str, Any], target_version: str) -> None:
    if document.get("skeleton", {}).get("spine") != target_version:
        raise MigrationError("Target skeleton version metadata is invalid")
    valid_modes = {
        "Normal",
        "OnlyTranslation",
        "NoRotationOrReflection",
        "NoScale",
        "NoScaleOrReflection",
    }
    mode_key = "inherit" if target_version in {"4.2.43", "4.3.13"} else "transform"
    other_key = "transform" if mode_key == "inherit" else "inherit"
    for bone in document["bones"]:
        if other_key in bone or bone.get(mode_key, "Normal") not in valid_modes:
            raise MigrationError(
                f"Invalid Spine {target_version} bone transform schema for {bone.get('name')!r}"
            )
    for skin in document["skins"]:
        for slot_name, values in skin.get("attachments", {}).items():
            for attachment_name, attachment in values.items():
                if attachment.get("type") == "linkedmesh":
                    if target_version == "4.0.31":
                        invalid_link = "timelines" in attachment or not isinstance(
                            attachment.get("deform", True), bool
                        )
                    elif target_version == "4.3.13":
                        invalid_link = (
                            "parent" in attachment
                            or not isinstance(attachment.get("source"), str)
                            or "deform" in attachment
                            or not isinstance(attachment.get("timelines", True), bool)
                        )
                    else:
                        invalid_link = "deform" in attachment or not isinstance(
                            attachment.get("timelines", True), bool
                        )
                    if invalid_link:
                        raise MigrationError(
                            f"Invalid Spine {target_version} linked mesh schema at "
                            f"{slot_name}/{attachment_name}"
                        )
    if target_version == "4.3.13":
        if any(category in document for category in ("ik", "transform", "path")):
            raise MigrationError("Spine 4.3 requires combined constraints serialization")
        constraints = document.get("constraints")
        if not isinstance(constraints, list) or any(
            item.get("type") not in {"ik", "path"} for item in constraints
        ):
            raise MigrationError("Invalid Spine 4.3 combined constraint list")
    for animation_name, animation in document.get("animations", {}).items():
        if "draworder" in animation or (
            target_version != "4.0.31" and "deform" in animation
        ):
            raise MigrationError(f"Legacy animation group remained in {animation_name!r}")
        for slot_name, timeline_set in animation.get("slots", {}).items():
            if "color" in timeline_set or "twoColor" in timeline_set:
                raise MigrationError(
                    f"Legacy color timeline remained in {animation_name}/{slot_name}"
                )
        for bone_name, timeline_set in animation.get("bones", {}).items():
            for timeline_name, frames in timeline_set.items():
                if timeline_name == "rotate" and any("angle" in frame for frame in frames):
                    raise MigrationError(
                        f"Legacy rotation value remained in {animation_name}/{bone_name}"
                    )
                for frame in frames:
                    curve = frame.get("curve")
                    if curve is not None and not isinstance(curve, (list, str)):
                        raise MigrationError(
                            f"Legacy scalar Bézier curve remained in {animation_name}/{bone_name}"
                        )
                    if isinstance(curve, list) and (
                        len(curve) % 4
                        or any(
                            isinstance(value, bool) or not isinstance(value, (int, float))
                            for value in curve
                        )
                    ):
                        raise MigrationError(
                            f"Invalid Spine {target_version} per-channel curve in "
                            f"{animation_name}/{bone_name}"
                        )


def _deform_length(attachment: dict[str, Any], context: str) -> int:
    kind = attachment.get("type", "region")
    vertices = attachment.get("vertices")
    if kind not in {"mesh", "boundingbox", "path", "clipping"}:
        raise MigrationError(f"deform timeline targets non-vertex attachment: {context}")
    if not isinstance(vertices, list):
        raise MigrationError(f"vertex attachment has no vertex array: {context}")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in vertices):
        raise MigrationError(f"vertex attachment contains non-numeric data: {context}")
    if kind == "mesh":
        uvs = attachment.get("uvs")
        if not isinstance(uvs, list):
            raise MigrationError(f"mesh has no UV array: {context}")
        if len(vertices) == len(uvs):
            return len(vertices)
        # Weighted vertices use count followed by (bone, x, y, weight) records.
        position = 0
        influences = 0
        while position < len(vertices):
            count_value = vertices[position]
            if not isinstance(count_value, int) or isinstance(count_value, bool) or count_value < 1:
                raise MigrationError(f"invalid weighted mesh bone count: {context}")
            position += 1
            end = position + count_value * 4
            if end > len(vertices):
                raise MigrationError(f"truncated weighted mesh vertex data: {context}")
            influences += count_value
            position = end
        return influences * 2
    vertex_count = attachment.get("vertexCount")
    if not isinstance(vertex_count, int) or isinstance(vertex_count, bool) or vertex_count < 0:
        raise MigrationError(f"invalid vertexCount: {context}")
    if len(vertices) == vertex_count * 2:
        return len(vertices)
    # Weighted vertices are encoded in the same count + four-value layout.
    position = 0
    influences = 0
    while position < len(vertices):
        count_value = vertices[position]
        if not isinstance(count_value, int) or isinstance(count_value, bool) or count_value < 1:
            raise MigrationError(f"invalid weighted vertex bone count: {context}")
        position += 1
        end = position + count_value * 4
        if end > len(vertices):
            raise MigrationError(f"truncated weighted vertex data: {context}")
        influences += count_value
        position = end
    return influences * 2


def _validate_deform_group(document: dict[str, Any], group: Any, animation: str) -> None:
    skin_by_name = {skin["name"]: skin for skin in document["skins"]}
    slot_names = {slot["name"] for slot in document["slots"]}
    deform_group = _map(group, f"animation {animation}.deform")
    for skin_name, skin_timelines in deform_group.items():
        if skin_name not in skin_by_name:
            raise MigrationError(f"deform timeline references missing skin {skin_name!r}")
        slots = _map(skin_timelines, f"deform skin {skin_name}")
        for slot_name, attachments_value in slots.items():
            if slot_name not in slot_names:
                raise MigrationError(f"deform timeline references missing slot {slot_name!r}")
            attachments = _map(attachments_value, f"deform slot {slot_name}")
            definitions = skin_by_name[skin_name]["attachments"].get(slot_name, {})
            for attachment_name, frame_values in attachments.items():
                definition = definitions.get(attachment_name)
                if not isinstance(definition, dict):
                    raise MigrationError(
                        f"deform timeline references missing attachment {attachment_name!r}"
                    )
                resolved = definition
                resolved_skin = skin_name
                visited: set[tuple[str, str]] = set()
                while resolved.get("type") == "linkedmesh":
                    parent_name = resolved.get("parent")
                    parent_skin = resolved.get("skin", resolved_skin)
                    identity = (str(parent_skin), str(parent_name))
                    if identity in visited:
                        raise MigrationError(
                            f"linked mesh parent cycle while resolving {attachment_name!r}"
                        )
                    visited.add(identity)
                    parent_definition = (
                        skin_by_name.get(str(parent_skin), {})
                        .get("attachments", {})
                        .get(slot_name, {})
                        .get(parent_name)
                    )
                    if not isinstance(parent_definition, dict):
                        raise MigrationError(
                            f"deform linked mesh parent is missing: {parent_name!r}"
                        )
                    resolved = parent_definition
                    resolved_skin = str(parent_skin)
                length = _deform_length(resolved, f"{skin_name}/{slot_name}/{attachment_name}")
                frames = _frames(frame_values, f"deform timeline {attachment_name}")
                for frame in frames:
                    frame_vertices = frame.get("vertices")
                    if frame_vertices is None:
                        continue
                    if not isinstance(frame_vertices, list) or any(
                        isinstance(value, bool) or not isinstance(value, (int, float))
                        for value in frame_vertices
                    ):
                        raise MigrationError(f"invalid deform values for {attachment_name!r}")
                    offset = frame.get("offset", 0)
                    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                        raise MigrationError(f"invalid deform offset for {attachment_name!r}")
                    if offset + len(frame_vertices) > length:
                        raise MigrationError(
                            f"deform range exceeds attachment geometry for {attachment_name!r}"
                        )


def migrate_38_to_target(
    source: dict[str, Any], source_version: str, target_version: str
) -> tuple[dict[str, Any], dict[str, int | float]]:
    """Transform supported exact 3.8 exports into a qualified later schema."""
    target = deepcopy(source)
    _validate_top_level(target)
    if source_version not in {"3.8.75", "3.8.99"}:
        raise MigrationError(f"Unsupported exact Spine 3.8 source version {source_version!r}")
    if target_version not in {"4.0.31", "4.1.56", "4.2.43", "4.3.13"}:
        raise MigrationError(f"Unsupported exact Spine target version {target_version!r}")
    if target["skeleton"].get("spine") != source_version:
        raise MigrationError("Source version argument does not match skeleton metadata")
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    _migrate_constraint_definitions(target)
    if target_version == "4.3.13":
        _migrate_constraints_to_43(target)
    animations = target.get("animations", {})
    stats = {"bezier_segments": 0, "timeline_count": 0, "keyframes": 0, "max_curve_error": 0.0}

    def add_curves(result: tuple[int, float]) -> None:
        stats["bezier_segments"] += result[0]
        stats["max_curve_error"] = max(stats["max_curve_error"], result[1])

    for animation_name, animation_value in animations.items():
        animation = _map(animation_value, f"animation {animation_name}")
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
            attachments_group = _map(
                animation["attachments"], f"animation {animation_name}.attachments"
            )
            for skin_name, skin_value in attachments_group.items():
                skin_map = _map(skin_value, f"deform skin {skin_name}")
                for slot_name, slot_value in skin_map.items():
                    slot_map = _map(slot_value, f"deform slot {slot_name}")
                    for attachment_name, frames_value in list(slot_map.items()):
                        if not isinstance(frames_value, list):
                            raise MigrationError(
                                f"deform frames for {attachment_name!r} must be an array"
                            )
                        slot_map[attachment_name] = {"deform": frames_value}
        for slot_name, timeline_set_value in _map(
            animation.get("slots", {}), f"animation {animation_name}.slots"
        ).items():
            timeline_set = _map(timeline_set_value, f"slot timelines {slot_name}")
            if slot_name not in {slot["name"] for slot in target["slots"]}:
                raise MigrationError(
                    f"animation {animation_name!r} references missing slot {slot_name!r}"
                )
            _rename_exclusive(timeline_set, "color", "rgba", f"slot {slot_name}")
            _rename_exclusive(timeline_set, "twoColor", "rgba2", f"slot {slot_name}")
            for name, value in timeline_set.items():
                frames = _frames(value, f"slot timeline {name}")
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
        for bone_name, timeline_set_value in _map(
            animation.get("bones", {}), f"animation {animation_name}.bones"
        ).items():
            timeline_set = _map(timeline_set_value, f"bone timelines {bone_name}")
            if bone_name not in {bone["name"] for bone in target["bones"]}:
                raise MigrationError(
                    f"animation {animation_name!r} references missing bone {bone_name!r}"
                )
            for name, value in timeline_set.items():
                frames = _frames(value, f"bone timeline {name}")
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
            ("ik", {c["name"] for c in target.get("ik", [])}),
            ("transform", {c["name"] for c in target.get("transform", [])}),
            ("path", {c["name"] for c in target.get("path", [])}),
        ):
            timelines = _map(animation.get(category, {}), f"animation {animation_name}.{category}")
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
                    for frame in _frames(values, f"{category} timeline {constraint_name}"):
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
                            _frames(values, "transform timeline"),
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
                    path_timelines = _map(values, f"path timelines {constraint_name}")
                    if set(path_timelines) - {"position", "spacing", "mix"}:
                        unsupported_path = sorted(
                            set(path_timelines) - {"position", "spacing", "mix"}
                        )
                        raise MigrationError(
                            f"unsupported path timeline(s): {', '.join(unsupported_path)}"
                        )
                    for timeline_name, timeline_value in path_timelines.items():
                        if timeline_name == "mix":
                            for frame in _frames(timeline_value, "path mix"):
                                frame["mixRotate"] = frame.pop(
                                    "rotateMix", frame.get("mixRotate", 1.0)
                                )
                                translate = frame.pop("translateMix", frame.get("mixX", 1.0))
                                frame["mixX"] = translate
                                frame["mixY"] = translate
                            add_curves(
                                _curve_fields(
                                    _frames(timeline_value, "path mix"),
                                    (("mixRotate", 1.0), ("mixX", 1.0), ("mixY", 1.0)),
                                    f"{animation_name}.{constraint_name}.path.mix",
                                )
                            )
                        elif timeline_name in ("position", "spacing"):
                            for frame in _frames(timeline_value, timeline_name):
                                _rename_exclusive(
                                    frame,
                                    timeline_name,
                                    "value",
                                    f"{animation_name}.{constraint_name}.{timeline_name}",
                                )
                            add_curves(
                                _curve_fields(
                                    _frames(timeline_value, timeline_name),
                                    (("value", 0.0),),
                                    f"{animation_name}.{constraint_name}.{timeline_name}",
                                )
                            )
                        else:
                            raise MigrationError(f"unsupported path timeline {timeline_name!r}")
                else:
                    frames = _frames(values, f"{category} timeline {constraint_name}")
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
                stats["timeline_count"] += len(values) if category == "path" else 1
                stats["keyframes"] += (
                    sum(len(v) for v in values.values())
                    if category == "path"
                    else len(_frames(values, f"{category} timeline"))
                )
        deform_group_name = "deform" if target_version == "4.0.31" else "attachments"
        for group_name in (deform_group_name, "drawOrder", "events"):
            if group_name in animation:
                group = animation[group_name]
                if group_name == deform_group_name:
                    _map(group, f"animation {animation_name}.attachments")
                    for skin_name, skin_value in group.items():
                        if skin_name not in {skin["name"] for skin in target["skins"]}:
                            raise MigrationError(
                                f"deform timeline references missing skin {skin_name!r}"
                            )
                        _map(skin_value, f"deform skin {skin_name}")
                elif not isinstance(group, list):
                    raise MigrationError(
                        f"animation {animation_name}.{group_name} must be an array"
                    )
                if group_name == deform_group_name:
                    for skin_values in group.values():
                        for slot_values in skin_values.values():
                            for attachment_frames in slot_values.values():
                                frame_sets = (
                                    (attachment_frames,)
                                    if target_version == "4.0.31"
                                    else tuple(attachment_frames.values())
                                )
                                for frames in frame_sets:
                                    deform_frames = _frames(frames, "deform timeline")
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
                                            time0 = _number(
                                                frame.get("time", 0), "deform keyframe time"
                                            )
                                            time1 = _number(
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
                    stats["keyframes"] += len(group)
    if target_version == "4.3.13":
        target.pop("ik", None)
        target.pop("path", None)
        target.pop("transform", None)
    target["skeleton"]["spine"] = target_version
    _validate_target(target, target_version)
    return target, stats
