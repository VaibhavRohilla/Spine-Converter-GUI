"""Shared validated Spine schema operations used by exact route writers."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument, JSONValue, is_document
from .document import require_array, require_number, require_object, require_records, require_text
from .errors import MigrationError
from .registry import bone_mode_field


def _weighted_vertex_influences(vertices: list[JSONValue], bone_count: int, context: str) -> int:
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
    item: JSONDocument, kind: str, context: str, bone_count: int
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


def _rename_exclusive(obj: JSONDocument, old: str, new: str, context: str) -> None:
    if old in obj and new in obj:
        raise MigrationError(
            f"{context}: both legacy {old!r} and target {new!r} fields are present"
        )
    if old in obj:
        obj[new] = obj.pop(old)


def _validate_top_level(document: JSONDocument) -> None:
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
    if not is_document(
        require_object(document.get("animations", {}), "migrate_38_to_4x JSON field")
    ):
        raise MigrationError("animations must be an object keyed by animation name")


def _walk_attachments(document: JSONDocument, target_version: str) -> None:
    slot_names = {
        slot.get("name")
        for slot in require_records(document["slots"], "migrate_38_to_4x JSON field")
        if is_document(slot)
    }
    bone_names = {
        bone.get("name")
        for bone in require_records(document["bones"], "migrate_38_to_4x JSON field")
        if is_document(bone)
    }
    skin_names: set[str] = set()
    linked_meshes: list[tuple[str, str, str, JSONDocument]] = []
    bone_count = len(bone_names)
    for skin in require_records(document["skins"], "migrate_38_to_4x JSON field"):
        require_object(skin, "skin")
        skin_name = skin.get("name")
        if not isinstance(skin_name, str):
            raise MigrationError("skin name is required")
        skin_names.add(skin_name)
        attachments = require_object(
            require_object(skin.get("attachments", {}), "migrate_38_to_4x JSON field"),
            f"skin {skin_name}.attachments",
        )
        for slot_name, values in attachments.items():
            if slot_name not in slot_names:
                raise MigrationError(
                    f"skin {skin_name}: attachment references missing slot {slot_name!r}"
                )
            for attachment_name, attachment in require_object(
                values, f"skin {skin_name}.{slot_name}"
            ).items():
                item = require_object(attachment, f"attachment {attachment_name}")
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
                            require_number(
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
                    _rename_exclusive(item, "deform", "timelines", f"linked mesh {attachment_name}")
    skins_by_name = {
        skin["name"]: skin
        for skin in require_records(document["skins"], "migrate_38_to_4x JSON field")
    }
    for owner_skin, slot_name, attachment_name, item in linked_meshes:
        parent_skin = item.get("skin", owner_skin)
        if not isinstance(parent_skin, str) or parent_skin not in skins_by_name:
            raise MigrationError(
                f"linked mesh {attachment_name!r} references missing skin {parent_skin!r}"
            )
        parent_name = require_text(item["parent"], "linked mesh parent")
        parent_attachments = require_object(
            skins_by_name[parent_skin].get("attachments", {}), "migrate_38_to_4x JSON field"
        )
        if slot_name not in parent_attachments or parent_name not in require_object(
            parent_attachments[slot_name], "parent slot attachments"
        ):
            raise MigrationError(
                f"linked mesh {attachment_name!r} has missing parent {parent_name!r}"
            )
        if target_version == "4.3.13":
            item.pop("parent")
            item["source"] = parent_name
    # Validate bone parents and slot bone references.
    for bone in require_records(document["bones"], "migrate_38_to_4x JSON field"):
        require_object(bone, "bone")
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
    for slot in require_records(document["slots"], "migrate_38_to_4x JSON field"):
        require_object(slot, "slot")
        if slot.get("bone") not in bone_names:
            raise MigrationError(
                f"slot {slot.get('name')!r} references missing bone {slot.get('bone')!r}"
            )


def _validate_constraints(document: JSONDocument) -> None:
    bones = {
        bone["name"] for bone in require_records(document["bones"], "migrate_38_to_4x JSON field")
    }
    slots = {
        slot["name"] for slot in require_records(document["slots"], "migrate_38_to_4x JSON field")
    }
    constraints: dict[str, set[str]] = {"ik": set(), "transform": set(), "path": set()}
    for category in constraints:
        values = require_records(document.get(category, []), "migrate_38_to_4x JSON field")
        if not isinstance(values, list):
            raise MigrationError(f"{category} constraints must be an array")
        for constraint in values:
            item = require_object(constraint, f"{category} constraint")
            name = item.get("name")
            if not isinstance(name, str):
                raise MigrationError(f"{category} constraint name is required")
            constraints[category].add(name)
            targets = require_array(
                item.get("bones", [item.get("bone")] if item.get("bone") else []),
                "constraint bones",
            )
            if any(target not in bones for target in targets):
                raise MigrationError(f"{category} constraint {name!r} references a missing bone")
            target = item.get("target")
            if target is not None and target not in (slots if category == "path" else bones):
                raise MigrationError(
                    f"{category} constraint {name!r} references missing target {target!r}"
                )
    for skin in require_records(document["skins"], "migrate_38_to_4x JSON field"):
        for category in constraints:
            names = require_array(skin.get(category, []), "migrate_38_to_4x JSON field")
            if any(name not in constraints[category] for name in names):
                raise MigrationError(
                    f"skin {skin['name']!r} references an unknown {category} constraint"
                )


def _migrate_constraint_definitions(document: JSONDocument) -> None:
    for constraint in require_records(document.get("transform", []), "migrate_38_to_4x JSON field"):
        _rename_exclusive(constraint, "rotateMix", "mixRotate", "transform constraint")
        _rename_exclusive(constraint, "translateMix", "mixX", "transform constraint")
        _rename_exclusive(constraint, "scaleMix", "mixScaleX", "transform constraint")
        _rename_exclusive(constraint, "shearMix", "mixShearY", "transform constraint")
        if "mixX" in constraint:
            constraint.setdefault("mixY", constraint["mixX"])
        if "mixScaleX" in constraint:
            constraint.setdefault("mixScaleY", constraint["mixScaleX"])
    for constraint in require_records(document.get("path", []), "migrate_38_to_4x JSON field"):
        _rename_exclusive(constraint, "rotateMix", "mixRotate", "path constraint")
        _rename_exclusive(constraint, "translateMix", "mixX", "path constraint")
        if "mixX" in constraint:
            constraint.setdefault("mixY", constraint["mixX"])


def _migrate_constraints_to_43(document: JSONDocument) -> None:
    """Combine supported IK and path constraints into Spine 4.3's ordered list."""
    if document.get("transform"):
        raise MigrationError(
            "Spine 4.3 transform constraints use property mappings; this route does not "
            "currently represent them faithfully"
        )
    for skin in require_records(document["skins"], "migrate_38_to_4x JSON field"):
        if skin.get("transform"):
            raise MigrationError("Spine 4.3 transform constraints in skins are unsupported")
    for animation_name, animation_value in require_object(
        document.get("animations", {}), "migrate_38_to_4x JSON field"
    ).items():
        animation = require_object(animation_value, f"animation {animation_name}")
        if require_object(animation, "semantic object").get("transform"):
            raise MigrationError(
                f"Spine 4.3 transform constraint timelines are unsupported in {animation_name!r}"
            )

    ordered: list[tuple[int, int, JSONDocument]] = []
    stable_index = 0
    for constraint_type in ("ik", "path"):
        values = require_records(document.get(constraint_type, []), "migrate_38_to_4x JSON field")
        if not isinstance(values, list):
            raise MigrationError(f"{constraint_type} constraints must be an array")
        for value in values:
            constraint = require_object(value, f"{constraint_type} constraint")
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

    def constraint_order(entry: tuple[int, int, JSONDocument]) -> tuple[int, int]:
        return entry[0], entry[1]

    ordered.sort(key=constraint_order)
    document["constraints"] = [entry[2] for entry in ordered]


