"""Regression tests for TradingView Paper Trading activity log exports."""

import json
from decimal import Decimal

from app.db.models.execution import Execution
from app.importers.detector import detect_file, preview_file
from app.importers.tradingview_activity_log import TradingViewActivityLogParser
from app.importers.tradingview_manual import TradingViewManualParser
from app.importers.base_parser import read_csv
from app.services.import_service import ImportService
from app.services.import_validation import compare_executions
from tests.conftest import fixture_path

TZ = "America/New_York"
ACTIVITY = "tv_paper_activity_log.csv"
ORDER_HISTORY = "tv_paper_order_history_full.csv"


def test_activity_log_detection():
    _, detections = detect_file(fixture_path(ACTIVITY))
    assert detections[0].parser_name == "tradingview_activity_log"
    assert detections[0].confidence >= 0.9


def test_activity_log_not_detected_as_order_history():
    _, detections = detect_file(fixture_path(ACTIVITY))
    manual = next(d for d in detections if d.parser_name == "tradingview_manual")
    assert manual.confidence < 0.5


def test_activity_log_preview_requires_timezone():
    result = preview_file(fixture_path(ACTIVITY), parser_name="tradingview_activity_log")
    assert result.timezone_status == "REQUIRES_USER_INPUT"


def test_activity_log_parse_executions():
    parser = TradingViewActivityLogParser()
    result = parser.parse(read_csv(fixture_path(ACTIVITY)), TZ)
    assert len(result.errors) == 0
    assert len(result.executions) == 17
    assert all(e.external_execution_id for e in result.executions)
    assert all(":" not in e.ticker for e in result.executions)


def test_activity_log_preserves_raw_columns():
    parser = TradingViewActivityLogParser()
    result = parser.parse(read_csv(fixture_path(ACTIVITY)), TZ)
    for ex in result.executions:
        assert "Time" in ex.raw_row
        assert "Text" in ex.raw_row


def test_activity_log_import(db_session, manual_account):
    service = ImportService(db_session)
    stats = service.commit_import(
        fixture_path(ACTIVITY),
        ACTIVITY,
        manual_account.id,
        "tradingview_activity_log",
        TZ,
    )
    assert stats["imported_executions"] == 17
    assert db_session.query(Execution).count() == 17


def test_activity_log_duplicate_import_idempotent(db_session, manual_account):
    service = ImportService(db_session)
    service.commit_import(
        fixture_path(ACTIVITY), ACTIVITY, manual_account.id, "tradingview_activity_log", TZ
    )
    stats2 = service.commit_import(
        fixture_path(ACTIVITY), ACTIVITY, manual_account.id, "tradingview_activity_log", TZ
    )
    assert stats2["imported_executions"] == 0
    assert stats2["duplicate_executions"] == 17
    assert db_session.query(Execution).count() == 17


def test_order_history_then_activity_log_no_duplicates(db_session, manual_account):
    """Overlapping exports: order history first, then activity log subset."""
    service = ImportService(db_session)
    service.commit_import(
        fixture_path(ORDER_HISTORY),
        ORDER_HISTORY,
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    assert db_session.query(Execution).count() == 72

    stats2 = service.commit_import(
        fixture_path(ACTIVITY),
        ACTIVITY,
        manual_account.id,
        "tradingview_activity_log",
        TZ,
    )
    assert stats2["imported_executions"] == 0
    assert stats2["duplicate_executions"] == 17
    assert db_session.query(Execution).count() == 72


def test_activity_log_then_order_history_no_duplicates(db_session, manual_account):
    """Reverse order: activity log first, then full order history."""
    service = ImportService(db_session)
    service.commit_import(
        fixture_path(ACTIVITY), ACTIVITY, manual_account.id, "tradingview_activity_log", TZ
    )
    assert db_session.query(Execution).count() == 17

    stats2 = service.commit_import(
        fixture_path(ORDER_HISTORY),
        ORDER_HISTORY,
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    assert stats2["duplicate_executions"] == 17
    assert stats2["imported_executions"] == 55
    assert db_session.query(Execution).count() == 72


def test_cross_validate_activity_vs_order_history(db_session, manual_account):
    """Activity log executions must match order history for shared Order IDs."""
    service = ImportService(db_session)
    service.commit_import(
        fixture_path(ORDER_HISTORY), ORDER_HISTORY, manual_account.id, "tradingview_manual", TZ
    )
    history_execs = db_session.query(Execution).all()

    service.commit_import(
        fixture_path(ACTIVITY), ACTIVITY, manual_account.id, "tradingview_activity_log", TZ
    )
    activity_execs = (
        db_session.query(Execution)
        .filter(Execution.external_execution_id.in_([e.external_execution_id for e in history_execs if e.external_execution_id]))
        .all()
    )
    # Only the 17 activity-log order IDs
    activity_ids = {e.external_execution_id for e in TradingViewActivityLogParser().parse(read_csv(fixture_path(ACTIVITY)), TZ).executions}
    ref = [e for e in history_execs if e.external_execution_id in activity_ids]
    cand = [e for e in activity_execs if e.external_execution_id in activity_ids]

    mismatches = compare_executions(ref, cand)
    assert mismatches == []
