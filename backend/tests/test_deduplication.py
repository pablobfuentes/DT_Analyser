from app.db.models.trade import Trade
from app.services.import_service import ImportService
from tests.conftest import fixture_path


def test_duplicate_file_import(db_session, manual_account):
    service = ImportService(db_session)
    stats1 = service.commit_import(
        fixture_path("simple_long.csv"),
        "simple_long.csv",
        manual_account.id,
        "tradingview_manual",
    )
    assert stats1["imported_trades"] == 1

    stats2 = service.commit_import(
        fixture_path("simple_long.csv"),
        "simple_long.csv",
        manual_account.id,
        "tradingview_manual",
    )
    assert stats2["duplicate_executions"] == 2
    assert stats2["imported_executions"] == 0
    assert stats2["imported_trades"] == 0
    assert db_session.query(Trade).count() == 1


def test_overlapping_import(db_session, manual_account):
    service = ImportService(db_session)
    service.commit_import(
        fixture_path("overlapping_1.csv"),
        "overlapping_1.csv",
        manual_account.id,
        "tradingview_manual",
    )
    count_after_first = db_session.query(Trade).count()

    stats2 = service.commit_import(
        fixture_path("overlapping_2.csv"),
        "overlapping_2.csv",
        manual_account.id,
        "tradingview_manual",
    )
    total_trades = db_session.query(Trade).count()
    # overlapping_1 produces 3 closed trades (200+100+75 share round trips on NCRA)
    # overlapping_2 adds one more 30-share trade
    assert total_trades == count_after_first + stats2["imported_trades"]
    assert stats2["duplicate_executions"] > 0
