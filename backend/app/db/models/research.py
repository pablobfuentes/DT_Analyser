"""Lightweight saved research artifacts. Candidate rules never modify Pine or risk."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class SavedCohort(Base):
    __tablename__ = "saved_cohorts"
    __table_args__ = (Index("ix_saved_cohorts_name", "name"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filter_json: Mapped[str] = mapped_column(Text, nullable=False)
    research_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="PRE_ENTRY_ONLY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class ResearchView(Base):
    __tablename__ = "research_views"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    global_scope_json: Mapped[str] = mapped_column(Text, nullable=False)
    cohort_a_json: Mapped[str] = mapped_column(Text, nullable=False)
    cohort_b_json: Mapped[str] = mapped_column(Text, nullable=False)
    visualization_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    research_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="PRE_ENTRY_ONLY")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class CandidateRule(Base):
    __tablename__ = "candidate_rules"
    __table_args__ = (
        Index("ix_candidate_rules_parent", "parent_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    filter_json: Mapped[str] = mapped_column(Text, nullable=False)
    research_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="PRE_ENTRY_ONLY")
    research_start: Mapped[str | None] = mapped_column(String(16), nullable=True)
    research_end: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cutoff_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    rule_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="RESEARCH")
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("candidate_rules.id", ondelete="SET NULL"), nullable=True)
    statistics_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
    bootstrap_seed: Mapped[int] = mapped_column(Integer, nullable=False, default=20260902)
    bootstrap_iterations: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PatternSnapshot(Base):
    __tablename__ = "pattern_snapshots"
    __table_args__ = ({"sqlite_autoincrement": True},)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    filter_json: Mapped[str] = mapped_column(Text, nullable=False)
    research_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, nullable=False)
    sample_size: Mapped[int] = mapped_column(Integer, nullable=False)
    date_start: Mapped[str | None] = mapped_column(String(16), nullable=True)
    date_end: Mapped[str | None] = mapped_column(String(16), nullable=True)
    starred_from: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    statistics_version: Mapped[str] = mapped_column(String(16), nullable=False, default="1")
