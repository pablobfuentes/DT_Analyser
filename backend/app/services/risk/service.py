"""RiskService — sole authoritative writer of trade_risk and denormalized Trade risk cache."""

from __future__ import annotations

import bisect
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.account import Account
from app.db.models.risk import RiskAuditLog, TradeRisk
from app.db.models.signal import Signal, TradeSignalLink
from app.db.models.trade import Trade
from app.services.analytics.risk import (
    compute_r_multiple,
    risk_per_share_from_stop,
    validate_stop_for_direction,
)
from app.services.signals.matcher import STATUS_CONFIRMED, confirmed_signal_for_trade
from app.utils.analytics import effective_realized_pnl
from app.utils.money import quantize_price, to_decimal

logger = logging.getLogger(__name__)

CALC_VERSION = "1"
R_QUANTUM = Decimal("0.00000001")

SOURCE_MANUAL = "MANUAL"
SOURCE_PINE = "PINE_SIGNAL"
SOURCE_IMPORTED = "IMPORTED"
SOURCE_CALCULATED = "CALCULATED"
SOURCE_UNKNOWN = "UNKNOWN"
VALID_SOURCES = frozenset({SOURCE_MANUAL, SOURCE_PINE, SOURCE_IMPORTED, SOURCE_CALCULATED, SOURCE_UNKNOWN, "PINE"})


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _dec_str(v) -> str | None:
    if v is None:
        return None
    return format(v, "f")


def quantize_r(value: Decimal) -> Decimal:
    return value.quantize(R_QUANTUM, rounding=ROUND_HALF_UP)


def planned_risk_from_signal(signal: Signal) -> tuple[Decimal | None, Decimal | None]:
    """Return (planned_risk_per_share, planned_risk_amount). allowed_risk is never the denominator."""
    entry = signal.planned_entry_price
    stop = signal.planned_stop_price
    shares = signal.suggested_shares
    if entry is None or stop is None:
        return None, None
    err = validate_stop_for_direction(signal.direction, entry, stop)
    if err:
        return None, None
    rps = risk_per_share_from_stop(signal.direction, entry, stop)
    if rps <= 0:
        return None, None
    amount = None
    if shares is not None:
        amount = rps * shares
    return rps, amount


def classify_missing_reason(
    trade: Trade,
    risk: TradeRisk | None,
    has_signal: bool,
) -> str | None:
    """Direct cause of missing R. NO_SIGNAL_AVAILABLE is context, not the primary reason."""
    if trade.status != "CLOSED":
        return None
    if risk and risk.r_multiple is not None and risk.actual_initial_risk_amount and risk.actual_initial_risk_amount > 0:
        return None
    if risk and risk.risk_quality_status == "INVALID_STOP":
        return "INVALID_STOP"
    if trade.avg_entry_price is None:
        return "MISSING_ENTRY"
    if trade.quantity is None or trade.quantity <= 0:
        return "MISSING_QUANTITY"
    if risk and risk.risk_quality_status == "AMBIGUOUS_SCALE_IN":
        return "AMBIGUOUS_SCALE_IN"
    if risk and risk.manual_override and risk.risk_quality_status == "MANUAL_REVIEW":
        return "MANUAL_REVIEW"
    if trade.initial_stop_price is None and (risk is None or risk.initial_stop_price is None):
        return "MISSING_STOP"
    if risk and risk.risk_quality_status:
        return risk.risk_quality_status
    return "MISSING_STOP"


@dataclass
class RiskComputationResult:
    initial_stop_price: Decimal | None = None
    actual_risk_per_share: Decimal | None = None
    actual_initial_risk_amount: Decimal | None = None
    explicit_initial_risk_amount: Decimal | None = None
    stop_derived_risk_amount: Decimal | None = None
    planned_entry_price: Decimal | None = None
    planned_stop_price: Decimal | None = None
    planned_risk_per_share: Decimal | None = None
    planned_risk_amount: Decimal | None = None
    allowed_risk: Decimal | None = None
    suggested_shares: Decimal | None = None
    stop_distance_pct: Decimal | None = None
    risk_pct_equity_at_entry: Decimal | None = None
    equity_before_entry: Decimal | None = None
    r_multiple: Decimal | None = None
    r_pnl_basis: str | None = None
    fees_known: bool | None = None
    risk_source: str | None = SOURCE_UNKNOWN
    stop_source: str | None = SOURCE_UNKNOWN
    risk_quality_status: str | None = "MISSING_STOP"
    risk_notes: str | None = None
    manual_override: bool = False
    warnings: list[str] = field(default_factory=list)


