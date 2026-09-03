"""Journal entries, tags, and local search."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models.journal import JournalEntry, JournalEntryTag, JournalTag
from app.db.models.trade import Trade
from app.utils.hashing import json_dumps


def _norm(name: str) -> str:
    return name.strip().upper()


def get_or_create_tag(db: Session, name: str, description: str | None = None) -> JournalTag:
    key = _norm(name)
    if not key:
        raise ValueError("Tag name required")
    row = db.query(JournalTag).filter(JournalTag.name_normalized == key).first()
    if row:
        return row
    row = JournalTag(name=name.strip(), name_normalized=key, description=description)
    db.add(row)
    db.flush()
    return row


def list_tags(db: Session) -> list[JournalTag]:
    return db.query(JournalTag).order_by(JournalTag.name_normalized.asc()).all()


def _tag_names(db: Session, entry_id: int) -> list[str]:
    rows = (
        db.query(JournalTag.name)
        .join(JournalEntryTag, JournalEntryTag.tag_id == JournalTag.id)
        .filter(JournalEntryTag.entry_id == entry_id)
        .all()
    )
    return [r[0] for r in rows]


def entry_dict(db: Session, entry: JournalEntry) -> dict:
    prompts = {}
    if entry.prompt_fields_json:
        try:
            prompts = json.loads(entry.prompt_fields_json)
        except json.JSONDecodeError:
            prompts = {}
    return {
        "id": entry.id,
        "trade_id": entry.trade_id,
        "review_date": entry.review_date,
        "entry_type": entry.entry_type,
        "title": entry.title,
        "body": entry.body,
        "followed_plan": entry.followed_plan,
        "prompt_fields": prompts,
        "tags": _tag_names(db, entry.id),
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
        "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
    }


def set_entry_tags(db: Session, entry: JournalEntry, names: list[str]) -> None:
    db.query(JournalEntryTag).filter(JournalEntryTag.entry_id == entry.id).delete()
    seen = set()
    for name in names:
        tag = get_or_create_tag(db, name)
        if tag.id in seen:
            continue
        db.add(JournalEntryTag(entry_id=entry.id, tag_id=tag.id))
        seen.add(tag.id)
    db.flush()


def upsert_trade_note(db: Session, trade_id: int, payload: dict) -> JournalEntry:
    trade = db.get(Trade, trade_id)
    if trade is None:
        raise ValueError("Trade not found")
    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.trade_id == trade_id, JournalEntry.entry_type == "TRADE_NOTE")
        .first()
    )
    if entry is None:
        entry = JournalEntry(trade_id=trade_id, entry_type="TRADE_NOTE", body="")
        db.add(entry)
        db.flush()
    if "title" in payload:
        entry.title = payload.get("title")
    if "body" in payload:
        entry.body = payload.get("body") or ""
    if "followed_plan" in payload:
        entry.followed_plan = str(payload["followed_plan"] or "NOT_ASSESSED").upper()
    if "prompt_fields" in payload:
        entry.prompt_fields_json = json_dumps(payload.get("prompt_fields") or {})
    entry.updated_at = datetime.now(timezone.utc)
    if "tags" in payload:
        set_entry_tags(db, entry, list(payload.get("tags") or []))
    db.commit()
    db.refresh(entry)
    return entry


def get_trade_note(db: Session, trade_id: int) -> JournalEntry | None:
    return (
        db.query(JournalEntry)
        .filter(JournalEntry.trade_id == trade_id, JournalEntry.entry_type == "TRADE_NOTE")
        .first()
    )


def trade_journal_map(db: Session, trade_ids: list[int]) -> dict[int, bool]:
    if not trade_ids:
        return {}
    rows = (
        db.query(JournalEntry.trade_id)
        .filter(JournalEntry.trade_id.in_(trade_ids), JournalEntry.entry_type == "TRADE_NOTE")
        .all()
    )
    have = {tid for (tid,) in rows if tid}
    return {tid: tid in have for tid in trade_ids}


def search_journal(db: Session, q: str) -> list[dict]:
    term = f"%{(q or '').strip()}%"
    if term == "%%":
        return []
    entries = (
        db.query(JournalEntry)
        .filter(
            or_(
                JournalEntry.body.ilike(term),
                JournalEntry.title.ilike(term),
                JournalEntry.prompt_fields_json.ilike(term),
            )
        )
        .order_by(JournalEntry.updated_at.desc())
        .limit(100)
        .all()
    )
    tag_hits = (
        db.query(JournalEntry)
        .join(JournalEntryTag, JournalEntryTag.entry_id == JournalEntry.id)
        .join(JournalTag, JournalTag.id == JournalEntryTag.tag_id)
        .filter(or_(JournalTag.name.ilike(term), JournalTag.name_normalized.ilike(term)))
        .all()
    )
    from app.db.models.journal import JournalAttachment

    cap_hits = (
        db.query(JournalEntry)
        .join(JournalAttachment, JournalAttachment.journal_entry_id == JournalEntry.id)
        .filter(JournalAttachment.caption.ilike(term))
        .all()
    )
    seen = {}
    for e in list(entries) + list(tag_hits) + list(cap_hits):
        seen[e.id] = e
    return [entry_dict(db, e) for e in seen.values()]


def export_journal(db: Session, fmt: str = "csv") -> str:
    entries = db.query(JournalEntry).order_by(JournalEntry.id.asc()).all()
    if fmt == "markdown":
        lines = ["# Journal export", ""]
        for e in entries:
            title = e.title or e.entry_type
            lines.append(f"## {title} ({e.entry_type} #{e.id})")
            if e.trade_id:
                lines.append(f"Trade: {e.trade_id}")
            if e.review_date:
                lines.append(f"Date: {e.review_date}")
            lines.append("")
            lines.append(e.body or "")
            lines.append("")
        return "\n".join(lines)
    import csv
    import io

    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "entry_type", "trade_id", "review_date", "title", "body", "followed_plan", "tags"])
    for e in entries:
        w.writerow([
            e.id,
            e.entry_type,
            e.trade_id or "",
            e.review_date or "",
            e.title or "",
            e.body or "",
            e.followed_plan,
            "|".join(_tag_names(db, e.id)),
        ])
    return buf.getvalue()
