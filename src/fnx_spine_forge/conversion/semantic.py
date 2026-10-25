"""Validated typed views over high-risk Spine JSON semantics.

Raw mappings remain at the JSON boundary for migration writers. This module
provides strict, version-aware indexes so callers can inspect constructs
without treating arbitrary dictionaries as validated semantics.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from .registry import ROUTES_BY_PATCH, SUPPORTED_PATCH_VERSIONS, MigrationKind

AttachmentKind = Literal["region", "mesh", "linkedmesh", "boundingbox", "path", "clipping", "point"]


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
    kind: AttachmentKind
    path: str | None
    parent: str | None
    parent_skin: str | None
    deform_inheritance: bool | None
    x: float
    y: float
    rotation: float
    width: float
    height: float
    uvs: tuple[float, ...]
    triangles: tuple[int, ...]
    vertices: tuple[float, ...]
    bone_influences: tuple[tuple[tuple[int, float, float, float], ...], ...]
    hull: int | None
    vertex_count: int | None
    lengths: tuple[float, ...]
    clipping_end_slot: str | None
    weighted: bool


@dataclass(frozen=True, slots=True)
class ConstraintDefinition:
    kind: ConstraintKind
    name: str
    target: str | None
    bones: tuple[str, ...]
    order: int | None
    setup: tuple[tuple[str, str | int | float | bool | None], ...]


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


class AtlasPageView(Protocol):
    @property
    def name(self) -> str: ...


class AtlasRegionView(Protocol):
    @property
    def name(self) -> str: ...

    @property
    def attributes(self) -> Sequence[tuple[str, str]]: ...


class AtlasView(Protocol):
    @property
    def pages(self) -> Sequence[AtlasPageView]: ...

    @property
    def regions(self) -> Sequence[AtlasRegionView]: ...

    @property
    def region_pages(self) -> Sequence[int]: ...


def decode_atlas_geometry(atlas: AtlasView, version: str) -> tuple[AtlasRegionGeometry, ...]:
    """Decode region geometry using the exact atlas vocabulary for a Spine patch."""
    if version not in SUPPORTED_PATCH_VERSIONS:
        raise ValueError(f"No atlas geometry schema is defined for {version!r}")
    decoded: list[AtlasRegionGeometry] = []
    for region, page_index in zip(atlas.regions, atlas.region_pages, strict=True):
        attrs = dict(region.attributes)
        if not 0 <= page_index < len(atlas.pages):
            raise ValueError(f"Atlas region {region.name!r} has invalid page index")
        page = atlas.pages[page_index].name
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
        if not page:
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
    "skin",
    "deform",
    "timelines",
    "sequence",
    "inheritDeform",
    "fps",
    "mode",
}
_ATTACHMENT_KEYS.update({"source", "color2", "sequence", "vertices", "bones"})

_CONSTRAINT_COMMON_FIELDS = {
    "name",
    "order",
    "bones",
    "target",
    "skin",
    "skinRequired",
    "icon",
    "color",
}
_CONSTRAINT_FIELDS: dict[str, set[str]] = {
    "ik": {
        "mix",
        "softness",
        "bendPositive",
        "bendDirection",
        "compress",
        "stretch",
        "uniform",
        "scaleX",
        "scaleY",
        "mixRotate",
    },
    "path": {
        "slot",
        "positionMode",
        "spacingMode",
        "rotateMode",
        "rotation",
        "offsetRotation",
        "position",
        "spacing",
        "rotateMix",
        "translateMix",
        "mixRotate",
        "mixX",
        "mixY",
    },
    "transform": {
        "rotation",
        "scaleX",
        "scaleY",
        "shearY",
        "x",
        "y",
        "rotateMix",
        "translateMix",
        "scaleMix",
        "shearMix",
        "mixRotate",
        "mixX",
        "mixY",
        "mixScaleX",
        "mixScaleY",
        "mixShearY",
    },
    "physics": {
        "bone",
        "x",
        "y",
        "rotate",
        "scale",
        "shear",
        "limit",
        "step",
        "inertia",
        "strength",
        "damping",
        "mass",
        "wind",
        "gravity",
        "mix",
    },
}
_CONSTRAINT_TYPES = frozenset(_CONSTRAINT_FIELDS)
ConstraintKind = Literal["ik", "path", "transform", "physics"]


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


def decode_semantic_skeleton(
    document: Mapping[str, object], version: str, *, migration_target: str | None = None
) -> SemanticSkeleton:
    """Decode supported high-risk records for one exact recognized patch version."""
    if version not in SUPPORTED_PATCH_VERSIONS:
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
    linked_parents: list[tuple[str, str, str, str, str]] = []
    attachment_names_by_skin_slot: dict[tuple[str, str], set[str]] = {}
    skin_records: list[tuple[str, Mapping[str, object], Mapping[str, object]]] = []
    if isinstance(raw_skins, list):
        for skin_index, raw_skin in enumerate(raw_skins):
            skin = _mapping(raw_skin, f"skins[{skin_index}]")
            skin_name = skin.get("name")
            if not isinstance(skin_name, str) or not skin_name:
                raise ValueError(f"skins[{skin_index}].name must be a non-empty string")
            skin_records.append(
                (
                    skin_name,
                    skin,
                    _mapping(skin.get("attachments", {}), f"skins[{skin_index}].attachments"),
                )
            )
    elif isinstance(raw_skins, Mapping) and version.startswith("3."):
        for skin_name, raw_skin in raw_skins.items():
            if not isinstance(skin_name, str) or not skin_name:
                raise ValueError("Legacy skin names must be non-empty strings")
            skin_records.append((skin_name, {}, _mapping(raw_skin, f"skin {skin_name}")))
    elif isinstance(raw_skins, Mapping) and not raw_skins:
        skin_records = []
    elif isinstance(raw_skins, Mapping):
        raise ValueError(f"Object-map skins are unsupported for Spine {version}")
    else:
        raise ValueError("skins must be a version-specific array or object")

    slot_names = {slot.name for slot in slots}
    for skin_name, skin, attachment_map in skin_records:
        skins.append(skin_name)
        for slot_name, slot_map_raw in attachment_map.items():
            if slot_name not in slot_names:
                raise ValueError(f"Skin {skin_name!r} references missing slot {slot_name!r}")
            slot_map = _mapping(slot_map_raw, f"skin {skin_name}.{slot_name}")
            attachment_names_by_skin_slot.setdefault((skin_name, slot_name), set()).update(slot_map)
            for attachment_name, attachment_raw in slot_map.items():
                row = _mapping(attachment_raw, f"attachment {attachment_name}")
                allowed_attachment_keys = _ATTACHMENT_KEYS
                if version.startswith("3."):
                    allowed_attachment_keys = _ATTACHMENT_KEYS - {"sequence"}
                unknown = set(row) - allowed_attachment_keys
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
                attachment_kind: AttachmentKind = kind_value
                vertices_raw = row.get("vertices", [])
                if not isinstance(vertices_raw, list):
                    raise ValueError(f"Attachment {attachment_name!r} vertices must be an array")
                vertices = tuple(_number(value, "attachment vertex") for value in vertices_raw)
                parent = row.get("parent", row.get("source"))
                parent_skin = row.get("skin", skin_name)
                deform = row.get("deform", row.get("inheritDeform"))
                path = row.get("path")
                if parent is not None and not isinstance(parent, str):
                    raise ValueError("Linked mesh parent must be a string")
                if not isinstance(parent_skin, str):
                    raise ValueError("Linked mesh skin must be a string")
                if deform is not None and not isinstance(deform, bool):
                    raise ValueError("Linked mesh deform inheritance must be boolean")
                if path is not None and not isinstance(path, str):
                    raise ValueError("Attachment path must be a string")
                if attachment_kind == "linkedmesh":
                    if parent is None:
                        raise ValueError(f"Linked mesh {attachment_name!r} lacks parent")
                    linked_parents.append(
                        (skin_name, parent_skin, slot_name, attachment_name, parent)
                    )
                uvs = row.get("uvs", [])
                uvs_tuple = _number_array(uvs, f"Attachment {attachment_name!r} UVs")
                if len(uvs_tuple) % 2:
                    raise ValueError(f"Attachment {attachment_name!r} UV count must be even")
                triangles_raw = row.get("triangles", [])
                triangles = _integer_array(
                    triangles_raw, f"Attachment {attachment_name!r} triangles"
                )
                if len(triangles) % 3:
                    raise ValueError(f"Attachment {attachment_name!r} triangle count is invalid")
                vertex_count_raw = row.get("vertexCount")
                if vertex_count_raw is not None and (
                    not isinstance(vertex_count_raw, int)
                    or isinstance(vertex_count_raw, bool)
                    or vertex_count_raw < 0
                ):
                    raise ValueError(f"Attachment {attachment_name!r} vertexCount is invalid")
                vertex_count = vertex_count_raw if isinstance(vertex_count_raw, int) else None
                influences: tuple[tuple[tuple[int, float, float, float], ...], ...] = ()
                weighted = False
                geometry_kind = attachment_kind in {"mesh", "boundingbox", "path", "clipping"}
                if geometry_kind and vertices:
                    expected_count = (
                        vertex_count if vertex_count is not None else len(uvs_tuple) // 2
                    )
                    influences = _decode_vertex_stream(
                        vertices, expected_count, len(bone_names), attachment_name
                    )
                    weighted = bool(influences)
                if attachment_kind == "mesh" and len(uvs_tuple) // 2 != (
                    vertex_count or len(uvs_tuple) // 2
                ):
                    raise ValueError(f"Mesh {attachment_name!r} UV and vertex counts differ")
                if attachment_kind == "mesh" and not vertex_count and uvs_tuple and not vertices:
                    raise ValueError(f"Mesh {attachment_name!r} lacks vertex geometry")
                vertex_total = vertex_count or len(uvs_tuple) // 2
                if any(index < 0 or index >= vertex_total for index in triangles):
                    raise ValueError(f"Mesh {attachment_name!r} triangle references invalid vertex")
                lengths = _number_array(
                    row.get("lengths", []), f"Attachment {attachment_name!r} lengths"
                )
                end_slot = row.get("end")
                if end_slot is not None and (
                    not isinstance(end_slot, str) or end_slot not in slot_names
                ):
                    raise ValueError(
                        f"Clipping attachment {attachment_name!r} has invalid end slot"
                    )
                values = {
                    key: _number(row.get(key), f"Attachment {attachment_name!r}.{key}", default)
                    for key, default in (
                        ("x", 0.0),
                        ("y", 0.0),
                        ("rotation", 0.0),
                        ("width", 0.0),
                        ("height", 0.0),
                    )
                }
                hull_raw = row.get("hull")
                if hull_raw is not None and (
                    not isinstance(hull_raw, int) or isinstance(hull_raw, bool) or hull_raw < 0
                ):
                    raise ValueError(f"Attachment {attachment_name!r} hull is invalid")
                attachments.append(
                    AttachmentDefinition(
                        attachment_name,
                        attachment_kind,
                        path,
                        parent,
                        parent_skin if attachment_kind == "linkedmesh" else None,
                        deform if attachment_kind == "linkedmesh" else None,
                        values["x"],
                        values["y"],
                        values["rotation"],
                        values["width"],
                        values["height"],
                        uvs_tuple,
                        triangles,
                        vertices,
                        influences,
                        hull_raw,
                        vertex_count,
                        lengths,
                        end_slot,
                        weighted,
                    )
                )
    for _owner_skin, parent_skin, slot_name, linked_name, parent_name in linked_parents:
        if parent_name not in attachment_names_by_skin_slot.get((parent_skin, slot_name), set()):
            raise ValueError(
                f"Linked mesh {linked_name!r} references missing parent {parent_name!r} "
                f"in slot {slot_name!r}"
            )

    constraints: list[ConstraintDefinition] = []
    constraint_records: list[tuple[ConstraintKind, Mapping[str, object], str]] = []
    for category in ("ik", "path", "transform", "physics"):
        constraint_values: object = document.get(category, [])
        if constraint_values is None:
            continue
        if not isinstance(constraint_values, list):
            raise ValueError(f"{category} constraints must be an array")
        for index, raw in enumerate(constraint_values):
            constraint_records.append(
                (
                    category,
                    _mapping(raw, f"{category}[{index}]"),
                    f"{category}[{index}]",
                )
            )
    if "constraints" in document:
        combined = document["constraints"]
        if version != "4.3.13":
            raise ValueError(f"Combined constraint schema is unsupported for {version}")
        if not isinstance(combined, list):
            raise ValueError("constraints must be an ordered array")
        if constraint_records:
            raise ValueError(
                "4.3 combined constraints cannot coexist with legacy constraint groups"
            )
        for index, raw in enumerate(combined):
            row = _mapping(raw, f"constraints[{index}]")
            kind_value = row.get("type")
            if kind_value not in _CONSTRAINT_TYPES:
                raise ValueError(f"Unsupported constraint discriminator {kind_value!r}")
            constraint_kind = cast(ConstraintKind, kind_value)
            constraint_records.append((constraint_kind, row, f"constraints[{index}]"))

    for kind, row, context in constraint_records:
        allowed = _CONSTRAINT_COMMON_FIELDS | _CONSTRAINT_FIELDS[kind]
        route = ROUTES_BY_PATCH.get((version, migration_target or ""))
        if route is not None and route.kind is MigrationKind.SPINE_43_TO_42 and kind == "physics":
            # Admit known typed fields so the exact downgrade writer can return
            # its route-specific unsupported-feature diagnostic.
            allowed |= set().union(*_CONSTRAINT_FIELDS.values())
        if kind in {"ik", "transform", "physics"} and version.startswith("3."):
            allowed |= {"order"}
        if "type" in row and version == "4.3.13":
            allowed.add("type")
        unknown = set(row) - allowed
        if unknown:
            raise ValueError(
                f"Unknown semantic {kind} constraint fields for {version}: "
                f"{', '.join(sorted(unknown))}"
            )
        name = row.get("name")
        order = row.get("order")
        bone_list = row.get("bones", [row["bone"]] if kind == "physics" and "bone" in row else [])
        if not isinstance(name, str) or not name:
            raise ValueError(f"{context}.name must be non-empty")
        if order is not None and (
            not isinstance(order, int) or isinstance(order, bool) or order < 0
        ):
            raise ValueError(f"{context}.order must be a non-negative integer")
        if not isinstance(bone_list, list) or any(
            not isinstance(item, str) or item not in bone_names for item in bone_list
        ):
            raise ValueError(f"{context}.bones contains an invalid bone reference")
        if kind in {"ik", "transform"} and not bone_list:
            raise ValueError(f"{context}.bones cannot be empty")
        target = row.get("slot", row.get("target")) if kind == "path" else row.get("target")
        if target is not None and not isinstance(target, str):
            raise ValueError(f"{context}.target must be a string")
        valid_targets = {slot.name for slot in slots} if kind == "path" else bone_names
        if target is not None and target not in valid_targets:
            raise ValueError(f"{context} references missing target {target!r}")
        skin_ref = row.get("skin")
        if skin_ref is not None and (not isinstance(skin_ref, str) or skin_ref not in skins):
            raise ValueError(f"{context} references missing skin {skin_ref!r}")
        setup: list[tuple[str, str | int | float | bool | None]] = []
        identity_fields = _CONSTRAINT_COMMON_FIELDS | {"type", "slot"}
        for field_name, value in row.items():
            if field_name in identity_fields:
                continue
            if value is not None and not isinstance(value, (str, int, float, bool)):
                raise ValueError(f"{context}.{field_name} must be a scalar setup value")
            setup.append((field_name, value))
        constraints.append(
            ConstraintDefinition(kind, name, target, tuple(bone_list), order, tuple(setup))
        )

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


def _number_array(value: object, where: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{where} must be an array")
    return tuple(_number(item, where) for item in value)


def _integer_array(value: object, where: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ValueError(f"{where} must be an array")
    result: list[int] = []
    for item in value:
        if not isinstance(item, int) or isinstance(item, bool):
            raise ValueError(f"{where} must contain integers")
        result.append(item)
    return tuple(result)


def _decode_vertex_stream(
    vertices: tuple[float, ...], vertex_count: int, bone_count: int, name: str
) -> tuple[tuple[tuple[int, float, float, float], ...], ...]:
    if len(vertices) == vertex_count * 2:
        return ()
    position = 0
    decoded: list[tuple[tuple[int, float, float, float], ...]] = []
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
        influences: list[tuple[int, float, float, float]] = []
        for influence in range(total):
            offset = position + influence * 4
            bone_index, local_x, local_y, weight = vertices[offset : offset + 4]
            if not bone_index.is_integer() or not 0 <= bone_index < bone_count:
                raise ValueError(f"Weighted mesh {name!r} references an invalid bone index")
            if not 0 <= weight <= 1:
                raise ValueError(f"Weighted mesh {name!r} has an invalid influence weight")
            weight_sum += weight
            influences.append((int(bone_index), local_x, local_y, weight))
        if abs(weight_sum - 1.0) > 1e-5:
            raise ValueError(f"Weighted mesh {name!r} influence weights do not sum to one")
        decoded.append(tuple(influences))
        position = end
    if len(decoded) != vertex_count:
        raise ValueError(f"Weighted mesh {name!r} vertex count does not match geometry")
    return tuple(decoded)


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
