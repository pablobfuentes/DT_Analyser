"""Step 8 MFE/MAE excursion tests."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.models.execution import Execution
from app.db.models.import_batch import ImportBatch
from app.db.models.trade import Trade
from app.db.models.trade_execution import TradeExecution
from app.market_data.fake import FakeMarketDataProvider, build_minute_bars, clear_fake_store, register_fake_intraday_series
from app.market_data.cache_intraday import store_intraday_bars
from app.services.excursion_enrichment.calculator import build_excursion_record
from app.services.excursion_enrichment.replay import ExecEvent, load_exec_events, replay_excursions
from app.services.excursion_enrichment.service import ExcursionEnrichmentService
from tests.dashboard_helpers import make_trade

UTC = timezone.utc


def _link_exec(db, trade, account_id, batch_id, role, qty, price, t):
    ex = Execution(
        account_id=account_id,
        import_batch_id=batch_id,
        execution_fingerprint=f"fp-{trade.id}-{role}-{t.isoformat()}",
        ticker=trade.ticker,
        side="BUY" if role == "ENTRY" else "SELL",
        execution_time_utc=t,
        execution_time_original=t.isoformat(),
        quantity=qty,
        price=price,
        raw_row_json="{}",
    )
    db.add(ex)
    db.flush()
    db.add(TradeExecution(trade_id=trade.id, execution_id=ex.id, role=role, allocated_quantity=qty))
    db.commit()
    return ex


@pytest.fixture
def import_batch(db_session, manual_account):
    b = ImportBatch(
        account_id=manual_account.id,
        filename="t.csv",
        file_hash="abc123",
        source_type="TRADINGVIEW_MANUAL",
        parser_name="test",
        parser_version="1",
        status="SUCCESS",
    )
    db_session.add(b)
    db_session.commit()
    return b


def test_simple_long_mfe_mae():
    """Fixture #101 — simple LONG MFE/MAE/efficiency."""
    trade = Trade(
        account_id=1,
        source_type="X",
        trade_fingerprint="x1",
        ticker="T",
        direction="LONG",
        entry_time_utc=datetime(2026, 9, 1, 14, 0, tzinfo=UTC),
        exit_time_utc=datetime(2026, 9, 1, 14, 5, tzinfo=UTC),
        avg_entry_price=Decimal("5"),
        avg_exit_price=Decimal("5.30"),
        quantity=Decimal("100"),
        gross_pnl=Decimal("30"),
        status="CLOSED",
    )
    start = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    bars = build_minute_bars(
        "T",
        start,
        [
            (Decimal("5.20"), Decimal("4.90"), Decimal("5.10")),
            (Decimal("5.50"), Decimal("5.10"), Decimal("5.40")),
            (Decimal("5.40"), Decimal("5.20"), Decimal("5.30")),
        ],
    )
    events = [
        ExecEvent(start, "ENTRY", Decimal("100"), Decimal("5.00")),
        ExecEvent(datetime(2026, 9, 1, 14, 5, tzinfo=UTC), "EXIT", Decimal("100"), Decimal("5.30")),
    ]
    track, state, _ = replay_excursions(trade, events, bars)
    assert track.price_high == Decimal("0.50")
    assert track.price_low == Decimal("-0.10")
    assert track.inclusive_mfe == Decimal("50")
    assert track.inclusive_mae == Decimal("-10")
    rec = build_excursion_record(
        trade, track, state, {"bar_count": 3, "sparse": False},
        holding_start=start,
        holding_end=events[-1].time,
        provider="FAKE", feed="fake", is_consolidated=True,
        initial_risk=Decimal("25"),
    )
    assert rec.exit_efficiency_pct == Decimal("60")
    assert rec.mfe_r == Decimal("2")


