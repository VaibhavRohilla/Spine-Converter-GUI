"""Atlas parse/serialize service using B1's shared atlas grammar."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..parsers import AtlasInfo, AtlasPage, AtlasRegion, parse_atlas
from .registry import EXACT_ROUTE_PAIRS
from .semantic import AtlasRegionGeometry, decode_atlas_geometry


@dataclass(frozen=True)
class CanonicalAtlas:
    pages: tuple[AtlasPage, ...]
    regions: tuple[AtlasRegion, ...]
    region_pages: tuple[int, ...]

    def geometry(self, source_version: str) -> tuple[AtlasRegionGeometry, ...]:
        return decode_atlas_geometry(self, source_version)


class AtlasConverter:
    """Semantically round-trip atlas text; texture payloads are never touched."""

    def read(self, source: bytes | str | Path) -> CanonicalAtlas:
        payload = source if isinstance(source, bytes) else Path(source).read_bytes()
        parsed = parse_atlas(payload)
        region_pages: list[int] = []
        page_index = -1
        for raw in payload.decode("utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or ":" in line:
                continue
            if line.lower().endswith(
                (".png", ".jpg", ".jpeg", ".webp", ".ktx", ".ktx2", ".pvr", ".tga")
            ):
                page_index += 1
            elif page_index >= 0:
                region_pages.append(page_index)
        return CanonicalAtlas(parsed.page_records, parsed.region_records, tuple(region_pages))

    def convert(
        self,
        source: bytes | str | Path,
        target_version: str | None = None,
        *,
        source_version: str | None = None,
    ) -> bytes:
        model = self.read(source)
        if target_version is not None:
            if (source_version, target_version) not in EXACT_ROUTE_PAIRS:
                raise ValueError(
                    "Atlas migration is qualified only for Spine 3.8.75 or 3.8.99 to "
                    "3.5.51, 3.6.53, 3.7.94, 3.8.99, 4.0.31, 4.1.56, 4.2.43, or 4.3.13"
                )
            if source_version is not None:
                model.geometry(source_version)
        chunks: list[str] = []
        direct_42_to_43 = source_version == "4.2.43" and target_version == "4.3.13"
        direct_43_to_42 = source_version == "4.3.13" and target_version == "4.2.43"
        direct_42_to_41 = source_version == "4.2.43" and target_version == "4.1.56"
        regions_by_page: list[list[AtlasRegion]] = [[] for _ in model.pages]
        for region, page_index in zip(model.regions, model.region_pages, strict=True):
            regions_by_page[page_index].append(region)
        for index, page in enumerate(model.pages):
            chunks.append(page.name)
            chunks.extend(f"  {key}: {value}" for key, value in page.attributes)
            for region in regions_by_page[index]:
                chunks.append(region.name)
                attributes = region.attributes
                if direct_42_to_43 or direct_43_to_42:
                    values = dict(attributes)
                    if not {"rotate", "bounds", "offsets"} <= values.keys():
                        raise ValueError(
                            f"Region {region.name!r} does not use the Spine 4.2 atlas schema"
                        )
                    try:
                        bounds = tuple(int(part.strip()) for part in values["bounds"].split(","))
                        offsets = tuple(int(part.strip()) for part in values["offsets"].split(","))
                        rotation = int(values["rotate"])
                    except ValueError as exc:
                        raise ValueError(
                            f"Malformed Spine 4.2 atlas region {region.name!r}"
                        ) from exc
                    if len(bounds) != 4 or len(offsets) != 4 or rotation not in {0, 90, 180, 270}:
                        raise ValueError(
                            f"Invalid Spine 4.2 atlas region geometry for {region.name!r}"
                        )
                elif direct_42_to_41:
                    values = dict(attributes)
                    if not {"rotate", "bounds", "offsets"} <= values.keys():
                        raise ValueError(
                            f"Region {region.name!r} does not use the Spine 4.2 atlas schema"
                        )
                    try:
                        bounds = tuple(int(part.strip()) for part in values["bounds"].split(","))
                        offsets = tuple(int(part.strip()) for part in values["offsets"].split(","))
                        rotation = int(values["rotate"])
                    except ValueError as exc:
                        raise ValueError(f"Malformed Spine 4.2 region {region.name!r}") from exc
                    if len(bounds) != 4 or len(offsets) != 4:
                        raise ValueError(f"Invalid Spine 4.2 region geometry for {region.name!r}")
                    if rotation not in {0, 90}:
                        raise ValueError(
                            f"Spine 4.1 cannot represent {rotation}-degree rotation"
                        )
                    retained = [
                        (key, value)
                        for key, value in attributes
                        if key not in {"rotate", "bounds", "offsets"}
                    ]
                    attributes = (
                        ("rotate", "true" if rotation == 90 else "false"),
                        ("xy", f"{bounds[0]}, {bounds[1]}"),
                        ("size", f"{bounds[2]}, {bounds[3]}"),
                        ("orig", f"{offsets[2]}, {offsets[3]}"),
                        ("offset", f"{offsets[0]}, {offsets[1]}"),
                    ) + tuple(retained)
                elif target_version in {"4.2.43", "4.3.13"}:
                    values = dict(attributes)
                    if len(values) != len(attributes):
                        raise ValueError(f"Duplicate atlas properties on region {region.name!r}")
                    if "bounds" in values or "offsets" in values:
                        if direct_43_to_42:
                            raise ValueError(
                                f"Region {region.name!r} does not use the Spine 4.3 atlas schema"
                            )
                        raise ValueError(
                            f"Region {region.name!r} does not use the declared 3.8 atlas syntax"
                        )
                    if not {"xy", "size"} <= values.keys():
                        raise ValueError(f"Region {region.name!r} requires xy and size fields")
                    xy = tuple(int(part.strip()) for part in values["xy"].split(","))
                    size = tuple(int(part.strip()) for part in values["size"].split(","))
                    bounds = (*xy, *size)
                    if len(bounds) != 4:
                        raise ValueError(f"Invalid bounds for atlas region {region.name!r}")
                    offset = tuple(
                        int(part.strip()) for part in values.get("offset", "0,0").split(",")
                    )
                    orig = tuple(
                        int(part.strip())
                        for part in values.get("orig", f"{bounds[2]},{bounds[3]}").split(",")
                    )
                    offsets = (*offset, *orig)
                    if len(offsets) != 4:
                        raise ValueError(f"Invalid offsets for atlas region {region.name!r}")
                    rotate = values.get("rotate", "false").lower()
                    if rotate not in {"false", "true"}:
                        raise ValueError(
                            f"Unsupported atlas rotation {rotate!r} on {region.name!r}"
                        )
                    rotate_value = {"false": "0", "true": "90"}.get(rotate, rotate)
                    retained = [
                        (key, value)
                        for key, value in attributes
                        if key
                        not in {"xy", "size", "orig", "offset", "bounds", "offsets", "rotate"}
                    ]
                    attributes = (
                        ("rotate", rotate_value),
                        ("bounds", ", ".join(map(str, bounds))),
                        ("offsets", ", ".join(map(str, offsets))),
                    ) + tuple(retained)
                elif target_version in {"4.0.31", "4.1.56"}:
                    values = dict(attributes)
                    if len(values) != len(attributes):
                        raise ValueError(f"Duplicate atlas properties on region {region.name!r}")
                    if not {"xy", "size"} <= values.keys() or "bounds" in values:
                        raise ValueError(
                            f"Region {region.name!r} does not use the declared 3.8 atlas syntax"
                        )
                    if values.get("rotate", "false").lower() not in {"true", "false"}:
                        raise ValueError(
                            f"Unsupported atlas rotation {values['rotate']!r} on {region.name!r}"
                        )
                chunks.extend(f"  {key}: {value}" for key, value in attributes)
            chunks.append("")
        output = ("\n".join(chunks).rstrip() + "\n").encode("utf-8")
        reparsed = parse_atlas(output)
        if len(reparsed.pages) != len(model.pages) or len(reparsed.regions) != len(model.regions):
            raise ValueError("Serialized atlas failed structural equivalence check")
        if direct_42_to_43:
            if reparsed.page_records != model.pages or reparsed.region_records != model.regions:
                raise ValueError("Spine 4.3 atlas serialization changed Spine 4.2 semantics")
        elif direct_43_to_42:
            if reparsed.page_records != model.pages or reparsed.region_records != model.regions:
                raise ValueError("Spine 4.2 atlas serialization changed Spine 4.3 semantics")
        elif direct_42_to_41:
            for before, after in zip(model.regions, reparsed.region_records, strict=True):
                before_attrs = dict(before.attributes)
                after_attrs = dict(after.attributes)
                bounds = tuple(int(part.strip()) for part in before_attrs["bounds"].split(","))
                offsets = tuple(int(part.strip()) for part in before_attrs["offsets"].split(","))
                xy = tuple(int(part.strip()) for part in after_attrs["xy"].split(","))
                size = tuple(int(part.strip()) for part in after_attrs["size"].split(","))
                original = tuple(int(part.strip()) for part in after_attrs["orig"].split(","))
                offset = tuple(int(part.strip()) for part in after_attrs["offset"].split(","))
                rotation = 90 if after_attrs["rotate"].lower() == "true" else 0
                if (xy + size, offset + original, rotation) != (
                    bounds,
                    offsets,
                    int(before_attrs["rotate"]),
                ):
                    raise ValueError(f"Atlas semantic equivalence failed for {before.name!r}")
        elif target_version in {"4.2.43", "4.3.13"}:
            for before, region in zip(model.regions, reparsed.region_records, strict=True):
                attrs = dict(region.attributes)
                if not {"rotate", "bounds", "offsets"} <= attrs.keys():
                    raise ValueError(f"Target atlas schema is incomplete for {region.name!r}")
                source_attrs = dict(before.attributes)
                old_xy = tuple(int(part.strip()) for part in source_attrs["xy"].split(","))
                old_size = tuple(int(part.strip()) for part in source_attrs["size"].split(","))
                old_orig = tuple(
                    int(part.strip())
                    for part in source_attrs.get("orig", f"{old_size[0]},{old_size[1]}").split(",")
                )
                old_offset = tuple(
                    int(part.strip()) for part in source_attrs.get("offset", "0,0").split(",")
                )
                old_rotation = 90 if source_attrs.get("rotate", "false").lower() == "true" else 0
                new_bounds = tuple(int(part.strip()) for part in attrs["bounds"].split(","))
                new_offsets = tuple(int(part.strip()) for part in attrs["offsets"].split(","))
                new_rotation = int(attrs["rotate"])
                if (
                    new_bounds != (*old_xy, *old_size)
                    or new_offsets != (*old_offset, *old_orig)
                    or new_rotation != old_rotation
                ):
                    raise ValueError(
                        f"Atlas semantic equivalence failed for region {region.name!r}"
                    )
        elif target_version in {
            "3.5.51", "3.6.53", "3.7.94", "3.8.99", "4.0.31", "4.1.56"
        }:
            if reparsed.page_records != model.pages or reparsed.region_records != model.regions:
                raise ValueError("Spine 4.1 atlas serialization changed source atlas semantics")
        return output


__all__ = ["AtlasConverter", "AtlasInfo"]
