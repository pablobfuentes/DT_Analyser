"""Step 2.5 — SHORT reconstruction, position flips, and rebuild tests."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.models.execution import Execution
from app.db.models.trade import Trade
from app.importers.base import NormalizedExecution
from app.importers.base_parser import read_csv
from app.importers.tradingview_manual import TradingViewManualParser
from app.services.import_service import ImportService
from app.services.trade_reconstruction import TradeReconstructor
from app.services.trade_rebuild import TradeRebuildService
from app.utils.money import calculate_gross_pnl, quantize_price
from tests.conftest import fixture_path

TZ = "America/New_York"
UTC = timezone.utc


def _ex(
    ticker: str,
    side: str,
    qty: str,
    price: str,
    hour: int,
    minute: int = 0,
    second: int = 0,
    order_id: str | None = None,
    row: int = 1,
) -> NormalizedExecution:
    t = datetime(2026, 9, 1, hour, minute, second, tzinfo=UTC)
    return NormalizedExecution(
        ticker=ticker,
        side=side,
        execution_time_utc=t,
        execution_time_original=t.isoformat(),
        timezone_original="UTC",
        quantity=Decimal(qty),
        price=Decimal(price),
        fees=None,
        order_id=order_id,
        external_execution_id=order_id,
        raw_row={"side": side, "qty": qty, "price": price},
        row_number=row,
    )


def _recon(*execs: NormalizedExecution):
    return TradeReconstructor().reconstruct(list(execs))


def _closed(trades, direction=None):
    items = [t for t in trades if t.status == "CLOSED"]
    if direction:
        items = [t for t in items if t.direction == direction]
    return items


# --- Spec §28 unit scenarios ---


def test_simple_long():
    r = _recon(_ex("A", "BUY", "100", "4", 10), _ex("A", "SELL", "100", "4.5", 11))
    assert len(r.errors) == 0
    assert len(_closed(r.trades)) == 1
    t = _closed(r.trades)[0]
    assert t.direction == "LONG" and t.quantity == Decimal("100")
    assert t.gross_pnl == Decimal("50")


def test_long_multiple_entries():
    r = _recon(
        _ex("A", "BUY", "100", "4.00", 10, row=1),
        _ex("A", "BUY", "100", "4.10", 10, minute=1, row=2),
        _ex("A", "SELL", "200", "4.45", 11, row=3),
    )
    t = _closed(r.trades)[0]
    assert t.quantity == Decimal("200")
    expected_entry = quantize_price((Decimal("400") + Decimal("410")) / Decimal("200"))
    assert t.avg_entry_price == expected_entry
    assert t.gross_pnl == Decimal("80.00")


def test_long_partial_exits():
    r = _recon(
        _ex("A", "BUY", "200", "4", 10),
        _ex("A", "SELL", "50", "4.3", 11),
        _ex("A", "SELL", "150", "4.5", 12),
    )
    assert len(_closed(r.trades)) == 1
    assert _closed(r.trades)[0].quantity == Decimal("200")


def test_simple_short_explicit():
    r = _recon(
        _ex("A", "SELL_SHORT", "100", "5.00", 10),
        _ex("A", "BUY_TO_COVER", "100", "4.50", 11),
    )
    t = _closed(r.trades, "SHORT")[0]
    assert t.gross_pnl == Decimal("50.00")


def test_simple_short_generic():
    r = _recon(_ex("A", "SELL", "100", "5.00", 10), _ex("A", "BUY", "100", "4.50", 11))
    t = _closed(r.trades, "SHORT")[0]
    assert t.direction == "SHORT" and t.gross_pnl == Decimal("50.00")


def test_short_multiple_entries():
    r = _recon(
        _ex("A", "SELL", "100", "5.00", 10),
        _ex("A", "SELL", "100", "5.20", 11),
        _ex("A", "BUY", "200", "4.80", 12),
    )
    t = _closed(r.trades, "SHORT")[0]
    assert t.quantity == Decimal("200")
    assert t.avg_entry_price == quantize_price(Decimal("5.10"))
    assert t.gross_pnl == Decimal("60.00")


def test_short_partial_covers():
    r = _recon(
        _ex("A", "SELL", "200", "5.00", 10),
        _ex("A", "BUY", "50", "4.80", 11),
        _ex("A", "BUY", "150", "4.40", 12),
    )
    t = _closed(r.trades, "SHORT")[0]
    assert t.quantity == Decimal("200")
    assert t.avg_exit_price == quantize_price(Decimal("4.50"))
    assert t.gross_pnl == Decimal("100.00")


def test_long_to_short_flip():
    r = _recon(_ex("A", "BUY", "100", "4.00", 10), _ex("A", "SELL", "150", "4.50", 11))
    assert r.flips_handled == 1
    longs = _closed(r.trades, "LONG")
    opens = [t for t in r.trades if t.status == "OPEN"]
    assert len(longs) == 1 and longs[0].quantity == Decimal("100")
    assert longs[0].gross_pnl == Decimal("50.00")
    assert len(opens) == 1 and opens[0].direction == "SHORT"
    assert opens[0].quantity == Decimal("50")


def test_short_to_long_flip():
    r = _recon(_ex("A", "SELL", "100", "5.00", 10), _ex("A", "BUY", "150", "4.70", 11))
    assert r.flips_handled == 1
    shorts = _closed(r.trades, "SHORT")
    opens = [t for t in r.trades if t.status == "OPEN"]
    assert shorts[0].gross_pnl == Decimal("30.00")
    assert opens[0].direction == "LONG" and opens[0].quantity == Decimal("50")


def test_long_short_flip_then_cover():
    r = _recon(
        _ex("A", "BUY", "100", "4.00", 10),
        _ex("A", "SELL", "150", "4.50", 11),
        _ex("A", "BUY", "50", "4.20", 12),
    )
    longs = _closed(r.trades, "LONG")
    shorts = _closed(r.trades, "SHORT")
    assert longs[0].gross_pnl == Decimal("50.00")
    assert shorts[0].quantity == Decimal("50")
    assert shorts[0].gross_pnl == Decimal("15.00")


def test_short_long_flip_then_sell():
    r = _recon(
        _ex("A", "SELL", "100", "5.00", 10),
        _ex("A", "BUY", "150", "4.70", 11),
        _ex("A", "SELL", "50", "5.00", 12),
    )
    assert _closed(r.trades, "SHORT")[0].gross_pnl == Decimal("30.00")
    assert _closed(r.trades, "LONG")[0].gross_pnl == Decimal("15.00")


def test_scale_in_out_single_cycle():
    r = _recon(
        _ex("A", "BUY", "100", "4", 10, row=1),
        _ex("A", "BUY", "50", "4.1", 10, minute=1, row=2),
        _ex("A", "SELL", "50", "4.2", 10, minute=2, row=3),
        _ex("A", "BUY", "50", "4.0", 10, minute=3, row=4),
        _ex("A", "SELL", "150", "4.5", 10, minute=4, row=5),
    )
    assert len(_closed(r.trades)) == 1


def test_zero_close_then_new_position():
    r = _recon(
        _ex("A", "BUY", "100", "4", 10),
        _ex("A", "SELL", "100", "4.5", 11),
        _ex("A", "BUY", "50", "4.2", 12),
    )
    assert len(_closed(r.trades)) == 1
    assert len([t for t in r.trades if t.status == "OPEN"]) == 1


def test_flip_allocation_quantities():
    r = _recon(_ex("A", "BUY", "100", "4.00", 10), _ex("A", "SELL", "150", "4.50", 11))
    sell_allocs = [a for a in r.trades[0].allocations if a.role == "EXIT"]
    assert len(sell_allocs) == 1 and sell_allocs[0].quantity == Decimal("100")
    short_open = [a for t in r.trades if t.direction == "SHORT" for a in t.allocations if a.role == "ENTRY"]
    assert short_open[0].quantity == Decimal("50")


def test_identical_timestamp_ordering():
    r = _recon(
        _ex("A", "BUY", "100", "4", 10, order_id="1001", row=1),
        _ex("A", "SELL", "100", "4.5", 10, order_id="1002", row=2),
    )
    assert len(_closed(r.trades)) == 1


def test_decimal_precision():
    r = _recon(_ex("A", "BUY", "100", "0.4875", 10), _ex("A", "SELL", "100", "0.5000", 11))
    assert _closed(r.trades)[0].avg_entry_price == Decimal("0.4875")


def test_short_losing_trade():
    r = _recon(_ex("A", "SELL", "100", "5", 10), _ex("A", "BUY", "100", "5.50", 11))
    assert _closed(r.trades, "SHORT")[0].gross_pnl == Decimal("-50.00")


def test_open_short():
    r = _recon(_ex("A", "SELL", "100", "5.00", 10))
    assert len(r.trades) == 1 and r.trades[0].status == "OPEN"
    assert r.trades[0].direction == "SHORT"


def test_open_long():
    r = _recon(_ex("A", "BUY", "100", "4", 10))
    assert r.trades[0].status == "OPEN" and r.trades[0].direction == "LONG"


def test_unknown_side_error():
    r = _recon(_ex("A", "UNKNOWN", "100", "4", 10))
    assert len(r.errors) == 1
    assert r.errors[0]["error_type"] == "TradeReconstructionError"


def test_malformed_does_not_corrupt_other_symbol():
    r = _recon(
        _ex("BAD", "UNKNOWN", "100", "4", 10),
        _ex("GOOD", "BUY", "100", "4", 10, row=2),
        _ex("GOOD", "SELL", "100", "4.5", 11, row=3),
    )
    assert len(r.errors) == 1
    assert len(_closed(r.trades)) == 1
    assert _closed(r.trades)[0].ticker == "GOOD"


# --- Real-data regression imports ---


@pytest.mark.parametrize(
    "fixture,expected_short",
    [
        ("regression_petz_short.csv", 1),
        ("regression_aehl_short.csv", 1),
    ],
)
def test_short_reconstruction_regression(db_session, manual_account, fixture, expected_short):
    stats = ImportService(db_session).commit_import(
        fixture_path(fixture), fixture, manual_account.id, "tradingview_manual", TZ
    )
    assert stats["errors"] == 0
    shorts = db_session.query(Trade).filter(Trade.direction == "SHORT", Trade.status == "CLOSED").all()
    assert len(shorts) == expected_short


def test_petz_short_reconstruction_regression(db_session, manual_account):
    stats = ImportService(db_session).commit_import(
        fixture_path("regression_petz_short.csv"),
        "regression_petz_short.csv",
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    assert stats["errors"] == 0
    t = db_session.query(Trade).filter(Trade.ticker == "PETZ").one()
    assert t.direction == "SHORT" and t.status == "CLOSED"
    assert t.gross_pnl == Decimal("-0.03")


def test_aehl_short_reconstruction_regression(db_session, manual_account):
    test_short_reconstruction_regression(
        db_session, manual_account, "regression_aehl_short.csv", 1
    )


def test_flye_position_flip_regression(db_session, manual_account):
    stats = ImportService(db_session).commit_import(
        fixture_path("regression_flye_flip.csv"),
        "regression_flye_flip.csv",
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    assert stats["errors"] == 0
    flye = db_session.query(Trade).filter(Trade.ticker == "FLYE").all()
    assert len(flye) >= 2
    directions = {t.direction for t in flye}
    assert "LONG" in directions and "SHORT" in directions


def test_ssm_position_flip_regression(db_session, manual_account):
    stats = ImportService(db_session).commit_import(
        fixture_path("regression_ssm_flip.csv"),
        "regression_ssm_flip.csv",
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    assert stats["errors"] == 0
    ssm_trades = db_session.query(Trade).filter(Trade.ticker == "SSM").all()
    assert len(ssm_trades) >= 1


def test_rebuild_command_idempotent(db_session, manual_account):
    ImportService(db_session).commit_import(
        fixture_path("regression_flye_flip.csv"),
        "regression_flye_flip.csv",
        manual_account.id,
        "tradingview_manual",
        TZ,
    )
    count_before = db_session.query(Trade).count()
    summary = TradeRebuildService(db_session).rebuild(manual_account.id, dry_run=False)
    count_after = db_session.query(Trade).count()
    assert summary.errors == 0
    assert count_after == count_before


def test_rebuild_dry_run(db_session, manual_account):
    ImportService(db_session).commit_import(
        fixture_path("simple_long.csv"),
        "simple_long.csv",
        manual_account.id,
        "tradingview_manual",
    )
    summary = TradeRebuildService(db_session).rebuild(manual_account.id, dry_run=True)
    assert summary.dry_run is True
    assert summary.trades_created >= 1
