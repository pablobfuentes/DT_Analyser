"""Market data provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime

from app.market_data.models import DailyBar, FetchStats, IntradayBar, SplitEvent


class MarketDataProvider(ABC):
    provider_name: str
    feed_name: str
    is_consolidated: bool
    supports_splits: bool = False
    supports_batch_symbols: bool = True
    supports_intraday: bool = False

    @abstractmethod
    def get_daily_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        adjustment_mode: str = "raw",
        stats: FetchStats | None = None,
    ) -> list[DailyBar]:
        ...

    def get_intraday_bars(
        self,
        symbols: list[str],
        start_utc: datetime,
        end_utc: datetime,
        timeframe: str = "1Min",
        adjustment_mode: str = "raw",
        stats: FetchStats | None = None,
    ) -> list[IntradayBar]:
        return []

    def get_splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]:
        return []
