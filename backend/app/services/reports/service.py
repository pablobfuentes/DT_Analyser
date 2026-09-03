"""Reports service — load, annotate, filter, aggregate."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.trade import Trade
from app.db.models.trade_execution import TradeExecution
from app.db.models.market_data import InstrumentDayFeature
from app.market_data.registry import provider_status
from app.services.dashboard_service import build_closed_trades_query
from app.services.reports.aggregation import aggregate_dimension, best_worst
from app.services.reports.features import AnnotatedTrade, apply_behavior_features, compute_base_features
from app.services.reports.filters import TradeFilterSet, apply_exploration, exploration_param_for_feature
from app.services.reports.registry import FUTURE_SECTIONS, LABEL_MAPS, METRICS, REPORT_DEFINITIONS, SECTIONS
from app.services.reports.config import EXECUTION_SECTION, MARKET_SECTION, RISK_SECTION, STRATEGY_SECTION
from app.utils.analytics import classify_outcome, decimal_str, effective_realized_pnl


def _load_exec_meta(db: Session, trade_ids: list[int]) -> dict[int, dict]:
    if not trade_ids:
        return {}
    rows = (
        db.query(
            TradeExecution.trade_id,
            TradeExecution.role,
            func.count(TradeExecution.execution_id),
        )
        .filter(TradeExecution.trade_id.in_(trade_ids))
        .group_by(TradeExecution.trade_id, TradeExecution.role)
        .all()
    )
    by_trade: dict[int, dict[str, int]] = defaultdict(lambda: {"ENTRY": 0, "EXIT": 0})
    for tid, role, cnt in rows:
        by_trade[tid][role] = cnt

    result = {}
    for tid, counts in by_trade.items():
        total = counts["ENTRY"] + counts["EXIT"]
        entry_style = "scale_in" if counts["ENTRY"] > 1 else "single"
        exit_style = "scale_out" if counts["EXIT"] > 1 else "single"
        fc = str(total) if total <= 4 else "5_plus"
        result[tid] = {"fill_count": fc, "entry_style": entry_style, "exit_style": exit_style}
    return result


def _annotate_trades(
    db: Session, trades: list[Trade], filt: TradeFilterSet | None = None
) -> list[AnnotatedTrade]:
    include_partial_feed = filt.include_partial_feed if filt else False
    meta = _load_exec_meta(db, [t.id for t in trades])
    annotated = []
    for t in trades:
        rp = effective_realized_pnl(t)
        feats = compute_base_features(t, meta.get(t.id))
        annotated.append(
            AnnotatedTrade(
                trade=t,
                pnl=rp.pnl,
                outcome=classify_outcome(rp.pnl),
                features=feats,
            )
        )
    apply_behavior_features(annotated)
    from app.services.reports.market_features import apply_market_features

    apply_market_features(db, annotated, include_partial_feed=include_partial_feed)
    from app.services.reports.excursion_features import apply_excursion_features

    apply_excursion_features(db, annotated)
    from app.services.reports.signal_features import apply_signal_features

    pine_scope = filt.pine_scope if filt else "REALTIME"
    include_suggested = filt.include_suggested_signals if filt else False
    apply_signal_features(
        db, annotated, include_suggested=include_suggested, pine_scope=pine_scope
    )
    from app.services.reports.risk_features import apply_risk_features

    apply_risk_features(db, annotated)
    return annotated


def get_reports(db: Session, filt: TradeFilterSet, min_sample: int = 1) -> dict:
    q = build_closed_trades_query(db, filt.global_filters)
    trades = q.all()
    annotated = _annotate_trades(db, trades, filt)
    filtered = [at for at in annotated if apply_exploration(at.features, filt)]

    section_reports: dict[str, list] = defaultdict(list)

    for defn in REPORT_DEFINITIONS:
        feature = defn["feature"]
        if feature == "_sequence":
            buckets = _sequence_report(filtered)
        else:
            label_map = LABEL_MAPS.get(feature, {})
            ms = defn.get("min_sample_default", min_sample)
            buckets = aggregate_dimension(
                filtered,
                feature,
                label_map=label_map,
                sort_keys=defn.get("sort"),
                min_sample=ms,
                exclude_missing=bool(defn.get("exclude_missing")),
            )
            if defn.get("limit"):
                if defn.get("default_metric") == "net_pnl":
                    buckets.sort(key=lambda b: Decimal(b["net_pnl"]), reverse=True)
                buckets = buckets[: defn["limit"]]

        bw = best_worst(buckets, min_sample=max(1, defn.get("min_sample_default", 1)))
        report_payload = {
            "key": defn["key"],
            "title": defn["title"],
            "section": defn["section"],
            "available": True,
            "default_metric": defn.get("default_metric", "net_pnl"),
            "chart_type": defn.get("chart_type", "bar"),
            "buckets": buckets,
            "best_bucket": bw["best"],
            "worst_bucket": bw["worst"],
            "filter_dimension": exploration_param_for_feature(feature),
            "feature_key": feature,
            "availability_timing": defn.get("availability_timing"),
            "description": defn.get("description"),
        }
        if defn.get("availability_timing") and feature != "_sequence":
            report_payload["coverage"] = _coverage_payload(filtered, feature)
        section_reports[defn["section"]].append(report_payload)

    sections = []
    for key, label, available, *rest in [(s[0], s[1], s[2], s[3] if len(s) > 3 else None) for s in SECTIONS if s[2]]:
        sections.append({
            "key": key,
            "label": label,
            "available": available,
            "reports": section_reports.get(key, []),
        })

    market_key, market_label, market_requires = MARKET_SECTION
    market_ready = _market_section_ready(db)
    sections.append({
        "key": market_key,
        "label": market_label,
        "available": market_ready,
        "requires": None if market_ready else market_requires,
        "reports": section_reports.get(market_key, []) if market_ready else [],
    })

    exec_key, exec_label, exec_requires = EXECUTION_SECTION
    exec_ready = _execution_section_ready(db)
    sections.append({
        "key": exec_key,
        "label": exec_label,
        "available": exec_ready,
        "requires": None if exec_ready else exec_requires,
        "reports": section_reports.get(exec_key, []) if exec_ready else [],
    })

    strategy_key, strategy_label, strategy_requires = STRATEGY_SECTION
    strategy_ready = _strategy_section_ready(db)
    strategy_reports = section_reports.get(strategy_key, []) if strategy_ready else []
    mixed = _mixed_strategy_versions(filtered) if strategy_ready else None
    realtime_in_cohort = sum(1 for at in filtered if at.features.get("_signal_linked") == "true")
    sections.append({
        "key": strategy_key,
        "label": strategy_label,
        "available": strategy_ready,
        "requires": None if strategy_ready else strategy_requires,
        "reports": strategy_reports,
        "pine_scope": filt.pine_scope,
        "include_suggested_signals": filt.include_suggested_signals,
        "mixed_strategy_versions": mixed,
        "realtime_linked_in_cohort": realtime_in_cohort,
        "empty_realtime_message": (
            "No realtime Pine signals in this cohort"
            if strategy_ready and filt.pine_scope == "REALTIME" and realtime_in_cohort == 0
            else None
        ),
        "opening_fade": {
            "premarket_rally_pct": {"status": "UNAVAILABLE", "reason": "SIGNALLOG emits FIRST_PULLBACK only; no typed Opening Fade fields."},
            "reversal_range_factor": {"status": "UNAVAILABLE", "reason": "No OPENING_FADE strategy_key events in current Pine producer."},
            "reversal_volume_factor": {"status": "UNAVAILABLE", "reason": "No OPENING_FADE strategy_key events in current Pine producer."},
            "distance_from_hod": {"status": "UNAVAILABLE", "reason": "No OPENING_FADE strategy_key events in current Pine producer."},
            "retracement_at_armed": {"status": "PARTIAL", "reason": "First Pullback retracement_pct is logged; Opening Fade-specific ARMED retracement is not a separate field."},
            "target_retracement": {"status": "UNAVAILABLE", "reason": "Not emitted by SIGNALLOG."},
        },
    })

    risk_key, risk_label, risk_requires = RISK_SECTION
    r_qualified = sum(1 for at in filtered if at.features.get("_r_qualified") == "true")
    sections.append({
        "key": risk_key,
        "label": risk_label,
        "available": True,
        "requires": None,
        "reports": section_reports.get(risk_key, []),
        "r_qualified_in_cohort": r_qualified,
        "empty_r_message": (
            "No R-qualified trades in current cohort" if filtered and r_qualified == 0 else None
        ),
    })

    sections.extend(FUTURE_SECTIONS)

    return {
        "matching_trade_count": len(filtered),
        "active_exploration_filters": filt.exploration,
        "global_filters": {
            "start_date": filt.global_filters.start_date.isoformat() if filt.global_filters.start_date else None,
            "end_date": filt.global_filters.end_date.isoformat() if filt.global_filters.end_date else None,
            "account_id": filt.global_filters.account_id,
            "source_type": filt.global_filters.source_type,
            "direction": filt.global_filters.direction,
            "ticker": filt.global_filters.ticker,
        },
        "pine_scope": filt.pine_scope,
        "include_suggested_signals": filt.include_suggested_signals,
        "metrics": METRICS,
        "sections": sections,
        "market_data": {
            **provider_status(),
            "include_partial_feed": filt.include_partial_feed,
            "cohort_market_available": sum(
                1 for at in filtered if at.features.get("_market_enriched") == "true"
            ),
        },
    }


def _coverage_payload(filtered: list[AnnotatedTrade], feature: str) -> dict:
    matching = len(filtered)
    reasons: dict[str, int] = {}
    with_data = 0
    for at in filtered:
        val = at.features.get(feature)
        if val not in (None, "", "unknown"):
            with_data += 1
            continue
        reason = at.features.get(f"_skip_{feature}")
        if not reason:
            if at.features.get("_signal_linked") != "true" and feature in (
                "strategy_key",
                "strategy_version",
                "signal_origin",
                "setup_quality",
                "signal_gap_bucket",
                "signal_rvol_bucket",
                "impulse_bucket",
                "retracement_bucket",
                "context_5m",
                "above_vwap",
                "above_ema9",
                "volume_confirmed",
                "suggested_shares_bucket",
                "planned_position_value_bucket",
                "planned_exposure_bucket",
                "mechanical_exit_reason",
            ):
                reason = "MISSING_SIGNAL"
            elif at.features.get("_market_enriched") != "true":
                reason = "MISSING_ENRICHMENT"
            else:
                reason = at.features.get("_inst_quality") or "MISSING_DATA"
        reasons[reason] = reasons.get(reason, 0) + 1
    excluded = matching - with_data
    return {
        "matching_trades": matching,
        "data_available": with_data,
        "coverage_pct": round(with_data / matching * 100, 1) if matching else 0.0,
        "excluded": excluded,
        "exclusion_reasons": reasons,
        "scope": "current_cohort",
    }


def _execution_section_ready(db: Session) -> bool:
    from app.services.reports.excursion_features import excursion_section_ready

    return excursion_section_ready(db)


def _strategy_section_ready(db: Session) -> bool:
    from app.db.models.signal import Signal

    return db.query(Signal.id).limit(1).first() is not None


def _mixed_strategy_versions(filtered: list[AnnotatedTrade]) -> dict | None:
    counts: dict[str, int] = defaultdict(int)
    originals: dict[str, str] = {}
    for at in filtered:
        if at.features.get("_signal_linked") != "true":
            continue
        key = at.features.get("strategy_version_normalized") or at.features.get("strategy_version") or ""
        if not key:
            continue
        counts[key] += 1
        originals.setdefault(key, at.features.get("strategy_version") or key)
    if len(counts) <= 1:
        return None
    return {
        "warning": "MIXED STRATEGY VERSIONS",
        "versions": [
            {"normalized": k, "original": originals[k], "sample_size": n} for k, n in sorted(counts.items())
        ],
    }


def _market_section_ready(db: Session) -> bool:
    if provider_status()["configured"]:
        return True
    benchmark = settings.market_benchmark.upper()
    return (
        db.query(InstrumentDayFeature)
        .filter(InstrumentDayFeature.symbol == benchmark)
        .first()
        is not None
    )


def _sequence_report(filtered: list[AnnotatedTrade]) -> list[dict]:
    ordered = sorted(filtered, key=lambda x: (x.trade.exit_time_utc or x.trade.entry_time_utc, x.trade.id))
    buckets = []
    for i, at in enumerate(ordered):
        buckets.append({
            "key": str(at.trade.id),
            "label": str(i + 1),
            "trade_count": 1,
            "wins": 1 if at.outcome == "WIN" else 0,
            "losses": 1 if at.outcome == "LOSS" else 0,
            "breakeven": 1 if at.outcome == "BREAKEVEN" else 0,
            "net_pnl": decimal_str(at.pnl),
            "avg_trade": decimal_str(at.pnl),
            "win_rate": None,
            "avg_winner": decimal_str(at.pnl) if at.outcome == "WIN" else None,
            "avg_loser": decimal_str(at.pnl) if at.outcome == "LOSS" else None,
        })
    return buckets
