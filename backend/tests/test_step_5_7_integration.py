"""Step 5 ↔ Step 7 integration: signal link drives RiskService."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.db.models.risk import TradeRisk
from app.db.models.signal import Signal
from app.services.reports.filters import TradeFilterSet
from app.services.reports.service import get_reports
from app.services.risk.service import RiskService
from app.services.signals.importer import commit_import
from app.services.signals.matcher import confirm_link, unlink
from tests.dashboard_helpers import make_trade
from tests.test_step_5_signals import pine_line


def test_confirmed_link_planned_vs_actual(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|1000"
    commit_import(
        db_session,
        pine_line(signal_id=sid, event_type="ENTRY", event_ms=1000, planned_entry="5.00", planned_stop="4.80", shares="500", allowed="100"),
    )
    t = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("40"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.05")
    t.quantity = Decimal("400")
    t.direction = "LONG"
    db_session.commit()
    sig = db_session.query(Signal).one()
    confirm_link(db_session, sig, t)
    db_session.commit()
    row = db_session.query(TradeRisk).filter(TradeRisk.trade_id == t.id).one()
    assert row.planned_risk_amount == Decimal("100") or row.planned_risk_amount == Decimal("100.000000")
    assert row.allowed_risk == Decimal("100")
    assert row.actual_initial_risk_amount == Decimal("100.0000") or row.actual_initial_risk_amount == Decimal("100")
    assert row.risk_source == "PINE_SIGNAL"
    assert t.r_multiple is not None
    # R denominator is actual 100, not allowed_risk-as-substitute (same number here by design)


def test_planned_not_equal_actual(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|2000"
    commit_import(
        db_session,
        pine_line(signal_id=sid, event_type="ENTRY", event_ms=2000, planned_entry="5.00", planned_stop="4.80", shares="500", allowed="100"),
    )
    t = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("50"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.10")
    t.quantity = Decimal("500")
    db_session.commit()
    confirm_link(db_session, db_session.query(Signal).one(), t)
    db_session.commit()
    row = db_session.query(TradeRisk).one()
    assert row.planned_risk_amount == Decimal("100")
    assert row.actual_initial_risk_amount == Decimal("150.0000")
    assert row.allowed_risk == Decimal("100")
    assert row.actual_initial_risk_amount != row.allowed_risk or row.planned_risk_amount != row.actual_initial_risk_amount


def test_short_pine_risk_orientation(db_session, manual_account):
    sid = "OPENING_FADE|XYZ|1|3000"
    commit_import(
        db_session,
        pine_line(
            signal_id=sid,
            event_type="ENTRY",
            event_ms=3000,
            ticker="XYZ",
            strategy="OPENING_FADE",
            direction="SHORT",
            planned_entry="10.00",
            planned_stop="10.20",
            shares="100",
            allowed="20",
        ),
    )
    t = make_trade(db_session, manual_account.id, ticker="XYZ", direction="SHORT", net_pnl=Decimal("15"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("10.00")
    t.quantity = Decimal("100")
    db_session.commit()
    confirm_link(db_session, db_session.query(Signal).one(), t)
    db_session.commit()
    row = db_session.query(TradeRisk).one()
    assert row.actual_risk_per_share == Decimal("0.20")
    assert row.actual_initial_risk_amount == Decimal("20.0000")
    assert row.risk_source == "PINE_SIGNAL"


def test_later_entry_recalculates_without_relink(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|4000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ARMED", event_ms=4000, planned_stop=""))
    t = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("10"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("100")
    db_session.commit()
    confirm_link(db_session, db_session.query(Signal).one(), t)
    db_session.commit()
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=4100, planned_stop="4.80"))
    db_session.refresh(t)
    row = db_session.query(TradeRisk).filter(TradeRisk.trade_id == t.id).one()
    assert row.initial_stop_price == Decimal("4.80")
    assert row.risk_source == "PINE_SIGNAL"


def test_manual_override_survives_signal_reprocess(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|5000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=5000, planned_stop="4.80"))
    t = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("10"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("100")
    db_session.commit()
    confirm_link(db_session, db_session.query(Signal).one(), t)
    db_session.commit()
    RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.70"), initial_risk_amount=Decimal("40"))
    db_session.commit()
    commit_import(db_session, pine_line(signal_id=sid, event_type="EXIT", event_ms=5200, exit_reason="STOP LOSS"))
    db_session.refresh(t)
    assert t.risk_source == "MANUAL"
    assert t.initial_risk_amount == Decimal("40.0000") or t.initial_risk_amount == Decimal("40")


def test_unlink_clears_pine_authority(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|6000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=6000, planned_stop="4.80"))
    t = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("10"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("100")
    db_session.commit()
    sig = db_session.query(Signal).one()
    confirm_link(db_session, sig, t)
    db_session.commit()
    unlink(db_session, sig, t)
    db_session.commit()
    db_session.refresh(t)
    assert t.risk_source != "PINE_SIGNAL"
    row = db_session.query(TradeRisk).filter(TradeRisk.trade_id == t.id).one()
    assert row.risk_source != "PINE_SIGNAL"
    assert row.planned_stop_price == Decimal("4.80")


def test_old_version_risk_not_changed_by_new_version(db_session, manual_account):
    old_id = "FIRST_PULLBACK|NCRA|1|7000"
    new_id = "FIRST_PULLBACK|NCRA|1|8000"
    commit_import(db_session, pine_line(signal_id=old_id, event_type="ENTRY", event_ms=7000, planned_stop="4.80", version="v0.3.3"))
    t = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("10"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("100")
    db_session.commit()
    old = db_session.query(Signal).filter(Signal.signal_id == old_id).one()
    confirm_link(db_session, old, t)
    db_session.commit()
    stop_before = db_session.query(TradeRisk).one().initial_stop_price
    commit_import(db_session, pine_line(signal_id=new_id, event_type="ENTRY", event_ms=8000, planned_stop="3.00", version="v0.4.0"))
    db_session.commit()
    assert db_session.query(TradeRisk).filter(TradeRisk.trade_id == t.id).one().initial_stop_price == stop_before


def test_strategy_average_r_and_coverage_not_conflated(db_session, manual_account):
    # A+: +2R, +1R  → avg 1.5; A: -1R, +0.5R → avg -0.25
    specs = [
        ("A1", "A+", Decimal("40"), Decimal("4.80")),
        ("A2", "A+", Decimal("20"), Decimal("4.80")),
        ("B1", "A", Decimal("-20"), Decimal("4.80")),
        ("B2", "A", Decimal("10"), Decimal("4.80")),
    ]
    for i, (tick, quality, pnl, stop) in enumerate(specs):
        sid = f"FIRST_PULLBACK|{tick}|1|{10000 + i}"
        commit_import(
            db_session,
            pine_line(signal_id=sid, event_type="ENTRY", event_ms=10000 + i, ticker=tick, quality=quality, planned_stop=str(stop)),
        )
        t = make_trade(
            db_session,
            manual_account.id,
            ticker=tick,
            net_pnl=pnl,
            fees=Decimal("0"),
            exit_time=datetime(2026, 9, 1, 15, i, tzinfo=timezone.utc),
        )
        t.avg_entry_price = Decimal("5.00")
        t.quantity = Decimal("100")
        db_session.commit()
        sig = db_session.query(Signal).filter(Signal.signal_id == sid).one()
        confirm_link(db_session, sig, t)
        db_session.commit()

    extra = make_trade(db_session, manual_account.id, ticker="NONE", net_pnl=Decimal("5"), exit_time=datetime(2026, 9, 3, 15, 0, tzinfo=timezone.utc))
    db_session.commit()

    reports = get_reports(db_session, TradeFilterSet(pine_scope="ALL"))
    quality = next(r for s in reports["sections"] if s["key"] == "STRATEGY" for r in s["reports"] if r["key"] == "setup_quality")
    by_key = {b["key"]: b for b in quality["buckets"]}
    assert Decimal(by_key["A+"]["average_r"]) == Decimal("1.5")
    assert Decimal(by_key["A"]["average_r"]) == Decimal("-0.25")

    # 5 closed trades, 4 linked, 4 R-qualified (all linked have stops)
    from app.services.signals.coverage import coverage_summary
    from app.services.risk.service import missing_r_breakdown
    from app.db.models.trade import Trade

    trades = db_session.query(Trade).all()
    cov = coverage_summary(db_session, trades)
    r = missing_r_breakdown(db_session, trades)
    assert cov["trades_with_signal"] == 4
    assert r["r_qualified"] == 4
    assert cov["closed_trades"] == 5
    assert Decimal(cov["strategy_coverage_pct"]) == Decimal("80")
    assert Decimal(r["r_coverage_pct"]) == Decimal("80")
    # they can numerically match here; the extra unlinked also has no R.
    # Add a 5th linked? Instead add risk to extra without signal:
    extra.avg_entry_price = Decimal("5")
    extra.quantity = Decimal("100")
    db_session.commit()
    RiskService(db_session).apply_manual(extra, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    db_session.commit()
    cov = coverage_summary(db_session, db_session.query(Trade).all())
    r = missing_r_breakdown(db_session, db_session.query(Trade).all())
    assert Decimal(cov["strategy_coverage_pct"]) == Decimal("80")
    assert Decimal(r["r_coverage_pct"]) == Decimal("100")
    assert cov["strategy_coverage_pct"] != r["r_coverage_pct"]


def test_delete_trade_does_not_delete_signal(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|9000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=9000))
    t = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("1"))
    db_session.commit()
    confirm_link(db_session, db_session.query(Signal).one(), t)
    db_session.commit()
    db_session.delete(t)
    db_session.commit()
    assert db_session.query(Signal).count() == 1
    from app.db.models.signal import TradeSignalLink

    assert db_session.query(TradeSignalLink).count() == 0
    from app.db.models.risk import TradeRisk

    assert db_session.query(TradeRisk).count() == 0
