"""Cohort summaries, observed differences, coverage."""

from __future__ import annotations

from decimal import Decimal

from app.services.analytics.drawdown import summarize_drawdown, summarize_r_drawdown
from app.services.analytics.expectancy import profit_factor, r_statistics
from app.services.reports.features import AnnotatedTrade
from app.services.research.cohorts import numeric_of
from app.services.research.statistics import (
    bootstrap_difference_ci,
    bootstrap_mean_ci,
    bootstrap_median_ci,
    sample_size_label,
    wilson_interval,
)
from app.utils.analytics import classify_outcome, decimal_str, win_rate_pct


def _r_values(rows: list[AnnotatedTrade]) -> list[Decimal]:
    out = []
    for at in rows:
        r = numeric_of(at, "actual_r")
        if r is not None:
            out.append(r)
    return out


def _exc_vals(rows: list[AnnotatedTrade], key: str) -> list[Decimal]:
    out = []
    for at in rows:
        v = numeric_of(at, key)
        if v is not None:
            out.append(v)
    return out


def summarize_cohort(rows: list[AnnotatedTrade]) -> dict:
    n = len(rows)
    pnls = [at.pnl for at in rows]
    rs = _r_values(rows)
    mfe = _exc_vals(rows, "mfe_r")
    mae = _exc_vals(rows, "mae_r")
    eff = _exc_vals(rows, "exit_efficiency_pct")
    left = _exc_vals(rows, "r_left_on_table")
    outcomes = [classify_outcome(p) for p in pnls]
    wins = sum(1 for o in outcomes if o == "WIN")
    losses = sum(1 for o in outcomes if o == "LOSS")
    be = sum(1 for o in outcomes if o == "BREAKEVEN")
    r_stats = r_statistics(rs)
    pf, pf_st = profit_factor(pnls)
    r_pf, r_pf_st = profit_factor(rs)
    wr = win_rate_pct(wins, losses)
    # drawdown on cohort sequence (selected cohort)
    peak = Decimal("0")
    eq = Decimal("0")
    max_dd = Decimal("0")
    r_series = []
    cum_r = Decimal("0")
    for at in sorted(rows, key=lambda x: (x.trade.exit_time_utc or x.trade.entry_time_utc, x.trade.id)):
        eq += at.pnl
        if eq > peak:
            peak = eq
        dd = eq - peak
        if dd < max_dd:
            max_dd = dd
        r = numeric_of(at, "actual_r")
        if r is not None:
            cum_r += r
            r_series.append({"cumulative_r": str(cum_r)})
    r_dd = summarize_r_drawdown(r_series) if r_series else {"max_r": None}
    mean_ci = bootstrap_mean_ci(rs) if rs else {"available": False, "n": 0}
    med_ci = bootstrap_median_ci(rs) if rs else {"available": False, "n": 0}
    wr_ci = wilson_interval(wins, losses)
    return {
        "trades": n,
        "sample_label": sample_size_label(n),
        "r_qualified": len(rs),
        "excursion_qualified": len(mfe),
        "r_coverage_pct": decimal_str((Decimal(len(rs)) / Decimal(n) * 100) if n else None),
        "excursion_coverage_pct": decimal_str((Decimal(len(mfe)) / Decimal(n) * 100) if n else None),
        "net_pnl": decimal_str(sum(pnls, Decimal("0")) if n else None),
        "avg_trade": decimal_str((sum(pnls, Decimal("0")) / Decimal(n)) if n else None),
        "win_rate": decimal_str(wr),
        "wins": wins,
        "losses": losses,
        "breakeven": be,
        "average_r": decimal_str(r_stats.get("average")),
        "median_r": decimal_str(r_stats.get("median")),
        "total_r": decimal_str(sum(rs, Decimal("0")) if rs else None),
        "profit_factor": decimal_str(pf),
        "profit_factor_status": pf_st,
        "r_profit_factor": decimal_str(r_pf),
        "r_profit_factor_status": r_pf_st,
        "avg_winner_r": decimal_str(r_stats.get("avg_winner")),
        "avg_loser_r": decimal_str(r_stats.get("avg_loser")),
        "max_drawdown_dollars": decimal_str(max_dd if n else None),
        "max_drawdown_r": r_dd.get("max_r"),
        "average_mfe_r": decimal_str((sum(mfe, Decimal("0")) / Decimal(len(mfe))) if mfe else None),
        "average_mae_r": decimal_str((sum(mae, Decimal("0")) / Decimal(len(mae))) if mae else None),
        "exit_efficiency": decimal_str((sum(eff, Decimal("0")) / Decimal(len(eff))) if eff else None),
        "r_left_on_table": decimal_str((sum(left, Decimal("0")) / Decimal(len(left))) if left else None),
        "avg_r_ci": mean_ci,
        "median_r_ci": med_ci,
        "win_rate_ci": wr_ci,
        "trade_ids": [at.trade.id for at in rows],
    }


