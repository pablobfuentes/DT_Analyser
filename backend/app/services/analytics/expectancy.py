"""Expectancy, profit factor, and payoff analytics."""

from __future__ import annotations

from decimal import Decimal

from app.utils.analytics import avg_decimal, decimal_str


def dollar_expectancy(pnls: list[Decimal]) -> Decimal | None:
    if not pnls:
        return None
    return sum(pnls, Decimal("0")) / Decimal(len(pnls))


def profit_factor(pnls: list[Decimal]) -> tuple[Decimal | None, str]:
    if not pnls:
        return None, "NO_TRADES"
    gross_profits = sum((p for p in pnls if p > 0), Decimal("0"))
    gross_losses = abs(sum((p for p in pnls if p < 0), Decimal("0")))
    if gross_losses == 0:
        if gross_profits > 0:
            return None, "NO_LOSSES"
        return None, "NO_WINS"
    if gross_profits == 0:
        return Decimal("0"), "FINITE"
    return gross_profits / gross_losses, "FINITE"


def payoff_ratio(pnls: list[Decimal]) -> Decimal | None:
    winners = [p for p in pnls if p > 0]
    losers = [p for p in pnls if p < 0]
    avg_w = avg_decimal(winners)
    avg_l = avg_decimal(losers)
    if avg_w is None or avg_l is None or avg_l == 0:
        return None
    return avg_w / abs(avg_l)


def r_statistics(r_values: list[Decimal]) -> dict:
    if not r_values:
        return {
            "trade_count": 0,
            "missing_count": 0,
            "coverage_pct": None,
            "average": None,
            "median": None,
            "expectancy": None,
            "avg_winner": None,
            "avg_loser": None,
            "best": None,
            "worst": None,
        }

    sorted_r = sorted(r_values)
    n = len(sorted_r)
    mid = n // 2
    if n % 2 == 1:
        median = sorted_r[mid]
    else:
        median = (sorted_r[mid - 1] + sorted_r[mid]) / Decimal("2")

    winners = [r for r in r_values if r > 0]
    losers = [r for r in r_values if r < 0]

    return {
        "trade_count": n,
        "average": sum(r_values, Decimal("0")) / Decimal(n),
        "median": median,
        "expectancy": sum(r_values, Decimal("0")) / Decimal(n),
        "avg_winner": avg_decimal(winners),
        "avg_loser": avg_decimal(losers),
        "best": max(r_values),
        "worst": min(r_values),
    }


def serialize_r_stats(stats: dict, total_closed: int) -> dict:
    missing = total_closed - stats.get("trade_count", 0)
    coverage = None
    if total_closed > 0:
        coverage = (Decimal(stats.get("trade_count", 0)) / Decimal(total_closed)) * Decimal("100")

    return {
        "trade_count": stats.get("trade_count", 0),
        "missing_count": missing,
        "coverage_pct": decimal_str(coverage),
        "average": decimal_str(stats.get("average")),
        "median": decimal_str(stats.get("median")),
        "expectancy": decimal_str(stats.get("expectancy")),
        "avg_winner": decimal_str(stats.get("avg_winner")),
        "avg_loser": decimal_str(stats.get("avg_loser")),
        "best": decimal_str(stats.get("best")),
        "worst": decimal_str(stats.get("worst")),
    }
