"""Tests for clearing all trading data."""

from app.db.models.execution import Execution
from app.db.models.import_batch import ImportBatch
from app.db.models.trade import Trade
from app.services.data_reset import clear_all_trading_data
from app.services.import_service import ImportService
from tests.conftest import fixture_path

TZ = "America/New_York"


def test_clear_all_trading_data(db_session, manual_account):
    service = ImportService(db_session)
    service.commit_import(
        fixture_path("tv_paper_activity_log.csv"),
        "tv_paper_activity_log.csv",
        manual_account.id,
        "tradingview_activity_log",
        TZ,
    )
    assert db_session.query(Execution).count() > 0
    assert db_session.query(ImportBatch).count() > 0

    result = clear_all_trading_data(db_session)
    assert result["executions"] > 0
    assert db_session.query(Trade).count() == 0
    assert db_session.query(Execution).count() == 0
    assert db_session.query(ImportBatch).count() == 0
    # Accounts preserved
    assert manual_account.id is not None
