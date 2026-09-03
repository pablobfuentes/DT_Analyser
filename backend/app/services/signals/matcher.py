"""Trade ↔ Signal matching. Never pick among ambiguous candidates. Never wrong ticker/direction."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.signal import Signal, TradeSignalLink
from app.db.models.trade import Trade
from app.utils.analytics import ny_date_from_utc


MATCH_EXPLICIT = "EXPLICIT_ID"
MATCH_AUTO_EXACT = "AUTO_EXACT"
MATCH_AUTO_TIME = "AUTO_TIME_MATCH"
MATCH_MANUAL_TIME = "MANUAL_TIME_MATCH"
MATCH_MANUAL_REVIEW = "MANUAL_REVIEW"
MATCH_LEGACY = "LEGACY"

STATUS_CONFIRMED = "CONFIRMED"
STATUS_SUGGESTED = "SUGGESTED"
STATUS_REJECTED = "REJECTED"
STATUS_AMBIGUOUS = "AMBIGUOUS"


def _ensure_utc(dt):
    from datetime import timezone

    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _delta_seconds(trade_entry, signal_entry) -> int | None:
    if trade_entry is None or signal_entry is None:
        return None
    return int((_ensure_utc(trade_entry) - _ensure_utc(signal_entry)).total_seconds())


def _upsert_link(
    db: Session,
    trade: Trade,
    signal: Signal,
    match_type: str,
    confidence: Decimal,
    status: str,
    time_delta: int | None,
) -> TradeSignalLink:
    existing = (
        db.query(TradeSignalLink)
        .filter(TradeSignalLink.trade_id == trade.id, TradeSignalLink.signal_id == signal.id)
        .first()
    )
    if existing:
        if existing.link_status == STATUS_REJECTED and status != MATCH_MANUAL_REVIEW:
            return existing
        if existing.link_status == STATUS_CONFIRMED and status != STATUS_REJECTED:
            existing.time_delta_seconds = time_delta if time_delta is not None else existing.time_delta_seconds
            return existing
        existing.match_type = match_type
        existing.confidence = confidence
        existing.link_status = status
        existing.time_delta_seconds = time_delta
        return existing
    link = TradeSignalLink(
        trade_id=trade.id,
        signal_id=signal.id,
        match_type=match_type,
        confidence=confidence,
        time_delta_seconds=time_delta,
        link_status=status,
    )
    db.add(link)
    return link


def refresh_signal_match_status(db: Session, signal: Signal) -> None:
    links = db.query(TradeSignalLink).filter(TradeSignalLink.signal_id == signal.id).all()
    confirmed = [l for l in links if l.link_status == STATUS_CONFIRMED]
    suggested = [l for l in links if l.link_status == STATUS_SUGGESTED]
    if confirmed:
        signal.match_status = STATUS_CONFIRMED
    elif signal.match_status == STATUS_AMBIGUOUS and not suggested:
        signal.match_status = STATUS_AMBIGUOUS
    elif suggested:
        signal.match_status = STATUS_SUGGESTED
    elif signal.match_status != STATUS_AMBIGUOUS:
        signal.match_status = "UNLINKED"


def _rejected_pairs(db: Session, signal_id: int) -> set[int]:
    rows = (
        db.query(TradeSignalLink.trade_id)
        .filter(TradeSignalLink.signal_id == signal_id, TradeSignalLink.link_status == STATUS_REJECTED)
        .all()
    )
    return {r[0] for r in rows}


def _trade_has_confirmed_signal(db: Session, trade_id: int) -> bool:
    return (
        db.query(TradeSignalLink)
        .filter(TradeSignalLink.trade_id == trade_id, TradeSignalLink.link_status == STATUS_CONFIRMED)
        .first()
        is not None
    )


def _manual_already_linked(db: Session, signal_id: int) -> bool:
    links = (
        db.query(TradeSignalLink, Trade)
        .join(Trade, Trade.id == TradeSignalLink.trade_id)
        .filter(
            TradeSignalLink.signal_id == signal_id,
            TradeSignalLink.link_status.in_((STATUS_CONFIRMED, STATUS_SUGGESTED)),
            Trade.source_type == "TRADINGVIEW_MANUAL",
        )
        .all()
    )
    return bool(links)


def _prefer_realtime(candidates: list[Trade]) -> list[Trade]:
    # Trades don't have origin; preference is applied on signal side when matching a trade to signals.
    return candidates


def candidates_for_signal(db: Session, signal: Signal) -> list[dict]:
    """Return candidate trades (not including REJECTED) for UI review."""
    if not signal.ticker or not signal.direction:
        return []
    q = db.query(Trade).filter(
        Trade.ticker == signal.ticker,
        Trade.direction == signal.direction,
        Trade.status == "CLOSED",
    )
    rejected = _rejected_pairs(db, signal.id)
    ref = signal.entry_signal_time_utc or signal.armed_time_utc
    out = []
    for trade in q.all():
        if trade.id in rejected:
            continue
        delta = _delta_seconds(trade.entry_time_utc, ref)
        out.append(
            {
                "trade_id": trade.id,
                "ticker": trade.ticker,
                "direction": trade.direction,
                "source_type": trade.source_type,
                "entry_time_utc": trade.entry_time_utc.isoformat() if trade.entry_time_utc else None,
                "time_delta_seconds": delta,
            }
        )
    out.sort(key=lambda r: abs(r["time_delta_seconds"] or 10**12))
    return out


def match_one_signal(db: Session, signal: Signal) -> None:
    if signal.legacy:
        # Conservative: never auto-confirm synthetic IDs.
        return

    rejected = _rejected_pairs(db, signal.id)
    ref = signal.entry_signal_time_utc or signal.armed_time_utc
    if ref is None:
        return

    trades = (
        db.query(Trade)
        .filter(
            Trade.ticker == signal.ticker,
            Trade.direction == signal.direction,
            Trade.status == "CLOSED",
        )
        .all()
    )
    trades = [t for t in trades if t.id not in rejected]

    auto_window = timedelta(seconds=settings.signal_auto_match_seconds)
    manual_before = timedelta(seconds=settings.signal_manual_match_before_seconds)
    manual_after = timedelta(seconds=settings.signal_manual_match_after_seconds)
    prefer_rt = settings.signal_prefer_realtime

    auto_candidates: list[Trade] = []
    manual_candidates: list[Trade] = []
    sig_day = ny_date_from_utc(ref)

    for trade in trades:
        entry = _ensure_utc(trade.entry_time_utc)
        ref_u = _ensure_utc(ref)
        delta = entry - ref_u
        if trade.source_type == "TRADINGVIEW_AUTO":
            if abs(delta) <= auto_window:
                auto_candidates.append(trade)
        elif trade.source_type == "TRADINGVIEW_MANUAL":
            if ny_date_from_utc(entry) == sig_day and -manual_before <= delta <= manual_after:
                manual_candidates.append(trade)

    if prefer_rt and signal.signal_origin != "REALTIME":
        # Still match historical, but AUTO realtime signals are preferred when multiple signals compete.
        pass

    if auto_candidates:
        if len(auto_candidates) == 1:
            t = auto_candidates[0]
            tight = abs(_delta_seconds(t.entry_time_utc, ref) or 999) <= 5
            _upsert_link(
                db,
                t,
                signal,
                MATCH_AUTO_EXACT if tight else MATCH_AUTO_TIME,
                Decimal("0.98") if tight else Decimal("0.90"),
                STATUS_CONFIRMED,
                _delta_seconds(t.entry_time_utc, ref),
            )
        else:
            signal.match_status = STATUS_AMBIGUOUS
            db.flush()
            return

    # Step 6 MANUAL-vs-AUTO pairing is skipped: do not auto-suggest MANUAL
    # onto a signal that already has a CONFIRMED (typically AUTO) link.
    already_confirmed = (
        db.query(TradeSignalLink)
        .filter(TradeSignalLink.signal_id == signal.id, TradeSignalLink.link_status == STATUS_CONFIRMED)
        .first()
    )
    if already_confirmed:
        refresh_signal_match_status(db, signal)
        db.flush()
        return

    if manual_candidates:
        if _manual_already_linked(db, signal.id):
            if len(manual_candidates) > 0:
                # Do not auto-link a second MANUAL trade.
                pass
        elif len(manual_candidates) == 1:
            t = manual_candidates[0]
            _upsert_link(
                db,
                t,
                signal,
                MATCH_MANUAL_TIME,
                Decimal("0.75"),
                STATUS_SUGGESTED,
                _delta_seconds(t.entry_time_utc, ref),
            )
        elif len(manual_candidates) > 1:
            signal.match_status = STATUS_AMBIGUOUS

    refresh_signal_match_status(db, signal)
    db.flush()


def match_signals_batch(db: Session, signals: list[Signal]) -> None:
    for sig in signals:
        match_one_signal(db, sig)


def confirm_link(db: Session, signal: Signal, trade: Trade, match_type: str = MATCH_MANUAL_REVIEW) -> TradeSignalLink:
    if trade.ticker != signal.ticker or trade.direction != signal.direction:
        raise ValueError("Cannot link a trade with a different ticker or direction than the signal.")
    if trade.source_type == "TRADINGVIEW_MANUAL" and _manual_already_linked(db, signal.id):
        existing = (
            db.query(TradeSignalLink)
            .join(Trade, Trade.id == TradeSignalLink.trade_id)
            .filter(
                TradeSignalLink.signal_id == signal.id,
                TradeSignalLink.link_status == STATUS_CONFIRMED,
                Trade.source_type == "TRADINGVIEW_MANUAL",
            )
            .first()
        )
        if existing and existing.trade_id != trade.id:
            raise ValueError("A MANUAL trade is already linked to this signal. Unlink it first for auditability.")
    link = _upsert_link(
        db,
        trade,
        signal,
        match_type,
        Decimal("1.0"),
        STATUS_CONFIRMED,
        _delta_seconds(trade.entry_time_utc, signal.entry_signal_time_utc or signal.armed_time_utc),
    )
    refresh_signal_match_status(db, signal)
    db.flush()
    from app.services.risk.service import RiskService

    RiskService(db).recalculate_trade(trade)
    return link


def reject_link(db: Session, signal: Signal, trade: Trade) -> TradeSignalLink:
    link = _upsert_link(db, trade, signal, MATCH_MANUAL_REVIEW, Decimal("0"), STATUS_REJECTED, None)
    refresh_signal_match_status(db, signal)
    db.flush()
    from app.services.risk.service import RiskService

    RiskService(db).recalculate_trade(trade)
    return link


def unlink(db: Session, signal: Signal, trade: Trade) -> None:
    link = (
        db.query(TradeSignalLink)
        .filter(TradeSignalLink.trade_id == trade.id, TradeSignalLink.signal_id == signal.id)
        .first()
    )
    if link:
        db.delete(link)
        db.flush()
    refresh_signal_match_status(db, signal)
    from app.services.risk.service import RiskService

    RiskService(db).recalculate_trade(trade)


def confirmed_signal_for_trade(db: Session, trade_id: int) -> Signal | None:
    row = (
        db.query(Signal)
        .join(TradeSignalLink, TradeSignalLink.signal_id == Signal.id)
        .filter(TradeSignalLink.trade_id == trade_id, TradeSignalLink.link_status == STATUS_CONFIRMED)
        .first()
    )
    return row
