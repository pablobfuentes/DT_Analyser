"""Automation jobs, runs, file events, preferences, and daily workflow flags."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AutomationJob(Base):
    __tablename__ = "automation_jobs"
    __table_args__ = (
        Index("ix_automation_jobs_status", "status"),
        Index("ix_automation_jobs_next_retry", "next_retry_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    job_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parent_job_id: Mapped[int | None] = mapped_column(ForeignKey("automation_jobs.id"), nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("automation_runs.id"), nullable=True)


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = (
        Index("ix_automation_runs_created", "created_at"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(64), nullable=False)
    ny_date: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)


class AutomationRunStep(Base):
    __tablename__ = "automation_run_steps"
    __table_args__ = (
        Index("ix_automation_run_steps_run", "run_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("automation_runs.id"), nullable=False)
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    records_processed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_created: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AutomationFileEvent(Base):
    __tablename__ = "automation_file_events"
    __table_args__ = (
        Index("ix_automation_file_events_sha", "sha256"),
        Index("ix_automation_file_events_status", "status"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    original_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    working_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    archived_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    detected_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detection_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    status: Mapped[str] = mapped_column(String(48), nullable=False, default="SEEN")
    import_batch_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class AppPreference(Base):
    __tablename__ = "app_preferences"
    __table_args__ = (UniqueConstraint("key", name="uq_app_preferences_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    value_json: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class DailyWorkflowDay(Base):
    __tablename__ = "daily_workflow_days"
    __table_args__ = (UniqueConstraint("ny_date", name="uq_daily_workflow_day"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ny_date: Mapped[str] = mapped_column(String(10), nullable=False)
    no_trading: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class BackupRecord(Base):
    __tablename__ = "backup_records"
    __table_args__ = (Index("ix_backup_records_created", "created_at"), {"sqlite_autoincrement": True})

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    backup_type: Mapped[str] = mapped_column(String(32), nullable=False)
    backup_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    path: Mapped[str] = mapped_column(String(1024), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="PENDING")
    db_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    archive_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum: Mapped[str | None] = mapped_column(String(64), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    manifest_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    attachment_warning: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
