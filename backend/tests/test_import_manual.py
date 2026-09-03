from decimal import Decimal

from app.db.models.execution import Execution
from app.db.models.trade import Trade
from app.services.import_service import ImportService
from tests.conftest import fixture_path


def _import(db_session, account, filename, timezone=None):
    service = ImportService(db_session)
    return service.commit_import(
        fixture_path(filename),
        filename,
        account.id,
        "tradingview_manual",
        timezone,
    )


def test_simple_long(db_session, manual_account):
    stats = _import(db_session, manual_account, "simple_long.csv")
    assert stats["imported_executions"] == 2
    assert stats["imported_trades"] == 1
    trade = db_session.query(Trade).one()
    assert trade.ticker == "AAPL"
    assert trade.direction == "LONG"
    assert trade.quantity == Decimal("100")


def test_multi_entry(db_session, manual_account):
    stats = _import(db_session, manual_account, "multi_entry.csv")
    assert stats["imported_executions"] == 3
    assert stats["imported_trades"] == 1
    trade = db_session.query(Trade).one()
    expected_entry = (Decimal("100") * Decimal("300") + Decimal("100") * Decimal("305")) / Decimal("200")
    assert trade.avg_entry_price == expected_entry.quantize(Decimal("0.0001"))


def test_partial_exit(db_session, manual_account):
    stats = _import(db_session, manual_account, "partial_exit.csv")
    assert stats["imported_executions"] == 3
    assert stats["imported_trades"] == 1
    trade = db_session.query(Trade).one()
    assert trade.quantity == Decimal("200")


def test_alias_columns(db_session, manual_account):
    stats = _import(db_session, manual_account, "alias_columns.csv")
    assert stats["imported_executions"] == 2
    assert stats["imported_trades"] == 1


def test_malformed_mixed(db_session, manual_account):
    stats = _import(db_session, manual_account, "malformed_mixed.csv")
    assert stats["imported_executions"] == 2
    assert stats["errors"] >= 1


def test_no_timezone_requires_input(db_session, manual_account):
    import pytest
    from app.importers.exceptions import TimezoneRequiredError

    service = ImportService(db_session)
    with pytest.raises(TimezoneRequiredError):
        service.commit_import(
            fixture_path("no_timezone.csv"),
            "no_timezone.csv",
            manual_account.id,
            "tradingview_manual",
            None,
        )


def test_no_timezone_with_selection(db_session, manual_account):
    stats = _import(db_session, manual_account, "no_timezone.csv", "America/New_York")
    assert stats["imported_executions"] == 2
