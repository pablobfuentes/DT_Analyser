"""Pine Signal domain: independent of Trade."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Signal(Base):
    __tablename__ = "signals"
    __table_args__ = (
        UniqueConstraint("signal_id", name="uq_signals_signal_id"),
        Index("ix_signals_ticker_entry", "ticker", "entry_signal_time_utc"),
        Index("ix_signals_strategy_key", "strategy_key"),
        Index("ix_signals_strategy_version", "strategy_version"),
        Index("ix_signals_origin", "signal_origin"),
        Index("ix_signals_match_status", "match_status"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_id: Mapped[str] = mapped_column(String(256), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_key: Mapped[str] = mapped_column(String(64), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version_normalized: Mapped[str] = mapped_column(String(64), nullable=False)
    script_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_origin: Mapped[str] = mapped_column(String(32), nullable=False)
    armed_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    entry_signal_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_signal_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False, default="INCOMPLETE")
    match_status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNLINKED")
    planned_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    planned_stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    reference_2r_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    suggested_shares: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    allowed_risk: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    planned_position_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    planned_exposure_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    setup_quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    signal_gap_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    signal_rvol: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    impulse_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    retracement_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    context_5m: Mapped[str | None] = mapped_column(String(32), nullable=True)
    above_vwap: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    above_ema9: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    volume_confirmed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    session_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mechanical_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    mechanical_exit_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strategy_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    legacy: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("pine_import_batches.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class SignalEvent(Base):
    __tablename__ = "signal_events"
    __table_args__ = (
        UniqueConstraint("event_fingerprint", name="uq_signal_event_fingerprint"),
        Index("ix_signal_events_signal_id", "signal_pk"),
        Index("ix_signal_events_external", "external_signal_id", "event_type"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    signal_pk: Mapped[int] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    external_signal_id: Mapped[str] = mapped_column(String(256), nullable=False)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False)
    event_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    event_time_original: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    bar_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    event_origin: Mapped[str] = mapped_column(String(32), nullable=False)
    raw_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    raw_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    event_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)
    strategy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class SignalEventConflict(Base):
    """Same fingerprint, different snapshot — original event is not mutated."""

    __tablename__ = "signal_event_conflicts"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    existing_event_id: Mapped[int] = mapped_column(
        ForeignKey("signal_events.id", ondelete="CASCADE"), nullable=False
    )
    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("pine_import_batches.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str] = mapped_column(String(32), nullable=False, default="EVENT_PAYLOAD_CONFLICT")
    incoming_raw_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    incoming_payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TradeSignalLink(Base):
    __tablename__ = "trade_signal_links"
    __table_args__ = (
        UniqueConstraint("trade_id", "signal_id", name="uq_trade_signal_pair"),
        Index("ix_trade_signal_links_trade", "trade_id"),
        Index("ix_trade_signal_links_signal", "signal_id"),
        Index("ix_trade_signal_links_status", "link_status"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)
    signal_id: Mapped[int] = mapped_column(ForeignKey("signals.id", ondelete="CASCADE"), nullable=False)
    match_type: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    time_delta_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    link_status: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class PineImportBatch(Base):
    __tablename__ = "pine_import_batches"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    filename: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    row_count_raw: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_valid: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_imported: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_duplicate: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_conflict: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    row_count_error: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    signal_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    armed_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    exit_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    realtime_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    historical_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    unknown_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    import_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    import_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PineImportError(Base):
    __tablename__ = "pine_import_errors"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("pine_import_batches.id", ondelete="CASCADE"), nullable=False)
    line_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_line: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
