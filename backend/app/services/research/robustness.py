"""Outlier trim, concentration, subperiod, chronological split. Temporary compute only."""

from __future__ import annotations

from decimal import Decimal

from app.services.analytics.expectancy import profit_factor, r_statistics
from app.services.reports.features import AnnotatedTrade
from app.services.research.cohorts import numeric_of
from app.services.research.comparison import summarize_cohort
from app.utils.analytics import classify_outcome, decimal_str, ny_date_from_utc, win_rate_pct


def _chrono(rows: list[AnnotatedTrade]) -> list[AnnotatedTrade]:
    return sorted(rows, key=lambda at: (at.trade.exit_time_utc or at.trade.entry_time_utc, at.trade.id))


def _mean_r(rows: list[AnnotatedTrade]) -> Decimal | None:
    rs = [numeric_of(at, "actual_r") for at in rows]
    rs = [r for r in rs if r is not None]
    if not rs:
        return None
    return sum(rs, Decimal("0")) / Decimal(len(rs))


def trim_rows(rows: list[AnnotatedTrade], mode: str) -> list[AnnotatedTrade]:
    """mode: none | trim_1 | trim_2_5 | trim_5 — trim by Actual R extremes."""
    if mode in (None, "none"):
        return list(rows)
    scored = [(numeric_of(at, "actual_r"), at) for at in rows]
    scored = [(r, at) for r, at in scored if r is not None]
    scored.sort(key=lambda x: x[0])
    n = len(scored)
    if n < 3:
        return [at for _, at in scored]
    if mode == "trim_1":
        keep = scored[1:-1] if n > 2 else scored
    else:
        pct = Decimal("0.025") if mode == "trim_2_5" else Decimal("0.05")
        k = int((n * pct).to_integral_value())
        k = max(1, k) if n >= 20 else 1
        keep = scored[k : n - k] if n - 2 * k >= 1 else scored
    kept_ids = {at.trade.id for _, at in keep}
    return [at for at in rows if at.trade.id in kept_ids]


def robustness_means(rows: list[AnnotatedTrade]) -> dict:
    all_m = _mean_r(rows)
    out = {"all": decimal_str(all_m), "n_all": len(rows)}
    for mode, label in (("trim_1", "trim_top_bottom_1"), ("trim_2_5", "trim_2_5_pct"), ("trim_5", "trim_5_pct")):
        trimmed = trim_rows(rows, mode)
        out[label] = {"average_r": decimal_str(_mean_r(trimmed)), "n": len(trimmed)}
    return out


def concentration(rows: list[AnnotatedTrade]) -> dict:
    rs = [(numeric_of(at, "actual_r"), at.trade.id) for at in rows]
    rs = [(r, tid) for r, tid in rs if r is not None]
    total = sum((r for r, _ in rs), Decimal("0"))
    if not rs:
        return {"available": False, "reason": "NO_R"}
    if total <= 0:
        worst = min(rs, key=lambda x: x[0])
        best = max(rs, key=lambda x: x[0])
        return {
            "available": False,
            "reason": "NONPOSITIVE_TOTAL_R",
            "message": "Percentage contribution is misleading when total R ≤ 0. Showing absolute extremes.",
            "top_1_r": str(best[0]),
            "worst_1_r": str(worst[0]),
            "total_r": str(total),
        }
    pos = sorted(rs, key=lambda x: x[0], reverse=True)
    neg = sorted(rs, key=lambda x: x[0])

    def share(k: int | None, pct: Decimal | None, seq):
        if k is not None:
            take = seq[:k]
        else:
            n = max(1, int((len(seq) * pct).to_integral_value()))
            take = seq[:n]
        s = sum((x[0] for x in take), Decimal("0"))
        return {"n": len(take), "r": str(s), "pct_of_total_r": str((s / total) * 100)}

    return {
        "available": True,
        "total_r": str(total),
        "top_1": share(1, None, pos),
        "top_5_pct": share(None, Decimal("0.05"), pos),
        "top_10_pct": share(None, Decimal("0.10"), pos),
        "worst_1": share(1, None, neg),
        "worst_5_pct": share(None, Decimal("0.05"), neg),
        "worst_10_pct": share(None, Decimal("0.10"), neg),
    }


def subperiod_halves(rows: list[AnnotatedTrade]) -> dict:
    ordered = _chrono(rows)
    if not ordered:
        return {"first_half": None, "second_half": None}
    mid = len(ordered) // 2
    return {
        "first_half": summarize_cohort(ordered[:mid] if mid else ordered[:1]),
        "second_half": summarize_cohort(ordered[mid:] if mid else []),
        "note": "Chronological half split of the selected cohort. Not labeled as decay.",
    }


def month_matrix(rows: list[AnnotatedTrade]) -> list[dict]:
    buckets: dict[str, list[AnnotatedTrade]] = {}
    for at in rows:
        d = ny_date_from_utc(at.trade.exit_time_utc or at.trade.entry_time_utc)
        key = d.strftime("%Y-%m") if d else "unknown"
        buckets.setdefault(key, []).append(at)
    out = []
    for month in sorted(buckets):
        s = summarize_cohort(buckets[month])
        out.append(
            {
                "month": month,
                "trades": s["trades"],
                "average_r": s["average_r"],
                "win_rate": s["win_rate"],
                "profit_factor": s["profit_factor"],
            }
        )
    return out


def stability_split(rows: list[AnnotatedTrade]) -> dict:
    ordered = _chrono(rows)
    odd = ordered[0::2]
    even = ordered[1::2]
    return {
        "label": "Stability Split",
        "note": "Alternating chronological trades. Not proper out-of-sample validation.",
        "odd": summarize_cohort(odd),
        "even": summarize_cohort(even),
    }


def chrono_split(rows: list[AnnotatedTrade], research_pct: int = 70) -> dict:
    if research_pct not in (50, 70, 80):
        raise ValueError("Split must be 50, 70, or 80")
    ordered = _chrono(rows)
    n = len(ordered)
    cut = int(n * research_pct / 100)
    research, validation = ordered[:cut], ordered[cut:]
    return {
        "research_pct": research_pct,
        "validation_pct": 100 - research_pct,
        "shuffled": False,
        "research": summarize_cohort(research),
        "validation": summarize_cohort(validation),
        "research_ids": [at.trade.id for at in research],
        "validation_ids": [at.trade.id for at in validation],
        "note": "Chronological split only. Trades were not shuffled.",
    }
