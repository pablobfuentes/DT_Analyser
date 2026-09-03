"""Screenshot attachments on the local filesystem. No SQLite BLOBs. No OCR."""

from __future__ import annotations

import struct
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.db.models.journal import JournalAttachment
from app.paths import data_layout, ensure_data_layout, is_under
from app.utils.hashing import sha256_bytes

ALLOWED = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/webp": ".webp",
}

ALLOWED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp"})
DANGEROUS_SUFFIXES = frozenset({
    ".exe", ".bat", ".cmd", ".com", ".msi", ".scr", ".ps1", ".vbs", ".js",
    ".dll", ".pif", ".cpl",
})

MAX_BYTES = 20 * 1024 * 1024


def sniff_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def image_size(data: bytes, mime: str) -> tuple[int | None, int | None]:
    try:
        if mime == "image/png" and len(data) >= 24:
            w, h = struct.unpack(">II", data[16:24])
            return int(w), int(h)
        if mime == "image/jpeg":
            i = 2
            while i < len(data) - 9:
                if data[i] != 0xFF:
                    break
                marker = data[i + 1]
                if marker in (0xC0, 0xC1, 0xC2):
                    h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                    return int(w), int(h)
                if marker == 0xD8:
                    i += 2
                    continue
                seglen = struct.unpack(">H", data[i + 2 : i + 4])[0]
                i += 2 + seglen
        if mime == "image/webp" and len(data) >= 30 and data[12:16] == b"VP8 ":
            w = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            h = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return int(w), int(h)
    except Exception:
        return None, None
    return None, None


def safe_original_name(name: str) -> str:
    return Path(str(name).replace("\\", "/")).name or "image.png"


def assert_safe_upload_name(name: str) -> str:
    """Reject traversal, absolute paths, missing/unknown/double extensions, executables.

    Filename is never trusted for type. Magic bytes are still required.
    """
    raw = str(name or "")
    if not raw.strip():
        raise ValueError("Attachment filename required")
    normalized = raw.replace("\\", "/")
    if normalized.startswith("/") or normalized.startswith("//"):
        raise ValueError("Absolute attachment paths are not allowed")
    if len(normalized) >= 2 and normalized[1] == ":":
        raise ValueError("Absolute attachment paths are not allowed")
    if ".." in normalized.split("/"):
        raise ValueError("Path traversal is not allowed")
    cleaned = safe_original_name(raw)
    if cleaned in (".", "..") or "\x00" in raw:
        raise ValueError("Unsafe attachment filename")
    suffixes = [s.lower() for s in Path(cleaned).suffixes]
    if not suffixes:
        raise ValueError("Attachment must have a .png, .jpg, .jpeg, or .webp extension")
    if len(suffixes) != 1:
        raise ValueError("Double extensions are not allowed")
    if suffixes[-1] not in ALLOWED_EXTENSIONS:
        raise ValueError("Only PNG, JPEG, and WEBP attachments are allowed")
    if any(s in DANGEROUS_SUFFIXES for s in suffixes):
        raise ValueError("Executable attachments are not allowed")
    return cleaned


def store_attachment(
    db: Session,
    data: bytes,
    original_filename: str,
    *,
    trade_id: int | None = None,
    journal_entry_id: int | None = None,
    daily_review_id: int | None = None,
    weekly_review_id: int | None = None,
    caption: str | None = None,
) -> JournalAttachment:
    if len(data) > MAX_BYTES:
        raise ValueError("Attachment too large")
    original = assert_safe_upload_name(original_filename)
    mime = sniff_mime(data)
    if mime not in ALLOWED:
        raise ValueError("Only PNG, JPEG, and WEBP attachments are allowed")
    digest = sha256_bytes(data)
    now = datetime.now(timezone.utc)
    rel = Path("screenshots") / f"{now.year:04d}" / f"{now.month:02d}" / f"{digest}{ALLOWED[mime]}"
    layout = ensure_data_layout()
    dest = layout["root"] / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists():
        dest.write_bytes(data)
    w, h = image_size(data, mime)
    row = JournalAttachment(
        trade_id=trade_id,
        journal_entry_id=journal_entry_id,
        daily_review_id=daily_review_id,
        weekly_review_id=weekly_review_id,
        relative_path=rel.as_posix(),
        original_filename=original,
        mime_type=mime,
        size_bytes=len(data),
        sha256=digest,
        width=w,
        height=h,
        caption=caption,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def attachment_abspath(relative_path: str) -> Path:
    root = data_layout()["root"]
    dest = (root / relative_path).resolve()
    if not is_under(dest, root):
        raise ValueError("Unsafe attachment path")
    return dest


def delete_attachment(db: Session, attachment_id: int) -> None:
    row = db.get(JournalAttachment, attachment_id)
    if row is None:
        raise ValueError("Attachment not found")
    digest = row.sha256
    rel = row.relative_path
    db.delete(row)
    db.flush()
    others = db.query(JournalAttachment).filter(JournalAttachment.sha256 == digest).count()
    if others == 0:
        path = attachment_abspath(rel)
        if path.exists():
            path.unlink()
    db.commit()


def attachment_dict(row: JournalAttachment) -> dict:
    return {
        "id": row.id,
        "trade_id": row.trade_id,
        "journal_entry_id": row.journal_entry_id,
        "daily_review_id": row.daily_review_id,
        "weekly_review_id": row.weekly_review_id,
        "relative_path": row.relative_path,
        "original_filename": row.original_filename,
        "mime_type": row.mime_type,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "width": row.width,
        "height": row.height,
        "caption": row.caption,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "url": f"/api/journal/attachments/{row.id}/file",
    }
