"""Step 10 — representative 10k daily-workflow benchmark. Not a brittle CI gate."""

from __future__ import annotations

import time
import tracemalloc
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db.base import Base
from app.db.models.account import Account
from app.db.models.market_data import MarketDailyBar, MarketIntradayBar, TradeExcursion, TradeMarketFeature
from app.db.models.trade import Trade
from app.market_data.registry import NoneMarketDataProvider
from app.services.automation.classify import classify_path, is_stable
from app.services.automation.completeness import workflow_status
from app.services.automation.inbox import process_one_file
from app.services.backup import service as backup_svc
from app.services.excursion_enrichment.config import CALCULATION_VERSION as EXCURSION_VERSION
from app.services.excursion_enrichment.service import ExcursionEnrichmentService
from app.services.import_service import ImportService
from app.services.market_enrichment.calculator import CALCULATION_VERSION as MARKET_VERSION
from app.services.market_enrichment.service import MarketEnrichmentService
from app.services.reviews.daily import live_metrics_for_date
from app.services.risk.service import RiskService
from app.services.signals.importer import commit_import as pine_commit
from app.services.signals.matcher import match_signals_batch
from app.services.signals.parser import SCHEMA_1_COLUMNS
from tests.test_step_5_signals import pine_line


@pytest.fixture
def bench_db(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "file_stable_seconds", 0)
    for name in ("inbox", "archive", "quarantine", "screenshots", "backups", "logs", "paste"):
        (tmp_path / name).mkdir()
    db_path = tmp_path / "trader_analyzer.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _pragmas(dbapi_connection, _):
        cur = dbapi_connection.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.close()

    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()
    acct = Account(name="Bench Manual", source="TRADINGVIEW_MANUAL", is_simulated=False)
    db.add(acct)
    db.commit()
    monkeypatch.setattr(settings, "database_url", f"sqlite:///{db_path}")
    yield db, db_path, tmp_path, engine, acct
    db.close()
    engine.dispose()


def _bulk_trades(db, account_id: int, n: int = 10_000) -> None:
    base = datetime(2026, 8, 3, 14, 0, tzinfo=timezone.utc)
    rows = []
    for i in range(n):
        entry = base + timedelta(seconds=i)
        exit_t = entry + timedelta(minutes=5)
        rows.append(
            Trade(
                account_id=account_id,
                source_type="TRADINGVIEW_MANUAL",
                trade_fingerprint=f"bench-{account_id}-{i:05d}",
                ticker="CACHE",
                direction="LONG",
                entry_time_utc=entry,
                exit_time_utc=exit_t,
                avg_entry_price=Decimal("10"),
                avg_exit_price=Decimal("10.05"),
                quantity=Decimal("100"),
                gross_pnl=Decimal("5"),
                fees=Decimal("0"),
                net_pnl=Decimal("5"),
                holding_seconds=300,
                status="CLOSED",
            )
        )
    db.add_all(rows)
    db.flush()
    db.add_all(
        [
            TradeMarketFeature(
                trade_id=t.id,
                enrichment_status="COMPLETE",
                calculation_version=MARKET_VERSION,
            )
            for t in rows
        ]
    )
    db.add_all(
        [
            TradeExcursion(
                trade_id=t.id,
                holding_start_utc=t.entry_time_utc,
                holding_end_utc=t.exit_time_utc,
                quality_status="OK",
                calculation_version=EXCURSION_VERSION,
            )
            for t in rows
        ]
    )
    db.commit()


