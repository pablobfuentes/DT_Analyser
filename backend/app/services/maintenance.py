"""Process-local maintenance mode. Used during restore so APIs fail cleanly."""

from __future__ import annotations

import threading

_lock = threading.Lock()
_active = False
_reason: str | None = None

MAINTENANCE_CODE = "MAINTENANCE_MODE"


class MaintenanceModeError(RuntimeError):
    code = MAINTENANCE_CODE

    def __init__(self, reason: str | None = None):
        self.reason = reason or "RESTORE"
        super().__init__(MAINTENANCE_CODE)


def enter_maintenance(reason: str = "RESTORE") -> None:
    global _active, _reason
    with _lock:
        _active = True
        _reason = reason


def leave_maintenance() -> None:
    global _active, _reason
    with _lock:
        _active = False
        _reason = None


def is_maintenance() -> bool:
    return _active


def maintenance_reason() -> str | None:
    return _reason


def maintenance_payload() -> dict:
    return {
        "error": MAINTENANCE_CODE,
        "code": MAINTENANCE_CODE,
        "reason": _reason or "RESTORE",
    }


# Paths that stay available so health/UI can report ownership + maintenance.
MAINTENANCE_EXEMPT_PREFIXES = (
    "/api/health",
    "/api/workflow/health",
    "/docs",
    "/openapi.json",
)
