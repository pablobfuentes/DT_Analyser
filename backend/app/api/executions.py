from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models.execution import Execution
from app.db.session import get_db
from app.schemas import ExecutionResponse, PaginatedExecutions

router = APIRouter(prefix="/api/executions", tags=["executions"])


@router.get("", response_model=PaginatedExecutions)
def list_executions(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    ticker: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Execution)
    if ticker:
        q = q.filter(Execution.ticker.ilike(f"%{ticker}%"))
    total = q.count()
    items = (
        q.order_by(Execution.execution_time_utc.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return PaginatedExecutions(items=items, total=total, page=page, page_size=page_size)


@router.get("/{execution_id}", response_model=ExecutionResponse)
def get_execution(execution_id: int, db: Session = Depends(get_db)):
    execution = db.get(Execution, execution_id)
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution
