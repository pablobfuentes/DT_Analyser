"""Parse Research Lab request bodies into scope + cohorts."""

from __future__ import annotations

from datetime import date

from app.services.dashboard_service import DashboardFilters
from app.services.research.cohorts import CohortDef, ResearchScope


def _date(v) -> date | None:
    if not v:
        return None
    if isinstance(v, date):
        return v
    return date.fromisoformat(str(v)[:10])


def parse_scope(body: dict) -> ResearchScope:
    g = body.get("global") or body.get("global_scope") or {}
    gf = DashboardFilters(
        start_date=_date(g.get("start_date") or g.get("startDate")),
        end_date=_date(g.get("end_date") or g.get("endDate")),
        account_id=int(g["account_id"]) if g.get("account_id") not in (None, "", "ALL") else None,
        source_type=(g.get("source_type") or g.get("source") or None),
        direction=(g.get("direction") or None),
        ticker=(g.get("ticker") or None) or None,
    )
    if gf.source_type in ("ALL", ""):
        gf.source_type = None
    if gf.direction in ("ALL", ""):
        gf.direction = None
    return ResearchScope(
        global_filters=gf,
        research_mode=str(body.get("research_mode") or "PRE_ENTRY_ONLY"),
        pine_scope=str(body.get("pine_scope") or "REALTIME"),
        include_suggested_signals=bool(body.get("include_suggested_signals")),
        include_partial_feed=bool(body.get("include_partial_feed")),
        quality_mode=str(body.get("quality_mode") or "RECOMMENDED"),
        exclusive=bool(body.get("exclusive") or body.get("force_exclusive")),
        strategy_version=g.get("strategy_version") or body.get("strategy_version"),
    )


def parse_cohort(body: dict, key: str, default_name: str) -> CohortDef:
    raw = body.get(key) or {}
    filters = raw.get("filters") or {}
    filters = {k: str(v) for k, v in filters.items() if v not in (None, "")}
    return CohortDef(name=raw.get("name") or default_name, filters=filters)