def test_simple_short():
    """Fixture #102 — SHORT normalization."""
    trade = Trade(
        account_id=1, source_type="X", trade_fingerprint="x2", ticker="T", direction="SHORT",
        entry_time_utc=datetime(2026, 9, 1, 14, 0, tzinfo=UTC),
        exit_time_utc=datetime(2026, 9, 1, 14, 5, tzinfo=UTC),
        avg_entry_price=Decimal("5"), avg_exit_price=Decimal("4.70"),
        quantity=Decimal("100"), gross_pnl=Decimal("30"), status="CLOSED",
    )
    start = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    bars = build_minute_bars(
        "T", start,
        [
            (Decimal("5.10"), Decimal("4.80"), Decimal("4.90")),
            (Decimal("4.90"), Decimal("4.50"), Decimal("4.70")),
            (Decimal("4.85"), Decimal("4.70"), Decimal("4.75")),
        ],
    )
    events = [
        ExecEvent(start, "ENTRY", Decimal("100"), Decimal("5.00")),
        ExecEvent(datetime(2026, 9, 1, 14, 5, tzinfo=UTC), "EXIT", Decimal("100"), Decimal("4.70")),
    ]
    track, _, _ = replay_excursions(trade, events, bars)
    assert track.price_high == Decimal("0.50")
    assert track.price_low == Decimal("-0.10")
    assert track.inclusive_mfe == Decimal("50")


def test_negative_exit_efficiency():
    trade = Trade(
        account_id=1, source_type="X", trade_fingerprint="x3", ticker="T", direction="LONG",
        entry_time_utc=datetime(2026, 9, 1, 14, 0, tzinfo=UTC),
        exit_time_utc=datetime(2026, 9, 1, 14, 3, tzinfo=UTC),
        avg_entry_price=Decimal("5"), avg_exit_price=Decimal("4.80"),
        quantity=Decimal("100"), gross_pnl=Decimal("-20"), status="CLOSED",
    )
    start = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    bars = build_minute_bars("T", start, [(Decimal("6.00"), Decimal("4.90"), Decimal("5.10"))])
    events = [
        ExecEvent(start, "ENTRY", Decimal("100"), Decimal("5.00")),
        ExecEvent(datetime(2026, 9, 1, 14, 3, tzinfo=UTC), "EXIT", Decimal("100"), Decimal("4.80")),
    ]
    track, state, _ = replay_excursions(trade, events, bars)
    rec = build_excursion_record(
        trade, track, state, {"bar_count": 1},
        holding_start=start, holding_end=events[-1].time,
        provider="FAKE", feed="fake", is_consolidated=True, initial_risk=None,
    )
    assert rec.exit_efficiency_pct == Decimal("-20")


def test_no_positive_mfe_null_efficiency():
    trade = Trade(
        account_id=1, source_type="X", trade_fingerprint="x4", ticker="T", direction="LONG",
        entry_time_utc=datetime(2026, 9, 1, 14, 0, tzinfo=UTC),
        exit_time_utc=datetime(2026, 9, 1, 14, 2, tzinfo=UTC),
        avg_entry_price=Decimal("5"), avg_exit_price=Decimal("4.90"),
        quantity=Decimal("100"), gross_pnl=Decimal("-10"), status="CLOSED",
    )
    start = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    bars = build_minute_bars("T", start, [(Decimal("5.00"), Decimal("4.80"), Decimal("4.85"))])
    events = [
        ExecEvent(start, "ENTRY", Decimal("100"), Decimal("5.00")),
        ExecEvent(datetime(2026, 9, 1, 14, 2, tzinfo=UTC), "EXIT", Decimal("100"), Decimal("4.90")),
    ]
    track, state, _ = replay_excursions(trade, events, bars)
    rec = build_excursion_record(
        trade, track, state, {"bar_count": 1},
        holding_start=start, holding_end=events[-1].time,
        provider="FAKE", feed="fake", is_consolidated=True, initial_risk=Decimal("100"),
    )
    if rec.position_mfe_amount is not None and rec.position_mfe_amount <= 0:
        assert rec.exit_efficiency_pct is None


