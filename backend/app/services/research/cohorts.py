"""Load annotated universe and apply Graph-equivalent cohort filters."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import settings
from app.services.dashboard_service import DashboardFilters, build_closed_trades_query
from app.services.reports.features import AnnotatedTrade
from app.services.reports.filters import TradeFilterSet, apply_exploration
from app.services.reports.service import _annotate_trades
from app.services.research import STATISTICS_VERSION
from app.services.research.numeric import attach_numeric
from app.services.research.timing import LookaheadFilterError, cohort_is_retrospective, validate_cohort_filters
from app.utils.analytics import ny_date_from_utc


CALC_VERSIONS = {
    "statistics_version": STATISTICS_VERSION,
    "research_calc": "1",
}


@dataclass
class ResearchScope:
    global_filters: DashboardFilters
    research_mode: str = "PRE_ENTRY_ONLY"
    pine_scope: str = "REALTIME"
    include_suggested_signals: bool = False
    include_partial_feed: bool = False
    quality_mode: str = "RECOMMENDED"  # RECOMMENDED | INCLUDE_PARTIAL | ALL
    exclusive: bool = False
    strategy_version: str | None = None


@dataclass
class CohortDef:
    name: str = "Cohort"
    filters: dict[str, str] = field(default_factory=dict)


def _scope_filter_set(scope: ResearchScope) -> TradeFilterSet:
    exploration = {}
    if scope.strategy_version:
        exploration["strategy_version"] = scope.strategy_version
    return TradeFilterSet(
        global_filters=scope.global_filters,
        exploration=exploration,
        include_partial_feed=scope.include_partial_feed or scope.quality_mode == "INCLUDE_PARTIAL",
        pine_scope=scope.pine_scope,
        include_suggested_signals=scope.include_suggested_signals,
    )


def load_universe(db: Session, scope: ResearchScope) -> list[AnnotatedTrade]:
    filt = _scope_filter_set(scope)
    trades = build_closed_trades_query(db, filt.global_filters).all()
    annotated = _annotate_trades(db, trades, filt)
    if filt.exploration:
        annotated = [at for at in annotated if apply_exploration(at.features, filt)]
    attach_numeric(db, annotated)
    return annotated


def apply_cohort(
    universe: list[AnnotatedTrade],
    cohort: CohortDef,
    research_mode: str,
) -> tuple[list[AnnotatedTrade], bool]:
    validate_cohort_filters(cohort.filters, research_mode)
    if not cohort.filters:
        return list(universe), cohort_is_retrospective(cohort.filters)
    filt = TradeFilterSet(exploration=dict(cohort.filters))
    members = [at for at in universe if apply_exploration(at.features, filt)]
    return members, cohort_is_retrospective(cohort.filters)


def split_ab(
    universe: list[AnnotatedTrade],
    cohort_a: CohortDef,
    cohort_b: CohortDef,
    research_mode: str,
    exclusive: bool = False,
) -> dict:
    a, a_retro = apply_cohort(universe, cohort_a, research_mode)
    b, b_retro = apply_cohort(universe, cohort_b, research_mode)
    ids_a = {at.trade.id for at in a}
    ids_b = {at.trade.id for at in b}
    overlap = sorted(ids_a & ids_b)
    if exclusive and overlap:
        drop = set(overlap)
        a = [at for at in a if at.trade.id not in drop]
        b = [at for at in b if at.trade.id not in drop]
        ids_a = {at.trade.id for at in a}
        ids_b = {at.trade.id for at in b}
        overlap = []
    return {
        "a": a,
        "b": b,
        "overlap_ids": overlap,
        "overlap_count": len(overlap),
        "independent": len(overlap) == 0,
        "a_retrospective": a_retro,
        "b_retrospective": b_retro,
        "exclusive_applied": exclusive,
    }


def cohort_hash(scope: ResearchScope, cohort: CohortDef) -> str:
    payload = {
        "global": {
            "start": scope.global_filters.start_date.isoformat() if scope.global_filters.start_date else None,
            "end": scope.global_filters.end_date.isoformat() if scope.global_filters.end_date else None,
            "account_id": scope.global_filters.account_id,
            "source_type": scope.global_filters.source_type,
            "direction": scope.global_filters.direction,
            "ticker": scope.global_filters.ticker,
        },
        "filters": dict(sorted(cohort.filters.items())),
        "research_mode": scope.research_mode,
        "pine_scope": scope.pine_scope,
        "quality_mode": scope.quality_mode,
        "include_suggested": scope.include_suggested_signals,
        "versions": CALC_VERSIONS,
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def numeric_of(at: AnnotatedTrade, key: str) -> Decimal | None:
    nums = getattr(at, "numeric", {}) or {}
    return nums.get(key)


def trade_ids(rows: list[AnnotatedTrade]) -> list[int]:
    return [at.trade.id for at in rows]


def ny_dates(rows: list[AnnotatedTrade]):
    out = []
    for at in rows:
        d = getattr(at, "ny_date", None) or ny_date_from_utc(at.trade.exit_time_utc or at.trade.entry_time_utc)
        out.append(d)
    return out
