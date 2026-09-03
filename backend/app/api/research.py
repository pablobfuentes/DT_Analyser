"""Research Lab API. Exploratory only — no proven-edge claims."""

from __future__ import annotations

import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.research.cohorts import cohort_hash, load_universe, split_ab
from app.services.research.comparison import compare_summaries, coverage_panel, summarize_cohort
from app.services.research.distributions import build_distribution
from app.services.research.heatmap import build_heatmap
from app.services.research.multifactor import build_multifactor
from app.services.research.payload import parse_cohort, parse_scope
from app.services.research.robustness import (
    chrono_split,
    concentration,
    month_matrix,
    robustness_means,
    stability_split,
    subperiod_halves,
)
from app.services.research.rolling import build_rolling, cumulative_r_series
from app.services.research.saved import (
    create_candidate_rule,
    current_vs_snapshot,
    delete_cohort,
    evaluate_rule,
    get_view,
    list_cohorts,
    list_patterns,
    list_rules,
    list_views,
    revise_candidate_rule,
    save_cohort,
    save_view,
    star_pattern,
    update_cohort,
    _cohort_dict,
    _rule_dict,
    _view_dict,
)
from app.services.research.scatter import build_scatter
from app.services.research.statistics import bootstrap_difference_ci
from app.services.research.timing import LookaheadFilterError, RetrospectiveRuleError
from app.services.research.variables import HEATMAP_METRICS, list_heatmap_dimensions, list_variables
from app.services.research.cohorts import numeric_of

router = APIRouter(prefix="/api/research", tags=["research"])

MULTIPLE_COMPARISON_WARNING = (
    "Exploring many combinations increases the chance of finding patterns that "
    "occur by chance. Forward validation is recommended."
)


def _handle(exc: Exception):
    if isinstance(exc, LookaheadFilterError):
        raise HTTPException(status_code=400, detail={"code": "LOOKAHEAD_FILTER", "keys": exc.keys, "message": str(exc)})
    if isinstance(exc, RetrospectiveRuleError):
        raise HTTPException(
            status_code=400,
            detail={"code": RetrospectiveRuleError.code, "keys": exc.keys, "message": str(exc)},
        )
    if isinstance(exc, ValueError):
        msg = str(exc)
        if "not found" in msg.lower():
            raise HTTPException(status_code=404, detail=msg)
        raise HTTPException(status_code=400, detail=msg)
    raise exc


def _run_split(db, body):
    scope = parse_scope(body)
    universe = load_universe(db, scope)
    a = parse_cohort(body, "cohort_a", "Cohort A")
    b = parse_cohort(body, "cohort_b", "Cohort B")
    split = split_ab(universe, a, b, scope.research_mode, exclusive=scope.exclusive)
    return scope, universe, a, b, split


@router.get("/variables")
def variables(research_mode: str = "PRE_ENTRY_ONLY"):
    return {
        "variables": list_variables(),
        "heatmap_dimensions": list_heatmap_dimensions(research_mode=research_mode),
        "heatmap_metrics": HEATMAP_METRICS,
        "research_mode_default": "PRE_ENTRY_ONLY",
        "multiple_comparison_warning": MULTIPLE_COMPARISON_WARNING,
    }


