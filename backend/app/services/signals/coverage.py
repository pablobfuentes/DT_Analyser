"""Signal coverage statistics (NY calendar dates)."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.signal import Signal, TradeSignalLink
from app.db.models.trade import Trade
from app.services.signals.matcher import STATUS_AMBIGUOUS, STATUS_CONFIRMED, STATUS_SUGGESTED
from app.utils.analytics import decimal_str, ny_date_from_utc


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def coverage_summary(db: Session, trades: list[Trade] | None = None) -> dict:
    closed = trades if trades is not None else db.query(Trade).filter(Trade.status == "CLOSED").all()
    closed_ids = {t.id for t in closed}
    signals = db.query(Signal).all()
    links = db.query(TradeSignalLink).all()

    confirmed = [l for l in links if l.link_status == STATUS_CONFIRMED]
    suggested = [l for l in links if l.link_status == STATUS_SUGGESTED]
    confirmed_trade_ids = {l.trade_id for l in confirmed if l.trade_id in closed_ids or trades is None}
    if trades is not None:
        confirmed_trade_ids = {l.trade_id for l in confirmed if l.trade_id in closed_ids}

    linked_trades = [t for t in closed if t.id in confirmed_trade_ids]
    manual_linked = [t for t in linked_trades if t.source_type == "TRADINGVIEW_MANUAL"]
    auto_linked = [t for t in linked_trades if t.source_type == "TRADINGVIEW_AUTO"]

    signal_ids_confirmed = {l.signal_id for l in confirmed}
    realtime_linked_trades = 0
    sig_by_pk = {s.id: s for s in signals}
    for tid in confirmed_trade_ids:
        # find signal origin
        for l in confirmed:
            if l.trade_id == tid:
                sig = sig_by_pk.get(l.signal_id)
                if sig and sig.signal_origin == "REALTIME":
                    realtime_linked_trades += 1
                break

    unlinked_signals = [s for s in signals if s.id not in signal_ids_confirmed]
    ambiguous = [s for s in signals if s.match_status == STATUS_AMBIGUOUS]
    n_closed = len(closed)
    cov = (Decimal(len(linked_trades)) / Decimal(n_closed) * Decimal("100")) if n_closed else None
    rt_cov = (Decimal(realtime_linked_trades) / Decimal(n_closed) * Decimal("100")) if n_closed else None

    return {
        "closed_trades": n_closed,
        "pine_signals": len(signals),
        "signal_events": None,
        "trades_with_signal": len(linked_trades),
        "manual_with_signal": len(manual_linked),
        "auto_with_signal": len(auto_linked),
        "unlinked_signals": len(unlinked_signals),
        "suggested_links": len(suggested),
        "confirmed_links": len(confirmed) if trades is None else len([l for l in confirmed if l.trade_id in closed_ids]),
        "ambiguous_signals": len(ambiguous),
        "strategy_coverage_pct": decimal_str(cov),
        "realtime_coverage_pct": decimal_str(rt_cov),
        "realtime_linked_trades": realtime_linked_trades,
    }


def coverage_by_date(db: Session) -> list[dict]:
    trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
    signals = db.query(Signal).all()
    confirmed = (
        db.query(TradeSignalLink)
        .filter(TradeSignalLink.link_status == STATUS_CONFIRMED)
        .all()
    )
    linked_trade_ids = {l.trade_id for l in confirmed}

    by_day: dict[str, dict] = defaultdict(lambda: {"trades": 0, "signals": 0, "linked": 0})
    for t in trades:
        if not t.exit_time_utc:
            continue
        day = ny_date_from_utc(_ensure_utc(t.exit_time_utc)).isoformat()
        by_day[day]["trades"] += 1
        if t.id in linked_trade_ids:
            by_day[day]["linked"] += 1
    for s in signals:
        ref = s.entry_signal_time_utc or s.armed_time_utc or s.exit_signal_time_utc
        if not ref:
            continue
        day = ny_date_from_utc(_ensure_utc(ref)).isoformat()
        by_day[day]["signals"] += 1

    rows = []
    for day in sorted(by_day):
        rec = by_day[day]
        cov = None
        if rec["trades"]:
            cov = Decimal(rec["linked"]) / Decimal(rec["trades"]) * Decimal("100")
        rows.append(
            {
                "date": day,
                "trades": rec["trades"],
                "signals": rec["signals"],
                "linked": rec["linked"],
                "coverage_pct": decimal_str(cov),
            }
        )
    return rows
