"""Aggregate trades into report buckets."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from app.services.analytics.expectancy import profit_factor
from app.services.reports.features import AnnotatedTrade
from app.utils.analytics import avg_decimal, decimal_str, win_rate_pct


def aggregate_dimension(
    trades: list[AnnotatedTrade],
    feature_key: str,
    label_map: dict[str, str] | None = None,
    sort_keys: list[str] | None = None,
    min_sample: int = 1,
    exclude_missing: bool = False,
) -> list[dict]:
    groups: dict[str, list[AnnotatedTrade]] = defaultdict(list)
    for at in trades:
        key = at.features.get(feature_key)
        if key in (None, "", "unknown"):
            if exclude_missing:
                continue
            key = key or "unknown"
        groups[key].append(at)

    buckets = []
    for key, items in groups.items():
        if len(items) < min_sample:
            continue
        label = _resolve_label(feature_key, key, items, label_map)
        b = _bucket_metrics(key, label, items)
        buckets.append(b)

    if sort_keys:
        order = {k: i for i, k in enumerate(sort_keys)}
        buckets.sort(key=lambda b: order.get(b["key"], 999))
    else:
        buckets.sort(key=lambda b: Decimal(b["net_pnl"]), reverse=True)

    return buckets


def _resolve_label(
    feature_key: str,
    key: str,
    items: list[AnnotatedTrade],
    label_map: dict[str, str] | None,
) -> str:
    if label_map and key in label_map:
        return label_map[key]
    if items:
        lbl = items[0].features.get(f"_label_{feature_key}")
        if lbl:
            return lbl
    if key == "16_plus":
        return "16:00+"
    if len(key) == 2 and key.isdigit():
        return f"{key}:00"
    return key.replace("-", "–")


def _excursion_vals(items: list[AnnotatedTrade], attr: str) -> list[Decimal]:
    vals = []
    for at in items:
        ex = at.features.get("_excursion")
        if ex is None:
            continue
        v = getattr(ex, attr, None)
        if v is not None:
            vals.append(v)
    return vals


def _bucket_metrics(key: str, label: str, items: list[AnnotatedTrade]) -> dict:
    pnls = [at.pnl for at in items]
    wins = [at for at in items if at.outcome == "WIN"]
    losses = [at for at in items if at.outcome == "LOSS"]
    be = [at for at in items if at.outcome == "BREAKEVEN"]
    net = sum(pnls, Decimal("0"))
    win_pnls = [at.pnl for at in wins]
    loss_pnls = [at.pnl for at in losses]

    exc_available = sum(1 for at in items if at.features.get("excursion_available") == "yes")
    mfe_rs = _excursion_vals(items, "mfe_r")
    mae_rs = _excursion_vals(items, "mae_r")
    effs = _excursion_vals(items, "exit_efficiency_pct")
    r_lefts = _excursion_vals(items, "r_left_on_table")
    givebacks = _excursion_vals(items, "peak_giveback_pct")
    t_mfe = _excursion_vals(items, "time_to_mfe_seconds")
    r_values = []
    for at in items:
        r = getattr(at.trade, "r_multiple", None)
        if r is not None:
            r_values.append(r)
    r_qualified = len(r_values)
    r_pf, r_pf_status = profit_factor(r_values)
    total_r = sum(r_values, Decimal("0")) if r_values else None
    avg_r = (total_r / Decimal(r_qualified)) if r_qualified else None

    result = {
        "key": key,
        "label": label,
        "trade_count": len(items),
        "wins": len(wins),
        "losses": len(losses),
        "breakeven": len(be),
        "net_pnl": decimal_str(net),
        "avg_trade": decimal_str(net / Decimal(len(items))),
        "win_rate": decimal_str(win_rate_pct(len(wins), len(losses))),
        "avg_winner": decimal_str(sum(win_pnls, Decimal("0")) / Decimal(len(win_pnls))) if win_pnls else None,
        "avg_loser": decimal_str(sum(loss_pnls, Decimal("0")) / Decimal(len(loss_pnls))) if loss_pnls else None,
        "excursion_available": exc_available,
        "mfe_r_qualified_count": len(mfe_rs),
        "r_qualified_count": r_qualified,
        "excursion_coverage_pct": decimal_str(
            (Decimal(exc_available) / Decimal(len(items))) * Decimal("100")
        ) if items else None,
        "r_coverage_pct": decimal_str(
            (Decimal(r_qualified) / Decimal(len(items))) * Decimal("100")
        ) if items else None,
        "average_r": decimal_str(avg_r),
        "total_r": decimal_str(total_r),
        "r_profit_factor": decimal_str(r_pf),
        "r_profit_factor_status": r_pf_status,
        "average_mfe_r": decimal_str(avg_decimal(mfe_rs)),
        "average_mae_r": decimal_str(avg_decimal(mae_rs)),
        "average_exit_efficiency": decimal_str(avg_decimal(effs)),
        "average_r_left": decimal_str(avg_decimal(r_lefts)),
        "average_peak_giveback": decimal_str(avg_decimal(givebacks)),
        "average_time_to_mfe": decimal_str(avg_decimal(t_mfe)),
    }
    return result


def best_worst(buckets: list[dict], min_sample: int = 1) -> dict:
    eligible = [b for b in buckets if b["trade_count"] >= min_sample and b.get("net_pnl")]
    if not eligible:
        return {"best": None, "worst": None}
    best = max(eligible, key=lambda b: Decimal(b["net_pnl"]))
    worst = min(eligible, key=lambda b: Decimal(b["net_pnl"]))
    return {
        "best": {"key": best["key"], "label": best["label"], "net_pnl": best["net_pnl"], "trade_count": best["trade_count"]},
        "worst": {"key": worst["key"], "label": worst["label"], "net_pnl": worst["net_pnl"], "trade_count": worst["trade_count"]},
    }
