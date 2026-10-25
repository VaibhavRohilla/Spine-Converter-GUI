"""Independent, test-only semantic reader for the B2 migration corpus.

The reader deliberately does not call production migration or semantic code.  It
normalizes the schema differences which are visible in official Spine JSON
readers (legacy object-map skins, named skins, and draw-order spellings).
Fixtures produced here are schema-derived synthetic inputs, not editor exports.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any


def feature_fixture(version: str) -> dict[str, Any]:
    legacy = version.startswith(("3.5.", "3.6.", "3.7."))
    spine_4x = version.startswith("4.")
    angle = "value" if spine_4x else "angle"
    skin = (
        {
            "default": {
                "body": {
                    "badge": {
                        "name": "badge",
                        "path": "badge",
                        "x": 2,
                        "y": 3,
                        "width": 16,
                        "height": 12,
                        "rotation": 7,
                    }
                }
            }
        }
        if legacy
        else [
            {
                "name": "default",
                "attachments": {
                    "body": {
                        "badge": {
                            "name": "badge",
                            "path": "badge",
                            "x": 2,
                            "y": 3,
                            "width": 16,
                            "height": 12,
                            "rotation": 7,
                        }
                    }
                },
            }
        ]
    )
    frames = (
        [
            {"time": 0, angle: 350, "curve": 0.2, "c2": 0.3, "c3": 0.7, "c4": 0.8},
            {"time": 1, angle: 370},
        ]
        if not spine_4x
        else [{"time": 0, angle: 350, "curve": [0.2, 350.0, 0.7, 370.0]}, {"time": 1, angle: 370}]
    )
    color_key = "rgba" if spine_4x else "color"
    color_frames = [
        {"time": 0, color_key: "ffffffff", "curve": "stepped"},
        {"time": 0.5, color_key: "ff8000ff"},
    ]
    animation: dict[str, Any] = {
        "bones": {
            "root": {
                "rotate": frames,
                "translate": [{"time": 0, "x": 0, "y": 0}, {"time": 1, "x": 12, "y": -4}],
            }
        },
        "slots": {
            "body": {
                color_key: color_frames,
                "attachment": [{"time": 0, "name": "badge"}, {"time": 0.75, "name": None}],
            }
        },
        "events": [{"time": 0.4, "name": "impact", "int": 2, "string": "stone", "float": 0.25}],
        ("drawOrder" if spine_4x else "draworder"): [
            {"time": 0.6, "offsets": [{"slot": "body", "offset": 1}]}
        ],
    }
    return {
        "skeleton": {"spine": version, "width": 64, "height": 64},
        "bones": [
            {
                "name": "root",
                "x": 1,
                "y": 2,
                "rotation": 5,
                "scaleX": 1.2,
                "scaleY": 0.8,
                "shearX": 3,
                "shearY": -2,
            },
            {"name": "child", "parent": "root", "x": 4, "y": 6},
        ],
        "slots": [
            {"name": "body", "bone": "child", "attachment": "badge", "color": "ffffffff"},
            {"name": "accent", "bone": "root", "color": "ffffffff"},
        ],
        "events": {"impact": {"int": 0, "string": "", "float": 0.0}},
        "skins": skin,
        "animations": {"motion": animation},
    }


def restricted_fixture(version: str, target: str) -> dict[str, Any]:
    """Keep only admitted common semantics when a downgrade lacks color mapping."""
    document = feature_fixture(version)
    if target in {"3.8.99", "3.6.53", "3.5.51"} and version.startswith("4."):
        document["animations"]["motion"]["slots"]["body"].pop("rgba", None)
        rotate = document["animations"]["motion"]["bones"]["root"]["rotate"][0]
        rotate.pop("curve", None)
    return document


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("expected JSON object")
    return value


def semantic_view(document: Mapping[str, Any]) -> dict[str, Any]:
    """Return normalized setup, attachment, event and timeline meanings."""
    bones = tuple(
        (
            b["name"],
            b.get("parent"),
            *(
                float(b.get(k, d))
                for k, d in (
                    ("x", 0),
                    ("y", 0),
                    ("rotation", 0),
                    ("scaleX", 1),
                    ("scaleY", 1),
                    ("shearX", 0),
                    ("shearY", 0),
                )
            ),
        )
        for b in (_mapping(x) for x in document.get("bones", []))
    )
    slots = tuple(
        (s["name"], s["bone"], s.get("attachment"), s.get("color"))
        for s in (_mapping(x) for x in document.get("slots", []))
    )
    raw_skins = document.get("skins", [])
    if isinstance(raw_skins, Mapping):
        skin_items = tuple((str(name), _mapping(items)) for name, items in raw_skins.items())
    else:
        skin_items = tuple(
            (str(_mapping(s)["name"]), _mapping(_mapping(s).get("attachments", {})))
            for s in raw_skins
        )
    attachments: list[tuple[str, str, str, str, float, float, float, float, float]] = []
    for skin_name, slots_map in skin_items:
        for slot_name, attachment_map in slots_map.items():
            for attachment_name, value in _mapping(attachment_map).items():
                row = _mapping(value)
                attachments.append(
                    (
                        skin_name,
                        slot_name,
                        attachment_name,
                        str(row.get("type", "region")),
                        float(row.get("x", 0)),
                        float(row.get("y", 0)),
                        float(row.get("rotation", 0)),
                        float(row.get("width", 0)),
                        float(row.get("height", 0)),
                    )
                )
    animation = _mapping(_mapping(document.get("animations", {})).get("motion", {}))
    key_times: list[float] = []

    def collect_times(value: object) -> None:
        if isinstance(value, Mapping):
            key_time = value.get("time")
            if isinstance(key_time, (int, float)) and not isinstance(key_time, bool):
                key_times.append(float(key_time))
            for child in value.values():
                collect_times(child)
        elif isinstance(value, list):
            for child in value:
                collect_times(child)

    collect_times(animation)
    slot_animation = _mapping(animation.get("slots", {}))
    slot_timelines = _mapping(slot_animation.get("body", {}))
    color_timeline = tuple(
        _mapping(x) for x in slot_timelines.get("color", slot_timelines.get("rgba", []))
    )
    attachment_timeline = tuple(_mapping(x) for x in slot_timelines.get("attachment", []))
    return {
        "bones": bones,
        "slots": slots,
        "skins": tuple(n for n, _ in skin_items),
        "attachments": tuple(sorted(attachments)),
        "rotation": tuple(
            _mapping(x)
            for x in _mapping(_mapping(animation.get("bones", {})).get("root", {})).get(
                "rotate", []
            )
        ),
        "color": color_timeline,
        "attachment_timeline": attachment_timeline,
        "translation": tuple(
            _mapping(x)
            for x in _mapping(_mapping(animation.get("bones", {})).get("root", {})).get(
                "translate", []
            )
        ),
        "events": tuple(_mapping(x) for x in animation.get("events", [])),
        "event_definitions": _mapping(document.get("events", {})),
        "duration": max(key_times, default=0.0),
        "draw_order": tuple(
            _mapping(x) for x in animation.get("draworder", animation.get("drawOrder", []))
        ),
    }


def _cubic(p1: float, p2: float, t: float) -> float:
    q = 1.0 - t
    return 3 * q * q * t * p1 + 3 * q * t * t * p2 + t**3


def evaluate(
    frames: tuple[Mapping[str, Any], ...], time: float, fields: tuple[str, ...]
) -> tuple[float, ...]:
    """Independent playback evaluator; Bezier time is inverted by bisection."""
    if not frames:
        return tuple(0.0 for _ in fields)
    times = tuple(float(frame.get("time", 0)) for frame in frames)
    if any(not math.isfinite(value) for value in times) or any(
        right <= left for left, right in zip(times, times[1:])
    ):
        raise ValueError("keyframe times must be strictly increasing and finite")
    before = 0
    while before + 1 < len(frames) and float(frames[before + 1].get("time", 0)) <= time:
        before += 1
    if before + 1 == len(frames):
        return tuple(float(frames[before].get(k, frames[before].get("value", 0))) for k in fields)
    a, b = frames[before], frames[before + 1]
    t0, t1 = float(a.get("time", 0)), float(b.get("time", 0))
    if t1 <= t0:
        raise ValueError("keyframe times must be strictly increasing")
    p = min(1.0, max(0.0, (time - t0) / (t1 - t0)))
    curve = a.get("curve")
    if curve == "stepped":
        p = 0.0
    elif isinstance(curve, list):
        if len(curve) != 4 or not all(math.isfinite(float(v)) for v in curve):
            raise ValueError("invalid Bezier curve")
        x1, y1, x2, y2 = (float(v) for v in curve)
        # 4.2+ stores absolute time/value controls; older versions use fractions.
        absolute = x1 > 1 or x2 > 1 or abs(y1) > 1 or abs(y2) > 1
        if absolute:
            x1, x2 = (x1 - t0) / (t1 - t0), (x2 - t0) / (t1 - t0)
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if _cubic(x1, x2, mid) < p:
                lo = mid
            else:
                hi = mid
        parameter = (lo + hi) / 2
        if absolute:
            value = (
                (1 - parameter) ** 3 * float(a.get(fields[0], a.get("value", 0)))
                + 3 * (1 - parameter) ** 2 * parameter * y1
                + 3 * (1 - parameter) * parameter**2 * y2
                + parameter**3 * float(b.get(fields[0], b.get("value", 0)))
            )
            return (value,)
        p = _cubic(y1, y2, parameter)
    elif isinstance(curve, (float, int)) and not isinstance(curve, bool):
        x1, y1, x2, y2 = (
            float(curve),
            float(a.get("c2", 0)),
            float(a.get("c3", 1)),
            float(a.get("c4", 1)),
        )
        lo, hi = 0.0, 1.0
        for _ in range(60):
            mid = (lo + hi) / 2
            if _cubic(x1, x2, mid) < p:
                lo = mid
            else:
                hi = mid
        p = _cubic(y1, y2, (lo + hi) / 2)
    return tuple(
        float(a.get(k, a.get("value", 0)))
        + (float(b.get(k, b.get("value", 0))) - float(a.get(k, a.get("value", 0)))) * p
        for k in fields
    )
