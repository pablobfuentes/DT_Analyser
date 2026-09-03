"""Dashboard aggregation service."""

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session, Query

from app.db.models.account import Account
from app.db.models.import_batch import ImportBatch
from app.db.models.import_error import ImportError
from app.db.models.trade import Trade
from app.services.analytics.advanced import build_advanced_analytics, extend_source_comparison_advanced
from app.services.analytics.drawdown import equity_baseline
from app.utils.analytics import (
    RealizedPnl,
    analytics_tz,
    avg_decimal,
    breakeven_tolerance,
    classify_outcome,
    decimal_str,
    effective_realized_pnl,
    map_source_filter,
    ny_date_from_utc,
    utc_bounds_for_ny_range,
    win_rate_pct,
)


@dataclass
class DashboardFilters:
    start_date: date | None = None
    end_date: date | None = None
    account_id: int | None = None
    source_type: str | None = None
    direction: str | None = None
    ticker: str | None = None


def build_closed_trades_query(db: Session, filters: DashboardFilters) -> Query:
    q = db.query(Trade).filter(Trade.status == "CLOSED", Trade.exit_time_utc.isnot(None))

    if filters.account_id:
        q = q.filter(Trade.account_id == filters.account_id)
    src = map_source_filter(filters.source_type)
    if src:
        q = q.filter(Trade.source_type == src)
    if filters.direction and filters.direction.upper() != "ALL":
        q = q.filter(Trade.direction == filters.direction.upper())
    if filters.ticker:
        q = q.filter(Trade.ticker.ilike(f"%{filters.ticker.strip()}%"))

    utc_start, utc_end = utc_bounds_for_ny_range(filters.start_date, filters.end_date)
    if utc_start:
        q = q.filter(Trade.exit_time_utc >= utc_start)
    if utc_end:
        q = q.filter(Trade.exit_time_utc <= utc_end)

    return q.order_by(Trade.exit_time_utc.asc())


def _trade_row(trade: Trade) -> dict:
    rp = effective_realized_pnl(trade)
    outcome = classify_outcome(rp.pnl)
    return {
        "trade": trade,
        "pnl": rp.pnl,
        "includes_fees": rp.includes_fees,
        "outcome": outcome,
        "r_multiple": trade.r_multiple,
    }


def _summary_stats(rows: list[dict]) -> dict:
    tol = breakeven_tolerance()
    wins = [r for r in rows if r["outcome"] == "WIN"]
    losses = [r for r in rows if r["outcome"] == "LOSS"]
    breakevens = [r for r in rows if r["outcome"] == "BREAKEVEN"]

    pnls = [r["pnl"] for r in rows]
    net_pnl = sum(pnls, Decimal("0"))
    gross_pnl = sum((r["trade"].gross_pnl or Decimal("0")) for r in rows)
    fees = sum((r["trade"].fees or Decimal("0")) for r in rows)

    win_pnls = [r["pnl"] for r in wins]
    loss_pnls = [r["pnl"] for r in losses]

    best = max(pnls) if pnls else None
    worst = min(pnls) if pnls else None

    hold_times = [r["trade"].holding_seconds for r in rows if r["trade"].holding_seconds is not None]
    avg_hold = int(sum(hold_times) / len(hold_times)) if hold_times else None

    total_shares = sum((r["trade"].quantity for r in rows), Decimal("0"))
    missing_fees = sum(1 for r in rows if not r["includes_fees"] and r["trade"].fees is None)
    pnl_mismatch = sum(1 for r in rows if r["trade"].pnl_mismatch_flag)

    return {
        "trades": len(rows),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(breakevens),
        "net_pnl": net_pnl,
        "gross_pnl": gross_pnl,
        "fees": fees,
        "win_rate": win_rate_pct(len(wins), len(losses)),
        "avg_trade": avg_decimal(pnls),
        "avg_winner": avg_decimal(win_pnls),
        "avg_loser": avg_decimal(loss_pnls),
        "best_trade": best,
        "worst_trade": worst,
        "avg_hold_seconds": avg_hold,
        "total_shares": total_shares,
        "missing_fees_count": missing_fees,
        "pnl_mismatch_count": pnl_mismatch,
    }


def _daily_rows(rows: list[dict]) -> list[dict]:
    by_day: dict[date, list[dict]] = {}
    for r in rows:
        exit_dt = r["trade"].exit_time_utc
        if exit_dt is None:
            continue
        d = ny_date_from_utc(exit_dt)
        by_day.setdefault(d, []).append(r)

    daily = []
    cumulative = Decimal("0")
    for d in sorted(by_day.keys()):
        day_rows = by_day[d]
        day_pnl = sum(r["pnl"] for r in day_rows)
        cumulative += day_pnl
        wins = sum(1 for r in day_rows if r["outcome"] == "WIN")
        losses = sum(1 for r in day_rows if r["outcome"] == "LOSS")
        be = sum(1 for r in day_rows if r["outcome"] == "BREAKEVEN")
        gross = sum((r["trade"].gross_pnl or Decimal("0")) for r in day_rows)
        fees = sum((r["trade"].fees or Decimal("0")) for r in day_rows)
        daily.append({
            "date": d.isoformat(),
            "trades": len(day_rows),
            "wins": wins,
            "losses": losses,
            "breakeven": be,
            "win_rate": win_rate_pct(wins, losses),
            "gross_pnl": gross,
            "fees": fees,
            "net_pnl": day_pnl,
            "cumulative_pnl": cumulative,
        })
    return daily


