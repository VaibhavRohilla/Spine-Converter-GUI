"""Validated typed views over high-risk Spine JSON semantics.

Raw mappings remain at the JSON boundary for migration writers. This module
provides strict, version-aware indexes so callers can inspect constructs
without treating arbitrary dictionaries as validated semantics.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, cast


@dataclass(frozen=True, slots=True)
class BoneTransform:
    x: float
    y: float
    rotation: float
    scale_x: float
    scale_y: float
    shear_x: float
    shear_y: float
    mode: str | None


@dataclass(frozen=True, slots=True)
class BoneDefinition:
    name: str
    parent: str | None
    transform: BoneTransform


@dataclass(frozen=True, slots=True)
class SlotDefinition:
    name: str
    bone: str
    attachment: str | None
    color: str | None


@dataclass(frozen=True, slots=True)
class AttachmentDefinition:
    name: str
    kind: Literal["region", "mesh", "linkedmesh", "boundingbox", "path", "clipping", "point"]
    path: str | None
    parent: str | None
    vertices: tuple[float, ...]
    weighted: bool


@dataclass(frozen=True, slots=True)
class ConstraintDefinition:
    kind: Literal["ik", "path", "transform", "physics"]
    name: str
    target: str | None
    bones: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TimelineDefinition:
    animation: str
    category: str
    owner: str
    timeline: str
    keyframes: int
    curves: tuple[tuple[float, float, float, float], ...]


@dataclass(frozen=True, slots=True)
class SemanticSkeleton:
    version: str
    bones: tuple[BoneDefinition, ...]
    slots: tuple[SlotDefinition, ...]
    skins: tuple[str, ...]
    attachments: tuple[AttachmentDefinition, ...]
    constraints: tuple[ConstraintDefinition, ...]
    timelines: tuple[TimelineDefinition, ...]


@dataclass(frozen=True, slots=True)
class AtlasRegionGeometry:
    page: str
    name: str
    x: int
    y: int
    width: int
    height: int
    original_width: int
    original_height: int
    offset_x: int
    offset_y: int
    rotation_degrees: int


def decode_atlas_geometry(atlas: object, version: str) -> tuple[AtlasRegionGeometry, ...]:
    """Decode region geometry using the exact atlas vocabulary for a Spine patch."""
    if version not in {
        "3.5.51",
        "3.6.53",
        "3.7.94",
        "3.8.75",
        "3.8.99",
        "4.0.31",
        "4.1.56",
        "4.2.43",
        "4.3.13",
    }:
        raise ValueError(f"No atlas geometry schema is defined for {version!r}")
    pages = getattr(atlas, "pages", ())
    regions = getattr(atlas, "regions", ())
    page_records = getattr(atlas, "page_records", pages)
    region_pages = getattr(atlas, "region_pages", ())
    decoded: list[AtlasRegionGeometry] = []
    for region, page_index in zip(regions, region_pages, strict=True):
        attrs = dict(region.attributes)
        page = page_records[page_index].name
        if version.startswith(("4.2.", "4.3.")):
            if not {"bounds", "offsets", "rotate"} <= attrs.keys():
                raise ValueError(f"Atlas region {region.name!r} does not match {version} geometry")
            x, y, width, height = _integer_tuple(attrs["bounds"], 4, region.name)
            ox, oy, original_width, original_height = _integer_tuple(
                attrs["offsets"], 4, region.name
            )
            rotation = _integer(attrs["rotate"], region.name)
        else:
            if not {"xy", "size"} <= attrs.keys():
                raise ValueError(f"Atlas region {region.name!r} does not match {version} geometry")
            x, y = _integer_tuple(attrs["xy"], 2, region.name)
            width, height = _integer_tuple(attrs["size"], 2, region.name)
            original_width, original_height = _integer_tuple(
                attrs.get("orig", attrs["size"]), 2, region.name
            )
            ox, oy = _integer_tuple(attrs.get("offset", "0,0"), 2, region.name)
            rotate = attrs.get("rotate", "false").lower()
            if rotate not in {"false", "true"}:
                raise ValueError(f"Unsupported {version} rotation {rotate!r} on {region.name!r}")
            rotation = 90 if rotate == "true" else 0
        if (
            rotation not in {0, 90, 180, 270}
            or min(width, height, original_width, original_height) < 0
        ):
            raise ValueError(f"Invalid atlas region geometry for {region.name!r}")
        if not page or page_index >= len(pages):
            raise ValueError(f"Atlas region {region.name!r} has no valid page")
        decoded.append(
            AtlasRegionGeometry(
                page,
                region.name,
                x,
                y,
                width,
                height,
                original_width,
                original_height,
                ox,
                oy,
                rotation,
            )
        )
    return tuple(decoded)


def _integer_tuple(value: object, count: int, name: str) -> tuple[int, ...]:
    if not isinstance(value, str):
        raise ValueError(f"Atlas region {name!r} has non-text geometry")
    parts = tuple(_integer(part.strip(), name) for part in value.split(","))
    if len(parts) != count:
        raise ValueError(f"Atlas region {name!r} has invalid geometry tuple")
    return parts


def _integer(value: str, name: str) -> int:
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"Atlas region {name!r} has invalid integer geometry") from exc


_BONE_KEYS = {
    "name",
    "parent",
    "length",
    "x",
    "y",
    "rotation",
    "scaleX",
    "scaleY",
    "shearX",
    "shearY",
    "transform",
    "inherit",
    "skin",
    "skinRequired",
    "icon",
    "color",
}
_SLOT_KEYS = {"name", "bone", "attachment", "color", "dark", "blend", "visible"}
_ATTACHMENT_KEYS = {
    "type",
    "path",
    "x",
    "y",
    "scaleX",
    "scaleY",
    "rotation",
    "width",
    "height",
    "color",
    "uvs",
    "triangles",
    "vertices",
    "hull",
    "edges",
    "width",
    "height",
    "vertexCount",
    "lengths",
    "closed",
    "constantSpeed",
    "end",
    "rotation",
    "name",
    "parent",
    "deform",
    "timelines",
    "sequence",
    "inheritDeform",
    "fps",
    "mode",
}
_ATTACHMENT_KEYS.update({"source", "color2", "sequence", "vertices", "bones"})


def _mapping(value: object, where: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{where} must be an object with string keys")
    return value


def _number(value: object, where: str, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{where} must be numeric")
    return float(value)


def decode_semantic_skeleton(document: Mapping[str, object], version: str) -> SemanticSkeleton:
    """Decode supported high-risk records for one exact recognized patch version."""
    supported_versions = {
        "3.5.51",
        "3.6.53",
        "3.7.94",
        "3.8.75",
        "3.8.99",
        "4.0.31",
        "4.1.56",
        "4.2.43",
        "4.3.13",
    }
    if version not in supported_versions:
        raise ValueError(f"No semantic schema is defined for exact Spine version {version!r}")
    metadata = _mapping(document.get("skeleton"), "skeleton")
    if metadata.get("spine") != version:
        raise ValueError(
            f"Declared source version {metadata.get('spine')!r} does not match {version}"
        )
    raw_bones = document.get("bones", [])
    if not isinstance(raw_bones, list):
        raise ValueError("bones must be an array")
    bones: list[BoneDefinition] = []
    for index, raw in enumerate(raw_bones):
        row = _mapping(raw, f"bones[{index}]")
        unknown = set(row) - _BONE_KEYS
        if unknown:
            raise ValueError(
                f"Unknown semantic bone fields for {version}: {', '.join(sorted(unknown))}"
            )
        name = row.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError(f"bones[{index}].name must be non-empty")
        parent = row.get("parent")
        if parent is not None and not isinstance(parent, str):
            raise ValueError(f"bones[{index}].parent must be a string")
        mode_key = (
            "transform"
            if version.startswith("4.0.")
            else "inherit"
            if version.startswith(("4.1.", "4.2.", "4.3."))
            else None
        )
        mode = row.get(mode_key) if mode_key else None
        if mode is not None and not isinstance(mode, str):
            raise ValueError(f"bones[{index}].{mode_key} must be a string")
        bones.append(
            BoneDefinition(
                name,
                parent,
                BoneTransform(
                    _number(row.get("x"), f"bones[{index}].x"),
                    _number(row.get("y"), f"bones[{index}].y"),
                    _number(row.get("rotation"), f"bones[{index}].rotation"),
                    _number(row.get("scaleX"), f"bones[{index}].scaleX", 1),
                    _number(row.get("scaleY"), f"bones[{index}].scaleY", 1),
                    _number(row.get("shearX"), f"bones[{index}].shearX"),
                    _number(row.get("shearY"), f"bones[{index}].shearY"),
                    mode,
                ),
            )
        )
    bone_names = {bone.name for bone in bones}
    for bone_record in bones:
        if bone_record.parent is not None and bone_record.parent not in bone_names:
            raise ValueError(
                f"Bone {bone_record.name!r} references missing parent {bone_record.parent!r}"
            )

    raw_slots = document.get("slots", [])
    if not isinstance(raw_slots, list):
        raise ValueError("slots must be an array")
    slots: list[SlotDefinition] = []
    for index, raw in enumerate(raw_slots):
        row = _mapping(raw, f"slots[{index}]")
        unknown = set(row) - _SLOT_KEYS
        if unknown:
            raise ValueError(
                f"Unknown semantic slot fields for {version}: {', '.join(sorted(unknown))}"
            )
        name, bone = row.get("name"), row.get("bone")
        if not isinstance(name, str) or not isinstance(bone, str) or bone not in bone_names:
            raise ValueError(f"slots[{index}] has invalid name or bone reference")
        attachment, color = row.get("attachment"), row.get("color")
        if attachment is not None and not isinstance(attachment, str):
            raise ValueError(f"slots[{index}].attachment must be a string")
        if color is not None and not isinstance(color, str):
            raise ValueError(f"slots[{index}].color must be a string")
        slots.append(SlotDefinition(name, bone, attachment, color))

    raw_skins = document.get("skins", [])
    skins: list[str] = []
    attachments: list[AttachmentDefinition] = []
    linked_parents: list[tuple[str, str, str, str]] = []
    attachment_names_by_skin_slot: dict[tuple[str, str], set[str]] = {}
    if isinstance(raw_skins, list):
        for skin_index, raw_skin in enumerate(raw_skins):
            skin = _mapping(raw_skin, f"skins[{skin_index}]")
            skin_name = skin.get("name")
            if not isinstance(skin_name, str):
                raise ValueError(f"skins[{skin_index}].name must be a string")
            skins.append(skin_name)
            attachment_map = _mapping(
                skin.get("attachments", {}), f"skins[{skin_index}].attachments"
            )
            for slot_name, slot_map_raw in attachment_map.items():
                if slot_name not in {slot.name for slot in slots}:
                    raise ValueError(f"Skin {skin_name!r} references missing slot {slot_name!r}")
                slot_map = _mapping(slot_map_raw, f"skin {skin_name}.{slot_name}")
                attachment_names_by_skin_slot.setdefault((skin_name, slot_name), set()).update(
                    slot_map
                )
                for attachment_name, attachment_raw in slot_map.items():
                    row = _mapping(attachment_raw, f"attachment {attachment_name}")
                    unknown = set(row) - _ATTACHMENT_KEYS
                    if unknown:
                        raise ValueError(
                            f"Unknown semantic attachment fields for {version}: "
                            f"{', '.join(sorted(unknown))}"
                        )
                    kind_value = row.get("type", "region")
                    if kind_value not in {
                        "region",
                        "mesh",
                        "linkedmesh",
                        "boundingbox",
                        "path",
                        "clipping",
                        "point",
                    }:
                        raise ValueError(f"Unsupported attachment discriminator {kind_value!r}")
                    vertices_raw = row.get("vertices", [])
                    if not isinstance(vertices_raw, list):
                        raise ValueError(
                            f"Attachment {attachment_name!r} vertices must be an array"
                        )
                    vertices = tuple(_number(value, "attachment vertex") for value in vertices_raw)
                    parent = row.get("parent", row.get("source"))
                    path = row.get("path")
                    if parent is not None and not isinstance(parent, str):
                        raise ValueError("Linked mesh parent must be a string")
                    if path is not None and not isinstance(path, str):
                        raise ValueError("Attachment path must be a string")
                    if kind_value == "linkedmesh":
                        if parent is None:
                            raise ValueError(f"Linked mesh {attachment_name!r} lacks parent")
                        linked_parents.append((skin_name, slot_name, attachment_name, parent))
                    uvs = row.get("uvs", [])
                    if not isinstance(uvs, list):
                        raise ValueError(f"Attachment {attachment_name!r} UVs must be an array")
                    weighted = bool(
                        kind_value == "mesh" and vertices_raw and len(vertices_raw) != len(uvs)
                    )
                    if weighted:
                        _validate_weighted_vertices(vertices, len(bone_names), attachment_name)
                    attachments.append(
                        AttachmentDefinition(
                            attachment_name,
                            kind_value,
                            path,
                            parent,
                            vertices,
                            weighted,
                        )
                    )
    elif isinstance(raw_skins, Mapping):
        skins.extend(str(name) for name in raw_skins)
        # Legacy object-map skins are retained as raw serialization boundary data;
        # this version decoder currently indexes newer named-skin records only.
    else:
        raise ValueError("skins must be a version-specific array or object")
    for skin_name, slot_name, linked_name, parent_name in linked_parents:
        if parent_name not in attachment_names_by_skin_slot.get((skin_name, slot_name), set()):
            raise ValueError(
                f"Linked mesh {linked_name!r} references missing parent {parent_name!r} "
                f"in slot {slot_name!r}"
            )

    constraints: list[ConstraintDefinition] = []
    for category in ("ik", "path", "transform", "physics"):
        values = document.get(category, [])
        if not isinstance(values, list):
            continue
        for index, raw in enumerate(values):
            row = _mapping(raw, f"{category}[{index}]")
            name = row.get("name")
            target = row.get("target")
            bone_list = row.get("bones", [])
            if not isinstance(name, str) or (target is not None and not isinstance(target, str)):
                raise ValueError(f"{category}[{index}] has invalid identity fields")
            if not isinstance(bone_list, list) or any(
                not isinstance(item, str) for item in bone_list
            ):
                raise ValueError(f"{category}[{index}].bones must be an array of names")
            constraints.append(ConstraintDefinition(category, name, target, tuple(bone_list)))

    timelines: list[TimelineDefinition] = []
    animations = _mapping(document.get("animations", {}), "animations")
    for animation_name, raw_animation in animations.items():
        animation = _mapping(raw_animation, f"animation {animation_name}")
        for category in (
            "bones",
            "slots",
            "ik",
            "path",
            "transform",
            "physics",
            "attachments",
            "deform",
            "drawOrder",
            "draworder",
            "events",
        ):
            group = animation.get(category)
            if group is None:
                continue
            _collect_timelines(timelines, animation_name, category, group)
    return SemanticSkeleton(
        version,
        tuple(bones),
        tuple(slots),
        tuple(skins),
        tuple(attachments),
        tuple(constraints),
        tuple(timelines),
    )


def _collect_timelines(
    out: list[TimelineDefinition],
    animation: str,
    category: str,
    value: object,
    owner: str = "",
) -> None:
    if isinstance(value, list):
        curves: list[tuple[float, float, float, float]] = []
        for frame_index, frame_raw in enumerate(value):
            frame = _mapping(frame_raw, f"{category} frame")
            curve = frame.get("curve")
            if isinstance(curve, list):
                if not curve or len(curve) % 4:
                    raise ValueError(
                        "Per-channel Bézier controls must be a non-empty multiple of four"
                    )
                for offset in range(0, len(curve), 4):
                    points = tuple(
                        _number(part, "Bézier control") for part in curve[offset : offset + 4]
                    )
                    curves.append(cast(tuple[float, float, float, float], points))
            elif curve is not None and curve != "stepped" and not isinstance(curve, (int, float)):
                raise ValueError("Unsupported Bézier interpolation encoding")
        out.append(
            TimelineDefinition(animation, category, owner, "frames", len(value), tuple(curves))
        )
        return
    if isinstance(value, Mapping):
        for key, child in value.items():
            _collect_timelines(out, animation, category, child, f"{owner}/{key}".strip("/"))


def _validate_weighted_vertices(vertices: tuple[float, ...], bone_count: int, name: str) -> None:
    position = 0
    while position < len(vertices):
        count = vertices[position]
        if count < 1 or not count.is_integer():
            raise ValueError(f"Weighted mesh {name!r} has invalid influence count")
        total = int(count)
        position += 1
        end = position + total * 4
        if end > len(vertices):
            raise ValueError(f"Weighted mesh {name!r} has truncated influence data")
        weight_sum = 0.0
        for influence in range(total):
            offset = position + influence * 4
            bone_index, weight = vertices[offset], vertices[offset + 3]
            if not bone_index.is_integer() or not 0 <= bone_index < bone_count:
                raise ValueError(f"Weighted mesh {name!r} references an invalid bone index")
            if not 0 <= weight <= 1:
                raise ValueError(f"Weighted mesh {name!r} has an invalid influence weight")
            weight_sum += weight
        if abs(weight_sum - 1.0) > 1e-5:
            raise ValueError(f"Weighted mesh {name!r} influence weights do not sum to one")
        position = end


__all__ = (
    "AttachmentDefinition",
    "AtlasRegionGeometry",
    "BoneDefinition",
    "BoneTransform",
    "ConstraintDefinition",
    "SemanticSkeleton",
    "SlotDefinition",
    "TimelineDefinition",
    "decode_atlas_geometry",
    "decode_semantic_skeleton",
)
