"""Explicit immutable contracts for the implemented binary wire profile.

Wire tags are format constants, not runtime configuration or guessed values.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, StrEnum
from typing import Literal


class BoneTimelineKind(IntEnum):
    ROTATE = 0
    TRANSLATE = 1
    TRANSLATEX = 2
    TRANSLATEY = 3
    SCALE = 4
    SCALEX = 5
    SCALEY = 6
    SHEAR = 7
    SHEARX = 8
    SHEARY = 9

    @property
    def dimensions(self) -> tuple[str, ...]:
        return ("x", "y") if self in (self.TRANSLATE, self.SCALE, self.SHEAR) else ("value",)

    @property
    def default(self) -> float:
        return 1.0 if self in (self.SCALE, self.SCALEX, self.SCALEY) else 0.0


class AttachmentKind(StrEnum):
    REGION = "region"
    MESH = "mesh"
    LINKED_MESH = "linkedmesh"


class SlotTimelineKind(StrEnum):
    ATTACHMENT = "attachment"
    RGBA = "rgba"


@dataclass(frozen=True, slots=True)
class BinaryProfile:
    attachments: tuple[AttachmentKind, ...]
    bone_timelines: tuple[BoneTimelineKind, ...]
    slot_timelines: tuple[SlotTimelineKind, ...]
    attachment_timelines: tuple[Literal["deform"], ...]
    global_timelines: tuple[Literal["drawOrder"], ...]
    constraints: tuple[Literal["one_or_two_bone_ik_setup_without_skin_requirement"], ...]
    interpolation: tuple[Literal["linear", "stepped", "bezier_per_channel"], ...]
    restrictions: tuple[str, ...]


ANIMATED_42_PROFILE = BinaryProfile(
    attachments=tuple(AttachmentKind),
    bone_timelines=tuple(BoneTimelineKind),
    slot_timelines=tuple(SlotTimelineKind),
    attachment_timelines=("deform",),
    global_timelines=("drawOrder",),
    constraints=("one_or_two_bone_ik_setup_without_skin_requirement",),
    interpolation=("linear", "stepped", "bezier_per_channel"),
    restrictions=(
        "exact registered export version only; runtime package version is separate",
        "no composed migration route promotion; B2 qualification unchanged",
        "no events, constraint timelines, physics, paths or sequences",
        "nonessential fields require explicit metadata; no hash truncation",
        "B4 production binary admission remains approved-fixture-only",
    ),
)
