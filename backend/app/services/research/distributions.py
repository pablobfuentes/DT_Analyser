"""ECDF + histogram for a numeric research variable."""

from __future__ import annotations

from app.services.reports.features import AnnotatedTrade
from app.services.research.cohorts import numeric_of
from app.services.research.variables import variable_by_key


def _values(rows: list[AnnotatedTrade], key: str) -> list[float]:
    out = []
    for at in rows:
        v = numeric_of(at, key)
        if v is not None:
            out.append(float(v))
    return out


def build_distribution(a: list[AnnotatedTrade], b: list[AnnotatedTrade], var_key: str) -> dict:
    spec = variable_by_key(var_key)
    if spec is None:
        raise ValueError("Unknown variable")
    va, vb = _values(a, var_key), _values(b, var_key)

    def ecdf(vals: list[float]) -> list[dict]:
        if not vals:
            return []
        s = sorted(vals)
        n = len(s)
        return [{"x": s[i], "p": (i + 1) / n} for i in range(n)]

    def hist(vals: list[float], bins: int = 12) -> list[dict]:
        if not vals:
            return []
        lo, hi = min(vals), max(vals)
        if lo == hi:
            return [{"lo": lo, "hi": hi, "count": len(vals)}]
        width = (hi - lo) / bins
        counts = [0] * bins
        for v in vals:
            idx = min(int((v - lo) / width), bins - 1)
            counts[idx] += 1
        return [{"lo": lo + i * width, "hi": lo + (i + 1) * width, "count": counts[i]} for i in range(bins)]

    def share_le(vals: list[float], thr: float) -> float | None:
        if not vals:
            return None
        return sum(1 for v in vals if v <= thr) / len(vals)

    return {
        "variable": spec,
        "cohort_a": {"n": len(va), "ecdf": ecdf(va), "histogram": hist(va)},
        "cohort_b": {"n": len(vb), "ecdf": ecdf(vb), "histogram": hist(vb)},
        "callouts": {
            "pct_le_0r": {"a": share_le(va, 0), "b": share_le(vb, 0)} if var_key == "actual_r" else None,
            "pct_ge_2r": {
                "a": (sum(1 for v in va if v >= 2) / len(va)) if va else None,
                "b": (sum(1 for v in vb if v >= 2) / len(vb)) if vb else None,
            }
            if var_key == "actual_r"
            else None,
        },
    }
