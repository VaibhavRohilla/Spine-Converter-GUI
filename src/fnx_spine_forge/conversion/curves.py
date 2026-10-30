"""Channel-aware curve conversion and numerical comparison."""

from __future__ import annotations

from collections.abc import Mapping

from ..json_types import JSONDocument, JSONValue
from .document import require_number, require_object
from .errors import MigrationError


def _curve_controls(
    frame: Mapping[str, JSONValue], context: str
) -> tuple[float, float, float, float] | None:
    curve = frame.get("curve")
    if curve is None:
        return None
    if curve == "stepped":
        return None
    if isinstance(curve, str):
        raise MigrationError(f"{context}: malformed legacy curve marker {curve!r}")
    cx1 = require_number(curve, f"{context}.curve")
    c2 = require_number(frame.get("c2", 0), f"{context}.c2")
    c3 = require_number(frame.get("c3", 1), f"{context}.c3")
    c4 = require_number(frame.get("c4", 1), f"{context}.c4")
    controls = (cx1, c2, c3, c4)
    if any(not 0 <= value <= 1 for value in controls):
        raise MigrationError(f"{context}: normalized Bézier controls must be in [0, 1]")
    return controls


def _target_curve(
    controls: tuple[float, float, float, float],
    start: float,
    end: float,
    time0: float,
    time1: float,
) -> list[float]:
    cx1, cy1, cx2, cy2 = controls
    delta = end - start
    duration = time1 - time0
    return [
        time0 + cx1 * duration,
        start + cy1 * delta,
        time0 + cx2 * duration,
        start + cy2 * delta,
    ]


def _cubic(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    u = 1 - t
    return u * u * u * p0 + 3 * u * u * t * p1 + 3 * u * t * t * p2 + t * t * t * p3


def _curve_error(
    controls: tuple[float, float, float, float],
    start: float,
    end: float,
    time0: float,
    time1: float,
) -> float:
    """Numerically compare normalized 3.8 and absolute 4.2 curves at fixed times."""
    cx1, cy1, cx2, cy2 = controls
    delta = end - start
    maximum = 0.0
    for sample in range(257):
        x = sample / 256
        low, high = 0.0, 1.0
        for _ in range(48):
            middle = (low + high) / 2
            if _cubic(0, cx1, cx2, 1, middle) < x:
                low = middle
            else:
                high = middle
        t = (low + high) / 2
        old_value = _cubic(start, start + cy1 * delta, start + cy2 * delta, end, t)
        target = _target_curve(controls, start, end, time0, time1)
        normalized_target_x1 = (target[0] - time0) / (time1 - time0)
        normalized_target_x2 = (target[2] - time0) / (time1 - time0)
        target_t_low, target_t_high = 0.0, 1.0
        for _ in range(48):
            target_t = (target_t_low + target_t_high) / 2
            if _cubic(0, normalized_target_x1, normalized_target_x2, 1, target_t) < x:
                target_t_low = target_t
            else:
                target_t_high = target_t
        target_value = _cubic(start, target[1], target[3], end, (target_t_low + target_t_high) / 2)
        maximum = max(maximum, abs(old_value - target_value))
    return maximum


def _curve_fields(
    frames: list[JSONDocument],
    channels: tuple[tuple[str, float], ...],
    context: str,
) -> tuple[int, float]:
    """Convert one 3.8 shared normalized curve to 4.2 per-channel curves."""
    count = 0
    maximum_error = 0.0
    for index, frame in enumerate(frames):
        controls = _curve_controls(frame, f"{context}[{index}]")
        for key in ("c2", "c3", "c4"):
            frame.pop(key, None)
        if controls is None:
            continue
        if index + 1 >= len(frames):
            raise MigrationError(
                f"{context}[{index}]: final keyframe cannot own an interpolation curve"
            )
        curves: list[float] = []
        for field, default in channels:
            start = require_number(frame.get(field, default), f"{context}[{index}].{field}")
            end = require_number(
                frames[index + 1].get(field, default), f"{context}[{index + 1}].{field}"
            )
            time0 = require_number(frame.get("time", 0), f"{context}[{index}].time")
            time1 = require_number(frames[index + 1].get("time", 0), f"{context}[{index + 1}].time")
            if time1 <= time0:
                raise MigrationError(f"{context}[{index}]: Bézier segment times must increase")
            curves.extend(_target_curve(controls, start, end, time0, time1))
            maximum_error = max(maximum_error, _curve_error(controls, start, end, time0, time1))
        frame["curve"] = list[JSONValue](curves)
        count += len(channels)
    return count, maximum_error


def _color_channels(
    frames: list[JSONDocument], fields: tuple[str, ...], context: str
) -> tuple[int, float]:
    # 3.8 stores one normalized curve for all color channels. Spine 4.2 stores
    # absolute per-channel curves; colors are normalized byte components.
    if not frames:
        return 0, 0.0
    components: dict[str, tuple[tuple[float, ...], ...]] = {}
    for field in fields:
        first = frames[0].get(field)
        if not isinstance(first, str) or len(first) not in (6, 8):
            raise MigrationError(f"{context}: {field} must be a 6- or 8-digit hex color")
        decoded: list[tuple[float, ...]] = []
        for frame in frames:
            color = frame.get(field)
            if not isinstance(color, str) or len(color) != len(first):
                raise MigrationError(f"{context}: inconsistent color representation in {field}")
            try:
                decoded.append(
                    tuple(int(color[i : i + 2], 16) / 255 for i in range(0, len(color), 2))
                )
            except ValueError as exc:
                raise MigrationError(f"{context}: invalid {field} color {color!r}") from exc
        components[field] = tuple(decoded)
    count = 0
    maximum_error = 0.0
    for index, frame in enumerate(frames):
        controls = _curve_controls(frame, f"{context}[{index}]")
        for key in ("c2", "c3", "c4"):
            frame.pop(key, None)
        if controls is None:
            continue
        if index + 1 >= len(frames):
            raise MigrationError(
                f"{context}[{index}]: final keyframe cannot own an interpolation curve"
            )
        curves: list[float] = []
        for field in fields:
            current = components[field][index]
            following = components[field][index + 1]
            for start_value, end_value in zip(current, following, strict=True):
                start = require_number(start_value, context)
                end = require_number(end_value, context)
                time0 = require_number(frame.get("time", 0), f"{context}[{index}].time")
                time1 = require_number(
                    frames[index + 1].get("time", 0), f"{context}[{index + 1}].time"
                )
                if time1 <= time0:
                    raise MigrationError(f"{context}[{index}]: Bézier segment times must increase")
                curves.extend(_target_curve(controls, start, end, time0, time1))
                maximum_error = max(maximum_error, _curve_error(controls, start, end, time0, time1))
        frame["curve"] = list[JSONValue](curves)
        count += len(curves) // 4
    return count, maximum_error


def _curve_statistics(document: JSONDocument) -> tuple[int, int]:
    segments = 0
    frames = 0
    stack: list[JSONValue] = [
        require_object(document.get("animations", {}), "migrate_42_to_43 JSON field")
    ]
    while stack:
        value = stack.pop()
        if isinstance(value, Mapping):
            curve = value.get("curve")
            if isinstance(curve, list):
                if len(curve) % 4 or any(
                    isinstance(item, bool) or not isinstance(item, (int, float)) for item in curve
                ):
                    raise MigrationError("Malformed Spine 4.2 Bézier control array")
                segments += len(curve) // 4
                frames += 1
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
    return segments, frames
