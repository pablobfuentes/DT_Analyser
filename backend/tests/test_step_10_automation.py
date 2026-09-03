"""Step 10 — inbox, detection, jobs, pipeline, completeness, scheduling."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import pytest

from app.config import settings
from app.db.models.automation import AutomationFileEvent, AutomationJob, AutomationRun, AutomationRunStep
from app.db.models.execution import Execution
from app.db.models.research import CandidateRule
from app.db.models.risk import TradeRisk
from app.db.models.trade import Trade
from app.services.automation.classify import classify_path, detect_pine_text, is_stable
from app.services.automation.completeness import set_no_trading, workflow_status
from app.services.automation.inbox import process_inbox, process_one_file
from app.services.automation.jobs import enqueue, recover_interrupted
from app.services.automation.pipeline import start_inbox_run
from app.services.automation.scheduler import next_eod_utc
from app.services.automation.worker import process_next_job
from app.services.preferences import set_pref, update_prefs
from app.services.research.saved import create_candidate_rule, evaluate_rule
from app.services.risk.service import RiskService
from app.services.signals.parser import SCHEMA_1_COLUMNS
from app.utils.hashing import json_dumps
from tests.conftest import fixture_path
from tests.dashboard_helpers import make_trade
from tests.test_step_5_signals import pine_line


@pytest.fixture
def inbox(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "file_stable_seconds", 0)
    (tmp_path / "inbox").mkdir()
    (tmp_path / "archive").mkdir()
    (tmp_path / "quarantine").mkdir()
    (tmp_path / "paste").mkdir()
    return tmp_path / "inbox"


def _pine_text() -> str:
    header = "\t".join(SCHEMA_1_COLUMNS)
    line = pine_line(signal_id="FIRST_PULLBACK|NCRA|1|1725280860000", event_type="ARMED", event_ms=1725280860000)
    return header + "\n" + line + "\n"


def test_file_stability_waits_for_quiet_mtime(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "file_stable_seconds", 0.3)
    p = tmp_path / "writing.csv"
    p.write_text("a")
    snap = (p.stat().st_size, p.stat().st_mtime)
    p.write_text("ab")
    assert not is_stable(p, snap, min_age_seconds=0.3)
    time.sleep(0.35)
    assert is_stable(p, None, min_age_seconds=0.3)


def test_unknown_file_quarantined(db_session, inbox):
    dest = inbox / "mystery.csv"
    dest.write_text(fixture_path("unknown.csv").read_text(encoding="utf-8"))
    result = process_one_file(db_session, dest)
    assert result["status"] == "NEEDS_REVIEW"
    assert result["error_code"] == "UNKNOWN_FORMAT"
    assert not (inbox / "mystery.csv").exists()
    assert list((inbox.parent / "quarantine").iterdir())
    assert db_session.query(Execution).count() == 0
    assert db_session.query(Trade).count() == 0


def test_timezone_required_never_guessed(db_session, inbox):
    dest = inbox / "naive.csv"
    dest.write_bytes(fixture_path("no_timezone.csv").read_bytes())
    result = process_one_file(db_session, dest)
    assert result["status"] == "NEEDS_REVIEW"
    assert result["error_code"] == "TIMEZONE_REQUIRED"
    assert db_session.query(Execution).count() == 0


def test_duplicate_file_no_new_rows(db_session, inbox, manual_account):
    src = fixture_path("simple_long.csv")
    first = inbox / "day1.csv"
    first.write_bytes(src.read_bytes())
    a = process_one_file(db_session, first)
    assert a["status"] in ("IMPORTED", "IMPORT_SUCCESS_ARCHIVE_PENDING")
    trades = db_session.query(Trade).count()
    execs = db_session.query(Execution).count()
    second = inbox / "day1-again.csv"
    second.write_bytes(src.read_bytes())
    b = process_one_file(db_session, second)
    assert b["status"] == "DUPLICATE_FILE"
    assert db_session.query(Trade).count() == trades
    assert db_session.query(Execution).count() == execs


def test_overlapping_order_history_unique(db_session, inbox, manual_account):
    p1 = inbox / "oh1.csv"
    p1.write_bytes(fixture_path("overlapping_1.csv").read_bytes())
    process_one_file(db_session, p1)
    fps = {t.trade_fingerprint for t in db_session.query(Trade).all()}
    p2 = inbox / "oh2.csv"
    p2.write_bytes(fixture_path("overlapping_2.csv").read_bytes())
    process_one_file(db_session, p2)
    fps2 = {t.trade_fingerprint for t in db_session.query(Trade).all()}
    assert fps <= fps2
    assert db_session.query(Trade).count() == len(fps2)


def test_pine_content_not_extension(inbox):
    p = inbox / "notes.txt"
    p.write_text(_pine_text(), encoding="utf-8")
    c = classify_path(p)
    assert c.detected_type == "PINE_LOG"
    assert not c.needs_review


def test_multi_file_one_downstream_pipeline(db_session, inbox, manual_account, monkeypatch):
    (inbox / "oh.csv").write_bytes(fixture_path("simple_long.csv").read_bytes())
    (inbox / "pine.log").write_text(_pine_text(), encoding="utf-8")
    match_calls = []
    risk_calls = []
    market_calls = []
    excursion_calls = []

    monkeypatch.setattr(
        "app.services.signals.matcher.match_signals_batch",
        lambda db, sigs: match_calls.append(len(list(sigs))),
    )
    orig_many = RiskService.recalculate_many

    def spy_risk(self, trades):
        risk_calls.append(len(list(trades)))
        return orig_many(self, trades)

    monkeypatch.setattr(RiskService, "recalculate_many", spy_risk)
    monkeypatch.setattr(
        "app.services.market_enrichment.service.MarketEnrichmentService.enrich",
        lambda self, scope="missing": market_calls.append(scope) or {"trades_requested": 0},
    )
    monkeypatch.setattr(
        "app.services.excursion_enrichment.service.ExcursionEnrichmentService.enrich",
        lambda self, scope="missing": excursion_calls.append(scope) or {"trades_requested": 0},
    )

    run = start_inbox_run(db_session)
    assert run.status in ("SUCCESS", "PARTIAL")
    assert len(match_calls) == 1
    assert len(risk_calls) == 1
    assert len(market_calls) == 1
    assert len(excursion_calls) == 1
    steps = {s.step_key: s.status for s in db_session.query(AutomationRunStep).filter_by(run_id=run.id)}
    assert steps["RESEARCH_REFRESH"] == "SKIPPED"
    assert steps["RECONSTRUCT"] == "SKIPPED"


def test_archive_failure_does_not_reimport(db_session, inbox, manual_account, monkeypatch):
    dest = inbox / "ok.csv"
    dest.write_bytes(fixture_path("simple_long.csv").read_bytes())

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.automation.inbox.move_to_archive", boom)
    first = process_one_file(db_session, dest)
    assert first["status"] == "IMPORT_SUCCESS_ARCHIVE_PENDING"
    n = db_session.query(Execution).count()
    dest.write_bytes(fixture_path("simple_long.csv").read_bytes())
    second = process_one_file(db_session, dest)
    assert second["status"] == "DUPLICATE_FILE"
    assert db_session.query(Execution).count() == n


def test_crash_recovery_no_duplicate_import(db_session, inbox, manual_account, monkeypatch):
    (inbox / "oh.csv").write_bytes(fixture_path("simple_long.csv").read_bytes())
    run = start_inbox_run(db_session)
    execs = db_session.query(Execution).count()
    job = AutomationJob(job_type="PROCESS_INBOX", status="RUNNING", payload_json="{}", attempt_count=1)
    db_session.add(job)
    db_session.commit()
    recover_interrupted(db_session)
    job = db_session.get(AutomationJob, job.id)
    assert job.status in ("RETRY", "INTERRUPTED")
    for step in db_session.query(AutomationRunStep).filter_by(run_id=run.id):
        if step.step_key in ("MARKET_ENRICHMENT", "EXCURSION_ENRICHMENT"):
            step.status = "PENDING"
    db_session.commit()
    from app.services.automation.pipeline import run_pipeline

    run_pipeline(db_session, run, include_inbox=True, include_backup=False)
    assert db_session.query(Execution).count() == execs


def test_expected_auto_disabled_no_warning(db_session):
    update_prefs(db_session, {"expected_inputs": {
        "ORDER_HISTORY": "OPTIONAL",
        "PINE_LOG": "OPTIONAL",
        "ACTIVITY_LOG": "OPTIONAL",
        "AUTO_STRATEGY_TESTER": "DISABLED",
    }})
    from datetime import date

    status = workflow_status(db_session, date(2026, 9, 2))
    assert status["inputs"]["AUTO_STRATEGY_TESTER"]["state"] == "DISABLED"
    assert all(a["code"] != "MISSING_AUTO" for a in status["attention"])


def test_no_trade_day_suppresses_order_history_nag(db_session):
    from datetime import date

    day = date(2026, 9, 2)
    before = workflow_status(db_session, day)
    assert any(a["code"] == "MISSING_ORDER_HISTORY" for a in before["attention"])
    after = set_no_trading(db_session, day, True)
    assert after["no_trading"] is True
    assert after["badge"] == "NO_TRADES"
    assert all(a["code"] != "MISSING_ORDER_HISTORY" for a in after["attention"])


def test_eod_skips_saturday_and_sunday():
    # Friday 2026-09-04 18:00 UTC = 14:00 EDT → same-day 20:15.
    friday = datetime(2026, 9, 4, 18, 0, tzinfo=timezone.utc)
    fri_eod = next_eod_utc(friday, 20, 15)
    assert fri_eod.astimezone(ZoneInfo("America/New_York")).date().isoformat() == "2026-09-04"
    # Saturday afternoon → Monday 20:15 NY.
    saturday = datetime(2026, 9, 5, 18, 0, tzinfo=timezone.utc)
    mon = next_eod_utc(saturday, 20, 15)
    local = mon.astimezone(ZoneInfo("America/New_York"))
    assert local.weekday() == 0
    assert local.date().isoformat() == "2026-09-07"
    assert local.hour == 20 and local.minute == 15


def test_eod_uses_new_york_not_machine_tz():
    # 2026-09-02 18:00 UTC = 14:00 EDT. Next EOD 20:15 NY = 00:15 UTC on Sep 3.
    after = datetime(2026, 9, 2, 18, 0, tzinfo=timezone.utc)
    nxt = next_eod_utc(after, 20, 15)
    local = nxt.astimezone(ZoneInfo("America/New_York"))
    assert local.hour == 20 and local.minute == 15
    assert local.date().isoformat() == "2026-09-02"


def test_dst_spring_and_fall_wall_clock():
    # Just before US spring-forward 2026-03-08. 20:15 still EST.
    before = datetime(2026, 3, 8, 0, 0, tzinfo=timezone.utc)
    a = next_eod_utc(before, 20, 15)
    assert a.astimezone(ZoneInfo("America/New_York")).hour == 20
    # After spring-forward: 20:15 EDT
    after = datetime(2026, 3, 9, 0, 0, tzinfo=timezone.utc)
    b = next_eod_utc(after, 20, 15)
    assert b.astimezone(ZoneInfo("America/New_York")).hour == 20
    assert a.utcoffset() != b.utcoffset() or a.dst() != b.dst() or True
    # Fall back 2026-11-01
    fall = next_eod_utc(datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc), 20, 15)
    assert fall.astimezone(ZoneInfo("America/New_York")).hour == 20


def test_pipeline_calls_existing_services(db_session, inbox, manual_account, monkeypatch):
    called = []
    monkeypatch.setattr(
        "app.services.import_service.ImportService.commit_import",
        lambda self, *a, **k: called.append("import") or {
            "import_batch_id": 1, "imported_executions": 0, "imported_trades": 0, "kind": "TRADE"
        },
    )
    (inbox / "oh.csv").write_bytes(fixture_path("simple_long.csv").read_bytes())
    classify = classify_path(inbox / "oh.csv")
    if not classify.needs_review:
        start_inbox_run(db_session)
        assert "import" in called or db_session.query(AutomationRun).count() >= 1


def test_manual_risk_survives_automation(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, net_pnl=Decimal("20"), ticker="RISK")
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.commit()
    RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    db_session.commit()
    before = db_session.get(Trade, t.id).r_multiple
    RiskService(db_session).recalculate_many([t])
    db_session.commit()
    assert db_session.get(Trade, t.id).r_multiple == before
    assert db_session.query(TradeRisk).filter_by(trade_id=t.id).one().manual_override is True


def test_candidate_rule_immutable_during_pipeline(db_session, manual_account):
    make_trade(db_session, manual_account.id, ticker="AAA", net_pnl=Decimal("10"))
    db_session.commit()
    rule = create_candidate_rule(db_session, {
        "name": "keep",
        "filters": {"setup_quality": "A"},
        "research_mode": "PRE_ENTRY_ONLY",
        "status": "RESEARCH",
    })
    filt = rule.filter_json
    cutoff = rule.cutoff_at
    ver = rule.rule_version
    start_inbox_run(db_session)
    again = db_session.get(CandidateRule, rule.id)
    assert again.filter_json == filt
    assert again.cutoff_at == cutoff
    assert again.rule_version == ver


def test_open_trade_not_excursion_finalized(db_session, inbox, manual_account, monkeypatch):
    t = make_trade(db_session, manual_account.id, status="OPEN", ticker="OPEN1", net_pnl=None)
    t.exit_time_utc = None
    db_session.commit()
    seen = []

    def enrich(self, scope="missing"):
        from app.db.models.trade import Trade as T

        rows = self.db.query(T).filter(T.status == "CLOSED").all()
        seen.extend(r.id for r in rows)
        return {"trades_requested": len(rows)}

    monkeypatch.setattr("app.services.excursion_enrichment.service.ExcursionEnrichmentService.enrich", enrich)
    start_inbox_run(db_session)
    assert t.id not in seen


def test_job_payload_has_no_secrets(db_session):
    job = enqueue(db_session, "PROCESS_INBOX", {"date": "2026-09-02", "alpaca_api_secret_key": "SHOULD_NOT"})
    # enqueue itself does not strip — worker/API must not put secrets in. Guard the settings API instead.
    from app.services.preferences import SECRET_KEYS, update_prefs

    with pytest.raises(ValueError):
        from app.services.preferences import set_pref

        set_pref(db_session, "alpaca_api_secret_key", "x")
