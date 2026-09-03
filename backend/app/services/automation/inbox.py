"""Inbox scan, import via existing services, archive / quarantine."""

from __future__ import annotations

import json
import logging
import shutil
from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.account import Account
from app.db.models.automation import AutomationFileEvent, utcnow
from app.importers.exceptions import ImporterError, TimezoneRequiredError
from app.paths import ensure_data_layout
from app.services.automation.classify import Classification, classify_path, is_candidate_name, is_stable
from app.services.import_service import ImportService
from app.services.signals.importer import commit_import as pine_commit
from app.utils.hashing import sha256_file

logger = logging.getLogger(__name__)

IMPORTED_STATUSES = frozenset({
    "IMPORTED",
    "IMPORT_SUCCESS_ARCHIVE_PENDING",
    "DUPLICATE_FILE",
})


def inbox_dir() -> Path:
    return ensure_data_layout()["inbox"]


def archive_dir_for(day: date | None = None) -> Path:
    d = day or utcnow().date()
    dest = ensure_data_layout()["archive"] / f"{d.year:04d}" / f"{d.month:02d}" / f"{d.day:02d}"
    dest.mkdir(parents=True, exist_ok=True)
    return dest


def quarantine_dir() -> Path:
    q = ensure_data_layout()["quarantine"]
    q.mkdir(parents=True, exist_ok=True)
    return q


def list_inbox_candidates(root: Path | None = None) -> list[Path]:
    folder = root or inbox_dir()
    if not folder.exists():
        return []
    out = []
    for p in sorted(folder.iterdir()):
        if p.is_file() and is_candidate_name(p.name):
            out.append(p)
    return out


def _unique_dest(folder: Path, filename: str, digest: str) -> Path:
    dest = folder / filename
    if not dest.exists():
        return dest
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    return folder / f"{stem}-{digest[:8]}{suffix}"


def move_to_archive(src: Path, digest: str) -> Path:
    dest = _unique_dest(archive_dir_for(), src.name, digest)
    shutil.move(str(src), str(dest))
    return dest


def move_to_quarantine(src: Path, digest: str) -> Path:
    dest = _unique_dest(quarantine_dir(), src.name, digest)
    shutil.move(str(src), str(dest))
    return dest


def archive_paste_text(text: str, filename: str | None = None) -> Path:
    from app.utils.hashing import sha256_bytes

    layout = ensure_data_layout()
    digest = sha256_bytes(text.encode("utf-8"))
    dest = _unique_dest(layout["paste"], filename or "pine-paste.txt", digest)
    dest.write_text(text, encoding="utf-8")
    return dest


def _account_for(db: Session, detected_type: str) -> Account | None:
    source = "TRADINGVIEW_AUTO" if detected_type == "AUTO_STRATEGY_TESTER" else "TRADINGVIEW_MANUAL"
    return db.query(Account).filter(Account.source == source).order_by(Account.id.asc()).first()


def _already_imported(db: Session, digest: str) -> AutomationFileEvent | None:
    return (
        db.query(AutomationFileEvent)
        .filter(
            AutomationFileEvent.sha256 == digest,
            AutomationFileEvent.status.in_(tuple(IMPORTED_STATUSES) + ("SEEN",)),
        )
        .first()
    )


def record_file_event(
    db: Session,
    path: Path,
    classification: Classification,
    status: str,
) -> AutomationFileEvent:
    digest = classification.metadata.get("sha256") or sha256_file(str(path))
    ev = AutomationFileEvent(
        original_path=str(path),
        working_path=str(path),
        filename=path.name,
        sha256=digest,
        size_bytes=path.stat().st_size if path.exists() else 0,
        detected_type=classification.detected_type,
        detection_confidence=str(classification.confidence),
        status=status,
        error_code=classification.error_code,
        error_message=classification.error_message,
        metadata_json=json.dumps(classification.metadata, default=str),
    )
    db.add(ev)
    db.flush()
    return ev


def import_classified_file(db: Session, path: Path, classification: Classification) -> dict:
    """Call authoritative importers. Never guess timezone."""
    if classification.detected_type == "PINE_LOG":
        text = path.read_text(encoding="utf-8-sig")
        stats = pine_commit(db, text, source="INBOX", filename=path.name)
        return {"kind": "PINE", **stats}

    account = _account_for(db, classification.detected_type)
    if account is None:
        raise ValueError(f"No account for {classification.detected_type}")
    if not classification.parser_name:
        raise ValueError("Missing parser")
    service = ImportService(db)
    stats = service.commit_import(path, path.name, account.id, classification.parser_name, None)
    return {"kind": "TRADE", **stats}


