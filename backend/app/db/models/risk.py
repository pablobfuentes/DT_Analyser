"""Trade risk audit model (1:1 with Trade) plus append-only audit log."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TradeRisk(Base):
    __tablename__ = "trade_risk"
    __table_args__ = (
        UniqueConstraint("trade_id", name="uq_trade_risk_trade_id"),
        Index("ix_trade_risk_quality", "risk_quality_status"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)

    initial_stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    actual_risk_per_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    actual_initial_risk_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    explicit_initial_risk_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    stop_derived_risk_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    planned_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    planned_stop_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    planned_risk_per_share: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    planned_risk_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    allowed_risk: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    suggested_shares: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)

    stop_distance_pct: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    risk_pct_equity_at_entry: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    equity_before_entry: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    r_multiple: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    r_pnl_basis: Mapped[str | None] = mapped_column(String(8), nullable=True)
    fees_known: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    risk_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    stop_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    risk_quality_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    risk_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculation_version: Mapped[str] = mapped_column(String(8), default="1", nullable=False)
    manual_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class RiskAuditLog(Base):
    __tablename__ = "risk_audit_log"
    __table_args__ = (
        Index("ix_risk_audit_trade_id", "trade_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id", ondelete="CASCADE"), nullable=False)
    field: Mapped[str] = mapped_column(String(64), nullable=False)
    old_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    new_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
