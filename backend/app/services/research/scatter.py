"""Scatter extraction, coverage, Spearman, OLS."""

from __future__ import annotations

from app.services.reports.features import AnnotatedTrade
from app.services.research.cohorts import numeric_of
from app.services.research.statistics import ols_trend, pearson, spearman
from app.services.research.timing import LookaheadFilterError
from app.services.research.variables import PRE_ENTRY_CLASSES, variable_by_key
from app.utils.analytics import ny_date_from_utc


def build_scatter(
    rows: list[AnnotatedTrade],
    x_key: str,
    y_key: str,
    research_mode: str,
) -> dict:
    xv = variable_by_key(x_key)
    yv = variable_by_key(y_key)
    if not xv or not yv:
        raise ValueError("Unknown scatter variable")
    if not xv["allowed_as_x"] or not yv["allowed_as_y"]:
        raise ValueError("Variable not allowed on that axis")
    if research_mode == "PRE_ENTRY_ONLY" and xv["timing_class"] not in PRE_ENTRY_CLASSES:
        # Y may be an outcome (Actual R). X used as a predictor must be pre-entry.
        raise LookaheadFilterError([x_key])

    missing_x = missing_y = missing_both = 0
    points = []
    xs: list[float] = []
    ys: list[float] = []
    for at in rows:
        x = numeric_of(at, x_key)
        y = numeric_of(at, y_key)
        if x is None and y is None:
            missing_both += 1
            continue
        if x is None:
            missing_x += 1
            continue
        if y is None:
            missing_y += 1
            continue
        t = at.trade
        sig = getattr(at, "signal", None)
        points.append(
            {
                "trade_id": t.id,
                "date": (ny_date_from_utc(t.exit_time_utc or t.entry_time_utc) or "").isoformat()
                if ny_date_from_utc(t.exit_time_utc or t.entry_time_utc)
                else None,
                "ticker": t.ticker,
                "direction": t.direction,
                "strategy": sig.strategy_version if sig else None,
                "actual_r": str(numeric_of(at, "actual_r")) if numeric_of(at, "actual_r") is not None else None,
                "x": float(x),
                "y": float(y),
            }
        )
        xs.append(float(x))
        ys.append(float(y))

    return {
        "x": xv,
        "y": yv,
        "total": len(rows),
        "plotted": len(points),
        "missing_x": missing_x,
        "missing_y": missing_y,
        "missing_both": missing_both,
        "points": points,
        "spearman": spearman(xs, ys),
        "pearson": pearson(xs, ys),
        "trend": ols_trend(xs, ys),
        "trend_warning": "Descriptive relationship only.",
    }
