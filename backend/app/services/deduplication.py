from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.execution import Execution
from app.db.models.trade import Trade
from app.importers.base import NormalizedExecution, NormalizedTrade
from app.utils.hashing import fingerprint_from_parts


def execution_fingerprint(
    account_id: int,
    execution: NormalizedExecution,
) -> str:
    if execution.external_execution_id:
        return fingerprint_from_parts(account_id, execution.external_execution_id)
    return fingerprint_from_parts(
        account_id,
        execution.ticker,
        execution.side,
        execution.execution_time_utc.isoformat(),
        execution.quantity,
        execution.price,
        execution.order_id or "",
    )


def trade_fingerprint(
    account_id: int,
    source_type: str,
    trade: NormalizedTrade,
) -> str:
    if trade.external_trade_id:
        return fingerprint_from_parts(account_id, trade.external_trade_id)
    return fingerprint_from_parts(
        account_id,
        source_type,
        trade.ticker,
        trade.direction,
        trade.entry_time_utc.isoformat(),
        trade.exit_time_utc.isoformat() if trade.exit_time_utc else "",
        trade.quantity,
        trade.avg_entry_price,
        trade.avg_exit_price or "",
    )


def execution_exists(db: Session, account_id: int, fingerprint: str) -> bool:
    return (
        db.query(Execution)
        .filter(
            Execution.account_id == account_id,
            Execution.execution_fingerprint == fingerprint,
        )
        .first()
        is not None
    )


def trade_exists(db: Session, account_id: int, fingerprint: str) -> bool:
    return (
        db.query(Trade)
        .filter(
            Trade.account_id == account_id,
            Trade.trade_fingerprint == fingerprint,
        )
        .first()
        is not None
    )
