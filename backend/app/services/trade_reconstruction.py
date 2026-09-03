from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.importers.base import NormalizedExecution, NormalizedTrade
from app.utils.money import calculate_gross_pnl, calculate_net_pnl, quantize_price, quantize_quantity


@dataclass
class ExecutionAllocation:
    execution: NormalizedExecution
    role: str  # ENTRY or EXIT
    quantity: Decimal


@dataclass
class ReconstructedTrade:
    ticker: str
    direction: str
    entry_time_utc: datetime
    exit_time_utc: datetime | None
    avg_entry_price: Decimal
    avg_exit_price: Decimal | None
    quantity: Decimal
    gross_pnl: Decimal | None
    fees: Decimal | None
    status: str
    allocations: list[ExecutionAllocation] = field(default_factory=list)

    @property
    def entry_executions(self) -> list[tuple[NormalizedExecution, str]]:
        return [(a.execution, a.role) for a in self.allocations if a.role == "ENTRY"]

    @property
    def exit_executions(self) -> list[tuple[NormalizedExecution, str]]:
        return [(a.execution, a.role) for a in self.allocations if a.role == "EXIT"]


@dataclass
class ReconstructionResult:
    trades: list[ReconstructedTrade] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)
    flips_handled: int = 0


@dataclass
class _Fill:
    quantity: Decimal
    price: Decimal
    execution: NormalizedExecution


@dataclass
class _TradeCycle:
    direction: str
    entry_fills: list[_Fill] = field(default_factory=list)
    exit_fills: list[_Fill] = field(default_factory=list)
    allocations: list[ExecutionAllocation] = field(default_factory=list)
    entry_time: datetime | None = None
    exit_time: datetime | None = None
    fees: Decimal = field(default_factory=lambda: Decimal("0"))


def _execution_sort_key(ex: NormalizedExecution) -> tuple:
    """Deterministic order: time, then source-row/id, then identifiers.

    Do not sort same-timestamp fills by lexicographic order_id — that can invert
    CSV/export sequence. row_number is CSV row at parse time and Execution.id
    when rebuilding from persisted rows.
    """
    return (
        ex.execution_time_utc,
        ex.row_number,
        ex.external_execution_id or "",
        ex.order_id or "",
    )


def _weighted_avg(fills: list[_Fill]) -> Decimal:
    total_qty = sum(f.quantity for f in fills)
    if total_qty == 0:
        return Decimal("0")
    total_cost = sum(f.quantity * f.price for f in fills)
    return quantize_price(total_cost / total_qty)


def _validate_execution(ex: NormalizedExecution) -> str | None:
    if ex.quantity is None or ex.quantity <= 0:
        return "quantity must be positive"
    if ex.price is None or ex.price <= 0:
        return "missing or invalid execution price"
    if ex.execution_time_utc is None:
        return "missing timestamp"
    return None


def _resolve_side(ex: NormalizedExecution, position_qty: Decimal) -> tuple[str | None, str | None]:
    """Return (effective_side, error_message). effective_side: BUY, SELL, SELL_SHORT, BUY_TO_COVER."""
    side = (ex.side or "UNKNOWN").upper()

    if side == "UNKNOWN":
        return None, "UNKNOWN side with no position-state basis"

    if side == "BUY":
        if position_qty < 0:
            return "BUY_TO_COVER", None
        return "BUY", None

    if side == "SELL":
        if position_qty > 0:
            return "SELL", None
        return "SELL_SHORT", None

    if side == "SELL_SHORT":
        if position_qty > 0:
            return None, f"SELL_SHORT contradicts open LONG position ({position_qty})"
        return "SELL_SHORT", None

    if side == "BUY_TO_COVER":
        if position_qty >= 0:
            return None, f"BUY_TO_COVER contradicts non-SHORT position ({position_qty})"
        return "BUY_TO_COVER", None

    return None, f"unsupported side {ex.side}"