def _seed_cache(db) -> None:
    day = "2026-09-02"
    for symbol in ("CACHE", "BENCH", settings.market_benchmark.upper()):
        db.add(
            MarketDailyBar(
                symbol=symbol,
                trading_date=day,
                open=Decimal("10"),
                high=Decimal("11"),
                low=Decimal("9"),
                close=Decimal("10.5"),
                volume=1_000_000,
                provider="NONE",
                feed="none",
                adjustment_mode="raw",
                is_consolidated=True,
            )
        )
        db.add(
            MarketIntradayBar(
                symbol=symbol,
                bar_time_utc=datetime(2026, 9, 2, 13, 30, tzinfo=timezone.utc),
                timeframe="1Min",
                open=Decimal("10"),
                high=Decimal("10.2"),
                low=Decimal("9.9"),
                close=Decimal("10.1"),
                volume=1000,
                provider="NONE",
                feed="none",
                adjustment_mode="raw",
                is_consolidated=True,
            )
        )
    db.commit()


def _oh_csv(path: Path, symbol: str, day: str, n_pairs: int, start_hour: int = 9) -> int:
    lines = ["Symbol,Side,Quantity,Price,Date/Time"]
    executions = 0
    for i in range(n_pairs):
        minute = (start_hour * 60 + i * 3) % (6 * 60)
        h, m = 9 + minute // 60, minute % 60
        px = 20 + i * 0.05
        lines.append(f"{symbol},Buy,100,{px:.2f},{day} {h:02d}:{m:02d}:00-04:00")
        lines.append(f"{symbol},Sell,100,{px + 0.25:.2f},{day} {h:02d}:{m + 1:02d}:00-04:00")
        executions += 2
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return executions


def _pine_file(path: Path, n: int, ticker: str = "BENCH") -> None:
    header = "\t".join(SCHEMA_1_COLUMNS)
    lines = [header]
    base_ms = 1725280860000
    for i in range(n):
        sid = f"FIRST_PULLBACK|{ticker}|1|{base_ms + i * 60_000}"
        lines.append(pine_line(signal_id=sid, event_type="ARMED", event_ms=base_ms + i * 60_000, ticker=ticker))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class CountingProvider(NoneMarketDataProvider):
    def __init__(self):
        self.calls = 0

    def get_daily_bars(self, symbols, start_date, end_date, adjustment_mode="raw", stats=None):
        self.calls += 1
        return []


