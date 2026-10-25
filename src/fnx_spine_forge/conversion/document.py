"""Checked access to admitted mutable JSON records."""

from __future__ import annotations

from math import isfinite

from ..json_types import JSONDocument, JSONValue, is_document
from .errors import MigrationError


def require_object(value: JSONValue, context: str) -> JSONDocument:
    if not is_document(value):
        raise MigrationError(f"{context} must be an object")
    return value


def require_array(value: JSONValue, context: str) -> list[JSONValue]:
    if not isinstance(value, list):
        raise MigrationError(f"{context} must be an array")
    return value


def require_text(value: JSONValue, context: str) -> str:
    if not isinstance(value, str):
        raise MigrationError(f"{context} must be a string")
    return value


def require_records(value: JSONValue, context: str) -> list[JSONDocument]:
    if not isinstance(value, list) or any(not is_document(item) for item in value):
        raise MigrationError(f"{context} must be an array of objects")
    return [require_object(item, context) for item in value]


def require_number(value: JSONValue, context: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MigrationError(f"{context} must be numeric")
    try:
        number = float(value)
    except OverflowError as exc:
        raise MigrationError(f"{context} exceeds finite numeric range") from exc
    if not isfinite(number):
        raise MigrationError(f"{context} must be finite")
    return number
