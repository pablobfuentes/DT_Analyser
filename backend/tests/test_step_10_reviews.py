"""Step 10 — daily/weekly review snapshots reuse existing analytics."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app.services.dashboard_service import DashboardFilters, _serialize_summary, _summary_stats, _trade_row, build_closed_trades_query
from app.services.reviews.daily import complete_review, live_metrics_for_date, review_payload
from app.services.reviews.weekly import live_metrics_for_week, week_bounds
from tests.dashboard_helpers import make_trade


def test_daily_snapshot_frozen_after_complete(db_session, manual_account):
    t = make_trade(
        db_session,
        manual_account.id,
        ticker="REV",
        net_pnl=Decimal("50"),
        entry_time=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc),
        exit_time=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    day = date(2026, 9, 2)
    live = live_metrics_for_date(db_session, day)
    assert live["trade_count"] == 1
    complete_review(db_session, day)
    payload = review_payload(db_session, day)
    snap_pnl = payload["metrics_snapshot"]["summary"]["net_pnl"]
    t.net_pnl = Decimal("999")
    db_session.commit()
    later = review_payload(db_session, day)
    assert later["metrics_snapshot"]["summary"]["net_pnl"] == snap_pnl
    assert later["live_metrics"]["summary"]["net_pnl"] != snap_pnl


def test_weekly_reuses_dashboard_formulas(db_session, manual_account):
    make_trade(
        db_session,
        manual_account.id,
        ticker="W1",
        net_pnl=Decimal("10"),
        entry_time=datetime(2026, 9, 1, 14, 0, tzinfo=timezone.utc),
        exit_time=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc),
    )
    make_trade(
        db_session,
        manual_account.id,
        ticker="W2",
        net_pnl=Decimal("-4"),
        entry_time=datetime(2026, 9, 2, 14, 0, tzinfo=timezone.utc),
        exit_time=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc),
    )
    db_session.commit()
    start, end = week_bounds(date(2026, 9, 1))
    filt = DashboardFilters(start_date=start, end_date=end)
    trades = list(build_closed_trades_query(db_session, filt).all())
    dash = _serialize_summary(_summary_stats([_trade_row(t) for t in trades]))
    weekly = live_metrics_for_week(db_session, date(2026, 9, 1))
    assert weekly["summary"]["net_pnl"] == dash["net_pnl"]
    assert weekly["summary"]["trades"] == dash["trades"]
    assert weekly["summary"]["win_rate"] == dash["win_rate"]
