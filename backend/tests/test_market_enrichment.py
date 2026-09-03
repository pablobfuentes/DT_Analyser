"""Integration tests for market enrichment."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.market_data.fake import FakeMarketDataProvider, build_flat_series, clear_fake_store, register_fake_series
from app.market_data.models import DailyBar
from app.services.market_enrichment.service import MarketEnrichmentService
from app.services.reports.service import get_reports
from app.services.reports.filters import TradeFilterSet
from tests.dashboard_helpers import make_trade


@pytest.fixture(autouse=True)
def _clear_fake():
    clear_fake_store()
    yield
    clear_fake_store()


def _seed_market_data(trade_date: date, symbol: str = "NCRA") -> None:
    start = trade_date - timedelta(days=120)
    stock = build_flat_series(symbol, start, 65, base_close=Decimal("4"), volume=1_000_000)
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
        is_consolidated=prev.is_consolidated,
        fetched_at=prev.fetched_at,
    )
    # Last session: 25% gap (prior close 4, open 5)
    last = stock[-1]
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
        is_consolidated=last.is_consolidated,
        fetched_at=last.fetched_at,
    )
    spy = build_flat_series("SPY", start, 65, base_close=Decimal("400"))
    register_fake_series(symbol, stock)
    register_fake_series("SPY", spy)


def test_enrichment_and_gap_filter(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    entry = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    _seed_market_data(trade_date)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        entry_time=entry,
        net_pnl=Decimal("100"),
    )

    provider = FakeMarketDataProvider()
    svc = MarketEnrichmentService(db_session, provider)
    result = svc.enrich(scope="all")
    assert result["status"] == "SUCCESS"
    assert result["provider_requests"] >= 1

    reports = get_reports(db_session, TradeFilterSet())
    inst = next(s for s in reports["sections"] if s["key"] == "INSTRUMENT")
    gap_report = next(r for r in inst["reports"] if r["key"] == "instrument_gap")
    assert any(b["trade_count"] > 0 for b in gap_report["buckets"])

    result2 = svc.enrich(scope="all")
    assert result2["provider_requests"] == 0


def test_cache_avoids_second_provider_call(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    entry = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    _seed_market_data(trade_date)
    make_trade(db_session, manual_account.id, ticker="NCRA", entry_time=entry, net_pnl=Decimal("50"))

    provider = FakeMarketDataProvider()
    svc = MarketEnrichmentService(db_session, provider)
    first = svc.enrich(scope="all")
    second = svc.enrich(scope="all")
    assert first["provider_requests"] >= 1
    assert second["provider_requests"] == 0
