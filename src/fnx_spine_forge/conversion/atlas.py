"""Atlas parse/serialize service using B1's shared atlas grammar."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..parsers import AtlasInfo, AtlasPage, AtlasRegion, parse_atlas


@dataclass(frozen=True)
class CanonicalAtlas:
    pages: tuple[AtlasPage, ...]
    regions: tuple[AtlasRegion, ...]
    region_pages: tuple[int, ...]


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
            if (source_version, target_version) not in {
                ("3.8.75", "4.2.43"),
                ("3.8.99", "4.2.43"),
            }:
                raise ValueError(
                    "Atlas migration is qualified only for Spine 3.8.75 or 3.8.99 -> 4.2.43"
                )
        chunks: list[str] = []
        regions_by_page: list[list[AtlasRegion]] = [[] for _ in model.pages]
        for region, page_index in zip(model.regions, model.region_pages, strict=True):
            regions_by_page[page_index].append(region)
        for index, page in enumerate(model.pages):
            chunks.append(page.name)
            chunks.extend(f"  {key}: {value}" for key, value in page.attributes)
            for region in regions_by_page[index]:
                chunks.append(region.name)
                attributes = region.attributes
                if target_version == "4.2.43":
                    values = dict(attributes)
                    if len(values) != len(attributes):
                        raise ValueError(f"Duplicate atlas properties on region {region.name!r}")
                    if "bounds" in values or "offsets" in values:
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
                chunks.extend(f"  {key}: {value}" for key, value in attributes)
            chunks.append("")
        output = ("\n".join(chunks).rstrip() + "\n").encode("utf-8")
        reparsed = parse_atlas(output)
        if len(reparsed.pages) != len(model.pages) or len(reparsed.regions) != len(model.regions):
            raise ValueError("Serialized atlas failed structural equivalence check")
        if target_version == "4.2.43":
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
        return output


__all__ = ["AtlasConverter", "AtlasInfo"]
