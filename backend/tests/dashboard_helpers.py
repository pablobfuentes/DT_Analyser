"""Dashboard test helpers."""

from datetime import datetime, timezone
from decimal import Decimal

from app.db.models.trade import Trade


def make_trade(
    db,
    account_id: int,
    *,
    source_type: str = "TRADINGVIEW_MANUAL",
    ticker: str = "TEST",
    direction: str = "LONG",
    net_pnl: Decimal | None = None,
    gross_pnl: Decimal | None = None,
    fees: Decimal | None = None,
    exit_time: datetime | None = None,
    entry_time: datetime | None = None,
    quantity: Decimal = Decimal("100"),
    status: str = "CLOSED",
    holding_seconds: int = 300,
    pnl_mismatch_flag: bool = False,
) -> Trade:
    entry = entry_time or datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc)
    exit = exit_time or datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
    fp = f"test-{account_id}-{ticker}-{exit.isoformat()}-{net_pnl}"
    trade = Trade(
        account_id=account_id,
        source_type=source_type,
        trade_fingerprint=fp,
        ticker=ticker,
        direction=direction,
        entry_time_utc=entry,
        exit_time_utc=exit if status == "CLOSED" else None,
        avg_entry_price=Decimal("10"),
        avg_exit_price=Decimal("11") if status == "CLOSED" else None,
        quantity=quantity,
        gross_pnl=gross_pnl if gross_pnl is not None else net_pnl,
        fees=fees,
        net_pnl=net_pnl,
        holding_seconds=holding_seconds if status == "CLOSED" else None,
        status=status,
        pnl_mismatch_flag=pnl_mismatch_flag,
    )
    db.add(trade)
    db.commit()
    db.refresh(trade)
    return trade


def seed_example_trades(db, manual_account, strategy_account):
    """Fixture from Step 2 spec section 31."""
    make_trade(db, manual_account.id, net_pnl=Decimal("100"), gross_pnl=Decimal("100"), fees=Decimal("0"), ticker="T1")
    make_trade(db, manual_account.id, net_pnl=Decimal("-50"), gross_pnl=Decimal("-50"), ticker="T2")
    make_trade(db, strategy_account.id, source_type="TRADINGVIEW_AUTO", net_pnl=Decimal("75"), gross_pnl=Decimal("75"), ticker="T3")
    make_trade(
        db,
        strategy_account.id,
        source_type="TRADINGVIEW_AUTO",
        direction="SHORT",
        net_pnl=Decimal("-25"),
        gross_pnl=Decimal("-25"),
        ticker="T4",
    )
    make_trade(db, manual_account.id, net_pnl=Decimal("0"), gross_pnl=Decimal("0"), ticker="T5")
