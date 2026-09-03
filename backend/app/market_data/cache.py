"""Local daily-bar cache."""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.market_data import MarketCacheCoverage, MarketDailyBar
from app.market_data.calendar import collapse_dates_to_ranges, nyse_trading_days
from app.market_data.models import DailyBar
from app.utils.analytics import ny_date_from_utc
from app.utils.clock import utc_now


def load_cached_bars(
    db: Session,
    symbol: str,
    start: date,
    end: date,
    provider: str,
    feed: str,
    adjustment_mode: str,
) -> list[DailyBar]:
    rows = (
        db.query(MarketDailyBar)
        .filter(
            MarketDailyBar.symbol == symbol.upper(),
            MarketDailyBar.provider == provider,
            MarketDailyBar.feed == feed,
            MarketDailyBar.adjustment_mode == adjustment_mode,
            MarketDailyBar.trading_date >= start.isoformat(),
            MarketDailyBar.trading_date <= end.isoformat(),
        )
        .order_by(MarketDailyBar.trading_date)
        .all()
    )
    return [_row_to_bar(r) for r in rows]


def store_bars(db: Session, bars: list[DailyBar], overwrite: bool = False) -> int:
    """Insert new bars. Overwrite existing rows when refresh=True or the bar is today's session."""
    count = 0
    today_ny = ny_date_from_utc(utc_now())
    for b in bars:
        existing = (
            db.query(MarketDailyBar)
            .filter(
                MarketDailyBar.symbol == b.symbol.upper(),
                MarketDailyBar.trading_date == b.trading_date.isoformat(),
                MarketDailyBar.provider == b.provider,
                MarketDailyBar.feed == b.feed,
                MarketDailyBar.adjustment_mode == b.adjustment_mode,
            )
            .first()
        )
        if existing:
            if overwrite or b.trading_date == today_ny:
                existing.open = b.open
                existing.high = b.high
                existing.low = b.low
                existing.close = b.close
                existing.volume = b.volume
                existing.vwap = b.vwap
                existing.trade_count = b.trade_count
                existing.is_consolidated = b.is_consolidated
                existing.raw_payload_json = b.raw_payload_json
                existing.fetched_at = b.fetched_at
                existing.updated_at = datetime.now(timezone.utc)
                count += 1
            continue
        db.add(
            MarketDailyBar(
                symbol=b.symbol.upper(),
                trading_date=b.trading_date.isoformat(),
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
                vwap=b.vwap,
                trade_count=b.trade_count,
                provider=b.provider,
                feed=b.feed,
                adjustment_mode=b.adjustment_mode,
                is_consolidated=b.is_consolidated,
                raw_payload_json=b.raw_payload_json,
                fetched_at=b.fetched_at,
            )
        )
        count += 1
    db.flush()
    return count


def load_probed_range(
    db: Session,
    symbol: str,
    provider: str,
    feed: str,
    adjustment_mode: str,
) -> tuple[date, date] | None:
    row = (
        db.query(MarketCacheCoverage)
        .filter(
            MarketCacheCoverage.symbol == symbol.upper(),
            MarketCacheCoverage.provider == provider,
            MarketCacheCoverage.feed == feed,
            MarketCacheCoverage.adjustment_mode == adjustment_mode,
        )
        .first()
    )
    if not row:
        return None
    return date.fromisoformat(row.probed_start), date.fromisoformat(row.probed_end)


def mark_probed(
    db: Session,
    symbol: str,
    provider: str,
    feed: str,
    adjustment_mode: str,
    start: date,
    end: date,
) -> None:
    row = (
        db.query(MarketCacheCoverage)
        .filter(
            MarketCacheCoverage.symbol == symbol.upper(),
            MarketCacheCoverage.provider == provider,
            MarketCacheCoverage.feed == feed,
            MarketCacheCoverage.adjustment_mode == adjustment_mode,
        )
        .first()
    )
    if not row:
        db.add(
            MarketCacheCoverage(
                symbol=symbol.upper(),
                provider=provider,
                feed=feed,
                adjustment_mode=adjustment_mode,
                probed_start=start.isoformat(),
                probed_end=end.isoformat(),
            )
        )
        db.flush()
        return
    existing_start = date.fromisoformat(row.probed_start)
    existing_end = date.fromisoformat(row.probed_end)
    row.probed_start = min(existing_start, start).isoformat()
    row.probed_end = max(existing_end, end).isoformat()
    row.updated_at = datetime.now(timezone.utc)
    db.flush()


def missing_date_ranges(
    cached: list[DailyBar],
    start: date,
    end: date,
    probed: tuple[date, date] | None = None,
) -> list[tuple[date, date]]:
    """Return NYSE trading-day ranges not present in cache and not already probed.

    Weekends and NYSE holidays are never treated as missing bars.
    Days already requested from the provider (even if no bar exists — new listings,
    halted symbols) are not refetched.
    """
    have = {b.trading_date for b in cached}
    expected = nyse_trading_days(start, end)
    probed_days = set(nyse_trading_days(probed[0], probed[1])) if probed else set()
    missing = [d for d in expected if d not in have and d not in probed_days]
    return collapse_dates_to_ranges(missing)


def _row_to_bar(r: MarketDailyBar) -> DailyBar:
    return DailyBar(
        symbol=r.symbol,
        trading_date=date.fromisoformat(r.trading_date),
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
        raw_payload_json=r.raw_payload_json,
    )


def count_cached_bars(db: Session) -> int:
    return db.query(MarketDailyBar).count()
