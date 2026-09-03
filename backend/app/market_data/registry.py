"""Resolve configured market data provider."""

from __future__ import annotations

from app.config import settings
from app.market_data.alpaca import AlpacaMarketDataProvider
from app.market_data.base import MarketDataProvider
from app.market_data.fake import FakeMarketDataProvider


class NoneMarketDataProvider(MarketDataProvider):
    provider_name = "NONE"
    feed_name = "none"
    is_consolidated = False

    def get_daily_bars(self, symbols, start_date, end_date, adjustment_mode="raw", stats=None):
        return []


def get_market_data_provider(force_fake: bool = False) -> MarketDataProvider:
    if force_fake or settings.market_data_provider == "fake":
        return FakeMarketDataProvider()
    if settings.market_data_provider == "alpaca":
        if settings.alpaca_api_key_id and settings.alpaca_api_secret_key:
            return AlpacaMarketDataProvider(
                settings.alpaca_api_key_id,
                settings.alpaca_api_secret_key,
                settings.alpaca_data_feed,
            )
    return NoneMarketDataProvider()


def provider_status() -> dict:
    provider = settings.market_data_provider
    configured = False
    feed = None
    consolidated = None
    name = "NONE"
    if provider == "alpaca" and settings.alpaca_api_key_id and settings.alpaca_api_secret_key:
        configured = True
        name = "ALPACA"
        feed = settings.alpaca_data_feed.upper()
        consolidated = settings.alpaca_data_feed.lower() == "sip"
    elif provider == "fake":
        configured = True
        name = "FAKE"
        feed = "fake"
        consolidated = True
    return {
        "configured": configured,
        "provider": name,
        "feed": feed,
        "is_consolidated": consolidated,
        "quality_level": "CONSOLIDATED" if consolidated else ("PARTIAL" if configured else None),
        "benchmark": settings.market_benchmark,
    }
