"""Pipeline orchestration. Calls existing authoritative services only."""

from __future__ import annotations

import json
import logging
from datetime import date
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.automation import AutomationRun, AutomationRunStep, utcnow
from app.db.models.signal import Signal
from app.db.models.trade import Trade
from app.market_data.registry import get_market_data_provider
from app.services.automation.inbox import process_inbox
from app.services.automation.jobs import create_run, parse_payload
from app.services.excursion_enrichment.service import ExcursionEnrichmentService
from app.services.market_enrichment.service import MarketEnrichmentService
from app.services.preferences import get_pref
from app.services.risk.service import RiskService
from app.services.signals.matcher import match_signals_batch
from app.utils.analytics import ny_date_from_utc
from app.utils.hashing import json_dumps

logger = logging.getLogger(__name__)

STEP_KEYS = (
    "INPUT_DETECTION",
    "TRADE_IMPORT",
    "RECONSTRUCT",
    "PINE_IMPORT",
    "SIGNAL_MATCHING",
    "RISK_RECALC",
    "MARKET_ENRICHMENT",
    "EXCURSION_ENRICHMENT",
    "RESEARCH_REFRESH",
    "REVIEW_SNAPSHOT",
    "BACKUP",
)


def _details(obj: Any) -> str:
    return json_dumps(obj)


def _ensure_steps(db: Session, run: AutomationRun) -> list[AutomationRunStep]:
    existing = {s.step_key: s for s in db.query(AutomationRunStep).filter(AutomationRunStep.run_id == run.id).all()}
    steps = []
    for key in STEP_KEYS:
        if key in existing:
            steps.append(existing[key])
            continue
        row = AutomationRunStep(run_id=run.id, step_key=key, status="PENDING")
        db.add(row)
        steps.append(row)
    db.flush()
    return steps


def _step_map(db: Session, run_id: int) -> dict[str, AutomationRunStep]:
    return {s.step_key: s for s in db.query(AutomationRunStep).filter(AutomationRunStep.run_id == run_id).all()}


def _run_step(db: Session, step: AutomationRunStep, fn: Callable[[], dict]) -> dict:
    if step.status == "SUCCESS":
        return json.loads(step.details_json or "{}")
    step.status = "RUNNING"
    step.started_at = utcnow()
    db.commit()
    try:
        result = fn()
        step.records_processed = int(result.get("processed", 0) or 0)
        step.records_created = int(result.get("created", 0) or 0)
        step.records_updated = int(result.get("updated", 0) or 0)
        step.records_skipped = int(result.get("skipped", 0) or 0)
        step.error_count = int(result.get("errors", 0) or 0)
        step.details_json = _details(result)
        status = result.get("status") or "SUCCESS"
        if status == "SKIPPED":
            step.status = "SKIPPED"
        elif status == "PARTIAL" or step.error_count:
            step.status = "PARTIAL"
        else:
            step.status = "SUCCESS"
        step.completed_at = utcnow()
        db.commit()
        return result
    except Exception as exc:
        logger.exception("Pipeline step %s failed", step.step_key)
        step.status = "FAILED"
        step.error_code = getattr(exc, "code", None) or type(exc).__name__
        step.error_message = str(exc)
        step.completed_at = utcnow()
        db.commit()
        return {"status": "FAILED", "error": str(exc)}


def _summarize_run(db: Session, run: AutomationRun) -> None:
    steps = db.query(AutomationRunStep).filter(AutomationRunStep.run_id == run.id).all()
    statuses = {s.status for s in steps}
    if "FAILED" in statuses and any(s.status == "SUCCESS" for s in steps):
        run.status = "PARTIAL"
    elif "PARTIAL" in statuses:
        run.status = "PARTIAL"
    elif statuses <= {"SUCCESS", "SKIPPED"}:
        run.status = "SUCCESS"
    elif "FAILED" in statuses:
        run.status = "FAILED"
    else:
        run.status = "PARTIAL"
    run.completed_at = utcnow()
    run.summary_json = _details({s.step_key: s.status for s in steps})
    db.commit()


