"""Local SQLite-consistent backup and restore. No naive live-file copy."""

from __future__ import annotations

import json
import logging
import shutil
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.automation import BackupRecord, utcnow
from app.db.models.journal import JournalAttachment
from app.db.models.signal import Signal
from app.db.models.trade import Trade
from app.paths import data_layout, ensure_data_layout, is_under, sqlite_file_path
from app.services.preferences import get_all, get_pref
from app.utils.hashing import sha256_file

logger = logging.getLogger(__name__)

SECRET_MANIFEST_KEYS = frozenset({
    "alpaca_api_key_id",
    "alpaca_api_secret_key",
})

NY = ZoneInfo("America/New_York")
PROTECTED_TYPES = frozenset({"PRE_RESTORE", "PRE_MIGRATION"})
VERIFIED_STATUSES = frozenset({"SUCCESS", "PARTIAL"})

# Backup IDs that must not be rotated (in-progress verify/restore).
_protected_backup_ids: set[str] = set()


def protect_backup(backup_id: str) -> None:
    _protected_backup_ids.add(backup_id)


def unprotect_backup(backup_id: str) -> None:
    _protected_backup_ids.discard(backup_id)


def _backup_root() -> Path:
    return ensure_data_layout()["backups"]


def _new_backup_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S.%fZ")


def _integrity_ok(db_path: Path) -> bool:
    conn = sqlite3.connect(str(db_path))
    try:
        row = conn.execute("PRAGMA integrity_check").fetchone()
        return bool(row and row[0] == "ok")
    finally:
        conn.close()


