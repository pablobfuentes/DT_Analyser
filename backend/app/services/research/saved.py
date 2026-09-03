"""Saved cohorts, views, candidate rules, pattern snapshots."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.research import CandidateRule, PatternSnapshot, ResearchView, SavedCohort
from app.services.research.cohorts import CohortDef, ResearchScope, apply_cohort, load_universe
from app.services.research.comparison import summarize_cohort
from app.services.research.timing import assert_forward_testable
from app.utils.analytics import decimal_str


def _now():
    return datetime.now(timezone.utc)


def _dumps(obj) -> str:
    return json.dumps(obj, separators=(",", ":"), sort_keys=True)


def _loads(text: str) -> dict:
    return json.loads(text) if text else {}


def save_cohort(db: Session, name: str, filters: dict, research_mode: str, description: str | None = None) -> SavedCohort:
    row = SavedCohort(name=name, description=description, filter_json=_dumps(filters), research_mode=research_mode)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_cohorts(db: Session) -> list[dict]:
    return [_cohort_dict(r) for r in db.query(SavedCohort).order_by(SavedCohort.id.desc()).all()]


def update_cohort(db: Session, pk: int, **fields) -> SavedCohort:
    row = db.get(SavedCohort, pk)
    if not row:
        raise ValueError("Saved cohort not found")
    if "name" in fields and fields["name"]:
        row.name = fields["name"]
    if "description" in fields:
        row.description = fields["description"]
    if "filters" in fields and fields["filters"] is not None:
        row.filter_json = _dumps(fields["filters"])
    if "research_mode" in fields and fields["research_mode"]:
        row.research_mode = fields["research_mode"]
    db.commit()
    db.refresh(row)
    return row


def delete_cohort(db: Session, pk: int) -> None:
    row = db.get(SavedCohort, pk)
    if row:
        db.delete(row)
        db.commit()


def _cohort_dict(r: SavedCohort) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "filters": _loads(r.filter_json),
        "research_mode": r.research_mode,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def save_view(db: Session, payload: dict) -> ResearchView:
    row = ResearchView(
        name=payload["name"],
        global_scope_json=_dumps(payload.get("global_scope") or {}),
        cohort_a_json=_dumps(payload.get("cohort_a") or {}),
        cohort_b_json=_dumps(payload.get("cohort_b") or {}),
        visualization_json=_dumps(payload.get("visualization") or {}),
        research_mode=payload.get("research_mode") or "PRE_ENTRY_ONLY",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_views(db: Session) -> list[dict]:
    return [_view_dict(r) for r in db.query(ResearchView).order_by(ResearchView.id.desc()).all()]


def get_view(db: Session, pk: int) -> dict:
    row = db.get(ResearchView, pk)
    if not row:
        raise ValueError("Research view not found")
    return _view_dict(row)


def _view_dict(r: ResearchView) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "global_scope": _loads(r.global_scope_json),
        "cohort_a": _loads(r.cohort_a_json),
        "cohort_b": _loads(r.cohort_b_json),
        "visualization": _loads(r.visualization_json),
        "research_mode": r.research_mode,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "updated_at": r.updated_at.isoformat() if r.updated_at else None,
    }


def create_candidate_rule(db: Session, payload: dict) -> CandidateRule:
    filters = payload.get("filters") or {}
    status = payload.get("status") or "RESEARCH"
    assert_forward_testable(filters, status)
    cutoff = _now()
    row = CandidateRule(
        name=payload["name"],
        description=payload.get("description"),
        filter_json=_dumps(filters),
        research_mode=payload.get("research_mode") or "PRE_ENTRY_ONLY",
        research_start=payload.get("research_start"),
        research_end=payload.get("research_end"),
        cutoff_at=cutoff,
        rule_version=1,
        status=status,
        statistics_version=settings.research_statistics_version,
        bootstrap_seed=settings.research_bootstrap_seed,
        bootstrap_iterations=settings.research_bootstrap_iterations,
        notes=payload.get("notes"),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def revise_candidate_rule(db: Session, pk: int, payload: dict) -> CandidateRule:
    """Create version N+1. Original row is not rewritten."""
    prev = db.get(CandidateRule, pk)
    if not prev:
        raise ValueError("Candidate rule not found")
    filters = payload["filters"] if payload.get("filters") is not None else _loads(prev.filter_json)
    status = payload.get("status") or prev.status
    assert_forward_testable(filters, status)
    nxt = CandidateRule(
        name=payload.get("name") or prev.name,
        description=payload.get("description", prev.description),
        filter_json=_dumps(filters),
        research_mode=payload.get("research_mode") or prev.research_mode,
        research_start=payload.get("research_start", prev.research_start),
        research_end=payload.get("research_end", prev.research_end),
        cutoff_at=prev.cutoff_at,
        rule_version=prev.rule_version + 1,
        status=status,
        parent_id=prev.id,
        statistics_version=prev.statistics_version,
        bootstrap_seed=prev.bootstrap_seed,
        bootstrap_iterations=prev.bootstrap_iterations,
        notes=payload.get("notes", prev.notes),
    )
    db.add(nxt)
    db.commit()
    db.refresh(nxt)
    return nxt


def list_rules(db: Session) -> list[dict]:
    return [_rule_dict(r) for r in db.query(CandidateRule).order_by(CandidateRule.id.desc()).all()]


def _rule_dict(r: CandidateRule) -> dict:
    return {
        "id": r.id,
        "name": r.name,
        "description": r.description,
        "filters": _loads(r.filter_json),
        "research_mode": r.research_mode,
        "research_start": r.research_start,
        "research_end": r.research_end,
        "cutoff_at": r.cutoff_at.isoformat() if r.cutoff_at else None,
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "rule_version": r.rule_version,
        "status": r.status,
        "parent_id": r.parent_id,
        "statistics_version": r.statistics_version,
        "bootstrap_seed": r.bootstrap_seed,
        "bootstrap_iterations": r.bootstrap_iterations,
        "notes": r.notes,
    }


def evaluate_rule(db: Session, pk: int, scope: ResearchScope) -> dict:
    rule = db.get(CandidateRule, pk)
    if not rule:
        raise ValueError("Candidate rule not found")
    universe = load_universe(db, scope)
    cohort = CohortDef(name=rule.name, filters=_loads(rule.filter_json))
    members, _ = apply_cohort(universe, cohort, rule.research_mode)
    cutoff = rule.cutoff_at
    if cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=timezone.utc)
    research, forward = [], []
    for at in members:
        # v1: entry_time_utc is the decision timestamp. A trade entered before
        # cutoff is research even if it exits after the rule existed.
        entry_t = at.trade.entry_time_utc
        if entry_t is None:
            continue
        if entry_t.tzinfo is None:
            entry_t = entry_t.replace(tzinfo=timezone.utc)
        if entry_t > cutoff:
            forward.append(at)
        else:
            research.append(at)
    rs = summarize_cohort(research)
    fs = summarize_cohort(forward)
    change = None
    if rs.get("average_r") is not None and fs.get("average_r") is not None:
        change = str(float(fs["average_r"]) - float(rs["average_r"]))
    return {
        "rule": _rule_dict(rule),
        "research": rs,
        "forward": fs,
        "observed_change_avg_r": change,
        "observed_change_label": "Observed Change",
        "forward_membership": "entry_time_utc > cutoff_at",
        "forward_membership_note": (
            "v1 uses trade.entry_time_utc as the decision timestamp. "
            "A later signal-level decision time is a future extension."
        ),
    }


def star_pattern(db: Session, payload: dict) -> PatternSnapshot:
    row = PatternSnapshot(
        name=payload["name"],
        filter_json=_dumps(payload.get("filters") or {}),
        research_mode=payload.get("research_mode") or "PRE_ENTRY_ONLY",
        metrics_json=_dumps(payload.get("metrics") or {}),
        sample_size=int(payload.get("sample_size") or 0),
        date_start=payload.get("date_start"),
        date_end=payload.get("date_end"),
        starred_from=payload.get("starred_from"),
        statistics_version=settings.research_statistics_version,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_patterns(db: Session) -> list[dict]:
    out = []
    for r in db.query(PatternSnapshot).order_by(PatternSnapshot.id.desc()).all():
        out.append(
            {
                "id": r.id,
                "name": r.name,
                "filters": _loads(r.filter_json),
                "research_mode": r.research_mode,
                "original_snapshot": _loads(r.metrics_json),
                "sample_size": r.sample_size,
                "date_start": r.date_start,
                "date_end": r.date_end,
                "starred_from": r.starred_from,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "statistics_version": r.statistics_version,
            }
        )
    return out


def current_vs_snapshot(db: Session, pk: int, scope: ResearchScope) -> dict:
    row = db.get(PatternSnapshot, pk)
    if not row:
        raise ValueError("Pattern not found")
    universe = load_universe(db, scope)
    members, _ = apply_cohort(universe, CohortDef(filters=_loads(row.filter_json)), row.research_mode)
    live = summarize_cohort(members)
    return {
        "original_research_snapshot": _loads(row.metrics_json),
        "current_results": live,
        "sample_size_original": row.sample_size,
        "sample_size_current": live["trades"],
    }
