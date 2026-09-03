"""Derive per-trade analysis features (in-memory, NY timezone)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.db.models.trade import Trade
from app.services.reports.config import (
    DAILY_PNL_STATE_BUCKETS,
    DURATION_BUCKETS_SEC,
    ENTRY_PRICE_BUCKETS,
    POSITION_VALUE_BUCKETS,
    QUANTITY_BUCKETS,
    WEEKDAYS,
)
from app.utils.analytics import TradeOutcome, analytics_tz, classify_outcome, effective_realized_pnl, ny_date_from_utc


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass
class AnnotatedTrade:
    trade: Trade
    pnl: Decimal
    outcome: TradeOutcome
    features: dict[str, str] = field(default_factory=dict)


def _bucket_numeric(value: Decimal, buckets) -> tuple[str, str]:
    for key, label, lo, hi in buckets:
        if lo is not None and value < lo:
            continue
        if hi is not None and value >= hi:
            continue
        return key, label
    return buckets[-1][0], buckets[-1][1]


def _bucket_duration(seconds: int | None) -> tuple[str, str]:
    if seconds is None:
        return "unknown", "Unknown"
    for key, label, lo, hi in DURATION_BUCKETS_SEC:
        if hi is None and seconds >= lo:
            return key, label
        if lo <= seconds < (hi or 999999999):
            return key, label
    return "60_plus", "60+ min"


def _entry_hour_bucket(dt: datetime) -> tuple[str, str, str, str]:
    local = _ensure_utc(dt).astimezone(analytics_tz())
    h = local.hour
    m = local.minute
    hour_key = f"{h:02d}" if h < 16 else "16_plus"
    hour_label = f"{h:02d}:00" if h < 16 else "16:00+"

    m30 = (m // 30) * 30
    m15 = (m // 15) * 15
    end30 = m30 + 30
    eh30 = h + end30 // 60
    em30 = end30 % 60
    key30 = f"{h:02d}:{m30:02d}-{eh30:02d}:{em30:02d}"
    label30 = key30.replace("-", "–")

    end15 = m15 + 15
    eh15 = h + end15 // 60
    em15 = end15 % 60
    key15 = f"{h:02d}:{m15:02d}-{eh15:02d}:{em15:02d}"
    label15 = key15.replace("-", "–")

    return hour_key, hour_label, key30, key15


def _weekday(dt: datetime) -> tuple[str, str]:
    wd = _ensure_utc(dt).astimezone(analytics_tz()).weekday()
    keys = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    labels = [w[1] for w in WEEKDAYS]
    return keys[wd], labels[wd]


def _month_week_day(dt: datetime) -> tuple[str, str, str]:
    local = _ensure_utc(dt).astimezone(analytics_tz())
    month_key = local.strftime("%Y-%m")
    month_label = local.strftime("%b %Y")
    # Week label: Monday of week
    week_start = local.date()
    week_start = week_start.fromordinal(week_start.toordinal() - week_start.weekday())
    week_end = week_start.fromordinal(week_start.toordinal() + 4)
    week_key = week_start.isoformat()
    week_label = f"{week_start.strftime('%b %d')}–{week_end.strftime('%b %d')}"
    dom_key = str(local.day)
    return month_key, week_key, dom_key


def _pnl_bucket(pnl: Decimal) -> tuple[str, str]:
    """Fixed P&L histogram buckets using Decimal (no float)."""
    if pnl < Decimal("-500"):
        return "lt_neg_500", "< -$500"
    if pnl < Decimal("-200"):
        return "neg_500_200", "-$500 to -$200"
    if pnl < Decimal("-50"):
        return "neg_200_50", "-$200 to -$50"
    if pnl < Decimal("0"):
        return "neg_50_0", "-$50 to $0"
    if pnl == Decimal("0"):
        return "zero", "$0"
    if pnl <= Decimal("50"):
        return "0_50", "$0 to $50"
    if pnl <= Decimal("200"):
        return "50_200", "$50 to $200"
    if pnl <= Decimal("500"):
        return "200_500", "$200 to $500"
    return "gt_500", "> $500"


def compute_base_features(
    trade: Trade,
    exec_meta: dict | None = None,
) -> dict[str, str]:
    rp = effective_realized_pnl(trade)
    outcome = classify_outcome(rp.pnl)
    entry = _ensure_utc(trade.entry_time_utc)
    pos_val = trade.avg_entry_price * trade.quantity

    wd_key, wd_label = _weekday(entry)
    eh_key, eh_label, k30, k15 = _entry_hour_bucket(entry)
    month_key, week_key, dom = _month_week_day(entry)
    month_label = entry.astimezone(analytics_tz()).strftime("%b %Y")
    week_start = entry.astimezone(analytics_tz()).date()
    week_start = week_start.fromordinal(week_start.toordinal() - week_start.weekday())
    week_end = week_start.fromordinal(week_start.toordinal() + 4)
    week_label = f"{week_start.strftime('%b %d')}–{week_end.strftime('%b %d')}"
    dur_key, _ = _bucket_duration(trade.holding_seconds)
    price_key, _ = _bucket_numeric(trade.avg_entry_price, ENTRY_PRICE_BUCKETS)
    qty_key, _ = _bucket_numeric(trade.quantity, QUANTITY_BUCKETS)
    pv_key, _ = _bucket_numeric(pos_val, POSITION_VALUE_BUCKETS)
    pnl_b_key, _ = _pnl_bucket(rp.pnl)

    src = "MANUAL" if trade.source_type == "TRADINGVIEW_MANUAL" else "AUTO"

    features = {
        "day_of_week": wd_key,
        "_label_day_of_week": wd_label,
        "entry_hour": eh_key,
        "_label_entry_hour": eh_label,
        "entry_30m": k30,
        "_label_entry_30m": k30.replace("-", "–"),
        "entry_15m": k15,
        "_label_entry_15m": k15.replace("-", "–"),
        "month": month_key,
        "_label_month": month_label,
        "week": week_key,
        "_label_week": week_label,
        "day_of_month": dom,
        "duration": dur_key,
        "entry_price": price_key,
        "quantity": qty_key,
        "position_value": pv_key,
        "symbol": trade.ticker.upper(),
        "source": src,
        "direction": trade.direction,
        "outcome": outcome,
        "pnl_bucket": pnl_b_key,
    }

    if exec_meta:
        features["fill_count"] = exec_meta.get("fill_count", "unknown")
        features["entry_style"] = exec_meta.get("entry_style", "unknown")
        features["exit_style"] = exec_meta.get("exit_style", "unknown")
    else:
        features["fill_count"] = "1"
        features["entry_style"] = "single"
        features["exit_style"] = "single"

    return features


def apply_behavior_features(
    annotated: list[AnnotatedTrade],
) -> None:
    """Mutate features with behavior dimensions (no lookahead). O(n log n)."""
    by_account_day: dict[tuple[int, str], list[AnnotatedTrade]] = {}
    for at in annotated:
        d = ny_date_from_utc(_ensure_utc(at.trade.entry_time_utc)).isoformat()
        by_account_day.setdefault((at.trade.account_id, d), []).append(at)

    for group in by_account_day.values():
        group.sort(key=lambda x: (_ensure_utc(x.trade.entry_time_utc), x.trade.id))
        for i, at in enumerate(group):
            num = i + 1
            at.features["trade_number"] = "5_plus" if num >= 5 else str(num)

    events: list[tuple[datetime, int, AnnotatedTrade]] = []
    for at in annotated:
        entry = _ensure_utc(at.trade.entry_time_utc)
        events.append((entry, 1, at))
        if at.trade.exit_time_utc:
            events.append((_ensure_utc(at.trade.exit_time_utc), 0, at))
    events.sort(key=lambda e: (e[0], e[1], e[2].trade.id))

    day_pnl: dict[tuple[int, str], Decimal] = {}
    last_outcome: dict[int, str | None] = {}
    loss_streak: dict[int, int] = {}

    for ts, kind, at in events:
        acct = at.trade.account_id
        if kind == 1:
            day = ny_date_from_utc(ts).isoformat()
            realized = day_pnl.get((acct, day), Decimal("0"))
            dkey, _ = _bucket_numeric(realized, DAILY_PNL_STATE_BUCKETS)
            at.features["daily_pnl_state"] = dkey

            prev = last_outcome.get(acct)
            if prev is None:
                at.features["prev_outcome"] = "FIRST"
                at.features["consec_losses"] = "0"
            else:
                at.features["prev_outcome"] = prev
                streak = loss_streak.get(acct, 0)
                at.features["consec_losses"] = "3_plus" if streak >= 3 else str(streak)
        else:
            day = ny_date_from_utc(ts).isoformat()
            key = (acct, day)
            day_pnl[key] = day_pnl.get(key, Decimal("0")) + at.pnl
            last_outcome[acct] = at.outcome
            if at.outcome == "LOSS":
                loss_streak[acct] = loss_streak.get(acct, 0) + 1
            else:
                loss_streak[acct] = 0
