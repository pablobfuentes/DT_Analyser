"""Rolling metrics with no lookahead. Strategy version markers."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from app.services.analytics.expectancy import profit_factor
from app.services.reports.features import AnnotatedTrade
from app.services.research.cohorts import numeric_of
from app.utils.analytics import classify_outcome, decimal_str, ny_date_from_utc, win_rate_pct


def _chrono(rows: list[AnnotatedTrade]) -> list[AnnotatedTrade]:
    return sorted(rows, key=lambda at: (at.trade.exit_time_utc or at.trade.entry_time_utc, at.trade.id))


def _window_metrics(window: list[AnnotatedTrade], metric: str) -> tuple[str | None, int, int]:
    n = len(window)
    rs = [numeric_of(at, "actual_r") for at in window]
    r_ok = [r for r in rs if r is not None]
    pnls = [at.pnl for at in window]
    if metric == "average_r":
        val = (sum(r_ok, Decimal("0")) / Decimal(len(r_ok))) if r_ok else None
    elif metric == "avg_trade":
        val = (sum(pnls, Decimal("0")) / Decimal(n)) if n else None
    elif metric == "win_rate":
        wins = sum(1 for at in window if classify_outcome(at.pnl) == "WIN")
        losses = sum(1 for at in window if classify_outcome(at.pnl) == "LOSS")
        val = win_rate_pct(wins, losses)
    elif metric == "profit_factor":
        pf, _ = profit_factor(pnls)
        val = pf
    elif metric == "average_mfe_r":
        xs = [numeric_of(at, "mfe_r") for at in window]
        xs = [x for x in xs if x is not None]
        val = (sum(xs, Decimal("0")) / Decimal(len(xs))) if xs else None
    elif metric == "exit_efficiency":
        xs = [numeric_of(at, "exit_efficiency_pct") for at in window]
        xs = [x for x in xs if x is not None]
        val = (sum(xs, Decimal("0")) / Decimal(len(xs))) if xs else None
    else:
        val = None
    return decimal_str(val), n, len(r_ok)


def build_rolling(
    rows: list[AnnotatedTrade],
    *,
    metric: str = "average_r",
    window: int = 20,
    calendar_days: int | None = None,
) -> dict:
    ordered = _chrono(rows)
    points = []
    for i, at in enumerate(ordered):
        if calendar_days:
            end = at.trade.exit_time_utc or at.trade.entry_time_utc
            start = end - timedelta(days=calendar_days)
            win = [
                x
                for x in ordered[: i + 1]
                if (x.trade.exit_time_utc or x.trade.entry_time_utc) >= start
            ]
        else:
            win = ordered[max(0, i + 1 - window) : i + 1]
        value, n, r_n = _window_metrics(win, metric)
        d = ny_date_from_utc(at.trade.exit_time_utc or at.trade.entry_time_utc)
        points.append(
            {
                "index": i + 1,
                "trade_id": at.trade.id,
                "date": d.isoformat() if d else None,
                "value": value,
                "window_n": n,
                "window_r_qualified": r_n,
            }
        )

    markers = []
    prev = None
    for i, at in enumerate(ordered):
        ver = at.features.get("strategy_version")
        if ver and ver != prev:
            d = ny_date_from_utc(at.trade.exit_time_utc or at.trade.entry_time_utc)
            markers.append({"index": i + 1, "trade_id": at.trade.id, "strategy_version": ver, "date": d.isoformat() if d else None})
            prev = ver
        elif ver:
            prev = ver

    return {
        "metric": metric,
        "window": window if not calendar_days else None,
        "calendar_days": calendar_days,
        "points": points,
        "version_markers": markers,
        "n": len(ordered),
        "note": "Window uses chronological trades only (current + prior). Not silently R-qualified-only.",
    }


def cumulative_r_series(rows: list[AnnotatedTrade], name: str) -> dict:
    ordered = _chrono(rows)
    cum = Decimal("0")
    pts = []
    for i, at in enumerate(ordered):
        r = numeric_of(at, "actual_r")
        if r is None:
            continue
        cum += r
        d = ny_date_from_utc(at.trade.exit_time_utc or at.trade.entry_time_utc)
        pts.append({"index": i + 1, "trade_id": at.trade.id, "date": d.isoformat() if d else None, "cumulative_r": str(cum)})
    return {
        "name": name,
        "points": pts,
        "label": "Independent cohort sequences; not synchronized trades.",
    }
