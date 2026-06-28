"""Cursor-based pagination helpers."""

from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass


@dataclass(frozen=True)
class CursorPage:
    limit: int
    cursor: str | None


def encode_cursor(offset: int) -> str:
    return urlsafe_b64encode(str(offset).encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        return int(urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return 0
