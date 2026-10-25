"""Read-only structural skeleton and Spine atlas parsers."""

from __future__ import annotations

from dataclasses import dataclass

from .detection import SPINE_VERSION
from .json_types import JSONValue, decode_json_object, is_document, require_json_object

IMAGE_ATTACHMENT_TYPES = {"region", "mesh", "linkedmesh", "weightedmesh"}
NON_IMAGE_ATTACHMENT_TYPES = {"boundingbox", "path", "point", "clipping"}


@dataclass(frozen=True)
class SkeletonInfo:
    version: str | None
    counts: dict[str, int]
    names: dict[str, tuple[str, ...]]
    attachment_paths: tuple[str, ...]
    diagnostics: tuple[tuple[str, str], ...]


def _names(records: JSONValue) -> tuple[str, ...]:
    if not isinstance(records, list):
        return ()
    return tuple(
        str(item["name"])
        for item in records
        if is_document(item) and isinstance(item.get("name"), str)
    )


def _skin_values(skins: JSONValue) -> list[JSONValue]:
    if is_document(skins):
        return list(skins.values())
    if isinstance(skins, list):
        return skins
    return []


def _attachment_refs(skins: JSONValue) -> tuple[str, ...]:
    refs = []
    for skin in _skin_values(skins):
        if not is_document(skin):
            continue
        attachment_slots = skin.get("attachments", skin)
        if not is_document(attachment_slots):
            continue
        for attachment_map in attachment_slots.values():
            if not is_document(attachment_map):
                continue
            for attachment_name, definition in attachment_map.items():
                if not is_document(definition):
                    continue
                kind = str(definition.get("type", "region")).lower()
                if kind not in IMAGE_ATTACHMENT_TYPES:
                    continue
                path = definition.get("path") or attachment_name
                if isinstance(path, str) and path:
                    refs.append(path)
    return tuple(sorted(set(refs)))


def inspect_skeleton(payload: bytes) -> SkeletonInfo | None:
    try:
        obj = decode_json_object(payload.decode("utf-8-sig"), "skeleton")
    except (UnicodeError, ValueError):
        return None
    if (
        not is_document(obj)
        or not is_document(obj.get("skeleton"))
        or not isinstance(obj.get("bones"), list)
    ):
        return None
    diagnostics = []
    meta = require_json_object(obj["skeleton"], "skeleton metadata")
    raw = meta.get("spine", meta.get("version"))
    version = str(raw).strip() if raw is not None else None
    if version is None:
        diagnostics.append(
            ("SKELETON_VERSION_MISSING", "Skeleton has no Spine export version metadata")
        )
    elif not SPINE_VERSION.fullmatch(version):
        diagnostics.append(
            ("SKELETON_VERSION_MALFORMED", f"Unrecognized Spine version: {version!r}")
        )
        version = None
    bones = _names(obj["bones"])
    slots = _names(obj.get("slots", []))
    skins = obj.get("skins", {})
    if "slots" not in obj:
        diagnostics.append(("SKELETON_SLOTS_MISSING", "Skeleton is missing essential slots field"))
    for label, values in (("bone", bones), ("slot", slots)):
        repeated = sorted({v for v in values if values.count(v) > 1})
        if repeated:
            diagnostics.append(
                ("DUPLICATE_IDENTIFIER", f"Duplicate {label} names: {', '.join(repeated)}")
            )
    if not bones:
        diagnostics.append(("SKELETON_BONES_EMPTY", "Skeleton has no named bones"))
    anim = obj.get("animations", {})
    events = obj.get("events", {})
    skin_names = (
        tuple(skins.keys())
        if is_document(skins)
        else tuple(
            str(s.get("name")) for s in skins if is_document(s) and isinstance(s.get("name"), str)
        )
        if isinstance(skins, list)
        else ()
    )
    constraints: list[str] = []
    for key in ("ik", "transform", "path", "physics"):
        constraints.extend(_names(obj.get(key, [])))
    if "constraints" in obj:
        combined_constraints = obj["constraints"]
        if not isinstance(combined_constraints, list) or any(
            not is_document(item) or not isinstance(item.get("name"), str)
            for item in combined_constraints
        ):
            diagnostics.append(
                (
                    "UNSUPPORTED_CONSTRAINTS_SHAPE",
                    "Combined Spine 4.3 constraints must be an array of named objects",
                )
            )
        else:
            constraints.extend(_names(combined_constraints))
    recognized = {
        "skeleton",
        "bones",
        "slots",
        "skins",
        "animations",
        "events",
        "ik",
        "transform",
        "path",
        "physics",
        "constraints",
        "drawOrder",
        "deform",
        "animations",
    }
    unfamiliar = sorted(set(obj) - recognized)
    if unfamiliar:
        diagnostics.append(
            (
                "UNRECOGNIZED_SKELETON_FIELDS",
                f"Unrecognized top-level fields retained: {', '.join(unfamiliar)}",
            )
        )
    if not isinstance(skins, (dict, list)):
        diagnostics.append(
            (
                "UNSUPPORTED_SKINS_SHAPE",
                "Skins must use a recognized historical object or modern array shape",
            )
        )
    if not is_document(anim):
        diagnostics.append(
            ("UNSUPPORTED_ANIMATIONS_SHAPE", "Animations must be an object keyed by animation name")
        )
    names = {
        "bones": bones,
        "slots": slots,
        "skins": skin_names,
        "animations": tuple(anim.keys()) if is_document(anim) else (),
        "events": tuple(events.keys()) if is_document(events) else (),
        "constraints": tuple(constraints),
    }
    refs = _attachment_refs(skins)
    counts = {
        "bones": len(bones),
        "slots": len(slots),
        "skins": len(skin_names),
        "animations": len(names["animations"]),
        "events": len(names["events"]),
        "constraints": len(constraints),
        "attachments": len(refs),
    }
    return SkeletonInfo(version, counts, names, refs, tuple(diagnostics))


