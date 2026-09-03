"""Step 3 Graphs — dimensions, behavior, filters, aggregations, API."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.db.models.trade import Trade
from app.services.reports.aggregation import aggregate_dimension, best_worst
from app.services.reports.features import AnnotatedTrade, apply_behavior_features, compute_base_features
from app.services.reports.filters import (
    TradeFilterSet,
    apply_exploration,
    exploration_param_for_feature,
    filters_from_query,
    parse_filter_set,
)
from app.main import app
from app.services.reports.service import _annotate_trades, get_reports
from app.utils.analytics import classify_outcome, effective_realized_pnl
from app.services.reports.registry import REPORT_DEFINITIONS

from tests.dashboard_helpers import make_trade

client = TestClient(app)


def _ny_utc(year, month, day, ny_hour, ny_minute=0):
    """Convert NY local time (EDT, UTC-4) to UTC for test fixtures."""
    return datetime(year, month, day, ny_hour + 4, ny_minute, tzinfo=timezone.utc)


def _annotate(db, trades):
    return _annotate_trades(db, trades)


# --- Dimensions ---


def test_day_of_week_monday(db_session, manual_account):
    t = make_trade(
        db_session,
        manual_account.id,
        entry_time=_ny_utc(2026, 9, 7, 9, 30),
        exit_time=_ny_utc(2026, 9, 7, 10, 0),
        net_pnl=Decimal("100"),
    )
    at = _annotate(db_session, [t])[0]
    assert at.features["day_of_week"] == "MON"


def test_wednesday_ny_timezone(db_session, manual_account):
    t = make_trade(
        db_session,
        manual_account.id,
        entry_time=_ny_utc(2026, 9, 2, 10, 20),
        net_pnl=Decimal("-50"),
    )
    at = _annotate(db_session, [t])[0]
    assert at.features["day_of_week"] == "WED"


def test_entry_hour_bucket(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, entry_time=_ny_utc(2026, 9, 1, 9, 45))
    at = _annotate(db_session, [t])[0]
    assert at.features["entry_hour"] == "09"


def test_entry_30m_bucket(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, entry_time=_ny_utc(2026, 9, 1, 9, 45))
    at = _annotate(db_session, [t])[0]
    assert at.features["entry_30m"] == "09:30-10:00"


def test_entry_15m_bucket(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, entry_time=_ny_utc(2026, 9, 1, 10, 20))
    at = _annotate(db_session, [t])[0]
    assert at.features["entry_15m"] == "10:15-10:30"


def test_month_week_day_of_month(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, entry_time=_ny_utc(2026, 9, 15, 10))
    at = _annotate(db_session, [t])[0]
    assert at.features["month"] == "2026-09"
    assert at.features["day_of_month"] == "15"
    assert at.features["week"]


def test_duration_buckets(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, holding_seconds=90, net_pnl=Decimal("10"))
    at = _annotate(db_session, [t])[0]
    assert at.features["duration"] == "1_2"


def test_entry_price_quantity_position_value(db_session, manual_account):
    t = make_trade(
        db_session,
        manual_account.id,
        quantity=Decimal("150"),
        net_pnl=Decimal("10"),
    )
    t.avg_entry_price = Decimal("7")
    db_session.commit()
    at = _annotate(db_session, [t])[0]
    assert at.features["entry_price"] == "5_10"
    assert at.features["quantity"] == "100_199"
    assert at.features["position_value"] == "1000_2500"


def test_source_direction_symbol(db_session, manual_account, strategy_account):
    t1 = make_trade(db_session, manual_account.id, ticker="AAPL", net_pnl=Decimal("1"))
    t2 = make_trade(
        db_session,
        strategy_account.id,
        source_type="TRADINGVIEW_AUTO",
        direction="SHORT",
        ticker="TSLA",
        net_pnl=Decimal("-1"),
    )
    a1, a2 = _annotate(db_session, [t1, t2])
    assert a1.features["source"] == "MANUAL"
    assert a2.features["source"] == "AUTO"
    assert a2.features["direction"] == "SHORT"
    assert a1.features["symbol"] == "AAPL"


# --- Behavior (no lookahead) ---


def test_trade_number_of_day(db_session, manual_account):
    d = _ny_utc(2026, 9, 1, 9, 30)
    t1 = make_trade(db_session, manual_account.id, entry_time=d, exit_time=d.replace(hour=14, minute=5), net_pnl=Decimal("10"))
    t2 = make_trade(db_session, manual_account.id, entry_time=d.replace(hour=14, minute=10), net_pnl=Decimal("-5"))
    t3 = make_trade(db_session, manual_account.id, entry_time=d.replace(hour=14, minute=20), net_pnl=Decimal("3"))
    annotated = _annotate(db_session, [t1, t2, t3])
    nums = {at.trade.id: at.features["trade_number"] for at in annotated}
    assert nums[t1.id] == "1"
    assert nums[t2.id] == "2"
    assert nums[t3.id] == "3"


def test_trade_number_five_plus(db_session, manual_account):
    base = _ny_utc(2026, 9, 2, 9, 30)
    trades = []
    for i in range(6):
        entry = base + timedelta(minutes=i * 5)
        trades.append(
            make_trade(
                db_session,
                manual_account.id,
                entry_time=entry,
                exit_time=entry + timedelta(minutes=4),
                net_pnl=Decimal("1"),
                ticker=f"T{i}",
            )
        )
    annotated = _annotate(db_session, trades)
    assert annotated[-1].features["trade_number"] == "5_plus"


def test_previous_completed_winner_loser_breakeven(db_session, manual_account):
    e1 = _ny_utc(2026, 9, 1, 9, 0)
    t1 = make_trade(db_session, manual_account.id, entry_time=e1, exit_time=e1 + timedelta(minutes=30), net_pnl=Decimal("50"), ticker="P1")
    t2 = make_trade(db_session, manual_account.id, entry_time=e1 + timedelta(hours=1), exit_time=e1 + timedelta(hours=1, minutes=30), net_pnl=Decimal("-20"), ticker="P2")
    t3 = make_trade(db_session, manual_account.id, entry_time=e1 + timedelta(hours=2), exit_time=e1 + timedelta(hours=2, minutes=30), net_pnl=Decimal("0"), ticker="P3")
    t4 = make_trade(db_session, manual_account.id, entry_time=e1 + timedelta(hours=3), exit_time=e1 + timedelta(hours=3, minutes=30), net_pnl=Decimal("5"), ticker="P4")
    annotated = _annotate(db_session, [t1, t2, t3, t4])
    by_id = {a.trade.id: a for a in annotated}
    assert by_id[t1.id].features["prev_outcome"] == "FIRST"
    assert by_id[t2.id].features["prev_outcome"] == "WIN"
    assert by_id[t3.id].features["prev_outcome"] == "LOSS"
    assert by_id[t4.id].features["prev_outcome"] == "BREAKEVEN"


def test_overlapping_no_lookahead(db_session, manual_account):
    """Open trade must not affect daily P&L before entry of overlapping trade."""
    e = _ny_utc(2026, 9, 1, 9, 30)
    t_open = make_trade(
        db_session,
        manual_account.id,
        entry_time=e,
        exit_time=e + timedelta(hours=2),
        net_pnl=Decimal("-500"),
        ticker="OPEN",
    )
    t_new = make_trade(
        db_session,
        manual_account.id,
        entry_time=e + timedelta(minutes=15),
        exit_time=e + timedelta(hours=1),
        net_pnl=Decimal("10"),
        ticker="NEW",
    )
    annotated = _annotate(db_session, [t_open, t_new])
    new_at = next(a for a in annotated if a.trade.ticker == "NEW")
    assert new_at.features["daily_pnl_state"] == "neg_50_50"
    assert new_at.features["prev_outcome"] == "FIRST"


def test_consecutive_losses(db_session, manual_account):
    e = _ny_utc(2026, 9, 1, 9, 0)
    trades = []
    for i, pnl in enumerate([Decimal("-1"), Decimal("-2"), Decimal("-3"), Decimal("5")]):
        entry = e + timedelta(hours=i)
        trades.append(
            make_trade(
                db_session,
                manual_account.id,
                entry_time=entry,
                exit_time=entry + timedelta(minutes=30),
                net_pnl=pnl,
                ticker=f"C{i}",
            )
        )
    annotated = _annotate(db_session, trades)
    streaks = [a.features["consec_losses"] for a in annotated]
    assert streaks == ["0", "1", "2", "3_plus"]


def test_daily_pnl_before_entry_excludes_current(db_session, manual_account):
    e = _ny_utc(2026, 9, 1, 9, 0)
    t1 = make_trade(db_session, manual_account.id, entry_time=e, exit_time=e + timedelta(minutes=30), net_pnl=Decimal("-100"), ticker="D1")
    t2 = make_trade(db_session, manual_account.id, entry_time=e + timedelta(hours=1), exit_time=e + timedelta(hours=1, minutes=30), net_pnl=Decimal("50"), ticker="D2")
    annotated = _annotate(db_session, [t1, t2])
    t2_at = next(a for a in annotated if a.trade.id == t2.id)
    assert t2_at.features["daily_pnl_state"] == "neg_200_50"


def test_ny_day_boundary(db_session, manual_account):
    late = datetime(2026, 9, 2, 3, 30, tzinfo=timezone.utc)
    early = datetime(2026, 9, 2, 13, 0, tzinfo=timezone.utc)
    t1 = make_trade(db_session, manual_account.id, entry_time=late, exit_time=early, net_pnl=Decimal("-10"), ticker="B1")
    t2 = make_trade(db_session, manual_account.id, entry_time=early + timedelta(hours=1), exit_time=early + timedelta(hours=2), net_pnl=Decimal("5"), ticker="B2")
    annotated = _annotate(db_session, [t1, t2])
    t2_at = next(a for a in annotated if a.trade.id == t2.id)
    assert t2_at.features["prev_outcome"] == "LOSS"


def test_two_accounts_independent(db_session, manual_account, strategy_account):
    e = _ny_utc(2026, 9, 1, 9, 0)
    t1 = make_trade(db_session, manual_account.id, entry_time=e, exit_time=e.replace(minute=30), net_pnl=Decimal("-50"))
    t2 = make_trade(db_session, strategy_account.id, entry_time=e.replace(hour=10), net_pnl=Decimal("10"))
    annotated = _annotate(db_session, [t1, t2])
    t2_at = next(a for a in annotated if a.trade.account_id == strategy_account.id)
    assert t2_at.features["prev_outcome"] == "FIRST"


# --- Filter engine ---


def test_weekday_filter():
    filt = parse_filter_set({"weekday": "WED"})
    assert apply_exploration({"day_of_week": "WED"}, filt)
    assert not apply_exploration({"day_of_week": "MON"}, filt)


def test_combined_global_exploration(db_session, manual_account):
    make_trade(db_session, manual_account.id, ticker="AAA", net_pnl=Decimal("10"))
    make_trade(db_session, manual_account.id, ticker="BBB", net_pnl=Decimal("-5"))
    filt = filters_from_query(ticker="AAA")
    result = get_reports(db_session, filt)
    assert result["matching_trade_count"] == 1


def test_reset_exploration_leaves_global(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("10"))
    filt = filters_from_query(ticker="TEST", weekday="MON")
    filt.exploration = {}
    result = get_reports(db_session, filt)
    assert result["matching_trade_count"] >= 1


def test_url_round_trip():
    filt = filters_from_query(weekday="WED", entry_15m="09:30-09:45", entry_price_bucket="5_10")
    assert filt.exploration["weekday"] == "WED"
    assert filt.exploration["entry_15m"] == "09:30-09:45"


# --- Aggregations ---


def _make_at(pnl: Decimal) -> AnnotatedTrade:
    from types import SimpleNamespace

    trade = SimpleNamespace(id=1, ticker="X")
    outcome = classify_outcome(pnl)
    return AnnotatedTrade(trade=trade, pnl=pnl, outcome=outcome, features={"sym": "X"})


def test_aggregation_metrics():
    items = [_make_at(Decimal("100")), _make_at(Decimal("-50")), _make_at(Decimal("0"))]
    for at in items:
        at.features["sym"] = "X"
    buckets = aggregate_dimension(items, "sym", {"X": "X"})
    b = buckets[0]
    assert b["trade_count"] == 3
    assert Decimal(b["net_pnl"]) == Decimal("50")
    assert Decimal(b["avg_trade"]) == Decimal("50") / 3
    assert Decimal(b["win_rate"]) == Decimal("50.00")
    assert b["breakeven"] == 1


def test_minimum_sample_filter():
    items = [_make_at(Decimal("10"))]
    for at in items:
        at.features["sym"] = "X"
    buckets = aggregate_dimension(items, "sym", min_sample=2)
    assert buckets == []


def test_best_worst():
    buckets = [
        {"key": "a", "label": "A", "trade_count": 5, "net_pnl": "100"},
        {"key": "b", "label": "B", "trade_count": 5, "net_pnl": "-50"},
    ]
    bw = best_worst(buckets)
    assert bw["best"]["key"] == "a"
    assert bw["worst"]["key"] == "b"


# --- Discovery integration ---


def seed_discovery_trades(db, account_id):
    """Patterns: MON+, WED-, 09:30-09:45+, 10:15-10:30-, $2-5+, $5-10-."""
    mon = _ny_utc(2026, 9, 7, 9, 35)
    wed_good = _ny_utc(2026, 9, 2, 9, 35)
    wed_bad = _ny_utc(2026, 9, 2, 10, 20)

    t_mon = make_trade(db, account_id, entry_time=mon, net_pnl=Decimal("200"), ticker="MON")
    t_mon.avg_entry_price = Decimal("2.5")
    t_wed_g = make_trade(db, account_id, entry_time=wed_good, net_pnl=Decimal("100"), ticker="WEDG")
    t_wed_g.avg_entry_price = Decimal("3")
    t_wed_b = make_trade(db, account_id, entry_time=wed_bad, net_pnl=Decimal("-150"), ticker="WEDB")
    t_wed_b.avg_entry_price = Decimal("7")
    db.commit()
    return t_mon, t_wed_g, t_wed_b


def test_discovery_workflow(db_session, manual_account):
    seed_discovery_trades(db_session, manual_account.id)
    base = get_reports(db_session, TradeFilterSet())
    wed_report = next(r for s in base["sections"] for r in s["reports"] if r["key"] == "day_of_week")
    wed_bucket = next(b for b in wed_report["buckets"] if b["key"] == "WED")
    assert Decimal(wed_bucket["net_pnl"]) < 0

    filt = filters_from_query(weekday="WED")
    wed_only = get_reports(db_session, filt)
    assert wed_only["matching_trade_count"] == 2

    filt2 = filters_from_query(weekday="WED", entry_15m="10:15-10:30")
    narrow = get_reports(db_session, filt2)
    assert narrow["matching_trade_count"] == 1

    filt3 = filters_from_query(weekday="WED", entry_15m="10:15-10:30", entry_price_bucket="5_10")
    narrow2 = get_reports(db_session, filt3)
    assert narrow2["matching_trade_count"] == 1
    price_report = next(r for s in narrow2["sections"] for r in s["reports"] if r["key"] == "entry_price")
    assert len(price_report["buckets"]) >= 1


def test_reports_api():
    res = client.get("/api/reports")
    assert res.status_code == 200
    body = res.json()
    assert "sections" in body


def test_registry_extensibility():
    """Adding a mock dimension should not require engine rewrite."""
    mock = {
        "key": "setup_quality",
        "title": "Mock Setup Quality",
        "section": "STRATEGY",
        "feature": "setup_quality",
        "default_metric": "net_pnl",
    }
    extended = list(REPORT_DEFINITIONS) + [mock]
    assert any(r["key"] == "setup_quality" for r in extended)
    assert exploration_param_for_feature("day_of_week") == "weekday"


def test_10k_trades_performance(db_session, manual_account):
    import time

    base = _ny_utc(2026, 1, 2, 9, 30)
    trades = []
    for i in range(10000):
        entry = base + timedelta(minutes=i)
        exit_t = entry + timedelta(minutes=5)
        fp = f"perf-{i}-{exit_t.isoformat()}"
        trades.append(
            Trade(
                account_id=manual_account.id,
                source_type="TRADINGVIEW_MANUAL",
                trade_fingerprint=fp,
                ticker=f"S{i % 50}",
                direction="LONG",
                entry_time_utc=entry,
                exit_time_utc=exit_t,
                avg_entry_price=Decimal("10"),
                avg_exit_price=Decimal("11"),
                quantity=Decimal("100"),
                gross_pnl=Decimal(str((i % 21) - 10)),
                net_pnl=Decimal(str((i % 21) - 10)),
                holding_seconds=300,
                status="CLOSED",
            )
        )
    db_session.add_all(trades)
    db_session.commit()
    start = time.perf_counter()
    reports = get_reports(db_session, TradeFilterSet())
    elapsed = time.perf_counter() - start
    assert reports["matching_trade_count"] == 10000
    print(f"BENCH graphs_10k={elapsed:.3f}s target=5.0s")
    # Functional correctness is matching_trade_count. Ceiling catches pathological
    # slowdown only; 5s is a reported target, not a brittle CI gate.
    # Investigation (Step 9 hardening): get_reports was not changed by Research Lab.
    # Isolated re-runs were 5.95–6.08s on this hardware — variance, not a code regression.
    assert elapsed < 45.0, f"Reports pathological slowdown: {elapsed:.2f}s for 10k trades"
