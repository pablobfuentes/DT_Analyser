from decimal import Decimal

from app.importers.base_parser import read_csv
from app.importers.tradingview_manual import TradingViewManualParser
from app.services.trade_reconstruction import TradeReconstructor
from tests.conftest import fixture_path


def test_reconstruct_simple_long():
    parser = TradingViewManualParser()
    df = read_csv(fixture_path("simple_long.csv"))
    result = parser.parse(df)
    recon = TradeReconstructor().reconstruct(result.executions)
    assert len(recon.trades) == 1
    assert recon.trades[0].quantity == Decimal("100")
    assert recon.trades[0].status == "CLOSED"


def test_reconstruct_multi_entry():
    parser = TradingViewManualParser()
    df = read_csv(fixture_path("multi_entry.csv"))
    result = parser.parse(df)
    recon = TradeReconstructor().reconstruct(result.executions)
    assert len(recon.trades) == 1
    expected = (Decimal("100") * Decimal("300") + Decimal("100") * Decimal("305")) / Decimal("200")
    assert recon.trades[0].avg_entry_price == expected.quantize(Decimal("0.0001"))


def test_reconstruct_partial_exit():
    parser = TradingViewManualParser()
    df = read_csv(fixture_path("partial_exit.csv"))
    result = parser.parse(df)
    recon = TradeReconstructor().reconstruct(result.executions)
    assert len(recon.trades) == 1
    assert recon.trades[0].quantity == Decimal("200")