def _diff(a, b):
    if a is None or b is None:
        return None
    return Decimal(a) - Decimal(b)


def compare_summaries(sum_a: dict, sum_b: dict, *, overlap_count: int, independent: bool) -> dict:
    keys = [
        "trades",
        "win_rate",
        "average_r",
        "median_r",
        "total_r",
        "profit_factor",
        "r_profit_factor",
        "avg_trade",
        "net_pnl",
        "average_mfe_r",
        "average_mae_r",
        "exit_efficiency",
        "max_drawdown_r",
        "max_drawdown_dollars",
    ]
    rows = []
    for k in keys:
        av, bv = sum_a.get(k), sum_b.get(k)
        d = None
        try:
            if av is not None and bv is not None:
                d = decimal_str(_diff(av, bv))
        except Exception:
            d = None
        rows.append({"metric": k, "cohort_a": av, "cohort_b": bv, "observed_difference": d})
    delta = None
    if independent:
        # reconstruct R lists from summaries is not enough — caller should pass
        delta = {
            "available": False,
            "reason": "COMPUTED_IN_SERVICE",
        }
    else:
        delta = {
            "available": False,
            "reason": "COHORTS_OVERLAP",
            "message": "Independent cohort comparison unavailable because cohorts overlap.",
            "overlap_count": overlap_count,
        }
    return {"rows": rows, "difference_label": "Observed Difference", "mean_r_difference": delta}


def coverage_panel(universe: list[AnnotatedTrade], a: list[AnnotatedTrade], b: list[AnnotatedTrade]) -> dict:
    def pct(rows, pred):
        if not rows:
            return None
        ok = sum(1 for at in rows if pred(at))
        return decimal_str(Decimal(ok) / Decimal(len(rows)) * 100)

    def has_r(at):
        return numeric_of(at, "actual_r") is not None

    def has_sig(at):
        return at.features.get("_signal_linked") == "true"

    def has_mkt(at):
        return at.features.get("_market_enriched") == "true"

    def has_exc(at):
        return numeric_of(at, "mfe_r") is not None

    a_exc = pct(a, has_exc)
    b_exc = pct(b, has_exc)
    warn = None
    try:
        if a_exc is not None and b_exc is not None and abs(float(a_exc) - float(b_exc)) >= 20:
            warn = "Comparison may be affected by unequal data availability."
    except Exception:
        pass
    return {
        "base_trades": len(universe),
        "cohort_a": len(a),
        "cohort_b": len(b),
        "r_available_pct": pct(universe, has_r),
        "signal_available_pct": pct(universe, has_sig),
        "market_available_pct": pct(universe, has_mkt),
        "excursion_available_pct": pct(universe, has_exc),
        "cohort_a_excursion_pct": a_exc,
        "cohort_b_excursion_pct": b_exc,
        "unequal_coverage_warning": warn,
    }