def _classify_day(net_pnl: Decimal) -> str:
    tol = breakeven_tolerance()
    if net_pnl > tol:
        return "GREEN"
    if net_pnl < -tol:
        return "RED"
    return "BREAKEVEN"


def _equity_section(db: Session, filters: DashboardFilters, net_pnl: Decimal) -> dict:
    """Period-start equity uses Step 7 equity_baseline (starting + prior realized P&L)."""
    baseline = equity_baseline(db, filters)
    if not baseline["starting_equity_available"]:
        accounts = []
        if filters.account_id:
            a = db.get(Account, filters.account_id)
            accounts = [a] if a else []
        else:
            accounts = db.query(Account).all()
        missing = [a for a in accounts if a is None or a.starting_equity is None]
        reason = None
        if not accounts:
            reason = None
        elif missing:
            reason = f"{len(missing)} account(s) missing starting equity"
        return {
            "starting_equity": None,
            "current_realized_equity": None,
            "realized_return_pct": None,
            "available": False,
            "reason": reason,
        }

    period_start = baseline["baseline_equity"]
    starting_sum = baseline["starting_equity_sum"]
    current = period_start + net_pnl
    ret_pct = (net_pnl / period_start * Decimal("100")) if period_start and period_start > 0 else None
    return {
        "starting_equity": decimal_str(period_start),
        "account_starting_equity": decimal_str(starting_sum),
        "current_realized_equity": decimal_str(current),
        "realized_return_pct": decimal_str(ret_pct) if ret_pct is not None else None,
        "available": True,
    }


def _source_comparison(rows: list[dict]) -> dict:
    groups = {"TRADINGVIEW_MANUAL": [], "TRADINGVIEW_AUTO": []}
    for r in rows:
        st = r["trade"].source_type
        if st in groups:
            groups[st].append(r)

    result = {}
    for key, label in [("TRADINGVIEW_MANUAL", "manual"), ("TRADINGVIEW_AUTO", "auto")]:
        grp = groups[key]
        if not grp:
            result[label] = None
        else:
            stats = _summary_stats(grp)
            result[label] = _serialize_summary(stats)
    return result


def _serialize_summary(stats: dict) -> dict:
    return {
        "trades": stats["trades"],
        "wins": stats["wins"],
        "losses": stats["losses"],
        "breakeven": stats["breakeven"],
        "net_pnl": decimal_str(stats["net_pnl"]),
        "gross_pnl": decimal_str(stats["gross_pnl"]),
        "fees": decimal_str(stats["fees"]),
        "win_rate": decimal_str(stats["win_rate"]) if stats["win_rate"] is not None else None,
        "avg_trade": decimal_str(stats["avg_trade"]),
        "avg_winner": decimal_str(stats["avg_winner"]),
        "avg_loser": decimal_str(stats["avg_loser"]),
        "best_trade": decimal_str(stats["best_trade"]),
        "worst_trade": decimal_str(stats["worst_trade"]),
        "avg_hold_seconds": stats["avg_hold_seconds"],
    }


def _recent_trades(rows: list[dict], limit: int = 10) -> list[dict]:
    sorted_rows = sorted(
        rows,
        key=lambda r: (
            r["trade"].exit_time_utc or datetime.min.replace(tzinfo=timezone.utc),
            r["trade"].id or 0,
        ),
        reverse=True,
    )
    recent = []
    for r in sorted_rows[:limit]:
        t = r["trade"]
        recent.append({
            "id": t.id,
            "exit_time_utc": t.exit_time_utc.isoformat() if t.exit_time_utc else None,
            "ticker": t.ticker,
            "source_type": t.source_type,
            "direction": t.direction,
            "quantity": decimal_str(t.quantity),
            "avg_entry_price": decimal_str(t.avg_entry_price),
            "avg_exit_price": decimal_str(t.avg_exit_price),
            "net_pnl": decimal_str(r["pnl"]),
            "holding_seconds": t.holding_seconds,
        })
    return recent


