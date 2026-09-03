"""Audit regressions for Steps 1 / 2 / 2.5 — parity, invariants, workflow."""

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import text

from app.db.models.execution import Execution
from app.db.models.import_batch import ImportBatch
from app.db.models.import_error import ImportError
from app.db.models.trade import Trade
from app.db.models.trade_execution import TradeExecution
from app.importers.base import NormalizedExecution
from app.importers.detector import detect_file, preview_file
from app.services.dashboard_service import DashboardFilters, get_dashboard
from app.services.deduplication import execution_fingerprint
from app.services.import_service import ImportService
from app.services.trade_reconstruction import TradeReconstructor
from app.services.trade_rebuild import TradeRebuildService
from tests.conftest import fixture_path
from tests.test_step_2_5_reconstruction import _ex, _recon

TZ = "America/New_York"
UTC = timezone.utc


def _aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _trade_snapshot(db):
    rows = []
    trades = (
        db.query(Trade)
        .order_by(Trade.ticker, Trade.entry_time_utc, Trade.direction, Trade.status, Trade.quantity)
        .all()
    )
    for t in trades:
        allocs = (
            db.query(TradeExecution)
            .filter(TradeExecution.trade_id == t.id)
            .order_by(TradeExecution.execution_id, TradeExecution.role)
            .all()
        )
        rows.append(
            {
                "ticker": t.ticker,
                "direction": t.direction,
                "status": t.status,
                "quantity": t.quantity,
                "entry": _aware(t.entry_time_utc),
                "exit": _aware(t.exit_time_utc),
                "avg_entry": t.avg_entry_price,
                "avg_exit": t.avg_exit_price,
                "gross": t.gross_pnl,
                "fees": t.fees,
                "net": t.net_pnl,
                "allocations": [
                    (a.execution_id, a.role, a.allocated_quantity) for a in allocs
                ],
            }
        )
    return rows


