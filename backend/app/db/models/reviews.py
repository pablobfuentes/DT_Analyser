"""Daily and weekly review records with frozen metric snapshots."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class DailyReview(Base):
    __tablename__ = "daily_reviews"
    __table_args__ = (UniqueConstraint("ny_date", name="uq_daily_review_date"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ny_date: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_STARTED")
    prompt_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculation_versions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class WeeklyReview(Base):
    __tablename__ = "weekly_reviews"
    __table_args__ = (UniqueConstraint("week_start_date", name="uq_weekly_review_week"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    week_start_date: Mapped[str] = mapped_column(String(10), nullable=False)
    week_end_date: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_STARTED")
    prompt_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    metrics_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    calculation_versions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)
