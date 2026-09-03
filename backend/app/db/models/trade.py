from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Trade(Base):
    __tablename__ = "trades"
    __table_args__ = (
        UniqueConstraint("account_id", "trade_fingerprint", name="uq_trade_fingerprint"),
        Index("ix_trades_ticker", "ticker"),
        Index("ix_trades_entry_time", "entry_time_utc"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    source_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_trade_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    trade_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    entry_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    exit_time_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    avg_exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    gross_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    fees: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    net_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    source_reported_pnl: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    pnl_mismatch_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    holding_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_row_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    initial_risk_per_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    initial_risk_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    r_multiple: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    risk_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
