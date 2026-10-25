"""Best-effort format discovery. Parsing/validation is not runtime certification."""

from __future__ import annotations

import re

from .json_types import decode_json_object, require_json_object

SPINE_VERSION = re.compile(r"^\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?$")
TEXTURE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".ktx", ".ktx2", ".pvr", ".tga"}


def skeleton_version(payload: bytes) -> tuple[bool, str | None, str | None]:
    """Return (is_skeleton, version, error), never assume that JSON is a skeleton."""
    try:
        obj = decode_json_object(payload, "skeleton")
    except (UnicodeError, ValueError) as exc:
        return False, None, f"Invalid JSON: {exc}"
    if (
        not isinstance(obj, dict)
        or not isinstance(obj.get("skeleton"), dict)
        or not isinstance(obj.get("bones"), list)
    ):
        return False, None, None
    metadata = require_json_object(obj["skeleton"], "skeleton metadata")
    raw = metadata.get("spine", metadata.get("version"))
    if raw is None:
        return True, None, "Skeleton contains no Spine export version"
    version = str(raw).strip()
    if not SPINE_VERSION.fullmatch(version):
        return True, None, f"Unrecognized Spine version: {version!r}"
    return True, version, None


def atlas_page_names(payload: bytes) -> list[str]:
    """Find common Spine atlas page declarations (not a full atlas grammar parser)."""
    raw = payload.decode("utf-8-sig")
    pages = []
    for line in raw.splitlines():
        candidate = line.strip()
        if not candidate or candidate.startswith("#") or ":" in candidate or line[:1].isspace():
            continue
        if any(candidate.lower().endswith(ext) for ext in TEXTURE_EXTENSIONS):
            if candidate not in pages:
                pages.append(candidate)
    return pages