def _validate_target(document: JSONDocument, target_version: str) -> None:
    if (
        require_object(document.get("skeleton", {}), "migrate_38_to_4x JSON field").get("spine")
        != target_version
    ):
        raise MigrationError("Target skeleton version metadata is invalid")
    valid_modes = {
        "Normal",
        "OnlyTranslation",
        "NoRotationOrReflection",
        "NoScale",
        "NoScaleOrReflection",
    }
    mode_key = bone_mode_field(target_version)
    other_key = "transform" if mode_key == "inherit" else "inherit"
    for bone in require_records(document["bones"], "migrate_38_to_4x JSON field"):
        if other_key in bone or bone.get(mode_key, "Normal") not in valid_modes:
            raise MigrationError(
                f"Invalid Spine {target_version} bone transform schema for {bone.get('name')!r}"
            )
    for skin in require_records(document["skins"], "migrate_38_to_4x JSON field"):
        for slot_name, values in require_object(
            skin.get("attachments", {}), "migrate_38_to_4x JSON field"
        ).items():
            for attachment_name, attachment_value in require_object(
                values, "semantic object"
            ).items():
                attachment = require_object(attachment_value, "attachment")
                if require_object(attachment, "semantic object").get("type") == "linkedmesh":
                    if target_version == "4.0.31":
                        invalid_link = "timelines" in attachment or not isinstance(
                            require_object(attachment, "semantic object").get("deform", True), bool
                        )
                    elif target_version == "4.3.13":
                        invalid_link = (
                            "parent" in attachment
                            or not isinstance(
                                require_object(attachment, "semantic object").get("source"), str
                            )
                            or "deform" in attachment
                            or not isinstance(
                                require_object(attachment, "semantic object").get(
                                    "timelines", True
                                ),
                                bool,
                            )
                        )
                    else:
                        invalid_link = "deform" in attachment or not isinstance(
                            require_object(attachment, "semantic object").get("timelines", True),
                            bool,
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
            require_object(item, "semantic object").get("type") not in {"ik", "path"}
            for item in constraints
        ):
            raise MigrationError("Invalid Spine 4.3 combined constraint list")
    for animation_name, animation_value in require_object(
        document.get("animations", {}), "migrate_38_to_4x JSON field"
    ).items():
        animation = require_object(animation_value, f"animation {animation_name}")
        if "draworder" in animation or (target_version != "4.0.31" and "deform" in animation):
            raise MigrationError(f"Legacy animation group remained in {animation_name!r}")
        for slot_name, timeline_set in require_object(
            require_object(animation, "semantic object").get("slots", {}),
            "migrate_38_to_4x JSON field",
        ).items():
            if "color" in require_object(
                timeline_set, "slot timelines"
            ) or "twoColor" in require_object(timeline_set, "slot timelines"):
                raise MigrationError(
                    f"Legacy color timeline remained in {animation_name}/{slot_name}"
                )
        for bone_name, timeline_set in require_object(
            require_object(animation, "semantic object").get("bones", {}),
            "migrate_38_to_4x JSON field",
        ).items():
            for timeline_name, frame_values in require_object(
                timeline_set, "semantic object"
            ).items():
                frames = require_records(frame_values, "bone timeline")
                if timeline_name == "rotate" and any("angle" in frame for frame in frames):
                    raise MigrationError(
                        f"Legacy rotation value remained in {animation_name}/{bone_name}"
                    )
                for frame in frames:
                    curve = require_object(frame, "semantic object").get("curve")
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


