from datetime import UTC, datetime
from typing import Callable

_now: Callable[[], datetime] = lambda: datetime.now(UTC)


def utc_now() -> datetime:
    return _now()


def set_clock(fn: Callable[[], datetime]) -> None:
    """Override the clock (used in tests)."""
    global _now
    _now = fn


def reset_clock() -> None:
    global _now
    _now = lambda: datetime.now(UTC)
