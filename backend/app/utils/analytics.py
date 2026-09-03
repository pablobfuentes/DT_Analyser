"""Analytics helpers for dashboard calculations."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from app.config import settings
from app.db.models.trade import Trade
from app.utils.money import to_decimal

TradeOutcome = Literal["WIN", "LOSS", "BREAKEVEN"]


@dataclass
class RealizedPnl:
    pnl: Decimal
    includes_fees: bool


def analytics_tz() -> ZoneInfo:
    return ZoneInfo(settings.analytics_timezone)


def breakeven_tolerance() -> Decimal:
    return to_decimal(settings.breakeven_tolerance, Decimal("0.01"))


def effective_realized_pnl(trade: Trade) -> RealizedPnl:
    if trade.net_pnl is not None:
        return RealizedPnl(pnl=trade.net_pnl, includes_fees=True)
    if trade.gross_pnl is not None:
        return RealizedPnl(pnl=trade.gross_pnl, includes_fees=False)
    return RealizedPnl(pnl=Decimal("0"), includes_fees=False)


def classify_outcome(pnl: Decimal, tolerance: Decimal | None = None) -> TradeOutcome:
    tol = tolerance or breakeven_tolerance()
    if pnl > tol:
        return "WIN"
    if pnl < -tol:
        return "LOSS"
    return "BREAKEVEN"


def ny_date_from_utc(dt: datetime) -> date:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(analytics_tz()).date()


def ny_regular_session_complete(now: datetime | None = None) -> bool:
    """True at or after 16:00 America/New_York."""
    from app.utils.clock import utc_now

    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    local = current.astimezone(analytics_tz())
    return local.time() >= time(16, 0)


def ny_day_utc_bounds(day: date) -> tuple[datetime, datetime]:
    """Return UTC start/end for a New York calendar day."""
    tz = analytics_tz()
    start_local = datetime.combine(day, time.min, tzinfo=tz)
    end_local = datetime.combine(day, time.max.replace(microsecond=0), tzinfo=tz)
    return start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


def utc_bounds_for_ny_range(start: date | None, end: date | None) -> tuple[datetime | None, datetime | None]:
    utc_start = None
    utc_end = None
    if start:
        utc_start, _ = ny_day_utc_bounds(start)
    if end:
        _, utc_end = ny_day_utc_bounds(end)
    return utc_start, utc_end


def map_source_filter(source: str | None) -> str | None:
    if not source or source.upper() == "ALL":
        return None
    mapping = {
        "MANUAL": "TRADINGVIEW_MANUAL",
        "AUTO": "TRADINGVIEW_AUTO",
        "TRADINGVIEW_MANUAL": "TRADINGVIEW_MANUAL",
        "TRADINGVIEW_AUTO": "TRADINGVIEW_AUTO",
    }
    return mapping.get(source.upper())


def decimal_str(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def avg_decimal(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values) / Decimal(len(values))


def win_rate_pct(wins: int, losses: int) -> Decimal | None:
    denom = wins + losses
    if denom == 0:
        return None
    return (Decimal(wins) / Decimal(denom)) * Decimal("100")
