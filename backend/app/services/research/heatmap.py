"""2D performance heatmap from already-annotated trades."""

from __future__ import annotations

from collections import Counter, defaultdict

from app.config import settings
from app.services.analytics.expectancy import profit_factor
from app.services.reports.aggregation import _bucket_metrics
from app.utils.analytics import decimal_str
from app.services.reports.features import AnnotatedTrade
from app.services.reports.registry import LABEL_MAPS
from app.services.research.timing import validate_heatmap_dim
from app.services.research.variables import HEATMAP_METRICS, heatmap_dim

OTHER_KEY = "other"
OTHER_LABEL = "Other"


def _keep_set(rows: list[AnnotatedTrade], feature: str, top_n: int | None) -> set[str] | None:
    if top_n is None:
        return None
    counts: Counter[str] = Counter()
    for at in rows:
        v = at.features.get(feature)
        if v:
            counts[v] += 1
    return {k for k, _ in counts.most_common(top_n)}


def _axis_val(raw: str | None, keep: set[str] | None) -> str | None:
    if not raw:
        return None
    if keep is None:
        return raw
    return raw if raw in keep else OTHER_KEY


def build_heatmap(
    rows: list[AnnotatedTrade],
    x_key: str,
    y_key: str,
    metric: str,
    research_mode: str,
    min_sample: int = 1,
    top_n: int | None = None,
) -> dict:
    if metric not in HEATMAP_METRICS:
        raise ValueError(f"Unsupported heatmap metric: {metric}")
    xd = validate_heatmap_dim(x_key, research_mode)
    yd = validate_heatmap_dim(y_key, research_mode)
    xf, yf = xd["feature"], yd["feature"]
    default_n = settings.research_heatmap_ticker_top_n
    x_n = top_n if top_n is not None else xd.get("top_n")
    y_n = top_n if top_n is not None else yd.get("top_n")
    if x_n is None and xf == "symbol":
        x_n = default_n
    if y_n is None and yf == "symbol":
        y_n = default_n
    x_keep = _keep_set(rows, xf, x_n)
    y_keep = _keep_set(rows, yf, y_n)

    groups: dict[tuple[str, str], list[AnnotatedTrade]] = defaultdict(list)
    other_n = 0
    unique_x_raw: set[str] = set()
    unique_y_raw: set[str] = set()
    for at in rows:
        xv_raw = at.features.get(xf)
        yv_raw = at.features.get(yf)
        if xv_raw:
            unique_x_raw.add(xv_raw)
        if yv_raw:
            unique_y_raw.add(yv_raw)
        xv = _axis_val(xv_raw, x_keep)
        yv = _axis_val(yv_raw, y_keep)
        if not xv or not yv:
            continue
        if xv == OTHER_KEY or yv == OTHER_KEY:
            other_n += 1
        groups[(xv, yv)].append(at)

    x_labels = LABEL_MAPS.get(xf, {})
    y_labels = LABEL_MAPS.get(yf, {})
    cells = []
    insufficient = 0
    nonempty = 0
    for (xk, yk), items in groups.items():
        nonempty += 1
        m = _bucket_metrics(xk, x_labels.get(xk, xk), items)
        if "profit_factor" not in m:
            pf, _st = profit_factor([at.pnl for at in items])
            m["profit_factor"] = decimal_str(pf)
        if items and m["trade_count"] < min_sample:
            insufficient += 1
        is_other = xk == OTHER_KEY or yk == OTHER_KEY
        cells.append(
            {
                "x": xk,
                "x_label": OTHER_LABEL if xk == OTHER_KEY else x_labels.get(xk, xk),
                "y": yk,
                "y_label": OTHER_LABEL if yk == OTHER_KEY else y_labels.get(yk, yk),
                "metric": metric,
                "value": m.get(metric),
                "trade_count": m["trade_count"],
                "r_qualified_count": m.get("r_qualified_count"),
                "r_coverage_pct": m.get("r_coverage_pct"),
                "is_other": is_other,
                "filters": None if is_other else {x_key: xk, y_key: yk},
            }
        )
    sparse = nonempty > 0 and insufficient / nonempty >= 0.5
    product = max(1, len({c["x"] for c in cells})) * max(1, len({c["y"] for c in cells}))
    return {
        "x": xd,
        "y": yd,
        "metric": metric,
        "cells": cells,
        "n_total": len(rows),
        "sparse": sparse,
        "sparse_message": "Most cells have insufficient samples. Consider broader buckets." if sparse else None,
        "cardinality": product,
        "cardinality_warning": product > settings.research_max_groups,
        "top_n": {
            "x": x_n,
            "y": y_n,
            "other_policy": "aggregated_as_Other",
            "other_trade_count": other_n,
            "unique_x_before": len(unique_x_raw),
            "unique_y_before": len(unique_y_raw),
            "unique_x_after": len({c["x"] for c in cells}),
            "unique_y_after": len({c["y"] for c in cells}),
        },
    }
