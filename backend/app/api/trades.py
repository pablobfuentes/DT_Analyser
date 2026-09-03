from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models.execution import Execution
from app.db.models.import_batch import ImportBatch
from app.db.models.trade import Trade
from app.db.models.trade_execution import TradeExecution
from app.db.session import get_db
from app.schemas import (
    ExecutionResponse,
    PaginatedTrades,
    TradeDetailResponse,
    TradeExecutionLink,
    TradeResponse,
    TradeRiskResponse,
    TradeRiskUpdate,
)
from app.utils.analytics import utc_bounds_for_ny_range

router = APIRouter(prefix="/api/trades", tags=["trades"])


@router.get("", response_model=PaginatedTrades)
def list_trades(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    ticker: str | None = None,
    source: str | None = None,
    direction: str | None = None,
    account_id: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    exit_date: str | None = Query(None, alias="date", description="NY calendar date YYYY-MM-DD"),
    has_risk: str | None = Query(None, description="yes, no, or all"),
    r_min: str | None = None,
    r_max: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Trade)
    if ticker:
        q = q.filter(Trade.ticker.ilike(f"%{ticker}%"))
    if source:
        q = q.filter(Trade.source_type == source)
    if direction:
        q = q.filter(Trade.direction == direction.upper())
    if account_id:
        q = q.filter(Trade.account_id == account_id)

    if exit_date:
        d = date.fromisoformat(exit_date)
        utc_start, utc_end = utc_bounds_for_ny_range(d, d)
        if utc_start:
            q = q.filter(Trade.exit_time_utc >= utc_start)
        if utc_end:
            q = q.filter(Trade.exit_time_utc <= utc_end)
    else:
        if date_from:
            d = datetime.fromisoformat(date_from).date() if "T" not in date_from else None
            if d:
                utc_start, _ = utc_bounds_for_ny_range(d, d)
                q = q.filter(Trade.exit_time_utc >= utc_start)
            else:
                q = q.filter(Trade.exit_time_utc >= datetime.fromisoformat(date_from))
        if date_to:
            d = datetime.fromisoformat(date_to).date() if "T" not in date_to else None
            if d:
                _, utc_end = utc_bounds_for_ny_range(d, d)
                q = q.filter(Trade.exit_time_utc <= utc_end)
            else:
                q = q.filter(Trade.exit_time_utc <= datetime.fromisoformat(date_to))

    if has_risk == "yes":
        q = q.filter(Trade.initial_risk_amount.isnot(None), Trade.r_multiple.isnot(None))
    elif has_risk == "no":
        q = q.filter(Trade.r_multiple.is_(None))

    if r_min is not None and r_min != "":
        from decimal import Decimal as D

        q = q.filter(Trade.r_multiple >= D(r_min))
    if r_max is not None and r_max != "":
        from decimal import Decimal as D

        q = q.filter(Trade.r_multiple <= D(r_max))

    total = q.count()
    items = (
        q.order_by(Trade.exit_time_utc.desc().nullslast(), Trade.entry_time_utc.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedTrades(items=items, total=total, page=page, page_size=page_size)


@router.get("/{trade_id}", response_model=TradeDetailResponse)
def get_trade(trade_id: int, db: Session = Depends(get_db)):
    trade = db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")

    links = db.query(TradeExecution).filter(TradeExecution.trade_id == trade_id).all()
    exec_ids = [l.execution_id for l in links]
    executions = db.query(Execution).filter(Execution.id.in_(exec_ids)).all() if exec_ids else []
    exec_by_id = {e.id: e for e in executions}

    batch_ids = {e.import_batch_id for e in executions}
    batches = db.query(ImportBatch).filter(ImportBatch.id.in_(batch_ids)).all() if batch_ids else []

    detail = TradeDetailResponse.model_validate(trade)
    detail.executions = [ExecutionResponse.model_validate(e) for e in executions]
    detail.execution_links = [
        TradeExecutionLink(
            execution=ExecutionResponse.model_validate(exec_by_id[link.execution_id]),
            role=link.role,
            allocated_quantity=link.allocated_quantity,
        )
        for link in links
        if link.execution_id in exec_by_id
    ]
    from app.schemas import ImportBatchResponse

    detail.import_batches = [ImportBatchResponse.model_validate(b) for b in batches]
    from app.db.models.risk import TradeRisk
    from app.db.models.signal import Signal, TradeSignalLink

    risk = db.query(TradeRisk).filter(TradeRisk.trade_id == trade_id).first()
    if risk:
        detail.planned = {
            "planned_entry_price": str(risk.planned_entry_price) if risk.planned_entry_price is not None else None,
            "planned_stop_price": str(risk.planned_stop_price) if risk.planned_stop_price is not None else None,
            "suggested_shares": str(risk.suggested_shares) if risk.suggested_shares is not None else None,
            "planned_risk_per_share": str(risk.planned_risk_per_share) if risk.planned_risk_per_share is not None else None,
            "planned_risk_amount": str(risk.planned_risk_amount) if risk.planned_risk_amount is not None else None,
            "allowed_risk": str(risk.allowed_risk) if risk.allowed_risk is not None else None,
        }
        detail.actual_risk = {
            "initial_stop_price": str(risk.initial_stop_price) if risk.initial_stop_price is not None else None,
            "actual_risk_per_share": str(risk.actual_risk_per_share) if risk.actual_risk_per_share is not None else None,
            "actual_initial_risk_amount": str(risk.actual_initial_risk_amount) if risk.actual_initial_risk_amount is not None else None,
            "stop_derived_risk_amount": str(risk.stop_derived_risk_amount) if risk.stop_derived_risk_amount is not None else None,
            "explicit_initial_risk_amount": str(risk.explicit_initial_risk_amount) if risk.explicit_initial_risk_amount is not None else None,
            "r_multiple": str(risk.r_multiple) if risk.r_multiple is not None else None,
            "r_pnl_basis": risk.r_pnl_basis,
            "fees_known": risk.fees_known,
            "risk_source": risk.risk_source,
            "stop_source": risk.stop_source,
            "risk_quality_status": risk.risk_quality_status,
            "risk_pct_equity_at_entry": str(risk.risk_pct_equity_at_entry) if risk.risk_pct_equity_at_entry is not None else None,
            "equity_before_entry": str(risk.equity_before_entry) if risk.equity_before_entry is not None else None,
            "manual_override": risk.manual_override,
        }
    links = (
        db.query(TradeSignalLink, Signal)
        .join(Signal, Signal.id == TradeSignalLink.signal_id)
        .filter(TradeSignalLink.trade_id == trade_id)
        .all()
    )
    detail.signal_links = [
        {
            "signal_pk": sig.id,
            "signal_id": sig.signal_id,
            "link_status": link.link_status,
            "match_type": link.match_type,
            "confidence": str(link.confidence),
        }
        for link, sig in links
    ]
    return detail


@router.patch("/{trade_id}/risk", response_model=TradeRiskResponse)
def update_trade_risk(trade_id: int, payload: TradeRiskUpdate, db: Session = Depends(get_db)):
    trade = db.get(Trade, trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    if trade.status != "CLOSED":
        raise HTTPException(status_code=400, detail="Risk can only be set on closed trades")

    from app.services.risk.service import RiskService

    if payload.initial_stop_price is None and payload.initial_risk_amount is None:
        raise HTTPException(status_code=400, detail="initial_stop_price or initial_risk_amount required")

    try:
        result = RiskService(db).apply_manual(
            trade,
            initial_stop_price=payload.initial_stop_price,
            initial_risk_amount=payload.initial_risk_amount,
            risk_notes=payload.risk_notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()
    db.refresh(trade)

    return TradeRiskResponse(
        id=trade.id,
        initial_stop_price=trade.initial_stop_price,
        initial_risk_per_share=trade.initial_risk_per_share,
        initial_risk_amount=trade.initial_risk_amount,
        r_multiple=trade.r_multiple,
        risk_source=trade.risk_source,
        risk_notes=trade.risk_notes,
        risk_updated_at=trade.risk_updated_at,
        warnings=result.warnings,
    )
