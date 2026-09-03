"""Risk coverage API."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.models.trade import Trade
from app.db.session import get_db
from app.services.risk.service import missing_r_breakdown

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/coverage")
def risk_coverage(db: Session = Depends(get_db)):
    trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
    breakdown = missing_r_breakdown(db, trades)
    missing_ids = []
    from app.db.models.risk import TradeRisk

    risk_by_trade = {r.trade_id: r for r in db.query(TradeRisk).all()}
    for t in trades:
        row = risk_by_trade.get(t.id)
        if not (row and row.r_multiple is not None):
            if t.r_multiple is None:
                missing_ids.append(t.id)
    breakdown["missing_trade_ids"] = missing_ids[:200]
    return breakdown
