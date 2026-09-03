# Research Statistics

Isolated module: `backend/app/services/research/statistics.py`.

Core persisted money and R stay `Decimal`. Bootstrap, Spearman, Pearson, and OLS convert to `float64` only inside this module. That exception is intentional.

`statistics_version` = `1` (also `LTA_RESEARCH_STATISTICS_VERSION`).

## Sample minimum

Configurable `LTA_RESEARCH_MIN_SAMPLE` (default 10) and `LTA_RESEARCH_MIN_CORRELATION_N` (default 10).

Below threshold: `available=false`, `reason=INSUFFICIENT_SAMPLE`. No NaN.

## Bootstrap confidence intervals

| Setting | Default | Env |
|---------|---------|-----|
| Seed | 20260902 | `LTA_RESEARCH_BOOTSTRAP_SEED` |
| Iterations | 2000 | `LTA_RESEARCH_BOOTSTRAP_ITERATIONS` |
| Interval | percentile 2.5 / 97.5 | 95% |

Same dataset + same seed → same CI.

Implemented: mean R, median R, independent Δ mean R (`mean(A) − mean(B)`).

### Assumption (limitation)

This is an **IID / exchangeable-observation exploratory bootstrap**. Trading outcomes may be serially dependent (market regime, strategy version, volatility regime, clustered conditions). Intervals may **understate** uncertainty when observations are strongly dependent.

A moving-block or session-level bootstrap is a future extension. **Not implemented in Step 9.** Do not treat these intervals as regime-robust.

If cohorts overlap, independent Δ is **disabled**:

“Independent cohort comparison unavailable because cohorts overlap.”

### Language

- Interval includes 0 → “Interval includes zero.”
- Entirely positive → “Observed difference remained positive across this bootstrap interval.”

Never: “no edge”, “statistically proven profitable.”

## Wilson interval (win rate)

Wilson score interval, z = 1.96. Breakevens excluded from wins+losses (Dashboard convention).

Do not use naïve `p ± 1.96√(p(1−p)/n)` for tiny samples.

## Profit factor

**Display:** Profit Factor value + sample size (n).

**Confidence interval:** **deferred**. Do not invent a simplistic normal-theory CI for PF.

Primary uncertainty metrics remain: mean R bootstrap CI, median R bootstrap CI, Wilson win-rate interval.

## Spearman

`scipy.stats.spearmanr` on plotted (valid X and Y) pairs. Display ρ and n.

Pearson and OLS trend (slope, intercept, R²) are optional companions. Trend warning: “Descriptive relationship only.”

## Multiple comparisons

Visible warning on the Lab and compare payload:

“Exploring many combinations increases the chance of finding patterns that occur by chance. Forward validation is recommended.”

No p-value hunting and no Benjamini–Hochberg FDR in v1.

## Saved snapshots

Candidate rules and pattern snapshots store `statistics_version`, and rules also store bootstrap seed / iterations.