class RiskService:
    def __init__(self, db: Session):
        self.db = db

    def get_or_create(self, trade: Trade) -> TradeRisk:
        row = self.db.query(TradeRisk).filter(TradeRisk.trade_id == trade.id).first()
        if row:
            return row
        row = TradeRisk(trade_id=trade.id, calculation_version=CALC_VERSION, manual_override=False)
        self.db.add(row)
        self.db.flush()
        return row

    def _append_audit(self, trade_id: int, field: str, old, new, source: str) -> None:
        old_s, new_s = _dec_str(old) if not isinstance(old, str) else old, _dec_str(new) if not isinstance(new, str) else new
        if old is True or old is False:
            old_s = str(old).lower()
        if new is True or new is False:
            new_s = str(new).lower()
        if old_s == new_s:
            return
        self.db.add(
            RiskAuditLog(
                trade_id=trade_id,
                field=field,
                old_value=old_s,
                new_value=new_s,
                source=source,
                created_at=_now(),
            )
        )

    def _write_cache_and_row(self, trade: Trade, row: TradeRisk, result: RiskComputationResult, audit_source: str | None) -> None:
        if audit_source:
            self._append_audit(trade.id, "initial_stop_price", row.initial_stop_price, result.initial_stop_price, audit_source)
            self._append_audit(trade.id, "actual_initial_risk_amount", row.actual_initial_risk_amount, result.actual_initial_risk_amount, audit_source)
            self._append_audit(trade.id, "r_multiple", row.r_multiple, result.r_multiple, audit_source)
            self._append_audit(trade.id, "risk_source", row.risk_source, result.risk_source, audit_source)
            self._append_audit(trade.id, "manual_override", row.manual_override, result.manual_override, audit_source)

        row.initial_stop_price = result.initial_stop_price
        row.actual_risk_per_share = result.actual_risk_per_share
        row.actual_initial_risk_amount = result.actual_initial_risk_amount
        row.explicit_initial_risk_amount = result.explicit_initial_risk_amount
        row.stop_derived_risk_amount = result.stop_derived_risk_amount
        row.planned_entry_price = result.planned_entry_price
        row.planned_stop_price = result.planned_stop_price
        row.planned_risk_per_share = result.planned_risk_per_share
        row.planned_risk_amount = result.planned_risk_amount
        row.allowed_risk = result.allowed_risk
        row.suggested_shares = result.suggested_shares
        row.stop_distance_pct = result.stop_distance_pct
        row.risk_pct_equity_at_entry = result.risk_pct_equity_at_entry
        row.equity_before_entry = result.equity_before_entry
        row.r_multiple = result.r_multiple
        row.r_pnl_basis = result.r_pnl_basis
        row.fees_known = result.fees_known
        row.risk_source = result.risk_source
        row.stop_source = result.stop_source
        row.risk_quality_status = result.risk_quality_status
        row.risk_notes = result.risk_notes
        row.manual_override = result.manual_override
        row.calculation_version = CALC_VERSION
        row.updated_at = _now()

        trade.initial_stop_price = result.initial_stop_price
        trade.initial_risk_per_share = result.actual_risk_per_share
        trade.initial_risk_amount = result.actual_initial_risk_amount
        trade.r_multiple = result.r_multiple
        trade.risk_source = result.risk_source
        trade.risk_notes = result.risk_notes
        trade.risk_updated_at = _now()

    def _confirmed_signal(self, trade: Trade) -> Signal | None:
        return confirmed_signal_for_trade(self.db, trade.id)

    def compute(self, trade: Trade, *, equity_before: Decimal | None = None) -> RiskComputationResult:
        row = self.db.query(TradeRisk).filter(TradeRisk.trade_id == trade.id).first()
        result = RiskComputationResult()
        signal = self._confirmed_signal(trade)

        if signal:
            result.planned_entry_price = signal.planned_entry_price
            result.planned_stop_price = signal.planned_stop_price
            result.allowed_risk = signal.allowed_risk
            result.suggested_shares = signal.suggested_shares
            prps, pramt = planned_risk_from_signal(signal)
            result.planned_risk_per_share = prps
            result.planned_risk_amount = pramt
        elif row:
            result.planned_entry_price = row.planned_entry_price
            result.planned_stop_price = row.planned_stop_price
            result.allowed_risk = row.allowed_risk
            result.suggested_shares = row.suggested_shares
            result.planned_risk_per_share = row.planned_risk_per_share
            result.planned_risk_amount = row.planned_risk_amount

        manual_override = bool(row.manual_override) if row else False
        explicit = row.explicit_initial_risk_amount if row else None
        manual_stop = row.initial_stop_price if row and manual_override else None
        imported_stop = None
        if row and row.stop_source == SOURCE_IMPORTED:
            imported_stop = row.initial_stop_price
        elif trade.risk_source == SOURCE_IMPORTED:
            imported_stop = trade.initial_stop_price

        stop = None
        stop_source = SOURCE_UNKNOWN
        risk_source = SOURCE_UNKNOWN

        if manual_override and explicit is not None and explicit > 0:
            result.explicit_initial_risk_amount = explicit
            stop = manual_stop or (row.initial_stop_price if row else trade.initial_stop_price)
            stop_source = SOURCE_MANUAL if manual_stop is not None else (row.stop_source if row else SOURCE_MANUAL)
            risk_source = SOURCE_MANUAL
        elif manual_override and (manual_stop is not None or (row and row.initial_stop_price is not None)):
            stop = manual_stop or row.initial_stop_price
            stop_source = SOURCE_MANUAL
            risk_source = SOURCE_MANUAL
        elif signal and signal.planned_stop_price is not None:
            stop = signal.planned_stop_price
            stop_source = SOURCE_PINE
            risk_source = SOURCE_PINE
        elif imported_stop is not None:
            stop = imported_stop
            stop_source = SOURCE_IMPORTED
            risk_source = SOURCE_IMPORTED
        else:
            stale_pine = (row and row.stop_source in (SOURCE_PINE, "PINE")) or (
                not row and trade.risk_source in (SOURCE_PINE, "PINE")
            )
            if stale_pine:
                stop = None
                stop_source = SOURCE_UNKNOWN
                risk_source = SOURCE_UNKNOWN
            elif row and row.initial_stop_price is not None:
                stop = row.initial_stop_price
                stop_source = row.stop_source or SOURCE_CALCULATED
                risk_source = row.risk_source or SOURCE_CALCULATED
            elif trade.initial_stop_price is not None:
                stop = trade.initial_stop_price
                stop_source = SOURCE_CALCULATED
                risk_source = SOURCE_CALCULATED

        result.initial_stop_price = stop
        result.stop_source = stop_source
        result.risk_source = risk_source
        result.manual_override = manual_override
        if row:
            result.risk_notes = row.risk_notes
            if explicit is not None:
                result.explicit_initial_risk_amount = explicit

        entry = trade.avg_entry_price
        qty = trade.quantity
        if entry is None:
            result.risk_quality_status = "MISSING_ENTRY"
            result.r_multiple = None
            return result
        if qty is None or qty <= 0:
            result.risk_quality_status = "MISSING_QUANTITY"
            result.r_multiple = None
            return result

        stop_derived = None
        rps = None
        if stop is not None:
            err = validate_stop_for_direction(trade.direction, entry, stop)
            if err:
                result.risk_quality_status = "INVALID_STOP"
                result.r_multiple = None
                result.actual_initial_risk_amount = None
                result.actual_risk_per_share = None
                result.warnings.append(err)
                result.equity_before_entry = equity_before
                return result
            rps = risk_per_share_from_stop(trade.direction, entry, stop)
            if rps <= 0:
                result.risk_quality_status = "INVALID_STOP"
                result.r_multiple = None
                return result
            # Multiply unrounded risk/share × quantity, then store money precision.
            # Pre-rounding rps to 4dp before qty would invent cents on scale-ins.
            stop_derived = quantize_price(rps * qty)
            result.stop_derived_risk_amount = stop_derived
            rps = rps.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
            if entry != 0:
                result.stop_distance_pct = (rps / entry) * Decimal("100")

        amount = None
        if result.explicit_initial_risk_amount is not None and result.explicit_initial_risk_amount > 0:
            amount = quantize_price(result.explicit_initial_risk_amount)
            risk_source = SOURCE_MANUAL
            result.risk_source = SOURCE_MANUAL
            if rps is None and qty > 0:
                rps = quantize_price(amount / qty)
        elif stop_derived is not None:
            amount = stop_derived

        result.actual_risk_per_share = rps
        result.actual_initial_risk_amount = amount

        if amount is None or amount <= 0:
            result.risk_quality_status = "MISSING_STOP"
            result.r_multiple = None
            result.equity_before_entry = equity_before
            return result

        r_mult, uses_gross = compute_r_multiple(trade, amount)
        result.r_multiple = quantize_r(r_mult) if r_mult is not None else None
        result.r_pnl_basis = "GROSS" if uses_gross else "NET"
        result.fees_known = trade.fees is not None
        if uses_gross:
            result.warnings.append("R calculated from gross P&L because fee data is unavailable.")

        result.risk_quality_status = "MANUAL_OVERRIDE" if manual_override else "OK"
        result.equity_before_entry = equity_before
        if amount is not None and equity_before is not None and equity_before > 0:
            result.risk_pct_equity_at_entry = (amount / equity_before) * Decimal("100")
        return result

    def recalculate_trade(self, trade: Trade, *, equity_before: Decimal | None = None, audit_source: str | None = None) -> RiskComputationResult:
        row = self.get_or_create(trade)
        if equity_before is None:
            equity_before = self._equity_before_entry(trade)
        result = self.compute(trade, equity_before=equity_before)
        self._write_cache_and_row(trade, row, result, audit_source)
        self.db.flush()
        return result

    def apply_manual(
        self,
        trade: Trade,
        *,
        initial_stop_price: Decimal | None,
        initial_risk_amount: Decimal | None,
        risk_notes: str | None = None,
    ) -> RiskComputationResult:
        if trade.status != "CLOSED":
            raise ValueError("Risk can only be set on closed trades")
        if initial_stop_price is None and initial_risk_amount is None:
            raise ValueError("initial_stop_price or initial_risk_amount required")
        if initial_stop_price is not None:
            err = validate_stop_for_direction(trade.direction, trade.avg_entry_price, initial_stop_price)
            if err:
                raise ValueError(err)
        row = self.get_or_create(trade)
        row.manual_override = True
        if initial_stop_price is not None:
            row.initial_stop_price = initial_stop_price
            row.stop_source = SOURCE_MANUAL
        if initial_risk_amount is not None:
            if initial_risk_amount <= 0:
                raise ValueError("Initial risk amount must be positive.")
            row.explicit_initial_risk_amount = initial_risk_amount
        if risk_notes is not None:
            row.risk_notes = risk_notes
        row.risk_source = SOURCE_MANUAL
        self.db.flush()
        return self.recalculate_trade(trade, audit_source="MANUAL")

    def recalculate_for_signal(self, signal_pk: int) -> None:
        links = (
            self.db.query(TradeSignalLink)
            .filter(TradeSignalLink.signal_id == signal_pk, TradeSignalLink.link_status == STATUS_CONFIRMED)
            .all()
        )
        if not links:
            return
        trades = self.db.query(Trade).filter(Trade.id.in_([l.trade_id for l in links])).all()
        eq_map = equity_before_entry_map(self.db, trades)
        for trade in trades:
            self.recalculate_trade(trade, equity_before=eq_map.get(trade.id))

    def recalculate_many(self, trades: Iterable[Trade]) -> None:
        trade_list = list(trades)
        eq_map = equity_before_entry_map(self.db, trade_list)
        for trade in trade_list:
            self.recalculate_trade(trade, equity_before=eq_map.get(trade.id))

    def _equity_before_entry(self, trade: Trade) -> Decimal | None:
        return equity_before_entry_map(self.db, [trade]).get(trade.id)


