"""Daily review metrics reuse Dashboard / Risk / Excursion / Signal services."""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.journal import JournalEntry
from app.db.models.market_data import TradeExcursion, TradeMarketFeature
from app.db.models.reviews import DailyReview
from app.db.models.signal import TradeSignalLink
from app.db.models.trade import Trade
from app.services.analytics.expectancy import profit_factor, r_statistics
from app.services.dashboard_service import DashboardFilters, _serialize_summary, _summary_stats, _trade_row, build_closed_trades_query
from app.services.journal.service import entry_dict, get_trade_note
from app.services.preferences import DAILY_PROMPTS
from app.services.risk.service import missing_r_breakdown
from app.services.signals.coverage import coverage_summary
from app.services.signals.matcher import STATUS_CONFIRMED
from app.utils.analytics import decimal_str
from app.utils.hashing import json_dumps
from app.utils.money import to_decimal


def calculation_versions() -> dict:
    return {
        "dashboard": "step2",
        "risk": "step7",
        "excursions": "step8",
        "signals": "step5",
        "research_statistics": settings.research_statistics_version,
        "schema": settings.schema_version,
    }


def _day_trades(db: Session, day: date) -> list[Trade]:
    filt = DashboardFilters(start_date=day, end_date=day)
    return list(build_closed_trades_query(db, filt).all())


def live_metrics_for_date(db: Session, day: date) -> dict:
    trades = _day_trades(db, day)
    rows = [_trade_row(t) for t in trades]
    summary = _serialize_summary(_summary_stats(rows))
    rs = [t.r_multiple for t in trades if t.r_multiple is not None]
    r_stats = r_statistics(rs)
    pf, pf_st = profit_factor([r["pnl"] for r in rows])

    ids = [t.id for t in trades]
    excursions = {
        e.trade_id: e
        for e in db.query(TradeExcursion).filter(TradeExcursion.trade_id.in_(ids)).all()
    } if ids else {}
    mfe_vals = [e.mfe_r for e in excursions.values() if e.mfe_r is not None]
    givebacks = [e.peak_giveback_r for e in excursions.values() if e.peak_giveback_r is not None]
    effs = [e.exit_efficiency_pct for e in excursions.values() if e.exit_efficiency_pct is not None]
    threshold = to_decimal(settings.loss_beyond_r_threshold, Decimal("-1.05"))
    beyond = sum(1 for r in rs if r <= threshold)

    best_trade = max(rows, key=lambda r: r["pnl"]) if rows else None
    worst_trade = min(rows, key=lambda r: r["pnl"]) if rows else None
    best_r_t = max(trades, key=lambda t: t.r_multiple) if rs else None
    worst_r_t = min((t for t in trades if t.r_multiple is not None), key=lambda t: t.r_multiple) if rs else None

    risk = missing_r_breakdown(db, trades)
    signals = coverage_summary(db, trades)
    market_n = (
        db.query(TradeMarketFeature)
        .filter(TradeMarketFeature.trade_id.in_(ids), TradeMarketFeature.enrichment_status.in_(["COMPLETE", "PARTIAL"]))
        .count()
        if ids
        else 0
    )
    exc_ok = sum(1 for e in excursions.values() if e.quality_status not in ("PENDING", "OPEN_TRADE"))

    return {
        "date": day.isoformat(),
        "summary": summary,
        "average_r": decimal_str(r_stats.get("average")),
        "best_r": decimal_str(r_stats.get("best")),
        "worst_r": decimal_str(r_stats.get("worst")),
        "profit_factor": decimal_str(pf),
        "profit_factor_status": pf_st,
        "max_mfe_r": decimal_str(max(mfe_vals) if mfe_vals else None),
        "largest_giveback_r": decimal_str(max(givebacks) if givebacks else None),
        "avg_exit_efficiency_pct": decimal_str(sum(effs) / len(effs) if effs else None),
        "loss_beyond_initial_risk_count": beyond,
        "best_trade_id": best_trade["trade"].id if best_trade else None,
        "worst_trade_id": worst_trade["trade"].id if worst_trade else None,
        "best_r_trade_id": best_r_t.id if best_r_t else None,
        "worst_r_trade_id": worst_r_t.id if worst_r_t else None,
        "strategy_coverage_pct": signals.get("strategy_coverage_pct"),
        "r_coverage_pct": risk.get("r_coverage_pct"),
        "market_coverage_pct": round(market_n / len(trades) * 100, 1) if trades else 0,
        "excursion_coverage_pct": round(exc_ok / len(trades) * 100, 1) if trades else 0,
        "trade_count": len(trades),
    }