def _write_csv(path: Path, rows: list[tuple[str, str, str, str, str]]):
    lines = ["Symbol,Side,Quantity,Price,Date/Time"]
    for symbol, side, qty, price, ts in rows:
        lines.append(f"{symbol},{side},{qty},{price},{ts}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_preview_does_not_mutate_persistent_data(db_session):
    before_e = db_session.query(Execution).count()
    before_t = db_session.query(Trade).count()
    before_b = db_session.query(ImportBatch).count()
    result = preview_file(fixture_path("simple_long.csv"))
    assert not isinstance(result, dict) or not result.get("error")
    assert db_session.query(Execution).count() == before_e
    assert db_session.query(Trade).count() == before_t
    assert db_session.query(ImportBatch).count() == before_b


def test_overlapping_executions_1_to_5_then_1_to_8(db_session, manual_account):
    service = ImportService(db_session)
    service.commit_import(
        fixture_path("overlapping_exec_5.csv"),
        "overlapping_exec_5.csv",
        manual_account.id,
        "tradingview_manual",
    )
    assert db_session.query(Execution).count() == 5
    pnl_after_first = sum((t.net_pnl or t.gross_pnl or 0) for t in db_session.query(Trade).all())

    stats2 = service.commit_import(
        fixture_path("overlapping_exec_8.csv"),
        "overlapping_exec_8.csv",
        manual_account.id,
        "tradingview_manual",
    )
    assert stats2["duplicate_executions"] == 5
    assert stats2["imported_executions"] == 3
    assert db_session.query(Execution).count() == 8
    trades = db_session.query(Trade).all()
    assert len(trades) == 4
    assert all(t.status == "CLOSED" for t in trades)
    assert db_session.query(TradeExecution).count() >= 8
    pnl_total = sum((t.net_pnl or t.gross_pnl or 0) for t in trades)
    assert pnl_total != 0
    service.commit_import(
        fixture_path("overlapping_exec_8.csv"),
        "overlapping_exec_8.csv",
        manual_account.id,
        "tradingview_manual",
    )
    assert db_session.query(Execution).count() == 8
    assert sum((t.net_pnl or t.gross_pnl or 0) for t in db_session.query(Trade).all()) == pnl_total
    assert pnl_after_first is not None


def test_execution_fingerprint_prefers_external_id():
    a = _ex("A", "BUY", "100", "4", 10, order_id="OID-1")
    b = _ex("A", "BUY", "100", "4", 10, order_id="OID-2")
    assert execution_fingerprint(1, a) != execution_fingerprint(1, b)
    a.external_execution_id = "EXT-9"
    c = _ex("A", "SELL", "999", "1", 11, order_id="other")
    c.external_execution_id = "EXT-9"
    assert execution_fingerprint(1, a) == execution_fingerprint(1, c)


def test_execution_fingerprint_without_external_id_keeps_order_id():
    a = _ex("A", "BUY", "100", "4", 10, order_id="1001")
    a.external_execution_id = None
    b = _ex("A", "BUY", "100", "4", 10, order_id="1002")
    b.external_execution_id = None
    assert execution_fingerprint(1, a) != execution_fingerprint(1, b)


def test_identical_fills_without_ids_collapse():
    a = _ex("A", "BUY", "100", "4", 10)
    a.order_id = None
    a.external_execution_id = None
    b = _ex("A", "BUY", "100", "4", 10)
    b.order_id = None
    b.external_execution_id = None
    assert execution_fingerprint(1, a) == execution_fingerprint(1, b)


def test_same_timestamp_uses_row_order_not_order_id():
    buy = _ex("A", "BUY", "100", "4", 10, order_id="9999", row=1)
    sell = _ex("A", "SELL", "100", "4.5", 10, order_id="0001", row=2)
    r = _recon(buy, sell)
    assert len(r.errors) == 0
    closed = [t for t in r.trades if t.status == "CLOSED"]
    assert len(closed) == 1
    assert closed[0].direction == "LONG"


def test_flip_fee_allocation_proportional():
    buy = _ex("A", "BUY", "100", "4.00", 10, row=1)
    buy.fees = Decimal("0")
    sell = _ex("A", "SELL", "150", "4.50", 11, row=2)
    sell.fees = Decimal("1.50")
    r = _recon(buy, sell)
    long_t = next(t for t in r.trades if t.direction == "LONG")
    short_t = next(t for t in r.trades if t.direction == "SHORT")
    assert long_t.fees == Decimal("1.00")
    assert short_t.fees == Decimal("0.50")
    assert long_t.gross_pnl == Decimal("50.00")
    assert long_t.status == "CLOSED"


def test_allocation_sum_does_not_exceed_execution_qty():
    buy = _ex("A", "BUY", "100", "4.00", 10, row=1)
    sell = _ex("A", "SELL", "150", "4.50", 11, row=2)
    cover = _ex("A", "BUY", "50", "4.20", 12, row=3)
    r = _recon(buy, sell, cover)
    sums: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    qty_by_id = {id(buy): buy.quantity, id(sell): sell.quantity, id(cover): cover.quantity}
    for trade in r.trades:
        for alloc in trade.allocations:
            sums[id(alloc.execution)] += alloc.quantity
            assert alloc.quantity > 0
    for key, total in sums.items():
        assert total <= qty_by_id[key]
        assert total == qty_by_id[key]


def test_unknown_opening_position_warning_on_sell_first():
    r = _recon(_ex("A", "SELL", "100", "5.00", 10), _ex("A", "BUY", "100", "4.50", 11))
    assert r.errors == []
    assert any(w["error_type"] == "UNKNOWN_OPENING_POSITION" for w in r.warnings)
    assert r.trades[0].direction == "SHORT"


def test_truncated_history_resolves_when_prior_buy_arrives(db_session, manual_account, tmp_path):
    truncated = tmp_path / "trunc.csv"
    _write_csv(
        truncated,
        [
            ("CUT", "Sell", "100", "5.00", "2026-09-02 11:00:00-04:00"),
            ("CUT", "Buy", "100", "4.50", "2026-09-02 12:00:00-04:00"),
        ],
    )
    service = ImportService(db_session)
    stats = service.commit_import(truncated, "trunc.csv", manual_account.id, "tradingview_manual")
    assert stats["errors"] == 0
    shorts = db_session.query(Trade).filter(Trade.direction == "SHORT").all()
    assert len(shorts) == 1
    opening = (
        db_session.query(ImportError)
        .filter(ImportError.error_type == "UNKNOWN_OPENING_POSITION", ImportError.resolved_at.is_(None))
        .all()
    )
    assert len(opening) == 1

    full = tmp_path / "full.csv"
    _write_csv(
        full,
        [
            ("CUT", "Buy", "100", "4.00", "2026-09-02 10:00:00-04:00"),
            ("CUT", "Sell", "100", "5.00", "2026-09-02 11:00:00-04:00"),
            ("CUT", "Buy", "100", "4.50", "2026-09-02 12:00:00-04:00"),
        ],
    )
    service.commit_import(full, "full.csv", manual_account.id, "tradingview_manual")
    trades = db_session.query(Trade).filter(Trade.ticker == "CUT").order_by(Trade.entry_time_utc).all()
    assert any(t.direction == "LONG" and t.status == "CLOSED" for t in trades)
    assert not any(t.direction == "SHORT" for t in trades)
    leftover = (
        db_session.query(ImportError)
        .filter(ImportError.error_type == "UNKNOWN_OPENING_POSITION", ImportError.resolved_at.is_(None))
        .count()
    )
    assert leftover == 0


def test_rebuild_does_not_resolve_parser_errors(db_session, manual_account):
    ImportService(db_session).commit_import(
        fixture_path("simple_long.csv"),
        "simple_long.csv",
        manual_account.id,
        "tradingview_manual",
    )
    batch = db_session.query(ImportBatch).one()
    parser_err = ImportError(
        import_batch_id=batch.id,
        row_number=9,
        error_type="InvalidExecutionError",
        message="bad qty",
    )
    recon_err = ImportError(
        import_batch_id=batch.id,
        row_number=1,
        error_type="TradeReconstructionError",
        message="stale flip",
        raw_row_json='{"Symbol": "AAPL"}',
    )
    db_session.add_all([parser_err, recon_err])
    db_session.commit()

    summary = TradeRebuildService(db_session).rebuild(manual_account.id, dry_run=False)
    assert summary.errors == 0
    db_session.refresh(parser_err)
    db_session.refresh(recon_err)
    assert parser_err.resolved_at is None
    assert recon_err.resolved_at is not None


def test_open_trade_persists_then_closes(db_session, manual_account, tmp_path):
    day1 = tmp_path / "day1.csv"
    _write_csv(day1, [("OPENR", "Buy", "100", "4.00", "2026-09-01 10:00:00-04:00")])
    ImportService(db_session).commit_import(day1, "day1.csv", manual_account.id, "tradingview_manual")
    open_trades = db_session.query(Trade).filter(Trade.status == "OPEN").all()
    assert len(open_trades) == 1
    assert open_trades[0].quantity == Decimal("100")

    day2 = tmp_path / "day2.csv"
    _write_csv(
        day2,
        [
            ("OPENR", "Buy", "100", "4.00", "2026-09-01 10:00:00-04:00"),
            ("OPENR", "Sell", "100", "4.50", "2026-09-02 10:00:00-04:00"),
        ],
    )
    ImportService(db_session).commit_import(day2, "day2.csv", manual_account.id, "tradingview_manual")
    trades = db_session.query(Trade).filter(Trade.ticker == "OPENR").all()
    assert len(trades) == 1
    assert trades[0].status == "CLOSED"
    assert trades[0].gross_pnl == Decimal("50.00")


def test_incremental_import_matches_rebuild(db_session, manual_account, tmp_path):
    files = []
    day1 = tmp_path / "wf1.csv"
    _write_csv(
        day1,
        [
            ("AAA", "Buy", "100", "4.00", "2026-09-01 10:00:00-04:00"),
            ("AAA", "Sell", "100", "4.40", "2026-09-01 11:00:00-04:00"),
            ("BBB", "Buy", "50", "2.00", "2026-09-01 10:30:00-04:00"),
        ],
    )
    files.append(day1)
    day2 = tmp_path / "wf2.csv"
    _write_csv(
        day2,
        [
            ("AAA", "Buy", "100", "4.00", "2026-09-01 10:00:00-04:00"),
            ("AAA", "Sell", "100", "4.40", "2026-09-01 11:00:00-04:00"),
            ("BBB", "Buy", "50", "2.00", "2026-09-01 10:30:00-04:00"),
            ("BBB", "Sell", "50", "2.20", "2026-09-02 10:00:00-04:00"),
            ("CCC", "Sell", "80", "5.00", "2026-09-02 10:15:00-04:00"),
            ("CCC", "Buy", "80", "4.70", "2026-09-02 11:00:00-04:00"),
        ],
    )
    files.append(day2)
    day3 = tmp_path / "wf3.csv"
    _write_csv(
        day3,
        [
            ("AAA", "Buy", "100", "4.00", "2026-09-01 10:00:00-04:00"),
            ("AAA", "Sell", "100", "4.40", "2026-09-01 11:00:00-04:00"),
            ("BBB", "Buy", "50", "2.00", "2026-09-01 10:30:00-04:00"),
            ("BBB", "Sell", "50", "2.20", "2026-09-02 10:00:00-04:00"),
            ("CCC", "Sell", "80", "5.00", "2026-09-02 10:15:00-04:00"),
            ("CCC", "Buy", "80", "4.70", "2026-09-02 11:00:00-04:00"),
            ("DDD", "Buy", "100", "1.00", "2026-09-03 10:00:00-04:00"),
            ("DDD", "Sell", "150", "1.10", "2026-09-03 11:00:00-04:00"),
        ],
    )
    files.append(day3)

    service = ImportService(db_session)
    for f in files:
        service.commit_import(f, f.name, manual_account.id, "tradingview_manual")

    incremental = _trade_snapshot(db_session)
    exec_count = db_session.query(Execution).count()
    assert exec_count == 8

    TradeRebuildService(db_session).rebuild(manual_account.id, dry_run=False)
    rebuilt = _trade_snapshot(db_session)
    assert incremental == rebuilt
    assert db_session.query(Execution).count() == exec_count


def test_lookalike_order_history_not_strategy():
    _, detections = detect_file(fixture_path("lookalike_not_strategy.csv"))
    assert detections[0].parser_name == "tradingview_manual"
    strategy = next(d for d in detections if d.parser_name == "tradingview_strategy")
    assert strategy.confidence < 0.5


def test_real_order_history_not_strategy():
    _, detections = detect_file(fixture_path("tv_paper_order_history_full.csv"))
    assert detections[0].parser_name == "tradingview_manual"
    strategy = next(d for d in detections if d.parser_name == "tradingview_strategy")
    assert strategy.confidence < 0.5


def test_rebuild_dry_run_does_not_mutate(db_session, manual_account):
    ImportService(db_session).commit_import(
        fixture_path("simple_long.csv"),
        "simple_long.csv",
        manual_account.id,
        "tradingview_manual",
    )
    before = _trade_snapshot(db_session)
    ids = [t.id for t in db_session.query(Trade).all()]
    TradeRebuildService(db_session).rebuild(manual_account.id, dry_run=True)
    assert _trade_snapshot(db_session) == before
    assert [t.id for t in db_session.query(Trade).all()] == ids


def test_rebuild_does_not_delete_executions(db_session, manual_account):
    ImportService(db_session).commit_import(
        fixture_path("simple_long.csv"),
        "simple_long.csv",
        manual_account.id,
        "tradingview_manual",
    )
    exec_ids = {e.id for e in db_session.query(Execution).all()}
    raw = {e.id: e.raw_row_json for e in db_session.query(Execution).all()}
    TradeRebuildService(db_session).rebuild(manual_account.id, dry_run=False)
    after = db_session.query(Execution).all()
    assert {e.id for e in after} == exec_ids
    assert {e.id: e.raw_row_json for e in after} == raw


def test_foreign_keys_enabled(db_session):
    enabled = db_session.execute(text("PRAGMA foreign_keys")).scalar()
    assert enabled == 1


def test_filtered_equity_uses_pre_period_baseline(db_session, manual_account):
    from tests.dashboard_helpers import make_trade

    manual_account.starting_equity = Decimal("10000")
    db_session.commit()
    make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("500"),
        exit_time=datetime(2026, 8, 15, 15, 0, tzinfo=UTC),
        ticker="OLD",
    )
    make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("200"),
        exit_time=datetime(2026, 9, 15, 15, 0, tzinfo=UTC),
        ticker="NEW",
    )
    r = get_dashboard(
        db_session,
        DashboardFilters(start_date=date(2026, 9, 1), end_date=date(2026, 9, 30), account_id=manual_account.id),
    )
    assert r["equity"]["available"] is True
    assert Decimal(r["equity"]["starting_equity"]) == Decimal("10500")
    assert Decimal(r["equity"]["current_realized_equity"]) == Decimal("10700")