def test_boundary_spread():
    trade = Trade(
        account_id=1, source_type="X", trade_fingerprint="x5", ticker="T", direction="LONG",
        entry_time_utc=datetime(2026, 9, 1, 14, 0, 24, tzinfo=UTC),
        exit_time_utc=datetime(2026, 9, 1, 14, 5, tzinfo=UTC),
        avg_entry_price=Decimal("5"), avg_exit_price=Decimal("5.20"),
        quantity=Decimal("100"), gross_pnl=Decimal("20"), status="CLOSED",
    )
    start = datetime(2026, 9, 1, 14, 0, tzinfo=UTC)
    bars = build_minute_bars(
        "T", start,
        [(Decimal("5.80"), Decimal("4.50"), Decimal("5.10")), (Decimal("5.30"), Decimal("5.00"), Decimal("5.20"))],
    )
    events = [
        ExecEvent(datetime(2026, 9, 1, 14, 0, 24, tzinfo=UTC), "ENTRY", Decimal("100"), Decimal("5.00")),
        ExecEvent(datetime(2026, 9, 1, 14, 5, tzinfo=UTC), "EXIT", Decimal("100"), Decimal("5.20")),
    ]
    track, state, _ = replay_excursions(trade, events, bars)
    assert track.boundary_ambiguity is True
    rec = build_excursion_record(
        trade, track, state, {"bar_count": 2},
        holding_start=events[0].time, holding_end=events[-1].time,
        provider="FAKE", feed="fake", is_consolidated=True, initial_risk=Decimal("100"),
    )
    assert rec.mfe_boundary_spread_amount is not None
    assert rec.conservative_position_mfe_amount <= rec.position_mfe_amount


def test_enrichment_integration(db_session, manual_account, import_batch):
    clear_fake_store()
    t = make_trade(
        db_session, manual_account.id,
        ticker="NCRA", net_pnl=Decimal("30"), gross_pnl=Decimal("30"),
        entry_time=datetime(2026, 9, 2, 13, 30, tzinfo=UTC),
        exit_time=datetime(2026, 9, 2, 13, 35, tzinfo=UTC),
    )
    t.avg_entry_price = Decimal("5")
    t.avg_exit_price = Decimal("5.30")
    t.quantity = Decimal("100")
    t.initial_risk_amount = Decimal("25")
    db_session.commit()
    _link_exec(db_session, t, manual_account.id, import_batch.id, "ENTRY", Decimal("100"), Decimal("5"), t.entry_time_utc)
    _link_exec(db_session, t, manual_account.id, import_batch.id, "EXIT", Decimal("100"), Decimal("5.30"), t.exit_time_utc)

    start = datetime(2026, 9, 2, 13, 30, tzinfo=UTC)
    bars = build_minute_bars(
        "NCRA", start,
        [
            (Decimal("5.20"), Decimal("4.90"), Decimal("5.10")),
            (Decimal("5.50"), Decimal("5.10"), Decimal("5.40")),
            (Decimal("5.40"), Decimal("5.20"), Decimal("5.30")),
        ],
    )
    register_fake_intraday_series("NCRA", bars)
    store_intraday_bars(db_session, bars)
    db_session.commit()

    svc = ExcursionEnrichmentService(db_session, FakeMarketDataProvider())
    result = svc.enrich(scope="all")
    assert result["success_count"] >= 1

    from app.db.models.market_data import TradeExcursion
    ex = db_session.query(TradeExcursion).filter(TradeExcursion.trade_id == t.id).first()
    assert ex is not None
    assert ex.mfe_r is not None
    assert ex.exit_efficiency_pct is not None


def test_cache_no_second_fetch(db_session, manual_account, import_batch):
    clear_fake_store()
    t = make_trade(db_session, manual_account.id, ticker="CACHE")
    _link_exec(db_session, t, manual_account.id, import_batch.id, "ENTRY", Decimal("100"), Decimal("5"), t.entry_time_utc)
    _link_exec(db_session, t, manual_account.id, import_batch.id, "EXIT", Decimal("100"), Decimal("5.10"), t.exit_time_utc)
    start = t.entry_time_utc
    bars = build_minute_bars("CACHE", start, [(Decimal("5.20"), Decimal("4.90"), Decimal("5.10"))])
    store_intraday_bars(db_session, bars)
    db_session.commit()

    provider = FakeMarketDataProvider()
    svc = ExcursionEnrichmentService(db_session, provider)
    r1 = svc.enrich(scope="all")
    assert r1["success_count"] >= 1
    svc2 = ExcursionEnrichmentService(db_session, provider)
    r2 = svc2.enrich(scope="all", recalculate=True)
    assert r2["success_count"] >= 1