def trade_table_rows(db: Session, day: date) -> list[dict]:
    trades = _day_trades(db, day)
    ids = [t.id for t in trades]
    excursions = {
        e.trade_id: e
        for e in db.query(TradeExcursion).filter(TradeExcursion.trade_id.in_(ids)).all()
    } if ids else {}
    notes = {
        e.trade_id: e
        for e in db.query(JournalEntry).filter(JournalEntry.trade_id.in_(ids), JournalEntry.entry_type == "TRADE_NOTE").all()
    } if ids else {}
    out = []
    for t in trades:
        rp = _trade_row(t)
        ex = excursions.get(t.id)
        note = notes.get(t.id)
        out.append({
            "id": t.id,
            "ticker": t.ticker,
            "direction": t.direction,
            "net_pnl": decimal_str(rp["pnl"]),
            "r_multiple": decimal_str(t.r_multiple),
            "mfe_r": decimal_str(ex.mfe_r) if ex else None,
            "mae_r": decimal_str(ex.mae_r) if ex else None,
            "exit_efficiency_pct": decimal_str(ex.exit_efficiency_pct) if ex else None,
            "setup_quality": None,
            "journal_status": "reviewed" if note and (note.body or note.prompt_fields_json) else "not_reviewed",
        })
    if ids:
        from app.db.models.signal import Signal

        links = (
            db.query(TradeSignalLink, Signal)
            .join(Signal, Signal.id == TradeSignalLink.signal_id)
            .filter(TradeSignalLink.trade_id.in_(ids), TradeSignalLink.link_status == STATUS_CONFIRMED)
            .all()
        )
        setup = {l.trade_id: s.setup_quality for l, s in links}
        for row in out:
            row["setup_quality"] = setup.get(row["id"])
    return out


def get_or_create(db: Session, day: date) -> DailyReview:
    row = db.query(DailyReview).filter(DailyReview.ny_date == day.isoformat()).first()
    if row:
        return row
    row = DailyReview(ny_date=day.isoformat(), status="NOT_STARTED")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def patch_review(db: Session, day: date, payload: dict) -> DailyReview:
    row = get_or_create(db, day)
    if "body" in payload:
        row.body = payload.get("body")
    if "prompt_fields" in payload:
        row.prompt_fields_json = json_dumps(payload.get("prompt_fields") or {})
    if row.status == "NOT_STARTED":
        row.status = "IN_PROGRESS"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def complete_review(db: Session, day: date, *, refresh_snapshot: bool = False) -> DailyReview:
    row = get_or_create(db, day)
    metrics = live_metrics_for_date(db, day)
    if row.metrics_snapshot_json is None or refresh_snapshot:
        row.metrics_snapshot_json = json_dumps(metrics)
        row.calculation_versions_json = json_dumps(calculation_versions())
    if row.completed_at is None:
        row.completed_at = datetime.now(timezone.utc)
    row.status = "COMPLETED"
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return row


def review_payload(db: Session, day: date) -> dict:
    row = get_or_create(db, day)
    prompts = {}
    if row.prompt_fields_json:
        try:
            prompts = json.loads(row.prompt_fields_json)
        except json.JSONDecodeError:
            prompts = {}
    snapshot = json.loads(row.metrics_snapshot_json) if row.metrics_snapshot_json else None
    return {
        "id": row.id,
        "date": row.ny_date,
        "status": row.status,
        "body": row.body,
        "prompt_fields": prompts,
        "prompt_labels": DAILY_PROMPTS,
        "live_metrics": live_metrics_for_date(db, day),
        "metrics_snapshot": snapshot,
        "calculation_versions": json.loads(row.calculation_versions_json) if row.calculation_versions_json else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "trades": trade_table_rows(db, day),
    }
