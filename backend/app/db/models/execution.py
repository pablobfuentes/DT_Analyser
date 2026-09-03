from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Execution(Base):
    __tablename__ = "executions"
    __table_args__ = (
        UniqueConstraint("account_id", "execution_fingerprint", name="uq_execution_fingerprint"),
        Index("ix_executions_ticker", "ticker"),
        Index("ix_executions_time", "execution_time_utc"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    import_batch_id: Mapped[int] = mapped_column(ForeignKey("import_batches.id"), nullable=False)
    external_execution_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    execution_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    ticker: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(16), nullable=False)
    execution_time_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    execution_time_original: Mapped[str] = mapped_column(String(64), nullable=False)
    timezone_original: Mapped[str | None] = mapped_column(String(64), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
    fees: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    order_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    raw_row_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
