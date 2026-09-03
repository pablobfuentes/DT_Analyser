"""Single in-process automation worker. Executes persistent jobs sequentially."""

from __future__ import annotations

import logging
import threading
import time

from sqlalchemy.orm import Session

from app.db.models.automation import AutomationJob
from app.db.session import SessionLocal
from app.services.automation.errors import is_retryable
from app.services.automation.jobs import claim_next, finish, mark_retry, parse_payload, recover_interrupted

logger = logging.getLogger(__name__)

_stop = threading.Event()
_thread: threading.Thread | None = None
_lock = threading.Lock()


def dispatch(db: Session, job: AutomationJob) -> str:
    payload = parse_payload(job)
    job_type = job.job_type
    logger.info("job=%s type=%s corr=%s start", job.id, job_type, job.correlation_id)

    if job_type == "PROCESS_INBOX":
        from app.services.automation.pipeline import start_inbox_run

        run = start_inbox_run(db, dry_run=bool(payload.get("dry_run")))
        job.run_id = run.id
        return run.status

    if job_type == "FINALIZE_DAY":
        from datetime import date

        from app.services.automation.pipeline import start_finalize_run

        raw = payload.get("date")
        ny = date.fromisoformat(raw) if raw else None
        run = start_finalize_run(db, ny)
        job.run_id = run.id
        return run.status

    if job_type == "BACKUP":
        from app.services.backup.service import create_backup

        rec = create_backup(db, backup_type=payload.get("backup_type") or "MANUAL")
        return rec.get("status") or "SUCCESS"

    if job_type == "ARCHIVE_FILE":
        from app.services.automation.inbox import retry_archive

        retry_archive(db, int(payload["file_event_id"]))
        return "SUCCESS"

    if job_type == "RETRY_STEP":
        from app.services.automation.pipeline import retry_failed_steps

        run = retry_failed_steps(db, int(payload["run_id"]))
        job.run_id = run.id
        return run.status

    raise ValueError(f"Unknown job_type {job_type}")


def process_next_job(db: Session) -> AutomationJob | None:
    job = claim_next(db)
    if job is None:
        return None
    try:
        status = dispatch(db, job)
        if status == "PARTIAL":
            finish(db, job, "PARTIAL")
        else:
            finish(db, job, "SUCCESS" if status in ("SUCCESS", "SKIPPED") else status)
    except Exception as exc:
        logger.exception("job=%s failed", job.id)
        code = getattr(exc, "code", None) or type(exc).__name__
        if is_retryable(code) or code in ("TimeoutError", "OSError"):
            mark_retry(db, job, code, str(exc))
        else:
            finish(db, job, "FAILED", code, str(exc))
    return job


def _loop() -> None:
    while not _stop.is_set():
        db = SessionLocal()
        try:
            job = process_next_job(db)
        except Exception:
            logger.exception("worker loop error")
            job = None
        finally:
            db.close()
        if job is None:
            _stop.wait(0.5)


def start_worker() -> None:
    global _thread
    with _lock:
        if _thread and _thread.is_alive():
            return
        _stop.clear()
        db = SessionLocal()
        try:
            recover_interrupted(db)
        finally:
            db.close()
        _thread = threading.Thread(target=_loop, name="lta-automation-worker", daemon=True)
        _thread.start()
        logger.info("Automation worker started")


def stop_worker(*, drain_timeout: float = 2.0) -> None:
    """Signal the loop to exit and wait for the current job to finish."""
    _stop.set()
    if _thread:
        _thread.join(timeout=drain_timeout)


def worker_alive() -> bool:
    return bool(_thread and _thread.is_alive())
