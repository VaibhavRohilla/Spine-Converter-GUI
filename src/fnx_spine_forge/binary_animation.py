"""Bounded 4.2.43 animated-region wire records.

Exact wire reference: pinned spine-core 4.2.43 SkeletonBinary/SkeletonJson.
This module is deliberately narrower than the complete 4.2 schema. Unknown
records fail before publication; it is not a migration engine.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Literal, Never, cast

from .binary import BinaryError, BinaryErrorCode, BinaryLimits, BinaryReader, _Writer
from .binary_schema import ANIMATED_42_PROFILE, BoneTimelineKind
from .conversion.document import require_array, require_number, require_object, require_text
from .json_types import JSONDocument, JSONValue


def frame_time(value: JSONValue) -> float:
    number = require_number(value, "time")
    try:
        return cast(tuple[float], struct.unpack(">f", struct.pack(">f", number)))[0]
    except (OverflowError, struct.error) as exc:
        raise BinaryError(BinaryErrorCode.TIMELINE, "Time exceeds float32") from exc


def reject(message: str) -> Never:
    raise BinaryError(BinaryErrorCode.FEATURE_UNSUPPORTED, message)


def fields(record: JSONDocument, allowed: set[str], context: str) -> None:
    extra = record.keys() - allowed
    if extra:
        reject(f"Unsupported {context} fields: {', '.join(sorted(extra))}")


def index(value: int, names: list[str], context: str) -> str:
    if not 0 <= value < len(names):
        raise BinaryError(BinaryErrorCode.REFERENCE, f"Invalid {context} index")
    return names[value]


def named(value: JSONValue, names: list[str], context: str) -> int:
    name = require_text(value, context)
    if name not in names:
        raise BinaryError(BinaryErrorCode.REFERENCE, f"Unknown {context}: {name}")
    return names.index(name)


def integer(value: JSONValue, context: str) -> int:
    if type(value) is not int or value < 0:
        raise BinaryError(BinaryErrorCode.GEOMETRY, f"Invalid {context}")
    return value


def unique(name: str | None, names: list[str], context: str) -> str:
    if not name or name in names:
        raise BinaryError(BinaryErrorCode.REFERENCE, f"Empty or duplicate {context}")
    return name


def color(value: JSONValue, size: int = 4) -> bytes:
    if not isinstance(value, str) or len(value) != size * 2:
        raise BinaryError(BinaryErrorCode.COLOR, "Invalid color length")
    try:
        result = bytes.fromhex(value)
    except ValueError as exc:
        raise BinaryError(BinaryErrorCode.COLOR, "Invalid color") from exc
    if len(result) != size:
        raise BinaryError(BinaryErrorCode.COLOR, "Invalid color")
    return result


@dataclass(frozen=True, slots=True)
class BezierCurve:
    channels: tuple[tuple[float, float, float, float], ...]

    @classmethod
    def parse(cls, value: JSONValue, dimensions: int) -> BezierCurve:
        controls = require_array(value, "curve")
        if len(controls) != dimensions * 4:
            raise BinaryError(BinaryErrorCode.TIMELINE, "Curve dimension mismatch")
        return cls(
            tuple(
                (
                    require_number(controls[i], "cx1"),
                    require_number(controls[i + 1], "cy1"),
                    require_number(controls[i + 2], "cx2"),
                    require_number(controls[i + 3], "cy2"),
                )
                for i in range(0, len(controls), 4)
            )
        )


@dataclass(frozen=True, slots=True)
class Keyframe:
    time: float
    values: tuple[float, ...]
    curve: Literal["stepped"] | BezierCurve | None


@dataclass(frozen=True, slots=True)
class BoneTimeline:
    bone: int
    kind: BoneTimelineKind
    frames: tuple[Keyframe, ...]


@dataclass(frozen=True, slots=True)
class RegionAttachment:
    name: str
    path: str
    rgba: bytes
    rotation: float
    transform: tuple[float, float, float, float, float, float]


def deform_size(skins: list[JSONDocument], skin_name: str, slot: str, key: str) -> int:
    visited: set[tuple[str, str]] = set()
    while True:
        identity = skin_name, key
        if identity in visited:
            raise BinaryError(BinaryErrorCode.REFERENCE, "Cyclic linked mesh")
        visited.add(identity)
        skin = next((s for s in skins if s["name"] == skin_name), None)
        if skin is None:
            raise BinaryError(BinaryErrorCode.REFERENCE, "Missing mesh skin")
        attachments = require_object(skin.get("attachments", {}), "attachments")
        values = require_object(attachments.get(slot, {}), "slot attachments")
        a = require_object(values.get(key, {}), "deform attachment")
        if a.get("type") == "linkedmesh":
            skin_name = require_text(a.get("skin", "default"), "parent skin")
            key = require_text(a.get("parent"), "parent mesh")
            continue
        if a.get("type") != "mesh":
            raise BinaryError(BinaryErrorCode.REFERENCE, "Deform or linked parent must be a mesh")
        vertices = require_array(a.get("vertices", []), "vertices")
        uvs = require_array(a.get("uvs", []), "uvs")
        if len(vertices) == len(uvs):
            return len(vertices)
        cursor = 0
        influences = 0
        for _ in range(len(uvs) // 2):
            if cursor >= len(vertices):
                raise BinaryError(BinaryErrorCode.GEOMETRY, "Truncated influences")
            count = integer(vertices[cursor], "influences")
            cursor += count * 4 + 1
            influences += count
        if cursor != len(vertices):
            raise BinaryError(BinaryErrorCode.GEOMETRY, "Invalid influences")
        return influences * 2


class TailWriter:
    def __init__(self, document: JSONDocument, limits: BinaryLimits, nonessential: bool):
        self.document = document
        self.writer = _Writer(limits)
        self.nonessential = nonessential
        self.strings: list[str] = []
        self._string_indices: dict[str, int] = {}
        self.bones = [
            require_text(require_object(b, "bone").get("name"), "bone name")
            for b in require_array(document.get("bones", []), "bones")
        ]
        self.slots: list[str] = []
        self.skin_names: list[str] = []
        self.skins: list[JSONDocument] = []

    def count(self, count: int) -> None:
        if count > self.writer.limits.max_count:
            raise BinaryError(BinaryErrorCode.COUNT_LIMIT, "Collection exceeds limit")
        self.writer.varint(count)

    def ref(self, value: JSONValue) -> None:
        if value is None:
            self.writer.varint(0)
            return
        name = require_text(value, "string reference")
        if not name:
            raise BinaryError(BinaryErrorCode.STRING_TABLE, "Empty referenced string")
        if name not in self._string_indices:
            if len(self.strings) >= self.writer.limits.max_count:
                raise BinaryError(BinaryErrorCode.COUNT_LIMIT, "String table exceeds limit")
            self.strings.append(name)
            self._string_indices[name] = len(self.strings)
        self.writer.varint(self._string_indices[name])

    def encode(self) -> bytes:
        w = self.writer
        slots = require_array(self.document.get("slots", []), "slots")
        self.count(len(slots))
        for item in slots:
            slot = require_object(item, "slot")
            fields(
                slot, {"name", "bone", "color", "dark", "attachment", "blend", "visible"}, "slot"
            )
            name = unique(require_text(slot.get("name"), "slot name"), self.slots, "slot name")
            self.slots.append(name)
            w.string(name)
            w.varint(named(slot.get("bone"), self.bones, "slot bone"))
            w.put(color(slot.get("color", "ffffffff")))
            w.put(b"\0" + color(slot["dark"], 3) if "dark" in slot else b"\xff" * 4)
            self.ref(slot.get("attachment"))
            blend = slot.get("blend", "normal")
            blends = ["normal", "additive", "multiply", "screen"]
            w.varint(named(blend, blends, "blend"))
            if not self.nonessential and "visible" in slot:
                reject("Slot visibility requires explicit nonessential metadata")
            if self.nonessential:
                visible = slot.get("visible", True)
                if type(visible) is not bool:
                    raise BinaryError(BinaryErrorCode.BOOLEAN, "Invalid slot visibility")
                w.put(bytes((int(visible),)))
        constraints = require_array(self.document.get("ik", []), "IK constraints")
        self.count(len(constraints))
        constraint_names: list[str] = []
        for value in constraints:
            c = require_object(value, "IK constraint")
            fields(
                c,
                {
                    "name",
                    "order",
                    "bones",
                    "target",
                    "skin",
                    "bendPositive",
                    "compress",
                    "stretch",
                    "uniform",
                    "mix",
                    "softness",
                },
                "IK constraint",
            )
            name = unique(require_text(c.get("name"), "IK name"), constraint_names, "IK name")
            constraint_names.append(name)
            w.string(name)
            self.count(integer(c.get("order", 0), "constraint order"))
            bones = require_array(c.get("bones", []), "IK bones")
            if not 1 <= len(bones) <= 2:
                reject("IK profile requires one or two constrained bones")
            self.count(len(bones))
            for bone in bones:
                w.varint(named(bone, self.bones, "IK bone"))
            w.varint(named(c.get("target"), self.bones, "IK target"))
            if c.get("skin", False):
                reject("Skin-required IK is outside this profile")
            flags = 32 | 64 | 128
            for bit, field, default_flag in (
                (1, "skin", False),
                (2, "bendPositive", True),
                (4, "compress", False),
                (8, "stretch", False),
                (16, "uniform", False),
            ):
                flag = c.get(field, default_flag)
                if type(flag) is not bool:
                    raise BinaryError(BinaryErrorCode.BOOLEAN, "Invalid IK boolean")
                if flag:
                    flags |= bit
            w.put(bytes((flags,)))
            w.number(c.get("mix", 1))
            w.number(c.get("softness", 0))
        for category in ("transform", "path", "physics"):
            if require_array(self.document.get(category, []), category):
                reject(f"Unsupported binary {category} constraints")
            self.count(0)
        skins = [
            require_object(s, "skin")
            for s in require_array(self.document.get("skins", []), "skins")
        ]
        self.skins = skins
        names: list[str] = []
        for skin in skins:
            names.append(unique(require_text(skin.get("name"), "skin name"), names, "skin name"))
        self.skin_names = (["default"] if "default" in names else []) + [
            n for n in names if n != "default"
        ]
        default = next((s for s in skins if s["name"] == "default"), None)
        if default is None:
            self.count(0)
        else:
            self.skin(default, True)
        others = [s for s in skins if s["name"] != "default"]
        self.count(len(others))
        for skin in others:
            self.skin(skin, False)
        for skin in skins:
            for slot_name, values in require_object(
                skin.get("attachments", {}), "attachments"
            ).items():
                for key, value in require_object(values, "attachments").items():
                    if require_object(value, "attachment").get("type") == "linkedmesh":
                        deform_size(skins, require_text(skin["name"], "skin"), slot_name, key)
        if require_object(self.document.get("events", {}), "events"):
            reject("Unsupported binary events")
        self.count(0)
        animations = require_object(self.document.get("animations", {}), "animations")
        self.count(len(animations))
        for name, value in animations.items():
            unique(name, [], "animation name")
            w.string(name)
            self.animation(require_object(value, "animation"))
        return bytes(w.data)

    def skin(self, skin: JSONDocument, default: bool) -> None:
        w = self.writer
        fields(skin, {"name", "attachments", "color"}, "skin")
        if "color" in skin and not self.nonessential:
            reject("Skin color requires nonessential metadata")
        if not default:
            w.string(require_text(skin["name"], "skin name"))
            if self.nonessential:
                w.put(color(skin.get("color", "989898ff")))
            w.put(bytes(5))  # No skin bone/constraint lists in this profile.
        elif "color" in skin:
            reject("Default skin color is not representable")
        attachments = require_object(skin.get("attachments", {}), "skin attachments")
        if default and not attachments:
            reject("Empty default skin is not representable in binary")
        self.count(len(attachments))
        for slot_name, value in attachments.items():
            w.varint(named(slot_name, self.slots, "skin slot"))
            records = require_object(value, "attachments")
            self.count(len(records))
            for key, record in records.items():
                self.ref(key)
                a = require_object(record, "attachment")
                if a.get("type") in ("mesh", "linkedmesh"):
                    self.mesh(a, key)
                    continue
                if a.get("type", "region") != "region":
                    reject("Unsupported attachment type: " + str(a.get("type")))
                fields(
                    a,
                    {
                        "type",
                        "name",
                        "path",
                        "color",
                        "rotation",
                        "x",
                        "y",
                        "scaleX",
                        "scaleY",
                        "width",
                        "height",
                    },
                    "region",
                )
                name = require_text(a.get("name", key), "region name")
                region = RegionAttachment(
                    name,
                    require_text(a.get("path", name), "region path"),
                    color(a.get("color", "ffffffff")),
                    require_number(a.get("rotation", 0), "rotation"),
                    (
                        require_number(a.get("x", 0), "x"),
                        require_number(a.get("y", 0), "y"),
                        require_number(a.get("scaleX", 1), "scaleX"),
                        require_number(a.get("scaleY", 1), "scaleY"),
                        require_number(a.get("width", 0), "width"),
                        require_number(a.get("height", 0), "height"),
                    ),
                )
                w.put(bytes((8 | 16 | 32 | 128,)))
                self.ref(region.name)
                self.ref(region.path)
                w.put(region.rgba)
                w.number(region.rotation)
                for number in region.transform:
                    w.number(number)

    def mesh(self, a: JSONDocument, key: str) -> None:
        w = self.writer
        linked = a.get("type") == "linkedmesh"
        fields(
            a,
            {"type", "name", "path", "color", "width", "height", "parent", "skin", "timelines"}
            if linked
            else {
                "type",
                "name",
                "path",
                "color",
                "width",
                "height",
                "vertices",
                "uvs",
                "triangles",
                "hull",
                "edges",
            },
            "mesh",
        )
        name = require_text(a.get("name", key), "mesh name")
        vertices = require_array(a.get("vertices", []), "vertices")
        uvs = require_array(a.get("uvs", []), "UVs")
        weighted = len(vertices) != len(uvs)
        inherit = a.get("timelines", True)
        if type(inherit) is not bool:
            raise BinaryError(BinaryErrorCode.BOOLEAN, "Invalid linked inheritance")
        w.put(
            bytes(
                (
                    (3 if linked else 2)
                    | 8
                    | 16
                    | 32
                    | (128 if (inherit if linked else weighted) else 0),
                )
            )
        )
        self.ref(name)
        self.ref(a.get("path", name))
        w.put(color(a.get("color", "ffffffff")))
        if linked:
            w.varint(named(a.get("skin", "default"), self.skin_names, "linked skin"))
            self.ref(a.get("parent"))
            if not a.get("parent"):
                raise BinaryError(BinaryErrorCode.REFERENCE, "Missing linked parent")
        else:
            count = len(uvs) // 2
            if len(uvs) % 2 or count < 3:
                raise BinaryError(BinaryErrorCode.GEOMETRY, "Invalid UV count")
            hull = integer(a.get("hull", 0), "hull")
            if hull > count:
                raise BinaryError(BinaryErrorCode.GEOMETRY, "Invalid hull")
            self.count(hull)
            self.count(count)
            if weighted:
                cursor = 0
                for _ in range(count):
                    if cursor >= len(vertices):
                        raise BinaryError(BinaryErrorCode.GEOMETRY, "Truncated weighted vertex")
                    influences = integer(vertices[cursor], "influence count")
                    cursor += 1
                    if not influences or cursor + 4 * influences > len(vertices):
                        raise BinaryError(BinaryErrorCode.GEOMETRY, "Invalid influence count")
                    self.count(influences)
                    total = 0.0
                    for _ in range(influences):
                        bone = integer(vertices[cursor], "influence bone")
                        index(bone, self.bones, "influence bone")
                        w.varint(bone)
                        w.number(vertices[cursor + 1])
                        w.number(vertices[cursor + 2])
                        weight = require_number(vertices[cursor + 3], "weight")
                        if weight < 0 or weight > 1:
                            raise BinaryError(BinaryErrorCode.GEOMETRY, "Invalid weight")
                        total += weight
                        w.number(weight)
                        cursor += 4
                    if abs(total - 1) > 1e-5:
                        raise BinaryError(BinaryErrorCode.GEOMETRY, "Weights must sum to one")
                if cursor != len(vertices):
                    raise BinaryError(BinaryErrorCode.GEOMETRY, "Trailing weighted vertices")
            else:
                for value in vertices:
                    w.number(value)
            for value in uvs:
                w.number(value)
            triangles = require_array(a.get("triangles", []), "triangles")
            if len(triangles) != (len(uvs) - hull - 2) * 3:
                raise BinaryError(
                    BinaryErrorCode.GEOMETRY, "Binary triangle topology count mismatch"
                )
            for value in triangles:
                triangle = integer(value, "triangle index")
                if triangle >= count:
                    raise BinaryError(BinaryErrorCode.GEOMETRY, "Triangle index exceeds vertices")
                w.varint(triangle)
            if self.nonessential:
                edges = require_array(a.get("edges", []), "edges")
                self.count(len(edges))
                for value in edges:
                    w.varint(integer(value, "edge"))
            elif "edges" in a:
                reject("Mesh edges require nonessential export")
        if self.nonessential:
            w.number(a.get("width", 0))
            w.number(a.get("height", 0))
        elif "width" in a or "height" in a:
            reject("Mesh dimensions require nonessential export")

    def animation(self, animation: JSONDocument) -> None:
        fields(animation, {"bones", "slots", "attachments", "drawOrder"}, "animation")
        groups = require_object(animation.get("bones", {}), "bone timelines")
        timelines: list[BoneTimeline] = []
        for bone_name, value in groups.items():
            bone = named(bone_name, self.bones, "timeline bone")
            for name, frames_value in require_object(value, "bone timelines").items():
                try:
                    kind = next(
                        k for k in ANIMATED_42_PROFILE.bone_timelines if k.name.lower() == name
                    )
                except StopIteration:
                    reject(f"Unsupported bone timeline: {name}")
                frames: list[Keyframe] = []
                for item in require_array(frames_value, "frames"):
                    frame = require_object(item, "keyframe")
                    fields(frame, {"time", "curve", *kind.dimensions}, "keyframe")
                    time = frame_time(frame.get("time", 0))
                    if time < 0 or (frames and time <= frames[-1].time):
                        raise BinaryError(BinaryErrorCode.TIMELINE, "Frames must increase strictly")
                    curve = frame.get("curve")
                    parsed: Literal["stepped"] | BezierCurve | None = None
                    if curve == "stepped":
                        parsed = "stepped"
                    elif curve is not None:
                        parsed = BezierCurve.parse(curve, len(kind.dimensions))
                    frames.append(
                        Keyframe(
                            time,
                            tuple(
                                require_number(frame.get(k, kind.default), k)
                                for k in kind.dimensions
                            ),
                            parsed,
                        )
                    )
                if not frames:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Empty timeline")
                if frames[-1].curve is not None:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Terminal key cannot have a curve")
                timelines.append(BoneTimeline(bone, kind, tuple(frames)))
        slot_groups = require_object(animation.get("slots", {}), "slot timelines")
        deform_groups = require_object(animation.get("attachments", {}), "attachment timelines")
        deform_count = sum(
            len(require_object(v, "attachments"))
            for skin in deform_groups.values()
            for v in require_object(skin, "slots").values()
        )
        draw_frames = require_array(animation.get("drawOrder", []), "draw order")
        if not timelines and not slot_groups and not deform_count and not draw_frames:
            reject("Empty animation has no representable motion")
        self.count(
            len(timelines)
            + deform_count
            + int(bool(draw_frames))
            + sum(len(require_object(v, "slot timelines")) for v in slot_groups.values())
        )
        self.slot_timelines(slot_groups)
        self.count(len(groups))
        w = self.writer
        for bone_name in groups:
            bone = named(bone_name, self.bones, "bone")
            selected = [t for t in timelines if t.bone == bone]
            w.varint(bone)
            self.count(len(selected))
            for timeline in selected:
                w.put(bytes((timeline.kind,)))
                self.count(len(timeline.frames))
                self.count(
                    sum(
                        len(timeline.kind.dimensions)
                        for f in timeline.frames
                        if isinstance(f.curve, BezierCurve)
                    )
                )
                for i, keyframe in enumerate(timeline.frames):
                    w.number(keyframe.time)
                    for value in keyframe.values:
                        w.number(value)
                    if i:
                        interpolation = timeline.frames[i - 1].curve
                        w.put(
                            bytes(
                                (
                                    1
                                    if interpolation == "stepped"
                                    else 2
                                    if isinstance(interpolation, BezierCurve)
                                    else 0,
                                )
                            )
                        )
                        if isinstance(interpolation, BezierCurve):
                            for channel in interpolation.channels:
                                for value in channel:
                                    w.number(value)
        w.put(bytes(4))  # IK, transform, path, physics timelines.
        self.deforms(deform_groups)
        self.draw_order(draw_frames)
        w.put(b"\0")  # Events.

    def draw_order(self, frames: list[JSONValue]) -> None:
        self.count(len(frames))
        last = -1.0
        for value in frames:
            frame = require_object(value, "draw order frame")
            fields(frame, {"time", "offsets"}, "draw order")
            time = frame_time(frame.get("time", 0))
            if time < 0 or time <= last:
                raise BinaryError(BinaryErrorCode.TIMELINE, "Frames must increase strictly")
            last = time
            self.writer.number(time)
            offsets = require_array(frame.get("offsets", []), "draw order offsets")
            self.count(len(offsets))
            previous = -1
            destinations: set[int] = set()
            for value in offsets:
                offset = require_object(value, "draw order offset")
                fields(offset, {"slot", "offset"}, "draw offset")
                slot = named(offset.get("slot"), self.slots, "draw slot")
                shift = offset.get("offset", 0)
                if type(shift) is not int:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Non-integer draw offset")
                target = slot + shift
                if slot <= previous or target in destinations or not 0 <= target < len(self.slots):
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Invalid draw order permutation")
                previous = slot
                destinations.add(target)
                self.writer.varint(slot)
                self.writer.varint(shift & 0xFFFFFFFF)

    def deforms(self, groups: JSONDocument) -> None:
        self.count(len(groups))
        w = self.writer
        for skin, slots_value in groups.items():
            w.varint(named(skin, self.skin_names, "deform skin"))
            slots = require_object(slots_value, "deform slots")
            self.count(len(slots))
            for slot, attachments_value in slots.items():
                w.varint(named(slot, self.slots, "deform slot"))
                attachments = require_object(attachments_value, "deform attachments")
                self.count(len(attachments))
                for key, timelines_value in attachments.items():
                    size = deform_size(self.skins, skin, slot, key)
                    timelines = require_object(timelines_value, "attachment timelines")
                    fields(timelines, {"deform"}, "attachment timeline")
                    frames = [
                        require_object(f, "deform frame")
                        for f in require_array(timelines.get("deform", []), "deform frames")
                    ]
                    if not frames:
                        raise BinaryError(BinaryErrorCode.TIMELINE, "Empty deform timeline")
                    self.ref(key)
                    w.put(b"\0")
                    self.count(len(frames))
                    self.count(sum(1 for f in frames if isinstance(f.get("curve"), list)))
                    last = -1.0
                    for i, frame in enumerate(frames):
                        fields(frame, {"time", "vertices", "offset", "curve"}, "deform frame")
                        time = frame_time(frame.get("time", 0))
                        if time < 0 or time <= last:
                            raise BinaryError(
                                BinaryErrorCode.TIMELINE, "Frames must increase strictly"
                            )
                        last = time
                        w.number(time)
                        if i:
                            curve = frames[i - 1].get("curve")
                            w.put(bytes((0 if curve is None else 1 if curve == "stepped" else 2,)))
                            if curve is not None and curve != "stepped":
                                controls = require_array(curve, "deform curve")
                                if len(controls) != 4:
                                    raise BinaryError(
                                        BinaryErrorCode.TIMELINE, "Deform curve needs four controls"
                                    )
                                for value in controls:
                                    w.number(value)
                        vertices = require_array(frame.get("vertices", []), "deform vertices")
                        offset = integer(frame.get("offset", 0), "deform offset")
                        if offset + len(vertices) > size or (not vertices and offset):
                            raise BinaryError(
                                BinaryErrorCode.GEOMETRY, "Deform exceeds vertex count"
                            )
                        self.count(len(vertices))
                        if vertices:
                            w.varint(offset)
                            for value in vertices:
                                w.number(value)
                    if "curve" in frames[-1]:
                        raise BinaryError(
                            BinaryErrorCode.TIMELINE, "Terminal key cannot have a curve"
                        )

    def slot_timelines(self, groups: JSONDocument) -> None:
        self.count(len(groups))
        w = self.writer
        for slot, value in groups.items():
            w.varint(named(slot, self.slots, "timeline slot"))
            timelines = require_object(value, "slot timelines")
            self.count(len(timelines))
            for kind, value in timelines.items():
                if kind not in ANIMATED_42_PROFILE.slot_timelines:
                    reject(f"Unsupported slot timeline: {kind}")
                frames = [require_object(f, "frame") for f in require_array(value, "frames")]
                if not frames:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Empty slot timeline")
                w.put(bytes((0 if kind == "attachment" else 1,)))
                self.count(len(frames))
                if kind == "rgba":
                    self.count(sum(4 for f in frames if isinstance(f.get("curve"), list)))
                last = -1.0
                for i, frame in enumerate(frames):
                    fields(
                        frame,
                        {"time", "name"} if kind == "attachment" else {"time", "color", "curve"},
                        "slot frame",
                    )
                    time = frame_time(frame.get("time", 0))
                    if time < 0 or time <= last:
                        raise BinaryError(BinaryErrorCode.TIMELINE, "Frames must increase strictly")
                    last = time
                    w.number(time)
                    if kind == "attachment":
                        self.ref(frame.get("name"))
                    else:
                        w.put(color(frame.get("color", "ffffffff")))
                        if i:
                            curve = frames[i - 1].get("curve")
                            w.put(bytes((0 if curve is None else 1 if curve == "stepped" else 2,)))
                            if curve is not None and curve != "stepped":
                                controls = require_array(curve, "RGBA curve")
                                if len(controls) != 16:
                                    raise BinaryError(
                                        BinaryErrorCode.TIMELINE, "RGBA curve needs 16 controls"
                                    )
                                for control in controls:
                                    w.number(control)
                if "curve" in frames[-1]:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Terminal key cannot have a curve")


class TailReader:
    def __init__(
        self, reader: BinaryReader, strings: list[str], bones: list[str], nonessential: bool
    ):
        self.reader, self.strings, self.bones = reader, strings, bones
        self.nonessential = nonessential
        self.slots: list[str] = []
        self.skins: list[JSONDocument] = []

    def ref(self) -> str | None:
        value = self.reader.varint()
        if value == 0:
            return None
        return index(value - 1, self.strings, "string table")

    def decode(self) -> JSONDocument:
        r = self.reader
        slots: list[JSONValue] = []
        for _ in range(r.count()):
            name = unique(r.string(), self.slots, "slots name")
            self.slots.append(name)
            slot: JSONDocument = {
                "name": name,
                "bone": index(r.varint(), self.bones, "slot bone"),
                "color": r.take(4).hex(),
            }
            dark = r.take(4)
            if dark != b"\xff" * 4:
                if dark[0] != 0:
                    raise BinaryError(BinaryErrorCode.COLOR, "Invalid RGB dark-color padding")
                slot["dark"] = dark[1:].hex()
            attachment = self.ref()
            if attachment is not None:
                slot["attachment"] = attachment
            slot["blend"] = index(r.varint(), ["normal", "additive", "multiply", "screen"], "blend")
            if self.nonessential:
                slot["visible"] = r.boolean()
            slots.append(slot)
        constraints: list[JSONValue] = []
        constraint_names: list[str] = []
        for _ in range(r.count()):
            name = unique(r.string(), constraint_names, "IK name")
            constraint_names.append(name)
            order, count = r.count(), r.count()
            if not 1 <= count <= 2:
                reject("IK profile requires one or two constrained bones")
            bones: list[JSONValue] = [
                index(r.varint(), self.bones, "IK bone") for _ in range(count)
            ]
            target = index(r.varint(), self.bones, "IK target")
            flags = r.byte()
            constraint: JSONDocument = {
                "name": name,
                "order": order,
                "bones": bones,
                "target": target,
            }
            for bit, field in (
                (1, "skin"),
                (2, "bendPositive"),
                (4, "compress"),
                (8, "stretch"),
                (16, "uniform"),
            ):
                constraint[field] = bool(flags & bit)
            if flags & 1:
                reject("Skin-required IK is outside this profile")
            constraint.pop("skin", None)
            constraint["mix"] = (r.number() if flags & 64 else 1) if flags & 32 else 0
            constraint["softness"] = r.number() if flags & 128 else 0
            constraints.append(constraint)
        for category in ("transform", "path", "physics"):
            if r.count():
                reject(f"Unsupported binary {category} constraints")
        skins: list[JSONValue] = []
        count = r.count()
        if count:
            skins.append(self.skin("default", count))
        names = ["default"] if count else []
        for _ in range(r.count()):
            name = unique(r.string(), names, "skin name")
            names.append(name)
            skin_color = r.take(4).hex() if self.nonessential else None
            for category in ("bones", "ik", "transform", "path", "physics"):
                if r.count():
                    reject(f"Unsupported skin {category}")
            skin = self.skin(name, r.count())
            if skin_color is not None:
                skin["color"] = skin_color
            skins.append(skin)
        for raw_skin in skins:
            skin_record = require_object(raw_skin, "skin")
            for attachments in require_object(skin_record["attachments"], "attachments").values():
                for value in require_object(attachments, "attachments").values():
                    linked_attachment = require_object(value, "attachment")
                    if linked_attachment.get("type") == "linkedmesh":
                        linked_attachment["skin"] = index(
                            integer(linked_attachment["skin"], "skin"), names, "linked skin"
                        )
        if r.count():
            reject("Unsupported binary events")
        self.skins = [require_object(s, "skin") for s in skins]
        for skin_record in self.skins:
            for slot_name, values in require_object(
                skin_record["attachments"], "attachments"
            ).items():
                for key, value in require_object(values, "attachments").items():
                    if require_object(value, "attachment").get("type") == "linkedmesh":
                        deform_size(
                            self.skins, require_text(skin_record["name"], "skin"), slot_name, key
                        )
        animations: JSONDocument = {}
        for _ in range(r.count()):
            name = unique(r.string(), list(animations), "animation name")
            animations[name] = self.animation()
        return {
            "slots": slots,
            "skins": skins,
            "animations": animations,
            **({"ik": constraints} if constraints else {}),
        }

    def skin(self, name: str, count: int) -> JSONDocument:
        r = self.reader
        attachments: JSONDocument = {}
        for _ in range(count):
            slot = index(r.varint(), self.slots, "skin slot")
            if slot in attachments:
                raise BinaryError(BinaryErrorCode.REFERENCE, "Duplicate skin slot")
            records: JSONDocument = {}
            for _ in range(r.count()):
                key = unique(self.ref(), list(records), "attachment key")
                flags = r.byte()
                if flags & 7 in (2, 3) and not flags & 64:
                    records[key] = self.mesh(flags, key)
                    continue
                if flags & 7 or flags & 64:
                    reject("Unsupported attachment type or sequence")
                attachment_name = self.ref() if flags & 8 else key
                if not attachment_name:
                    raise BinaryError(BinaryErrorCode.REFERENCE, "Missing attachment name")
                a: JSONDocument = {"type": "region", "name": attachment_name}
                if flags & 16:
                    path = self.ref()
                    if path is not None:
                        a["path"] = path
                a["color"] = r.take(4).hex() if flags & 32 else "ffffffff"
                a["rotation"] = r.number() if flags & 128 else 0
                for field in ("x", "y", "scaleX", "scaleY", "width", "height"):
                    a[field] = r.number()
                records[key] = a
            attachments[slot] = records
        return {"name": name, "attachments": attachments}

    def mesh(self, flags: int, key: str) -> JSONDocument:
        r = self.reader
        linked = flags & 7 == 3
        name = self.ref() if flags & 8 else key
        if not name:
            raise BinaryError(BinaryErrorCode.REFERENCE, "Missing mesh name")
        a: JSONDocument = {"type": "linkedmesh" if linked else "mesh", "name": name}
        a["path"] = (self.ref() if flags & 16 else name) or name
        a["color"] = r.take(4).hex() if flags & 32 else "ffffffff"
        if linked:
            a["timelines"] = bool(flags & 128)
            # Resolve only after all skins have been read.
            a["skin"] = r.count()
            parent = self.ref()
            if not parent:
                raise BinaryError(BinaryErrorCode.REFERENCE, "Missing linked parent")
            a["parent"] = parent
        else:
            hull, count = r.count(), r.count()
            if count < 3 or hull > count:
                raise BinaryError(BinaryErrorCode.GEOMETRY, "Invalid mesh vertex/hull count")
            vertices: list[JSONValue] = []
            for _ in range(count):
                if flags & 128:
                    influences = r.count()
                    if not influences:
                        raise BinaryError(BinaryErrorCode.GEOMETRY, "Empty weighted vertex")
                    vertices.append(influences)
                    total = 0.0
                    for _ in range(influences):
                        bone = r.varint()
                        index(bone, self.bones, "weighted bone")
                        x, y, weight = r.number(), r.number(), r.number()
                        if weight < 0 or weight > 1:
                            raise BinaryError(BinaryErrorCode.GEOMETRY, "Invalid weight")
                        total += weight
                        vertices.extend((bone, x, y, weight))
                    if abs(total - 1) > 1e-5:
                        raise BinaryError(BinaryErrorCode.GEOMETRY, "Weights must sum to one")
                else:
                    vertices.extend((r.number(), r.number()))
            a["vertices"] = vertices
            a["uvs"] = [r.number() for _ in range(count * 2)]
            triangle_count = (count * 2 - hull - 2) * 3
            if triangle_count > r.limits.max_count:
                raise BinaryError(BinaryErrorCode.COUNT_LIMIT, "Triangle limit")
            triangles: list[JSONValue] = []
            for _ in range(triangle_count):
                value = r.varint()
                if value >= count:
                    raise BinaryError(BinaryErrorCode.GEOMETRY, "Invalid triangle index")
                triangles.append(value)
            a["triangles"], a["hull"] = triangles, hull
            if self.nonessential:
                a["edges"] = [r.varint() for _ in range(r.count())]
        if self.nonessential:
            a["width"], a["height"] = r.number(), r.number()
        return a

    def animation(self) -> JSONDocument:
        r = self.reader
        declared = r.count()
        slots, actual = self.slot_timelines()
        bones: JSONDocument = {}
        for _ in range(r.count()):
            bone = index(r.varint(), self.bones, "timeline bone")
            if bone in bones:
                raise BinaryError(BinaryErrorCode.TIMELINE, "Duplicate timeline bone")
            timelines: JSONDocument = {}
            for _ in range(r.count()):
                try:
                    kind = BoneTimelineKind(r.byte())
                except ValueError as exc:
                    raise BinaryError(
                        BinaryErrorCode.FEATURE_UNSUPPORTED, "Unsupported bone timeline"
                    ) from exc
                key = kind.name.lower()
                if key in timelines:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Duplicate timeline")
                count = r.count()
                if not count:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Empty timeline")
                beziers = r.count()
                observed = 0
                frames: list[JSONValue] = []
                previous: JSONDocument | None = None
                last_time = -1.0
                for _ in range(count):
                    time = r.number()
                    if time < 0 or time <= last_time:
                        raise BinaryError(BinaryErrorCode.TIMELINE, "Frames must increase strictly")
                    last_time = time
                    frame: JSONDocument = {"time": time}
                    for field in kind.dimensions:
                        frame[field] = r.number()
                    if previous is not None:
                        curve = r.byte()
                        if curve == 1:
                            previous["curve"] = "stepped"
                        elif curve == 2:
                            previous["curve"] = [
                                r.number() for _ in range(len(kind.dimensions) * 4)
                            ]
                            observed += len(kind.dimensions)
                        elif curve != 0:
                            raise BinaryError(BinaryErrorCode.TIMELINE, "Invalid curve type")
                    frames.append(frame)
                    previous = frame
                if observed != beziers:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Bezier count mismatch")
                timelines[key] = frames
                actual += 1
            bones[bone] = timelines
        for category in ("ik", "transform", "path", "physics"):
            if r.count():
                reject(f"Unsupported {category} timelines")
        attachments, deform_count = self.deforms()
        actual += deform_count
        draw_frames = self.draw_order()
        actual += int(bool(draw_frames))
        if r.count():
            reject("Unsupported events timelines")
        if declared != actual:
            raise BinaryError(BinaryErrorCode.TIMELINE, "Timeline count mismatch")
        return {
            "bones": bones,
            **({"slots": slots} if slots else {}),
            **({"attachments": attachments} if attachments else {}),
            **({"drawOrder": draw_frames} if draw_frames else {}),
        }

    def slot_timelines(self) -> tuple[JSONDocument, int]:
        r = self.reader
        groups: JSONDocument = {}
        actual = 0
        for _ in range(r.count()):
            slot = index(r.varint(), self.slots, "timeline slot")
            unique(slot, list(groups), "timeline slot")
            timelines: JSONDocument = {}
            for _ in range(r.count()):
                kind = r.byte()
                if kind not in (0, 1):
                    reject("Unsupported slot timeline")
                key = "attachment" if kind == 0 else "rgba"
                unique(key, list(timelines), "slot timeline")
                count = r.count()
                if not count:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Empty timeline")
                beziers = r.count() if kind else 0
                observed = 0
                frames: list[JSONValue] = []
                previous: JSONDocument | None = None
                last = -1.0
                for _ in range(count):
                    time = r.number()
                    if time < 0 or time <= last:
                        raise BinaryError(BinaryErrorCode.TIMELINE, "Frames must increase strictly")
                    last = time
                    frame: JSONDocument = {"time": time}
                    if kind == 0:
                        frame["name"] = self.ref()
                    else:
                        frame["color"] = r.take(4).hex()
                        if previous is not None:
                            curve = r.byte()
                            if curve == 1:
                                previous["curve"] = "stepped"
                            elif curve == 2:
                                previous["curve"] = [r.number() for _ in range(16)]
                                observed += 4
                            elif curve != 0:
                                raise BinaryError(BinaryErrorCode.TIMELINE, "Invalid curve")
                    frames.append(frame)
                    previous = frame
                if observed != beziers:
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Bezier count mismatch")
                timelines[key] = frames
                actual += 1
            groups[slot] = timelines
        return groups, actual

    def deforms(self) -> tuple[JSONDocument, int]:
        r = self.reader
        groups: JSONDocument = {}
        actual = 0
        names = [require_text(s["name"], "skin") for s in self.skins]
        for _ in range(r.count()):
            skin = unique(index(r.varint(), names, "deform skin"), list(groups), "deform skin")
            slots: JSONDocument = {}
            for _ in range(r.count()):
                slot = unique(
                    index(r.varint(), self.slots, "deform slot"), list(slots), "deform slot"
                )
                attachments: JSONDocument = {}
                for _ in range(r.count()):
                    key = unique(self.ref(), list(attachments), "deform attachment")
                    size = deform_size(self.skins, skin, slot, key)
                    if r.byte() != 0:
                        reject("Unsupported attachment timeline")
                    count, beziers = r.count(), r.count()
                    if not count:
                        raise BinaryError(BinaryErrorCode.TIMELINE, "Empty deform timeline")
                    frames: list[JSONValue] = []
                    previous: JSONDocument | None = None
                    last = -1.0
                    observed = 0
                    for _ in range(count):
                        time = r.number()
                        if time < 0 or time <= last:
                            raise BinaryError(
                                BinaryErrorCode.TIMELINE, "Frames must increase strictly"
                            )
                        last = time
                        if previous is not None:
                            curve = r.byte()
                            if curve == 1:
                                previous["curve"] = "stepped"
                            elif curve == 2:
                                previous["curve"] = [r.number() for _ in range(4)]
                                observed += 1
                            elif curve != 0:
                                raise BinaryError(BinaryErrorCode.TIMELINE, "Invalid curve")
                        frame: JSONDocument = {"time": time}
                        length = r.count()
                        if length:
                            offset = r.count()
                            if offset + length > size:
                                raise BinaryError(
                                    BinaryErrorCode.GEOMETRY, "Deform exceeds vertex count"
                                )
                            frame["offset"] = offset
                            frame["vertices"] = [r.number() for _ in range(length)]
                        frames.append(frame)
                        previous = frame
                    if beziers != observed:
                        raise BinaryError(BinaryErrorCode.TIMELINE, "Bezier count mismatch")
                    attachments[key] = {"deform": frames}
                    actual += 1
                slots[slot] = attachments
            groups[skin] = slots
        return groups, actual

    def draw_order(self) -> list[JSONValue]:
        r = self.reader
        frames: list[JSONValue] = []
        last = -1.0
        for _ in range(r.count()):
            time = r.number()
            if time < 0 or time <= last:
                raise BinaryError(BinaryErrorCode.TIMELINE, "Frames must increase strictly")
            last = time
            offsets: list[JSONValue] = []
            previous = -1
            destinations: set[int] = set()
            for _ in range(r.count()):
                slot = r.varint()
                name = index(slot, self.slots, "draw slot")
                shift = r.varint()
                if shift >= 0x80000000:
                    shift -= 0x100000000
                target = slot + shift
                if slot <= previous or target in destinations or not 0 <= target < len(self.slots):
                    raise BinaryError(BinaryErrorCode.TIMELINE, "Invalid draw order permutation")
                previous = slot
                destinations.add(target)
                offsets.append({"slot": name, "offset": shift})
            frames.append({"time": time, "offsets": offsets})
        return frames