def run_pipeline(
    db: Session,
    run: AutomationRun,
    *,
    include_inbox: bool = True,
    include_backup: bool = False,
    dry_run: bool = False,
    inbox_root=None,
) -> AutomationRun:
    """Execute remaining pipeline steps. Successful steps are not re-run."""
    run.status = "RUNNING"
    run.started_at = run.started_at or utcnow()
    db.commit()
    _ensure_steps(db, run)
    steps = _step_map(db, run.id)
    inbox_result: dict = {}

    def input_detection():
        if not include_inbox:
            return {"status": "SKIPPED", "reason": "finalize has no inbox scan"}
        from app.services.automation.inbox import list_inbox_candidates

        files = list_inbox_candidates(inbox_root)
        return {"status": "SUCCESS", "processed": len(files), "files": [p.name for p in files]}

    _run_step(db, steps["INPUT_DETECTION"], input_detection)

    def trade_and_pine():
        nonlocal inbox_result
        if not include_inbox:
            return {"status": "SKIPPED", "reason": "no inbox import on finalize"}
        if dry_run:
            inbox_result = process_inbox(db, dry_run=True, root=inbox_root)
            return {"status": "SUCCESS", **inbox_result, "processed": inbox_result.get("files_seen", 0)}
        inbox_result = process_inbox(db, dry_run=False, root=inbox_root)
        created = 0
        pine_created = 0
        errors = inbox_result.get("needs_review", 0)
        for r in inbox_result.get("results", []):
            imp = r.get("import") or {}
            created += int(imp.get("imported_executions") or 0) + int(imp.get("imported_trades") or 0)
            pine_created += int(imp.get("imported_events") or 0)
        status = "PARTIAL" if errors and created else ("SUCCESS" if not errors or created or pine_created else "SUCCESS")
        if inbox_result.get("needs_review") and not created and not pine_created and inbox_result.get("imported", 0) == 0:
            if inbox_result.get("files_seen", 0) and all(
                r.get("status") == "NEEDS_REVIEW" for r in inbox_result.get("results", []) if r.get("status") != "UNSTABLE"
            ):
                status = "PARTIAL"
        return {
            "status": status,
            "created": created + pine_created,
            "errors": errors,
            "processed": inbox_result.get("files_seen", 0),
            "inbox": inbox_result,
        }

    import_result = _run_step(db, steps["TRADE_IMPORT"], trade_and_pine)

    def reconstruct():
        return {
            "status": "SKIPPED",
            "reason": "Reconstruction already runs inside ImportService.commit_import",
            "skipped": 1,
        }

    _run_step(db, steps["RECONSTRUCT"], reconstruct)

    def pine_import_note():
        inbox = (import_result.get("inbox") or inbox_result) if isinstance(import_result, dict) else inbox_result
        pine = 0
        for r in (inbox or {}).get("results", []):
            if (r.get("import") or {}).get("kind") == "PINE":
                pine += int((r.get("import") or {}).get("imported_events") or 0)
        if not include_inbox:
            return {"status": "SKIPPED", "reason": "finalize"}
        return {"status": "SUCCESS", "created": pine, "note": "Pine files imported in TRADE_IMPORT pass"}

    _run_step(db, steps["PINE_IMPORT"], pine_import_note)

    def match():
        signals = db.query(Signal).all()
        if not signals:
            return {"status": "SKIPPED", "reason": "no signals"}
        match_signals_batch(db, signals)
        db.commit()
        return {"status": "SUCCESS", "processed": len(signals)}

    _run_step(db, steps["SIGNAL_MATCHING"], match)

    def risk():
        trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
        if not trades:
            return {"status": "SKIPPED", "reason": "no closed trades"}
        RiskService(db).recalculate_many(trades)
        db.commit()
        return {"status": "SUCCESS", "processed": len(trades)}

    _run_step(db, steps["RISK_RECALC"], risk)

    def market():
        trades = db.query(Trade).filter(Trade.status == "CLOSED").count()
        if not trades:
            return {"status": "SKIPPED", "reason": "no closed trades"}
        svc = MarketEnrichmentService(db, get_market_data_provider())
        result = svc.enrich(scope="missing")
        return {"status": "SUCCESS", "processed": result.get("trades_requested") or 0, "result": result}

    _run_step(db, steps["MARKET_ENRICHMENT"], market)

    def excursion():
        closed = db.query(Trade).filter(Trade.status == "CLOSED", Trade.exit_time_utc.isnot(None)).count()
        if not closed:
            return {"status": "SKIPPED", "reason": "no closed trades"}
        svc = ExcursionEnrichmentService(db)
        result = svc.enrich(scope="missing")
        return {"status": "SUCCESS", "processed": result.get("trades_requested") or 0, "result": result}

    _run_step(db, steps["EXCURSION_ENRICHMENT"], excursion)

    def research():
        return {
            "status": "SKIPPED",
            "reason": "Forward samples are query-time (entry_time_utc > cutoff_at). Candidate rules not mutated.",
        }

    _run_step(db, steps["RESEARCH_REFRESH"], research)

    def snapshot():
        from app.services.reviews.daily import live_metrics_for_date

        ny = run.ny_date or ny_date_from_utc(utcnow()).isoformat()
        metrics = live_metrics_for_date(db, date.fromisoformat(ny))
        return {"status": "SUCCESS", "ny_date": ny, "metrics": metrics}

    _run_step(db, steps["REVIEW_SNAPSHOT"], snapshot)

    def backup_step():
        auto = get_pref(db, "automatic_backup", settings.automatic_backup)
        if not include_backup or not auto:
            return {"status": "SKIPPED", "reason": "backup not requested for this run"}
        from app.services.backup.service import create_backup

        rec = create_backup(db, backup_type="DAILY")
        return {"status": rec.get("status", "SUCCESS"), "backup": rec}

    _run_step(db, steps["BACKUP"], backup_step)

    _summarize_run(db, run)
    return run


def start_inbox_run(db: Session, *, dry_run: bool = False, inbox_root=None) -> AutomationRun:
    ny = ny_date_from_utc(utcnow()).isoformat()
    run = create_run(db, "INBOX_PROCESSING", ny_date=ny)
    return run_pipeline(db, run, include_inbox=True, include_backup=False, dry_run=dry_run, inbox_root=inbox_root)


def start_finalize_run(db: Session, ny: date | None = None, *, include_backup: bool = True) -> AutomationRun:
    day = ny or ny_date_from_utc(utcnow())
    run = create_run(db, "EOD_FINALIZE", ny_date=day.isoformat())
    return run_pipeline(db, run, include_inbox=True, include_backup=include_backup)


def retry_failed_steps(db: Session, run_id: int) -> AutomationRun:
    run = db.get(AutomationRun, run_id)
    if run is None:
        raise ValueError("run not found")
    for step in db.query(AutomationRunStep).filter(AutomationRunStep.run_id == run_id).all():
        if step.status in ("FAILED", "PARTIAL"):
            if step.step_key in ("TRADE_IMPORT", "PINE_IMPORT"):
                continue
            step.status = "PENDING"
            step.error_code = None
            step.error_message = None
    db.commit()
    include_inbox = run.run_type == "INBOX_PROCESSING"
    include_backup = run.run_type in ("EOD_FINALIZE", "MANUAL_BACKUP")
    return run_pipeline(db, run, include_inbox=include_inbox, include_backup=include_backup)
