"""Drawdown and equity curve calculations."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.db.models.account import Account
from app.db.models.trade import Trade
from app.utils.analytics import decimal_str, effective_realized_pnl, ny_date_from_utc, utc_bounds_for_ny_range

if TYPE_CHECKING:
    from app.services.dashboard_service import DashboardFilters


def _accounts_for_filters(db: Session, filters: "DashboardFilters") -> list[Account]:
    if filters.account_id:
        a = db.get(Account, filters.account_id)
        return [a] if a else []
    return db.query(Account).all()


def pre_period_realized_pnl(db: Session, filters: "DashboardFilters") -> Decimal:
    """Real account equity before the period: all prior realized P&L of selected account(s).

    Analytical cohort filters (direction, ticker, strategy, exploration) must NOT
    rewrite historical account equity. Account selection is the capital identity.
    Source is not treated as a separate account book.
    """
    if not filters.start_date:
        return Decimal("0")

    q = db.query(Trade).filter(Trade.status == "CLOSED", Trade.exit_time_utc.isnot(None))
    if filters.account_id:
        q = q.filter(Trade.account_id == filters.account_id)

    utc_start, _ = utc_bounds_for_ny_range(filters.start_date, filters.start_date)
    if utc_start:
        q = q.filter(Trade.exit_time_utc < utc_start)

    total = Decimal("0")
    for t in q.all():
        total += effective_realized_pnl(t).pnl
    return total


def equity_baseline(db: Session, filters: "DashboardFilters") -> dict:
    """
    Returns baseline for filtered-period equity curve.
    starting_equity_available: all selected accounts have starting_equity
    baseline_equity: sum(starting) + pre_period_pnl (when equity available)
    baseline_pnl: pre_period_pnl for P&L-only drawdown
    """
    accounts = _accounts_for_filters(db, filters)
    pre_pnl = pre_period_realized_pnl(db, filters)

    missing = [a for a in accounts if a.starting_equity is None]
    if missing or not accounts:
        return {
            "starting_equity_available": False,
            "baseline_equity": None,
            "baseline_pnl": pre_pnl,
            "starting_equity_sum": None,
        }

    starting = sum(a.starting_equity for a in accounts)
    return {
        "starting_equity_available": True,
        "baseline_equity": starting + pre_pnl,
        "baseline_pnl": pre_pnl,
        "starting_equity_sum": starting,
    }


def build_equity_series(rows: list[dict], baseline: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """
    rows: sorted trade rows with pnl, r_multiple, exit_time
    Returns (equity_series, pnl_series, cumulative_r_series)
    """
    cumulative_pnl = baseline["baseline_pnl"]
    cumulative_r = Decimal("0")
    equity = baseline["baseline_equity"]
    has_equity = baseline["starting_equity_available"]

    equity_series: list[dict] = []
    pnl_series: list[dict] = []
    r_series: list[dict] = []
    r_count = 0

    running_peak_equity = equity if has_equity and equity is not None else Decimal("0")
    running_peak_pnl = cumulative_pnl
    trades_since_peak = 0

    drawdown_points: list[dict] = []

    for r in rows:
        t = r["trade"]
        pnl = r["pnl"]
        exit_dt = t.exit_time_utc
        exit_date = ny_date_from_utc(exit_dt).isoformat() if exit_dt else None

        cumulative_pnl += pnl
        pnl_series.append(
            {
                "date": exit_date,
                "exit_time_utc": exit_dt.isoformat() if exit_dt else None,
                "cumulative_pnl": decimal_str(cumulative_pnl),
                "trade_id": t.id,
            }
        )

        if r.get("r_multiple") is not None:
            cumulative_r += r["r_multiple"]
            r_count += 1
            r_series.append(
                {
                    "date": exit_date,
                    "exit_time_utc": exit_dt.isoformat() if exit_dt else None,
                    "cumulative_r": decimal_str(cumulative_r),
                    "r_trades_included": r_count,
                }
            )

        if has_equity and equity is not None:
            equity += pnl
            if equity > running_peak_equity:
                running_peak_equity = equity
                trades_since_peak = 0
            else:
                trades_since_peak += 1
            dd_d = equity - running_peak_equity
            dd_pct = (dd_d / running_peak_equity * Decimal("100")) if running_peak_equity > 0 else None
            equity_series.append(
                {
                    "date": exit_date,
                    "exit_time_utc": exit_dt.isoformat() if exit_dt else None,
                    "equity": decimal_str(equity),
                    "peak": decimal_str(running_peak_equity),
                    "drawdown_dollars": decimal_str(dd_d),
                    "drawdown_pct": decimal_str(dd_pct),
                    "trades_since_peak": trades_since_peak,
                }
            )
            drawdown_points.append(
                {
                    "date": exit_date,
                    "exit_time_utc": exit_dt.isoformat() if exit_dt else None,
                    "drawdown_dollars": decimal_str(dd_d),
                    "drawdown_pct": decimal_str(dd_pct),
                    "peak": decimal_str(running_peak_equity),
                    "equity": decimal_str(equity),
                    "trades_since_peak": trades_since_peak,
                    "mode": "equity",
                }
            )
        else:
            if cumulative_pnl > running_peak_pnl:
                running_peak_pnl = cumulative_pnl
                trades_since_peak = 0
            else:
                trades_since_peak += 1
            dd_d = cumulative_pnl - running_peak_pnl
            drawdown_points.append(
                {
                    "date": exit_date,
                    "exit_time_utc": exit_dt.isoformat() if exit_dt else None,
                    "drawdown_dollars": decimal_str(dd_d),
                    "drawdown_pct": None,
                    "peak": decimal_str(running_peak_pnl),
                    "equity": decimal_str(cumulative_pnl),
                    "trades_since_peak": trades_since_peak,
                    "mode": "pnl",
                }
            )

    return equity_series, pnl_series, r_series, drawdown_points


def summarize_drawdown(drawdown_points: list[dict], has_equity_pct: bool) -> dict:
    if not drawdown_points:
        return {
            "max_dollars": None,
            "max_pct": None,
            "max_duration_trading_days": 0,
            "max_duration_calendar_days": 0,
            "current_dollars": None,
            "current_pct": None,
            "current_duration_trading_days": 0,
            "current_duration_calendar_days": 0,
            "current_is_active": False,
            "label": "Max Drawdown — Selected Cohort",
            "duration_type": "calendar_days",
            "duration_label": "Calendar Days Underwater",
            "pct_available": has_equity_pct,
        }

    max_dd = min(Decimal(p["drawdown_dollars"]) for p in drawdown_points)
    current = drawdown_points[-1]
    current_dd = Decimal(current["drawdown_dollars"])
    current_pct = Decimal(current["drawdown_pct"]) if current.get("drawdown_pct") else None

    max_pct = None
    if has_equity_pct:
        pcts = [Decimal(p["drawdown_pct"]) for p in drawdown_points if p.get("drawdown_pct")]
        max_pct = min(pcts) if pcts else None

    # Max duration: longest stretch where drawdown < 0
    max_duration = 0
    current_duration = 0
    in_dd = False
    dd_start_date: date | None = None
    peak_dates: set[str] = set()

    for p in drawdown_points:
        dd = Decimal(p["drawdown_dollars"])
        d = p["date"]
        if dd == 0:
            if in_dd and dd_start_date and d:
                end = date.fromisoformat(d)
                days = (end - dd_start_date).days + 1
                max_duration = max(max_duration, days)
            in_dd = False
            dd_start_date = None
        else:
            if not in_dd and d:
                in_dd = True
                dd_start_date = date.fromisoformat(d)

    if in_dd and dd_start_date and drawdown_points[-1]["date"]:
        end = date.fromisoformat(drawdown_points[-1]["date"])
        current_duration = (end - dd_start_date).days + 1
        max_duration = max(max_duration, current_duration)

    current_active = current_dd < 0

    return {
        "max_dollars": decimal_str(max_dd),
        "max_pct": decimal_str(max_pct) if max_pct is not None else None,
        "max_duration_trading_days": max_duration,
        "max_duration_calendar_days": max_duration,
        "current_dollars": decimal_str(current_dd),
        "current_pct": decimal_str(current_pct) if current_pct is not None else None,
        "current_duration_trading_days": current_duration if current_active else 0,
        "current_duration_calendar_days": current_duration if current_active else 0,
        "current_is_active": current_active,
        "label": "Max Drawdown — Selected Cohort",
        "duration_type": "calendar_days",
        "duration_label": "Calendar Days Underwater",
        "pct_available": has_equity_pct,
    }


def summarize_r_drawdown(r_series: list[dict]) -> dict:
    """Peak-to-trough of cumulative R. Independent of account equity."""
    if not r_series:
        return {
            "max_r": None,
            "current_r": None,
            "current_is_active": False,
            "label": "Max R Drawdown — Selected Cohort",
        }
    peak = Decimal("0")
    max_dd = Decimal("0")
    current_dd = Decimal("0")
    for p in r_series:
        cum = Decimal(p["cumulative_r"])
        if cum > peak:
            peak = cum
        current_dd = cum - peak
        if current_dd < max_dd:
            max_dd = current_dd
    return {
        "max_r": decimal_str(max_dd),
        "current_r": decimal_str(current_dd),
        "current_is_active": current_dd < 0,
        "label": "Max R Drawdown — Selected Cohort",
    }
