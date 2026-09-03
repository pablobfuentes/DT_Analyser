"""Daily completeness from import records, not filenames."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.automation import AutomationFileEvent, AutomationRun, BackupRecord, DailyWorkflowDay
from app.db.models.import_batch import ImportBatch
from app.db.models.signal import PineImportBatch, TradeSignalLink
from app.db.models.trade import Trade
from app.services.excursion_enrichment.coverage import get_excursion_coverage
from app.services.market_enrichment.service import get_coverage as market_coverage
from app.services.preferences import expected_inputs
from app.services.risk.service import missing_r_breakdown
from app.services.signals.coverage import coverage_summary
from app.services.signals.matcher import STATUS_CONFIRMED
from app.utils.analytics import ny_date_from_utc, utc_bounds_for_ny_range


PARSER_TO_INPUT = {
    "tradingview_manual": "ORDER_HISTORY",
    "tradingview_activity_log": "ACTIVITY_LOG",
    "tradingview_strategy": "AUTO_STRATEGY_TESTER",
}


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _batch_on_day(completed_at: datetime | None, day: date) -> bool:
    if completed_at is None:
        return False
    return ny_date_from_utc(_ensure_utc(completed_at)) == day


def _trades_for_day(db: Session, day: date) -> list[Trade]:
    start, end = utc_bounds_for_ny_range(day, day)
    q = db.query(Trade)
    if start and end:
        q = q.filter(
            ((Trade.exit_time_utc >= start) & (Trade.exit_time_utc <= end))
            | ((Trade.exit_time_utc.is_(None)) & (Trade.entry_time_utc >= start) & (Trade.entry_time_utc <= end))
        )
    return q.all()


def input_status(db: Session, day: date) -> dict[str, dict]:
    expected = expected_inputs(db)
    found = {k: False for k in expected}

    for batch in db.query(ImportBatch).filter(ImportBatch.status.in_(("SUCCESS", "PARTIAL", "COMPLETE"))).all():
        if not _batch_on_day(batch.import_completed_at or batch.import_started_at, day):
            continue
        key = PARSER_TO_INPUT.get(batch.parser_name)
        if key:
            found[key] = True

    for batch in db.query(PineImportBatch).all():
        when = batch.import_completed_at or batch.import_started_at
        if when and _batch_on_day(when, day):
            found["PINE_LOG"] = True

    for ev in db.query(AutomationFileEvent).filter(AutomationFileEvent.status.in_(("IMPORTED", "IMPORT_SUCCESS_ARCHIVE_PENDING"))).all():
        if ev.processed_at and ny_date_from_utc(_ensure_utc(ev.processed_at)) == day and ev.detected_type:
            found[ev.detected_type] = True

    out = {}
    for key, policy in expected.items():
        policy = policy.upper()
        present = found.get(key, False)
        if policy == "DISABLED":
            state = "DISABLED"
        elif policy == "OPTIONAL" and not present:
            state = "NOT_EXPECTED"
        elif present:
            state = "IMPORTED"
        elif policy == "REQUIRED":
            state = "MISSING"
        else:
            state = "MISSING_RECOMMENDED"
        out[key] = {"policy": policy, "present": present, "state": state}
    return out


def day_badge(inputs: dict, trades: list[Trade], no_trading: bool, needs_attention: int) -> str:
    if no_trading and not trades:
        return "NO_TRADES"
    if not trades and all(v["state"] in ("NOT_EXPECTED", "DISABLED", "MISSING", "MISSING_RECOMMENDED") for v in inputs.values()):
        if any(v["state"] == "MISSING" for v in inputs.values()) and not no_trading:
            return "NEEDS_ATTENTION"
        return "NO_TRADES"
    if needs_attention:
        return "NEEDS_ATTENTION"
    if any(v["state"] == "MISSING" for v in inputs.values()) and not no_trading:
        return "NEEDS_ATTENTION"
    return "PARTIAL" if trades else "COMPLETE"


def workflow_status(db: Session, day: date) -> dict:
    from app.db.models.reviews import DailyReview

    trades = _trades_for_day(db, day)
    inputs = input_status(db, day)
    flag = db.query(DailyWorkflowDay).filter(DailyWorkflowDay.ny_date == day.isoformat()).first()
    no_trading = bool(flag and flag.no_trading)

    attention = attention_items(db, day)
    if no_trading:
        attention = [a for a in attention if a.get("code") != "MISSING_ORDER_HISTORY"]

    closed = [t for t in trades if t.status == "CLOSED"]
    risk = missing_r_breakdown(db, closed)
    signals = coverage_summary(db, closed)
    market = market_coverage(db)
    excursions = get_excursion_coverage(db)

    review = db.query(DailyReview).filter(DailyReview.ny_date == day.isoformat()).first()
    last_backup = db.query(BackupRecord).order_by(BackupRecord.created_at.desc()).first()
    last_eod = (
        db.query(AutomationRun)
        .filter(AutomationRun.run_type == "EOD_FINALIZE")
        .order_by(AutomationRun.created_at.desc())
        .first()
    )

    missing_signals = 0
    if closed:
        linked = {
            l.trade_id
            for l in db.query(TradeSignalLink)
            .filter(TradeSignalLink.link_status == STATUS_CONFIRMED, TradeSignalLink.trade_id.in_([t.id for t in closed]))
            .all()
        }
        missing_signals = sum(1 for t in closed if t.id not in linked)

    badge = day_badge(inputs, trades, no_trading, len(attention))
    if review and review.status == "COMPLETED" and badge == "PARTIAL" and not attention:
        badge = "COMPLETE"
    if all(v["state"] in ("IMPORTED", "NOT_EXPECTED", "DISABLED") for v in inputs.values()):
        if not attention and (review and review.status == "COMPLETED" or no_trading):
            badge = "COMPLETE" if no_trading or trades else "NO_TRADES"

    return {
        "date": day.isoformat(),
        "badge": badge,
        "no_trading": no_trading,
        "inputs": inputs,
        "trades": len(trades),
        "open_trades": sum(1 for t in trades if t.status == "OPEN"),
        "coverage": {
            "market_pct": market.get("coverage_pct"),
            "risk_pct": risk.get("r_coverage_pct"),
            "signal_pct": signals.get("strategy_coverage_pct"),
            "excursion_pct": excursions.get("excursion_coverage_pct"),
            "missing_signals": missing_signals,
        },
        "review_status": review.status if review else "NOT_STARTED",
        "last_backup": {
            "id": last_backup.id,
            "created_at": last_backup.created_at.isoformat() if last_backup and last_backup.created_at else None,
            "status": last_backup.status,
            "path": last_backup.path,
        } if last_backup else None,
        "last_eod": {
            "id": last_eod.id,
            "created_at": last_eod.created_at.isoformat() if last_eod and last_eod.created_at else None,
            "status": last_eod.status,
        } if last_eod else None,
        "attention": attention,
    }


def attention_items(db: Session, day: date) -> list[dict]:
    items = []
    inputs = input_status(db, day)
    flag = db.query(DailyWorkflowDay).filter(DailyWorkflowDay.ny_date == day.isoformat()).first()
    no_trading = bool(flag and flag.no_trading)
    if not no_trading and inputs.get("ORDER_HISTORY", {}).get("state") == "MISSING":
        items.append({"code": "MISSING_ORDER_HISTORY", "message": "Order History not imported for this NY date.", "severity": "attention"})

    q_files = (
        db.query(AutomationFileEvent)
        .filter(AutomationFileEvent.status == "NEEDS_REVIEW")
        .all()
    )
    tz = [e for e in q_files if e.error_code == "TIMEZONE_REQUIRED"]
    unknown = [e for e in q_files if e.error_code in ("UNKNOWN_FORMAT", "AMBIGUOUS_FORMAT")]
    if tz:
        items.append({"code": "TIMEZONE_REQUIRED", "message": f"{len(tz)} file(s) require a timezone.", "severity": "attention", "count": len(tz)})
    if unknown:
        items.append({"code": "UNKNOWN_FORMAT", "message": f"{len(unknown)} unknown file(s) in quarantine.", "severity": "attention", "count": len(unknown)})

    failed = db.query(AutomationFileEvent).filter(AutomationFileEvent.status == "FAILED").count()
    if failed:
        items.append({"code": "FAILED_FILES", "message": f"{failed} failed file event(s).", "severity": "attention"})

    from app.db.models.automation import AutomationJob

    failed_jobs = db.query(AutomationJob).filter(AutomationJob.status == "FAILED").count()
    if failed_jobs:
        items.append({"code": "FAILED_JOBS", "message": f"{failed_jobs} failed automation job(s).", "severity": "attention"})

    last_backup = db.query(BackupRecord).filter(BackupRecord.status == "SUCCESS").order_by(BackupRecord.created_at.desc()).first()
    if last_backup is None:
        items.append({"code": "BACKUP_NONE", "message": "No verified backup yet.", "severity": "attention"})
    failed_backup = db.query(BackupRecord).filter(BackupRecord.status == "FAILED").order_by(BackupRecord.created_at.desc()).first()
    if failed_backup and (last_backup is None or failed_backup.created_at > last_backup.created_at):
        items.append({"code": "BACKUP_FAILED", "message": "Latest backup failed.", "severity": "attention"})

    return items


def set_no_trading(db: Session, day: date, value: bool) -> dict:
    row = db.query(DailyWorkflowDay).filter(DailyWorkflowDay.ny_date == day.isoformat()).first()
    if row is None:
        row = DailyWorkflowDay(ny_date=day.isoformat(), no_trading=1 if value else 0)
        db.add(row)
    else:
        row.no_trading = 1 if value else 0
    db.commit()
    return workflow_status(db, day)
