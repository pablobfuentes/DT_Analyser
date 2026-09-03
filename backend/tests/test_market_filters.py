"""Market dimension exploration filter tests."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.market_data.fake import FakeMarketDataProvider, build_flat_series, clear_fake_store, register_fake_series
from app.market_data.models import DailyBar
from app.services.market_enrichment.service import MarketEnrichmentService
from app.services.reports.filters import TradeFilterSet, parse_filter_set
from app.services.reports.service import get_reports
from tests.dashboard_helpers import make_trade


@pytest.fixture(autouse=True)
def _clear_fake():
    clear_fake_store()
    yield
    clear_fake_store()


def _setup(db_session, manual_account):
    trade_date = date(2026, 9, 1)
    start = trade_date - timedelta(days=120)
    stock = build_flat_series("NCRA", start, 65, base_close=Decimal("4"))
    prev = stock[-2]
    stock[-2] = DailyBar(
        symbol=prev.symbol, trading_date=prev.trading_date, open=prev.open, high=prev.high,
        low=prev.low, close=Decimal("4"), volume=prev.volume, provider=prev.provider,
        feed=prev.feed, adjustment_mode=prev.adjustment_mode, is_consolidated=prev.is_consolidated,
        fetched_at=prev.fetched_at,
    )
    stock[-1] = DailyBar(
        symbol=stock[-1].symbol, trading_date=trade_date, open=Decimal("5"), high=Decimal("5.5"),
        low=Decimal("4.8"), close=Decimal("5.2"), volume=5_000_000, provider=stock[-1].provider,
        feed=stock[-1].feed, adjustment_mode=stock[-1].adjustment_mode,
        is_consolidated=stock[-1].is_consolidated, fetched_at=stock[-1].fetched_at,
    )
    register_fake_series("NCRA", stock)
    register_fake_series("SPY", build_flat_series("SPY", start, 65, base_close=Decimal("400")))
    entry = datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    make_trade(db_session, manual_account.id, ticker="NCRA", entry_time=entry, net_pnl=Decimal("100"))
    MarketEnrichmentService(db_session, FakeMarketDataProvider()).enrich(scope="all")
    return trade_date


def test_gap_exploration_filter(db_session, manual_account):
    _setup(db_session, manual_account)
    filt = parse_filter_set({"gap_bucket": "20_50"})
    reports = get_reports(db_session, filt)
    assert reports["matching_trade_count"] == 1


def test_combined_gap_and_weekday(db_session, manual_account):
    _setup(db_session, manual_account)
    filt = parse_filter_set({"gap_bucket": "20_50", "weekday": "TUE"})
    reports = get_reports(db_session, filt)
    assert reports["matching_trade_count"] == 1