def equity_before_entry_map(db: Session, trades: list[Trade]) -> dict[int, Decimal | None]:
    """Batch no-lookahead equity at entry. Strict exit_time < entry_time. Account isolation."""
    if not trades:
        return {}
    account_ids = {t.account_id for t in trades}
    accounts = {a.id: a for a in db.query(Account).filter(Account.id.in_(account_ids)).all()}
    closed = (
        db.query(Trade)
        .filter(
            Trade.status == "CLOSED",
            Trade.account_id.in_(account_ids),
            Trade.exit_time_utc.isnot(None),
        )
        .all()
    )
    by_acct: dict[int, list[Trade]] = {aid: [] for aid in account_ids}
    for t in closed:
        by_acct.setdefault(t.account_id, []).append(t)
    for aid in by_acct:
        by_acct[aid].sort(key=lambda t: (_ensure_utc(t.exit_time_utc), t.id))

    prefix: dict[int, list[tuple[datetime, Decimal]]] = {}
    prefix_keys: dict[int, list[datetime]] = {}
    for aid, rows in by_acct.items():
        running = Decimal("0")
        seq = []
        for t in rows:
            running += effective_realized_pnl(t).pnl
            seq.append((_ensure_utc(t.exit_time_utc), running))
        prefix[aid] = seq
        prefix_keys[aid] = [item[0] for item in seq]

    out: dict[int, Decimal | None] = {}
    for trade in trades:
        acct = accounts.get(trade.account_id)
        if acct is None or acct.starting_equity is None:
            out[trade.id] = None
            continue
        starting = acct.starting_equity
        entry = _ensure_utc(trade.entry_time_utc)
        keys = prefix_keys.get(trade.account_id, [])
        idx = bisect.bisect_left(keys, entry)
        prior = prefix[trade.account_id][idx - 1][1] if idx else Decimal("0")
        out[trade.id] = starting + prior
    return out


