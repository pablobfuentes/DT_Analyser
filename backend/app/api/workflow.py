"""Daily workflow, inbox, runs, and automation health."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.automation import AutomationJob, AutomationRun, AutomationRunStep
from app.db.session import get_db
from app.paths import data_layout, resolve_data_dir
from app.services.automation.completeness import attention_items, set_no_trading, workflow_status
from app.services.automation.jobs import cancel_pending, enqueue
from app.services.automation.ownership import ownership_status
from app.services.automation.scheduler import scheduler_alive
from app.services.automation.watcher import watcher_alive
from app.services.automation.worker import worker_alive
from app.services.maintenance import is_maintenance, maintenance_reason
from app.utils.analytics import ny_date_from_utc
from app.utils.clock import utc_now

router = APIRouter(prefix="/api/workflow", tags=["workflow"])


class NoTradeBody(BaseModel):
    date: str | None = None
    no_trading: bool = True


def _parse_day(raw: str | None) -> date:
    if raw:
        return date.fromisoformat(raw)
    return ny_date_from_utc(utc_now())


@router.get("/status")
def status(date_str: str | None = Query(None, alias="date"), db: Session = Depends(get_db)):
    return workflow_status(db, _parse_day(date_str))


@router.get("/attention")
def attention(date_str: str | None = Query(None, alias="date"), db: Session = Depends(get_db)):
    return {"items": attention_items(db, _parse_day(date_str))}


@router.post("/process-inbox")
def process_inbox(db: Session = Depends(get_db)):
    job = enqueue(db, "PROCESS_INBOX", {}, coalesce_type=True)
    return {"job_id": job.id, "status": job.status, "correlation_id": job.correlation_id}


@router.post("/finalize")
def finalize(date_str: str | None = Query(None, alias="date"), db: Session = Depends(get_db)):
    day = _parse_day(date_str)
    job = enqueue(db, "FINALIZE_DAY", {"date": day.isoformat()}, coalesce_type=True)
    return {"job_id": job.id, "status": job.status, "date": day.isoformat()}


@router.post("/no-trade-day")
def no_trade(body: NoTradeBody, db: Session = Depends(get_db)):
    day = _parse_day(body.date)
    return set_no_trading(db, day, body.no_trading)


@router.get("/runs")
def runs(db: Session = Depends(get_db), limit: int = 30):
    rows = db.query(AutomationRun).order_by(AutomationRun.id.desc()).limit(limit).all()
    out = []
    for r in rows:
        steps = db.query(AutomationRunStep).filter(AutomationRunStep.run_id == r.id).all()
        out.append({
            "id": r.id,
            "run_type": r.run_type,
            "ny_date": r.ny_date,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "steps": len(steps),
            "errors": sum(s.error_count for s in steps),
        })
    return {"items": out}


@router.get("/runs/{run_id}")
def run_detail(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AutomationRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    steps = (
        db.query(AutomationRunStep)
        .filter(AutomationRunStep.run_id == run_id)
        .order_by(AutomationRunStep.id.asc())
        .all()
    )
    import json

    return {
        "id": run.id,
        "run_type": run.run_type,
        "ny_date": run.ny_date,
        "status": run.status,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "summary": json.loads(run.summary_json) if run.summary_json else None,
        "steps": [
            {
                "step_key": s.step_key,
                "status": s.status,
                "started_at": s.started_at.isoformat() if s.started_at else None,
                "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                "records_processed": s.records_processed,
                "records_created": s.records_created,
                "records_updated": s.records_updated,
                "records_skipped": s.records_skipped,
                "error_count": s.error_count,
                "error_code": s.error_code,
                "error_message": s.error_message,
                "details": json.loads(s.details_json) if s.details_json else None,
            }
            for s in steps
        ],
    }


@router.get("/health")
def health(db: Session = Depends(get_db)):
    pending = db.query(AutomationJob).filter(AutomationJob.status.in_(("PENDING", "RETRY"))).count()
    failed = db.query(AutomationJob).filter(AutomationJob.status == "FAILED").count()
    running = db.query(AutomationJob).filter(AutomationJob.status == "RUNNING").count()
    layout = data_layout()
    own = ownership_status()
    return {
        "watcher": "Running" if watcher_alive() else "Stopped",
        "worker": "Running" if worker_alive() else "Stopped",
        "scheduler": "Running" if scheduler_alive() else "Stopped",
        "automation_ownership": own["automation_ownership"],
        "automation_ownership_detail": own["automation_ownership_detail"],
        "owner_pid": own.get("owner_pid"),
        "maintenance_mode": is_maintenance(),
        "maintenance_reason": maintenance_reason(),
        "pending_jobs": pending,
        "failed_jobs": failed,
        "running_jobs": running,
        "data_dir": str(resolve_data_dir()),
        "inbox": str(layout["inbox"]),
        "archive": str(layout["archive"]),
        "backups": str(layout["backups"]),
        "scheduler_note": "In-process scheduler only runs while the backend is up. Use CLI + Task Scheduler for offline EOD. Monday–Friday only; no holiday calendar.",
        "app_version": settings.app_version,
    }


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db)):
    try:
        job = cancel_pending(db, job_id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    if job is None:
        raise HTTPException(404, "Job not found")
    return {"id": job.id, "status": job.status}
