from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MarketDailyBar(Base):
    __tablename__ = "market_daily_bars"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "trading_date", "provider", "feed", "adjustment_mode",
            name="uq_market_bar",
        ),
        Index("ix_market_bars_symbol_date", "symbol", "trading_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(nullable=False)
    trading_date: Mapped[str] = mapped_column(nullable=False)  # ISO date string
    open: Mapped[Decimal] = mapped_column(nullable=False)
    high: Mapped[Decimal] = mapped_column(nullable=False)
    low: Mapped[Decimal] = mapped_column(nullable=False)
    close: Mapped[Decimal] = mapped_column(nullable=False)
    volume: Mapped[int] = mapped_column(nullable=False)
    vwap: Mapped[Decimal | None] = mapped_column(nullable=True)
    trade_count: Mapped[int | None] = mapped_column(nullable=True)
    provider: Mapped[str] = mapped_column(nullable=False)
    feed: Mapped[str] = mapped_column(nullable=False)
    adjustment_mode: Mapped[str] = mapped_column(nullable=False)
    is_consolidated: Mapped[bool] = mapped_column(nullable=False, default=True)
    raw_payload_json: Mapped[str | None] = mapped_column(nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow, onupdate=utcnow)


class InstrumentDayFeature(Base):
    __tablename__ = "instrument_day_features"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "trading_date",
            "provider",
            "feed",
            "adjustment_mode",
            "calculation_version",
            name="uq_instrument_day_prov",
        ),
        Index("ix_instrument_day_symbol_date", "symbol", "trading_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(nullable=False)
    trading_date: Mapped[str] = mapped_column(nullable=False)
    prior_close: Mapped[Decimal | None] = mapped_column(nullable=True)
    day_open: Mapped[Decimal | None] = mapped_column(nullable=True)
    day_high: Mapped[Decimal | None] = mapped_column(nullable=True)
    day_low: Mapped[Decimal | None] = mapped_column(nullable=True)
    day_close: Mapped[Decimal | None] = mapped_column(nullable=True)
    day_volume: Mapped[int | None] = mapped_column(nullable=True)
    opening_gap_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    daily_movement_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    rvol50_multiple: Mapped[Decimal | None] = mapped_column(nullable=True)
    prior_day_rvol50_multiple: Mapped[Decimal | None] = mapped_column(nullable=True)
    true_range: Mapped[Decimal | None] = mapped_column(nullable=True)
    atr14_prior: Mapped[Decimal | None] = mapped_column(nullable=True)
    relative_volatility_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    sma20_prior: Mapped[Decimal | None] = mapped_column(nullable=True)
    sma50_prior: Mapped[Decimal | None] = mapped_column(nullable=True)
    day_type: Mapped[str | None] = mapped_column(nullable=True)
    provider: Mapped[str] = mapped_column(nullable=False)
    feed: Mapped[str] = mapped_column(nullable=False)
    adjustment_mode: Mapped[str] = mapped_column(nullable=False, default="raw")
    quality_status: Mapped[str] = mapped_column(nullable=False, default="OK")
    quality_flags: Mapped[str | None] = mapped_column(nullable=True)
    completeness_status: Mapped[str] = mapped_column(nullable=False, default="COMPLETE")
    calculation_version: Mapped[str] = mapped_column(nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)


class TradeMarketFeature(Base):
    __tablename__ = "trade_market_features"
    __table_args__ = (Index("ix_trade_market_trade_id", "trade_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False, unique=True)
    instrument_feature_id: Mapped[int | None] = mapped_column(
        ForeignKey("instrument_day_features.id"), nullable=True
    )
    benchmark_feature_id: Mapped[int | None] = mapped_column(
        ForeignKey("instrument_day_features.id"), nullable=True
    )
    benchmark_symbol: Mapped[str | None] = mapped_column(nullable=True)
    entry_vs_atr_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    entry_vs_sma20_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    entry_vs_sma50_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    enrichment_status: Mapped[str] = mapped_column(nullable=False, default="FAILED")
    missing_reason: Mapped[str | None] = mapped_column(nullable=True)
    calculation_version: Mapped[str] = mapped_column(nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)


class MarketEnrichmentJob(Base):
    __tablename__ = "market_enrichment_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str | None] = mapped_column(nullable=True)
    feed: Mapped[str | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    trades_requested: Mapped[int] = mapped_column(nullable=False, default=0)
    symbols_requested: Mapped[int] = mapped_column(nullable=False, default=0)
    bars_fetched: Mapped[int] = mapped_column(nullable=False, default=0)
    cache_hits: Mapped[int] = mapped_column(nullable=False, default=0)
    features_calculated: Mapped[int] = mapped_column(nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(nullable=False, default="RUNNING")
    error_message: Mapped[str | None] = mapped_column(nullable=True)


class MarketCacheCoverage(Base):
    """Records the calendar range already requested from a provider for a provenance."""

    __tablename__ = "market_cache_coverage"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "provider", "feed", "adjustment_mode",
            name="uq_market_cache_coverage",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(nullable=False)
    provider: Mapped[str] = mapped_column(nullable=False)
    feed: Mapped[str] = mapped_column(nullable=False)
    adjustment_mode: Mapped[str] = mapped_column(nullable=False)
    probed_start: Mapped[str] = mapped_column(nullable=False)
    probed_end: Mapped[str] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)


class MarketIntradayBar(Base):
    __tablename__ = "market_intraday_bars"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "bar_time_utc",
            "timeframe",
            "provider",
            "feed",
            "adjustment_mode",
            name="uq_intraday_bar",
        ),
        Index("ix_intraday_symbol_time", "symbol", "bar_time_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(nullable=False)
    bar_time_utc: Mapped[datetime] = mapped_column(nullable=False)
    timeframe: Mapped[str] = mapped_column(nullable=False, default="1Min")
    open: Mapped[Decimal] = mapped_column(nullable=False)
    high: Mapped[Decimal] = mapped_column(nullable=False)
    low: Mapped[Decimal] = mapped_column(nullable=False)
    close: Mapped[Decimal] = mapped_column(nullable=False)
    volume: Mapped[int] = mapped_column(nullable=False)
    vwap: Mapped[Decimal | None] = mapped_column(nullable=True)
    trade_count: Mapped[int | None] = mapped_column(nullable=True)
    provider: Mapped[str] = mapped_column(nullable=False)
    feed: Mapped[str] = mapped_column(nullable=True)
    is_consolidated: Mapped[bool] = mapped_column(nullable=False, default=True)
    adjustment_mode: Mapped[str] = mapped_column(nullable=False)
    session_type: Mapped[str | None] = mapped_column(nullable=True)
    raw_payload_json: Mapped[str | None] = mapped_column(nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    created_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow, onupdate=utcnow)


class TradeExcursion(Base):
    __tablename__ = "trade_excursions"
    __table_args__ = (
        Index("ix_trade_excursions_trade_id", "trade_id"),
        Index("ix_trade_excursions_quality", "quality_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(nullable=False, unique=True)

    data_provider: Mapped[str | None] = mapped_column(nullable=True)
    data_feed: Mapped[str | None] = mapped_column(nullable=True)
    data_resolution: Mapped[str] = mapped_column(nullable=False, default="1Min")
    is_consolidated: Mapped[bool | None] = mapped_column(nullable=True)

    holding_start_utc: Mapped[datetime] = mapped_column(nullable=False)
    holding_end_utc: Mapped[datetime] = mapped_column(nullable=False)

    reference_entry_price: Mapped[Decimal | None] = mapped_column(nullable=True)

    # Price excursions (inclusive primary)
    price_mfe: Mapped[Decimal | None] = mapped_column(nullable=True)
    price_mae: Mapped[Decimal | None] = mapped_column(nullable=True)
    price_mfe_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    price_mae_pct: Mapped[Decimal | None] = mapped_column(nullable=True)

    conservative_price_mfe: Mapped[Decimal | None] = mapped_column(nullable=True)
    conservative_price_mae: Mapped[Decimal | None] = mapped_column(nullable=True)

    # Position excursions — inclusive (primary UI)
    position_mfe_amount: Mapped[Decimal | None] = mapped_column(nullable=True)
    position_mae_amount: Mapped[Decimal | None] = mapped_column(nullable=True)
    mfe_r: Mapped[Decimal | None] = mapped_column(nullable=True)
    mae_r: Mapped[Decimal | None] = mapped_column(nullable=True)

    # Position excursions — conservative
    conservative_position_mfe_amount: Mapped[Decimal | None] = mapped_column(nullable=True)
    conservative_position_mae_amount: Mapped[Decimal | None] = mapped_column(nullable=True)
    conservative_mfe_r: Mapped[Decimal | None] = mapped_column(nullable=True)
    conservative_mae_r: Mapped[Decimal | None] = mapped_column(nullable=True)

    mfe_boundary_spread_amount: Mapped[Decimal | None] = mapped_column(nullable=True)
    mfe_boundary_spread_r: Mapped[Decimal | None] = mapped_column(nullable=True)
    mae_boundary_spread_amount: Mapped[Decimal | None] = mapped_column(nullable=True)
    mae_boundary_spread_r: Mapped[Decimal | None] = mapped_column(nullable=True)

    mfe_time_utc: Mapped[datetime | None] = mapped_column(nullable=True)
    mae_time_utc: Mapped[datetime | None] = mapped_column(nullable=True)
    time_to_mfe_seconds: Mapped[int | None] = mapped_column(nullable=True)
    time_to_mae_seconds: Mapped[int | None] = mapped_column(nullable=True)
    mfe_to_exit_seconds: Mapped[int | None] = mapped_column(nullable=True)

    gross_realized_pnl: Mapped[Decimal | None] = mapped_column(nullable=True)
    gross_realized_r: Mapped[Decimal | None] = mapped_column(nullable=True)
    exit_efficiency_pct: Mapped[Decimal | None] = mapped_column(nullable=True)
    r_left_on_table: Mapped[Decimal | None] = mapped_column(nullable=True)

    peak_giveback_amount: Mapped[Decimal | None] = mapped_column(nullable=True)
    peak_giveback_r: Mapped[Decimal | None] = mapped_column(nullable=True)
    peak_giveback_pct: Mapped[Decimal | None] = mapped_column(nullable=True)

    post_exit_favorable_5m: Mapped[Decimal | None] = mapped_column(nullable=True)
    post_exit_favorable_15m: Mapped[Decimal | None] = mapped_column(nullable=True)
    post_exit_favorable_30m: Mapped[Decimal | None] = mapped_column(nullable=True)
    post_exit_favorable_5m_r: Mapped[Decimal | None] = mapped_column(nullable=True)
    post_exit_favorable_15m_r: Mapped[Decimal | None] = mapped_column(nullable=True)
    post_exit_favorable_30m_r: Mapped[Decimal | None] = mapped_column(nullable=True)

    copilot_exit_time_utc: Mapped[datetime | None] = mapped_column(nullable=True)
    copilot_exit_price: Mapped[Decimal | None] = mapped_column(nullable=True)
    copilot_exit_delta_seconds: Mapped[int | None] = mapped_column(nullable=True)
    copilot_exit_delta_price: Mapped[Decimal | None] = mapped_column(nullable=True)
    copilot_exit_delta_pct: Mapped[Decimal | None] = mapped_column(nullable=True)

    quality_status: Mapped[str] = mapped_column(nullable=False, default="PENDING")
    quality_flags_json: Mapped[str | None] = mapped_column(nullable=True)
    boundary_ambiguity: Mapped[bool] = mapped_column(nullable=False, default=False)
    efficiency_over_100: Mapped[bool] = mapped_column(nullable=False, default=False)
    sparse_interval: Mapped[bool] = mapped_column(nullable=False, default=False)
    longest_bar_gap_seconds: Mapped[int | None] = mapped_column(nullable=True)
    provider_missing_data: Mapped[bool] = mapped_column(nullable=False, default=False)

    calculation_version: Mapped[str] = mapped_column(nullable=False, default="1")
    calculated_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)


class ExcursionEnrichmentJob(Base):
    __tablename__ = "excursion_enrichment_jobs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str | None] = mapped_column(nullable=True)
    feed: Mapped[str | None] = mapped_column(nullable=True)
    started_at: Mapped[datetime] = mapped_column(nullable=False, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    trades_requested: Mapped[int] = mapped_column(nullable=False, default=0)
    symbol_days_requested: Mapped[int] = mapped_column(nullable=False, default=0)
    bars_fetched: Mapped[int] = mapped_column(nullable=False, default=0)
    cache_hits: Mapped[int] = mapped_column(nullable=False, default=0)
    provider_requests: Mapped[int] = mapped_column(nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_count: Mapped[int] = mapped_column(nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(nullable=False, default=0)
    status: Mapped[str] = mapped_column(nullable=False, default="RUNNING")
    error_message: Mapped[str | None] = mapped_column(nullable=True)
