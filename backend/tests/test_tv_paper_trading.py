"""Regression tests against real TradingView Paper Trading order history exports."""

from decimal import Decimal

import pytest

from app.db.models.execution import Execution
from app.db.models.trade import Trade
from app.importers.detector import detect_file, preview_file
from app.importers.tradingview_manual import TradingViewManualParser
from app.importers.base_parser import read_csv
from app.services.import_service import ImportService
from tests.conftest import fixture_path

TZ = "America/New_York"
FULL = "tv_paper_order_history_full.csv"
PARTIAL = "tv_paper_order_history_partial.csv"


def test_tv_paper_detection():
    _, detections = detect_file(fixture_path(FULL))
    best = detections[0]
    assert best.parser_name == "tradingview_manual"
    assert best.confidence >= 0.9
    assert best.missing_fields == []


def test_tv_paper_preview_requires_timezone():
    result = preview_file(fixture_path(FULL), parser_name="tradingview_manual")
    assert result.timezone_status == "REQUIRES_USER_INPUT"


def test_tv_paper_parse_filled_only():
    parser = TradingViewManualParser()
    result = parser.parse(read_csv(fixture_path(FULL)), TZ)
    assert len(result.errors) == 0
    assert len(result.executions) == 72
    assert any("Skipped 6 non-filled" in w for w in result.warnings)


def test_tv_paper_ticker_normalization():
    parser = TradingViewManualParser()
    result = parser.parse(read_csv(fixture_path(FULL)), TZ)
    tickers = {e.ticker for e in result.executions}
    assert "PPCB" in tickers
    assert "NASDAQ:PPCB" not in tickers
    assert all(":" not in t for t in tickers)


def test_tv_paper_penny_stock_price():
    parser = TradingViewManualParser()
    result = parser.parse(read_csv(fixture_path(FULL)), TZ)
    gsun = [e for e in result.executions if e.ticker == "GSUN"]
    assert Decimal("0.3768") in {e.price for e in gsun}
    assert Decimal("0.3595") in {e.price for e in gsun}


def test_tv_paper_order_id_dedup_fingerprint():
    parser = TradingViewManualParser()
    result = parser.parse(read_csv(fixture_path(FULL)), TZ)
    order_ids = [e.external_execution_id for e in result.executions]
    assert all(oid is not None for oid in order_ids)
    assert len(order_ids) == len(set(order_ids))


def test_tv_paper_full_import(db_session, manual_account):
    service = ImportService(db_session)
    stats = service.commit_import(
        fixture_path(FULL),
        FULL,
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    assert stats["imported_executions"] == 72
    assert stats["imported_trades"] >= 20
    assert db_session.query(Execution).count() == 72
    assert stats["errors"] == 0


def test_tv_paper_duplicate_import_idempotent(db_session, manual_account):
    service = ImportService(db_session)
    stats1 = service.commit_import(
        fixture_path(FULL), FULL, manual_account.id, "tradingview_manual", TZ
    )
    exec_count = db_session.query(Execution).count()
    trade_count = db_session.query(Trade).count()

    stats2 = service.commit_import(
        fixture_path(FULL), FULL, manual_account.id, "tradingview_manual", TZ
    )
    assert stats2["imported_executions"] == 0
    assert stats2["imported_trades"] == 0
    assert stats2["duplicate_executions"] == 72
    assert db_session.query(Execution).count() == exec_count
    assert db_session.query(Trade).count() == trade_count


def test_tv_paper_overlapping_import_idempotent(db_session, manual_account):
    service = ImportService(db_session)
    stats1 = service.commit_import(
        fixture_path(PARTIAL), PARTIAL, manual_account.id, "tradingview_manual", TZ
    )
    partial_execs = db_session.query(Execution).count()
    partial_trades = db_session.query(Trade).count()
    assert stats1["imported_executions"] == 30

    stats2 = service.commit_import(
        fixture_path(FULL), FULL, manual_account.id, "tradingview_manual", TZ
    )
    assert stats2["duplicate_executions"] == 30
    assert stats2["imported_executions"] == 42
    assert db_session.query(Execution).count() == 72
    assert db_session.query(Trade).count() >= partial_trades

    # Third import of full file — fully idempotent
    stats3 = service.commit_import(
        fixture_path(FULL), FULL, manual_account.id, "tradingview_manual", TZ
    )
    assert stats3["imported_executions"] == 0
    assert stats3["duplicate_executions"] == 72
    assert db_session.query(Execution).count() == 72
