"""Up to 3-dimension grouped explorer with cardinality protection."""

from __future__ import annotations

from collections import defaultdict

from app.config import settings
from app.services.analytics.expectancy import profit_factor
from app.services.reports.aggregation import _bucket_metrics
from app.utils.analytics import decimal_str
from app.services.reports.features import AnnotatedTrade
from app.services.reports.registry import LABEL_MAPS
from app.services.research.timing import validate_heatmap_dim
from app.services.research.variables import heatmap_dim


def estimate_groups(rows: list[AnnotatedTrade], dim_keys: list[str]) -> int:
    cards = []
    for k in dim_keys:
        spec = heatmap_dim(k)
        if not spec:
            continue
        feat = spec["feature"]
        cards.append(len({at.features.get(feat) for at in rows if at.features.get(feat)}))
    prod = 1
    for c in cards:
        prod *= max(c, 1)
    return prod


def build_multifactor(
    rows: list[AnnotatedTrade],
    dim_keys: list[str],
    research_mode: str,
    min_sample: int = 1,
    force: bool = False,
    sort_by: str = "trade_count",
) -> dict:
    if not 1 <= len(dim_keys) <= 3:
        raise ValueError("Select 1–3 dimensions")
    specs = [validate_heatmap_dim(k, research_mode) for k in dim_keys]
    est = estimate_groups(rows, dim_keys)
    if est > settings.research_max_groups and not force:
        return {
            "blocked": True,
            "estimated_groups": est,
            "max_groups": settings.research_max_groups,
            "message": "Dimension cardinality product exceeds the group limit. Narrow dimensions or proceed explicitly.",
            "rows": [],
        }
    groups: dict[tuple, list[AnnotatedTrade]] = defaultdict(list)
    feats = [s["feature"] for s in specs]
    for at in rows:
        keys = tuple(at.features.get(f) for f in feats)
        if any(k is None or k == "" for k in keys):
            continue
        groups[keys].append(at)
    table = []
    for key, items in groups.items():
        if len(items) < min_sample:
            continue
        m = _bucket_metrics("|".join(key), "|".join(key), items)
        row = {dim_keys[i]: key[i] for i in range(len(dim_keys))}
        for i, spec in enumerate(specs):
            labels = LABEL_MAPS.get(spec["feature"], {})
            row[f"{dim_keys[i]}_label"] = labels.get(key[i], key[i])
        row.update(
            {
                "trade_count": m["trade_count"],
                "average_r": m.get("average_r"),
                "total_r": m.get("total_r"),
                "win_rate": m.get("win_rate"),
                "profit_factor": decimal_str(profit_factor([at.pnl for at in items])[0]),
                "exit_efficiency": m.get("average_exit_efficiency"),
                "net_pnl": m.get("net_pnl"),
                "r_qualified_count": m.get("r_qualified_count"),
                "filters": {dim_keys[i]: key[i] for i in range(len(dim_keys))},
            }
        )
        table.append(row)
    reverse = sort_by != "win_rate"
    table.sort(key=lambda r: (r.get(sort_by) is None, r.get(sort_by) or 0), reverse=True)
    return {
        "blocked": False,
        "estimated_groups": est,
        "rows": table,
        "n_groups": len(table),
        "min_sample": min_sample,
    }