def process_one_file(db: Session, path: Path, *, dry_run: bool = False) -> dict:
    if not path.exists():
        return {"status": "MISSING", "path": str(path)}
    if not is_stable(path, None):
        return {"status": "UNSTABLE", "path": str(path), "filename": path.name}

    classification = classify_path(path)
    digest = classification.metadata.get("sha256") or sha256_file(str(path))

    if dry_run:
        return {
            "status": "DRY_RUN",
            "filename": path.name,
            "detected_type": classification.detected_type,
            "needs_review": classification.needs_review,
            "error_code": classification.error_code,
            "sha256": digest,
        }

    prior = _already_imported(db, digest)
    ev = record_file_event(db, path, classification, "SEEN")

    if prior:
        ev.status = "DUPLICATE_FILE"
        ev.error_code = "DUPLICATE_FILE"
        ev.error_message = f"SHA-256 already processed as file event {prior.id}"
        ev.processed_at = utcnow()
        try:
            dest = move_to_archive(path, digest)
            ev.archived_path = str(dest)
        except OSError as exc:
            ev.error_code = "ARCHIVE_FAILED"
            ev.error_message = str(exc)
        db.commit()
        return {"status": ev.status, "file_event_id": ev.id, "sha256": digest, "imported": 0}

    if classification.needs_review:
        try:
            dest = move_to_quarantine(path, digest)
            ev.archived_path = str(dest)
        except OSError:
            dest = None
        ev.status = "NEEDS_REVIEW"
        ev.processed_at = utcnow()
        db.commit()
        return {
            "status": "NEEDS_REVIEW",
            "file_event_id": ev.id,
            "error_code": classification.error_code,
            "error_message": classification.error_message,
            "quarantine": str(dest) if dest else None,
        }

    try:
        stats = import_classified_file(db, path, classification)
    except TimezoneRequiredError as exc:
        dest = move_to_quarantine(path, digest)
        ev.status = "NEEDS_REVIEW"
        ev.error_code = "TIMEZONE_REQUIRED"
        ev.error_message = str(exc)
        ev.archived_path = str(dest)
        ev.processed_at = utcnow()
        db.commit()
        return {"status": "NEEDS_REVIEW", "file_event_id": ev.id, "error_code": "TIMEZONE_REQUIRED"}
    except ImporterError as exc:
        dest = move_to_quarantine(path, digest)
        ev.status = "NEEDS_REVIEW"
        ev.error_code = getattr(exc, "error_code", "PARSER_ERROR")
        ev.error_message = str(exc)
        ev.archived_path = str(dest)
        ev.processed_at = utcnow()
        db.commit()
        return {"status": "NEEDS_REVIEW", "file_event_id": ev.id, "error_code": ev.error_code}

    ev.import_batch_id = stats.get("import_batch_id")
    ev.import_batch_type = "PINE" if stats.get("kind") == "PINE" else "TRADE"
    ev.processed_at = utcnow()
    ev.metadata_json = json.dumps({**(classification.metadata), "import": stats}, default=str)
    try:
        dest = move_to_archive(path, digest)
        ev.archived_path = str(dest)
        ev.status = "IMPORTED"
    except OSError as exc:
        ev.status = "IMPORT_SUCCESS_ARCHIVE_PENDING"
        ev.error_code = "ARCHIVE_FAILED"
        ev.error_message = str(exc)
    db.commit()
    return {"status": ev.status, "file_event_id": ev.id, "import": stats}


def retry_archive(db: Session, event_id: int) -> dict:
    ev = db.get(AutomationFileEvent, event_id)
    if ev is None:
        raise ValueError("file event not found")
    src = Path(ev.working_path or ev.original_path)
    if not src.exists():
        raise ValueError("source file no longer present")
    dest = move_to_archive(src, ev.sha256)
    ev.archived_path = str(dest)
    ev.status = "IMPORTED"
    ev.error_code = None
    ev.error_message = None
    db.commit()
    return {"status": "IMPORTED", "archived_path": str(dest)}


def process_inbox(db: Session, *, dry_run: bool = False, root: Path | None = None) -> dict:
    files = list_inbox_candidates(root)
    results = []
    for path in files:
        results.append(process_one_file(db, path, dry_run=dry_run))
    return {
        "files_seen": len(files),
        "results": results,
        "imported": sum(1 for r in results if r.get("status") in ("IMPORTED", "IMPORT_SUCCESS_ARCHIVE_PENDING")),
        "needs_review": sum(1 for r in results if r.get("status") == "NEEDS_REVIEW"),
        "duplicates": sum(1 for r in results if r.get("status") == "DUPLICATE_FILE"),
        "unstable": sum(1 for r in results if r.get("status") == "UNSTABLE"),
    }


def ignore_file_event(db: Session, event_id: int) -> AutomationFileEvent:
    ev = db.get(AutomationFileEvent, event_id)
    if ev is None:
        raise ValueError("file event not found")
    ev.status = "IGNORED"
    ev.processed_at = utcnow()
    db.commit()
    return ev
