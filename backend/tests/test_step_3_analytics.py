"""Step 3 analytics tests."""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.db.models.trade import Trade
from app.services.analytics.drawdown import build_equity_series, equity_baseline, summarize_drawdown
from app.services.analytics.expectancy import dollar_expectancy, payoff_ratio, profit_factor, r_statistics
from app.services.analytics.risk import (
    build_risk_computation,
    compute_r_multiple,
    validate_stop_for_direction,
)
from app.services.analytics.streaks import compute_streaks
from app.services.dashboard_service import DashboardFilters, get_dashboard
from tests.dashboard_helpers import make_trade

UTC = timezone.utc


def _risk_trade(db, account_id, **kwargs):
    t = make_trade(db, account_id, **kwargs)
    return t


# --- R calculation ---


def test_r_long_winner(db_session, manual_account):
    t = _risk_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("40"),
        gross_pnl=Decimal("40"),
    )
    t.direction = "LONG"
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.flush()
    comp = build_risk_computation(t, initial_stop_price=Decimal("4.80"))
    assert comp.initial_risk_amount == Decimal("20")
    assert comp.r_multiple == Decimal("2")


def test_r_long_loser(db_session, manual_account):
    t = _risk_trade(db_session, manual_account.id, net_pnl=Decimal("-20"))
    t.direction = "LONG"
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    comp = build_risk_computation(t, initial_stop_price=Decimal("4.80"))
    assert comp.r_multiple == Decimal("-1")


def test_r_short_winner(db_session, manual_account):
    t = _risk_trade(db_session, manual_account.id, net_pnl=Decimal("30"), direction="SHORT")
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    comp = build_risk_computation(t, initial_stop_price=Decimal("5.20"))
    assert comp.initial_risk_amount == Decimal("20")
    assert comp.r_multiple == Decimal("1.5")


def test_r_short_loser(db_session, manual_account):
    t = _risk_trade(db_session, manual_account.id, net_pnl=Decimal("-50"), direction="SHORT")
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    comp = build_risk_computation(t, initial_stop_price=Decimal("5.20"))
    assert comp.r_multiple == Decimal("-2.5")


def test_stop_validation_long():
    assert validate_stop_for_direction("LONG", Decimal("5"), Decimal("5.20")) is not None


def test_stop_validation_short():
    assert validate_stop_for_direction("SHORT", Decimal("5"), Decimal("4.80")) is not None


def test_explicit_risk_amount(db_session, manual_account):
    t = _risk_trade(db_session, manual_account.id, net_pnl=Decimal("40"))
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    comp = build_risk_computation(t, initial_risk_amount=Decimal("20"))
    assert comp.r_multiple == Decimal("2")


def test_r_fixture_spec_39():
    r_vals = [Decimal("2"), Decimal("-1"), Decimal("1.5"), Decimal("-1")]
    stats = r_statistics(r_vals)
    assert stats["expectancy"] == Decimal("0.375")
    assert stats["median"] == Decimal("0.25")
    assert stats["avg_winner"] == Decimal("1.75")
    assert stats["avg_loser"] == Decimal("-1")
    assert stats["best"] == Decimal("2")
    assert stats["worst"] == Decimal("-1")


def test_profit_factor_fixture():
    pnls = [Decimal("200"), Decimal("-100"), Decimal("75"), Decimal("-100")]
    pf, status = profit_factor(pnls)
    assert status == "FINITE"
    assert pf == Decimal("1.375")
    assert dollar_expectancy(pnls) == Decimal("18.75")
    assert payoff_ratio(pnls) == Decimal("1.375")


def test_profit_factor_no_losses():
    pf, status = profit_factor([Decimal("100")])
    assert status == "NO_LOSSES"
    assert pf is None


def test_drawdown_fixture():
    baseline = {"starting_equity_available": True, "baseline_equity": Decimal("10000"), "baseline_pnl": Decimal("0")}
    rows = []
    pnls = [500, 200, -300, -400, 100, 500, 200]
    for i, p in enumerate(pnls):
        t = Trade(
            account_id=1,
            source_type="X",
            trade_fingerprint=f"x{i}",
            ticker="T",
            direction="LONG",
            entry_time_utc=datetime(2026, 9, 1, tzinfo=UTC),
            exit_time_utc=datetime(2026, 9, 1, 10 + i, tzinfo=UTC),
            avg_entry_price=Decimal("1"),
            quantity=Decimal("1"),
            status="CLOSED",
            net_pnl=Decimal(str(p)),
        )
        rows.append({"trade": t, "pnl": Decimal(str(p)), "r_multiple": None})

    _, _, _, dd = build_equity_series(rows, baseline)
    summary = summarize_drawdown(dd, True)
    assert Decimal(summary["max_dollars"]) == Decimal("-700")
    max_pct = Decimal(summary["max_pct"])
    assert abs(max_pct - Decimal("-6.542056")) < Decimal("0.001")


def test_streaks_fixture():
    outcomes = ["WIN", "WIN", "LOSS", "LOSS", "LOSS", "BREAKEVEN", "WIN", "WIN", "WIN", "WIN", "LOSS"]
    s = compute_streaks(outcomes)
    assert s["longest_win"] == 4
    assert s["longest_loss"] == 3
    assert s["current_type"] == "LOSS"
    assert s["current_count"] == 1


def test_breakeven_breaks_streaks():
    s = compute_streaks(["WIN", "WIN", "BREAKEVEN", "WIN"])
    assert s["longest_win"] == 2
    assert s["current_type"] == "BE"


def test_dashboard_advanced_empty(db_session):
    r = get_dashboard(db_session, DashboardFilters())
    assert r["advanced"]["dollar_expectancy"] is None


def test_dashboard_r_coverage(db_session, manual_account):
    t1 = make_trade(db_session, manual_account.id, net_pnl=Decimal("100"))
    t1.initial_risk_amount = Decimal("50")
    t1.r_multiple = Decimal("2")
    t2 = make_trade(db_session, manual_account.id, net_pnl=Decimal("-50"), ticker="B")
    db_session.commit()
    r = get_dashboard(db_session, DashboardFilters())
    assert r["advanced"]["r"]["trade_count"] == 1
    assert r["advanced"]["r"]["missing_count"] == 1


def test_patch_risk_via_service(db_session, manual_account):
    from app.services.analytics.risk import apply_risk_to_trade, build_risk_computation

    t = make_trade(db_session, manual_account.id, net_pnl=Decimal("40"))
    t.direction = "LONG"
    t.avg_entry_price = Decimal("5")
    t.quantity = Decimal("100")
    db_session.commit()

    comp = build_risk_computation(t, initial_stop_price=Decimal("4.80"), risk_source="MANUAL")
    apply_risk_to_trade(t, comp)
    db_session.commit()
    db_session.refresh(t)
    assert t.r_multiple == Decimal("2")


def test_patch_risk_invalid_long_stop_service(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, net_pnl=Decimal("10"))
    t.direction = "LONG"
    t.avg_entry_price = Decimal("5")
    db_session.commit()
    with pytest.raises(ValueError, match="below"):
        build_risk_computation(t, initial_stop_price=Decimal("5.20"))
