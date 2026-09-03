"""Intraday bar cache (Step 8)."""

from __future__ import annotations

from datetime import date, datetime, time, timezone

from sqlalchemy.orm import Session

from app.db.models.market_data import MarketIntradayBar
from app.market_data.models import IntradayBar
from app.services.excursion_enrichment.config import INTRADAY_TIMEFRAME
from app.utils.analytics import analytics_tz


def ny_session_bounds_utc(trading_date: date) -> tuple[datetime, datetime]:
    """04:00–20:00 America/New_York for a calendar date."""
    tz = analytics_tz()
    start_local = datetime.combine(trading_date, time(4, 0), tzinfo=tz)
    end_local = datetime.combine(trading_date, time(20, 0), tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def load_cached_intraday(
    db: Session,
    symbol: str,
    start_utc: datetime,
    end_utc: datetime,
    provider: str,
    feed: str,
    adjustment_mode: str,
    timeframe: str = INTRADAY_TIMEFRAME,
) -> list[IntradayBar]:
    rows = (
        db.query(MarketIntradayBar)
        .filter(
            MarketIntradayBar.symbol == symbol.upper(),
            MarketIntradayBar.provider == provider,
            MarketIntradayBar.feed == feed,
            MarketIntradayBar.adjustment_mode == adjustment_mode,
            MarketIntradayBar.timeframe == timeframe,
            MarketIntradayBar.bar_time_utc >= start_utc,
            MarketIntradayBar.bar_time_utc < end_utc,
        )
        .order_by(MarketIntradayBar.bar_time_utc)
        .all()
    )
    return [_row_to_bar(r) for r in rows]


def session_fully_cached(
    db: Session,
    symbol: str,
    trading_date: date,
    provider: str,
    feed: str,
    adjustment_mode: str,
    timeframe: str = INTRADAY_TIMEFRAME,
    min_bars: int = 1,
) -> bool:
    start, end = ny_session_bounds_utc(trading_date)
    count = (
        db.query(MarketIntradayBar)
        .filter(
            MarketIntradayBar.symbol == symbol.upper(),
            MarketIntradayBar.provider == provider,
            MarketIntradayBar.feed == feed,
            MarketIntradayBar.adjustment_mode == adjustment_mode,
            MarketIntradayBar.timeframe == timeframe,
            MarketIntradayBar.bar_time_utc >= start,
            MarketIntradayBar.bar_time_utc < end,
        )
        .count()
    )
    return count >= min_bars


def store_intraday_bars(db: Session, bars: list[IntradayBar], store_raw: bool = False) -> int:
    count = 0
    for b in bars:
        existing = (
            db.query(MarketIntradayBar)
            .filter(
                MarketIntradayBar.symbol == b.symbol.upper(),
                MarketIntradayBar.bar_time_utc == b.bar_time_utc,
                MarketIntradayBar.timeframe == b.timeframe,
                MarketIntradayBar.provider == b.provider,
                MarketIntradayBar.feed == b.feed,
                MarketIntradayBar.adjustment_mode == b.adjustment_mode,
            )
            .first()
        )
        if existing:
            continue
        db.add(
            MarketIntradayBar(
                symbol=b.symbol.upper(),
                bar_time_utc=b.bar_time_utc,
                timeframe=b.timeframe,
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
                vwap=b.vwap,
                trade_count=b.trade_count,
                provider=b.provider,
                feed=b.feed,
                is_consolidated=b.is_consolidated,
                adjustment_mode=b.adjustment_mode,
                session_type=b.session_type,
                raw_payload_json=b.raw_payload_json if store_raw else None,
                fetched_at=b.fetched_at,
            )
        )
        count += 1
    db.flush()
    return count


def count_intraday_bars(db: Session) -> int:
    return db.query(MarketIntradayBar).count()


def count_unique_symbol_days(db: Session) -> int:
    from sqlalchemy import func

    q = (
        db.query(MarketIntradayBar.symbol, func.date(MarketIntradayBar.bar_time_utc))
        .distinct()
        .count()
    )
    return q


def _row_to_bar(r: MarketIntradayBar) -> IntradayBar:
    bt = r.bar_time_utc
    if bt.tzinfo is None:
        bt = bt.replace(tzinfo=timezone.utc)
    return IntradayBar(
        symbol=r.symbol,
        bar_time_utc=bt,
        timeframe=r.timeframe,
        open=r.open,
        high=r.high,
        low=r.low,
        close=r.close,
        volume=r.volume,
        vwap=r.vwap,
        trade_count=r.trade_count,
        provider=r.provider,
        feed=r.feed,
        adjustment_mode=r.adjustment_mode,
        is_consolidated=r.is_consolidated,
        fetched_at=r.fetched_at,
        session_type=r.session_type,
        raw_payload_json=r.raw_payload_json,
    )
