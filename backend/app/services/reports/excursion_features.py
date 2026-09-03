"""Join trade excursions into report features."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.market_data import TradeExcursion
from app.services.reports.config import (
    EXIT_EFFICIENCY_BUCKETS,
    MFE_R_BUCKETS,
    MAE_R_BUCKETS,
    MFE_TO_EXIT_BUCKETS,
    PEAK_GIVEBACK_BUCKETS,
    R_LEFT_BUCKETS,
    TIME_TO_MFE_BUCKETS,
)
from app.services.reports.features import AnnotatedTrade, _bucket_numeric


def apply_excursion_features(db: Session, annotated: list[AnnotatedTrade]) -> None:
    if not annotated:
        return
    ids = [at.trade.id for at in annotated]
    rows = db.query(TradeExcursion).filter(TradeExcursion.trade_id.in_(ids)).all()
    by_id = {r.trade_id: r for r in rows}

    for at in annotated:
        ex = by_id.get(at.trade.id)
        if not ex or ex.quality_status in ("PENDING", "NO_INTRADAY_DATA", "OPEN_TRADE"):
            at.features["excursion_available"] = "no"
            continue

        at.features["excursion_available"] = "yes"
        at.features["_excursion"] = ex

        if ex.mfe_r is not None:
            k, lbl = _bucket_numeric(ex.mfe_r, MFE_R_BUCKETS)
            at.features["mfe_r_bucket"] = k
            at.features["_label_mfe_r_bucket"] = lbl

        if ex.mae_r is not None:
            k, lbl = _bucket_numeric(ex.mae_r, MAE_R_BUCKETS)
            at.features["mae_r_bucket"] = k
            at.features["_label_mae_r_bucket"] = lbl

        if ex.exit_efficiency_pct is not None:
            k, lbl = _bucket_numeric(ex.exit_efficiency_pct, EXIT_EFFICIENCY_BUCKETS)
            at.features["exit_efficiency_bucket"] = k
            at.features["_label_exit_efficiency_bucket"] = lbl

        if ex.r_left_on_table is not None:
            k, lbl = _bucket_numeric(ex.r_left_on_table, R_LEFT_BUCKETS)
            at.features["r_left_bucket"] = k
            at.features["_label_r_left_bucket"] = lbl

        if ex.time_to_mfe_seconds is not None:
            k, lbl = _bucket_duration(ex.time_to_mfe_seconds, TIME_TO_MFE_BUCKETS)
            at.features["time_to_mfe_bucket"] = k
            at.features["_label_time_to_mfe_bucket"] = lbl

        if ex.time_to_mae_seconds is not None:
            k, lbl = _bucket_duration(ex.time_to_mae_seconds, TIME_TO_MFE_BUCKETS)
            at.features["time_to_mae_bucket"] = k
            at.features["_label_time_to_mae_bucket"] = lbl

        if ex.mfe_to_exit_seconds is not None:
            k, lbl = _bucket_duration(ex.mfe_to_exit_seconds, MFE_TO_EXIT_BUCKETS)
            at.features["mfe_to_exit_bucket"] = k
            at.features["_label_mfe_to_exit_bucket"] = lbl

        if ex.peak_giveback_pct is not None:
            k, lbl = _bucket_numeric(ex.peak_giveback_pct, PEAK_GIVEBACK_BUCKETS)
            at.features["peak_giveback_bucket"] = k
            at.features["_label_peak_giveback_bucket"] = lbl


def _bucket_duration(seconds: int, buckets) -> tuple[str, str]:
    for key, label, lo, hi in buckets:
        if hi is None and seconds >= lo:
            return key, label
        if lo <= seconds < (hi or 999999999):
            return key, label
    return buckets[-1][0], buckets[-1][1]


def excursion_section_ready(db: Session) -> bool:
    return db.query(TradeExcursion).filter(
        TradeExcursion.quality_status.notin_(["PENDING", "OPEN_TRADE"])
    ).first() is not None
