"""Join enriched market features into report annotation."""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy.orm import Session, aliased

from app.db.models.market_data import InstrumentDayFeature, TradeMarketFeature
from app.services.reports.config import bucket_key_for_value
from app.services.reports.features import AnnotatedTrade

VOLUME_FEATURES = frozenset({"day_volume_bucket", "rvol50_bucket", "prior_rvol_bucket"})


def apply_market_features(
    db: Session,
    annotated: list[AnnotatedTrade],
    include_partial_feed: bool = False,
) -> None:
    if not annotated:
        return
    trade_ids = [at.trade.id for at in annotated]
    Inst = aliased(InstrumentDayFeature)
    Bench = aliased(InstrumentDayFeature)
    rows = (
        db.query(TradeMarketFeature, Inst, Bench)
        .outerjoin(Inst, TradeMarketFeature.instrument_feature_id == Inst.id)
        .outerjoin(Bench, TradeMarketFeature.benchmark_feature_id == Bench.id)
        .filter(TradeMarketFeature.trade_id.in_(trade_ids))
        .all()
    )
    by_trade = {tmf.trade_id: (tmf, inst, bench) for tmf, inst, bench in rows}

    for at in annotated:
        packed = by_trade.get(at.trade.id)
        if not packed:
            at.features["_market_enriched"] = "false"
            continue
        tmf, inst, bench = packed
        at.features["_market_enriched"] = "true"
        if inst:
            _apply_instrument_features(at, inst, tmf, include_partial_feed)
        if bench:
            _apply_benchmark_features(at, bench)


def _flags(inst: InstrumentDayFeature) -> list[str]:
    if not inst.quality_flags:
        return []
    try:
        parsed = json.loads(inst.quality_flags)
        return parsed if isinstance(parsed, list) else []
    except json.JSONDecodeError:
        return []


def _is_partial(inst: InstrumentDayFeature) -> bool:
    if inst.quality_status == "PARTIAL_FEED":
        return True
    return "PARTIAL_FEED" in _flags(inst)


def _apply_instrument_features(
    at: AnnotatedTrade,
    inst: InstrumentDayFeature,
    tmf: TradeMarketFeature,
    include_partial_feed: bool,
) -> None:
    f = at.features
    flags = _flags(inst)
    f["_inst_quality"] = inst.quality_status
    f["_quality_flags"] = ",".join(flags)
    f["_completeness"] = inst.completeness_status
    partial = _is_partial(inst)
    allow_volume = include_partial_feed or not partial

    if inst.opening_gap_pct is not None:
        f["opening_gap_bucket"] = bucket_key_for_value("gap", inst.opening_gap_pct)
    else:
        f["_skip_opening_gap_bucket"] = inst.quality_status or "MISSING_DATA"

    if inst.day_volume is not None and allow_volume:
        f["day_volume_bucket"] = bucket_key_for_value("volume", Decimal(inst.day_volume))
    elif inst.day_volume is not None and partial:
        f["_skip_day_volume_bucket"] = "PARTIAL_FEED"

    if inst.rvol50_multiple is not None and allow_volume:
        f["rvol50_bucket"] = bucket_key_for_value("rvol", inst.rvol50_multiple)
    elif inst.rvol50_multiple is not None and partial:
        f["_skip_rvol50_bucket"] = "PARTIAL_FEED"
    elif inst.rvol50_multiple is None:
        f["_skip_rvol50_bucket"] = (
            "PENDING_EOD" if inst.completeness_status == "PRE_ENTRY_ONLY" else (inst.quality_status or "INSUFFICIENT_HISTORY")
        )

    if inst.prior_day_rvol50_multiple is not None and allow_volume:
        f["prior_rvol_bucket"] = bucket_key_for_value("prior_rvol", inst.prior_day_rvol50_multiple)
    elif inst.prior_day_rvol50_multiple is not None and partial:
        f["_skip_prior_rvol_bucket"] = "PARTIAL_FEED"
    elif inst.prior_day_rvol50_multiple is None:
        f["_skip_prior_rvol_bucket"] = inst.quality_status or "INSUFFICIENT_HISTORY"

    if inst.daily_movement_pct is not None:
        f["movement_bucket"] = bucket_key_for_value("movement", inst.daily_movement_pct)
    elif inst.completeness_status == "PRE_ENTRY_ONLY":
        f["_skip_movement_bucket"] = "PENDING_EOD"

    if inst.atr14_prior is not None:
        f["atr14_bucket"] = bucket_key_for_value("atr", inst.atr14_prior)
    if tmf.entry_vs_atr_pct is not None:
        f["entry_atr_bucket"] = bucket_key_for_value("entry_atr", tmf.entry_vs_atr_pct)
    if inst.relative_volatility_pct is not None:
        f["tr_atr_bucket"] = bucket_key_for_value("tr_atr", inst.relative_volatility_pct)
    elif inst.completeness_status == "PRE_ENTRY_ONLY":
        f["_skip_tr_atr_bucket"] = "PENDING_EOD"
    if inst.day_type:
        f["day_type"] = inst.day_type.lower()
    elif inst.completeness_status == "PRE_ENTRY_ONLY":
        f["_skip_day_type"] = "PENDING_EOD"
    if tmf.entry_vs_sma20_pct is not None:
        f["entry_sma20_bucket"] = bucket_key_for_value("sma_dist", tmf.entry_vs_sma20_pct)
    if tmf.entry_vs_sma50_pct is not None:
        f["entry_sma50_bucket"] = bucket_key_for_value("sma_dist", tmf.entry_vs_sma50_pct)


def _apply_benchmark_features(at: AnnotatedTrade, bench: InstrumentDayFeature) -> None:
    f = at.features
    if bench.opening_gap_pct is not None:
        f["market_gap_bucket"] = bucket_key_for_value("market_gap", bench.opening_gap_pct)
    if bench.daily_movement_pct is not None:
        f["market_movement_bucket"] = bucket_key_for_value("market_movement", bench.daily_movement_pct)
    elif bench.completeness_status == "PRE_ENTRY_ONLY":
        f["_skip_market_movement_bucket"] = "PENDING_EOD"
    if bench.day_type:
        f["market_day_type"] = bench.day_type.lower()
    elif bench.completeness_status == "PRE_ENTRY_ONLY":
        f["_skip_market_day_type"] = "PENDING_EOD"
