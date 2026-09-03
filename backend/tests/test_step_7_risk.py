"""Step 7 — RiskService, R analytics, equity baseline, drawdown."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.db.models.risk import RiskAuditLog, TradeRisk
from app.services.analytics.drawdown import pre_period_realized_pnl, summarize_r_drawdown
from app.services.analytics.expectancy import dollar_expectancy, payoff_ratio, profit_factor, r_statistics
from app.services.dashboard_service import DashboardFilters, get_dashboard
from app.services.risk.service import RiskService, equity_before_entry_map, missing_r_breakdown
from tests.dashboard_helpers import make_trade


def _long(db, account, **kw):
    t = make_trade(db, account.id, **kw)
    t.direction = "LONG"
    return t


def test_long_risk(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("80"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("400")
    db_session.commit()
    result = RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    db_session.commit()
    assert result.actual_risk_per_share == Decimal("0.20")
    assert result.actual_initial_risk_amount == Decimal("80.00")
    assert result.r_multiple == Decimal("1")
    row = db_session.query(TradeRisk).filter(TradeRisk.trade_id == t.id).one()
    assert row.actual_initial_risk_amount == t.initial_risk_amount
    assert t.r_multiple == row.r_multiple


def test_short_risk(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, direction="SHORT", net_pnl=Decimal("60"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("200")
    db_session.commit()
    result = RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("5.20"), initial_risk_amount=None)
    assert result.actual_risk_per_share == Decimal("0.20")
    assert result.actual_initial_risk_amount == Decimal("40.00")
    assert result.r_multiple == Decimal("1.5")


def test_invalid_stop_null_r(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("10"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("100")
    db_session.commit()
    row = RiskService(db_session).get_or_create(t)
    row.initial_stop_price = Decimal("5.20")
    row.manual_override = True
    db_session.flush()
    result = RiskService(db_session).recalculate_trade(t)
    assert result.risk_quality_status == "INVALID_STOP"
    assert result.r_multiple is None
    assert result.actual_initial_risk_amount is None


def test_scale_in_uses_avg_entry(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("30"), fees=Decimal("0"), quantity=Decimal("300"))
    t.avg_entry_price = Decimal("4.066666")
    db_session.commit()
    result = RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("3.90"), initial_risk_amount=None)
    assert result.actual_risk_per_share > 0
    expected = (t.avg_entry_price - Decimal("3.90")) * Decimal("300")
    assert abs(result.actual_initial_risk_amount - expected.quantize(Decimal("0.0001"))) < Decimal("0.01")


def test_manual_override_survives_recalc(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("20"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("100")
    db_session.commit()
    RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=Decimal("25"))
    db_session.commit()
    RiskService(db_session).recalculate_trade(t)
    db_session.commit()
    db_session.refresh(t)
    assert t.risk_source == "MANUAL"
    assert t.initial_risk_amount == Decimal("25.0000") or t.initial_risk_amount == Decimal("25")
    assert db_session.query(RiskAuditLog).filter(RiskAuditLog.trade_id == t.id).count() >= 1


def test_explicit_amount_preserves_stop_derived(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("20"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("100")
    db_session.commit()
    RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=Decimal("25"))
    db_session.commit()
    row = db_session.query(TradeRisk).one()
    assert row.explicit_initial_risk_amount == Decimal("25") or row.explicit_initial_risk_amount == Decimal("25.0000")
    assert row.stop_derived_risk_amount == Decimal("20.0000")
    assert row.actual_initial_risk_amount == Decimal("25.0000") or row.actual_initial_risk_amount == Decimal("25")


def test_r_basis_net_vs_gross(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=None, gross_pnl=Decimal("40"), fees=None)
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.commit()
    result = RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    assert result.r_pnl_basis == "GROSS"
    assert result.fees_known is False
    t2 = _long(db_session, manual_account, net_pnl=Decimal("40"), fees=Decimal("0"), ticker="BB")
    t2.avg_entry_price = Decimal("5")
    t2.quantity = Decimal("100")
    db_session.commit()
    r2 = RiskService(db_session).apply_manual(t2, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    assert r2.r_pnl_basis == "NET"
    assert r2.fees_known is True


def test_expectancy_pf_payoff_r():
    pnls = [Decimal("100"), Decimal("-50"), Decimal("0")]
    assert dollar_expectancy(pnls) == Decimal("50") / Decimal("3")
    pf, status = profit_factor(pnls)
    assert status == "FINITE"
    assert pf == Decimal("2")
    rs = [Decimal("2"), Decimal("-1"), Decimal("0.5")]
    st = r_statistics(rs)
    assert st["average"] == Decimal("0.5")
    assert st["expectancy"] == Decimal("0.5")
    assert st["avg_loser"] == Decimal("-1")
    rpf, rst = profit_factor(rs)
    assert rst == "FINITE"
    assert payoff_ratio(rs) == Decimal("1.25")


def test_profit_factor_special_cases():
    assert profit_factor([]) == (None, "NO_TRADES")
    pf, st = profit_factor([Decimal("10")])
    assert pf is None and st == "NO_LOSSES"
    pf, st = profit_factor([Decimal("-10")])
    assert pf == Decimal("0")


def test_r_drawdown():
    series = [
        {"cumulative_r": "1"},
        {"cumulative_r": "2"},
        {"cumulative_r": "-0.5"},
        {"cumulative_r": "0"},
    ]
    summary = summarize_r_drawdown(series)
    assert Decimal(summary["max_r"]) == Decimal("-2.5")


def test_equity_at_entry_no_lookahead(db_session, manual_account):
    manual_account.starting_equity = Decimal("10000")
    db_session.commit()
    a = make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("500"),
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        exit_time=datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc),
        ticker="A",
    )
    b = make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("100"),
        entry_time=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc),
        exit_time=datetime(2026, 9, 1, 17, 0, tzinfo=timezone.utc),
        ticker="B",
    )
    eq = equity_before_entry_map(db_session, [a, b])
    assert eq[a.id] == Decimal("10000")
    assert eq[b.id] == Decimal("10000")


def test_equity_same_timestamp_excluded(db_session, manual_account):
    manual_account.starting_equity = Decimal("10000")
    db_session.commit()
    ts = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
    a = make_trade(db_session, manual_account.id, net_pnl=Decimal("500"), exit_time=ts, ticker="A")
    b = make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("100"),
        entry_time=ts,
        exit_time=datetime(2026, 9, 1, 16, 0, tzinfo=timezone.utc),
        ticker="B",
    )
    eq = equity_before_entry_map(db_session, [b])
    assert eq[b.id] == Decimal("10000")


def test_multi_account_isolation(db_session, manual_account, strategy_account):
    manual_account.starting_equity = Decimal("10000")
    strategy_account.starting_equity = Decimal("5000")
    db_session.commit()
    make_trade(db_session, manual_account.id, net_pnl=Decimal("1000"), ticker="A")
    b = make_trade(
        db_session,
        strategy_account.id,
        source_type="TRADINGVIEW_AUTO",
        net_pnl=Decimal("10"),
        ticker="B",
        entry_time=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc),
        exit_time=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc),
    )
    eq = equity_before_entry_map(db_session, [b])
    assert eq[b.id] == Decimal("5000")


def test_risk_pct_null_without_starting_equity(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("10"))
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.commit()
    result = RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    assert result.risk_pct_equity_at_entry is None


def test_risk_pct_with_equity(db_session, manual_account):
    manual_account.starting_equity = Decimal("10000")
    db_session.commit()
    t = _long(db_session, manual_account, net_pnl=Decimal("10"))
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.commit()
    result = RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    assert result.risk_pct_equity_at_entry == Decimal("0.20")


def test_real_equity_baseline_ignores_direction_filter(db_session, manual_account):
    manual_account.starting_equity = Decimal("10000")
    db_session.commit()
    make_trade(
        db_session,
        manual_account.id,
        direction="LONG",
        net_pnl=Decimal("500"),
        exit_time=datetime(2026, 8, 15, 15, 0, tzinfo=timezone.utc),
        ticker="OLD",
    )
    make_trade(
        db_session,
        manual_account.id,
        direction="SHORT",
        net_pnl=Decimal("500"),
        exit_time=datetime(2026, 8, 16, 15, 0, tzinfo=timezone.utc),
        ticker="OLD2",
    )
    make_trade(
        db_session,
        manual_account.id,
        direction="LONG",
        net_pnl=Decimal("200"),
        exit_time=datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc),
        ticker="NEW",
    )
    pre = pre_period_realized_pnl(
        db_session,
        DashboardFilters(start_date=__import__("datetime").date(2026, 9, 1), direction="LONG", ticker="NEW", account_id=manual_account.id),
    )
    assert pre == Decimal("1000")
    r = get_dashboard(
        db_session,
        DashboardFilters(
            start_date=__import__("datetime").date(2026, 9, 1),
            end_date=__import__("datetime").date(2026, 9, 30),
            account_id=manual_account.id,
            direction="LONG",
            ticker="NEW",
        ),
    )
    assert Decimal(r["equity"]["starting_equity"]) == Decimal("11000")


def test_r_coverage_reasons_not_all_no_pine(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("10"))
    db_session.commit()
    breakdown = missing_r_breakdown(db_session, [t])
    assert breakdown["reasons"].get("MISSING_STOP", 0) == 1
    assert "NO_PINE_SIGNAL" not in breakdown["reasons"]
    assert breakdown["no_signal_available_context"] == 1


def test_graph_average_r_uses_trade_r(db_session, manual_account):
    from app.services.reports.filters import TradeFilterSet
    from app.services.reports.service import get_reports

    t = _long(db_session, manual_account, net_pnl=Decimal("40"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.commit()
    RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    db_session.commit()
    reports = get_reports(db_session, TradeFilterSet())
    dow = next(r for s in reports["sections"] if s["key"] == "TIME" for r in s["reports"] if r["key"] == "day_of_week")
    bucket = dow["buckets"][0]
    assert Decimal(bucket["average_r"]) == Decimal("2")
    assert bucket["r_qualified_count"] == 1
    risk_sec = next(s for s in reports["sections"] if s["key"] == "RISK")
    assert risk_sec["available"] is True


def test_loss_beyond_threshold(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("-30"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.commit()
    RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    db_session.commit()
    dash = get_dashboard(db_session, DashboardFilters())
    assert dash["advanced"]["loss_beyond_initial_risk"]["count"] == 1
    assert dash["advanced"]["loss_beyond_initial_risk"]["threshold"] == "-1.05"


def test_cache_invariant(db_session, manual_account):
    t = _long(db_session, manual_account, net_pnl=Decimal("20"), fees=Decimal("0"))
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.commit()
    RiskService(db_session).apply_manual(t, initial_stop_price=Decimal("4.80"), initial_risk_amount=None)
    db_session.commit()
    row = db_session.query(TradeRisk).one()
    db_session.refresh(t)
    assert t.initial_risk_amount == row.actual_initial_risk_amount
    assert t.r_multiple == row.r_multiple
    assert t.risk_source == row.risk_source
    assert t.initial_stop_price == row.initial_stop_price
