"""Step 9 Research Lab — cohort reuse, timing, visuals, robustness, stats."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.reports.features import AnnotatedTrade
from app.services.reports.filters import TradeFilterSet, apply_exploration
from app.services.reports.service import _annotate_trades
from app.services.research.cohorts import (
    CohortDef,
    ResearchScope,
    apply_cohort,
    cohort_hash,
    load_universe,
    split_ab,
)
from app.services.research.comparison import compare_summaries, coverage_panel, summarize_cohort
from app.services.research.heatmap import build_heatmap
from app.services.research.multifactor import build_multifactor
from app.services.research.payload import parse_scope
from app.services.research.distributions import build_distribution
from app.services.research.numeric import attach_numeric
from app.services.research.robustness import (
    chrono_split,
    concentration,
    robustness_means,
    trim_rows,
)
from app.services.research.rolling import build_rolling
from app.services.research.saved import (
    create_candidate_rule,
    evaluate_rule,
    get_view,
    revise_candidate_rule,
    save_view,
    star_pattern,
)
from app.services.research.scatter import build_scatter
from app.services.research.statistics import (
    bootstrap_difference_ci,
    bootstrap_mean_ci,
    sample_size_label,
    spearman,
    wilson_interval,
)
from app.services.research.timing import LookaheadFilterError, validate_cohort_filters
from app.services.research.variables import FILTER_TIMING, RESEARCH_VARIABLES
from app.utils.analytics import classify_outcome
from tests.dashboard_helpers import make_trade

UTC = timezone.utc
client = TestClient(app)


def _ny_utc(year, month, day, ny_hour, ny_minute=0):
    return datetime(year, month, day, ny_hour + 4, ny_minute, tzinfo=UTC)


def _at(trade, features=None, r=None, mfe=None, extra_numeric=None):
    pnl = trade.net_pnl if trade.net_pnl is not None else Decimal("0")
    at = AnnotatedTrade(trade=trade, pnl=pnl, outcome=classify_outcome(pnl), features=dict(features or {}))
    nums = {}
    if r is not None:
        nums["actual_r"] = Decimal(str(r))
        trade.r_multiple = Decimal(str(r))
    elif trade.r_multiple is not None:
        nums["actual_r"] = trade.r_multiple
    if mfe is not None:
        nums["mfe_r"] = Decimal(str(mfe))
    if extra_numeric:
        nums.update(extra_numeric)
    setattr(at, "numeric", nums)
    return at


def _trade(db, account_id, i, r=None, pnl=None, exit_time=None, features=None, extra_numeric=None, **kwargs):
    t = make_trade(
        db,
        account_id,
        ticker=kwargs.pop("ticker", f"T{i}"),
        net_pnl=Decimal(str(pnl if pnl is not None else (r if r is not None else 0))),
        entry_time=kwargs.pop("entry_time", _ny_utc(2026, 6, 1, 9, 35) + timedelta(days=i)),
        exit_time=exit_time or (_ny_utc(2026, 6, 1, 10, 0) + timedelta(days=i)),
        **kwargs,
    )
    if r is not None:
        t.r_multiple = Decimal(str(r))
        db.commit()
        db.refresh(t)
    return _at(t, features=features, r=r, extra_numeric=extra_numeric)


# --- 91 filter equivalence ---


def test_cohort_filter_matches_graphs_exploration(db_session, manual_account):
    rows = []
    for i, q in enumerate(["A+", "A+", "A", "A", "Other"]):
        rows.append(_trade(db_session, manual_account.id, i, r=1, features={"setup_quality": q, "signal_rvol_bucket": "10_20"}))
    filt = TradeFilterSet(exploration={"setup_quality": "A+", "signal_rvol_bucket": "10_20"})
    graph_ids = [at.trade.id for at in rows if apply_exploration(at.features, filt)]
    research, _ = apply_cohort(rows, CohortDef(filters={"setup_quality": "A+", "signal_rvol_bucket": "10_20"}), "PRE_ENTRY_ONLY")
    assert [at.trade.id for at in research] == graph_ids
    assert len(graph_ids) == 2


def test_cohort_weekday_matches_annotated_graphs(db_session, manual_account):
    wed = make_trade(db_session, manual_account.id, entry_time=_ny_utc(2026, 9, 2, 10, 20), ticker="WED1", net_pnl=Decimal("10"))
    thu = make_trade(db_session, manual_account.id, entry_time=_ny_utc(2026, 9, 3, 10, 20), ticker="THU1", net_pnl=Decimal("10"))
    annotated = _annotate_trades(db_session, [wed, thu])
    filt = TradeFilterSet(exploration={"weekday": "WED"})
    graph_ids = [at.trade.id for at in annotated if apply_exploration(at.features, filt)]
    research, _ = apply_cohort(annotated, CohortDef(filters={"weekday": "WED"}), "PRE_ENTRY_ONLY")
    assert [at.trade.id for at in research] == graph_ids == [wed.id]


# --- 92 A/B metrics ---


def test_cohort_ab_metrics_and_difference(db_session, manual_account):
    a = [
        _trade(db_session, manual_account.id, 0, r=2, pnl=200, features={"setup_quality": "A+"}),
        _trade(db_session, manual_account.id, 1, r=1, pnl=100, features={"setup_quality": "A+"}),
        _trade(db_session, manual_account.id, 2, r=-1, pnl=-100, features={"setup_quality": "A+"}),
    ]
    b = [
        _trade(db_session, manual_account.id, 3, r=Decimal("0.5"), pnl=50, features={"setup_quality": "A"}),
        _trade(db_session, manual_account.id, 4, r=-1, pnl=-100, features={"setup_quality": "A"}),
        _trade(db_session, manual_account.id, 5, r=-1, pnl=-100, features={"setup_quality": "A"}),
    ]
    sa, sb = summarize_cohort(a), summarize_cohort(b)
    assert sa["trades"] == 3
    assert Decimal(sa["average_r"]) == Decimal("2") / Decimal("3")
    assert Decimal(sa["median_r"]) == Decimal("1")
    assert Decimal(sa["win_rate"]) == Decimal("200") / Decimal("3")
    assert Decimal(sa["total_r"]) == Decimal("2")
    assert sb["trades"] == 3
    assert Decimal(sb["average_r"]) == Decimal("-0.5")
    assert Decimal(sb["median_r"]) == Decimal("-1")
    assert Decimal(sb["win_rate"]) == Decimal("100") / Decimal("3")
    assert Decimal(sb["total_r"]) == Decimal("-1.5")
    table = compare_summaries(sa, sb, overlap_count=0, independent=True)
    avg = next(r for r in table["rows"] if r["metric"] == "average_r")
    assert Decimal(avg["observed_difference"]) == Decimal("2") / Decimal("3") - Decimal("-0.5")
    assert table["difference_label"] == "Observed Difference"


# --- 93 overlap ---


def test_overlap_count_and_independent_flag(db_session, manual_account):
    shared = [_trade(db_session, manual_account.id, i, r=1, features={"setup_quality": "A+", "context_5m": "bullish"}) for i in range(3)]
    only_a = [_trade(db_session, manual_account.id, 10 + i, r=1, features={"setup_quality": "A+"}) for i in range(2)]
    only_b = [_trade(db_session, manual_account.id, 20 + i, r=1, features={"context_5m": "bullish"}) for i in range(2)]
    universe = shared + only_a + only_b
    split = split_ab(universe, CohortDef(filters={"setup_quality": "A+"}), CohortDef(filters={"context_5m": "bullish"}), "PRE_ENTRY_ONLY")
    assert split["overlap_count"] == 3
    assert split["independent"] is False
    table = compare_summaries(summarize_cohort(split["a"]), summarize_cohort(split["b"]), overlap_count=3, independent=False)
    assert table["mean_r_difference"]["reason"] == "COHORTS_OVERLAP"
    excl = split_ab(universe, CohortDef(filters={"setup_quality": "A+"}), CohortDef(filters={"context_5m": "bullish"}), "PRE_ENTRY_ONLY", exclusive=True)
    assert excl["overlap_count"] == 0
    assert excl["independent"] is True
    assert len(excl["a"]) == 2
    assert len(excl["b"]) == 2


# --- 94–96 timing ---


def test_pre_entry_rejects_mfe_filter():
    with pytest.raises(LookaheadFilterError) as exc:
        validate_cohort_filters({"mfe_r_bucket": "1_1_5"}, "PRE_ENTRY_ONLY")
    assert "mfe_r_bucket" in exc.value.keys
    assert "Not available before trade entry" in str(exc.value)


def test_retrospective_allows_mfe_and_marks_cohort():
    validate_cohort_filters({"mfe_r_bucket": "1_1_5"}, "ALL_FEATURES")
    rows = []
    members, retro = apply_cohort(rows, CohortDef(filters={"mfe_r_bucket": "1_1_5"}), "ALL_FEATURES")
    assert retro is True


def test_full_day_rvol_blocked_prior_rvol_allowed():
    assert FILTER_TIMING["rvol_bucket"] == "END_OF_DAY"
    assert FILTER_TIMING["prior_rvol_bucket"] == "PRE_ENTRY"
    with pytest.raises(LookaheadFilterError):
        validate_cohort_filters({"rvol_bucket": "5_10"}, "PRE_ENTRY_ONLY")
    validate_cohort_filters({"prior_rvol_bucket": "5_10"}, "PRE_ENTRY_ONLY")


# --- 97–98 scatter / spearman ---


def test_scatter_points_and_missing_coverage(db_session, manual_account):
    rows = [
        _trade(db_session, manual_account.id, 0, r=2, extra_numeric={"signal_rvol": Decimal("8")}),
        _trade(db_session, manual_account.id, 1, r=1, extra_numeric={"signal_rvol": Decimal("12")}),
        _trade(db_session, manual_account.id, 2, r=None, extra_numeric={"signal_rvol": Decimal("6")}),
        _trade(db_session, manual_account.id, 3, r=1, extra_numeric={}),
        _trade(db_session, manual_account.id, 4, r=None, extra_numeric={}),
    ]
    # extra_numeric via _trade doesn't pass through — set after
    data = build_scatter(rows, "signal_rvol", "actual_r", "PRE_ENTRY_ONLY")
    assert data["total"] == 5
    assert data["plotted"] == 2
    assert data["missing_x"] + data["missing_y"] + data["missing_both"] + data["plotted"] == 5
    assert {p["trade_id"] for p in data["points"]} == {rows[0].trade.id, rows[1].trade.id}


def test_scatter_blocks_mae_as_x_in_pre_entry():
    with pytest.raises(LookaheadFilterError):
        build_scatter([], "mae_r", "actual_r", "PRE_ENTRY_ONLY")


def test_spearman_perfect_and_reverse():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    assert spearman(xs, xs)["rho"] == pytest.approx(1.0)
    assert spearman(xs, list(reversed(xs)))["rho"] == pytest.approx(-1.0)


# --- 99–100 heatmap ---


def test_heatmap_2x2_avg_r_and_click_filters(db_session, manual_account):
    cells_src = [
        ("5_10", "20_30", 1),
        ("5_10", "20_30", 3),
        ("10_20", "20_30", 2),
        ("5_10", "30_40", -1),
    ]
    rows = []
    for i, (rv, ret, r) in enumerate(cells_src):
        rows.append(
            _trade(
                db_session,
                manual_account.id,
                i,
                r=r,
                pnl=r * 100,
                features={"signal_rvol_bucket": rv, "retracement_bucket": ret},
            )
        )
    hm = build_heatmap(rows, "signal_rvol_bucket", "retracement_bucket", "average_r", "PRE_ENTRY_ONLY")
    by = {(c["x"], c["y"]): c for c in hm["cells"]}
    assert by[("5_10", "20_30")]["trade_count"] == 2
    assert Decimal(by[("5_10", "20_30")]["value"]) == Decimal("2")
    assert by[("5_10", "20_30")]["filters"] == {"signal_rvol_bucket": "5_10", "retracement_bucket": "20_30"}
    members, _ = apply_cohort(rows, CohortDef(filters=by[("5_10", "20_30")]["filters"]), "PRE_ENTRY_ONLY")
    assert len(members) == 2


# --- 101–103 rolling ---


def test_rolling_window_no_lookahead(db_session, manual_account):
    rs = [Decimal("1"), Decimal("2"), Decimal("3"), Decimal("6")]
    rows = [_trade(db_session, manual_account.id, i, r=float(r), pnl=float(r) * 10) for i, r in enumerate(rs)]
    out = build_rolling(rows, metric="average_r", window=3)
    vals = [Decimal(p["value"]) for p in out["points"]]
    assert vals[0] == Decimal("1")
    assert vals[1] == Decimal("1.5")
    assert vals[2] == Decimal("2")
    assert vals[3] == Decimal("11") / Decimal("3")
    # point 2 (index 2) must not include the 4th trade
    assert out["points"][1]["window_n"] == 2


def test_strategy_version_markers(db_session, manual_account):
    rows = []
    for i, ver in enumerate(["v0.3.3", "v0.3.3", "v0.3.4", "v0.3.4"]):
        at = _trade(db_session, manual_account.id, i, r=1, features={"strategy_version": ver})
        rows.append(at)
    out = build_rolling(rows, metric="average_r", window=2)
    marks = out["version_markers"]
    assert marks[0]["strategy_version"] == "v0.3.3"
    assert marks[0]["index"] == 1
    assert any(m["strategy_version"] == "v0.3.4" and m["index"] == 3 for m in marks)


# --- 104–106 robustness ---


def test_outlier_trim_exact(db_session, manual_account):
    rows = [_trade(db_session, manual_account.id, i, r=Decimal("0.2"), pnl=20) for i in range(9)]
    rows.append(_trade(db_session, manual_account.id, 9, r=10, pnl=1000))
    means = robustness_means(rows)
    assert Decimal(means["all"]) == Decimal("1.18")
    trimmed = trim_rows(rows, "trim_1")
    assert len(trimmed) == 8
    assert Decimal(means["trim_top_bottom_1"]["average_r"]) == Decimal("0.2")


def test_winner_concentration_and_nonpositive(db_session, manual_account):
    rows = [_trade(db_session, manual_account.id, 0, r=10, pnl=100)]
    rows += [_trade(db_session, manual_account.id, i + 1, r=1, pnl=10) for i in range(4)]
    c = concentration(rows)
    assert c["available"] is True
    assert Decimal(c["top_1"]["pct_of_total_r"]) == Decimal("10") / Decimal("14") * 100
    losers = [_trade(db_session, manual_account.id, 50 + i, r=-1, pnl=-10) for i in range(3)]
    bad = concentration(losers)
    assert bad["available"] is False
    assert bad["reason"] == "NONPOSITIVE_TOTAL_R"


def test_chrono_split_70_30_never_shuffles(db_session, manual_account):
    rows = [_trade(db_session, manual_account.id, i, r=1, pnl=10) for i in range(10)]
    split = chrono_split(rows, 70)
    assert split["shuffled"] is False
    assert split["research_ids"] == [at.trade.id for at in rows[:7]]
    assert split["validation_ids"] == [at.trade.id for at in rows[7:]]


# --- 107–108 candidate rules ---


def test_forward_sample_uses_entry_not_exit(db_session, manual_account):
    """Entry before cutoff is research even if exit is after cutoff."""
    cutoff = datetime(2026, 8, 1, 14, 0, tzinfo=UTC)  # 10:00 NY (EDT)
    before = make_trade(
        db_session,
        manual_account.id,
        ticker="PRE",
        net_pnl=Decimal("10"),
        entry_time=datetime(2026, 8, 1, 13, 55, tzinfo=UTC),  # 09:55 NY
        exit_time=datetime(2026, 8, 1, 14, 8, tzinfo=UTC),  # 10:08 NY
    )
    before.r_multiple = Decimal("1")
    after = make_trade(
        db_session,
        manual_account.id,
        ticker="POST",
        net_pnl=Decimal("20"),
        entry_time=datetime(2026, 8, 1, 14, 1, tzinfo=UTC),  # 10:01 NY
        exit_time=datetime(2026, 8, 1, 14, 8, tzinfo=UTC),
    )
    after.r_multiple = Decimal("2")
    db_session.commit()
    rule = create_candidate_rule(db_session, {"name": "cutoff", "filters": {}})
    rule.cutoff_at = cutoff
    db_session.commit()
    from app.services.dashboard_service import DashboardFilters

    ev = evaluate_rule(db_session, rule.id, ResearchScope(global_filters=DashboardFilters()))
    assert ev["forward_membership"] == "entry_time_utc > cutoff_at"
    assert before.id in ev["research"]["trade_ids"]
    assert before.id not in ev["forward"]["trade_ids"]
    assert after.id in ev["forward"]["trade_ids"]
    assert after.id not in ev["research"]["trade_ids"]


def test_candidate_rule_forward_sample(db_session, manual_account):
    before = make_trade(
        db_session,
        manual_account.id,
        ticker="FWD",
        net_pnl=Decimal("10"),
        entry_time=_ny_utc(2026, 7, 1, 9, 40),
        exit_time=_ny_utc(2026, 7, 1, 10, 0),
    )
    before.r_multiple = Decimal("1")
    db_session.commit()
    rule = create_candidate_rule(
        db_session,
        {"name": "A+ test", "filters": {"weekday": "WED"}, "research_mode": "PRE_ENTRY_ONLY"},
    )
    rule.cutoff_at = datetime(2026, 8, 1, tzinfo=UTC)
    db_session.commit()
    after = make_trade(
        db_session,
        manual_account.id,
        ticker="FWD2",
        net_pnl=Decimal("20"),
        entry_time=_ny_utc(2026, 9, 2, 10, 20),
        exit_time=_ny_utc(2026, 9, 2, 11, 0),
    )
    after.r_multiple = Decimal("2")
    db_session.commit()
    from app.services.dashboard_service import DashboardFilters

    scope = ResearchScope(global_filters=DashboardFilters())
    ev = evaluate_rule(db_session, rule.id, scope)
    assert after.id in ev["forward"]["trade_ids"]
    assert after.id not in ev["research"]["trade_ids"]
    assert before.id in ev["research"]["trade_ids"]


def test_retrospective_rule_cannot_forward_test(db_session):
    from app.services.research.timing import RetrospectiveRuleError

    with pytest.raises(RetrospectiveRuleError) as exc:
        create_candidate_rule(
            db_session,
            {"name": "mfe rule", "filters": {"mfe_r_bucket": "1_1_5"}, "status": "FORWARD_TESTING"},
        )
    assert RetrospectiveRuleError.code == "RETROSPECTIVE_RULE_NOT_FORWARD_TESTABLE"
    assert "mfe_r_bucket" in exc.value.keys

    research = create_candidate_rule(
        db_session,
        {"name": "mfe research", "filters": {"mfe_r_bucket": "1_1_5"}, "status": "RESEARCH"},
    )
    assert research.status == "RESEARCH"
    with pytest.raises(RetrospectiveRuleError):
        revise_candidate_rule(db_session, research.id, {"status": "FORWARD_TESTING"})
    db_session.refresh(research)
    assert research.status == "RESEARCH"
    assert research.rule_version == 1


def test_api_rejects_retrospective_forward_testing():
    bad = client.post(
        "/api/research/candidate-rules",
        json={"name": "eod", "filters": {"rvol_bucket": "5_10"}, "status": "FORWARD_TESTING"},
    )
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "RETROSPECTIVE_RULE_NOT_FORWARD_TESTABLE"


def test_pre_entry_rule_can_forward_test(db_session):
    row = create_candidate_rule(
        db_session,
        {"name": "A+", "filters": {"setup_quality": "A+"}, "status": "FORWARD_TESTING"},
    )
    assert row.status == "FORWARD_TESTING"


def test_heatmap_ticker_top_n(db_session, manual_account):
    rows = []
    for i in range(25):
        rows.append(
            _trade(
                db_session,
                manual_account.id,
                i,
                r=1,
                pnl=10,
                ticker=f"TK{i:02d}",
                features={"symbol": f"TK{i:02d}", "setup_quality": "A+"},
            )
        )
    hm = build_heatmap(rows, "symbol", "setup_quality", "trade_count", "PRE_ENTRY_ONLY")
    xs = {c["x"] for c in hm["cells"]}
    assert "other" in xs
    assert hm["top_n"]["unique_x_before"] == 25
    assert hm["top_n"]["unique_x_after"] == 21
    assert hm["top_n"]["other_trade_count"] == 5
    named = [c for c in hm["cells"] if c["x"] != "other"]
    assert len(named) == 20
    other = next(c for c in hm["cells"] if c["x"] == "other")
    assert other["is_other"] is True
    assert other["filters"] is None
    assert other["trade_count"] == 5


def test_candidate_rule_revise_creates_version(db_session):
    rule = create_candidate_rule(db_session, {"name": "v1", "filters": {"setup_quality": "A+"}})
    original_json = rule.filter_json
    original_cutoff = rule.cutoff_at
    v2 = revise_candidate_rule(db_session, rule.id, {"filters": {"setup_quality": "A"}})
    db_session.refresh(rule)
    assert rule.filter_json == original_json
    assert rule.rule_version == 1
    assert v2.rule_version == 2
    assert v2.parent_id == rule.id
    assert v2.cutoff_at == original_cutoff
    assert '"A+"' in rule.filter_json


# --- 109–111 stats ---


def test_bootstrap_determinism():
    vals = [Decimal("1"), Decimal("0.5"), Decimal("-0.2"), Decimal("2"), Decimal("0.1")] * 3
    a = bootstrap_mean_ci(vals, seed=20260902, iterations=200)
    b = bootstrap_mean_ci(vals, seed=20260902, iterations=200)
    assert a["ci_low"] == b["ci_low"]
    assert a["ci_high"] == b["ci_high"]
    assert a["statistics_version"] == "1"


def test_wilson_interval_known():
    # 8 wins / 2 losses. Wilson 95% ≈ [0.4902, 0.9433]
    w = wilson_interval(8, 2)
    assert w["available"] is True
    assert w["n"] == 10
    assert w["p"] == pytest.approx(0.8)
    assert w["ci_low"] == pytest.approx(0.49016, abs=0.002)
    assert w["ci_high"] == pytest.approx(0.94333, abs=0.002)
    be = wilson_interval(0, 0)
    assert be["available"] is False


def test_sample_minimum_disables_stats():
    small = bootstrap_mean_ci([Decimal("1")] * 5)
    assert small["available"] is False
    assert small["reason"] == "INSUFFICIENT_SAMPLE"
    assert sample_size_label(5) == "N<10"
    assert sample_size_label(15) == "N10-19"
    assert sample_size_label(25) == "N20-49"
    assert sample_size_label(60) == "N50-99"
    assert sample_size_label(120) == "N100+"
    assert spearman([1, 2], [2, 1])["reason"] == "INSUFFICIENT_SAMPLE"


# --- 112–113 coverage ---


def test_coverage_percentages(db_session, manual_account):
    universe = []
    for i in range(100):
        at = _trade(db_session, manual_account.id, i, r=1 if i < 70 else None, pnl=10)
        if i < 80:
            at.features["_signal_linked"] = "true"
        if i < 96:
            at.features["_market_enriched"] = "true"
        if i < 60:
            at.numeric["mfe_r"] = Decimal("1")
        universe.append(at)
    cov = coverage_panel(universe, universe[:50], universe[50:])
    assert cov["base_trades"] == 100
    assert Decimal(cov["r_available_pct"]) == Decimal("70")
    assert Decimal(cov["signal_available_pct"]) == Decimal("80")
    assert Decimal(cov["market_available_pct"]) == Decimal("96")
    assert Decimal(cov["excursion_available_pct"]) == Decimal("60")


def test_unequal_coverage_warning(db_session, manual_account):
    a = [_trade(db_session, manual_account.id, i, r=1, pnl=10) for i in range(20)]
    for at in a:
        at.numeric["mfe_r"] = Decimal("1")
    b = [_trade(db_session, manual_account.id, 100 + i, r=1, pnl=10) for i in range(20)]
    for i, at in enumerate(b):
        if i < 10:
            at.numeric["mfe_r"] = Decimal("1")
    cov = coverage_panel(a + b, a, b)
    assert cov["unequal_coverage_warning"]


# --- 114 multifactor ---


def test_multifactor_grouping_and_cap(db_session, manual_account):
    rows = []
    combos = [
        ("A+", "5_10", "20_30"),
        ("A+", "5_10", "20_30"),
        ("A+", "10_20", "30_40"),
        ("A", "5_10", "20_30"),
    ]
    for i, (q, rv, ret) in enumerate(combos):
        rows.append(
            _trade(
                db_session,
                manual_account.id,
                i,
                r=1,
                features={"setup_quality": q, "signal_rvol_bucket": rv, "retracement_bucket": ret},
            )
        )
    out = build_multifactor(rows, ["setup_quality", "signal_rvol_bucket", "retracement_bucket"], "PRE_ENTRY_ONLY")
    assert out["blocked"] is False
    assert out["n_groups"] == 3
    pair = next(r for r in out["rows"] if r["setup_quality"] == "A+" and r["signal_rvol_bucket"] == "5_10")
    assert pair["trade_count"] == 2

    from app.config import settings

    original = settings.research_max_groups
    settings.research_max_groups = 1
    try:
        blocked = build_multifactor(rows, ["setup_quality", "signal_rvol_bucket", "retracement_bucket"], "PRE_ENTRY_ONLY")
        assert blocked["blocked"] is True
        forced = build_multifactor(rows, ["setup_quality", "signal_rvol_bucket", "retracement_bucket"], "PRE_ENTRY_ONLY", force=True)
        assert forced["blocked"] is False
    finally:
        settings.research_max_groups = original


# --- 115 saved view ---


def test_saved_view_roundtrip(db_session):
    row = save_view(
        db_session,
        {
            "name": "A+ vs A",
            "research_mode": "PRE_ENTRY_ONLY",
            "global_scope": {"direction": "LONG"},
            "cohort_a": {"name": "A+", "filters": {"setup_quality": "A+"}},
            "cohort_b": {"name": "A", "filters": {"setup_quality": "A"}},
            "visualization": {"tab": "scatter", "xVar": "signal_rvol", "yVar": "actual_r"},
        },
    )
    loaded = get_view(db_session, row.id)
    assert loaded["global_scope"]["direction"] == "LONG"
    assert loaded["cohort_a"]["filters"]["setup_quality"] == "A+"
    assert loaded["cohort_b"]["filters"]["setup_quality"] == "A"
    assert loaded["visualization"]["xVar"] == "signal_rvol"
    assert loaded["research_mode"] == "PRE_ENTRY_ONLY"


def test_pattern_snapshot_immutable(db_session):
    row = star_pattern(
        db_session,
        {"name": "cell", "filters": {"setup_quality": "A+"}, "metrics": {"average_r": "0.73"}, "sample_size": 42},
    )
    assert row.metrics_json
    assert "0.73" in row.metrics_json


def test_cohort_hash_ignores_name():
    from app.services.dashboard_service import DashboardFilters

    scope = ResearchScope(global_filters=DashboardFilters())
    h1 = cohort_hash(scope, CohortDef(name="Foo", filters={"setup_quality": "A+"}))
    h2 = cohort_hash(scope, CohortDef(name="Bar", filters={"setup_quality": "A+"}))
    assert h1 == h2


def test_difference_ci_disabled_when_overlap():
    table = compare_summaries({"average_r": "1"}, {"average_r": "0"}, overlap_count=2, independent=False)
    assert table["mean_r_difference"]["available"] is False
    assert "overlap" in table["mean_r_difference"]["message"].lower()


def test_bootstrap_difference_independent():
    a = [Decimal("1")] * 12
    b = [Decimal("0")] * 12
    d = bootstrap_difference_ci(a, b, seed=20260902, iterations=200)
    assert d["available"] is True
    assert d["observed"] == pytest.approx(1.0)


def test_variables_registry_timing_counts():
    pre = [v for v in RESEARCH_VARIABLES if v["allowed_pre_entry"]]
    retro = [v for v in RESEARCH_VARIABLES if not v["allowed_pre_entry"]]
    assert len(RESEARCH_VARIABLES) >= 20
    assert len(pre) >= 10
    assert len(retro) >= 6
    assert any(v["key"] == "signal_rvol" and v["allowed_pre_entry"] for v in RESEARCH_VARIABLES)
    assert any(v["key"] == "rvol50_eod" and not v["allowed_pre_entry"] for v in RESEARCH_VARIABLES)
    assert any(v["key"] == "actual_r" and not v["allowed_pre_entry"] for v in RESEARCH_VARIABLES)
    assert any(v["key"] == "mfe_r" and not v["allowed_pre_entry"] for v in RESEARCH_VARIABLES)


def test_api_variables_and_lookahead(db_session):
    r = client.get("/api/research/variables")
    assert r.status_code == 200
    assert "Exploring many combinations" in r.json()["multiple_comparison_warning"]
    body = {
        "research_mode": "PRE_ENTRY_ONLY",
        "cohort_a": {"filters": {"mfe_r_bucket": "1_1_5"}},
        "cohort_b": {"filters": {}},
    }
    bad = client.post("/api/research/compare", json=body)
    assert bad.status_code == 400
    assert bad.json()["detail"]["code"] == "LOOKAHEAD_FILTER"


def test_load_universe_attach_numeric(db_session, manual_account):
    t = make_trade(db_session, manual_account.id, net_pnl=Decimal("20"), ticker="NUM")
    t.r_multiple = Decimal("1.5")
    db_session.commit()
    from app.services.dashboard_service import DashboardFilters

    rows = load_universe(db_session, ResearchScope(global_filters=DashboardFilters()))
    match = next(at for at in rows if at.trade.id == t.id)
    assert match.numeric["actual_r"] == Decimal("1.5")


# --- performance (in-memory, no per-cell SQL) ---


def test_10k_standardized_research_matrix(db_session, manual_account):
    """One 10k fully annotated universe. Times are reported; ceiling is pathological only."""
    import time
    from app.db.models.trade import Trade

    n = 10_000
    base = datetime(2026, 1, 5, 14, 30, tzinfo=UTC)
    trades = []
    for i in range(n):
        entry = base + timedelta(minutes=i)
        trades.append(
            Trade(
                account_id=manual_account.id,
                source_type="TRADINGVIEW_MANUAL",
                trade_fingerprint=f"r9-10k-{i}",
                ticker=f"S{i % 40}",
                direction="LONG",
                entry_time_utc=entry,
                exit_time_utc=entry + timedelta(minutes=5),
                avg_entry_price=Decimal("10"),
                avg_exit_price=Decimal("11"),
                quantity=Decimal("100"),
                net_pnl=Decimal("20") if i % 3 else Decimal("-10"),
                gross_pnl=Decimal("20") if i % 3 else Decimal("-10"),
                holding_seconds=300,
                status="CLOSED",
                r_multiple=Decimal("0.2") if i % 5 else Decimal("1.1"),
            )
        )
    db_session.add_all(trades)
    db_session.commit()

    t0 = time.perf_counter()
    loaded = db_session.query(Trade).filter(Trade.trade_fingerprint.like("r9-10k-%")).all()
    annotated = _annotate_trades(db_session, loaded)
    attach_numeric(db_session, annotated)
    qualities = ["A+", "A", "Other"]
    rvols = ["2_5", "5_10", "10_20", "20_plus"]
    retr = ["20_30", "30_40", "40_50"]
    for i, at in enumerate(annotated):
        at.features["setup_quality"] = qualities[i % 3]
        at.features["signal_rvol_bucket"] = rvols[i % 4]
        at.features["retracement_bucket"] = retr[i % 3]
        at.numeric["signal_rvol"] = Decimal(str((i % 20) + 1))
        at.numeric["mfe_r"] = Decimal("1") if i % 4 == 0 else None
    load_t = time.perf_counter() - t0
    assert len(annotated) == n

    t0 = time.perf_counter()
    split = split_ab(
        annotated,
        CohortDef(filters={"setup_quality": "A+"}),
        CohortDef(filters={"setup_quality": "A"}),
        "PRE_ENTRY_ONLY",
    )
    compare_summaries(summarize_cohort(split["a"]), summarize_cohort(split["b"]), overlap_count=0, independent=True)
    compare_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    build_scatter(annotated, "signal_rvol", "actual_r", "PRE_ENTRY_ONLY")
    scatter_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    build_heatmap(annotated, "signal_rvol_bucket", "retracement_bucket", "average_r", "PRE_ENTRY_ONLY")
    heat_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    build_rolling(annotated, metric="average_r", window=20)
    roll_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    build_distribution(split["a"], split["b"], "actual_r")
    dist_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    robustness_means(annotated)
    robust_t = time.perf_counter() - t0

    t0 = time.perf_counter()
    build_multifactor(annotated, ["setup_quality", "signal_rvol_bucket", "retracement_bucket"], "PRE_ENTRY_ONLY")
    mf_t = time.perf_counter() - t0

    r_vals = [at.numeric["actual_r"] for at in annotated if at.numeric.get("actual_r") is not None]
    t0 = time.perf_counter()
    bootstrap_mean_ci(r_vals, iterations=2000)
    boot_t = time.perf_counter() - t0

    print(
        "STEP9_10K_MATRIX "
        f"load={load_t:.3f}s compare={compare_t:.3f}s scatter={scatter_t:.3f}s "
        f"heatmap={heat_t:.3f}s rolling={roll_t:.3f}s distribution={dist_t:.3f}s "
        f"robustness={robust_t:.3f}s multifactor={mf_t:.3f}s bootstrap_n={len(r_vals)}={boot_t:.3f}s"
    )
    # Pathological ceiling only — not a 1s product target.
    for label, elapsed in (
        ("load", load_t),
        ("compare", compare_t),
        ("scatter", scatter_t),
        ("heatmap", heat_t),
        ("rolling", roll_t),
        ("distribution", dist_t),
        ("robustness", robust_t),
        ("multifactor", mf_t),
        ("bootstrap", boot_t),
    ):
        assert elapsed < 60, f"{label} took {elapsed:.2f}s"
