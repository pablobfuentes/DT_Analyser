"""Integration tests: all three TradingView import formats."""

from decimal import Decimal

from app.db.models.execution import Execution
from app.db.models.trade import Trade
from app.importers.detector import detect_file
from app.services.import_service import ImportService
from app.services.import_validation import validate_reconstructed_trades
from tests.conftest import fixture_path

TZ = "America/New_York"


def test_strategy_tester_format_detects_and_imports(db_session, strategy_account):
    path = fixture_path("strategy_tester.csv")
    _, detections = detect_file(path)
    assert detections[0].parser_name == "tradingview_strategy"

    stats = ImportService(db_session).commit_import(
        path, "strategy_tester.csv", strategy_account.id, "tradingview_strategy", TZ
    )
    assert stats["imported_trades"] == 2
    assert stats["duplicate_trades"] == 0
    assert db_session.query(Trade).count() == 2


def test_order_history_format_detects_and_imports(db_session, manual_account):
    path = fixture_path("tv_paper_order_history_full.csv")
    _, detections = detect_file(path)
    assert detections[0].parser_name == "tradingview_manual"

    stats = ImportService(db_session).commit_import(
        path, "tv_paper_order_history_full.csv", manual_account.id, "tradingview_manual", TZ
    )
    assert stats["imported_executions"] == 72
    assert db_session.query(Execution).count() == 72


def test_activity_log_format_detects_and_imports(db_session, manual_account):
    path = fixture_path("tv_paper_activity_log.csv")
    _, detections = detect_file(path)
    assert detections[0].parser_name == "tradingview_activity_log"

    stats = ImportService(db_session).commit_import(
        path, "tv_paper_activity_log.csv", manual_account.id, "tradingview_activity_log", TZ
    )
    assert stats["imported_executions"] == 17
    assert db_session.query(Execution).count() == 17


def test_all_three_formats_sequential_no_execution_duplicates(db_session, manual_account, strategy_account):
    """Import strategy, order history, and activity log — no duplicate executions."""
    service = ImportService(db_session)

    service.commit_import(
        fixture_path("strategy_tester.csv"),
        "strategy_tester.csv",
        strategy_account.id,
        "tradingview_strategy",
        TZ,
    )

    service.commit_import(
        fixture_path("tv_paper_order_history_full.csv"),
        "tv_paper_order_history_full.csv",
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    exec_after_history = db_session.query(Execution).count()
    assert exec_after_history == 72

    stats_activity = service.commit_import(
        fixture_path("tv_paper_activity_log.csv"),
        "tv_paper_activity_log.csv",
        manual_account.id,
        "tradingview_activity_log",
        TZ,
    )
    assert stats_activity["imported_executions"] == 0
    assert stats_activity["duplicate_executions"] == 17
    assert db_session.query(Execution).count() == exec_after_history

    # Re-import all three — fully idempotent
    assert service.commit_import(
        fixture_path("strategy_tester.csv"), "strategy_tester.csv",
        strategy_account.id, "tradingview_strategy", TZ,
    )["imported_trades"] == 0

    assert service.commit_import(
        fixture_path("tv_paper_order_history_full.csv"), "tv_paper_order_history_full.csv",
        manual_account.id, "tradingview_manual", TZ,
    )["imported_executions"] == 0

    assert service.commit_import(
        fixture_path("tv_paper_activity_log.csv"), "tv_paper_activity_log.csv",
        manual_account.id, "tradingview_activity_log", TZ,
    )["imported_executions"] == 0


def test_reconstructed_trade_pnl_valid(db_session, manual_account):
    """Reconstructed LONG trades must have internally consistent gross P&L."""
    ImportService(db_session).commit_import(
        fixture_path("tv_paper_order_history_full.csv"),
        "tv_paper_order_history_full.csv",
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    closed_long = (
        db_session.query(Trade)
        .filter(Trade.status == "CLOSED", Trade.direction == "LONG", Trade.gross_pnl.isnot(None))
        .all()
    )
    assert len(closed_long) > 0
    result = validate_reconstructed_trades(closed_long, Decimal("0.01"))
    assert result.ok, result.message
