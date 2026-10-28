"""Restricted exact-version binary serialization, independent of migration.

The wire contract is referenced to @esotericsoftware/spine-core 4.2.43
SkeletonBinary. Unsupported records are rejected, never skipped. The animated
profile remains experimental until independent decoder and release evidence
are complete. Registry evidence
separates implemented operations from qualification.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

from .binary_schema import ANIMATED_42_PROFILE, BinaryProfile
from .json_types import JSONDocument, JSONValue
from .versions import BINARY_EXPORT_VERSION, BINARY_REFERENCE_EXPORT_VERSION


class BinaryFeature(StrEnum):
    HIERARCHY = "hierarchy_setup_transforms"
    INHERITANCE = "bone_inheritance"
    EDITOR_METADATA = "bone_editor_metadata"
    REGIONS = "region_attachments"
    WEIGHTED_MESH = "weighted_mesh_attachments"
    LINKED_MESH = "linked_mesh_attachments"
    BONE_TIMELINES = "bone_transform_timelines"
    SLOT_TIMELINES = "slot_attachment_rgba_timelines"
    IK_SETUP = "ik_setup_constraints"
    DRAW_ORDER = "draw_order_timelines"
    SLOTS = "slots"
    ATTACHMENTS = "attachments"
    CONSTRAINTS = "constraints"
    ANIMATIONS = "animations"
    MESH = "mesh"
    DEFORM = "deform"
    EVENTS = "events"
    IMPLICIT_METADATA = "implicit_nonessential_metadata"


class BinaryErrorCode(StrEnum):
    GEOMETRY = "BINARY_GEOMETRY"
    REFERENCE = "BINARY_REFERENCE"
    TIMELINE = "BINARY_TIMELINE"
    CAPABILITY_INVALID = "BINARY_CAPABILITY_INVALID"
    METADATA_INCOMPLETE = "BINARY_METADATA_INCOMPLETE"
    BONES = "BINARY_BONES"
    BONE_INDEX = "BINARY_BONE_INDEX"
    BONE_NAME = "BINARY_BONE_NAME"
    BOOLEAN = "BINARY_BOOLEAN"
    COLOR = "BINARY_COLOR"
    COUNT_LIMIT = "BINARY_COUNT_LIMIT"
    DECODE_UNSUPPORTED = "BINARY_DECODE_UNSUPPORTED"
    ENCODE_UNSUPPORTED = "BINARY_ENCODE_UNSUPPORTED"
    FEATURE_UNSUPPORTED = "BINARY_FEATURE_UNSUPPORTED"
    HASH = "BINARY_HASH"
    INHERIT = "BINARY_INHERIT"
    INVALID_DOCUMENT = "BINARY_INVALID_DOCUMENT"
    NONFINITE = "BINARY_NONFINITE"
    NUMBER = "BINARY_NUMBER"
    SIZE_LIMIT = "BINARY_SIZE_LIMIT"
    STRING_LIMIT = "BINARY_STRING_LIMIT"
    STRING_TABLE = "BINARY_STRING_TABLE"
    TRAILING_DATA = "BINARY_TRAILING_DATA"
    TRUNCATED = "BINARY_TRUNCATED"
    UNQUALIFIED = "BINARY_UNQUALIFIED"
    UTF8 = "BINARY_UTF8"
    VARINT = "BINARY_VARINT"
    VERSION_UNSUPPORTED = "BINARY_VERSION_UNSUPPORTED"


class BinaryError(ValueError):
    def __init__(self, code: BinaryErrorCode, message: str, offset: int = 0):
        super().__init__(message)
        self.code, self.offset = code, offset

    def to_dict(self) -> JSONDocument:
        return {"code": self.code.value, "message": str(self), "offset": self.offset}


@dataclass(frozen=True)
class BinaryLimits:
    max_bytes: int = 32 * 1024 * 1024
    max_string_bytes: int = 65536
    max_count: int = 10000
    max_total_items: int = 160000
    max_depth: int = 32

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 1
            for value in (
                self.max_bytes,
                self.max_string_bytes,
                self.max_count,
                self.max_total_items,
                self.max_depth,
            )
        ):
            raise ValueError("Binary limits must be positive integers")


class BinaryReader:
    def __init__(self, data: bytes, limits: BinaryLimits | None = None):
        self.limits = limits or BinaryLimits()
        if len(data) > self.limits.max_bytes:
            raise BinaryError(BinaryErrorCode.SIZE_LIMIT, "Binary exceeds configured byte limit")
        self.data, self.offset = data, 0
        self._declared_items = 0

    def take(self, count: int) -> bytes:
        if count < 0 or count > len(self.data) - self.offset:
            raise BinaryError(BinaryErrorCode.TRUNCATED, "Read exceeds binary bounds", self.offset)
        start = self.offset
        self.offset += count
        return self.data[start : self.offset]

    def byte(self) -> int:
        return self.take(1)[0]

    def boolean(self) -> bool:
        value = self.byte()
        if value not in (0, 1):
            raise BinaryError(BinaryErrorCode.BOOLEAN, "Invalid boolean", self.offset - 1)
        return bool(value)

    def varint(self) -> int:
        value = 0
        for index in range(5):
            byte = self.byte()
            if index == 4 and byte > 15:
                raise BinaryError(BinaryErrorCode.VARINT, "Varint exceeds 32 bits", self.offset - 1)
            value |= (byte & 127) << (index * 7)
            if byte < 128:
                if index and byte == 0:
                    raise BinaryError(
                        BinaryErrorCode.VARINT, "Noncanonical varint", self.offset - 1
                    )
                return value
        raise BinaryError(BinaryErrorCode.VARINT, "Unterminated varint", self.offset)

    def count(self) -> int:
        value = self.varint()
        self._declared_items += value
        if value > self.limits.max_count or self._declared_items > self.limits.max_total_items:
            raise BinaryError(
                BinaryErrorCode.COUNT_LIMIT, "Collection count exceeds limit", self.offset
            )
        return value

    def string(self) -> str | None:
        length = self.varint()
        if length == 0:
            return None
        length -= 1
        if length > self.limits.max_string_bytes:
            raise BinaryError(BinaryErrorCode.STRING_LIMIT, "String exceeds limit", self.offset)
        try:
            return self.take(length).decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise BinaryError(BinaryErrorCode.UTF8, "Invalid UTF-8", self.offset) from exc

    def number(self) -> float:
        value = cast(tuple[float], struct.unpack(">f", self.take(4)))[0]
        if not math.isfinite(value):
            raise BinaryError(BinaryErrorCode.NONFINITE, "Non-finite number", self.offset - 4)
        return value


class _Writer:
    def __init__(self, limits: BinaryLimits):
        self.data = bytearray()
        self.limits = limits

    def put(self, data: bytes) -> None:
        if len(self.data) + len(data) > self.limits.max_bytes:
            raise BinaryError(BinaryErrorCode.SIZE_LIMIT, "Encoded output exceeds limit")
        self.data.extend(data)

    def varint(self, value: int) -> None:
        if not 0 <= value <= 0xFFFFFFFF:
            raise BinaryError(BinaryErrorCode.VARINT, "Integer outside unsigned 32-bit range")
        while value >= 128:
            self.put(bytes(((value & 127) | 128,)))
            value >>= 7
        self.put(bytes((value,)))

    def string(self, value: str | None) -> None:
        if value is None:
            self.varint(0)
            return
        try:
            encoded = value.encode("utf-8")
        except UnicodeError as exc:
            raise BinaryError(BinaryErrorCode.UTF8, "String cannot be encoded as UTF-8") from exc
        if len(encoded) > self.limits.max_string_bytes:
            raise BinaryError(BinaryErrorCode.STRING_LIMIT, "String exceeds limit")
        self.varint(len(encoded) + 1)
        self.put(encoded)

    def number(self, value: JSONValue) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise BinaryError(BinaryErrorCode.NUMBER, "Expected a finite numeric value")
        try:
            numeric = float(value)
            if not math.isfinite(numeric):
                raise ValueError
            self.put(struct.pack(">f", numeric))
        except (ValueError, OverflowError, struct.error) as exc:
            raise BinaryError(
                BinaryErrorCode.NUMBER, "Value cannot be serialized as finite float32"
            ) from exc


@dataclass(frozen=True)
class BinaryCapability:
    version: str
    decode: bool
    encode: bool
    features: tuple[BinaryFeature, ...]
    unsupported: tuple[BinaryFeature, ...]
    fixture_evidence: tuple[str, ...]
    structurally_verified: bool
    semantically_qualified: bool
    profile: BinaryProfile
    runtime_qualified: bool = False

    def to_dict(self) -> JSONDocument:
        return {
            "version": self.version,
            "source_version": self.version,
            "target_version": self.version,
            "decode": self.decode,
            "decode_structural_verification": self.structurally_verified and self.decode,
            "encode_structural_verification": self.structurally_verified and self.encode,
            "encode": self.encode,
            "features": tuple(f.value for f in self.features),
            "unsupported": tuple(f.value for f in self.unsupported),
            "fixture_evidence": self.fixture_evidence,
            "structurally_verified": self.structurally_verified,
            "semantically_qualified": self.semantically_qualified,
            "runtime_qualified": self.runtime_qualified,
            "input_formats": tuple(
                name
                for name, enabled in (("json", self.encode), ("binary", self.decode))
                if enabled
            ),
            "output_formats": tuple(
                name
                for name, enabled in (("json", self.decode), ("binary", self.encode))
                if enabled
            ),
            "experimental": not self.semantically_qualified,
            "supported_attachments": tuple(kind.value for kind in self.profile.attachments),
            "supported_bone_timelines": tuple(
                kind.name.lower() for kind in self.profile.bone_timelines
            ),
            "supported_slot_timelines": tuple(kind.value for kind in self.profile.slot_timelines),
            "supported_attachment_timelines": self.profile.attachment_timelines,
            "supported_global_timelines": self.profile.global_timelines,
            "supported_constraints": self.profile.constraints,
            "interpolation": self.profile.interpolation,
            "decoder_qualification": (
                "experimental: authentic Powerup 4.2.22 region/bone/RGBA comparisons; "
                "unverified fields and release gates remain"
                if self.version == BINARY_REFERENCE_EXPORT_VERSION
                else "unqualified: authentic animated binary evidence missing"
            ),
            "encoder_qualification": (
                "unqualified: unchanged authentic JSON rejected; binary-derived "
                "input is not independent JSON encoder qualification"
                if self.version == BINARY_REFERENCE_EXPORT_VERSION
                else "experimental: specified-fixture official runtime comparisons"
            ),
            "restrictions": self.profile.restrictions,
        }


class BinaryCodecRegistry:
    def capabilities(self) -> tuple[BinaryCapability, ...]:
        return tuple(
            BinaryCapability(
                version,
                True,
                True,
                (
                    BinaryFeature.HIERARCHY,
                    BinaryFeature.INHERITANCE,
                    BinaryFeature.EDITOR_METADATA,
                    BinaryFeature.SLOTS,
                    BinaryFeature.REGIONS,
                    BinaryFeature.MESH,
                    BinaryFeature.WEIGHTED_MESH,
                    BinaryFeature.LINKED_MESH,
                    BinaryFeature.DEFORM,
                    BinaryFeature.BONE_TIMELINES,
                    BinaryFeature.SLOT_TIMELINES,
                    BinaryFeature.IK_SETUP,
                    BinaryFeature.DRAW_ORDER,
                ),
                (
                    BinaryFeature.ATTACHMENTS,
                    BinaryFeature.CONSTRAINTS,
                    BinaryFeature.ANIMATIONS,
                    BinaryFeature.EVENTS,
                    BinaryFeature.IMPLICIT_METADATA,
                ),
                (
                    "docs/evidence/B3_decoder/qualification.json: authentic Powerup decoder",
                    "tests/fixtures/binary/official42/provenance.json: pinned unchanged sources",
                    "scripts/compare_binary42.mts: official binary semantic reference",
                ) if version == BINARY_REFERENCE_EXPORT_VERSION else (
                    "docs/evidence/B3_binary/qualification.json: animated encoder fixtures",
                    "tests/test_binary_animation.py: independent region/rotate decoder wire vector",
                    "decode: independent hand-authored wire vector; official reader parsed",
                    "encode: independent layout assertions and official reader parsed",
                    "wire SHA-256: 6e9dd66f7417a4c30415ba496331e5fff"
                    "3fed83518ba49f754b53c4a45c35e28",
                ),
                True,
                False,
                ANIMATED_42_PROFILE,
            )
            for version in (BINARY_EXPORT_VERSION, BINARY_REFERENCE_EXPORT_VERSION)
        )

    def codec(
        self, version: str, *, experimental: bool = False, limits: BinaryLimits | None = None
    ) -> BinarySkeletonCodec:
        if type(experimental) is not bool:
            raise TypeError("experimental authorization must be a boolean")
        capability = next((c for c in self.capabilities() if c.version == version), None)
        if capability is None:
            raise BinaryError(
                BinaryErrorCode.VERSION_UNSUPPORTED, "No codec for exact binary version"
            )
        if not capability.semantically_qualified and not experimental:
            raise BinaryError(
                BinaryErrorCode.UNQUALIFIED,
                "Binary codec requires explicit experimental authorization",
            )
        return BinarySkeletonCodec(capability, limits, experimental=experimental)

    def probe(self, data: bytes, *, limits: BinaryLimits | None = None) -> str:
        reader = BinaryReader(data, limits)
        reader.take(8)  # 4.2 hash consists of two big-endian int32 words.
        version = reader.string()
        if not version or version not in {c.version for c in self.capabilities()}:
            raise BinaryError(
                BinaryErrorCode.VERSION_UNSUPPORTED,
                "Unrecognized exact binary schema",
                reader.offset,
            )
        return version


_INHERIT = ("normal", "onlyTranslation", "noRotationOrReflection", "noScale", "noScaleOrReflection")
_BONE_FLOATS = ("rotation", "x", "y", "scaleX", "scaleY", "shearX", "shearY", "length")


class BinarySkeletonCodec:
    def __init__(
        self,
        capability: BinaryCapability,
        limits: BinaryLimits | None = None,
        *,
        experimental: bool = False,
    ):
        if type(experimental) is not bool:
            raise TypeError("experimental authorization must be a boolean")
        approved = next(
            (c for c in BinaryCodecRegistry().capabilities() if c.version == capability.version),
            None,
        )
        if approved is None or capability != replace(
            approved,
            decode=capability.decode and approved.decode,
            encode=capability.encode and approved.encode,
        ):
            raise BinaryError(
                BinaryErrorCode.CAPABILITY_INVALID,
                "Codec capabilities must match registered evidence; only disabling "
                "an operation is permitted",
            )
        if not capability.semantically_qualified and not experimental:
            raise BinaryError(
                BinaryErrorCode.UNQUALIFIED, "Explicit experimental authorization is required"
            )
        self._capability = capability
        self.limits = limits or BinaryLimits()

    @property
    def capability(self) -> BinaryCapability:
        return self._capability

    def decode(self, data: bytes) -> JSONDocument:
        if not self.capability.decode:
            raise BinaryError(BinaryErrorCode.DECODE_UNSUPPORTED, "Codec has no decoder")
        reader = BinaryReader(data, self.limits)
        hash_bytes = reader.take(8)
        version = reader.string()
        if version != self.capability.version:
            raise BinaryError(
                BinaryErrorCode.VERSION_UNSUPPORTED, "Codec and header versions differ"
            )
        metadata: JSONDocument = {"spine": version, "hash": hash_bytes.hex()}
        for metadata_name in ("x", "y", "width", "height", "referenceScale"):
            metadata[metadata_name] = reader.number()
        nonessential = reader.boolean()
        if nonessential:
            metadata["fps"] = reader.number()
            for metadata_name in ("images", "audio"):
                value = reader.string()
                if value is not None:
                    metadata[metadata_name] = value
        # Even unused strings must be bounded and verified.
        strings: list[str] = []
        for _ in range(reader.count()):
            string = reader.string()
            if not string:
                raise BinaryError(
                    BinaryErrorCode.STRING_TABLE, "String table contains empty entry", reader.offset
                )
            strings.append(string)
        bones: list[JSONValue] = []
        names: list[str] = []
        seen_names: set[str] = set()
        for index in range(reader.count()):
            name = reader.string()
            if not name or name in seen_names:
                raise BinaryError(
                    BinaryErrorCode.BONE_NAME, "Empty or duplicate bone name", reader.offset
                )
            bone: JSONDocument = {"name": name}
            if index:
                parent = reader.varint()
                if parent >= index:
                    raise BinaryError(
                        BinaryErrorCode.BONE_INDEX, "Parent must precede child", reader.offset
                    )
                bone["parent"] = names[parent]
            for field_name in _BONE_FLOATS:
                bone[field_name] = reader.number()
            inherit = reader.byte()
            if inherit >= len(_INHERIT):
                raise BinaryError(
                    BinaryErrorCode.INHERIT, "Invalid inheritance enum", reader.offset - 1
                )
            bone["inherit"] = _INHERIT[inherit]
            bone["skin"] = reader.boolean()
            if nonessential:
                bone["color"] = reader.take(4).hex()
                icon = reader.string()
                if icon is not None:
                    bone["icon"] = icon
                bone["visible"] = reader.boolean()
            bones.append(bone)
            names.append(name)
            seen_names.add(name)
        if not bones:
            raise BinaryError(BinaryErrorCode.BONES, "Skeleton requires a root bone", reader.offset)
        from .binary_animation import TailReader

        tail = TailReader(reader, strings, names, nonessential).decode()
        if reader.offset != len(data):
            raise BinaryError(
                BinaryErrorCode.TRAILING_DATA, "Unexpected trailing binary data", reader.offset
            )
        document = {"skeleton": metadata, "bones": bones, **tail}
        self._validate_semantics(document)
        return document

    def encode(self, document: JSONDocument) -> bytes:
        if not self.capability.encode:
            raise BinaryError(BinaryErrorCode.ENCODE_UNSUPPORTED, "Codec has no encoder")
        try:
            self._preflight(document)
            encoded = self._encode(document)
            self._validate_semantics(document)
            return encoded
        except BinaryError:
            raise
        except (ValueError, UnicodeError, OverflowError) as exc:
            raise BinaryError(BinaryErrorCode.INVALID_DOCUMENT, str(exc)) from exc

    def _preflight(self, document: JSONDocument) -> None:
        # Iterative, bounded admission also rejects cycles and hostile Python
        # values supplied directly to the API, before constructing domain lists.
        stack: list[tuple[JSONValue, int]] = [(document, 0)]
        visited = 0
        while stack:
            value, depth = stack.pop()
            visited += 1
            if depth > self.limits.max_depth or visited > self.limits.max_total_items:
                raise BinaryError(BinaryErrorCode.COUNT_LIMIT, "Document complexity exceeds limit")
            if isinstance(value, dict):
                if len(value) > self.limits.max_count:
                    raise BinaryError(BinaryErrorCode.COUNT_LIMIT, "Object exceeds limit")
                for key, child in value.items():
                    if not isinstance(key, str):
                        raise BinaryError(BinaryErrorCode.INVALID_DOCUMENT, "Non-string object key")
                    stack.append((child, depth + 1))
            elif isinstance(value, list):
                if len(value) > self.limits.max_count:
                    raise BinaryError(BinaryErrorCode.COUNT_LIMIT, "Array exceeds limit")
                stack.extend((child, depth + 1) for child in value)
            elif isinstance(value, str):
                if len(value.encode("utf-8")) > self.limits.max_string_bytes:
                    raise BinaryError(BinaryErrorCode.STRING_LIMIT, "String exceeds limit")
            elif value is not None and not isinstance(value, (int, float, bool)):
                raise BinaryError(BinaryErrorCode.INVALID_DOCUMENT, "Non-JSON input")

    def _validate_semantics(self, document: JSONDocument) -> None:
        from .conversion.document import require_array, require_object
        from .conversion.semantic import decode_semantic_skeleton

        # B2 models runtime semantics; binary-only editor visibility remains in
        # the original document and is validated by this codec.
        projection = dict(document)
        for category in ("bones", "slots"):
            projection[category] = [
                {k: v for k, v in require_object(row, category).items() if k != "visible"}
                for row in require_array(document.get(category, []), category)
            ]
        projection["ik"] = [
            {k: v for k, v in require_object(row, "ik").items() if k != "skin"}
            for row in require_array(document.get("ik", []), "ik")
        ]
        try:
            decode_semantic_skeleton(projection, self.capability.version)
        except ValueError as exc:
            raise BinaryError(BinaryErrorCode.INVALID_DOCUMENT, str(exc)) from exc

    def _encode(self, document: JSONDocument) -> bytes:
        from .conversion.document import require_array, require_object, require_text

        if set(document) - {
            "skeleton",
            "bones",
            "slots",
            "skins",
            "animations",
            "ik",
            "transform",
            "path",
            "physics",
            "events",
        }:
            raise BinaryError(BinaryErrorCode.FEATURE_UNSUPPORTED, "Unknown skeleton extensions")
        metadata = require_object(document.get("skeleton", {}), "skeleton metadata")
        if metadata.get("spine") != self.capability.version:
            raise BinaryError(
                BinaryErrorCode.VERSION_UNSUPPORTED, "Use B2 migration before target encoding"
            )
        if set(metadata) - {
            "spine",
            "hash",
            "x",
            "y",
            "width",
            "height",
            "referenceScale",
            "fps",
            "images",
            "audio",
        }:
            raise BinaryError(BinaryErrorCode.FEATURE_UNSUPPORTED, "Unknown skeleton metadata")
        hash_value = metadata.get("hash")
        if hash_value is None or hash_value == "":
            hash_bytes = bytes(8)
        elif isinstance(hash_value, str) and len(hash_value) == 16:
            try:
                hash_bytes = bytes.fromhex(hash_value)
            except ValueError as exc:
                raise BinaryError(BinaryErrorCode.HASH, "Hash must represent eight bytes") from exc
            if len(hash_bytes) != 8:
                raise BinaryError(BinaryErrorCode.HASH, "Hash must represent eight bytes")
        else:
            raise BinaryError(BinaryErrorCode.HASH, "Hash is not representable by this codec")
        writer = _Writer(self.limits)
        writer.put(hash_bytes)
        writer.string(self.capability.version)
        for name in ("x", "y", "width", "height", "referenceScale"):
            writer.number(metadata.get(name, 100 if name == "referenceScale" else 0))
        bones = require_array(document.get("bones", []), "bones")
        if not bones or len(bones) > self.limits.max_count:
            raise BinaryError(BinaryErrorCode.COUNT_LIMIT, "Bone count outside supported limits")
        records = [require_object(b, "bone") for b in bones]
        nonessential = any(k in metadata for k in ("fps", "images", "audio")) or any(
            set(b) & {"color", "icon", "visible"} for b in records
        )
        writer.put(bytes((int(nonessential),)))
        if nonessential:
            if "fps" not in metadata or any(
                not {"color", "visible"} <= bone.keys() for bone in records
            ):
                raise BinaryError(
                    BinaryErrorCode.METADATA_INCOMPLETE,
                    "Nonessential binary output requires explicit fps, bone color and visibility; "
                    "editor metadata defaults are not inferred",
                )
            writer.number(metadata["fps"])
            for name in ("images", "audio"):
                value = metadata.get(name)
                writer.string(require_text(value, name) if value is not None else None)
        from .binary_animation import TailWriter

        tail_writer = TailWriter(document, self.limits, nonessential)
        tail = tail_writer.encode()
        writer.varint(len(tail_writer.strings))
        for string in tail_writer.strings:
            writer.string(string)
        writer.varint(len(records))
        name_indices: dict[str, int] = {}
        for index, bone in enumerate(records):
            if set(bone) - {
                "name",
                "parent",
                "inherit",
                "skin",
                "color",
                "icon",
                "visible",
                *_BONE_FLOATS,
            }:
                raise BinaryError(BinaryErrorCode.FEATURE_UNSUPPORTED, "Unknown bone fields")
            name = require_text(bone.get("name"), "bone name")
            if not name or name in name_indices:
                raise BinaryError(BinaryErrorCode.BONE_NAME, "Empty or duplicate bone name")
            writer.string(name)
            parent = bone.get("parent")
            if index:
                if not isinstance(parent, str) or parent not in name_indices:
                    raise BinaryError(BinaryErrorCode.BONE_INDEX, "Parent must precede child")
                writer.varint(name_indices[parent])
            elif parent is not None:
                raise BinaryError(BinaryErrorCode.BONE_INDEX, "Root must not have a parent")
            for field_name in _BONE_FLOATS:
                writer.number(bone.get(field_name, 1 if field_name in ("scaleX", "scaleY") else 0))
            inherit = bone.get("inherit", "normal")
            if not isinstance(inherit, str) or inherit not in _INHERIT:
                raise BinaryError(BinaryErrorCode.INHERIT, "Invalid inheritance mode")
            skin, visible = bone.get("skin", False), bone.get("visible", False)
            if not isinstance(skin, bool) or not isinstance(visible, bool):
                raise BinaryError(BinaryErrorCode.BOOLEAN, "Bone flags must be boolean")
            writer.put(bytes((_INHERIT.index(inherit), int(skin))))
            if nonessential:
                color = bone["color"]
                if not isinstance(color, str) or len(color) != 8:
                    raise BinaryError(BinaryErrorCode.COLOR, "Invalid RGBA color")
                try:
                    encoded_color = bytes.fromhex(color)
                except ValueError as exc:
                    raise BinaryError(BinaryErrorCode.COLOR, "Invalid RGBA color") from exc
                if len(encoded_color) != 4:
                    raise BinaryError(BinaryErrorCode.COLOR, "Invalid RGBA color")
                writer.put(encoded_color)
                icon = bone.get("icon")
                writer.string(require_text(icon, "bone icon") if icon is not None else None)
                writer.put(bytes((int(visible),)))
            name_indices[name] = index
        writer.put(tail)
        return bytes(writer.data)