def get_dashboard(db: Session, filters: DashboardFilters) -> dict:
    closed_q = build_closed_trades_query(db, filters)
    trades = closed_q.all()
    rows = [_trade_row(t) for t in trades]

    summary = _summary_stats(rows)
    daily = _daily_rows(rows)

    green_days = sum(1 for d in daily if _classify_day(Decimal(d["net_pnl"])) == "GREEN")
    red_days = sum(1 for d in daily if _classify_day(Decimal(d["net_pnl"])) == "RED")
    be_days = sum(1 for d in daily if _classify_day(Decimal(d["net_pnl"])) == "BREAKEVEN")

    # Open trades count (same filters except status)
    open_q = db.query(Trade).filter(Trade.status == "OPEN")
    if filters.account_id:
        open_q = open_q.filter(Trade.account_id == filters.account_id)
    src = map_source_filter(filters.source_type)
    if src:
        open_q = open_q.filter(Trade.source_type == src)
    if filters.direction and filters.direction.upper() != "ALL":
        open_q = open_q.filter(Trade.direction == filters.direction.upper())
    if filters.ticker:
        open_q = open_q.filter(Trade.ticker.ilike(f"%{filters.ticker.strip()}%"))
    open_count = open_q.count()

    warnings = []
    if summary["missing_fees_count"]:
        warnings.append(f"{summary['missing_fees_count']} trades do not contain fee data.")
    if summary["pnl_mismatch_count"]:
        warnings.append(f"{summary['pnl_mismatch_count']} trades contain a P&L validation mismatch.")
    if open_count:
        warnings.append(f"{open_count} imported trades are OPEN and excluded from realized statistics.")

    opening_q = (
        db.query(ImportError)
        .join(ImportBatch, ImportError.import_batch_id == ImportBatch.id)
        .filter(
            ImportError.error_type == "UNKNOWN_OPENING_POSITION",
            ImportError.resolved_at.is_(None),
        )
    )
    if filters.account_id:
        opening_q = opening_q.filter(ImportBatch.account_id == filters.account_id)
    opening_count = opening_q.count()
    if opening_count:
        warnings.append(
            f"{opening_count} ticker(s) have UNKNOWN_OPENING_POSITION: history starts with "
            "SELL and SHORT opening assumed the account was FLAT. Import earlier fills if "
            "this closed a prior LONG."
        )

    equity = _equity_section(db, filters, summary["net_pnl"])
    if not equity.get("available") and equity.get("reason"):
        warnings.append(equity["reason"])

    advanced = build_advanced_analytics(db, filters, rows)
    warnings.extend(advanced.pop("warnings", []))
    source_advanced = extend_source_comparison_advanced(rows, len(rows))

    return {
        "filters": {
            "start_date": filters.start_date.isoformat() if filters.start_date else None,
            "end_date": filters.end_date.isoformat() if filters.end_date else None,
            "account_id": filters.account_id,
            "source_type": filters.source_type,
            "direction": filters.direction,
            "ticker": filters.ticker,
            "analytics_timezone": str(analytics_tz()),
        },
        "summary": _serialize_summary(summary),
        "secondary": {
            "trading_days": len(daily),
            "green_days": green_days,
            "red_days": red_days,
            "breakeven_days": be_days,
            "open_trades": open_count,
        },
        "equity": equity,
        "daily": [
            {
                **d,
                "net_pnl": decimal_str(d["net_pnl"]),
                "gross_pnl": decimal_str(d["gross_pnl"]),
                "fees": decimal_str(d["fees"]),
                "cumulative_pnl": decimal_str(d["cumulative_pnl"]),
                "win_rate": decimal_str(d["win_rate"]) if d["win_rate"] is not None else None,
                "day_type": _classify_day(d["net_pnl"]),
            }
            for d in sorted(daily, key=lambda x: x["date"], reverse=True)
        ],
        "cumulative": [
            {"date": d["date"], "daily_pnl": decimal_str(d["net_pnl"]), "cumulative_pnl": decimal_str(d["cumulative_pnl"]), "trades": d["trades"]}
            for d in daily
        ],
        "source_comparison": _source_comparison(rows),
        "source_comparison_advanced": source_advanced,
        "recent_trades": _recent_trades(rows),
        "warnings": warnings,
        "empty": len(rows) == 0,
        "advanced": {
            "dollar_expectancy": advanced["dollar_expectancy"],
            "profit_factor": advanced["profit_factor"],
            "profit_factor_status": advanced["profit_factor_status"],
            "payoff_ratio": advanced["payoff_ratio"],
            "r": advanced["r"],
            "drawdown": advanced["drawdown"],
            "streaks": advanced["streaks"],
            "r_profit_factor": advanced.get("r_profit_factor"),
            "r_profit_factor_status": advanced.get("r_profit_factor_status"),
            "r_payoff_ratio": advanced.get("r_payoff_ratio"),
            "r_drawdown": advanced.get("r_drawdown"),
            "loss_beyond_initial_risk": advanced.get("loss_beyond_initial_risk"),
            "large_winners": advanced.get("large_winners"),
            "drawdown_label": advanced.get("drawdown_label"),
            "period_baseline_equity": advanced.get("period_baseline_equity"),
            "equity_pct_available": advanced.get("equity_pct_available"),
        },
        "r_distribution": advanced["r_distribution"],
        "drawdown_series": advanced["drawdown_series"],
        "equity_series": advanced["equity_series"],
        "cumulative_r_series": advanced["cumulative_r_series"],
    }
