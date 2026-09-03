from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.reports.filters import parse_filter_set
from app.services.reports.service import get_reports

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("")
def reports(
    request: Request,
    min_sample: int = Query(1, ge=1, le=100),
    db: Session = Depends(get_db),
):
    params = {k: v for k, v in request.query_params.items() if v not in (None, "")}
    filt = parse_filter_set(params)
    return get_reports(db, filt, min_sample=min_sample)