@router.post("/compare")
def compare(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        scope, universe, a_def, b_def, split = _run_split(db, body)
        sum_a = summarize_cohort(split["a"])
        sum_b = summarize_cohort(split["b"])
        table = compare_summaries(sum_a, sum_b, overlap_count=split["overlap_count"], independent=split["independent"])
        if split["independent"]:
            ra = [numeric_of(at, "actual_r") for at in split["a"] if numeric_of(at, "actual_r") is not None]
            rb = [numeric_of(at, "actual_r") for at in split["b"] if numeric_of(at, "actual_r") is not None]
            table["mean_r_difference"] = bootstrap_difference_ci(ra, rb)
        cov = coverage_panel(universe, split["a"], split["b"])
        return {
            "research_mode": scope.research_mode,
            "retrospective_warning": scope.research_mode != "PRE_ENTRY_ONLY",
            "cohort_a_retrospective": split["a_retrospective"],
            "cohort_b_retrospective": split["b_retrospective"],
            "overlap_count": split["overlap_count"],
            "overlap_ids": split["overlap_ids"],
            "independent": split["independent"],
            "overlap_warning": "These cohorts are not independent." if split["overlap_count"] else None,
            "exclusive_applied": split["exclusive_applied"],
            "cohort_a": {"name": a_def.name, "filters": a_def.filters, "hash": cohort_hash(scope, a_def), **sum_a},
            "cohort_b": {"name": b_def.name, "filters": b_def.filters, "hash": cohort_hash(scope, b_def), **sum_b},
            "comparison": table,
            "coverage": cov,
            "multiple_comparison_warning": MULTIPLE_COMPARISON_WARNING,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        _handle(exc)


@router.post("/scatter")
def scatter(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        scope, universe, a_def, _b, split = _run_split(db, body)
        which = body.get("which") or "A"
        rows = split["a"] if which != "B" else split["b"]
        return {
            "research_mode": scope.research_mode,
            "which": which,
            "n": len(rows),
            **build_scatter(rows, body.get("x") or "signal_rvol", body.get("y") or "actual_r", scope.research_mode),
        }
    except Exception as exc:
        _handle(exc)


@router.post("/heatmap")
def heatmap(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        scope, universe, a_def, _b, split = _run_split(db, body)
        which = body.get("which") or "A"
        rows = split["a"] if which != "B" else split["b"]
        if body.get("on") == "universe":
            rows = universe
        top_n = body.get("top_n")
        return build_heatmap(
            rows,
            body.get("x") or "signal_rvol_bucket",
            body.get("y") or "retracement_bucket",
            body.get("metric") or "average_r",
            scope.research_mode,
            min_sample=int(body.get("min_sample") or 1),
            top_n=int(top_n) if top_n not in (None, "") else None,
        )
    except Exception as exc:
        _handle(exc)


@router.post("/rolling")
def rolling(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        scope, _u, _a, _b, split = _run_split(db, body)
        which = body.get("which") or "A"
        rows = split["a"] if which != "B" else split["b"]
        cal = body.get("calendar_days")
        return build_rolling(
            rows,
            metric=body.get("metric") or "average_r",
            window=int(body.get("window") or 20),
            calendar_days=int(cal) if cal else None,
        )
    except Exception as exc:
        _handle(exc)


@router.post("/cumulative")
def cumulative(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        _scope, _u, a_def, b_def, split = _run_split(db, body)
        return {
            "label": "Independent cohort sequences; not synchronized trades.",
            "a": cumulative_r_series(split["a"], a_def.name),
            "b": cumulative_r_series(split["b"], b_def.name),
        }
    except Exception as exc:
        _handle(exc)


@router.post("/distribution")
def distribution(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        scope, _u, _a, _b, split = _run_split(db, body)
        return build_distribution(split["a"], split["b"], body.get("variable") or "actual_r")
    except Exception as exc:
        _handle(exc)


@router.post("/multifactor")
def multifactor(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        scope, universe, _a, _b, split = _run_split(db, body)
        rows = universe if body.get("on") == "universe" else split["a"]
        return build_multifactor(
            rows,
            list(body.get("dimensions") or []),
            scope.research_mode,
            min_sample=int(body.get("min_sample") or 1),
            force=bool(body.get("force")),
            sort_by=body.get("sort_by") or "trade_count",
        )
    except Exception as exc:
        _handle(exc)


@router.post("/robustness")
def robustness(body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        _scope, _u, _a, _b, split = _run_split(db, body)
        which = body.get("which") or "A"
        rows = split["a"] if which != "B" else split["b"]
        return {
            "outlier": robustness_means(rows),
            "concentration": concentration(rows),
            "subperiod": subperiod_halves(rows),
            "months": month_matrix(rows),
            "stability_split": stability_split(rows),
            "chrono_split": chrono_split(rows, int(body.get("research_pct") or 70)),
        }
    except Exception as exc:
        _handle(exc)


@router.post("/export/{kind}")
def export_csv(kind: str, body: dict = Body(...), db: Session = Depends(get_db)):
    try:
        scope, universe, a_def, b_def, split = _run_split(db, body)
        buf = io.StringIO()
        buf.write(f"# research_mode={scope.research_mode} calculated_at={datetime.now(timezone.utc).isoformat()}\n")
        buf.write(f"# cohort_a={a_def.filters} cohort_b={b_def.filters}\n")
        w = csv.writer(buf)
        if kind == "trades":
            w.writerow(["cohort", "trade_id", "ticker", "direction", "actual_r", "net_pnl"])
            for label, rows in (("A", split["a"]), ("B", split["b"])):
                for at in rows:
                    r = numeric_of(at, "actual_r")
                    w.writerow([label, at.trade.id, at.trade.ticker, at.trade.direction, r, at.pnl])
        elif kind == "scatter":
            data = build_scatter(split["a"], body.get("x") or "signal_rvol", body.get("y") or "actual_r", scope.research_mode)
            w.writerow(["trade_id", "ticker", "x", "y", "actual_r"])
            for p in data["points"]:
                w.writerow([p["trade_id"], p["ticker"], p["x"], p["y"], p.get("actual_r")])
        elif kind == "heatmap":
            data = build_heatmap(
                split["a"],
                body.get("x") or "signal_rvol_bucket",
                body.get("y") or "retracement_bucket",
                body.get("metric") or "average_r",
                scope.research_mode,
            )
            w.writerow(["x", "y", "value", "n", "r_coverage_pct"])
            for c in data["cells"]:
                w.writerow([c["x"], c["y"], c["value"], c["trade_count"], c.get("r_coverage_pct")])
        elif kind == "multifactor":
            data = build_multifactor(universe, list(body.get("dimensions") or []), scope.research_mode, force=True)
            if data["rows"]:
                w.writerow(list(data["rows"][0].keys()))
                for row in data["rows"]:
                    w.writerow([row.get(k) for k in data["rows"][0].keys()])
        else:
            raise ValueError("Unknown export kind")
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")
    except Exception as exc:
        _handle(exc)


@router.get("/saved-cohorts")
def get_saved_cohorts(db: Session = Depends(get_db)):
    return {"items": list_cohorts(db)}


@router.post("/saved-cohorts")
def post_saved_cohort(body: dict, db: Session = Depends(get_db)):
    row = save_cohort(db, body["name"], body.get("filters") or {}, body.get("research_mode") or "PRE_ENTRY_ONLY", body.get("description"))
    return _cohort_dict(row)


@router.patch("/saved-cohorts/{pk}")
def patch_saved_cohort(pk: int, body: dict, db: Session = Depends(get_db)):
    try:
        return _cohort_dict(update_cohort(db, pk, **body))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/saved-cohorts/{pk}")
def del_saved_cohort(pk: int, db: Session = Depends(get_db)):
    delete_cohort(db, pk)
    return {"ok": True}


@router.get("/views")
def get_views(db: Session = Depends(get_db)):
    return {"items": list_views(db)}


@router.post("/views")
def post_view(body: dict, db: Session = Depends(get_db)):
    return _view_dict(save_view(db, body))


@router.get("/views/{pk}")
def get_one_view(pk: int, db: Session = Depends(get_db)):
    try:
        return get_view(db, pk)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/candidate-rules")
def get_rules(db: Session = Depends(get_db)):
    return {"items": list_rules(db)}


@router.post("/candidate-rules")
def post_rule(body: dict, db: Session = Depends(get_db)):
    try:
        return _rule_dict(create_candidate_rule(db, body))
    except Exception as exc:
        _handle(exc)


@router.post("/candidate-rules/{pk}/revise")
def revise_rule(pk: int, body: dict, db: Session = Depends(get_db)):
    try:
        return _rule_dict(revise_candidate_rule(db, pk, body))
    except Exception as exc:
        _handle(exc)


@router.post("/candidate-rules/{pk}/evaluate")
def eval_rule(pk: int, body: dict, db: Session = Depends(get_db)):
    try:
        scope = parse_scope(body)
        return evaluate_rule(db, pk, scope)
    except Exception as exc:
        _handle(exc)


@router.get("/patterns")
def get_patterns(db: Session = Depends(get_db)):
    return {"items": list_patterns(db)}


@router.post("/patterns")
def post_pattern(body: dict, db: Session = Depends(get_db)):
    row = star_pattern(db, body)
    return {"id": row.id, "name": row.name, "sample_size": row.sample_size}


@router.post("/patterns/{pk}/current")
def pattern_current(pk: int, body: dict, db: Session = Depends(get_db)):
    try:
        return current_vs_snapshot(db, pk, parse_scope(body))
    except Exception as exc:
        _handle(exc)
