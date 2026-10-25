"""Conservative direct Spine 4.3 to 4.2 downgrade for representable data."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from ..json_types import JSONDocument, JSONValue, is_document
from .curves import _curve_statistics
from .document import require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route
from .schema import (
    _validate_constraints,
    _validate_deform_group,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)


def _reject_43_only_features(document: JSONDocument) -> None:
    for bone in require_records(document.get("bones", []), "migrate_43_to_42 JSON field"):
        if isinstance(bone, Mapping) and {"icon", "iconSize", "iconRotation"} & bone.keys():
            raise MigrationError("Spine 4.2 cannot represent Spine 4.3 bone icon fields")
    for slot in require_records(document.get("slots", []), "migrate_43_to_42 JSON field"):
        if isinstance(slot, Mapping) and "visible" in slot:
            raise MigrationError("Spine 4.2 cannot represent Spine 4.3 slot visibility")
    for skin in require_records(document.get("skins", []), "migrate_43_to_42 JSON field"):
        if isinstance(skin, Mapping) and any(skin.get(key) for key in ("physics", "slider")):
            raise MigrationError("Spine 4.2 cannot represent Spine 4.3 skin constraint references")
        attachments = (
            require_object(skin.get("attachments", {}), "migrate_43_to_42 JSON field")
            if isinstance(skin, Mapping)
            else {}
        )
        stack: list[JSONValue] = [attachments]
        while stack:
            value = stack.pop()
            if isinstance(value, Mapping):
                if "sequence" in value:
                    raise MigrationError(
                        "Spine 4.2 cannot represent Spine 4.3 attachment sequences"
                    )
                stack.extend(value.values())
            elif isinstance(value, list):
                stack.extend(value)
    for animation_name, animation in require_object(
        document.get("animations", {}), "migrate_43_to_42 JSON field"
    ).items():
        if not isinstance(animation, Mapping):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        if any(animation.get(key) for key in ("physics", "slider", "drawOrderFolder")):
            raise MigrationError(
                f"Spine 4.2 cannot represent 4.3-only animation timelines in {animation_name!r}"
            )


def _constraints_to_42(document: JSONDocument) -> None:
    constraints = require_records(document.get("constraints", []), "migrate_43_to_42 JSON field")
    if not isinstance(constraints, list):
        raise MigrationError("Spine 4.3 constraints must be an array")
    ik: list[JSONDocument] = []
    path: list[JSONDocument] = []
    for order, value in enumerate(constraints):
        if not is_document(value):
            raise MigrationError("Spine 4.3 constraint entries must be objects")
        category = value.get("type")
        if category not in {"ik", "path"}:
            raise MigrationError(
                f"Spine 4.2 downgrade does not support Spine 4.3 constraint type {category!r}"
            )
        item = deepcopy(value)
        item.pop("type")
        item["order"] = order
        if category == "ik":
            scale_y = item.pop("scaleY", None)
            if scale_y not in {None, "None", "Uniform"}:
                raise MigrationError(
                    f"Spine 4.2 cannot represent Spine 4.3 IK scaleY mode {scale_y!r}"
                )
            item["uniform"] = scale_y == "Uniform"
            ik.append(item)
        else:
            if "mixRotate" in item:
                if "rotateMix" in item:
                    raise MigrationError("Path constraint has both mixRotate and rotateMix")
                item["rotateMix"] = item.pop("mixRotate")
            if "mixX" in item:
                if "translateMix" in item:
                    raise MigrationError("Path constraint has both mixX and translateMix")
                item["translateMix"] = item.pop("mixX")
            mix_x = item.pop("mixY", None)
            if mix_x is not None and mix_x != item.get("translateMix", 1):
                raise MigrationError("Spine 4.2 path constraints cannot represent separate mixY")
            path.append(item)
    document["ik"] = [item for item in ik]
    document["path"] = [item for item in path]
    document.pop("constraints", None)


def migrate_43_to_42(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Downgrade exact 4.3.13 data when every construct has a 4.2 representation."""
    require_route(MigrationKind.SPINE_43_TO_42, source_version, target_version)
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.3.13 metadata")
    for field in ("bones", "slots", "skins"):
        if not isinstance(target.get(field), list):
            raise MigrationError(f"Spine 4.3 skeleton requires {field} array")
    _reject_43_only_features(target)
    _constraints_to_42(target)
    for skin in require_records(target["skins"], "migrate_43_to_42 JSON field"):
        attachments = require_object(skin.get("attachments", {}), "migrate_43_to_42 JSON field")
        if not is_document(attachments):
            raise MigrationError("Skin attachments must be an object")
        for slot in attachments.values():
            if not is_document(slot):
                continue
            for attachment in slot.values():
                if is_document(attachment) and "source" in attachment:
                    if "parent" in attachment:
                        raise MigrationError("Linked mesh has both source and parent fields")
                    attachment["parent"] = attachment.pop("source")

    require_object(target["skeleton"], "migrate_43_to_42 JSON field")["spine"] = target_version
    _validate_top_level(target)
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    for animation_name, animation in require_object(
        target.get("animations", {}), "migrate_43_to_42 JSON field"
    ).items():
        if is_document(animation) and "deform" in animation:
            _validate_deform_group(target, animation["deform"], animation_name)
    _validate_target(target, target_version)
    bezier_segments, bezier_frames = _curve_statistics(target)
    return target, {
        "bezier_segments": bezier_segments,
        "bezier_frames": bezier_frames,
        "max_curve_error": 0.0,
        "attachments": 0,
    }


__all__ = ["migrate_43_to_42"]
