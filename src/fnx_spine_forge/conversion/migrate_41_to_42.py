"""Direct Spine 4.1 to 4.2 schema migration based on official readers."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument, is_document
from .curves import _curve_statistics
from .document import require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route
from .schema import (
    _migrate_constraint_definitions,
    _validate_constraints,
    _validate_target,
    _validate_top_level,
    _walk_attachments,
)


def migrate_41_to_42(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Transform exact 4.1.56 JSON directly into the 4.2.43 schema."""
    require_route(MigrationKind.SPINE_41_TO_42, source_version, target_version)
    target = deepcopy(source)
    skeleton = target.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 4.1.56 metadata")
    _validate_top_level(target)
    for bone in require_records(target.get("bones", []), "migrate_41_to_42 JSON field"):
        if is_document(bone) and ("inherit" in bone or "skin" in bone):
            raise MigrationError("Spine 4.1 bone schema cannot contain 4.2 inherit or skin fields")
    for animation_name, animation in require_object(
        target.get("animations", {}), "migrate_41_to_42 JSON field"
    ).items():
        if not is_document(animation):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        for bone_name, timelines in require_object(
            animation.get("bones", {}), "migrate_41_to_42 JSON field"
        ).items():
            if is_document(timelines) and "inherit" in timelines:
                raise MigrationError(
                    f"Spine 4.1 cannot contain an inherit timeline on bone {bone_name!r}"
                )
    _walk_attachments(target, target_version)
    _validate_constraints(target)
    _migrate_constraint_definitions(target)
    segments, curve_frames = _curve_statistics(target)
    require_object(target["skeleton"], "migrate_41_to_42 JSON field")["spine"] = target_version
    _validate_target(target, target_version)
    return target, {
        "bezier_segments": segments,
        "bezier_frames": curve_frames,
        "max_curve_error": 0.0,
    }


__all__ = ["migrate_41_to_42"]
