"""Restricted exact-version binary serialization, independent of migration.

The wire contract is referenced to @esotericsoftware/spine-core 4.2.43
SkeletonBinary. Unsupported records are rejected, never skipped. No animation
or attachment support is implied by the hierarchy codec. Registry evidence
separates implemented operations from qualification.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import cast

from .json_types import JSONDocument, JSONValue
from .versions import BINARY_HIERARCHY_VERSION


class BinaryFeature(StrEnum):
    HIERARCHY = "hierarchy_setup_transforms"
    INHERITANCE = "bone_inheritance"
    EDITOR_METADATA = "bone_editor_metadata"
    SLOTS = "slots"
    ATTACHMENTS = "attachments"
    CONSTRAINTS = "constraints"
    ANIMATIONS = "animations"
    MESH = "mesh"
    DEFORM = "deform"
    EVENTS = "events"
    IMPLICIT_METADATA = "implicit_nonessential_metadata"


class BinaryErrorCode(StrEnum):
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

    def __post_init__(self) -> None:
        if any(
            type(value) is not int or value < 1
            for value in (self.max_bytes, self.max_string_bytes, self.max_count)
        ):
            raise ValueError("Binary limits must be positive integers")


class BinaryReader:
    def __init__(self, data: bytes, limits: BinaryLimits | None = None):
        self.limits = limits or BinaryLimits()
        if len(data) > self.limits.max_bytes:
            raise BinaryError(BinaryErrorCode.SIZE_LIMIT, "Binary exceeds configured byte limit")
        self.data, self.offset = data, 0

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
        if value > self.limits.max_count:
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
        }


class BinaryCodecRegistry:
    def capabilities(self) -> tuple[BinaryCapability, ...]:
        return (
            BinaryCapability(
                BINARY_HIERARCHY_VERSION,
                True,
                True,
                (BinaryFeature.HIERARCHY, BinaryFeature.INHERITANCE, BinaryFeature.EDITOR_METADATA),
                (
                    BinaryFeature.SLOTS,
                    BinaryFeature.ATTACHMENTS,
                    BinaryFeature.CONSTRAINTS,
                    BinaryFeature.ANIMATIONS,
                    BinaryFeature.MESH,
                    BinaryFeature.DEFORM,
                    BinaryFeature.EVENTS,
                    BinaryFeature.IMPLICIT_METADATA,
                ),
                (
                    "decode: independent hand-authored wire vector; official reader parsed",
                    "encode: independent layout assertions and official reader parsed",
                    "wire SHA-256: 6e9dd66f7417a4c30415ba496331e5fff"
                    "3fed83518ba49f754b53c4a45c35e28",
                ),
                True,
                False,
            ),
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
        for _ in range(reader.count()):
            if not reader.string():
                raise BinaryError(
                    BinaryErrorCode.STRING_TABLE, "String table contains empty entry", reader.offset
                )
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
        for feature in (
            "slots",
            "ik",
            "transform",
            "path",
            "physics",
            "default_skin",
            "skins",
            "events",
            "animations",
        ):
            if reader.count():
                raise BinaryError(
                    BinaryErrorCode.FEATURE_UNSUPPORTED,
                    f"Unsupported binary {feature} records",
                    reader.offset,
                )
        if reader.offset != len(data):
            raise BinaryError(
                BinaryErrorCode.TRAILING_DATA, "Unexpected trailing binary data", reader.offset
            )
        return {"skeleton": metadata, "bones": bones, "slots": [], "skins": [], "animations": {}}

    def encode(self, document: JSONDocument) -> bytes:
        if not self.capability.encode:
            raise BinaryError(BinaryErrorCode.ENCODE_UNSUPPORTED, "Codec has no encoder")
        try:
            return self._encode(document)
        except BinaryError:
            raise
        except (ValueError, UnicodeError, OverflowError) as exc:
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
        for feature in (
            "slots",
            "skins",
            "animations",
            "ik",
            "transform",
            "path",
            "physics",
            "events",
        ):
            if feature not in document:
                continue
            value = document[feature]
            if feature in ("animations", "events"):
                require_object(value, feature)
            else:
                require_array(value, feature)
            if value:
                raise BinaryError(
                    BinaryErrorCode.FEATURE_UNSUPPORTED, f"Unsupported binary {feature} records"
                )
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
        writer.varint(0)  # No referenced strings for the supported hierarchy subset.
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
        writer.put(bytes(9))  # Nine empty collections after hierarchy.
        return bytes(writer.data)
