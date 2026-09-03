"""Daily and weekly reviews."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.reviews import daily as daily_svc
from app.services.reviews import weekly as weekly_svc
from app.utils.analytics import ny_date_from_utc
from app.utils.clock import utc_now

router = APIRouter(prefix="/api/reviews", tags=["reviews"])


class ReviewPatch(BaseModel):
    body: str | None = None
    prompt_fields: dict | None = None


class CompleteBody(BaseModel):
    refresh_snapshot: bool = False


def _day(raw: str | None) -> date:
    return date.fromisoformat(raw) if raw else ny_date_from_utc(utc_now())


@router.get("/daily/{ny_date}")
def get_daily(ny_date: str, db: Session = Depends(get_db)):
    try:
        return daily_svc.review_payload(db, date.fromisoformat(ny_date))
    except ValueError:
        raise HTTPException(400, "Invalid date")


@router.patch("/daily/{ny_date}")
def patch_daily(ny_date: str, body: ReviewPatch, db: Session = Depends(get_db)):
    daily_svc.patch_review(db, date.fromisoformat(ny_date), body.model_dump())
    return daily_svc.review_payload(db, date.fromisoformat(ny_date))


@router.post("/daily/{ny_date}/complete")
def complete_daily(ny_date: str, body: CompleteBody | None = None, db: Session = Depends(get_db)):
    daily_svc.complete_review(db, date.fromisoformat(ny_date), refresh_snapshot=bool(body and body.refresh_snapshot))
    return daily_svc.review_payload(db, date.fromisoformat(ny_date))


@router.get("/weekly/{week}")
def get_weekly(week: str, db: Session = Depends(get_db)):
    return weekly_svc.review_payload(db, date.fromisoformat(week))


@router.patch("/weekly/{week}")
def patch_weekly(week: str, body: ReviewPatch, db: Session = Depends(get_db)):
    weekly_svc.patch_review(db, date.fromisoformat(week), body.model_dump())
    return weekly_svc.review_payload(db, date.fromisoformat(week))


@router.post("/weekly/{week}/complete")
def complete_weekly(week: str, body: CompleteBody | None = None, db: Session = Depends(get_db)):
    weekly_svc.complete_review(db, date.fromisoformat(week), refresh_snapshot=bool(body and body.refresh_snapshot))
    return weekly_svc.review_payload(db, date.fromisoformat(week))


@router.get("/history")
def history(db: Session = Depends(get_db)):
    return weekly_svc.review_history(db)


@router.get("/today")
def today(db: Session = Depends(get_db), date_str: str | None = Query(None, alias="date")):
    return daily_svc.review_payload(db, _day(date_str))
