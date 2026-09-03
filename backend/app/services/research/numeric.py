"""Attach numeric research values to annotated trades (batched)."""

from __future__ import annotations

from datetime import time
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.market_data import InstrumentDayFeature, TradeExcursion, TradeMarketFeature
from app.db.models.risk import TradeRisk
from app.db.models.signal import Signal, TradeSignalLink
from app.services.reports.features import AnnotatedTrade
from app.services.signals.matcher import STATUS_CONFIRMED
from app.utils.analytics import analytics_tz, ny_date_from_utc


def _minutes_since_open(trade) -> Decimal | None:
    if trade.entry_time_utc is None:
        return None
    local = trade.entry_time_utc.astimezone(analytics_tz()) if trade.entry_time_utc.tzinfo else trade.entry_time_utc
    open_t = local.replace(hour=9, minute=30, second=0, microsecond=0)
    return Decimal((local - open_t).total_seconds()) / Decimal("60")


def attach_numeric(db: Session, annotated: list[AnnotatedTrade]) -> None:
    if not annotated:
        return
    ids = [at.trade.id for at in annotated]
    risks = {r.trade_id: r for r in db.query(TradeRisk).filter(TradeRisk.trade_id.in_(ids)).all()}
    exc = {e.trade_id: e for e in db.query(TradeExcursion).filter(TradeExcursion.trade_id.in_(ids)).all()}
    links = (
        db.query(TradeSignalLink)
        .filter(TradeSignalLink.trade_id.in_(ids), TradeSignalLink.link_status == STATUS_CONFIRMED)
        .all()
    )
    sigs = {}
    if links:
        sigs = {s.id: s for s in db.query(Signal).filter(Signal.id.in_({l.signal_id for l in links})).all()}
    link_by_trade = {}
    for l in links:
        link_by_trade.setdefault(l.trade_id, l)

    tmf = {t.trade_id: t for t in db.query(TradeMarketFeature).filter(TradeMarketFeature.trade_id.in_(ids)).all()}
    inst_ids = {row.instrument_feature_id for row in tmf.values() if getattr(row, "instrument_feature_id", None)}
    inst = {}
    if inst_ids:
        inst = {i.id: i for i in db.query(InstrumentDayFeature).filter(InstrumentDayFeature.id.in_(inst_ids)).all()}

    for at in annotated:
        t = at.trade
        r = risks.get(t.id)
        e = exc.get(t.id)
        sig = None
        link = link_by_trade.get(t.id)
        if link:
            sig = sigs.get(link.signal_id)
        feat = None
        tm = tmf.get(t.id)
        if tm is not None and getattr(tm, "instrument_feature_id", None):
            feat = inst.get(tm.instrument_feature_id)

        nums: dict[str, Decimal | None] = {
            "actual_r": t.r_multiple if t.r_multiple is not None else (r.r_multiple if r else None),
            "net_pnl": at.pnl,
            "hold_seconds": Decimal(t.holding_seconds) if t.holding_seconds is not None else None,
            "minutes_since_open": _minutes_since_open(t),
            "entry_price": t.avg_entry_price,
            "quantity": t.quantity,
            "position_value": (t.avg_entry_price * t.quantity) if t.avg_entry_price is not None and t.quantity is not None else None,
            "initial_risk_amount": (r.actual_initial_risk_amount if r else t.initial_risk_amount),
            "risk_pct_equity": r.risk_pct_equity_at_entry if r else None,
            "stop_distance_pct": r.stop_distance_pct if r else None,
            "signal_rvol": sig.signal_rvol if sig else None,
            "signal_gap_pct": sig.signal_gap_pct if sig else None,
            "impulse_pct": sig.impulse_pct if sig else None,
            "retracement_pct": sig.retracement_pct if sig else None,
            "opening_gap_pct": feat.opening_gap_pct if feat is not None else None,
            "prior_rvol50": feat.prior_day_rvol50_multiple if feat is not None else None,
            "rvol50_eod": feat.rvol50_multiple if feat is not None else None,
            "atr14_prior": feat.atr14_prior if feat is not None else None,
            "mfe_r": e.mfe_r if e else None,
            "mae_r": e.mae_r if e else None,
            "exit_efficiency_pct": e.exit_efficiency_pct if e else None,
            "r_left_on_table": e.r_left_on_table if e else None,
            "time_to_mfe_seconds": Decimal(e.time_to_mfe_seconds) if e and e.time_to_mfe_seconds is not None else None,
            "post_exit_favorable_15m_r": e.post_exit_favorable_15m_r if e else None,
        }
        at.features["_numeric"] = {k: (str(v) if v is not None else None) for k, v in nums.items()}  # type: ignore
        setattr(at, "numeric", nums)
        setattr(at, "signal", sig)
        setattr(at, "excursion", e)
        ny = ny_date_from_utc(t.exit_time_utc or t.entry_time_utc)
        setattr(at, "ny_date", ny)
