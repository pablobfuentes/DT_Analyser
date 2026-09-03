"""Pure feature calculations from ordered daily bars (Decimal-safe)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from app.market_data.quality import QualityStatus

CALCULATION_VERSION = "instrument-v1"
ZERO = Decimal("0")
HUNDRED = Decimal("100")


@dataclass
class SessionBar:
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int


@dataclass
class DayFeatureResult:
    prior_close: Decimal | None = None
    day_open: Decimal | None = None
    day_high: Decimal | None = None
    day_low: Decimal | None = None
    day_close: Decimal | None = None
    day_volume: int | None = None
    opening_gap_pct: Decimal | None = None
    daily_movement_pct: Decimal | None = None
    rvol50_multiple: Decimal | None = None
    prior_day_rvol50_multiple: Decimal | None = None
    true_range: Decimal | None = None
    atr14_prior: Decimal | None = None
    relative_volatility_pct: Decimal | None = None
    sma20_prior: Decimal | None = None
    sma50_prior: Decimal | None = None
    day_type: str | None = None
    quality_status: QualityStatus = QualityStatus.OK
    quality_flags: list[str] = field(default_factory=list)
    completeness_status: str = "COMPLETE"


def pct_change(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator is None or denominator == ZERO:
        return None
    return (numerator / denominator) * HUNDRED


def true_range(high: Decimal, low: Decimal, prior_close: Decimal | None) -> Decimal:
    if prior_close is None:
        return high - low
    return max(high - low, abs(high - prior_close), abs(low - prior_close))


def wilder_atr(tr_values: list[Decimal], period: int = 14) -> list[Decimal | None]:
    """Return ATR series aligned with tr_values; first period-1 are None."""
    if len(tr_values) < period:
        return [None] * len(tr_values)
    out: list[Decimal | None] = [None] * (period - 1)
    first = sum(tr_values[:period]) / Decimal(period)
    out.append(first)
    prev = first
    for tr in tr_values[period:]:
        prev = (prev * Decimal(period - 1) + tr) / Decimal(period)
        out.append(prev)
    return out


def avg_volume(volumes: list[int]) -> Decimal | None:
    if not volumes:
        return None
    return Decimal(sum(volumes)) / Decimal(len(volumes))


def rvol_multiple(current_volume: int, prior_volumes: list[int]) -> Decimal | None:
    if len(prior_volumes) < 50:
        return None
    baseline = avg_volume(prior_volumes[-50:])
    if baseline is None or baseline == ZERO:
        return None
    return Decimal(current_volume) / baseline


def classify_day_type(
    day_open: Decimal,
    day_high: Decimal,
    day_low: Decimal,
    day_close: Decimal,
    prev_high: Decimal,
    prev_low: Decimal,
) -> str:
    day_range = day_high - day_low
    if day_range <= ZERO:
        return "INSIDE_RANGE"

    open_pos = (day_open - day_low) / day_range
    close_pos = (day_close - day_low) / day_range

    if day_close > prev_high and open_pos <= Decimal("0.15") and close_pos >= Decimal("0.85"):
        return "TREND_UP"
    if day_close < prev_low and open_pos >= Decimal("0.85") and close_pos <= Decimal("0.15"):
        return "TREND_DOWN"
    if day_high <= prev_high and day_low >= prev_low:
        return "INSIDE_RANGE"
    return "OUTSIDE_RANGE"


def _add_flag(result: DayFeatureResult, flag: str) -> None:
    if flag not in result.quality_flags:
        result.quality_flags.append(flag)


def _set_primary_if_ok(result: DayFeatureResult, status: QualityStatus) -> None:
    if result.quality_status == QualityStatus.OK:
        result.quality_status = status


def compute_day_features(
    sessions: list[SessionBar],
    index: int,
    *,
    is_consolidated: bool,
    is_today_incomplete: bool = False,
    split_metadata_available: bool = False,
) -> DayFeatureResult:
    """Compute features for sessions[index] using prior sessions only for rolling metrics."""
    result = DayFeatureResult()
    if index <= 0 or index >= len(sessions):
        result.quality_status = QualityStatus.MISSING_BAR
        result.completeness_status = "FAILED"
        _add_flag(result, str(QualityStatus.MISSING_BAR))
        return result

    cur = sessions[index]
    prev = sessions[index - 1]
    prior_close = prev.close

    result.prior_close = prior_close
    result.day_open = cur.open
    result.day_high = cur.high
    result.day_low = cur.low
    result.day_close = cur.close
    result.day_volume = cur.volume

    if not is_consolidated:
        result.quality_status = QualityStatus.PARTIAL_FEED
        _add_flag(result, str(QualityStatus.PARTIAL_FEED))

    if not split_metadata_available:
        _add_flag(result, "SPLIT_METADATA_UNAVAILABLE")

    result.opening_gap_pct = pct_change(cur.open - prior_close, prior_close)

    # PRE_ENTRY rolling metrics — prior sessions only (current bar excluded)
    prior_sessions = sessions[:index]
    prior_vols = [s.volume for s in prior_sessions]
    if index >= 2:
        prev_vols = [s.volume for s in sessions[: index - 1]]
        result.prior_day_rvol50_multiple = rvol_multiple(prev.volume, prev_vols)
        if result.prior_day_rvol50_multiple is None and len(prev_vols) < 50:
            _add_flag(result, str(QualityStatus.INSUFFICIENT_HISTORY))
            _set_primary_if_ok(result, QualityStatus.INSUFFICIENT_HISTORY)

    tr_prior_series = [
        true_range(s.high, s.low, sessions[i - 1].close if i > 0 else None)
        for i, s in enumerate(prior_sessions)
    ]
    atr_prior_series = wilder_atr(tr_prior_series, 14)
    atr_prior = atr_prior_series[-1] if atr_prior_series else None
    result.atr14_prior = atr_prior
    if atr_prior is None and len(tr_prior_series) < 14:
        _add_flag(result, str(QualityStatus.INSUFFICIENT_HISTORY))
        _set_primary_if_ok(result, QualityStatus.INSUFFICIENT_HISTORY)

    closes = [s.close for s in prior_sessions]
    if len(closes) >= 20:
        result.sma20_prior = sum(closes[-20:]) / Decimal(20)
    else:
        _add_flag(result, str(QualityStatus.INSUFFICIENT_HISTORY))
        _set_primary_if_ok(result, QualityStatus.INSUFFICIENT_HISTORY)
    if len(closes) >= 50:
        result.sma50_prior = sum(closes[-50:]) / Decimal(50)

    if is_today_incomplete:
        result.completeness_status = "PRE_ENTRY_ONLY"
        _add_flag(result, str(QualityStatus.PENDING_EOD))
        _set_primary_if_ok(result, QualityStatus.PENDING_EOD)
        result.daily_movement_pct = None
        result.rvol50_multiple = None
        result.true_range = None
        result.relative_volatility_pct = None
        result.day_type = None
        return result

    result.daily_movement_pct = pct_change(cur.close - prior_close, prior_close)
    tr = true_range(cur.high, cur.low, prior_close)
    result.true_range = tr
    result.rvol50_multiple = rvol_multiple(cur.volume, prior_vols)
    if result.rvol50_multiple is None and len(prior_vols) < 50:
        _add_flag(result, str(QualityStatus.INSUFFICIENT_HISTORY))
        _set_primary_if_ok(result, QualityStatus.INSUFFICIENT_HISTORY)

    if atr_prior and atr_prior != ZERO:
        result.relative_volatility_pct = (tr / atr_prior) * HUNDRED

    result.day_type = classify_day_type(
        cur.open, cur.high, cur.low, cur.close, prev.high, prev.low
    )
    return result


def entry_vs_atr_pct(entry_price: Decimal, prior_close: Decimal, atr14_prior: Decimal | None) -> Decimal | None:
    if atr14_prior is None or atr14_prior == ZERO:
        return None
    return pct_change(entry_price - prior_close, atr14_prior)


def entry_vs_sma_pct(entry_price: Decimal, sma_prior: Decimal | None) -> Decimal | None:
    if sma_prior is None or sma_prior == ZERO:
        return None
    return pct_change(entry_price - sma_prior, sma_prior)
