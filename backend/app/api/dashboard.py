from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import DashboardFilters, get_dashboard

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardResponse)
def dashboard(
    start_date: date | None = None,
    end_date: date | None = None,
    account_id: int | None = None,
    source_type: str | None = Query(None, description="ALL, MANUAL, AUTO, or full source type"),
    direction: str | None = None,
    ticker: str | None = None,
    db: Session = Depends(get_db),
):
    filters = DashboardFilters(
        start_date=start_date,
        end_date=end_date,
        account_id=account_id,
        source_type=source_type,
        direction=direction,
        ticker=ticker,
    )
    return get_dashboard(db, filters)
