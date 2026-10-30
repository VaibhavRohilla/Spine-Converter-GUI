"""Direct Spine 3.6 to 3.7 JSON migration, based on official versioned readers."""

from __future__ import annotations

from copy import deepcopy

from ..json_types import JSONDocument, is_document
from .document import require_object, require_records
from .errors import MigrationError
from .registry import MigrationKind, require_route

_TOP_LEVEL = {
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


def migrate_36_to_37(
    source: JSONDocument, source_version: str, target_version: str
) -> tuple[JSONDocument, dict[str, int | float]]:
    """Write 3.7's IK flags explicitly while retaining legacy skin/timeline schemas."""
    require_route(MigrationKind.SPINE_36_TO_37, source_version, target_version)
    if set(source) - _TOP_LEVEL:
        raise MigrationError("Unsupported Spine 3.6 top-level field")
    skeleton = source.get("skeleton")
    if not is_document(skeleton) or skeleton.get("spine") != source_version:
        raise MigrationError("Source version does not match Spine 3.6.53 metadata")
    for field in ("bones", "slots"):
        if not isinstance(source.get(field), list):
            raise MigrationError(f"Spine 3.6 skeleton requires {field} array")
    skins = source.get("skins")
    if not is_document(skins) or any(
        not isinstance(name, str) or not is_document(entries) for name, entries in skins.items()
    ):
        raise MigrationError("Spine 3.6 skins must use the legacy object-map representation")

    target = deepcopy(source)
    constraints = require_records(target.get("ik", []), "migrate_36_to_37 JSON field")
    if not isinstance(constraints, list):
        raise MigrationError("Spine 3.6 IK constraints must be an array")
    for constraint in constraints:
        if not is_document(constraint):
            raise MigrationError("Spine 3.6 IK constraints must be objects")
        if {"compress", "stretch", "uniform"} & constraint.keys():
            raise MigrationError("Spine 3.6 source cannot declare Spine 3.7 IK options")
        # These fields were introduced in the 3.7 reader and default to false there.
        constraint.update(compress=False, stretch=False, uniform=False)

    animations = require_object(target.get("animations", {}), "migrate_36_to_37 JSON field")
    if not is_document(animations):
        raise MigrationError("Spine 3.6 animations must be an object")
    for animation_name, animation in animations.items():
        if not is_document(animation):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        allowed_groups = {
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
        if set(animation) - allowed_groups:
            raise MigrationError(
                f"Animation {animation_name!r} contains an unsupported timeline group"
            )
        ik_timelines = require_object(animation.get("ik", {}), "migrate_36_to_37 JSON field")
        if not is_document(ik_timelines):
            raise MigrationError(f"Animation {animation_name!r} IK timelines must be an object")
        for name, frames in ik_timelines.items():
            if not isinstance(frames, list):
                raise MigrationError(
                    f"Animation {animation_name!r} IK timeline {name!r} must be an array"
                )
            for frame in frames:
                if not is_document(frame):
                    raise MigrationError("IK timeline keyframes must be objects")
                if {"compress", "stretch"} & frame.keys():
                    raise MigrationError(
                        "Spine 3.6 source cannot declare Spine 3.7 IK animation options"
                    )
                frame.update(compress=False, stretch=False)

    require_object(target["skeleton"], "migrate_36_to_37 JSON field")["spine"] = target_version
    return target, {"bezier_segments": 0, "max_curve_error": 0.0, "attachments": 0}


__all__ = ["migrate_36_to_37"]
