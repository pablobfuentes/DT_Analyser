"""Trade journal, tags, attachments, search, export."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models.journal import JournalAttachment, JournalEntry
from app.db.session import get_db
from app.services.journal.attachments import (
    attachment_abspath,
    attachment_dict,
    delete_attachment,
    store_attachment,
)
from app.services.journal.service import (
    entry_dict,
    export_journal,
    get_trade_note,
    list_tags,
    search_journal,
    upsert_trade_note,
)

router = APIRouter(prefix="/api/journal", tags=["journal"])


class TradeNoteBody(BaseModel):
    title: str | None = None
    body: str | None = None
    followed_plan: str | None = None
    prompt_fields: dict | None = None
    tags: list[str] | None = None


class CaptionBody(BaseModel):
    caption: str | None = None


@router.get("/trades/{trade_id}")
def get_trade_journal(trade_id: int, db: Session = Depends(get_db)):
    note = get_trade_note(db, trade_id)
    atts = db.query(JournalAttachment).filter(JournalAttachment.trade_id == trade_id).all()
    return {
        "trade_id": trade_id,
        "entry": entry_dict(db, note) if note else None,
        "attachments": [attachment_dict(a) for a in atts],
    }


@router.post("/trades/{trade_id}")
def save_trade_journal(trade_id: int, body: TradeNoteBody, db: Session = Depends(get_db)):
    try:
        entry = upsert_trade_note(db, trade_id, body.model_dump())
    except ValueError as exc:
        raise HTTPException(404 if "not found" in str(exc).lower() else 400, str(exc))
    return entry_dict(db, entry)


@router.get("/trade-status")
def trade_status(ids: str = Query(""), db: Session = Depends(get_db)):
    from app.services.journal.service import trade_journal_map

    raw = [int(x) for x in ids.split(",") if x.strip().isdigit()]
    return trade_journal_map(db, raw)


@router.get("/tags")
def tags(db: Session = Depends(get_db)):
    return {"items": [{"id": t.id, "name": t.name, "description": t.description} for t in list_tags(db)]}


@router.get("/search")
def search(q: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    return {"items": search_journal(db, q)}


@router.get("/export")
def export(fmt: str = Query("csv", pattern="^(csv|markdown)$"), db: Session = Depends(get_db)):
    text = export_journal(db, fmt)
    media = "text/markdown" if fmt == "markdown" else "text/csv"
    return PlainTextResponse(text, media_type=media)


@router.post("/attachments")
async def upload_attachment(
    file: UploadFile = File(...),
    trade_id: int | None = Form(None),
    journal_entry_id: int | None = Form(None),
    daily_review_id: int | None = Form(None),
    weekly_review_id: int | None = Form(None),
    caption: str | None = Form(None),
    db: Session = Depends(get_db),
):
    data = await file.read()
    # Content-Type is ignored. Type comes from magic bytes + extension allowlist.
    try:
        row = store_attachment(
            db,
            data,
            file.filename or "image.png",
            trade_id=trade_id,
            journal_entry_id=journal_entry_id,
            daily_review_id=daily_review_id,
            weekly_review_id=weekly_review_id,
            caption=caption,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    return attachment_dict(row)


@router.get("/attachments/{attachment_id}/file")
def get_file(attachment_id: int, db: Session = Depends(get_db)):
    row = db.get(JournalAttachment, attachment_id)
    if not row:
        raise HTTPException(404, "Attachment not found")
    path = attachment_abspath(row.relative_path)
    if not path.exists():
        raise HTTPException(404, "File missing")
    return FileResponse(path, media_type=row.mime_type, filename=row.original_filename)


@router.patch("/attachments/{attachment_id}")
def patch_caption(attachment_id: int, body: CaptionBody, db: Session = Depends(get_db)):
    row = db.get(JournalAttachment, attachment_id)
    if not row:
        raise HTTPException(404, "Attachment not found")
    row.caption = body.caption
    db.commit()
    return attachment_dict(row)


@router.delete("/attachments/{attachment_id}")
def remove_attachment(attachment_id: int, db: Session = Depends(get_db)):
    try:
        delete_attachment(db, attachment_id)
    except ValueError as exc:
        raise HTTPException(404, str(exc))
    return {"status": "deleted"}
