"""Safe, bounded wire encoding for named RIX application messages."""

from __future__ import annotations

import base64
import json
import math
import struct
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final


_MAGIC: Final = b"RIXM"
_VERSION: Final = 1
_HEADER: Final = struct.Struct("<4sBHI")
_MAX_NAME_BYTES: Final = 128
_MAX_DEPTH: Final = 16
_MAX_ITEMS: Final = 4096
_BYTES_TAG: Final = "__rix_bytes__"


@dataclass(frozen=True, slots=True)
class Message:
    """One validated application message decoded from the network."""

    name: str
    fields: dict[str, object]


_SCHEMA_TYPES: Final = (type(None), bool, int, float, str, bytes, list, dict)


@dataclass(frozen=True, slots=True)
class MessageSchema:
    """Exact bounded field declaration for one optional named message schema."""

    name: str
    fields: tuple[tuple[str, tuple[type, ...]], ...]
    allow_extra: bool = False

    @classmethod
    def create(
        cls,
        name: str,
        declarations: Mapping[str, type | tuple[type, ...]],
        *,
        allow_extra: bool = False,
    ) -> MessageSchema:
        _name(name)
        if not isinstance(allow_extra, bool):
            raise TypeError("allow_extra must be a bool")
        normalized: list[tuple[str, tuple[type, ...]]] = []
        for field_name, declaration in declarations.items():
            if not isinstance(field_name, str) or not field_name:
                raise ValueError("schema field names must be non-empty strings")
            choices = declaration if isinstance(declaration, tuple) else (declaration,)
            if not choices or any(choice not in _SCHEMA_TYPES for choice in choices):
                raise TypeError(
                    "schema field types must be NoneType, bool, int, float, str, "
                    "bytes, list, or dict"
                )
            normalized.append((field_name, choices))
        return cls(name, tuple(normalized), allow_extra)

    def validate(self, values: Mapping[str, object]) -> None:
        if not isinstance(values, Mapping):
            raise TypeError("message fields must be a mapping")
        declared = dict(self.fields)
        missing = declared.keys() - values.keys()
        extra = values.keys() - declared.keys()
        if missing:
            raise ValueError(
                f"message {self.name!r} is missing fields: {', '.join(sorted(missing))}"
            )
        if extra and not self.allow_extra:
            raise ValueError(
                f"message {self.name!r} has undeclared fields: {', '.join(sorted(extra))}"
            )
        for field_name, choices in self.fields:
            value = values[field_name]
            valid = any(
                type(value) is choice
                or (choice is bytes and isinstance(value, bytes))
                for choice in choices
            )
            if not valid:
                expected = " or ".join(choice.__name__ for choice in choices)
                raise TypeError(
                    f"message {self.name!r} field {field_name!r} must be {expected}"
                )


def _name(value: str) -> tuple[str, bytes]:
    if not isinstance(value, str):
        raise TypeError("message name must be a string")
    if not value or any(ord(character) < 0x20 for character in value):
        raise ValueError("message name must be non-empty and contain no controls")
    encoded = value.encode("utf-8")
    if len(encoded) > _MAX_NAME_BYTES:
        raise ValueError(f"message name must be at most {_MAX_NAME_BYTES} UTF-8 bytes")
    return value, encoded


def _safe(value: object, *, depth: int = 0, budget: list[int] | None = None) -> object:
    if depth > _MAX_DEPTH:
        raise ValueError("message payload nesting is too deep")
    if budget is None:
        budget = [_MAX_ITEMS]
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError("message payload contains too many values")
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        if not -(2**63) <= value <= 2**63 - 1:
            raise ValueError("message integers must fit signed 64-bit range")
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("message floats must be finite")
        return value
    if isinstance(value, bytes):
        return {_BYTES_TAG: base64.b64encode(value).decode("ascii")}
    if isinstance(value, (list, tuple)):
        return [_safe(item, depth=depth + 1, budget=budget) for item in value]
    if isinstance(value, Mapping):
        converted: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("message mapping keys must be strings")
            if key == _BYTES_TAG:
                raise ValueError(f"{_BYTES_TAG!r} is reserved")
            converted[key] = _safe(item, depth=depth + 1, budget=budget)
        return converted
    raise TypeError(
        "message values must be None, bool, int, finite float, str, bytes, "
        "list/tuple, or a string-keyed mapping"
    )


def _restore(value: object, *, depth: int = 0, budget: list[int] | None = None) -> object:
    if depth > _MAX_DEPTH:
        raise ValueError("message payload nesting is too deep")
    if budget is None:
        budget = [_MAX_ITEMS]
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError("message payload contains too many values")
    if isinstance(value, list):
        return [_restore(item, depth=depth + 1, budget=budget) for item in value]
    if isinstance(value, dict):
        if set(value) == {_BYTES_TAG}:
            encoded = value[_BYTES_TAG]
            if not isinstance(encoded, str):
                raise ValueError("invalid encoded byte payload")
            try:
                return base64.b64decode(encoded, validate=True)
            except ValueError as error:
                raise ValueError("invalid encoded byte payload") from error
        return {
            key: _restore(item, depth=depth + 1, budget=budget)
            for key, item in value.items()
        }
    return value


def encode_message(
    name: str,
    fields: Mapping[str, object],
    *,
    maximum_size: int = 64 * 1024,
) -> bytes:
    """Encode one named message without pickle or executable object graphs."""

    _, encoded_name = _name(name)
    if not isinstance(fields, Mapping):
        raise TypeError("message fields must be a mapping")
    safe = _safe(fields)
    payload = json.dumps(
        safe, ensure_ascii=False, allow_nan=False, separators=(",", ":")
    ).encode("utf-8")
    frame = _HEADER.pack(_MAGIC, _VERSION, len(encoded_name), len(payload))
    frame += encoded_name + payload
    if len(frame) > maximum_size:
        raise ValueError("encoded message exceeds maximum_size")
    return frame


def decode_message(data: bytes, *, maximum_size: int = 64 * 1024) -> Message:
    """Validate and decode one named message frame."""

    if not isinstance(data, bytes):
        raise TypeError("message frame must be bytes")
    if len(data) > maximum_size:
        raise ValueError("message frame exceeds maximum_size")
    if len(data) < _HEADER.size:
        raise ValueError("message frame is truncated")
    magic, version, name_size, payload_size = _HEADER.unpack_from(data)
    if magic != _MAGIC or version != _VERSION:
        raise ValueError("message frame has an unsupported format or version")
    if not 1 <= name_size <= _MAX_NAME_BYTES:
        raise ValueError("message frame has an invalid name length")
    if _HEADER.size + name_size + payload_size != len(data):
        raise ValueError("message frame length does not match its declaration")
    name_start = _HEADER.size
    try:
        name = data[name_start : name_start + name_size].decode("utf-8")
        raw = json.loads(data[name_start + name_size :].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("message frame contains invalid UTF-8 or JSON") from error
    _name(name)
    restored = _restore(raw)
    if not isinstance(restored, dict) or not all(
        isinstance(key, str) for key in restored
    ):
        raise ValueError("message fields must decode to a string-keyed mapping")
    return Message(name, restored)


__all__ = ["Message", "MessageSchema", "decode_message", "encode_message"]
