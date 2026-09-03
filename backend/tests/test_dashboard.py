"""Dashboard analytics and API tests."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.db.models.account import Account
from app.db.models.trade import Trade
from app.services.dashboard_service import DashboardFilters, get_dashboard
from app.utils.analytics import (
    breakeven_tolerance,
    classify_outcome,
    effective_realized_pnl,
    ny_date_from_utc,
    utc_bounds_for_ny_range,
)
from tests.dashboard_helpers import make_trade, seed_example_trades


def test_empty_database(db_session):
    result = get_dashboard(db_session, DashboardFilters())
    assert result["empty"] is True
    assert result["summary"]["trades"] == 0


def test_single_winner(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("50"))
    r = get_dashboard(db_session, DashboardFilters())
    assert r["summary"]["trades"] == 1
    assert Decimal(r["summary"]["net_pnl"]) == Decimal("50")
    assert r["summary"]["wins"] == 1


def test_single_loser(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("-30"))
    r = get_dashboard(db_session, DashboardFilters())
    assert r["summary"]["losses"] == 1
    assert Decimal(r["summary"]["net_pnl"]) == Decimal("-30")


def test_example_fixture_metrics(db_session, manual_account, strategy_account):
    seed_example_trades(db_session, manual_account, strategy_account)
    r = get_dashboard(db_session, DashboardFilters())
    s = r["summary"]
    assert s["trades"] == 5
    assert s["wins"] == 2
    assert s["losses"] == 2
    assert s["breakeven"] == 1
    assert Decimal(s["net_pnl"]) == Decimal("100")
    assert Decimal(s["win_rate"]) == Decimal("50")
    assert Decimal(s["avg_trade"]) == Decimal("20")
    assert Decimal(s["avg_winner"]) == Decimal("87.5")
    assert Decimal(s["avg_loser"]) == Decimal("-37.5")
    assert Decimal(s["best_trade"]) == Decimal("100")
    assert Decimal(s["worst_trade"]) == Decimal("-50")


def test_manual_vs_auto_comparison(db_session, manual_account, strategy_account):
    seed_example_trades(db_session, manual_account, strategy_account)
    cmp = get_dashboard(db_session, DashboardFilters())["source_comparison"]
    m = cmp["manual"]
    a = cmp["auto"]
    assert m["trades"] == 3
    assert Decimal(m["net_pnl"]) == Decimal("50")
    assert Decimal(m["win_rate"]) == Decimal("50")
    assert Decimal(m["avg_trade"]).quantize(Decimal("0.01")) == Decimal("16.67")
    assert Decimal(m["avg_winner"]) == Decimal("100")
    assert Decimal(m["avg_loser"]) == Decimal("-50")
    assert a["trades"] == 2
    assert Decimal(a["net_pnl"]) == Decimal("50")
    assert Decimal(a["avg_trade"]) == Decimal("25")
    assert Decimal(a["avg_winner"]) == Decimal("75")
    assert Decimal(a["avg_loser"]) == Decimal("-25")


def test_breakeven_excluded_from_win_rate(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("0"))
    make_trade(db_session, manual_account.id, net_pnl=Decimal("10"), ticker="A")
    r = get_dashboard(db_session, DashboardFilters())
    assert r["summary"]["breakeven"] == 1
    assert Decimal(r["summary"]["win_rate"]) == Decimal("100")  # 1W / (1W + 0L)


def test_win_rate_null_when_no_wins_or_losses(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("0"))
    make_trade(db_session, manual_account.id, net_pnl=Decimal("0.005"), ticker="B")
    r = get_dashboard(db_session, DashboardFilters())
    assert r["summary"]["win_rate"] is None


def test_missing_fees_warning(db_session, manual_account):
    make_trade(db_session, manual_account.id, gross_pnl=Decimal("10"), net_pnl=None, fees=None)
    r = get_dashboard(db_session, DashboardFilters())
    assert any("fee" in w.lower() for w in r["warnings"])


def test_open_trades_excluded(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("10"), status="CLOSED")
    make_trade(db_session, manual_account.id, net_pnl=Decimal("999"), status="OPEN", ticker="OPEN")
    r = get_dashboard(db_session, DashboardFilters())
    assert r["summary"]["trades"] == 1
    assert r["secondary"]["open_trades"] == 1


def test_daily_aggregation_ny_timezone(db_session, manual_account):
    # 2026-09-01 01:00 UTC = 2026-08-31 21:00 NY (EDT)
    make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("10"),
        exit_time=datetime(2026, 9, 1, 1, 0, tzinfo=timezone.utc),
        ticker="A",
    )
    # 2026-09-01 20:00 UTC = 2026-09-01 16:00 NY
    make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("20"),
        exit_time=datetime(2026, 9, 1, 20, 0, tzinfo=timezone.utc),
        ticker="B",
    )
    r = get_dashboard(db_session, DashboardFilters())
    dates = {d["date"] for d in r["cumulative"]}
    assert "2026-08-31" in dates
    assert "2026-09-01" in dates


def test_dst_boundary(db_session, manual_account):
    """March DST transition — use zoneinfo bounds, not fixed offset."""
    # 2026-03-09 is DST start in US; pick a date after
    d = date(2026, 3, 10)
    utc_start, utc_end = utc_bounds_for_ny_range(d, d)
    make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("5"),
        exit_time=utc_start,
        ticker="DST",
    )
    r = get_dashboard(db_session, DashboardFilters(start_date=d, end_date=d))
    assert r["summary"]["trades"] == 1


def test_date_range_filter(db_session, manual_account):
    make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("1"),
        exit_time=datetime(2026, 8, 1, 15, 0, tzinfo=timezone.utc),
        ticker="OLD",
    )
    make_trade(
        db_session,
        manual_account.id,
        net_pnl=Decimal("2"),
        exit_time=datetime(2026, 9, 15, 15, 0, tzinfo=timezone.utc),
        ticker="NEW",
    )
    r = get_dashboard(
        db_session,
        DashboardFilters(start_date=date(2026, 9, 1), end_date=date(2026, 9, 30)),
    )
    assert r["summary"]["trades"] == 1
    assert Decimal(r["summary"]["net_pnl"]) == Decimal("2")


def test_manual_filter(db_session, manual_account, strategy_account):
    seed_example_trades(db_session, manual_account, strategy_account)
    r = get_dashboard(db_session, DashboardFilters(source_type="MANUAL"))
    assert r["summary"]["trades"] == 3


def test_auto_filter(db_session, manual_account, strategy_account):
    seed_example_trades(db_session, manual_account, strategy_account)
    r = get_dashboard(db_session, DashboardFilters(source_type="AUTO"))
    assert r["summary"]["trades"] == 2


def test_direction_filter(db_session, manual_account, strategy_account):
    seed_example_trades(db_session, manual_account, strategy_account)
    r = get_dashboard(db_session, DashboardFilters(direction="SHORT"))
    assert r["summary"]["trades"] == 1


def test_ticker_filter(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("1"), ticker="AAPL")
    make_trade(db_session, manual_account.id, net_pnl=Decimal("2"), ticker="MSFT")
    r = get_dashboard(db_session, DashboardFilters(ticker="AAPL"))
    assert r["summary"]["trades"] == 1


def test_account_filter(db_session, manual_account, strategy_account):
    seed_example_trades(db_session, manual_account, strategy_account)
    r = get_dashboard(db_session, DashboardFilters(account_id=manual_account.id))
    assert r["summary"]["trades"] == 3


def test_starting_equity(db_session, manual_account):
    manual_account.starting_equity = Decimal("10000")
    db_session.commit()
    make_trade(db_session, manual_account.id, net_pnl=Decimal("500"))
    r = get_dashboard(db_session, DashboardFilters(account_id=manual_account.id))
    assert r["equity"]["available"] is True
    assert Decimal(r["equity"]["starting_equity"]) == Decimal("10000")
    assert Decimal(r["equity"]["current_realized_equity"]) == Decimal("10500")
    assert Decimal(r["equity"]["realized_return_pct"]) == Decimal("5")


def test_missing_starting_equity(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("100"))
    r = get_dashboard(db_session, DashboardFilters(account_id=manual_account.id))
    assert r["equity"]["available"] is False


def test_cumulative_sequence(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("50"), exit_time=datetime(2026, 9, 1, 10, 0, tzinfo=timezone.utc), ticker="A")
    make_trade(db_session, manual_account.id, net_pnl=Decimal("-20"), exit_time=datetime(2026, 9, 2, 10, 0, tzinfo=timezone.utc), ticker="B")
    make_trade(db_session, manual_account.id, net_pnl=Decimal("70"), exit_time=datetime(2026, 9, 3, 10, 0, tzinfo=timezone.utc), ticker="C")
    cum = get_dashboard(db_session, DashboardFilters())["cumulative"]
    values = [Decimal(c["cumulative_pnl"]) for c in cum]
    assert values[-1] == Decimal("100")


def test_green_red_day_classification(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("100"), exit_time=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc), ticker="G")
    make_trade(db_session, manual_account.id, net_pnl=Decimal("-50"), exit_time=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc), ticker="R")
    daily = get_dashboard(db_session, DashboardFilters())["daily"]
    by_date = {d["date"]: d["day_type"] for d in daily}
    assert by_date["2026-09-01"] == "GREEN"
    assert by_date["2026-09-02"] == "RED"


def test_effective_realized_pnl_prefers_net(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, net_pnl=Decimal("90"), gross_pnl=Decimal("100"), fees=Decimal("10"))
    rp = effective_realized_pnl(t)
    assert rp.pnl == Decimal("90")
    assert rp.includes_fees is True


def test_classify_outcome_tolerance():
    tol = breakeven_tolerance()
    assert classify_outcome(Decimal("0.02"), tol) == "WIN"
    assert classify_outcome(Decimal("-0.02"), tol) == "LOSS"
    assert classify_outcome(Decimal("0"), tol) == "BREAKEVEN"


def test_decimal_precision(db_session, manual_account):
    make_trade(db_session, manual_account.id, net_pnl=Decimal("0.4875"), ticker="PENNY")
    r = get_dashboard(db_session, DashboardFilters())
    assert Decimal(r["summary"]["net_pnl"]) == Decimal("0.4875")


def test_combined_accounts_starting_equity(db_session, manual_account, strategy_account):
    manual_account.starting_equity = Decimal("5000")
    strategy_account.starting_equity = Decimal("10000")
    db_session.commit()
    make_trade(db_session, manual_account.id, net_pnl=Decimal("100"))
    make_trade(db_session, strategy_account.id, source_type="TRADINGVIEW_AUTO", net_pnl=Decimal("200"), ticker="A")
    r = get_dashboard(db_session, DashboardFilters())
    assert r["equity"]["available"] is True
    assert Decimal(r["equity"]["starting_equity"]) == Decimal("15000")
    assert Decimal(r["equity"]["current_realized_equity"]) == Decimal("15300")


def test_recent_trades_id_tie_break(db_session, manual_account):
    same_exit = datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc)
    first = make_trade(db_session, manual_account.id, net_pnl=Decimal("1"), exit_time=same_exit, ticker="A")
    second = make_trade(db_session, manual_account.id, net_pnl=Decimal("2"), exit_time=same_exit, ticker="B")
    r = get_dashboard(db_session, DashboardFilters())
    ids = [t["id"] for t in r["recent_trades"]]
    assert ids[0] == second.id
    assert ids[1] == first.id


def test_recent_trades_limit(db_session, manual_account):
    for i in range(15):
        make_trade(
            db_session,
            manual_account.id,
            net_pnl=Decimal("1"),
            exit_time=datetime(2026, 9, 1, 10, i, tzinfo=timezone.utc),
            ticker=f"T{i}",
        )
    r = get_dashboard(db_session, DashboardFilters())
    assert len(r["recent_trades"]) == 10


def test_short_trades_in_dashboard_and_filter(db_session, manual_account):
    """LONG winner/loser + SHORT winner/loser — direction filter and net P&L."""
    make_trade(db_session, manual_account.id, direction="LONG", net_pnl=Decimal("40"), ticker="LW")
    make_trade(db_session, manual_account.id, direction="LONG", net_pnl=Decimal("-20"), ticker="LL")
    make_trade(db_session, manual_account.id, direction="SHORT", net_pnl=Decimal("30"), ticker="SW")
    make_trade(db_session, manual_account.id, direction="SHORT", net_pnl=Decimal("-10"), ticker="SL")

    all_r = get_dashboard(db_session, DashboardFilters())
    assert all_r["summary"]["trades"] == 4
    assert Decimal(all_r["summary"]["net_pnl"]) == Decimal("40")
    assert all_r["summary"]["wins"] == 2
    assert all_r["summary"]["losses"] == 2

    short_r = get_dashboard(db_session, DashboardFilters(direction="SHORT"))
    assert short_r["summary"]["trades"] == 2
    assert Decimal(short_r["summary"]["net_pnl"]) == Decimal("20")
    assert short_r["summary"]["wins"] == 1
    assert short_r["summary"]["losses"] == 1
