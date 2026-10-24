"""Recursive JSON value types used at conversion serialization boundaries."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TypeAlias, cast

JSONScalar: TypeAlias = str | int | float | bool | None
JSONValue: TypeAlias = (
    JSONScalar
    | list["JSONValue"]
    | tuple["JSONValue", ...]
    | Mapping[str, "JSONValue"]
)
JSONObject: TypeAlias = Mapping[str, JSONValue]
JSONDocument: TypeAlias = dict[str, JSONValue]


def require_json_object(value: object, context: str) -> JSONDocument:
    """Validate and narrow data parsed by the standard JSON decoder."""
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError(f"{context} must be a JSON object with string keys")
    _validate_json_value(value, context)
    return cast(JSONDocument, value)


def _validate_json_value(value: object, context: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            raise ValueError(f"{context} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, f"{context}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{context} contains a non-string object key")
            _validate_json_value(item, f"{context}.{key}")
        return
    raise ValueError(f"{context} contains unsupported value type {type(value).__name__}")