def test_10k_execution_benchmark(db_session, manual_account):
    import time as time_mod

    execs: list[NormalizedExecution] = []
    t0 = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    for i in range(2500):
        base = t0 + timedelta(seconds=i * 8)
        ticker = f"T{i}"
        legs = [
            ("BUY", "100", "4.0000", "0.10"),
            ("BUY", "50", "4.0500", "0.05"),
            ("SELL", "200", "4.2000", "0.20"),
            ("BUY", "50", "4.1000", "0.05"),
        ]
        for j, (side, qty, price, fee) in enumerate(legs):
            ts = base + timedelta(seconds=j)
            oid = str(i * 4 + j + 1)
            execs.append(
                NormalizedExecution(
                    ticker=ticker,
                    side=side,
                    execution_time_utc=ts,
                    execution_time_original=ts.isoformat(),
                    timezone_original="UTC",
                    quantity=Decimal(qty),
                    price=Decimal(price),
                    fees=Decimal(fee),
                    order_id=oid,
                    external_execution_id=oid,
                    raw_row={"i": i, "leg": j},
                    row_number=i * 4 + j + 1,
                )
            )

    assert len(execs) == 10000
    start = time_mod.perf_counter()
    recon = TradeReconstructor().reconstruct(execs)
    recon_s = time_mod.perf_counter() - start
    assert recon.errors == []
    assert len(recon.trades) > 0

    persist_start = time_mod.perf_counter()
    batch = ImportBatch(
        filename="bench.csv",
        file_hash="c" * 64,
        source_type="TRADINGVIEW_MANUAL",
        parser_name="tradingview_manual",
        parser_version="1",
        account_id=manual_account.id,
        status="SUCCESS",
    )
    db_session.add(batch)
    db_session.flush()
    for ex in execs:
        db_session.add(
            Execution(
                account_id=manual_account.id,
                import_batch_id=batch.id,
                external_execution_id=ex.external_execution_id,
                execution_fingerprint=execution_fingerprint(manual_account.id, ex),
                ticker=ex.ticker,
                side=ex.side,
                execution_time_utc=ex.execution_time_utc,
                execution_time_original=ex.execution_time_original,
                timezone_original=ex.timezone_original,
                quantity=ex.quantity,
                price=ex.price,
                fees=ex.fees,
                order_id=ex.order_id,
                raw_row_json="{}",
            )
        )
    db_session.commit()
    persist_s = time_mod.perf_counter() - persist_start

    rebuild_start = time_mod.perf_counter()
    summary = TradeRebuildService(db_session).rebuild(manual_account.id, dry_run=False)
    rebuild_s = time_mod.perf_counter() - rebuild_start
    assert summary.errors == 0

    dash_start = time_mod.perf_counter()
    dash = get_dashboard(db_session, DashboardFilters(account_id=manual_account.id))
    dash_s = time_mod.perf_counter() - dash_start
    assert dash["summary"]["trades"] >= 0

    print(
        f"\n10k benchmark: reconstruct={recon_s:.3f}s persist={persist_s:.3f}s "
        f"rebuild={rebuild_s:.3f}s dashboard={dash_s:.3f}s trades={summary.trades_created}"
    )
    assert recon_s < 30
    assert rebuild_s < 60
    assert dash_s < 10
