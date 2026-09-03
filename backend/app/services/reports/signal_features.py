"""Join CONFIRMED (default) Pine signals onto annotated trades. Distinct from Step 4 gap/RVOL."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.signal import Signal, TradeSignalLink
from app.services.reports.config import bucket_key_for_value
from app.services.reports.features import AnnotatedTrade
from app.services.signals.matcher import STATUS_CONFIRMED, STATUS_SUGGESTED


def apply_signal_features(
    db: Session,
    annotated: list[AnnotatedTrade],
    *,
    include_suggested: bool = False,
    pine_scope: str = "REALTIME",
) -> None:
    if not annotated:
        return
    trade_ids = [at.trade.id for at in annotated]
    statuses = [STATUS_CONFIRMED]
    if include_suggested:
        statuses.append(STATUS_SUGGESTED)
    links = (
        db.query(TradeSignalLink)
        .filter(TradeSignalLink.trade_id.in_(trade_ids), TradeSignalLink.link_status.in_(statuses))
        .all()
    )
    if not links:
        for at in annotated:
            at.features["_signal_linked"] = "false"
            at.features["_skip_strategy"] = "MISSING_SIGNAL"
        return

    prefer_confirmed: dict[int, TradeSignalLink] = {}
    for link in links:
        prev = prefer_confirmed.get(link.trade_id)
        if prev is None or (prev.link_status != STATUS_CONFIRMED and link.link_status == STATUS_CONFIRMED):
            prefer_confirmed[link.trade_id] = link

    sig_ids = {l.signal_id for l in prefer_confirmed.values()}
    signals = {s.id: s for s in db.query(Signal).filter(Signal.id.in_(sig_ids)).all()}

    for at in annotated:
        link = prefer_confirmed.get(at.trade.id)
        if not link:
            at.features["_signal_linked"] = "false"
            at.features["_skip_strategy"] = "MISSING_SIGNAL"
            continue
        sig = signals.get(link.signal_id)
        if not sig:
            at.features["_signal_linked"] = "false"
            at.features["_skip_strategy"] = "MISSING_SIGNAL"
            continue
        if pine_scope and pine_scope != "ALL" and sig.signal_origin != pine_scope:
            at.features["_signal_linked"] = "false"
            at.features["_signal_origin_filtered"] = sig.signal_origin
            at.features["_skip_strategy"] = "ORIGIN_FILTER"
            continue
        _apply_signal(at, sig, link.link_status)


def _bool_bucket(val: bool | None, true_key: str, false_key: str) -> str | None:
    if val is True:
        return true_key
    if val is False:
        return false_key
    return None


def _apply_signal(at: AnnotatedTrade, sig: Signal, link_status: str) -> None:
    f = at.features
    f["_signal_linked"] = "true"
    f["_signal_link_status"] = link_status
    f["_signal_origin"] = sig.signal_origin
    f["strategy_key"] = sig.strategy_key
    f["strategy_version"] = sig.strategy_version
    f["strategy_version_normalized"] = sig.strategy_version_normalized
    f["signal_origin"] = sig.signal_origin
    if sig.setup_quality:
        q = sig.setup_quality.strip()
        f["setup_quality"] = q if q in ("A+", "A", "Other") else q
    else:
        f["_skip_setup_quality"] = "MISSING_SIGNAL"
    if sig.signal_gap_pct is not None:
        f["signal_gap_bucket"] = bucket_key_for_value("signal_gap", sig.signal_gap_pct)
    else:
        f["_skip_signal_gap_bucket"] = "MISSING_SIGNAL"
    if sig.signal_rvol is not None:
        f["signal_rvol_bucket"] = bucket_key_for_value("signal_rvol", sig.signal_rvol)
    else:
        f["_skip_signal_rvol_bucket"] = "MISSING_SIGNAL"
    if sig.impulse_pct is not None:
        f["impulse_bucket"] = bucket_key_for_value("impulse", sig.impulse_pct)
    else:
        f["_skip_impulse_bucket"] = "MISSING_SIGNAL"
    if sig.retracement_pct is not None:
        f["retracement_bucket"] = bucket_key_for_value("retracement", sig.retracement_pct)
    else:
        f["_skip_retracement_bucket"] = "MISSING_SIGNAL"
    if sig.context_5m:
        ctx = sig.context_5m.strip().upper()
        if ctx in ("BULLISH", "BEARISH", "NEUTRAL", "NOT_BULLISH"):
            f["context_5m"] = "not_bullish" if ctx == "NOT_BULLISH" else ctx.lower()
        else:
            f["context_5m"] = ctx.lower()
    else:
        f["_skip_context_5m"] = "MISSING_SIGNAL"
    vwap = _bool_bucket(sig.above_vwap, "above", "not_above")
    if vwap:
        f["above_vwap"] = vwap
    else:
        f["_skip_above_vwap"] = "MISSING_SIGNAL"
    ema = _bool_bucket(sig.above_ema9, "above", "not_above")
    if ema:
        f["above_ema9"] = ema
    else:
        f["_skip_above_ema9"] = "MISSING_SIGNAL"
    vol = _bool_bucket(sig.volume_confirmed, "confirmed", "not_confirmed")
    if vol:
        f["volume_confirmed"] = vol
    else:
        f["_skip_volume_confirmed"] = "MISSING_SIGNAL"
    if sig.suggested_shares is not None:
        f["suggested_shares_bucket"] = bucket_key_for_value("quantity", Decimal(sig.suggested_shares))
    if sig.planned_position_value is not None:
        f["planned_position_value_bucket"] = bucket_key_for_value("position_value", sig.planned_position_value)
    if sig.planned_exposure_pct is not None:
        f["planned_exposure_bucket"] = bucket_key_for_value("planned_exposure", sig.planned_exposure_pct)
    if sig.mechanical_exit_reason:
        f["mechanical_exit_reason"] = sig.mechanical_exit_reason
    else:
        f["_skip_mechanical_exit_reason"] = "MISSING_EXIT"