def _deform_length(attachment: JSONDocument, context: str) -> int:
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


def _validate_deform_group(document: JSONDocument, group: JSONValue, animation: str) -> None:
    skin_by_name = {
        skin["name"]: skin
        for skin in require_records(document["skins"], "migrate_38_to_4x JSON field")
    }
    slot_names = {
        slot["name"] for slot in require_records(document["slots"], "migrate_38_to_4x JSON field")
    }
    deform_group = require_object(group, f"animation {animation}.deform")
    for skin_name, skin_timelines in deform_group.items():
        if skin_name not in skin_by_name:
            raise MigrationError(f"deform timeline references missing skin {skin_name!r}")
        slots = require_object(skin_timelines, f"deform skin {skin_name}")
        for slot_name, attachments_value in slots.items():
            if slot_name not in slot_names:
                raise MigrationError(f"deform timeline references missing slot {slot_name!r}")
            attachments = require_object(attachments_value, f"deform slot {slot_name}")
            definitions = require_object(
                require_object(skin_by_name[skin_name]["attachments"], "semantic object").get(
                    slot_name, {}
                ),
                "migrate_38_to_4x JSON field",
            )
            for attachment_name, frame_values in attachments.items():
                definition = definitions.get(attachment_name)
                if not is_document(definition):
                    raise MigrationError(
                        f"deform timeline references missing attachment {attachment_name!r}"
                    )
                resolved = definition
                resolved_skin = skin_name
                visited: set[tuple[str, str]] = set()
                while resolved.get("type") == "linkedmesh":
                    parent_name = require_text(resolved.get("parent"), "linked parent")
                    parent_skin = resolved.get("skin", resolved_skin)
                    identity = (str(parent_skin), str(parent_name))
                    if identity in visited:
                        raise MigrationError(
                            f"linked mesh parent cycle while resolving {attachment_name!r}"
                        )
                    visited.add(identity)
                    parent_definition = require_object(
                        require_object(
                            require_object(
                                skin_by_name.get(str(parent_skin), {}),
                                "migrate_38_to_4x JSON field",
                            ).get("attachments", {}),
                            "migrate_38_to_4x JSON field",
                        ).get(slot_name, {}),
                        "migrate_38_to_4x JSON field",
                    ).get(parent_name)
                    if not is_document(parent_definition):
                        raise MigrationError(
                            f"deform linked mesh parent is missing: {parent_name!r}"
                        )
                    resolved = parent_definition
                    resolved_skin = str(parent_skin)
                length = _deform_length(resolved, f"{skin_name}/{slot_name}/{attachment_name}")
                frames = require_records(frame_values, f"deform timeline {attachment_name}")
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
