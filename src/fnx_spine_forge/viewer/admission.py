"""Renderer capability/resource admission, not asset discovery or conversion."""

from ..json_types import JSONDocument, JSONValue, is_document
from ..parsers import NON_IMAGE_ATTACHMENT_TYPES


def admit_render_document(document: JSONDocument, family: str) -> None:
    pending: list[JSONValue] = [document]
    visited = 0
    while pending:
        value = pending.pop()
        visited += 1
        if visited > 1000000:
            raise ValueError("VIEWER_RESOURCE_LIMIT_EXCEEDED: JSON allocation budget")
        if is_document(value):
            pending.extend(value.values())
        elif isinstance(value, (list, tuple)):
            if len(value) > 1000000:
                raise ValueError("VIEWER_RESOURCE_LIMIT_EXCEEDED: array allocation budget")
            pending.extend(value)
    for key, limit in (("bones", 10000), ("slots", 10000), ("animations", 2000)):
        records = document.get(key)
        if isinstance(records, (list, dict)) and len(records) > limit:
            raise ValueError(f"VIEWER_RESOURCE_LIMIT_EXCEEDED: {key}")
    if document.get("physics") and family not in ("4.2", "4.3"):
        raise ValueError("UNSUPPORTED_RENDER_FEATURE: physics requires a compatible runtime")
    skins = document.get("skins", [])
    records = (
        list(skins.values()) if is_document(skins) else skins if isinstance(skins, list) else []
    )
    for skin in records:
        if not is_document(skin):
            raise ValueError("UNSUPPORTED_RENDER_FEATURE: malformed skin")
        slots = skin.get("attachments", skin)
        if not is_document(slots):
            raise ValueError("UNSUPPORTED_RENDER_FEATURE: malformed attachments")
        for attachments in slots.values():
            if not is_document(attachments):
                raise ValueError("UNSUPPORTED_RENDER_FEATURE: malformed slot attachments")
            for attachment in attachments.values():
                if not is_document(attachment):
                    raise ValueError("UNSUPPORTED_RENDER_FEATURE: malformed attachment")
                kind = attachment.get("type", "region")
                if not isinstance(kind, str) or kind not in (
                    {"region", "mesh", "linkedmesh"} | NON_IMAGE_ATTACHMENT_TYPES
                ):
                    raise ValueError(f"UNSUPPORTED_RENDER_FEATURE: attachment type {kind}")
