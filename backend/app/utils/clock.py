"""Injectable current-time helper for enrichment and tests."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

_now_override: datetime | None = None


def utc_now() -> datetime:
    if _now_override is not None:
        return _now_override
    return datetime.now(timezone.utc)


@contextmanager
def freeze_time(when: datetime):
    """Pin utc_now() for the duration of the context."""
    global _now_override
    prev = _now_override
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    _now_override = when
    try:
        yield
    finally:
        _now_override = prev
