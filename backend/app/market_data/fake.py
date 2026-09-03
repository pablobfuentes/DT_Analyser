"""Deterministic fake market data provider for tests."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from app.market_data.base import MarketDataProvider
from app.market_data.models import DailyBar, FetchStats, IntradayBar

# Module-level store keyed by symbol
_FAKE_STORE: dict[str, list[DailyBar]] = {}
_FAKE_INTRADAY: dict[str, list[IntradayBar]] = {}


def register_fake_series(symbol: str, bars: list[DailyBar]) -> None:
    _FAKE_STORE[symbol.upper()] = sorted(bars, key=lambda b: b.trading_date)


def register_fake_intraday_series(symbol: str, bars: list[IntradayBar]) -> None:
    _FAKE_INTRADAY[symbol.upper()] = sorted(bars, key=lambda b: b.bar_time_utc)


def clear_fake_store() -> None:
    _FAKE_STORE.clear()
    _FAKE_INTRADAY.clear()


class FakeMarketDataProvider(MarketDataProvider):
    provider_name = "FAKE"
    feed_name = "fake"
    is_consolidated = True
    supports_splits = False
    supports_batch_symbols = True
    supports_intraday = True

    def __init__(
        self,
        feed: str = "fake",
        is_consolidated: bool = True,
        provider_name: str = "FAKE",
    ):
        self.feed_name = feed
        self.is_consolidated = is_consolidated
        self.provider_name = provider_name

    def get_daily_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        adjustment_mode: str = "raw",
        stats: FetchStats | None = None,
    ) -> list[DailyBar]:
        if stats:
            stats.provider_requests += 1
        out: list[DailyBar] = []
        now = datetime.now(timezone.utc)
        for sym in symbols:
            sym = sym.upper()
            series = _FAKE_STORE.get(sym, [])
            added = 0
            for b in series:
                if start_date <= b.trading_date <= end_date:
                    out.append(
                        DailyBar(
                            symbol=sym,
                            trading_date=b.trading_date,
                            open=b.open,
                            high=b.high,
                            low=b.low,
                            close=b.close,
                            volume=b.volume,
                            provider=self.provider_name,
                            feed=self.feed_name,
                            adjustment_mode=adjustment_mode,
                            is_consolidated=self.is_consolidated,
                            fetched_at=now,
                        )
                    )
                    added += 1
            if stats:
                stats.bars_fetched += added
        return out

    def get_intraday_bars(
        self,
        symbols: list[str],
        start_utc: datetime,
        end_utc: datetime,
        timeframe: str = "1Min",
        adjustment_mode: str = "raw",
        stats: FetchStats | None = None,
    ) -> list[IntradayBar]:
        if stats:
            stats.provider_requests += 1
        out: list[IntradayBar] = []
        for sym in symbols:
            sym = sym.upper()
            series = _FAKE_INTRADAY.get(sym, [])
            for b in series:
                bt = b.bar_time_utc
                if bt.tzinfo is None:
                    bt = bt.replace(tzinfo=timezone.utc)
                if start_utc <= bt < end_utc:
                    out.append(b)
        if stats:
            stats.bars_fetched += len(out)
            stats.symbol_days_fetched += 1
        return out


def build_minute_bars(
    symbol: str,
    start_utc: datetime,
    specs: list[tuple[Decimal, Decimal, Decimal]],
) -> list[IntradayBar]:
    """Build 1-min bars from (high, low, close) specs starting at start_utc."""
    bars: list[IntradayBar] = []
    t = start_utc
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    fetched = datetime.now(timezone.utc)
    for h, l, c in specs:
        o = (h + l) / Decimal("2")
        bars.append(
            IntradayBar(
                symbol=symbol.upper(),
                bar_time_utc=t,
                timeframe="1Min",
                open=o,
                high=h,
                low=l,
                close=c,
                volume=1000,
                provider="FAKE",
                feed="fake",
                adjustment_mode="raw",
                is_consolidated=True,
                fetched_at=fetched,
            )
        )
        t += timedelta(minutes=1)
    return bars


def build_flat_series(
    symbol: str,
    start: date,
    sessions: int,
    *,
    base_close: Decimal = Decimal("4"),
    volume: int = 1_000_000,
    gap_open: Decimal | None = None,
    day_close: Decimal | None = None,
    day_high: Decimal | None = None,
    day_low: Decimal | None = None,
) -> list[DailyBar]:
    """Helper to build consecutive weekday bars."""
    bars: list[DailyBar] = []
    d = start
    close = base_close
    fetched = datetime.now(timezone.utc)
    added = 0
    while added < sessions:
        if d.weekday() < 5:
            prior = close
            o = gap_open if gap_open is not None and added == sessions - 1 else prior
            c = day_close if day_close is not None and added == sessions - 1 else (o + Decimal("0.1"))
            h = day_high if day_high is not None and added == sessions - 1 else max(o, c) + Decimal("0.5")
            l = day_low if day_low is not None and added == sessions - 1 else min(o, c) - Decimal("0.5")
            vol = volume
            bars.append(
                DailyBar(
                    symbol=symbol.upper(),
                    trading_date=d,
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=vol,
                    provider="FAKE",
                    feed="fake",
                    adjustment_mode="raw",
                    is_consolidated=True,
                    fetched_at=fetched,
                )
            )
            close = c
            added += 1
        d += timedelta(days=1)
    return bars
