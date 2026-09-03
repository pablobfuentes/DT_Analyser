from decimal import Decimal

from app.db.models.trade import Trade
from app.services.import_service import ImportService
from tests.conftest import fixture_path


def test_strategy_tester_import(db_session, strategy_account):
    service = ImportService(db_session)
    stats = service.commit_import(
        fixture_path("strategy_tester.csv"),
        "strategy_tester.csv",
        strategy_account.id,
        "tradingview_strategy",
    )
    assert stats["imported_trades"] == 2
    trades = db_session.query(Trade).order_by(Trade.id).all()
    assert trades[0].ticker == "NCRA"
    assert trades[0].quantity == Decimal("238")


def test_penny_stock_price(db_session, strategy_account):
    service = ImportService(db_session)
    service.commit_import(
        fixture_path("penny_stock.csv"),
        "penny_stock.csv",
        strategy_account.id,
        "tradingview_strategy",
    )
    trade = db_session.query(Trade).one()
    assert trade.avg_entry_price == Decimal("0.4875")
    assert trade.avg_exit_price == Decimal("0.5200")


def test_pnl_mismatch_flag(db_session, strategy_account):
    service = ImportService(db_session)
    service.commit_import(
        fixture_path("pnl_mismatch.csv"),
        "pnl_mismatch.csv",
        strategy_account.id,
        "tradingview_strategy",
    )
    trade = db_session.query(Trade).one()
    assert trade.pnl_mismatch_flag is True
    assert trade.source_reported_pnl == Decimal("50.00")
    assert trade.gross_pnl == Decimal("100.00")