@dataclass(frozen=True)
class AtlasPage:
    name: str
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AtlasRegion:
    name: str
    attributes: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class AtlasInfo:
    pages: tuple[str, ...]
    regions: tuple[str, ...]
    attributes: tuple[tuple[str, str], ...]
    unknown_attributes: tuple[tuple[str, str], ...]
    duplicate_regions: tuple[str, ...] = ()
    page_records: tuple[AtlasPage, ...] = ()
    region_records: tuple[AtlasRegion, ...] = ()


PAGE_KEYS = {"size", "format", "filter", "repeat", "pma", "scale", "-"}
REGION_KEYS = {
    "rotate",
    "xy",
    "size",
    "bounds",
    "offset",
    "orig",
    "offsets",
    "index",
    "split",
    "pad",
    "-",
}
TEXTURE_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp", ".ktx", ".ktx2", ".pvr", ".tga")


def parse_atlas(payload: bytes) -> AtlasInfo:
    text = payload.decode("utf-8-sig")
    pages: list[tuple[str, list[tuple[str, str]]]] = []
    regions: list[tuple[str, list[tuple[str, str]]]] = []
    attrs: list[tuple[str, str]] = []
    unknown: list[tuple[str, str]] = []
    current_page: int | None = None
    current_region: int | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Atlas attributes may be indented in modern output and unindented in
        # historical exports. A colon identifies an attribute in either grammar.
        if ":" in line:
            key, value = (part.strip() for part in line.split(":", 1))
            attrs.append((key, value))
            if current_region is not None:
                regions[current_region][1].append((key, value))
                known = REGION_KEYS
            elif current_page is not None:
                pages[current_page][1].append((key, value))
                known = PAGE_KEYS
            else:
                raise ValueError(f"Atlas attribute declared before texture page: {line!r}")
            if key.lower() not in known:
                unknown.append((key, value))
            continue
        if line.lower().endswith(TEXTURE_SUFFIXES):
            # Texture declarations are page headers in both atlas syntax families.
            pages.append((line, []))
            current_page = len(pages) - 1
            current_region = None
        elif current_page is None:
            raise ValueError(f"Region declared before texture page: {line!r}")
        else:
            regions.append((line, []))
            current_region = len(regions) - 1
    if not pages:
        raise ValueError("Atlas contains no page declarations")
    region_names = [name for name, _ in regions]
    # Atlas names may repeat when region indices distinguish the entries.
    indices = [dict(values).get("index") for _, values in regions]
    duplicate_names = {
        name
        for i, name in enumerate(region_names)
        if name in region_names[:i]
        and (indices[i] is None or indices[region_names.index(name)] is None)
    }
    duplicates = tuple(sorted(duplicate_names))
    page_records = tuple(AtlasPage(name, tuple(values)) for name, values in pages)
    region_records = tuple(AtlasRegion(name, tuple(values)) for name, values in regions)
    return AtlasInfo(
        tuple(name for name, _ in pages),
        tuple(region_names),
        tuple(attrs),
        tuple(unknown),
        duplicates,
        page_records,
        region_records,
    )
