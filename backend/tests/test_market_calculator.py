"""Tests for market feature calculations."""

from datetime import date, timedelta
from decimal import Decimal

from app.services.market_enrichment.calculator import (
    SessionBar,
    avg_volume,
    classify_day_type,
    compute_day_features,
    entry_vs_atr_pct,
    pct_change,
    rvol_multiple,
    true_range,
    wilder_atr,
)


def test_opening_gap_25_pct():
    sessions = [
        SessionBar(date(2026, 1, 1), Decimal("4"), Decimal("4.2"), Decimal("3.9"), Decimal("4"), 1_000_000),
        SessionBar(date(2026, 1, 2), Decimal("5"), Decimal("5.2"), Decimal("4.8"), Decimal("5"), 1_000_000),
    ]
    feat = compute_day_features(sessions, 1, is_consolidated=True)
    assert feat.opening_gap_pct == Decimal("25")


def test_daily_movement_20_pct():
    sessions = [
        SessionBar(date(2026, 1, 1), Decimal("4"), Decimal("4.2"), Decimal("3.9"), Decimal("4"), 1_000_000),
        SessionBar(date(2026, 1, 2), Decimal("4.1"), Decimal("4.9"), Decimal("4"), Decimal("4.8"), 1_000_000),
    ]
    feat = compute_day_features(sessions, 1, is_consolidated=True)
    assert feat.daily_movement_pct == Decimal("20")


def test_rvol50_5x():
    vols = [1_000_000] * 50 + [5_000_000]
    sessions = []
    start = date(2026, 1, 1)
    for i, v in enumerate(vols):
        sessions.append(
            SessionBar(start + timedelta(days=i), Decimal("10"), Decimal("10.5"), Decimal("9.5"), Decimal("10"), v)
        )
    feat = compute_day_features(sessions, 50, is_consolidated=True)
    assert feat.rvol50_multiple == Decimal("5")


def test_true_range_3():
    assert true_range(Decimal("12"), Decimal("9"), Decimal("10")) == Decimal("3")


def test_entry_vs_atr():
    result = entry_vs_atr_pct(Decimal("51"), Decimal("50"), Decimal("1.5"))
    assert result is not None
    assert abs(result - Decimal("66.66666666666666666666666667")) < Decimal("0.0001")


def test_relative_volatility_200_pct():
    tr = Decimal("3")
    atr = Decimal("1.5")
    assert (tr / atr) * Decimal("100") == Decimal("200")


def test_trend_up_day_type():
    dt = classify_day_type(
        Decimal("9.1"), Decimal("12"), Decimal("9"), Decimal("11.9"),
        Decimal("10.5"), Decimal("9.5"),
    )
    assert dt == "TREND_UP"


def test_wilder_atr_init():
    trs = [Decimal(str(i)) for i in range(1, 20)]
    atrs = wilder_atr(trs, 14)
    assert atrs[13] == sum(trs[:14]) / Decimal(14)
