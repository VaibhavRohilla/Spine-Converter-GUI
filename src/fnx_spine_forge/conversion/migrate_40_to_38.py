"""Conservative Spine 4.0.31 to 3.8.99 downgrade."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .migrate_38_to_4x import MigrationError


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
    for skin in skins:
        if not isinstance(skin, dict) or not isinstance(skin.get("name"), str):
            raise MigrationError("Skin name is required")
        name = skin["name"]
        if name in skin_names:
            raise MigrationError(f"Duplicate skin name {name!r}")
        skin_names.add(name)
        if any(skin.get(key) for key in ("bones", "ik", "transform", "path")):
            raise MigrationError("Spine 3.8 cannot represent skin-specific bones or constraints")
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
                    raise MigrationError("Spine 3.8 cannot represent attachment sequences")
                if attachment.get("type") == "linkedmesh":
                    if "timelines" in attachment and "deform" in attachment:
                        raise MigrationError("Linked mesh contains conflicting deform flags")
                    attachment["deform"] = attachment.pop("timelines", True)

    for animation_name, animation in target.get("animations", {}).items():
        if not isinstance(animation, dict):
            raise MigrationError(f"Animation {animation_name!r} must be an object")
        stack: list[Any] = [animation]
        while stack:
            value = stack.pop()
            if isinstance(value, dict):
                curve = value.get("curve")
                if isinstance(curve, list):
                    raise MigrationError(
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
        if "attachments" in animation:
            if "deform" in animation:
                raise MigrationError("Animation contains conflicting deform and attachments groups")
            attachment_group = animation.pop("attachments")
            if not isinstance(attachment_group, dict):
                raise MigrationError("Attachment timelines must be an object")
            deform: dict[str, Any] = {}
            for skin_name, skin in attachment_group.items():
                if not isinstance(skin, dict):
                    raise MigrationError("Attachment timeline skin must be an object")
                out_skin: dict[str, Any] = {}
                for slot_name, slots in skin.items():
                    if not isinstance(slots, dict):
                        raise MigrationError("Attachment timeline slot must be an object")
                    out_slot: dict[str, Any] = {}
                    for attachment_name, groups in slots.items():
                        if not isinstance(groups, dict) or set(groups) - {"deform"}:
                            raise MigrationError(
                                "Spine 3.8 cannot represent non-deform attachment timelines"
                            )
                        if "deform" in groups:
                            out_slot[attachment_name] = groups["deform"]
                    if out_slot:
                        out_skin[slot_name] = out_slot
                if out_skin:
                    deform[skin_name] = out_skin
            if deform:
                animation["deform"] = deform
    # 3.8 uses the named skin record array, as does 4.0; keep setup attachment
    # semantics intact and only validate that the target-required fields exist.
    skeleton["spine"] = target_version
    return target, {"bezier_segments": 0, "max_curve_error": 0.0}


__all__ = ["migrate_40_to_38"]
