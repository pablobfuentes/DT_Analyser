"""Cross-source validation for imports (executions, reconstructed P&L)."""

from dataclasses import dataclass, field
from decimal import Decimal

from app.db.models.execution import Execution
from app.db.models.trade import Trade
from app.utils.money import calculate_gross_pnl, pnl_mismatch, to_decimal


@dataclass
class ExecutionMismatch:
    order_id: str
    field: str
    expected: str
    actual: str


@dataclass
class ValidationResult:
    ok: bool
    execution_mismatches: list[ExecutionMismatch] = field(default_factory=list)
    pnl_mismatches: list[int] = field(default_factory=list)
    message: str = ""


def compare_executions(
    reference: list[Execution],
    candidate: list[Execution],
    *,
    key_attr: str = "external_execution_id",
) -> list[ExecutionMismatch]:
    """Compare candidate executions against a reference set by order/external ID."""
    ref_map: dict[str, Execution] = {}
    for ex in reference:
        key = getattr(ex, key_attr, None) or ex.order_id
        if key:
            ref_map[str(key)] = ex

    mismatches: list[ExecutionMismatch] = []
    for ex in candidate:
        key = getattr(ex, key_attr, None) or ex.order_id
        if not key:
            continue
        ref = ref_map.get(str(key))
        if not ref:
            continue
        if ex.ticker != ref.ticker:
            mismatches.append(ExecutionMismatch(str(key), "ticker", ref.ticker, ex.ticker))
        if ex.side != ref.side:
            mismatches.append(ExecutionMismatch(str(key), "side", ref.side, ex.side))
        if ex.quantity != ref.quantity:
            mismatches.append(
                ExecutionMismatch(str(key), "quantity", str(ref.quantity), str(ex.quantity))
            )
        if ex.price != ref.price:
            mismatches.append(
                ExecutionMismatch(str(key), "price", str(ref.price), str(ex.price))
            )
    return mismatches


def validate_trade_pnl(trade: Trade, tolerance: Decimal | None = None) -> bool:
    """Verify calculated gross P&L matches stored gross P&L for closed trades."""
    tol = tolerance or Decimal("0.01")
    if trade.status != "CLOSED" or trade.avg_exit_price is None:
        return True
    if trade.gross_pnl is None:
        return True
    calculated = calculate_gross_pnl(
        trade.direction, trade.avg_entry_price, trade.avg_exit_price, trade.quantity
    )
    return not pnl_mismatch(calculated, trade.gross_pnl, tol)


def validate_reconstructed_trades(trades: list[Trade], tolerance: Decimal | None = None) -> ValidationResult:
    """Validate reconstructed trade P&L consistency."""
    tol = tolerance or Decimal("0.01")
    bad_ids = [t.id for t in trades if not validate_trade_pnl(t, tol)]
    return ValidationResult(
        ok=len(bad_ids) == 0,
        pnl_mismatches=bad_ids,
        message=f"{len(bad_ids)} trades with P&L inconsistency" if bad_ids else "OK",
    )
