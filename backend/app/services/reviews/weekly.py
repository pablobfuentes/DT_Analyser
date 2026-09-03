"""Weekly review — existing analytics only. Language is observational."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.reviews import WeeklyReview
from app.services.analytics.drawdown import summarize_drawdown
from app.services.analytics.expectancy import profit_factor, r_statistics
from app.services.dashboard_service import (
    DashboardFilters,
    _daily_rows,
    _serialize_summary,
    _summary_stats,
    _trade_row,
    build_closed_trades_query,
)
from app.services.preferences import WEEKLY_PROMPTS
from app.services.reports.filters import TradeFilterSet
from app.services.reports.service import _annotate_trades
from app.services.reviews.daily import calculation_versions
from app.services.risk.service import missing_r_breakdown
from app.services.signals.coverage import coverage_summary
from app.utils.analytics import decimal_str, ny_date_from_utc
from app.utils.hashing import json_dumps
from app.db.models.market_data import TradeExcursion


def week_bounds(week: date) -> tuple[date, date]:
    start = week - timedelta(days=week.weekday())
    end = start + timedelta(days=6)
    return start, end


def live_metrics_for_week(db: Session, week: date) -> dict:
    start, end = week_bounds(week)
    filt = DashboardFilters(start_date=start, end_date=end)
    trades = list(build_closed_trades_query(db, filt).all())
    rows = [_trade_row(t) for t in trades]
    summary = _serialize_summary(_summary_stats(rows))
    daily = _daily_rows(rows)
    rs = [t.r_multiple for t in trades if t.r_multiple is not None]
    r_stats = r_statistics(rs)
    pf, pf_st = profit_factor([r["pnl"] for r in rows])

    best_day = max(daily, key=lambda d: d["net_pnl"]) if daily else None
    worst_day = min(daily, key=lambda d: d["net_pnl"]) if daily else None

    # Peak-to-trough on this week's daily P&L (same realized P&L as dashboard)
    dd_points = []
    peak = Decimal("0")
    cum = Decimal("0")
    for d in daily:
        cum += d["net_pnl"]
        if cum > peak:
            peak = cum
        dd_points.append({"date": d["date"], "drawdown_dollars": str(cum - peak), "drawdown_pct": None})
    dd = summarize_drawdown(dd_points, False)

    ids = [t.id for t in trades]
    excursions = (
        db.query(TradeExcursion).filter(TradeExcursion.trade_id.in_(ids)).all() if ids else []
    )
    mfe = [e.mfe_r for e in excursions if e.mfe_r is not None]
    eff = [e.exit_efficiency_pct for e in excursions if e.exit_efficiency_pct is not None]
    left = [e.r_left_on_table for e in excursions if e.r_left_on_table is not None]
    risk = missing_r_breakdown(db, trades)
    signals = coverage_summary(db, trades)

    return {
        "week_start": start.isoformat(),
        "week_end": end.isoformat(),
        "summary": summary,
        "average_r": decimal_str(r_stats.get("average")),
        "median_r": decimal_str(r_stats.get("median")),
        "profit_factor": decimal_str(pf),
        "profit_factor_status": pf_st,
        "best_day": best_day["date"] if best_day else None,
        "worst_day": worst_day["date"] if worst_day else None,
        "max_drawdown": dd.get("max_dollars"),
        "avg_mfe_r": decimal_str(sum(mfe) / len(mfe) if mfe else None),
        "avg_exit_efficiency_pct": decimal_str(sum(eff) / len(eff) if eff else None),
        "avg_r_left_on_table": decimal_str(sum(left) / len(left) if left else None),
        "r_coverage_pct": risk.get("r_coverage_pct"),
        "signal_coverage_pct": signals.get("strategy_coverage_pct"),
        "excursion_coverage_pct": round(len(excursions) / len(trades) * 100, 1) if trades else 0,
        "daily": [
            {**d, "net_pnl": decimal_str(d["net_pnl"]), "win_rate": decimal_str(d["win_rate"]), "gross_pnl": decimal_str(d["gross_pnl"]), "fees": decimal_str(d["fees"]), "cumulative_pnl": decimal_str(d["cumulative_pnl"])}
            for d in daily
        ],
        "trade_count": len(trades),
    }


def observed_patterns(db: Session, week: date) -> list[dict]:
    start, end = week_bounds(week)
    filt = DashboardFilters(start_date=start, end_date=end)
    trades = list(build_closed_trades_query(db, filt).all())
    if not trades:
        return []
    annotated = _annotate_trades(db, trades, TradeFilterSet())
    groups = {
        "day_of_week": defaultdict(list),
        "entry_15m": defaultdict(list),
        "setup_quality": defaultdict(list),
        "signal_rvol_bucket": defaultdict(list),
        "retracement_bucket": defaultdict(list),
    }
    for at in annotated:
        for key in groups:
            val = at.features.get(key) or "unknown"
            groups[key][val].append(at)
    out = []
    for dim, buckets in groups.items():
        items = []
        for label, ats in buckets.items():
            pnls = [a.pnl for a in ats]
            items.append({
                "label": label,
                "trades": len(ats),
                "net_pnl": decimal_str(sum(pnls, Decimal("0"))),
                "research_href": f"/research?{dim}={label}",
            })
        items.sort(key=lambda x: x["trades"], reverse=True)
        out.append({"dimension": dim, "caption": "Observed this week.", "buckets": items[:8]})
    return out


def get_or_create(db: Session, week: date) -> WeeklyReview:
    start, end = week_bounds(week)
    row = db.query(WeeklyReview).filter(WeeklyReview.week_start_date == start.isoformat()).first()
    if row:
        return row
    row = WeeklyReview(week_start_date=start.isoformat(), week_end_date=end.isoformat(), status="NOT_STARTED")
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def patch_review(db: Session, week: date, payload: dict) -> WeeklyReview:
    row = get_or_create(db, week)
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


def complete_review(db: Session, week: date, *, refresh_snapshot: bool = False) -> WeeklyReview:
    row = get_or_create(db, week)
    metrics = live_metrics_for_week(db, week)
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


def review_payload(db: Session, week: date) -> dict:
    row = get_or_create(db, week)
    prompts = json.loads(row.prompt_fields_json) if row.prompt_fields_json else {}
    return {
        "id": row.id,
        "week_start": row.week_start_date,
        "week_end": row.week_end_date,
        "status": row.status,
        "body": row.body,
        "prompt_fields": prompts,
        "prompt_labels": WEEKLY_PROMPTS,
        "live_metrics": live_metrics_for_week(db, week),
        "metrics_snapshot": json.loads(row.metrics_snapshot_json) if row.metrics_snapshot_json else None,
        "calculation_versions": json.loads(row.calculation_versions_json) if row.calculation_versions_json else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "patterns": observed_patterns(db, week),
    }


def review_history(db: Session) -> dict:
    from app.db.models.reviews import DailyReview

    dailies = db.query(DailyReview).order_by(DailyReview.ny_date.desc()).limit(90).all()
    weeklies = db.query(WeeklyReview).order_by(WeeklyReview.week_start_date.desc()).limit(52).all()

    def _snap(raw: str | None) -> dict:
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    daily_out = []
    for r in dailies:
        snap = _snap(r.metrics_snapshot_json)
        daily_out.append({
            "date": r.ny_date,
            "status": r.status,
            "net_pnl": (snap.get("summary") or {}).get("net_pnl"),
            "average_r": snap.get("average_r"),
        })
    weekly_out = []
    for r in weeklies:
        snap = _snap(r.metrics_snapshot_json)
        weekly_out.append({
            "week_start": r.week_start_date,
            "week_end": r.week_end_date,
            "status": r.status,
            "net_pnl": (snap.get("summary") or {}).get("net_pnl"),
            "average_r": snap.get("average_r"),
        })
    return {"daily": daily_out, "weekly": weekly_out}
