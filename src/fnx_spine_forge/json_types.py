"""Recursive JSON value types used at conversion serialization boundaries."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Never, TypeAlias, TypeGuard

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = (
    JSONScalar | list["JSONValue"] | tuple["JSONValue", ...] | Mapping[str, "JSONValue"]
)
JSONObject: TypeAlias = Mapping[str, JSONValue]
JSONDocument: TypeAlias = dict[str, JSONValue]


def is_document(value: JSONValue) -> TypeGuard[JSONDocument]:
    """Narrow an already admitted JSON value without erasing its value type."""
    return isinstance(value, dict)


def _object_dict(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


def _object_list(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def require_json_object(value: object, context: str) -> JSONDocument:
    try:
        return _checked_object(value, context)
    except RecursionError as exc:
        raise ValueError(f"{context} exceeds supported JSON nesting or contains a cycle") from exc


def _checked_object(value: object, context: str) -> JSONDocument:
    """Reconstruct checked JSON; arbitrary Python containers never escape admission."""
    if not _object_dict(value):
        raise ValueError(f"{context} must be a JSON object with string keys")
    result: JSONDocument = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{context} contains a non-string object key")
        result[key] = _json_value(item, f"{context}.{key}")
    return result


def _json_value(value: object, context: str) -> JSONValue:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{context} contains a non-finite number")
        return value
    if _object_list(value):
        return [_json_value(item, f"{context}[{index}]") for index, item in enumerate(value)]
    if _object_dict(value):
        return require_json_object(value, context)
    raise ValueError(f"{context} contains unsupported value type {type(value).__name__}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON object field: {key!r}")
        result[key] = value
    return result


def _reject_constant(value: str) -> Never:
    raise ValueError(f"Non-finite JSON constant: {value}")


def decode_json_object(payload: bytes | str, context: str) -> JSONDocument:
    try:
        decoded: object = json.loads(
            payload.decode("utf-8-sig") if isinstance(payload, bytes) else payload,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
        return require_json_object(decoded, context)
    except RecursionError as exc:
        raise ValueError(f"{context} exceeds supported JSON nesting") from exc


def encode_json(document: JSONDocument) -> bytes:
    """Canonical UTF-8 report/document encoding, with no Python object coercion."""
    return (
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
