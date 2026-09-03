"""Isolated statistical helpers.

Core persisted money remains Decimal. Bootstrap / rank / OLS use float64.
statistics_version must be stored with snapshots that depend on these estimates.
"""

from __future__ import annotations

from decimal import Decimal

import numpy as np
from scipy import stats as scipy_stats

from app.config import settings
from app.services.research import STATISTICS_VERSION
from app.utils.analytics import decimal_str

STATISTICS_VERSION = STATISTICS_VERSION


def _arr(values: list[Decimal | float]) -> np.ndarray:
    return np.asarray([float(v) for v in values], dtype=np.float64)


def sample_size_label(n: int) -> str:
    if n < 10:
        return "N<10"
    if n < 20:
        return "N10-19"
    if n < 50:
        return "N20-49"
    if n < 100:
        return "N50-99"
    return "N100+"


def bootstrap_mean_ci(
    values: list[Decimal | float],
    *,
    seed: int | None = None,
    iterations: int | None = None,
    min_n: int | None = None,
) -> dict:
    seed = settings.research_bootstrap_seed if seed is None else seed
    iterations = settings.research_bootstrap_iterations if iterations is None else iterations
    min_n = settings.research_min_sample if min_n is None else min_n
    n = len(values)
    if n < min_n:
        return {
            "available": False,
            "reason": "INSUFFICIENT_SAMPLE",
            "n": n,
            "observed": None,
            "ci_low": None,
            "ci_high": None,
            "includes_zero": None,
            "seed": seed,
            "iterations": iterations,
            "statistics_version": STATISTICS_VERSION,
        }
    arr = _arr(values)
    rng = np.random.default_rng(seed)
    means = np.empty(iterations, dtype=np.float64)
    for i in range(iterations):
        sample = rng.choice(arr, size=n, replace=True)
        means[i] = sample.mean()
    lo, hi = np.percentile(means, [2.5, 97.5])
    observed = float(arr.mean())
    return {
        "available": True,
        "reason": None,
        "n": n,
        "observed": observed,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "includes_zero": bool(lo <= 0 <= hi),
        "seed": seed,
        "iterations": iterations,
        "statistics_version": STATISTICS_VERSION,
        "interpretation": (
            "Interval includes zero."
            if lo <= 0 <= hi
            else (
                "Observed difference remained positive across this bootstrap interval."
                if lo > 0
                else "Observed difference remained negative across this bootstrap interval."
            )
        ),
    }


def bootstrap_median_ci(
    values: list[Decimal | float],
    *,
    seed: int | None = None,
    iterations: int | None = None,
    min_n: int | None = None,
) -> dict:
    seed = settings.research_bootstrap_seed if seed is None else seed
    iterations = settings.research_bootstrap_iterations if iterations is None else iterations
    min_n = settings.research_min_sample if min_n is None else min_n
    n = len(values)
    if n < min_n:
        return {"available": False, "reason": "INSUFFICIENT_SAMPLE", "n": n, "observed": None, "ci_low": None, "ci_high": None}
    arr = _arr(values)
    rng = np.random.default_rng(seed)
    meds = np.empty(iterations, dtype=np.float64)
    for i in range(iterations):
        meds[i] = np.median(rng.choice(arr, size=n, replace=True))
    lo, hi = np.percentile(meds, [2.5, 97.5])
    return {
        "available": True,
        "n": n,
        "observed": float(np.median(arr)),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "includes_zero": bool(lo <= 0 <= hi),
        "seed": seed,
        "iterations": iterations,
        "statistics_version": STATISTICS_VERSION,
    }


def bootstrap_difference_ci(
    a: list[Decimal | float],
    b: list[Decimal | float],
    *,
    seed: int | None = None,
    iterations: int | None = None,
    min_n: int | None = None,
) -> dict:
    seed = settings.research_bootstrap_seed if seed is None else seed
    iterations = settings.research_bootstrap_iterations if iterations is None else iterations
    min_n = settings.research_min_sample if min_n is None else min_n
    if len(a) < min_n or len(b) < min_n:
        return {"available": False, "reason": "INSUFFICIENT_SAMPLE", "n_a": len(a), "n_b": len(b)}
    aa, bb = _arr(a), _arr(b)
    rng = np.random.default_rng(seed)
    diffs = np.empty(iterations, dtype=np.float64)
    for i in range(iterations):
        diffs[i] = rng.choice(aa, size=len(aa), replace=True).mean() - rng.choice(bb, size=len(bb), replace=True).mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    observed = float(aa.mean() - bb.mean())
    return {
        "available": True,
        "observed": observed,
        "ci_low": float(lo),
        "ci_high": float(hi),
        "includes_zero": bool(lo <= 0 <= hi),
        "n_a": len(a),
        "n_b": len(b),
        "seed": seed,
        "iterations": iterations,
        "statistics_version": STATISTICS_VERSION,
        "interpretation": (
            "Interval includes zero."
            if lo <= 0 <= hi
            else (
                "Observed difference remained positive across this bootstrap interval."
                if lo > 0
                else "Observed difference remained negative across this bootstrap interval."
            )
        ),
    }


def wilson_interval(wins: int, losses: int, z: float = 1.96) -> dict:
    n = wins + losses
    if n <= 0:
        return {"available": False, "reason": "NO_DECISIVE_TRADES", "n": 0, "p": None, "ci_low": None, "ci_high": None}
    p = wins / n
    z2 = z * z
    denom = 1 + z2 / n
    center = (p + z2 / (2 * n)) / denom
    margin = z * ((p * (1 - p) / n + z2 / (4 * n * n)) ** 0.5) / denom
    return {
        "available": True,
        "n": n,
        "wins": wins,
        "losses": losses,
        "p": p,
        "ci_low": max(0.0, center - margin),
        "ci_high": min(1.0, center + margin),
        "method": "wilson",
    }


def spearman(xs: list[float], ys: list[float], min_n: int | None = None) -> dict:
    min_n = settings.research_min_correlation_n if min_n is None else min_n
    n = min(len(xs), len(ys))
    if n < min_n:
        return {"available": False, "reason": "INSUFFICIENT_SAMPLE", "n": n, "rho": None}
    rho, _p = scipy_stats.spearmanr(xs, ys)
    return {"available": True, "n": n, "rho": float(rho) if rho == rho else None, "method": "scipy.stats.spearmanr"}


def pearson(xs: list[float], ys: list[float], min_n: int | None = None) -> dict:
    min_n = settings.research_min_correlation_n if min_n is None else min_n
    if len(xs) < min_n:
        return {"available": False, "reason": "INSUFFICIENT_SAMPLE", "n": len(xs), "r": None}
    r, _p = scipy_stats.pearsonr(xs, ys)
    return {"available": True, "n": len(xs), "r": float(r) if r == r else None}


def ols_trend(xs: list[float], ys: list[float]) -> dict:
    if len(xs) < 2:
        return {"available": False, "slope": None, "intercept": None, "r_squared": None}
    x = np.asarray(xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    A = np.vstack([x, np.ones(len(x))]).T
    slope, intercept = np.linalg.lstsq(A, y, rcond=None)[0]
    yhat = slope * x + intercept
    ss_res = float(((y - yhat) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = None if ss_tot == 0 else 1 - ss_res / ss_tot
    return {
        "available": True,
        "slope": float(slope),
        "intercept": float(intercept),
        "r_squared": r2,
        "warning": "Descriptive relationship only.",
    }


def fmt_stat(v: float | None) -> str | None:
    if v is None:
        return None
    return decimal_str(Decimal(str(v)))
