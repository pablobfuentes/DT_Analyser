"""Trade risk calculation and validation."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from app.db.models.trade import Trade
from app.utils.analytics import RealizedPnl, effective_realized_pnl
from app.utils.money import quantize_price, to_decimal

logger = logging.getLogger(__name__)

VALID_RISK_SOURCES = frozenset({"MANUAL", "IMPORTED", "PINE", "PINE_SIGNAL", "CALCULATED", "UNKNOWN"})
RISK_CONFLICT_TOLERANCE = Decimal("0.05")


@dataclass
class RiskComputation:
    initial_stop_price: Decimal | None
    initial_risk_per_share: Decimal | None
    initial_risk_amount: Decimal | None
    r_multiple: Decimal | None
    risk_source: str | None
    risk_notes: str | None
    warnings: list[str] = field(default_factory=list)
    uses_gross_pnl: bool = False


def validate_stop_for_direction(direction: str, entry: Decimal, stop: Decimal) -> str | None:
    if direction == "LONG" and stop >= entry:
        return "Initial stop for a LONG trade must be below the entry price."
    if direction == "SHORT" and stop <= entry:
        return "Initial stop for a SHORT trade must be above the entry price."
    return None


def risk_per_share_from_stop(direction: str, entry: Decimal, stop: Decimal) -> Decimal:
    if direction == "LONG":
        return entry - stop
    return stop - entry


def compute_risk_amount(
    trade: Trade,
    stop: Decimal | None,
    explicit_amount: Decimal | None,
) -> tuple[Decimal | None, Decimal | None, list[str]]:
    """Return (risk_per_share, risk_amount, warnings). Precedence: explicit amount, then stop-derived."""
    warnings: list[str] = []
    entry = trade.avg_entry_price
    qty = trade.quantity

    derived_amount: Decimal | None = None
    rps: Decimal | None = None

    if stop is not None:
        err = validate_stop_for_direction(trade.direction, entry, stop)
        if err:
            raise ValueError(err)
        rps = quantize_price(risk_per_share_from_stop(trade.direction, entry, stop))
        if rps <= 0:
            raise ValueError("Risk per share must be positive.")
        derived_amount = quantize_price(rps * qty)

    if explicit_amount is not None:
        if explicit_amount <= 0:
            raise ValueError("Initial risk amount must be positive.")
        explicit_amount = quantize_price(explicit_amount)
        if derived_amount is not None and abs(derived_amount - explicit_amount) > RISK_CONFLICT_TOLERANCE:
            warnings.append(
                f"Manually entered risk ({explicit_amount}) differs from stop-derived risk ({derived_amount})."
            )
        amount = explicit_amount
        if rps is None and qty > 0:
            rps = quantize_price(amount / qty)
    elif derived_amount is not None:
        amount = derived_amount
    else:
        return None, None, warnings

    return rps, amount, warnings


def compute_r_multiple(trade: Trade, risk_amount: Decimal | None) -> tuple[Decimal | None, bool]:
    """Return (r_multiple, uses_gross_pnl)."""
    if risk_amount is None or risk_amount <= 0:
        return None, False
    rp: RealizedPnl = effective_realized_pnl(trade)
    r = rp.pnl / risk_amount
    return r, not rp.includes_fees


def build_risk_computation(
    trade: Trade,
    *,
    initial_stop_price: Decimal | None = None,
    initial_risk_amount: Decimal | None = None,
    risk_source: str | None = None,
    risk_notes: str | None = None,
) -> RiskComputation:
    warnings: list[str] = []
    stop = initial_stop_price if initial_stop_price is not None else trade.initial_stop_price
    explicit = initial_risk_amount if initial_risk_amount is not None else None

    if stop is None and explicit is None:
        return RiskComputation(None, None, None, None, risk_source, risk_notes, warnings)

    rps, amount, w = compute_risk_amount(trade, stop, explicit)
    warnings.extend(w)
    r_mult, uses_gross = compute_r_multiple(trade, amount)
    if uses_gross:
        warnings.append("R calculated from gross P&L because fee data is unavailable.")

    src = risk_source or trade.risk_source or "MANUAL"
    if src not in VALID_RISK_SOURCES:
        src = "MANUAL"

    return RiskComputation(
        initial_stop_price=stop,
        initial_risk_per_share=rps,
        initial_risk_amount=amount,
        r_multiple=r_mult,
        risk_source=src,
        risk_notes=risk_notes if risk_notes is not None else trade.risk_notes,
        warnings=warnings,
        uses_gross_pnl=uses_gross,
    )


def apply_risk_to_trade(trade: Trade, comp: RiskComputation) -> None:
    """Legacy cache-only writer for pre-Step-7 unit tests.

    Production PATCH/import/recalc must use RiskService so trade_risk and
    the Trade cache stay atomic.
    """
    prev_stop = trade.initial_stop_price
    prev_amount = trade.initial_risk_amount

    trade.initial_stop_price = comp.initial_stop_price
    trade.initial_risk_per_share = comp.initial_risk_per_share
    trade.initial_risk_amount = comp.initial_risk_amount
    trade.r_multiple = comp.r_multiple
    trade.risk_source = comp.risk_source
    trade.risk_notes = comp.risk_notes
    trade.risk_updated_at = datetime.now(timezone.utc)

    logger.info(
        "Risk updated trade_id=%s stop %s→%s amount %s→%s source=%s",
        trade.id,
        prev_stop,
        comp.initial_stop_price,
        prev_amount,
        comp.initial_risk_amount,
        comp.risk_source,
    )


def parse_risk_payload(data: dict) -> tuple[Decimal | None, Decimal | None, str | None, str | None]:
    stop = to_decimal(data.get("initial_stop_price")) if data.get("initial_stop_price") is not None else None
    amount = to_decimal(data.get("initial_risk_amount")) if data.get("initial_risk_amount") is not None else None
    source = data.get("risk_source")
    notes = data.get("risk_notes")
    return stop, amount, source, notes
