"""Orchestrate Step 3 advanced dashboard analytics."""

from __future__ import annotations

from decimal import Decimal

from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.config import settings
from app.services.analytics.drawdown import (
    build_equity_series,
    equity_baseline,
    summarize_drawdown,
    summarize_r_drawdown,
)
from app.services.analytics.expectancy import (
    dollar_expectancy,
    payoff_ratio,
    profit_factor,
    r_statistics,
    serialize_r_stats,
)
from app.services.analytics.r_distribution import r_distribution
from app.services.analytics.streaks import compute_streaks
from app.utils.analytics import decimal_str

if TYPE_CHECKING:
    from app.services.dashboard_service import DashboardFilters


def build_advanced_analytics(db: Session, filters: "DashboardFilters", rows: list[dict]) -> dict:
    pnls = [r["pnl"] for r in rows]
    r_values = [r["trade"].r_multiple for r in rows if r["trade"].r_multiple is not None]

    exp = dollar_expectancy(pnls)
    pf, pf_status = profit_factor(pnls)
    payoff = payoff_ratio(pnls)
    r_stats = r_statistics(r_values)
    r_serialized = serialize_r_stats(r_stats, len(rows))
    r_pf, r_pf_status = profit_factor(r_values)
    r_payoff = payoff_ratio(r_values)

    threshold = Decimal(settings.loss_beyond_r_threshold)
    beyond = [r for r in r_values if r < threshold]
    two_r = sum(1 for r in r_values if r >= Decimal("2"))
    three_r = sum(1 for r in r_values if r >= Decimal("3"))

    outcomes = [r["outcome"] for r in rows]
    streaks = compute_streaks(outcomes)

    baseline = equity_baseline(db, filters)
    equity_series, pnl_series, r_series, dd_points = build_equity_series(rows, baseline)
    dd_summary = summarize_drawdown(dd_points, baseline["starting_equity_available"])
    r_dd = summarize_r_drawdown(r_series)

    period_baseline = baseline.get("baseline_equity")
    chart_equity = []
    for p in pnl_series:
        point = dict(p)
        if baseline["starting_equity_available"] and period_baseline is not None:
            point["equity"] = decimal_str(Decimal(p["cumulative_pnl"]) + period_baseline)
        chart_equity.append(point)

    warnings = []
    missing_r = len(rows) - len(r_values)
    if missing_r:
        warnings.append(
            f"{missing_r} closed trade(s) are missing initial risk and are excluded from R analytics."
        )
    gross_r_count = sum(
        1
        for r in rows
        if r["trade"].r_multiple is not None and not r.get("includes_fees", True)
    )
    if gross_r_count:
        warnings.append(f"{gross_r_count} R value(s) use gross P&L because fee data is unavailable.")

    return {
        "dollar_expectancy": decimal_str(exp),
        "profit_factor": decimal_str(pf),
        "profit_factor_status": pf_status,
        "payoff_ratio": decimal_str(payoff),
        "r": r_serialized,
        "drawdown": dd_summary,
        "streaks": streaks,
        "warnings": warnings,
        "r_distribution": r_distribution(r_values),
        "drawdown_series": dd_points,
        "equity_series": chart_equity,
        "cumulative_r_series": r_series,
        "period_baseline_equity": decimal_str(period_baseline) if period_baseline is not None else None,
        "equity_pct_available": baseline["starting_equity_available"],
        "r_profit_factor": decimal_str(r_pf),
        "r_profit_factor_status": r_pf_status,
        "r_payoff_ratio": decimal_str(r_payoff),
        "r_drawdown": r_dd,
        "loss_beyond_initial_risk": {
            "count": len(beyond),
            "pct": decimal_str((Decimal(len(beyond)) / Decimal(len(r_values)) * Decimal("100")) if r_values else None),
            "threshold": str(threshold),
        },
        "large_winners": {"two_r_plus": two_r, "three_r_plus": three_r},
        "drawdown_label": "Selected Cohort Drawdown",
    }


def extend_source_comparison_advanced(rows: list[dict], total_closed: int) -> dict:
    """Build advanced metrics for manual vs auto groups."""
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
            continue
        pnls = [r["pnl"] for r in grp]
        r_vals = [r["trade"].r_multiple for r in grp if r["trade"].r_multiple is not None]
        pf, pf_status = profit_factor(pnls)
        r_st = r_statistics(r_vals)
        baseline_pnl = Decimal("0")
        dd_points = []
        running_peak = Decimal("0")
        cum = Decimal("0")
        for r in grp:
            cum += r["pnl"]
            if cum > running_peak:
                running_peak = cum
            dd_points.append({"drawdown_dollars": str(cum - running_peak), "drawdown_pct": None, "date": ""})
        max_dd = min((Decimal(p["drawdown_dollars"]) for p in dd_points), default=Decimal("0"))
        streaks = compute_streaks([r["outcome"] for r in grp])
        r_cov = None
        if grp:
            r_cov = decimal_str((Decimal(len(r_vals)) / Decimal(len(grp))) * Decimal("100"))

        result[label] = {
            "dollar_expectancy": decimal_str(dollar_expectancy(pnls)),
            "profit_factor": decimal_str(pf),
            "profit_factor_status": pf_status,
            "payoff_ratio": decimal_str(payoff_ratio(pnls)),
            "r_expectancy": decimal_str(r_st.get("expectancy")),
            "average_r": decimal_str(r_st.get("average")),
            "max_drawdown_dollars": decimal_str(max_dd),
            "max_drawdown_pct": None,
            "longest_losing_streak": streaks["longest_loss"],
            "r_coverage_pct": r_cov,
        }
    return result
