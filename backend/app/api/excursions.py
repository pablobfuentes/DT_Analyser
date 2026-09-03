"""Excursions API (Step 8)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.market_data import TradeExcursion
from app.db.session import get_db
from app.services.excursion_enrichment.coverage import boundary_spread_stats, get_excursion_coverage, storage_stats
from app.services.excursion_enrichment.service import ExcursionEnrichmentService
from app.market_data.registry import get_market_data_provider

router = APIRouter(prefix="/api/excursions", tags=["excursions"])


class EnrichRequest(BaseModel):
    scope: str = "missing"
    dry_run: bool = False


@router.get("/coverage")
def coverage(db: Session = Depends(get_db)):
    return {
        **get_excursion_coverage(db),
        **boundary_spread_stats(db),
        **storage_stats(db),
    }


@router.post("/enrich")
def enrich(body: EnrichRequest, db: Session = Depends(get_db)):
    svc = ExcursionEnrichmentService(db, get_market_data_provider())
    return svc.enrich(scope=body.scope, dry_run=body.dry_run)


@router.post("/recalculate")
def recalculate(db: Session = Depends(get_db)):
    svc = ExcursionEnrichmentService(db, get_market_data_provider())
    return svc.recalculate()


@router.get("/trades/{trade_id}")
def get_trade_excursion(trade_id: int, db: Session = Depends(get_db)):
    row = db.query(TradeExcursion).filter(TradeExcursion.trade_id == trade_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Excursion data not found")
    return _serialize(row)


def _serialize(r: TradeExcursion) -> dict:
    import json

    flags = json.loads(r.quality_flags_json) if r.quality_flags_json else []
    return {
        "trade_id": r.trade_id,
        "data_provider": r.data_provider,
        "data_feed": r.data_feed,
        "data_resolution": r.data_resolution,
        "is_consolidated": r.is_consolidated,
        "holding_start_utc": r.holding_start_utc.isoformat() if r.holding_start_utc else None,
        "holding_end_utc": r.holding_end_utc.isoformat() if r.holding_end_utc else None,
        "reference_entry_price": str(r.reference_entry_price) if r.reference_entry_price else None,
        "price_mfe": str(r.price_mfe) if r.price_mfe is not None else None,
        "price_mae": str(r.price_mae) if r.price_mae is not None else None,
        "price_mfe_pct": str(r.price_mfe_pct) if r.price_mfe_pct is not None else None,
        "price_mae_pct": str(r.price_mae_pct) if r.price_mae_pct is not None else None,
        "conservative_price_mfe": str(r.conservative_price_mfe) if r.conservative_price_mfe is not None else None,
        "conservative_price_mae": str(r.conservative_price_mae) if r.conservative_price_mae is not None else None,
        "position_mfe_amount": str(r.position_mfe_amount) if r.position_mfe_amount is not None else None,
        "position_mae_amount": str(r.position_mae_amount) if r.position_mae_amount is not None else None,
        "mfe_r": str(r.mfe_r) if r.mfe_r is not None else None,
        "mae_r": str(r.mae_r) if r.mae_r is not None else None,
        "conservative_position_mfe_amount": str(r.conservative_position_mfe_amount) if r.conservative_position_mfe_amount is not None else None,
        "conservative_position_mae_amount": str(r.conservative_position_mae_amount) if r.conservative_position_mae_amount is not None else None,
        "conservative_mfe_r": str(r.conservative_mfe_r) if r.conservative_mfe_r is not None else None,
        "conservative_mae_r": str(r.conservative_mae_r) if r.conservative_mae_r is not None else None,
        "mfe_boundary_spread_amount": str(r.mfe_boundary_spread_amount) if r.mfe_boundary_spread_amount is not None else None,
        "mfe_boundary_spread_r": str(r.mfe_boundary_spread_r) if r.mfe_boundary_spread_r is not None else None,
        "mae_boundary_spread_amount": str(r.mae_boundary_spread_amount) if r.mae_boundary_spread_amount is not None else None,
        "mae_boundary_spread_r": str(r.mae_boundary_spread_r) if r.mae_boundary_spread_r is not None else None,
        "mfe_time_utc": r.mfe_time_utc.isoformat() if r.mfe_time_utc else None,
        "mae_time_utc": r.mae_time_utc.isoformat() if r.mae_time_utc else None,
        "time_to_mfe_seconds": r.time_to_mfe_seconds,
        "time_to_mae_seconds": r.time_to_mae_seconds,
        "mfe_to_exit_seconds": r.mfe_to_exit_seconds,
        "gross_realized_pnl": str(r.gross_realized_pnl) if r.gross_realized_pnl is not None else None,
        "gross_realized_r": str(r.gross_realized_r) if r.gross_realized_r is not None else None,
        "exit_efficiency_pct": str(r.exit_efficiency_pct) if r.exit_efficiency_pct is not None else None,
        "r_left_on_table": str(r.r_left_on_table) if r.r_left_on_table is not None else None,
        "peak_giveback_amount": str(r.peak_giveback_amount) if r.peak_giveback_amount is not None else None,
        "peak_giveback_r": str(r.peak_giveback_r) if r.peak_giveback_r is not None else None,
        "peak_giveback_pct": str(r.peak_giveback_pct) if r.peak_giveback_pct is not None else None,
        "post_exit_favorable_5m": str(r.post_exit_favorable_5m) if r.post_exit_favorable_5m is not None else None,
        "post_exit_favorable_15m": str(r.post_exit_favorable_15m) if r.post_exit_favorable_15m is not None else None,
        "post_exit_favorable_30m": str(r.post_exit_favorable_30m) if r.post_exit_favorable_30m is not None else None,
        "post_exit_favorable_5m_r": str(r.post_exit_favorable_5m_r) if r.post_exit_favorable_5m_r is not None else None,
        "post_exit_favorable_15m_r": str(r.post_exit_favorable_15m_r) if r.post_exit_favorable_15m_r is not None else None,
        "post_exit_favorable_30m_r": str(r.post_exit_favorable_30m_r) if r.post_exit_favorable_30m_r is not None else None,
        "copilot_exit_time_utc": r.copilot_exit_time_utc.isoformat() if r.copilot_exit_time_utc else None,
        "copilot_exit_price": str(r.copilot_exit_price) if r.copilot_exit_price is not None else None,
        "copilot_exit_delta_seconds": r.copilot_exit_delta_seconds,
        "copilot_exit_delta_price": str(r.copilot_exit_delta_price) if r.copilot_exit_delta_price is not None else None,
        "copilot_exit_delta_pct": str(r.copilot_exit_delta_pct) if r.copilot_exit_delta_pct is not None else None,
        "quality_status": r.quality_status,
        "quality_flags": flags,
        "boundary_ambiguity": r.boundary_ambiguity,
        "efficiency_over_100": r.efficiency_over_100,
        "sparse_interval": r.sparse_interval,
        "longest_bar_gap_seconds": r.longest_bar_gap_seconds,
        "provider_missing_data": r.provider_missing_data,
        "calculation_version": r.calculation_version,
        "calculated_at": r.calculated_at.isoformat() if r.calculated_at else None,
    }
