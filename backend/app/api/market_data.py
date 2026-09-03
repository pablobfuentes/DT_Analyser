"""Market data API."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.market_data.registry import get_market_data_provider, provider_status
from app.services.market_enrichment.service import MarketEnrichmentService, get_coverage

router = APIRouter(prefix="/api/market-data", tags=["market-data"])


class EnrichRequest(BaseModel):
    scope: str = "missing"
    dry_run: bool = False


@router.get("/status")
def status(db: Session = Depends(get_db)):
    cov = get_coverage(db)
    st = provider_status()
    return {**st, **cov}


@router.get("/coverage")
def coverage(db: Session = Depends(get_db)):
    return get_coverage(db)


@router.post("/enrich")
def enrich(body: EnrichRequest, db: Session = Depends(get_db)):
    svc = MarketEnrichmentService(db, get_market_data_provider())
    return svc.enrich(scope=body.scope, dry_run=body.dry_run)


@router.post("/recalculate")
def recalculate(db: Session = Depends(get_db)):
    svc = MarketEnrichmentService(db, get_market_data_provider())
    return svc.recalculate()


@router.post("/refresh")
def refresh(body: EnrichRequest, db: Session = Depends(get_db)):
    svc = MarketEnrichmentService(db, get_market_data_provider())
    return svc.refresh(scope=body.scope or "all")