def missing_r_breakdown(db: Session, trades: list[Trade]) -> dict:
    """Coverage reasons for closed trades missing R. Totals reconcile."""
    closed = [t for t in trades if t.status == "CLOSED"]
    ids = [t.id for t in closed]
    risk_rows = {
        r.trade_id: r for r in db.query(TradeRisk).filter(TradeRisk.trade_id.in_(ids)).all()
    } if ids else {}
    confirmed = set()
    if ids:
        confirmed = {
            l.trade_id
            for l in db.query(TradeSignalLink)
            .filter(TradeSignalLink.trade_id.in_(ids), TradeSignalLink.link_status == STATUS_CONFIRMED)
            .all()
        }
    qualified = 0
    reasons: dict[str, int] = {}
    no_signal_context = 0
    for t in closed:
        row = risk_rows.get(t.id)
        has_sig = t.id in confirmed
        if row and row.r_multiple is not None and row.actual_initial_risk_amount and row.actual_initial_risk_amount > 0:
            qualified += 1
            continue
        reason = classify_missing_reason(t, row, has_sig)
        reasons[reason or "OTHER"] = reasons.get(reason or "OTHER", 0) + 1
        if not has_sig:
            no_signal_context += 1
    n = len(closed)
    cov = (Decimal(qualified) / Decimal(n) * Decimal("100")) if n else None
    from app.utils.analytics import decimal_str

    return {
        "closed_trades": n,
        "r_qualified": qualified,
        "r_coverage_pct": decimal_str(cov),
        "missing": n - qualified,
        "reasons": reasons,
        "no_signal_available_context": no_signal_context,
        "risk_source_mix": _source_mix(list(risk_rows.values())),
    }


def _source_mix(rows: list[TradeRisk]) -> dict[str, int]:
    mix: dict[str, int] = {}
    for r in rows:
        src = r.risk_source or SOURCE_UNKNOWN
        mix[src] = mix.get(src, 0) + 1
    return mix
