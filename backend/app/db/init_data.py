import logging
import re
import shutil
import time
from pathlib import Path

from app.config import settings
from app.db.models.account import Account
from app.db.session import SessionLocal, init_db
from app.db.migrate import run_migrations
from app.utils.hashing import sha256_bytes

logger = logging.getLogger(__name__)

DEFAULT_ACCOUNTS = [
    {"name": "Manual TradingView Account", "source": "TRADINGVIEW_MANUAL", "is_simulated": False},
    {"name": "AUTO Strategy Tester", "source": "TRADINGVIEW_AUTO", "is_simulated": True},
]

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def seed_accounts() -> None:
    db = SessionLocal()
    try:
        for acct in DEFAULT_ACCOUNTS:
            existing = db.query(Account).filter(Account.name == acct["name"]).first()
            if not existing:
                db.add(Account(**acct))
        db.commit()
    finally:
        db.close()


def initialize_app() -> None:
    from app.paths import ensure_data_layout

    ensure_data_layout()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    Path("./data").mkdir(parents=True, exist_ok=True)
    _pre_migration_file_backup()
    init_db()
    db = SessionLocal()
    try:
        from app.services.backup.service import maybe_pre_migration_backup

        maybe_pre_migration_backup(db)
    except Exception:
        logger.exception("Recorded PRE_MIGRATION backup skipped")
    finally:
        db.close()
    run_migrations()
    seed_accounts()
    cleanup_stale_uploads()
    logger.info("Application initialized")


def _pre_migration_marker(signature: str) -> Path:
    from app.paths import ensure_data_layout

    return ensure_data_layout()["backups"] / f".pre_migration_{signature}"


def _pre_migration_file_backup() -> None:
    """One PRE_MIGRATION file copy when a schema mutation is pending and user data exists.

    Used when backup_records is not available yet. Future ALTERs use maybe_pre_migration_backup
    after tables exist. Not keyed only to automation_jobs being absent. Not every startup.
    """
    import sqlite3
    from datetime import datetime, timezone

    from app.db.migrate import (
        meaningful_user_data_count,
        pending_schema_mutations_at_path,
        pre_migration_signature,
    )
    from app.paths import ensure_data_layout, sqlite_file_path
    from app.services.backup.service import _copy_db, _integrity_ok

    path = sqlite_file_path()
    if path is None or not path.exists():
        return
    pending = pending_schema_mutations_at_path(path)
    if not pending:
        return
    if meaningful_user_data_count(path) <= 0:
        return
    sig = pre_migration_signature(pending)
    marker = _pre_migration_marker(sig)
    if marker.exists():
        return
    conn = sqlite3.connect(str(path))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    if "backup_records" in tables:
        # Recorded backup path will run after init_db.
        return
    dest_dir = ensure_data_layout()["backups"] / f"pre-migration-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "trader.db"
    _copy_db(path, dest)
    if _integrity_ok(dest):
        marker.write_text("\n".join(pending), encoding="utf-8")
        logger.info("PRE_MIGRATION file backup written to %s pending=%s", dest, pending)
    else:
        logger.error("PRE_MIGRATION backup failed integrity check")


def sanitize_upload_filename(filename: str) -> str:
    """Keep only the final path component so uploads cannot escape the temp dir."""
    name = Path(str(filename).replace("\\", "/")).name
    name = name.replace("\x00", "")
    if not name or name in (".", ".."):
        return "upload.csv"
    return name


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def cleanup_stale_uploads(max_age_seconds: int | None = None) -> int:
    """Delete hash-keyed preview dirs older than the retention window.

    Only removes directories named with a 64-char hex SHA-256 under upload_dir.
    Never deletes files outside that directory.
    """
    ttl = max_age_seconds
    if ttl is None:
        ttl = int(settings.upload_retention_hours * 3600)
    upload_root = settings.upload_dir
    if not upload_root.exists():
        return 0
    upload_root = upload_root.resolve()
    now = time.time()
    removed = 0
    for child in upload_root.iterdir():
        if not child.is_dir() or not _HASH_RE.fullmatch(child.name):
            continue
        if not _is_under(child, upload_root):
            continue
        try:
            mtime = child.stat().st_mtime
        except OSError:
            continue
        if now - mtime <= ttl:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed += 1
        logger.info("Removed stale upload dir %s", child.name)
    return removed


def save_upload(content: bytes, filename: str) -> tuple[Path, str]:
    cleanup_stale_uploads()
    file_hash = sha256_bytes(content)
    upload_root = settings.upload_dir.resolve()
    dest_dir = (settings.upload_dir / file_hash).resolve()
    if not _is_under(dest_dir, upload_root):
        raise ValueError("Invalid upload path")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / sanitize_upload_filename(filename)
    dest.write_bytes(content)
    return dest, file_hash


def get_upload_path(file_hash: str, filename: str | None = None) -> Path | None:
    if not file_hash or not _HASH_RE.fullmatch(file_hash):
        return None
    upload_root = settings.upload_dir.resolve()
    dest_dir = (settings.upload_dir / file_hash).resolve()
    if not dest_dir.exists() or not _is_under(dest_dir, upload_root):
        return None
    if filename:
        path = (dest_dir / sanitize_upload_filename(filename)).resolve()
        if not _is_under(path, dest_dir):
            return None
        return path if path.exists() else None
    files = [p for p in dest_dir.iterdir() if p.is_file()]
    return files[0] if files else None
