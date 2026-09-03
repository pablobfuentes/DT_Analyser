from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TradeExecution(Base):
    __tablename__ = "trade_executions"

    trade_id: Mapped[int] = mapped_column(ForeignKey("trades.id"), primary_key=True)
    execution_id: Mapped[int] = mapped_column(ForeignKey("executions.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    allocated_quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6), nullable=False)
