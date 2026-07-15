"""Opaque, bounded integer-key cursor codec for descending keyset pagination."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


class InvalidCursor(ValueError):
    pass


def encode_cursor(last_id: int | None) -> str | None:
    if last_id is None:
        return None
    if last_id <= 0:
        raise ValueError("cursor id must be positive")
    raw = f"v1:{last_id}".encode("ascii")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    if not cursor or len(cursor) > 64 or any(ch.isspace() for ch in cursor):
        raise InvalidCursor("invalid cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.b64decode(padded, altchars=b"-_", validate=True).decode("ascii")
        version, value = raw.split(":", 1)
        decoded = int(value)
    except (UnicodeDecodeError, ValueError):
        raise InvalidCursor("invalid cursor") from None
    if version != "v1" or decoded <= 0 or encode_cursor(decoded) != cursor:
        raise InvalidCursor("invalid cursor")
    return decoded


@dataclass(frozen=True)
class KeysetPage(Generic[T]):
    items: tuple[T, ...]
    next_cursor: str | None

    @property
    def has_more(self) -> bool:
        return self.next_cursor is not None
