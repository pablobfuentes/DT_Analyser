"""Step 10 — SQLite backup, checksum, restore, PRE_RESTORE."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.base import Base
from app.db.models.account import Account
from app.db.models.automation import BackupRecord
from app.db.models.journal import JournalAttachment, JournalEntry
from app.db.models.trade import Trade
from app.services.backup import service as backup_svc
from app.services.journal.attachments import store_attachment
from app.services.journal.service import upsert_trade_note
from tests.dashboard_helpers import make_trade

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
    b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)
NY = ZoneInfo("America/New_York")


@pytest.fixture
def file_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    for name in ("inbox", "archive", "quarantine", "screenshots", "backups", "logs", "paste"):
        (tmp_path / name).mkdir()
    db_path = tmp_path / "trader_analyzer.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    acct = Account(name="Backup Acct", source="TRADINGVIEW_MANUAL", is_simulated=False)
    db.add(acct)
    db.commit()
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    yield db, db_path, tmp_path, engine
    db.close()
    engine.dispose()


def test_backup_during_wal_and_checksum(file_db):
    db, db_path, tmp, _engine = file_db
    make_trade(db, db.query(Account).first().id, ticker="B1", net_pnl=Decimal("12"))
    db.commit()
    rec = backup_svc.create_backup(db, backup_type="MANUAL", src_db=db_path)
    assert rec["status"] in ("SUCCESS", "PARTIAL")
    folder = Path(rec["path"])
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    assert rec["checksum"] == manifest["database_sha256"]
    assert "alpaca" not in json.dumps(manifest).lower() or "secret" not in json.dumps(manifest.get("settings_snapshot"))
    v = backup_svc.verify_backup(db, rec["backup_id"])
    assert v["ok"] is True


def test_corrupted_backup_blocked(file_db):
    db, db_path, tmp, _engine = file_db
    make_trade(db, db.query(Account).first().id, ticker="B2", net_pnl=Decimal("1"))
    db.commit()
    rec = backup_svc.create_backup(db, backup_type="MANUAL", src_db=db_path)
    dest = Path(rec["path"]) / "trader.db"
    dest.write_bytes(dest.read_bytes() + b"CORRUPT")
    v = backup_svc.verify_backup(db, rec["backup_id"])
    assert v["ok"] is False
    with pytest.raises(ValueError):
        backup_svc.restore_preview(db, rec["backup_id"])


def test_restore_roundtrip_and_pre_restore(file_db):
    db, db_path, tmp, engine = file_db
    acct = db.query(Account).first()
    t = make_trade(db, acct.id, ticker="ORIG", net_pnl=Decimal("99"))
    db.commit()
    rec = backup_svc.create_backup(db, backup_type="MANUAL", src_db=db_path)
    t.net_pnl = Decimal("0")
    db.commit()
    result = backup_svc.restore_backup(db, rec["backup_id"], confirm=True, dest_db=db_path)
    assert result["status"] == "SUCCESS"
    assert result["pre_restore"]
    db.close()
    engine.dispose()
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    fresh = sessionmaker(bind=engine)()
    restored = fresh.query(Trade).filter(Trade.ticker == "ORIG").first()
    assert restored is not None
    assert restored.net_pnl == Decimal("99")
    fresh.close()
    engine.dispose()


def test_restore_attachment_roundtrip(file_db):
    db, db_path, tmp, engine = file_db
    acct = db.query(Account).first()
    t = make_trade(db, acct.id, ticker="ATT", net_pnl=Decimal("7"))
    db.commit()
    entry = upsert_trade_note(db, t.id, {"body": "screenshot note", "tags": ["CHART"]})
    att = store_attachment(db, PNG, "chart.png", trade_id=t.id, journal_entry_id=entry.id)
    rel = att.relative_path
    digest = att.sha256
    rec = backup_svc.create_backup(db, backup_type="MANUAL", src_db=db_path)
    assert rec["status"] == "SUCCESS"
    t.net_pnl = Decimal("1")
    entry.body = "mutated after backup"
    db.commit()
    live_file = tmp / rel
    if live_file.exists():
        live_file.write_bytes(b"mutated")
    result = backup_svc.restore_backup(db, rec["backup_id"], confirm=True, dest_db=db_path)
    assert result["status"] == "SUCCESS"
    assert result.get("missing_attachments") == []
    engine.dispose()
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    fresh = sessionmaker(bind=engine)()
    trade = fresh.query(Trade).filter(Trade.ticker == "ATT").one()
    assert trade.net_pnl == Decimal("7")
    note = fresh.query(JournalEntry).filter(JournalEntry.trade_id == trade.id).one()
    assert "screenshot" in note.body
    row = fresh.query(JournalAttachment).one()
    assert row.sha256 == digest
    assert row.relative_path == rel
    assert ".." not in row.relative_path
    restored_bytes = (tmp / row.relative_path).read_bytes()
    assert restored_bytes.startswith(b"\x89PNG")
    assert restored_bytes == PNG
    fresh.close()
    engine.dispose()


def test_restore_preview_warns_when_attachment_missing(file_db):
    db, db_path, tmp, engine = file_db
    acct = db.query(Account).first()
    t = make_trade(db, acct.id, ticker="MISS", net_pnl=Decimal("3"))
    db.commit()
    upsert_trade_note(db, t.id, {"body": "has chart"})
    store_attachment(db, PNG, "gone.png", trade_id=t.id)
    rec = backup_svc.create_backup(db, backup_type="MANUAL", src_db=db_path)
    folder = Path(rec["path"])
    for img in (folder / "attachments").rglob("*"):
        if img.is_file() and img.suffix == ".png":
            img.unlink()
    live_png = next((p for p in (tmp / "screenshots").rglob("*.png") if p.is_file()), None)
    if live_png is not None:
        live_png.unlink()
    preview = backup_svc.restore_preview(db, rec["backup_id"])
    assert preview["can_restore_db"] is True
    assert preview["attachment_warning"] is True
    assert preview["attachments_ok"] is False
    assert preview["policy"] == "PARTIAL_ALLOWED"
    result = backup_svc.restore_backup(db, rec["backup_id"], confirm=True, dest_db=db_path)
    assert result["status"] == "PARTIAL"
    assert result["attachment_warning"] is True
    assert result["missing_attachments"]
    engine.dispose()
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    fresh = sessionmaker(bind=engine)()
    assert fresh.query(Trade).filter(Trade.ticker == "MISS").one().net_pnl == Decimal("3")
    # Rows may exist from the backup DB; restore must not claim the file is present.
    fresh.close()
    engine.dispose()


def _expected_retention_dates(all_days, anchor):
    daily_start = anchor - timedelta(days=29)
    keep = {anchor}
    for d in all_days:
        if daily_start <= d <= anchor:
            keep.add(d)
    monday = anchor - timedelta(days=anchor.weekday())
    for i in range(12):
        week_mon = monday - timedelta(weeks=i)
        week_sun = week_mon + timedelta(days=6)
        in_week = [d for d in all_days if week_mon <= d <= week_sun]
        if in_week:
            keep.add(max(in_week))
    return keep


def test_retention_100_daily_exact_set(file_db):
    db, db_path, tmp, _engine = file_db
    root = tmp / "backups"
    anchor = datetime(2026, 9, 2, tzinfo=NY).date()
    all_days = [anchor - timedelta(days=99 - i) for i in range(100)]
    assert len(all_days) == 100
    for i, d in enumerate(all_days):
        folder = root / f"d{i:03d}"
        folder.mkdir()
        (folder / "trader.db").write_bytes(b"x")
        created = datetime(d.year, d.month, d.day, 20, 15, tzinfo=NY).astimezone(timezone.utc)
        db.add(
            BackupRecord(
                backup_id=f"d{i:03d}",
                backup_type="DAILY",
                path=str(folder),
                status="SUCCESS",
                created_at=created,
                verified_at=created,
                checksum="abc",
            )
        )
    db.commit()
    expected = _expected_retention_dates(all_days, anchor)
    deleted = backup_svc.apply_retention(db, today_ny=anchor)
    kept = (
        db.query(BackupRecord)
        .filter(BackupRecord.status == "SUCCESS")
        .all()
    )
    kept_dates = {backup_svc._ny_date(r.created_at) for r in kept}
    assert kept_dates == expected
    assert len(kept) == len(expected)
    assert len(deleted) == 100 - len(expected)
    newest = max(kept, key=lambda r: r.created_at)
    assert backup_svc._ny_date(newest.created_at) == anchor
    rotated = db.query(BackupRecord).filter(BackupRecord.status == "ROTATED").count()
    assert rotated == len(deleted)
    # Never delete the newest or leave zero verified.
    assert db.query(BackupRecord).filter(BackupRecord.status == "SUCCESS").count() >= 1
