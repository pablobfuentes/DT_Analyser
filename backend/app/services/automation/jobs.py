"""Persistent automation job queue. Watcher/scheduler enqueue; worker executes."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models.automation import AutomationJob, AutomationRun, utcnow

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 30


def _payload(data: dict | None) -> str:
    return json.dumps(data or {}, default=str)


def enqueue(
    db: Session,
    job_type: str,
    payload: dict | None = None,
    *,
    parent_job_id: int | None = None,
    run_id: int | None = None,
    priority: int = 100,
    delay_seconds: float = 0,
    correlation_id: str | None = None,
    coalesce_type: bool = False,
) -> AutomationJob:
    if coalesce_type:
        existing = (
            db.query(AutomationJob)
            .filter(
                AutomationJob.job_type == job_type,
                AutomationJob.status.in_(("PENDING", "RETRY")),
            )
            .first()
        )
        if existing:
            return existing
    job = AutomationJob(
        job_type=job_type,
        status="PENDING",
        payload_json=_payload(payload),
        parent_job_id=parent_job_id,
        run_id=run_id,
        priority=priority,
        correlation_id=correlation_id or uuid.uuid4().hex[:16],
        next_retry_at=utcnow() + timedelta(seconds=delay_seconds) if delay_seconds else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info("Enqueued job %s type=%s corr=%s", job.id, job_type, job.correlation_id)
    return job


def claim_next(db: Session) -> AutomationJob | None:
    now = utcnow()
    job = (
        db.query(AutomationJob)
        .filter(AutomationJob.status.in_(("PENDING", "RETRY")))
        .filter((AutomationJob.next_retry_at.is_(None)) | (AutomationJob.next_retry_at <= now))
        .order_by(AutomationJob.priority.asc(), AutomationJob.id.asc())
        .first()
    )
    if job is None:
        return None
    job.status = "RUNNING"
    job.started_at = now
    job.attempt_count = (job.attempt_count or 0) + 1
    db.commit()
    db.refresh(job)
    return job


def finish(db: Session, job: AutomationJob, status: str, error_code: str | None = None, error_message: str | None = None) -> None:
    job.status = status
    job.completed_at = utcnow()
    job.error_code = error_code
    job.error_message = error_message
    db.commit()


def mark_retry(db: Session, job: AutomationJob, error_code: str, error_message: str) -> None:
    if job.attempt_count >= MAX_ATTEMPTS:
        finish(db, job, "FAILED", error_code, error_message)
        return
    job.status = "RETRY"
    job.error_code = error_code
    job.error_message = error_message
    job.next_retry_at = utcnow() + timedelta(seconds=RETRY_DELAY_SECONDS * job.attempt_count)
    db.commit()


def recover_interrupted(db: Session) -> list[int]:
    """Mark leftover RUNNING jobs INTERRUPTED and re-queue if retry is safe."""
    running = db.query(AutomationJob).filter(AutomationJob.status == "RUNNING").all()
    ids = []
    for job in running:
        job.status = "INTERRUPTED"
        job.error_code = "INTERRUPTED"
        job.error_message = "Process exited while job was running"
        ids.append(job.id)
        if job.attempt_count < MAX_ATTEMPTS:
            job.status = "RETRY"
            job.next_retry_at = utcnow()
    db.commit()
    if ids:
        logger.warning("Recovered interrupted jobs: %s", ids)
    return ids


def cancel_pending(db: Session, job_id: int) -> AutomationJob | None:
    job = db.get(AutomationJob, job_id)
    if job is None:
        return None
    if job.status not in ("PENDING", "RETRY"):
        raise ValueError("Only PENDING or RETRY jobs can be cancelled")
    job.status = "CANCELLED"
    job.completed_at = utcnow()
    db.commit()
    return job


def parse_payload(job: AutomationJob) -> dict:
    try:
        data = json.loads(job.payload_json or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def create_run(db: Session, run_type: str, ny_date: str | None = None, correlation_id: str | None = None) -> AutomationRun:
    run = AutomationRun(
        run_type=run_type,
        ny_date=ny_date,
        status="PENDING",
        correlation_id=correlation_id or uuid.uuid4().hex[:16],
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    return run
