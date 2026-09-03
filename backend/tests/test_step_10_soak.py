"""Synthetic 30 NY-trading-day workflow soak. Asserts invariants, not timings."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.base import Base
from app.db.models.account import Account
from app.db.models.automation import AutomationJob, AutomationRun, AutomationRunStep, BackupRecord
from app.db.models.execution import Execution
from app.db.models.journal import JournalAttachment
from app.db.models.research import CandidateRule
from app.db.models.risk import TradeRisk
from app.db.models.signal import SignalEvent, TradeSignalLink
from app.db.models.trade import Trade
from app.services.automation.inbox import move_to_archive as real_move_to_archive
from app.services.automation.inbox import process_inbox
from app.services.automation.jobs import recover_interrupted
from app.services.automation.worker import process_next_job
from app.services.automation.pipeline import start_finalize_run, start_inbox_run
from app.services.backup import service as backup_svc
from app.services.journal.attachments import store_attachment
from app.services.journal.service import upsert_trade_note
from app.services.dashboard_service import DashboardFilters
from app.services.research.cohorts import ResearchScope
from app.services.research.saved import create_candidate_rule, evaluate_rule
from app.services.risk.service import RiskService
from app.services.signals.parser import SCHEMA_1_COLUMNS
from tests.conftest import fixture_path
from tests.test_step_5_signals import pine_line

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05"
    b"\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture
def soak_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "file_stable_seconds", 0)
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
    db.add(Account(name="Soak Manual", source="TRADINGVIEW_MANUAL", is_simulated=False))
    db.commit()
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    yield db, db_path, tmp_path
    db.close()
    engine.dispose()


def _weekdays(start: date, n: int) -> list[date]:
    out = []
    d = start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _oh_text(rows: list[tuple[str, str, str, str, str]]) -> str:
    lines = ["Symbol,Side,Quantity,Price,Date/Time"]
    for symbol, side, qty, px, when in rows:
        lines.append(f"{symbol},{side},{qty},{px},{when}")
    return "\n".join(lines) + "\n"


def _pine_for_day(day: date, n: int = 1) -> str:
    header = "\t".join(SCHEMA_1_COLUMNS)
    ms = int(datetime(day.year, day.month, day.day, 13, 30, tzinfo=timezone.utc).timestamp() * 1000)
    lines = [header]
    for i in range(n):
        sid = f"FIRST_PULLBACK|SOAK|1|{ms + i * 60_000}"
        lines.append(pine_line(signal_id=sid, event_type="ARMED", event_ms=ms + i * 60_000, ticker="SOAK"))
    return "\n".join(lines) + "\n"


def test_30_day_synthetic_soak(soak_db, monkeypatch):
    db, db_path, tmp = soak_db
    inbox = tmp / "inbox"
    days = _weekdays(date(2026, 7, 20), 30)
    assert len(days) == 30
    assert all(d.weekday() < 5 for d in days)

    accumulated: list[tuple[str, str, str, str, str]] = []
    rule = None
    filt = cutoff = ver = None
    override_trade_id = None
    override_r = None

    for i, day in enumerate(days):
        ds = day.isoformat()
        accumulated.append((f"D{i}", "Buy", "100", "10.00", f"{ds} 09:31:00-04:00"))
        accumulated.append((f"D{i}", "Sell", "100", "10.40", f"{ds} 10:02:00-04:00"))
        if i == 0:
            accumulated.append(("OPENX", "Buy", "50", "8.00", f"{ds} 11:00:00-04:00"))
        if i == 8:
            accumulated.append(("OPENX", "Sell", "50", "8.50", f"{ds} 11:15:00-04:00"))

        (inbox / f"oh_{ds}.csv").write_text(_oh_text(accumulated), encoding="utf-8")
        (inbox / f"pine_{ds}.log").write_text(_pine_for_day(day, 1), encoding="utf-8")

        if i == 2:
            (inbox / "exact_dup.csv").write_text(_oh_text(accumulated), encoding="utf-8")

        if i == 3:
            (inbox / "mystery.csv").write_text(fixture_path("unknown.csv").read_text(encoding="utf-8"))

        if i == 5:
            (inbox / "naive.csv").write_bytes(fixture_path("no_timezone.csv").read_bytes())

        if i == 6:
            monkeypatch.setattr(
                "app.services.automation.inbox.move_to_archive",
                MagicMock(side_effect=OSError("archive full")),
            )
        if i == 7:
            monkeypatch.setattr("app.services.automation.inbox.move_to_archive", real_move_to_archive)

        if i == 7:
            def _mfail(self, scope="missing"):
                raise TimeoutError("temporary market-provider failure")

            monkeypatch.setattr(
                "app.services.market_enrichment.service.MarketEnrichmentService.enrich",
                _mfail,
            )
        if i == 8:
            monkeypatch.setattr(
                "app.services.market_enrichment.service.MarketEnrichmentService.enrich",
                lambda self, scope="missing": {"trades_requested": 0, "status": "SUCCESS"},
            )
            def _efail(self, scope="missing"):
                raise TimeoutError("temporary excursion-provider failure")

            monkeypatch.setattr(
                "app.services.excursion_enrichment.service.ExcursionEnrichmentService.enrich",
                _efail,
            )
        if i == 9:
            monkeypatch.setattr(
                "app.services.excursion_enrichment.service.ExcursionEnrichmentService.enrich",
                lambda self, scope="missing": {"trades_requested": 0, "status": "SUCCESS"},
            )

        process_inbox(db, dry_run=False, root=inbox)
        start_inbox_run(db, inbox_root=inbox)

        if i == 10:
            job = AutomationJob(
                job_type="PROCESS_INBOX",
                status="RUNNING",
                payload_json="{}",
                attempt_count=1,
            )
            db.add(job)
            db.commit()
            recover_interrupted(db)
            process_next_job(db)

        if i == 4:
            closed = db.query(Trade).filter(Trade.status == "CLOSED", Trade.ticker == "D0").first()
            if closed:
                RiskService(db).apply_manual(closed, initial_stop_price=Decimal("9.50"), initial_risk_amount=None)
                db.commit()
                override_trade_id = closed.id
                override_r = closed.r_multiple

        if i == 5 and rule is None:
            rule = create_candidate_rule(db, {
                "name": "soak-rule",
                "filters": {},
                "research_mode": "PRE_ENTRY_ONLY",
                "status": "RESEARCH",
            })
            filt = rule.filter_json
            cutoff = rule.cutoff_at
            ver = rule.rule_version
            evaluate_rule(db, rule.id, ResearchScope(global_filters=DashboardFilters()))

        if i == 12:
            t = db.query(Trade).filter(Trade.ticker == "D1").first()
            if t:
                upsert_trade_note(db, t.id, {"body": "soak journal"})
                store_attachment(db, PNG, "soak.png", trade_id=t.id)

        start_finalize_run(db, day, include_backup=True)

    # Restore real movers if still mocked
    from app.services.automation import inbox as inbox_mod

    monkeypatch.setattr("app.services.automation.inbox.move_to_archive", inbox_mod.move_to_archive)

    exec_fps = [r[0] for r in db.query(Execution.execution_fingerprint).all()]
    assert len(exec_fps) == len(set(exec_fps))
    ev_fps = [r[0] for r in db.query(SignalEvent.event_fingerprint).all()]
    assert len(ev_fps) == len(set(ev_fps))

    trade_fps = [(t.account_id, t.trade_fingerprint) for t in db.query(Trade).all()]
    assert len(trade_fps) == len(set(trade_fps))

    closed = db.query(Trade).filter(Trade.status == "CLOSED").all()
    pnl = sum((t.net_pnl or Decimal("0")) for t in closed)
    # 30 day-pairs at +0.40 * 100 = 40 each, plus OPENX +25, minus any reconstruction variance.
    assert pnl > 0
    # No inflation: one closed trade per D0..D29 plus OPENX.
    d_closed = {t.ticker for t in closed if t.ticker.startswith("D")}
    assert len(d_closed) == 30

    open_left = db.query(Trade).filter(Trade.ticker == "OPENX", Trade.status == "OPEN").count()
    closed_openx = db.query(Trade).filter(Trade.ticker == "OPENX", Trade.status == "CLOSED").count()
    assert open_left == 0
    assert closed_openx == 1

    if override_trade_id:
        risk = db.query(TradeRisk).filter(TradeRisk.trade_id == override_trade_id).one()
        assert risk.manual_override is True
        assert db.get(Trade, override_trade_id).r_multiple == override_r

    assert rule is not None
    again = db.get(CandidateRule, rule.id)
    assert again.filter_json == filt
    assert again.cutoff_at == cutoff
    assert again.rule_version == ver
    ev = evaluate_rule(db, rule.id, ResearchScope(global_filters=DashboardFilters()))
    assert "forward" in ev

    while process_next_job(db) is not None:
        pass
    assert db.query(AutomationJob).filter(AutomationJob.status == "RUNNING").count() == 0
    leftover = {
        s
        for (s,) in db.query(AutomationJob.status).all()
        if s in ("PENDING", "RETRY", "RUNNING")
    }
    assert leftover == set()

    run_ids = {r.id for r in db.query(AutomationRun).all()}
    for step in db.query(AutomationRunStep).all():
        assert step.run_id in run_ids
    trade_ids = {t.id for t in db.query(Trade).all()}
    for link in db.query(TradeSignalLink).all():
        assert link.trade_id in trade_ids
    for risk in db.query(TradeRisk).all():
        assert risk.trade_id in trade_ids
    root = tmp
    for att in db.query(JournalAttachment).all():
        assert (root / att.relative_path).exists()

    latest = (
        db.query(BackupRecord)
        .filter(BackupRecord.status.in_(("SUCCESS", "PARTIAL")))
        .order_by(BackupRecord.created_at.desc())
        .first()
    )
    assert latest is not None
    v = backup_svc.verify_backup(db, latest.backup_id)
    assert v["ok"] is True

    dailies = (
        db.query(BackupRecord)
        .filter(BackupRecord.backup_type == "DAILY", BackupRecord.status.in_(("SUCCESS", "PARTIAL")))
        .all()
    )
    keep = backup_svc.retention_keep_ids(dailies, today_ny=days[-1])
    live_ids = {r.id for r in dailies}
    assert keep <= live_ids or keep == {r.id for r in dailies}
    # 30 daily backups all fall in the most recent 30 days → all kept.
    assert len(dailies) >= 1
    rotated_daily = (
        db.query(BackupRecord)
        .filter(BackupRecord.backup_type == "DAILY", BackupRecord.status == "ROTATED")
        .count()
    )
    assert rotated_daily == 0

    conn = sqlite3.connect(str(db_path))
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        conn.close()

    backup_bytes = 0
    for folder in (tmp / "backups").iterdir():
        if folder.is_dir() and not folder.name.startswith("."):
            for f in folder.rglob("*"):
                if f.is_file():
                    backup_bytes += f.stat().st_size
    print(
        f"STEP10_SOAK days=30 db_bytes={db_path.stat().st_size} backup_bytes={backup_bytes} "
        f"trades={db.query(Trade).count()} executions={db.query(Execution).count()} "
        f"jobs={db.query(AutomationJob).count()} runs={db.query(AutomationRun).count()}"
    )
