"""Step 3/4 audit regression tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.models.market_data import InstrumentDayFeature, MarketDailyBar, TradeMarketFeature
from app.main import app
from app.market_data.alpaca import AlpacaMarketDataProvider
from app.market_data.cache import missing_date_ranges
from app.market_data.calendar import is_nyse_trading_day, nyse_holidays
from app.market_data.fake import FakeMarketDataProvider, build_flat_series, clear_fake_store, register_fake_series
from app.market_data.models import DailyBar
from app.services.market_enrichment.calculator import SessionBar, classify_day_type, compute_day_features, rvol_multiple
from app.services.market_enrichment.service import MarketEnrichmentService
from app.services.reports.config import ENTRY_PRICE_BUCKETS, bucket_key_for_value
from app.services.reports.features import apply_behavior_features, compute_base_features
from app.services.reports.filters import TradeFilterSet, filters_from_query
from app.services.reports.registry import REPORT_DEFINITIONS
from app.services.reports.service import get_reports
from app.utils.clock import freeze_time
from tests.dashboard_helpers import make_trade

client = TestClient(app)


@pytest.fixture(autouse=True)
def _clear_fake():
    clear_fake_store()
    yield
    clear_fake_store()


def _ny_utc(year, month, day, ny_hour, ny_minute=0, ny_second=0):
    return datetime(year, month, day, ny_hour + 4, ny_minute, ny_second, tzinfo=timezone.utc)


def _seed(symbol: str, trade_date: date, sessions: int = 65, consolidated: bool = True):
    start = trade_date - timedelta(days=140)
    stock = build_flat_series(symbol, start, sessions, base_close=Decimal("4"), volume=1_000_000)
    last = stock[-1]
    prev = stock[-2]
    stock[-2] = DailyBar(
        symbol=prev.symbol,
        trading_date=prev.trading_date,
        open=prev.open,
        high=prev.high,
        low=prev.low,
        close=Decimal("4"),
        volume=prev.volume,
        provider=prev.provider,
        feed=prev.feed,
        adjustment_mode=prev.adjustment_mode,
        is_consolidated=consolidated,
        fetched_at=prev.fetched_at,
    )
    stock[-1] = DailyBar(
        symbol=last.symbol,
        trading_date=trade_date,
        open=Decimal("5"),
        high=Decimal("5.5"),
        low=Decimal("4.8"),
        close=Decimal("5.2"),
        volume=5_000_000,
        provider=last.provider,
        feed=last.feed,
        adjustment_mode=last.adjustment_mode,
        is_consolidated=consolidated,
        fetched_at=last.fetched_at,
    )
    register_fake_series(symbol, stock)
    register_fake_series("SPY", build_flat_series("SPY", start, sessions, base_close=Decimal("400")))
    return stock


def test_matching_trade_count_consistent_across_reports(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    _seed("NCRA", trade_date)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=_ny_utc(2026, 9, 1, 9, 35),
        net_pnl=Decimal("40"),
    )
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc),
        net_pnl=Decimal("-10"),
    )
    MarketEnrichmentService(db_session, FakeMarketDataProvider()).enrich(scope="all")
    filt = filters_from_query(weekday="TUE", entry_15m="09:30-09:45", gap_bucket="20_50")
    result = get_reports(db_session, filt)
    assert result["matching_trade_count"] == 1
    expected = result["matching_trade_count"]
    for section in result["sections"]:
        for report in section["reports"]:
            if report.get("coverage"):
                assert report["coverage"]["matching_trades"] == expected


def test_entry_hour_edges(db_session, manual_account):
    cases = [
        ((9, 29, 59), "09", "09:00-09:30", "09:15-09:30"),
        ((9, 30, 0), "09", "09:30-10:00", "09:30-09:45"),
        ((9, 44, 59), "09", "09:30-10:00", "09:30-09:45"),
        ((9, 45, 0), "09", "09:30-10:00", "09:45-10:00"),
        ((9, 59, 59), "09", "09:30-10:00", "09:45-10:00"),
        ((10, 0, 0), "10", "10:00-10:30", "10:00-10:15"),
    ]
    for (h, m, s), hour, b30, b15 in cases:
        t = make_trade(
            db_session,
            manual_account.id,
            entry_time=_ny_utc(2026, 9, 1, h, m, s),
            ticker=f"E{h}{m}{s}",
        )
        feats = compute_base_features(t)
        assert feats["entry_hour"] == hour
        assert feats["entry_30m"] == b30
        assert feats["entry_15m"] == b15
        db_session.delete(t)
        db_session.commit()


def test_price_quantity_boundaries():
    assert bucket_key_for_value("gap", Decimal("0")) == "0_2"
    assert bucket_key_for_value("gap", Decimal("2")) == "2_5"
    assert bucket_key_for_value("rvol", Decimal("5")) == "5_10"
    assert bucket_key_for_value("rvol", Decimal("1")) == "1_2"
    from app.services.reports.features import _bucket_numeric

    assert _bucket_numeric(Decimal("2.00"), ENTRY_PRICE_BUCKETS)[0] == "2_3"
    assert _bucket_numeric(Decimal("1.99"), ENTRY_PRICE_BUCKETS)[0] == "lt_2"


def test_same_timestamp_trade_number_tie_break(db_session, manual_account):
    ts = _ny_utc(2026, 9, 1, 9, 30)
    t1 = make_trade(db_session, manual_account.id, entry_time=ts, ticker="A", net_pnl=Decimal("1"))
    t2 = make_trade(db_session, manual_account.id, entry_time=ts, ticker="B", net_pnl=Decimal("2"))
    from app.services.reports.features import AnnotatedTrade
    from app.utils.analytics import classify_outcome, effective_realized_pnl

    annotated = []
    for t in (t1, t2):
        rp = effective_realized_pnl(t)
        annotated.append(
            AnnotatedTrade(trade=t, pnl=rp.pnl, outcome=classify_outcome(rp.pnl), features=compute_base_features(t))
        )
    apply_behavior_features(annotated)
    by_id = {a.trade.id: a.features["trade_number"] for a in annotated}
    ordered = [t1.id, t2.id] if t1.id < t2.id else [t2.id, t1.id]
    assert by_id[ordered[0]] == "1"
    assert by_id[ordered[1]] == "2"


def test_breakeven_breaks_loss_streak(db_session, manual_account):
    e = _ny_utc(2026, 9, 1, 9, 0)
    pnls = [Decimal("-10"), Decimal("0.00"), Decimal("-5")]
    trades = []
    for i, pnl in enumerate(pnls):
        entry = e + timedelta(hours=i)
        trades.append(
            make_trade(
                db_session,
                manual_account.id,
                entry_time=entry,
                exit_time=entry + timedelta(minutes=20),
                net_pnl=pnl,
                ticker=f"BE{i}",
            )
        )
    from app.services.reports.service import _annotate_trades

    annotated = _annotate_trades(db_session, trades)
    streaks = [a.features["consec_losses"] for a in annotated]
    assert streaks == ["0", "1", "0"]


def test_unknown_keys_ignored():
    filt = filters_from_query(weekday="WED", not_a_filter="boom")
    assert filt.exploration == {"weekday": "WED"}


def test_invalid_date_400():
    res = client.get("/api/reports", params={"start_date": "not-a-date"})
    assert res.status_code == 400


def test_report_order_deterministic(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("1"))
    a = get_reports(db_session, TradeFilterSet())
    b = get_reports(db_session, TradeFilterSet())
    keys_a = [r["key"] for s in a["sections"] for r in s["reports"]]
    keys_b = [r["key"] for s in b["sections"] for r in s["reports"]]
    assert keys_a == keys_b
    available = {s["key"] for s in a["sections"] if s["available"]}
    expected = [d["key"] for d in REPORT_DEFINITIONS if d["section"] in available]
    assert keys_a == expected


def test_min_sample_does_not_change_population(db_session, manual_account):
    make_trade(db_session, manual_account.id, ticker="A", net_pnl=Decimal("1"))
    make_trade(db_session, manual_account.id, ticker="B", net_pnl=Decimal("1"))
    r1 = get_reports(db_session, TradeFilterSet(), min_sample=1)
    r2 = get_reports(db_session, TradeFilterSet(), min_sample=10)
    assert r1["matching_trade_count"] == r2["matching_trade_count"] == 2


def test_rvol50_excludes_current_and_requires_50():
    start = date(2026, 1, 1)
    sessions = [
        SessionBar(start + timedelta(days=i), Decimal("10"), Decimal("10.5"), Decimal("9.5"), Decimal("10"), 1_000_000)
        for i in range(50)
    ]
    feat = compute_day_features(sessions, 49, is_consolidated=True)
    assert feat.rvol50_multiple is None
    sessions.append(
        SessionBar(start + timedelta(days=50), Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"), 5_000_000)
    )
    feat = compute_day_features(sessions, 50, is_consolidated=True)
    assert feat.rvol50_multiple == Decimal("5")
    assert rvol_multiple(5_000_000, [1_000_000] * 49) is None


def test_prior_day_rvol_session_index():
    start = date(2026, 1, 1)
    vols = [1_000_000] * 50 + [2_000_000, 8_000_000]
    sessions = [
        SessionBar(start + timedelta(days=i), Decimal("10"), Decimal("10.5"), Decimal("9.5"), Decimal("10"), v)
        for i, v in enumerate(vols)
    ]
    feat = compute_day_features(sessions, 51, is_consolidated=True)
    baseline = (Decimal("1000000") * 49 + Decimal("2000000")) / Decimal(50)
    assert feat.rvol50_multiple == Decimal("8000000") / baseline
    assert feat.prior_day_rvol50_multiple == Decimal("2")


def test_zero_range_day_type():
    assert (
        classify_day_type(Decimal("5"), Decimal("5"), Decimal("5"), Decimal("5"), Decimal("6"), Decimal("4"))
        == "INSIDE_RANGE"
    )


def test_incomplete_day_keeps_pre_entry():
    start = date(2026, 1, 1)
    sessions = [
        SessionBar(start + timedelta(days=i), Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"), 1_000_000)
        for i in range(52)
    ]
    feat = compute_day_features(sessions, 51, is_consolidated=True, is_today_incomplete=True)
    assert feat.opening_gap_pct is not None
    assert feat.atr14_prior is not None
    assert feat.sma20_prior is not None
    assert feat.rvol50_multiple is None
    assert feat.daily_movement_pct is None
    assert feat.day_type is None
    assert "PENDING_EOD" in feat.quality_flags


def test_iex_rvol_excluded_from_default_graphs(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    _seed("NCRA", trade_date, consolidated=False)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        net_pnl=Decimal("25"),
    )
    provider = FakeMarketDataProvider(feed="iex", is_consolidated=False)
    MarketEnrichmentService(db_session, provider).enrich(scope="all")
    reports = get_reports(db_session, TradeFilterSet())
    inst = next(s for s in reports["sections"] if s["key"] == "INSTRUMENT")
    rvol = next(r for r in inst["reports"] if r["key"] == "instrument_rvol50")
    gap = next(r for r in inst["reports"] if r["key"] == "instrument_gap")
    dow = next(r for s in reports["sections"] for r in s["reports"] if r["key"] == "day_of_week")
    assert sum(b["trade_count"] for b in rvol["buckets"] if b["key"] != "unknown") == 0
    assert any(b["trade_count"] > 0 for b in gap["buckets"] if b["key"] != "unknown")
    assert reports["matching_trade_count"] == sum(b["trade_count"] for b in dow["buckets"])
    assert rvol["coverage"]["exclusion_reasons"].get("PARTIAL_FEED", 0) >= 1

    included = get_reports(db_session, filters_from_query(include_partial_feed=True))
    inst2 = next(s for s in included["sections"] if s["key"] == "INSTRUMENT")
    rvol2 = next(r for r in inst2["reports"] if r["key"] == "instrument_rvol50")
    assert any(b["trade_count"] > 0 for b in rvol2["buckets"] if b["key"] != "unknown")


def test_weekend_holiday_not_refetched(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    _seed("NCRA", trade_date)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        net_pnl=Decimal("10"),
    )
    svc = MarketEnrichmentService(db_session, FakeMarketDataProvider())
    first = svc.enrich(scope="all")
    second = svc.enrich(scope="all")
    recalc = svc.recalculate()
    assert first["provider_requests"] >= 1
    assert second["provider_requests"] == 0
    assert recalc["provider_requests"] == 0
    labor_day = date(2026, 9, 7)
    assert labor_day in nyse_holidays(2026)
    assert not is_nyse_trading_day(date(2026, 9, 5))
    assert missing_date_ranges([], date(2026, 9, 5), date(2026, 9, 7)) == []


def test_provider_switch_does_not_mix_feeds(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    _seed("NCRA", trade_date)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        net_pnl=Decimal("10"),
    )
    iex = FakeMarketDataProvider(feed="iex", is_consolidated=False, provider_name="FAKE")
    sip = FakeMarketDataProvider(feed="sip", is_consolidated=True, provider_name="FAKE")
    MarketEnrichmentService(db_session, iex).enrich(scope="all")
    iex_rows = db_session.query(InstrumentDayFeature).filter(InstrumentDayFeature.feed == "iex").count()
    assert iex_rows >= 1
    MarketEnrichmentService(db_session, sip).enrich(scope="all")
    sip_rows = db_session.query(InstrumentDayFeature).filter(InstrumentDayFeature.feed == "sip").count()
    iex_rows_after = db_session.query(InstrumentDayFeature).filter(InstrumentDayFeature.feed == "iex").count()
    assert sip_rows >= 1
    assert iex_rows_after == iex_rows
    tmf = db_session.query(TradeMarketFeature).one()
    inst = db_session.get(InstrumentDayFeature, tmf.instrument_feature_id)
    assert inst.feed == "sip"
    bars_iex = db_session.query(MarketDailyBar).filter(MarketDailyBar.feed == "iex").count()
    bars_sip = db_session.query(MarketDailyBar).filter(MarketDailyBar.feed == "sip").count()
    assert bars_iex > 0 and bars_sip > 0


def test_calculation_version_recalc_no_network(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    _seed("NCRA", trade_date)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        net_pnl=Decimal("10"),
    )
    svc = MarketEnrichmentService(db_session, FakeMarketDataProvider())
    svc.enrich(scope="all")
    v2 = svc.enrich(scope="all", fetch_from_provider=False, calculation_version="instrument-v2")
    assert v2["provider_requests"] == 0
    versions = {r.calculation_version for r in db_session.query(InstrumentDayFeature).all()}
    assert "instrument-v1" in versions
    assert "instrument-v2" in versions
    tmf = db_session.query(TradeMarketFeature).one()
    inst = db_session.get(InstrumentDayFeature, tmf.instrument_feature_id)
    assert inst.calculation_version == "instrument-v2"


def test_refresh_calls_provider_recalculate_does_not(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    _seed("NCRA", trade_date)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        net_pnl=Decimal("10"),
    )
    svc = MarketEnrichmentService(db_session, FakeMarketDataProvider())
    svc.enrich(scope="all")
    assert svc.recalculate()["provider_requests"] == 0
    assert svc.refresh()["provider_requests"] >= 1


def test_pending_eod_with_frozen_clock(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    _seed("NCRA", trade_date)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        net_pnl=Decimal("10"),
    )
    with freeze_time(datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc)):
        MarketEnrichmentService(db_session, FakeMarketDataProvider()).enrich(scope="all")
    inst = (
        db_session.query(InstrumentDayFeature)
        .filter(InstrumentDayFeature.symbol == "NCRA", InstrumentDayFeature.trading_date == "2026-09-01")
        .one()
    )
    assert inst.completeness_status == "PRE_ENTRY_ONLY"
    assert inst.opening_gap_pct is not None
    assert inst.rvol50_multiple is None
    assert inst.atr14_prior is not None


def test_status_hides_secrets():
    res = client.get("/api/market-data/status")
    assert res.status_code == 200
    body = res.json()
    blob = str(body).lower()
    assert "secret" not in blob
    assert "apca-api" not in blob
    assert "api_key" not in blob


def test_alpaca_does_not_retry_401(monkeypatch):
    provider = AlpacaMarketDataProvider("key", "secret", "iex")
    sleeps: list[float] = []
    monkeypatch.setattr("app.market_data.alpaca._retry_sleep", lambda s: sleeps.append(s))

    response = MagicMock()
    response.status_code = 401

    mock_client = MagicMock()
    mock_client.get.return_value = response
    mock_client.__enter__.return_value = mock_client
    mock_client.__exit__.return_value = False

    def raise_status():
        import httpx

        req = httpx.Request("GET", "https://data.alpaca.markets/v2/stocks/bars")
        resp = httpx.Response(401, request=req)
        raise httpx.HTTPStatusError("401", request=req, response=resp)

    response.raise_for_status.side_effect = raise_status

    with patch("app.market_data.alpaca.httpx.Client", return_value=mock_client):
        with pytest.raises(Exception):
            provider.get_daily_bars(["AAPL"], date(2026, 1, 1), date(2026, 1, 10))
    assert sleeps == []


def test_same_symbol_day_reuses_instrument_row(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    _seed("NCRA", trade_date)
    e = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    make_trade(db_session, manual_account.id, ticker="NCRA", entry_time=e, net_pnl=Decimal("10"))
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=e + timedelta(minutes=20),
        net_pnl=Decimal("5"),
    )
    MarketEnrichmentService(db_session, FakeMarketDataProvider()).enrich(scope="all")
    inst = (
        db_session.query(InstrumentDayFeature)
        .filter(InstrumentDayFeature.symbol == "NCRA", InstrumentDayFeature.trading_date == "2026-09-01")
        .count()
    )
    assert inst == 1
    assert db_session.query(TradeMarketFeature).count() == 2


def test_symbol_failure_does_not_drop_trade(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    register_fake_series("SPY", build_flat_series("SPY", trade_date - timedelta(days=140), 65, base_close=Decimal("400")))
    make_trade(
        db_session,
        manual_account.id,
        ticker="MISSING",
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        net_pnl=Decimal("3"),
    )
    MarketEnrichmentService(db_session, FakeMarketDataProvider()).enrich(scope="all")
    reports = get_reports(db_session, TradeFilterSet())
    assert reports["matching_trade_count"] == 1
    dow = next(r for s in reports["sections"] for r in s["reports"] if r["key"] == "day_of_week")
    assert sum(b["trade_count"] for b in dow["buckets"]) == 1


def test_combined_exploration_cross_section(db_session, manual_account):
    trade_date = date(2026, 9, 2)
    _seed("NCRA", trade_date)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=_ny_utc(2026, 9, 2, 9, 35),
        net_pnl=Decimal("80"),
    )
    MarketEnrichmentService(db_session, FakeMarketDataProvider()).enrich(scope="all")
    filt = filters_from_query(
        weekday="WED",
        entry_15m="09:30-09:45",
        gap_bucket="20_50",
        rvol_bucket="5_10",
    )
    result = get_reports(db_session, filt)
    assert result["matching_trade_count"] == 1
    for section in result["sections"]:
        if not section["available"]:
            continue
        for report in section["reports"]:
            if report.get("coverage"):
                assert report["coverage"]["matching_trades"] == 1
