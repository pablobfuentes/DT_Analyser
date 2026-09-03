"""Normalized market-data objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass
class DailyBar:
    symbol: str
    trading_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    provider: str
    feed: str
    adjustment_mode: str
    is_consolidated: bool
    fetched_at: datetime
    vwap: Decimal | None = None
    trade_count: int | None = None
    raw_payload_json: str | None = None


@dataclass
class IntradayBar:
    symbol: str
    bar_time_utc: datetime
    timeframe: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    provider: str
    feed: str
    adjustment_mode: str
    is_consolidated: bool
    fetched_at: datetime
    vwap: Decimal | None = None
    trade_count: int | None = None
    session_type: str | None = None
    raw_payload_json: str | None = None


@dataclass
class SplitEvent:
    symbol: str
    effective_date: date
    split_from: Decimal
    split_to: Decimal


@dataclass
class FetchStats:
    provider_requests: int = 0
    bars_fetched: int = 0
    cache_hits: int = 0
    symbol_days_fetched: int = 0