def _copy_db(src: Path, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    src_conn = sqlite3.connect(str(src))
    try:
        dst_conn = sqlite3.connect(str(dest))
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()


def _settings_snapshot(db: Session) -> dict:
    prefs = get_all(db)
    for k in list(prefs):
        if k in SECRET_MANIFEST_KEYS or "secret" in k.lower() or "api_key" in k.lower():
            prefs.pop(k, None)
    return {
        "analytics_timezone": settings.analytics_timezone,
        "schema_version": settings.schema_version,
        "app_version": settings.app_version,
        "preferences": prefs,
    }


def _copy_attachments(dest_dir: Path, db: Session) -> dict:
    root = data_layout()["root"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    checksums = {}
    missing = 0
    for att in db.query(JournalAttachment).all():
        src = (root / att.relative_path).resolve()
        if not is_under(src, root) or not src.exists():
            missing += 1
            continue
        target = dest_dir / att.relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        checksums[att.relative_path] = sha256_file(str(target))
    return {"count": len(checksums), "missing": missing, "checksums": checksums}


def _ny_date(dt: datetime | None) -> date | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(NY).date()


def _verify_attachment_payload(folder: Path, manifest: dict) -> dict:
    checksums = manifest.get("attachments_checksums") or {}
    missing: list[str] = []
    corrupt: list[str] = []
    att_root = folder / "attachments"
    for rel, expected in checksums.items():
        path = att_root / rel
        if not path.exists() or not path.is_file():
            missing.append(rel)
            continue
        if sha256_file(str(path)) != expected:
            corrupt.append(rel)
    db_count = int((manifest.get("counts") or {}).get("attachments") or 0)
    checksum_count = len(checksums)
    if db_count > checksum_count:
        # Manifest recorded fewer files than attachment rows — those rows have no file.
        missing.append(f"[manifest] {db_count - checksum_count} attachment row(s) without a stored file")
    ok = not missing and not corrupt
    return {
        "ok": ok,
        "missing": missing,
        "corrupt": corrupt,
        "checked": checksum_count,
        "policy": "PARTIAL_ALLOWED" if not ok else "OK",
    }


def create_backup(db: Session, backup_type: str = "MANUAL", *, src_db: Path | None = None) -> dict:
    src = src_db or sqlite_file_path()
    if src is None or not src.exists():
        raise ValueError("SQLite file path is not available for backup (in-memory?)")
    bid = _new_backup_id()
    folder = _backup_root() / bid
    folder.mkdir(parents=True, exist_ok=True)
    dest_db = folder / "trader.db"

    record = BackupRecord(
        backup_type=backup_type,
        backup_id=bid,
        path=str(folder),
        status="PENDING",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    protect_backup(bid)

    try:
        _copy_db(src, dest_db)
        if not _integrity_ok(dest_db):
            record.status = "FAILED"
            record.error_message = "SQLite integrity_check failed on backup copy"
            db.commit()
            return _record_dict(record)
        att = _copy_attachments(folder / "attachments", db)
        checksum = sha256_file(str(dest_db))
        manifest = {
            "backup_id": bid,
            "created_at": utcnow().isoformat(),
            "app_version": settings.app_version,
            "schema_version": settings.schema_version,
            "database_sha256": checksum,
            "database_size": dest_db.stat().st_size,
            "attachments_count": att["count"],
            "attachments_missing": att["missing"],
            "attachments_checksums": att["checksums"],
            "archive_included": False,
            "settings_snapshot": _settings_snapshot(db),
            "counts": {
                "trades": db.query(Trade).count(),
                "signals": db.query(Signal).count(),
                "attachments": db.query(JournalAttachment).count(),
            },
        }
        (folder / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        record.db_size = dest_db.stat().st_size
        record.checksum = checksum
        record.verified_at = utcnow()
        record.manifest_json = json.dumps(manifest)
        record.attachment_warning = 1 if att["missing"] else 0
        record.status = "PARTIAL" if att["missing"] else "SUCCESS"
        if att["missing"]:
            record.error_message = f"ATTACHMENT_WARNING: {att['missing']} missing screenshot(s)"
        db.commit()
        apply_retention(db)
        logger.info("Backup %s status=%s", bid, record.status)
        return _record_dict(record)
    except Exception as exc:
        logger.exception("Backup failed")
        record.status = "FAILED"
        record.error_message = str(exc)
        db.commit()
        return _record_dict(record)
    finally:
        unprotect_backup(bid)


def verify_backup(db: Session, backup_id: str) -> dict:
    rec = db.query(BackupRecord).filter(BackupRecord.backup_id == backup_id).first()
    if rec is None:
        rec = db.get(BackupRecord, int(backup_id)) if str(backup_id).isdigit() else None
    if rec is None:
        raise ValueError("Backup not found")
    protect_backup(rec.backup_id)
    try:
        folder = Path(rec.path)
        dest_db = folder / "trader.db"
        manifest_path = folder / "manifest.json"
        if not dest_db.exists() or not manifest_path.exists():
            rec.status = "FAILED"
            rec.error_message = "Backup files missing"
            db.commit()
            return {"ok": False, "reason": "FILES_MISSING", **_record_dict(rec)}
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        actual = sha256_file(str(dest_db))
        if actual != manifest.get("database_sha256"):
            rec.status = "FAILED"
            rec.error_message = "Checksum mismatch"
            db.commit()
            return {"ok": False, "reason": "CHECKSUM_MISMATCH", **_record_dict(rec)}
        if not _integrity_ok(dest_db):
            rec.status = "FAILED"
            rec.error_message = "Integrity check failed"
            db.commit()
            return {"ok": False, "reason": "INTEGRITY_FAILED", **_record_dict(rec)}
        att = _verify_attachment_payload(folder, manifest)
        rec.verified_at = utcnow()
        if not att["ok"]:
            rec.attachment_warning = 1
            if rec.status == "SUCCESS":
                rec.status = "PARTIAL"
            rec.error_message = rec.error_message or (
                f"ATTACHMENT_WARNING: missing={len(att['missing'])} corrupt={len(att['corrupt'])}"
            )
        db.commit()
        return {
            "ok": True,
            "reason": None,
            **_record_dict(rec),
            "manifest": manifest,
            "attachments": att,
        }
    finally:
        unprotect_backup(rec.backup_id)


def restore_preview(db: Session, backup_id: str) -> dict:
    v = verify_backup(db, backup_id)
    if not v.get("ok"):
        raise ValueError(v.get("reason") or v.get("error_message") or "Backup failed verification")
    att = v.get("attachments") or {"ok": True, "missing": [], "corrupt": []}
    return {
        "backup_id": v["backup_id"],
        "created_at": v.get("created_at"),
        "db_size": v.get("db_size"),
        "schema_version": (v.get("manifest") or {}).get("schema_version"),
        "counts": (v.get("manifest") or {}).get("counts"),
        "status": v.get("status"),
        "can_restore_db": True,
        "attachments_ok": bool(att.get("ok")),
        "attachment_warning": not bool(att.get("ok")),
        "attachment_missing": att.get("missing") or [],
        "attachment_corrupt": att.get("corrupt") or [],
        "policy": "PARTIAL_ALLOWED" if not att.get("ok") else "OK",
        "policy_note": (
            "Database restore is allowed. Missing or corrupt screenshots make the restore PARTIAL; "
            "SUCCESS requires every journal_attachment file to be present and SHA-256-matched."
        ),
    }


def _pause_automation() -> bool:
    from app.services.automation.ownership import is_automation_owner
    from app.services.automation.scheduler import stop_scheduler
    from app.services.automation.watcher import stop_watcher
    from app.services.automation.worker import stop_worker

    if not is_automation_owner():
        stop_scheduler()
        stop_watcher()
        stop_worker(drain_timeout=2)
        return False
    stop_scheduler()
    stop_watcher()
    stop_worker(drain_timeout=60)
    return True


def _resume_automation() -> None:
    from app.services.automation.ownership import is_automation_owner
    from app.services.automation.scheduler import start_scheduler
    from app.services.automation.watcher import start_watcher
    from app.services.automation.worker import start_worker

    if not is_automation_owner():
        return
    start_worker()
    start_watcher()
    start_scheduler()


def _row_counts_at(db_path: Path) -> dict:
    conn = sqlite3.connect(str(db_path))
    try:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        out = {}
        for name in ("trades", "signals", "journal_entries", "journal_attachments", "executions"):
            out[name] = int(conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]) if name in tables else 0
        return out
    finally:
        conn.close()


def _validate_restored_attachments(live_root: Path, db: Session) -> list[str]:
    missing = []
    for att in db.query(JournalAttachment).all():
        dest = (live_root / att.relative_path).resolve()
        if not is_under(dest, live_root) or not dest.exists():
            missing.append(att.relative_path)
            continue
        if att.sha256 and sha256_file(str(dest)) != att.sha256:
            missing.append(f"{att.relative_path} (sha mismatch)")
    return missing


def restore_backup(
    db: Session,
    backup_id: str,
    *,
    confirm: bool = False,
    dest_db: Path | None = None,
    manage_app_engine: bool | None = None,
) -> dict:
    if not confirm:
        raise ValueError("Restore requires explicit confirm")
    preview = restore_preview(db, backup_id)
    rec = db.query(BackupRecord).filter(BackupRecord.backup_id == preview["backup_id"]).first()
    assert rec is not None
    src_folder = Path(rec.path)
    src_db = src_folder / "trader.db"
    live = dest_db or sqlite_file_path()
    if live is None:
        raise ValueError("Cannot restore into an in-memory database")

    if manage_app_engine is None:
        # Explicit dest_db is used by tests against a private file. Live CLI/API omit dest_db.
        manage_app_engine = dest_db is None

    source_id = rec.backup_id
    protect_backup(source_id)
    from app.services.maintenance import enter_maintenance, leave_maintenance

    was_owner = False
    entered = False
    safety_id: str | None = None
    try:
        # 1–4 already done by restore_preview (manifest, SHA, integrity, attachments).
        # 5. PRE_RESTORE before any live mutation.
        safety = create_backup(db, backup_type="PRE_RESTORE", src_db=live)
        if safety.get("status") not in ("SUCCESS", "PARTIAL"):
            raise ValueError(f"PRE_RESTORE backup failed: {safety.get('error_message')}")
        safety_id = safety["backup_id"]
        protect_backup(safety_id)

        if not _integrity_ok(src_db):
            raise ValueError("Backup copy failed integrity check; current database left unchanged")

        expected_sha = (json.loads((src_folder / "manifest.json").read_text(encoding="utf-8"))).get("database_sha256")
        if sha256_file(str(src_db)) != expected_sha:
            raise ValueError("Backup SHA changed after preview; current database left unchanged")

        # 6–10. Maintenance + pause automation.
        enter_maintenance("RESTORE")
        entered = True
        was_owner = _pause_automation()

        stage_dir = live.parent / f".restore_stage_{rec.backup_id}"
        if stage_dir.exists():
            shutil.rmtree(stage_dir, ignore_errors=True)
        stage_dir.mkdir(parents=True, exist_ok=True)
        stage_db = stage_dir / "trader.db"
        _copy_db(src_db, stage_db)
        if not _integrity_ok(stage_db):
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise ValueError("Staged restore failed integrity_check; current database left unchanged")
        if sha256_file(str(stage_db)) != expected_sha:
            shutil.rmtree(stage_dir, ignore_errors=True)
            raise ValueError("Staged restore SHA mismatch; current database left unchanged")
        stage_counts = _row_counts_at(stage_db)

        att_root = src_folder / "attachments"
        if att_root.exists():
            shutil.copytree(att_root, stage_dir / "attachments", dirs_exist_ok=True)

        # 11. Dispose pooled connections before replacing the live file.
        try:
            db.commit()
            db.close()
        except Exception:
            logger.warning("Closing pre-restore session failed", exc_info=True)

        if manage_app_engine:
            from app.db.session import dispose_engine

            dispose_engine()

        # 14–15. Swap live DB, then attachments, only after PRE_RESTORE + staged validation.
        _copy_db(stage_db, live)
        live_root = data_layout()["root"]
        staged_att = stage_dir / "attachments"
        if staged_att.exists():
            for src in staged_att.rglob("*"):
                if src.is_file():
                    rel = src.relative_to(staged_att)
                    target = live_root / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, target)

        shutil.rmtree(stage_dir, ignore_errors=True)

        # 16–19. Recreate engine, migrate, integrity, counts.
        post_db = None
        if manage_app_engine:
            from app.db.migrate import run_migrations
            from app.db.session import SessionLocal, recreate_engine

            recreate_engine()
            run_migrations()
            post_db = SessionLocal()
        else:
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            from app.db.migrate import run_migrations

            eng = create_engine(f"sqlite:///{live}", connect_args={"check_same_thread": False})
            run_migrations(eng)
            post_db = sessionmaker(bind=eng)()

        try:
            if not _integrity_ok(live):
                raise ValueError("Restored database failed integrity_check")
            live_counts = {
                "trades": post_db.query(Trade).count(),
                "signals": post_db.query(Signal).count(),
                "attachments": post_db.query(JournalAttachment).count(),
            }
            missing_files = _validate_restored_attachments(data_layout()["root"], post_db)
        finally:
            if post_db is not None:
                post_db.close()
            if not manage_app_engine:
                try:
                    eng.dispose()
                except Exception:
                    pass

        status = "PARTIAL" if missing_files or preview.get("attachment_warning") else "SUCCESS"
        return {
            "status": status,
            "restored": source_id,
            "pre_restore": safety_id,
            "integrity_check": "ok",
            "counts": live_counts,
            "staged_counts": stage_counts,
            "missing_attachments": missing_files,
            "attachment_warning": bool(missing_files or preview.get("attachment_warning")),
        }
    finally:
        unprotect_backup(source_id)
        if safety_id:
            unprotect_backup(safety_id)
        if entered:
            if was_owner or manage_app_engine:
                try:
                    _resume_automation()
                except Exception:
                    logger.exception("Resume automation after restore failed")
            leave_maintenance()


def retention_keep_ids(
    rows: list[BackupRecord],
    *,
    today_ny: date | None = None,
    daily_days: int = 30,
    weekly_weeks: int = 12,
) -> set[int]:
    """Deterministic keep-set for verified backups.

    Preserve:
    - newest verified backup always
    - all eligible verified DAILY backups whose NY calendar date is in the
      most recent ``daily_days`` days (inclusive of today)
    - one verified DAILY backup per NY/calendar week (Monday–Sunday) for each
      of the ``weekly_weeks`` weeks ending at the Monday of ``today_ny``
    """
    verified = [r for r in rows if r.status in VERIFIED_STATUSES]
    if not verified:
        return set()
    verified_sorted = sorted(
        verified,
        key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    newest = verified_sorted[0]
    keep = {newest.id}
    if today_ny is None:
        today_ny = _ny_date(newest.created_at) or datetime.now(timezone.utc).astimezone(NY).date()
    daily_start = today_ny - timedelta(days=daily_days - 1)
    dailies = [r for r in verified if r.backup_type == "DAILY"]
    for r in dailies:
        d = _ny_date(r.created_at)
        if d is not None and daily_start <= d <= today_ny:
            keep.add(r.id)
    monday = today_ny - timedelta(days=today_ny.weekday())
    for i in range(weekly_weeks):
        week_mon = monday - timedelta(weeks=i)
        week_sun = week_mon + timedelta(days=6)
        in_week = []
        for r in dailies:
            d = _ny_date(r.created_at)
            if d is not None and week_mon <= d <= week_sun:
                in_week.append(r)
        if in_week:
            pick = max(in_week, key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc))
            keep.add(pick.id)
    return keep


def apply_retention(db: Session, *, today_ny: date | None = None) -> list[str]:
    daily_keep = int(get_pref(db, "backup_retain_daily", settings.backup_retain_daily) or 30)
    weekly_keep = int(get_pref(db, "backup_retain_weekly", settings.backup_retain_weekly) or 12)
    rows = (
        db.query(BackupRecord)
        .filter(BackupRecord.status.in_(tuple(VERIFIED_STATUSES)))
        .order_by(BackupRecord.created_at.desc())
        .all()
    )
    if not rows:
        return []
    keep_ids = retention_keep_ids(rows, today_ny=today_ny, daily_days=daily_keep, weekly_weeks=weekly_keep)
    deleted = []
    for r in rows:
        if r.id in keep_ids:
            continue
        if r.backup_type in PROTECTED_TYPES:
            continue
        if r.backup_id in _protected_backup_ids:
            continue
        if r.status == "PENDING":
            continue
        remaining = [x for x in rows if x.id in keep_ids or x.backup_type in PROTECTED_TYPES or x.id == r.id]
        # Never delete the only verified backup.
        others = [x for x in remaining if x.id != r.id]
        if not others:
            continue
        folder = Path(r.path)
        root = _backup_root()
        if folder.exists() and is_under(folder, root):
            shutil.rmtree(folder, ignore_errors=True)
            logger.info("Rotated backup %s", r.backup_id)
        r.status = "ROTATED"
        deleted.append(r.backup_id)
    db.commit()
    return deleted


def _record_dict(rec: BackupRecord) -> dict:
    return {
        "id": rec.id,
        "backup_id": rec.backup_id,
        "backup_type": rec.backup_type,
        "path": rec.path,
        "status": rec.status,
        "db_size": rec.db_size,
        "checksum": rec.checksum,
        "verified_at": rec.verified_at.isoformat() if rec.verified_at else None,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "error_message": rec.error_message,
        "attachment_warning": bool(rec.attachment_warning),
    }


def list_backups(db: Session) -> list[dict]:
    rows = db.query(BackupRecord).order_by(BackupRecord.created_at.desc()).limit(100).all()
    return [_record_dict(r) for r in rows]


def maybe_pre_migration_backup(db: Session) -> dict | None:
    """One recorded PRE_MIGRATION backup when a schema mutation is pending and user data exists.

    Not every startup. Not keyed only to automation_jobs being absent. Signature-deduped.
    """
    from app.db.migrate import (
        meaningful_user_data_count,
        pending_schema_mutations,
        pre_migration_signature,
    )
    from app.paths import sqlite_file_path as live_path

    pending = pending_schema_mutations(db.get_bind())
    if not pending:
        return None
    path = live_path()
    if path is None or meaningful_user_data_count(path) <= 0:
        return None
    sig = pre_migration_signature(pending)
    marker = _backup_root() / f".pre_migration_{sig}"
    if marker.exists():
        return None
    try:
        rec = create_backup(db, backup_type="PRE_MIGRATION")
        if rec.get("status") in ("SUCCESS", "PARTIAL"):
            marker.write_text("\n".join(pending), encoding="utf-8")
        return rec
    except Exception:
        logger.exception("PRE_MIGRATION backup skipped")
        return None
