"""Journal entries, tags, and filesystem attachments."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        Index("ix_journal_entries_trade", "trade_id"),
        Index("ix_journal_entries_type", "entry_type"),
        Index("ix_journal_entries_review_date", "review_date"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), nullable=True)
    review_date: Mapped[str | None] = mapped_column(String(10), nullable=True)
    entry_type: Mapped[str] = mapped_column(String(32), nullable=False, default="GENERAL")
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    followed_plan: Mapped[str] = mapped_column(String(32), nullable=False, default="NOT_ASSESSED")
    prompt_fields_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class JournalTag(Base):
    __tablename__ = "journal_tags"
    __table_args__ = (UniqueConstraint("name_normalized", name="uq_journal_tag_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    name_normalized: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class JournalEntryTag(Base):
    __tablename__ = "journal_entry_tags"
    __table_args__ = (UniqueConstraint("entry_id", "tag_id", name="uq_journal_entry_tag"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"), nullable=False)
    tag_id: Mapped[int] = mapped_column(ForeignKey("journal_tags.id"), nullable=False)


class JournalAttachment(Base):
    __tablename__ = "journal_attachments"
    __table_args__ = (
        Index("ix_journal_attachments_sha", "sha256"),
        Index("ix_journal_attachments_trade", "trade_id"),
        {"sqlite_autoincrement": True},
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    trade_id: Mapped[int | None] = mapped_column(ForeignKey("trades.id"), nullable=True)
    journal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"), nullable=True)
    daily_review_id: Mapped[int | None] = mapped_column(ForeignKey("daily_reviews.id"), nullable=True)
    weekly_review_id: Mapped[int | None] = mapped_column(ForeignKey("weekly_reviews.id"), nullable=True)
    relative_path: Mapped[str] = mapped_column(String(512), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(64), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