class TradeReconstructor:
    """Position-cycle weighted-average reconstruction with signed position state."""

    def reconstruct(self, executions: list[NormalizedExecution]) -> ReconstructionResult:
        by_ticker: dict[str, list[NormalizedExecution]] = {}
        for ex in sorted(executions, key=_execution_sort_key):
            by_ticker.setdefault(ex.ticker, []).append(ex)

        all_trades: list[ReconstructedTrade] = []
        all_errors: list[dict] = []
        all_warnings: list[dict] = []
        flips = 0

        for ticker, ticker_execs in by_ticker.items():
            result = self._reconstruct_ticker(ticker, ticker_execs)
            all_trades.extend(result.trades)
            all_errors.extend(result.errors)
            all_warnings.extend(result.warnings)
            flips += result.flips_handled

        return ReconstructionResult(
            trades=all_trades,
            errors=all_errors,
            warnings=all_warnings,
            flips_handled=flips,
        )

    def _reconstruct_ticker(self, ticker: str, executions: list[NormalizedExecution]) -> ReconstructionResult:
        trades: list[ReconstructedTrade] = []
        errors: list[dict] = []
        warnings: list[dict] = []
        flips_handled = 0

        cycle: _TradeCycle | None = None
        position_qty = Decimal("0")
        saw_opening_fill = False

        def start_cycle(direction: str, entry_time: datetime) -> _TradeCycle:
            return _TradeCycle(direction=direction, entry_time=entry_time)

        def emit_closed_cycle(c: _TradeCycle) -> ReconstructedTrade | None:
            if not c.entry_fills:
                return None
            trade_qty = sum(f.quantity for f in c.entry_fills)
            exit_qty = sum(f.quantity for f in c.exit_fills)
            if exit_qty < trade_qty:
                return None

            avg_entry = _weighted_avg(c.entry_fills)
            avg_exit = _weighted_avg(c.exit_fills) if c.exit_fills else None
            gross = None
            if avg_exit is not None:
                gross = calculate_gross_pnl(c.direction, avg_entry, avg_exit, trade_qty)

            return ReconstructedTrade(
                ticker=ticker,
                direction=c.direction,
                entry_time_utc=c.entry_time or c.entry_fills[0].execution.execution_time_utc,
                exit_time_utc=c.exit_time,
                avg_entry_price=avg_entry,
                avg_exit_price=avg_exit,
                quantity=quantize_quantity(trade_qty),
                gross_pnl=gross,
                fees=c.fees if c.fees > 0 else None,
                status="CLOSED",
                allocations=list(c.allocations),
            )

        def emit_open_cycle(c: _TradeCycle) -> ReconstructedTrade | None:
            if not c.entry_fills:
                return None
            trade_qty = sum(f.quantity for f in c.entry_fills)
            exit_qty = sum(f.quantity for f in c.exit_fills)
            open_qty = trade_qty - exit_qty
            if open_qty <= 0:
                return None
            avg_entry = _weighted_avg(c.entry_fills)
            return ReconstructedTrade(
                ticker=ticker,
                direction=c.direction,
                entry_time_utc=c.entry_time or c.entry_fills[0].execution.execution_time_utc,
                exit_time_utc=None,
                avg_entry_price=avg_entry,
                avg_exit_price=None,
                quantity=quantize_quantity(open_qty),
                gross_pnl=None,
                fees=c.fees if c.fees > 0 else None,
                status="OPEN",
                allocations=list(c.allocations),
            )

        def add_entry(c: _TradeCycle, ex: NormalizedExecution, qty: Decimal):
            if c.entry_time is None:
                c.entry_time = ex.execution_time_utc
            fill = _Fill(quantity=qty, price=ex.price, execution=ex)
            c.entry_fills.append(fill)
            c.allocations.append(ExecutionAllocation(ex, "ENTRY", qty))

        def add_exit(c: _TradeCycle, ex: NormalizedExecution, qty: Decimal):
            fill = _Fill(quantity=qty, price=ex.price, execution=ex)
            c.exit_fills.append(fill)
            c.exit_time = ex.execution_time_utc
            c.allocations.append(ExecutionAllocation(ex, "EXIT", qty))

        def allocate_fee(c: _TradeCycle | None, ex: NormalizedExecution, portion_qty: Decimal):
            if c is None or not ex.fees or ex.quantity <= 0:
                return
            c.fees += ex.fees * (portion_qty / ex.quantity)

        for ex in executions:
            validation_err = _validate_execution(ex)
            if validation_err:
                errors.append(
                    {
                        "row_number": ex.row_number,
                        "error_type": "TradeReconstructionError",
                        "message": validation_err,
                        "raw_row": ex.raw_row,
                    }
                )
                continue

            effective_side, side_err = _resolve_side(ex, position_qty)
            if side_err or effective_side is None:
                errors.append(
                    {
                        "row_number": ex.row_number,
                        "error_type": "TradeReconstructionError",
                        "message": side_err or "unable to resolve side",
                        "raw_row": ex.raw_row,
                    }
                )
                continue

            remaining = ex.quantity

            if not saw_opening_fill:
                saw_opening_fill = True
                if position_qty == 0 and effective_side in ("SELL", "SELL_SHORT"):
                    warnings.append(
                        {
                            "row_number": ex.row_number,
                            "error_type": "UNKNOWN_OPENING_POSITION",
                            "ticker": ticker,
                            "message": (
                                f"[{ticker}] History starts with {effective_side} and no prior "
                                "fills are present. Reconstruction assumes the account was FLAT "
                                "and opens SHORT. If this export is truncated, this SELL may have "
                                "closed a prior LONG. Import earlier executions to resolve."
                            ),
                            "raw_row": ex.raw_row,
                        }
                    )

            if effective_side in ("BUY", "BUY_TO_COVER"):
                while remaining > 0:
                    if position_qty < 0:
                        cover_qty = min(remaining, abs(position_qty))
                        if cycle is None or cycle.direction != "SHORT":
                            errors.append(
                                {
                                    "row_number": ex.row_number,
                                    "error_type": "TradeReconstructionError",
                                    "message": "SHORT cover without active SHORT cycle",
                                    "raw_row": ex.raw_row,
                                }
                            )
                            remaining = Decimal("0")
                            break
                        add_exit(cycle, ex, cover_qty)
                        allocate_fee(cycle, ex, cover_qty)
                        position_qty += cover_qty
                        remaining -= cover_qty

                        if position_qty == 0:
                            closed = emit_closed_cycle(cycle)
                            if closed:
                                trades.append(closed)
                            cycle = None

                        if remaining > 0 and position_qty == 0:
                            flips_handled += 1
                            cycle = start_cycle("LONG", ex.execution_time_utc)
                            add_entry(cycle, ex, remaining)
                            allocate_fee(cycle, ex, remaining)
                            position_qty += remaining
                            remaining = Decimal("0")

                    elif position_qty == 0:
                        cycle = start_cycle("LONG", ex.execution_time_utc)
                        add_entry(cycle, ex, remaining)
                        allocate_fee(cycle, ex, remaining)
                        position_qty += remaining
                        remaining = Decimal("0")

                    else:
                        if cycle is None or cycle.direction != "LONG":
                            cycle = start_cycle("LONG", ex.execution_time_utc)
                        add_entry(cycle, ex, remaining)
                        allocate_fee(cycle, ex, remaining)
                        position_qty += remaining
                        remaining = Decimal("0")

            elif effective_side in ("SELL", "SELL_SHORT"):
                while remaining > 0:
                    if position_qty > 0:
                        close_qty = min(remaining, position_qty)
                        if cycle is None or cycle.direction != "LONG":
                            errors.append(
                                {
                                    "row_number": ex.row_number,
                                    "error_type": "TradeReconstructionError",
                                    "message": "LONG close without active LONG cycle",
                                    "raw_row": ex.raw_row,
                                }
                            )
                            remaining = Decimal("0")
                            break
                        add_exit(cycle, ex, close_qty)
                        allocate_fee(cycle, ex, close_qty)
                        position_qty -= close_qty
                        remaining -= close_qty

                        if position_qty == 0:
                            closed = emit_closed_cycle(cycle)
                            if closed:
                                trades.append(closed)
                            cycle = None

                        if remaining > 0 and position_qty == 0:
                            flips_handled += 1
                            cycle = start_cycle("SHORT", ex.execution_time_utc)
                            add_entry(cycle, ex, remaining)
                            allocate_fee(cycle, ex, remaining)
                            position_qty -= remaining
                            remaining = Decimal("0")

                    elif position_qty == 0:
                        cycle = start_cycle("SHORT", ex.execution_time_utc)
                        add_entry(cycle, ex, remaining)
                        allocate_fee(cycle, ex, remaining)
                        position_qty -= remaining
                        remaining = Decimal("0")

                    else:
                        if cycle is None or cycle.direction != "SHORT":
                            cycle = start_cycle("SHORT", ex.execution_time_utc)
                        add_entry(cycle, ex, remaining)
                        allocate_fee(cycle, ex, remaining)
                        position_qty -= remaining
                        remaining = Decimal("0")

        if cycle and cycle.entry_fills:
            open_trade = emit_open_cycle(cycle)
            if open_trade:
                trades.append(open_trade)
            elif cycle.exit_fills:
                closed = emit_closed_cycle(cycle)
                if closed:
                    trades.append(closed)

        for trade in trades:
            self._assert_trade_integrity(trade)

        return ReconstructionResult(
            trades=trades,
            errors=errors,
            warnings=warnings,
            flips_handled=flips_handled,
        )

    @staticmethod
    def _assert_trade_integrity(trade: ReconstructedTrade):
        entry_qty = sum(a.quantity for a in trade.allocations if a.role == "ENTRY")
        exit_qty = sum(a.quantity for a in trade.allocations if a.role == "EXIT")
        if trade.status == "CLOSED":
            assert entry_qty == trade.quantity, f"{trade.ticker} entry qty mismatch"
            assert exit_qty == trade.quantity, f"{trade.ticker} exit qty mismatch"
        else:
            assert exit_qty <= entry_qty, f"{trade.ticker} over-closed open trade"
            assert entry_qty - exit_qty == trade.quantity, f"{trade.ticker} open qty mismatch"


def reconstructed_to_normalized(trade: ReconstructedTrade) -> NormalizedTrade:
    net = None
    if trade.gross_pnl is not None:
        net = calculate_net_pnl(trade.gross_pnl, trade.fees)
    return NormalizedTrade(
        ticker=trade.ticker,
        direction=trade.direction,
        entry_time_utc=trade.entry_time_utc,
        exit_time_utc=trade.exit_time_utc,
        avg_entry_price=trade.avg_entry_price,
        avg_exit_price=trade.avg_exit_price,
        quantity=trade.quantity,
        gross_pnl=trade.gross_pnl,
        fees=trade.fees,
        net_pnl=net,
        status=trade.status,
        executions=[a.execution for a in trade.allocations],
    )
