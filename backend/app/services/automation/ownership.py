"""Inter-process automation ownership via an OS file lock.

Only the process that holds `{data_dir}/automation.lock` may start the
watcher, automation worker, or APScheduler. Other processes may serve HTTP
as STANDBY. The lock is released on clean shutdown or when the process
dies (OS releases the handle). PID text is informational only.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from app.paths import resolve_data_dir

logger = logging.getLogger(__name__)

LOCK_NAME = "automation.lock"

_lock: "AutomationLock | None" = None


class AutomationLock:
    """Exclusive OS lock on `{data_dir}/automation.lock`. Keep the handle open."""

    def __init__(self, data_dir: Path | str | None = None):
        root = Path(data_dir) if data_dir is not None else resolve_data_dir()
        self.path = root / LOCK_NAME
        self._fh = None
        self.owned = False
        self.pid: int | None = None

    def acquire(self) -> bool:
        if self.owned:
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+b")
        try:
            if fh.seek(0, os.SEEK_END) == 0:
                fh.write(b"\x00")
                fh.flush()
            fh.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        self._fh = fh
        self.owned = True
        self.pid = os.getpid()
        self._write_info()
        logger.info("Automation ownership acquired pid=%s path=%s", self.pid, self.path)
        return True

    def _write_info(self) -> None:
        if self._fh is None:
            return
        payload = json.dumps({
            "pid": self.pid,
            "acquired_at": datetime.now(timezone.utc).isoformat(),
        }).encode("utf-8")
        # First byte stays in the locked region; metadata starts at offset 1.
        self._fh.seek(1)
        self._fh.truncate()
        self._fh.write(payload)
        self._fh.flush()

    def release(self) -> None:
        if self._fh is None:
            self.owned = False
            return
        try:
            self._fh.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
        except OSError:
            logger.warning("Automation lock unlock failed (handle close will release)")
        finally:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
            self.owned = False
            logger.info("Automation ownership released path=%s", self.path)

    def simulate_crash(self) -> None:
        """Close the handle without an unlock protocol. OS drops the lock."""
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
        self.owned = False


def lock_path(data_dir: Path | str | None = None) -> Path:
    root = Path(data_dir) if data_dir is not None else resolve_data_dir()
    return root / LOCK_NAME


def read_lock_info(data_dir: Path | str | None = None) -> dict | None:
    path = lock_path(data_dir)
    if not path.exists():
        return None
    try:
        raw = path.read_bytes()
        text = raw[1:].decode("utf-8", errors="replace").strip() if raw else ""
        if not text:
            return None
        return json.loads(text)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None


def try_acquire_automation_ownership(data_dir: Path | str | None = None) -> bool:
    global _lock
    if _lock is not None and _lock.owned:
        return True
    lock = AutomationLock(data_dir)
    if lock.acquire():
        _lock = lock
        return True
    return False


def release_automation_ownership() -> None:
    global _lock
    if _lock is not None:
        _lock.release()
        _lock = None


def is_automation_owner() -> bool:
    return bool(_lock is not None and _lock.owned)


def ownership_status(data_dir: Path | str | None = None) -> dict:
    if is_automation_owner():
        return {
            "automation_ownership": "OWNER",
            "automation_ownership_detail": None,
            "owner_pid": _lock.pid if _lock else os.getpid(),
        }
    info = read_lock_info(data_dir)
    other_pid = info.get("pid") if info else None
    return {
        "automation_ownership": "STANDBY",
        "automation_ownership_detail": "OWNED BY ANOTHER PROCESS",
        "owner_pid": other_pid,
    }
