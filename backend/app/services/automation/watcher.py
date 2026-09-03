"""Lightweight inbox watcher. Enqueues PROCESS_INBOX; does not import in the callback."""

from __future__ import annotations

import logging
from pathlib import Path

from app.config import settings
from app.paths import ensure_data_layout
from app.services.automation.classify import is_candidate_name
from app.services.preferences import get_pref

logger = logging.getLogger(__name__)

_observer = None
_poll_thread = None
_stop = None


def _enqueue_inbox() -> None:
    from app.db.session import SessionLocal
    from app.services.automation.jobs import enqueue

    db = SessionLocal()
    try:
        auto = get_pref(db, "auto_process_inbox", settings.auto_process_inbox)
        if not auto:
            logger.info("Inbox file seen; auto-process OFF — waiting for Process Inbox")
            return
        enqueue(db, "PROCESS_INBOX", {}, coalesce_type=True, delay_seconds=settings.inbox_debounce_seconds)
    finally:
        db.close()


def notify_candidate(path: str | Path) -> bool:
    name = Path(path).name
    if not is_candidate_name(name):
        return False
    _enqueue_inbox()
    return True


def start_watcher() -> None:
    global _observer
    inbox = ensure_data_layout()["inbox"]
    try:
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
        from watchdog.observers.polling import PollingObserver

        class Handler(FileSystemEventHandler):
            def on_created(self, event):
                if event.is_directory:
                    return
                notify_candidate(event.src_path)

            def on_moved(self, event):
                if event.is_directory:
                    return
                notify_candidate(event.dest_path)

        handler = Handler()
        try:
            obs = Observer()
            obs.schedule(handler, str(inbox), recursive=False)
            obs.start()
            _observer = obs
            logger.info("Inbox watcher started on %s", inbox)
            return
        except Exception:
            logger.warning("Native watcher failed; using polling fallback")
            obs = PollingObserver(timeout=settings.watcher_poll_seconds)
            obs.schedule(handler, str(inbox), recursive=False)
            obs.start()
            _observer = obs
    except ImportError:
        logger.warning("watchdog not installed; inbox watcher disabled. Use Process Inbox / CLI.")


def stop_watcher() -> None:
    global _observer
    if _observer:
        _observer.stop()
        _observer.join(timeout=2)
        _observer = None


def watcher_alive() -> bool:
    return bool(_observer and getattr(_observer, "is_alive", lambda: False)())