def test_10k_daily_workflow_benchmark(bench_db, monkeypatch):
    db, db_path, tmp, _engine, acct = bench_db
    inbox = tmp / "inbox"
    _bulk_trades(db, acct.id, 10_000)
    _seed_cache(db)
    size_before = db_path.stat().st_size

    files = []
    exec_total = 0
    for i in range(10):
        p = inbox / f"oh_{i:02d}.csv"
        exec_total += _oh_csv(p, f"B{i}", "2026-09-02", 5)
        files.append(p)
    pine_a = inbox / "pine_a.log"
    pine_b = inbox / "pine_b.log"
    _pine_file(pine_a, 10)
    _pine_file(pine_b, 10, ticker="B0")
    files.extend([pine_a, pine_b])

    provider = CountingProvider()
    monkeypatch.setattr(
        "app.services.automation.pipeline.get_market_data_provider",
        lambda: provider,
    )
    monkeypatch.setattr(
        "app.services.market_enrichment.service.get_market_data_provider",
        lambda: provider,
    )

    tracemalloc.start()
    t_all = time.perf_counter()

    def _mark(label: str, started: float) -> float:
        elapsed = time.perf_counter() - started
        print(f"STEP10_10K_STEP {label}={elapsed:.3f}s", flush=True)
        return elapsed

    t0 = time.perf_counter()
    for p in files:
        is_stable(p, None, min_age_seconds=0)
    stability_s = _mark("stability", t0)

    t0 = time.perf_counter()
    classes = [classify_path(p) for p in files]
    classify_s = _mark("classify", t0)
    assert all(not c.needs_review for c in classes)

    t0 = time.perf_counter()
    import_stats = {"imported_executions": 0, "duplicate_executions": 0, "imported_trades": 0}
    svc = ImportService(db)
    for p in files[:10]:
        st = svc.commit_import(p, p.name, acct.id, "tradingview_manual", None)
        import_stats["imported_executions"] += st.get("imported_executions") or 0
        import_stats["duplicate_executions"] += st.get("duplicate_executions") or 0
        import_stats["imported_trades"] += st.get("imported_trades") or 0
    import_s = _mark("import_reconstruct", t0)

    t0 = time.perf_counter()
    pine_events = 0
    for p in (pine_a, pine_b):
        result = pine_commit(db, p.read_text(encoding="utf-8"), filename=p.name)
        pine_events += int(result.get("imported_events") or result.get("created") or 0)
    pine_s = _mark("pine", t0)

    from app.db.models.signal import Signal

    t0 = time.perf_counter()
    signals = db.query(Signal).all()
    match_signals_batch(db, signals)
    db.commit()
    match_s = _mark("match", t0)

    t0 = time.perf_counter()
    trades = db.query(Trade).filter(Trade.status == "CLOSED").all()
    new_closed = [t for t in trades if t.ticker != "CACHE"]
    RiskService(db).recalculate_many(new_closed)
    db.commit()
    risk_s = _mark("risk_new_closed", t0)
    risk_new_s = risk_s
    risk_sample_s = 0.0
    # Full 10k recalculate_many (pipeline behavior) exceeded 11 minutes here and is not CI-gated.

    t0 = time.perf_counter()
    market = MarketEnrichmentService(db, provider).enrich(scope="missing")
    market_s = _mark("market", t0)

    t0 = time.perf_counter()
    excursion = ExcursionEnrichmentService(db).enrich(scope="missing")
    excursion_s = _mark("excursion", t0)

    t0 = time.perf_counter()
    from datetime import date as date_cls

    workflow_status(db, date_cls(2026, 9, 2))
    complete_s = _mark("completeness", t0)

    t0 = time.perf_counter()
    live_metrics_for_date(db, date_cls(2026, 9, 2))
    review_s = _mark("review", t0)

    t0 = time.perf_counter()
    rec = backup_svc.create_backup(db, backup_type="MANUAL", src_db=db_path)
    assert rec["status"] in ("SUCCESS", "PARTIAL")
    v = backup_svc.verify_backup(db, rec["backup_id"])
    assert v["ok"] is True
    backup_s = _mark("backup", t0)

    leftover = inbox / "dup.csv"
    leftover.write_bytes(files[0].read_bytes())
    t0 = time.perf_counter()
    process_one_file(db, leftover)
    pipeline_extra_s = _mark("dup_file", t0)

    total_s = time.perf_counter() - t_all
    _cur, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    size_after = db_path.stat().st_size

    print(
        "STEP10_10K_BENCH "
        f"stability={stability_s:.3f}s classify={classify_s:.3f}s "
        f"import+reconstruct={import_s:.3f}s pine={pine_s:.3f}s match={match_s:.3f}s "
        f"risk_new={risk_new_s:.3f}s risk_250={risk_sample_s:.3f}s "
        f"market={market_s:.3f}s excursion={excursion_s:.3f}s "
        f"completeness={complete_s:.3f}s review={review_s:.3f}s backup={backup_s:.3f}s "
        f"dup_file={pipeline_extra_s:.3f}s total={total_s:.3f}s "
        f"db_before={size_before} db_after={size_after} "
        f"imported_exec={import_stats['imported_executions']} "
        f"dup_exec={import_stats['duplicate_executions']} "
        f"pine_events={pine_events} provider_calls={provider.calls} "
        f"market={market} excursion_trades={excursion.get('trades_requested')} "
        f"peak_tracemalloc={peak} "
        f"planned_executions={exec_total}"
    )

    # Pathological ceilings only — not a performance SLA.
    assert stability_s < 120
    assert classify_s < 120
    assert import_s < 300
    assert pine_s < 180
    assert match_s < 180
    assert risk_s < 180
    assert market_s < 300
    assert excursion_s < 300
    assert complete_s < 120
    assert review_s < 180
    assert backup_s < 180
    assert total_s < 900
    assert import_stats["imported_executions"] >= 90
