# Step 9 Plan — Advanced Research Lab

**Status:** Implemented + hardening pass 2026-09-02. See [STEP_9_COMPLETION.md](STEP_9_COMPLETION.md).

**Goal:** Add an exploratory **Research Lab** at `/research` that answers *is this pattern worth investigating further?* Distinct from Graphs (*where do patterns appear?*). No proven-edge claims. No automatic strategy optimization. No Step 10 workflow automation.

**Prerequisite context:** Steps 1–5, 7, 8 are implemented and audited. Step 6 MANUAL-vs-AUTO pairing remains **skipped**. AUTO remains a normal `source_type`.

---

## Current State (Audit)

| Area | Location | Status for Research reuse |
|------|----------|---------------------------|
| Report engine | `services/reports/service.py` | Single pipeline: `build_closed_trades_query` → `_annotate_trades` → `apply_exploration` → aggregate. **Reuse for cohort membership.** |
| Dimension registry | `reports/registry.py` `REPORT_DEFINITIONS` | TIME / TRADE / INSTRUMENT / MARKET / SOURCE / BEHAVIOR / OUTCOMES / STRATEGY / EXECUTION / RISK. Feature keys + `availability_timing` + `exclude_missing`. |
| Metric registry | `METRICS` | net_pnl, avg_trade, win_rate, trade_count, avg winner/loser, Average/Total/R PF, excursion metrics. **Reuse formulas via `aggregation._bucket_metrics` / expectancy helpers.** |
| Filter model | `TradeFilterSet` | `global_filters` = `DashboardFilters` (date, account, source, direction, ticker). `exploration` dict uses Graph URL keys. `pine_scope` default REALTIME. `include_partial_feed`, `include_suggested_signals`. |
| Exploration keys | `TradeFilterSet.EXPLORATION_KEYS` + `filters.py` maps | One semantic for Gap/RVOL/Wednesday/etc. Research **must** call `apply_exploration`, not a second interpreter. |
| URL serialization | `frontend/src/utils/graphFilters.ts` | Graphs-only today. Research views persist in DB; optional URL subset for workspace restore. |
| AnnotatedTrade | `reports/features.py` | `trade`, `pnl`, `outcome`, `features: dict[str,str]` (buckets). Research needs **numeric** values too — attach a sidecar `numeric` dict, do not replace features. |
| Step 4 timing | `availability_timing` PRE_ENTRY \| END_OF_DAY | Opening gap / prior RVOL / ATR / SMA / SPY gap = PRE_ENTRY. Full-day RVOL, day volume, daily movement, day type, SPY movement = END_OF_DAY. |
| Step 5 timing | STRATEGY reports PRE_ENTRY except mechanical exit EXIT | Signal gap/RVOL/impulse/retrace/5m/VWAP/EMA9/quality = PRE_ENTRY. Exit reason = EXIT. |
| Step 7 R | `trade.r_multiple`, `trade_risk`, `_bucket_metrics` | Actual R is EXIT / retrospective. Risk $ / risk % / stop distance = PRE_ENTRY (known at entry if set). R outcome bucket = retrospective. |
| Step 8 excursion | `trade_excursions`, `apply_excursion_features` | MFE/MAE/efficiency/R-left/timing = POST_ENTRY. Post-exit extension = POST_EXIT. |
| Quality / coverage | `_skip_*` features, `include_partial_feed`, excursion `quality_status` | Reuse. Research Quality: Recommended / Include Partial / All. |
| Graphs frontend | `/graphs` | Leave unchanged. Do not merge Lab into Graphs. |
| Exit Analyzer | `/exit-analysis` | Leave unchanged. |
| Dashboard filters | `DashboardFilters` + `DashboardFiltersBar` | Reuse bar for Research global scope. |
| Query performance | Annotate-once + in-memory filter | 10k reports &lt; 5s after Step 5/7 audit. Research must load annotated set **once** per request, never per heatmap cell. |
| Indexes | `ix_trades_exit_time`, account/status/source, ticker, entry_time | Sufficient for closed-trade scope query. |
| Tests | 281 backend (Steps 1–8) | Do not weaken. Add `test_step_9_research.py`. |
| Polars | In `requirements.txt`, unused in reports | Allowed for grouping/rolling/heatmaps. |
| numpy / scipy | **Not pinned** | Add for Spearman / bootstrap / OLS. Isolate in `services/research/statistics.py`. |
| Saved research | **None** | New lightweight tables. |

### Timing gaps to close in Research (not Graphs)

Graphs mark report-level `availability_timing`. Research needs a **per-variable** timing class including SIGNAL / ENTRY / POST_ENTRY / POST_EXIT so PRE-ENTRY ONLY can reject MFE, actual R, full-day RVOL, etc.

### Filter-key contract (must stay identical)

| Graph URL / exploration param | Feature key on AnnotatedTrade |
|-------------------------------|-------------------------------|
| `weekday` | `day_of_week` |
| `entry_15m` | `entry_15m` |
| `gap_bucket` | `opening_gap_bucket` |
| `rvol_bucket` | `rvol50_bucket` |
| `prior_rvol_bucket` | `prior_rvol_bucket` |
| `setup_quality` | `setup_quality` |
| `signal_rvol_bucket` | `signal_rvol_bucket` |
| `retracement_bucket` | `retracement_bucket` |
| `mfe_r_bucket` | `mfe_r_bucket` |
| `r_outcome_bucket` | `r_outcome_bucket` |

`apply_exploration` is the single membership test.

---

## Architecture Overview

```
DashboardFilters (global scope)
        │
        ▼
_annotate_trades (existing: base + behavior + market + excursion + signal + risk)
        │
        ├── numeric sidecar (Research variables)
        ▼
Cohort A filters ── apply_exploration ──► set A
Cohort B filters ── apply_exploration ──► set B
        │
        ├── overlap IDs
        ├── optional exclusive mode (default OFF)
        ▼
comparison / scatter / heatmap / rolling / distribution / robustness
        │
        ▼
POST /api/research/*   (compute in process; optional in-memory cache by cohort hash)
```

**Do not** send 10k raw trades to the frontend for statistics.

---

## A. Research philosophy

- Exploratory only. Language: Observed Pattern, Candidate Pattern, Exploratory Difference, Research Finding, Needs More Samples.
- Never: proven edge, statistically guaranteed, optimal strategy, future profitable rule, AI recommends.
- Human decides whether a pattern is worth further work.
- Multiple-comparison warning always visible.
- No automatic parameter search / threshold optimization.
- Candidate Rules never modify Pine, Copilot, orders, or risk.
- Core persisted money stays Decimal. Statistical loops may use float64; document exception + `statistics_version`.

---

## B. Cohort model

Serializable:

```json
{
  "name": "A+ High RVOL",
  "filters": {
    "setup_quality": "A+",
    "signal_rvol_bucket": "10_20",
    "entry_15m": "09:30-09:45"
  }
}
```

Filter keys are **Graph exploration params** (not feature keys, not labels). Values are existing bucket keys (`10_20` not `10-20x`).

Global scope is **not** duplicated inside each cohort:

- date range, account, source, direction, ticker
- optional strategy version (applied as exploration `strategy_version` on the shared annotated set *before* A/B, or as a global extra filter — documented as global)

Membership = `apply_exploration(features, TradeFilterSet(exploration=cohort.filters))` after global query + annotate.

**Cohort hash** (no display name): SHA-256 of canonical JSON:

`global_scope + cohort_filters + research_mode + pine_scope + quality_mode + include_suggested + calculation_versions`

---

## C. Cohort comparison

- Independent A and B builders; multi-dimension chips.
- Clone A→B, Swap A/B (display only).
- Overlap = intersection of trade IDs. If &gt;0: count + “These cohorts are not independent.”
- Force A/B Exclusive (default OFF): trades in both **excluded from both**. Deterministic. Not silent.
- Summary metrics (only where valid) + coverage: trades, R-qualified, excursion-qualified, net P&L, avg trade, win rate, avg/median/total R, PF, R PF, avg win/lose R, max DD $ / R, avg MFE/MAE R, exit efficiency, R left.
- Difference column: A − B, labeled **Observed Difference**. No “better strategy.”
- Mean and median R always shown together when R exists.
- Effect size v1: absolute difference. Optional Cohen’s d on R if n≥min; document formula. No vague Strong/Weak.

---

## D. Predictor / retrospective timing classes

| Class | Meaning | Pre-entry cohort filter? |
|-------|---------|--------------------------|
| PRE_ENTRY | Known before/at entry from market or calendar | Yes |
| SIGNAL | Pine snapshot at ARMED/ENTRY | Yes (subset of pre-entry) |
| ENTRY | Trade entry facts (price, time, qty, planned stop/risk %) | Yes |
| POST_ENTRY | Path after entry (MFE/MAE/timing) | No |
| EXIT | Realized R, outcome, exit reason, hold duration | No |
| END_OF_DAY | Same-day EOD instrument/market | No |
| POST_EXIT | Post-exit extension | No |

**Research Mode** default: `PRE_ENTRY_ONLY` (user-facing **KNOWN BY ENTRY**). Allows PRE_ENTRY + SIGNAL + ENTRY — known no later than entry, including fill variables. Not strictly “before the fill.”

In that mode, cohort filters whose variable timing is not PRE_ENTRY / SIGNAL / ENTRY are rejected (`LOOKAHEAD_FILTER`) with “Not available before trade entry.”

`ALL_FEATURES` shows persistent warning: some variables were only known after entry; results are descriptive, not entry-selection rules.

If cohort filters include any POST_ENTRY / EXIT / END_OF_DAY / POST_EXIT key: badge **RETROSPECTIVE COHORT**. Analyzing PRE_ENTRY X vs Actual R Y is normal and does **not** by itself mark the cohort retrospective.

---

## E. Scatterplot engine

Registry-only numeric X/Y (`allowed_as_x` / `allowed_as_y`). Optional color/size from registered categoricals/numerics.

Coverage: total / plotted / missing X / missing Y / missing both. No silent enriched-only plot.

Tooltip: date, ticker, trade id, X, Y, strategy, direction, actual R. Click → `/trades/:id`.

OLS trend (numpy): slope, intercept, R² + “Descriptive relationship only.”

Spearman ρ (scipy, ranked, tie-aware) + n. Pearson optional. n &lt; `research_min_correlation_n` (default 10) → unavailable, not NaN.

---

## F. Two-dimensional heatmaps

Registered **bucket/categorical** dimensions only. Ticker = **enforced Top N** (default 20, `LTA_RESEARCH_HEATMAP_TICKER_TOP_N`). Remaining tickers aggregate as **Other** with coverage metadata (`unique_*_before/after`, `other_trade_count`). Other cells are not click-to-cohort filters.

Metrics: trade count, net P&L, avg trade, win rate, avg R, total R, PF, avg MFE/MAE R, exit efficiency, R left.

Every cell: metric + n + coverage. Click → Set as Cohort A / B (union of X+Y exploration keys).

Sparse: if majority of non-empty cells have n &lt; min_sample (default 5) → “Most cells have insufficient samples…”

Cardinality: product of axis bucket counts warned if &gt; 200.

---

## G. Rolling analytics

- Default window: **20 trades** (chronological by `exit_time_utc`, then trade id).
- Windows: 10 / 20 / 30 / 50 / 100 trades; optional 7 / 30 / 60 calendar days.
- Metrics: avg R, win rate, PF, avg trade, exit efficiency, avg MFE R.
- At index N: only trades `≤ N` (no lookahead).
- R metrics: window is N **trades**, disclose R-qualified count inside the window (not silently 20 R-qualified unless mode selected).
- Strategy version markers at first trade of a new `strategy_version` (CONFIRMED links; unlinked = no marker).
- Optional cumulative R A vs B: independent sequences; label “Independent cohort sequences; not synchronized trades.”

---

## H. Distribution analysis

Numeric research variables. ECDF (preferred) + optional histogram. A and B overlaid. Always show n. Quantile callouts (≤0R, ≥+2R) when Y is R.

---

## I. Robustness checks

Temporary compute only; never mutate stored trades.

- Trim: none / top+bottom 1 trade / 2.5% / 5%. Show mean R all vs trimmed. Neither is “correct.”
- Winner/loser concentration: top 1, top 5%, top 10% of total R (and worst). If total R ≤ 0: percentage **unavailable**; show absolute contribution.
- Subperiod: first/second half of cohort date range; optional month matrix (month, n, avg R, win rate, PF).
- Stability Split: alternating chronological trades. Label **Stability Split**, not OOS validation.
- Chronological train/validation: 50/50, 70/30, 80/20 by trade order. **No shuffle.**

---

## J. Sample-quality framework

| n | Label (sample size only) |
|---|--------------------------|
| &lt; 10 | N&lt;10 / VERY LOW |
| 10–19 | N10–19 / LOW |
| 20–49 | N20–49 / MODERATE |
| 50–99 | N50–99 / GOOD |
| 100+ | N100+ / STRONGER SAMPLE |

Does **not** mean result quality or certainty. Every chart/table/CI shows n. Below `research_min_sample` (default 10): stats that need sample → `INSUFFICIENT_SAMPLE`.

Coverage panel: base, A, B, R/signal/market/excursion %. Unequal coverage (e.g. excursion 95% vs 50%): warning.

Quality modes: Recommended (exclude partial feed + failed excursion quality), Include Partial, All. Variable-aware (partial IEX can drop RVOL without dropping weekday).

---

## K. Statistical summaries

Isolated module `app/services/research/statistics.py`.

| Statistic | Method | Notes |
|-----------|--------|-------|
| Mean R 95% CI | Bootstrap, 2000 resamples, seeded | float64 in loop; `statistics_version=1` |
| Median R 95% CI | Same bootstrap | v1 include |
| Win rate CI | Wilson | BE excluded from win+loss denom (same as Dashboard) |
| PF CI | **Deferred** | Display PF + n only. No normal-theory CI. |
| A−B mean R | Bootstrap only if overlap=0 and exclusive not required | Overlap → disable: “Independent cohort comparison unavailable because cohorts overlap.” |
| Spearman | `scipy.stats.spearmanr` | |
| OLS / R² | numpy lstsq | Descriptive |

Defaults: seed `20260902`, iterations `2000` (`LTA_RESEARCH_BOOTSTRAP_SEED`, `LTA_RESEARCH_BOOTSTRAP_ITERATIONS`).

Interpretation copy:

- CI includes 0 → “Interval includes zero.” Not “No edge.”
- Entirely positive → “Observed difference remained positive across this bootstrap interval.” Not “statistically proven.”

No central p-value hunting. No BH-FDR in v1 (deferred unless p-values are added later).

---

## L. Saved research views

Tables (lightweight):

**saved_cohorts:** name, description, filter_json, research_mode, created_at, updated_at

**research_views:** name, global_scope_json, cohort_a_json, cohort_b_json, visualization_json, research_mode, created_at, updated_at

**candidate_rules:** name, description, filter_json, research_mode, research_start, research_end, created_at, rule_version, status (`RESEARCH` \| `FORWARD_TESTING` \| `RETIRED`), parent_id nullable, statistics_version, bootstrap_seed, bootstrap_iterations. **Never PROVEN.**

**pattern_snapshots:** filter_json, metrics_json, sample_size, date range, created_at, starred_from (heatmap/multifactor/compare). Immutable observed metrics. Live “Current Results” recomputed separately.

Editing a candidate rule **inserts version N+1**; original row unchanged.

**Forward sample (v1, authoritative):** matching trades with `entry_time_utc` **>** `cutoff_at` (strict). A trade entered before the rule existed and exited afterward is **not** forward. Outcome may realize after cutoff; the ENTRY/DECISION must occur after the rule existed. A later signal-level decision timestamp is a future extension.

Research sample = matches with `entry_time_utc` ≤ cutoff.

**FORWARD_TESTING** is allowed only when every cohort filter is prospectively available (PRE_ENTRY / SIGNAL / ENTRY). Retrospective filters may be saved as cohorts, views, pattern snapshots, or CandidateRule status RESEARCH — never FORWARD_TESTING.

Observed Change = Forward Avg R − Research Avg R. Not labeled “Decay.”

---

## M. Export behavior

CSV endpoints for: comparison trade lists, scatter points, heatmap table, multifactor table.

Include trade_id, NY date, ticker, features used, outcomes. Plus header comment / first rows: scope, filters, mode, calculation timestamp, statistics_version.

No secrets/API keys.

---

## N. Performance architecture

- One annotated load per API call.
- In-memory (or Polars from already-annotated rows) for group/roll/heatmap.
- Optional process-local cache keyed by cohort hash + analysis type. Correctness over cache.
- Targets (dev hardware, 10k enriched trades): ordinary query &lt;1s; bootstrap &lt;2–3s. Document actual; do not fail CI on small hardware variance.
- 100k stress optional; document if run.
- No per-cell SQL.

---

## O. Tests

Backend `tests/test_step_9_research.py` (+ focused modules if needed):

Filter equivalence vs Graphs; A/B metrics; overlap; pre-entry reject MFE; retrospective allow MFE; EOD RVOL vs prior RVOL; scatter coverage; Spearman ±1; 2×2 heatmap; heatmap→cohort; rolling no lookahead; version markers; trim; concentration; 70/30 chrono split; candidate forward; rule versioning; bootstrap determinism; Wilson; min sample; coverage %; unequal coverage warning; multifactor + 200-group cap.

Frontend: research route, default PRE-ENTRY, warnings, clone/swap, overlap, selectors, sample n, CI copy. Do not test Recharts internals.

Keep Steps 1–8 passing. Graphs / Exit Analyzer / Risk / Signals unchanged.

---

## P. Known limitations

- Opening Fade extra dims still unavailable (Step 5).
- No live user Pine journal in repo — real-data sanity checks are USER-DATA VALIDATION if no signals.
- Calendar drawdown days (Step 7), not exchange sessions.
- Ticker heatmap Top N only.
- No BH multiple-test correction in v1.
- No 100k required for DoD.
- Statistical float64 ≠ stored Decimal; CIs are estimates.
- Exclusive mode drops overlap from **both** sides (documented).
- Step 6 pairing not reintroduced.
- Step 10 (watchers, backups, AI notes) out of scope.

---

## Implementation map

```
backend/app/services/research/
  variables.py      # RESEARCH_VARIABLES + heatmap dims + timing
  timing.py         # pre-entry allow / reject
  cohorts.py        # load, filter, overlap, exclusive, hash
  numeric.py        # attach numeric sidecar (batch queries)
  comparison.py
  scatter.py
  heatmap.py
  rolling.py
  distributions.py
  statistics.py     # numpy/scipy isolated
  robustness.py
  multifactor.py
  saved.py
backend/app/api/research.py
backend/app/db/models/research.py
frontend/src/pages/ResearchPage.tsx
docs/RESEARCH_LAB.md
docs/COHORT_COMPARISON.md
docs/RESEARCH_TIMING_AND_LOOKAHEAD.md
docs/RESEARCH_STATISTICS.md
docs/CANDIDATE_RULES.md
```

Config: `research_min_sample=10`, `research_min_correlation_n=10`, `research_max_groups=200`, bootstrap seed/iterations.

Dependencies: pin `numpy`, `scipy` (Polars already present).

---

## Definition of Done

Matches user spec §124 (65 items): `/research` exists; global + A/B reuse Graph semantics; clone/swap/overlap/exclusive; PRE-ENTRY default + retrospective warning; timing visible; comparison + observed difference; scatter + Spearman + coverage; heatmap + n + click-to-cohort; rolling no lookahead + version markers; distributions; robustness; chrono split; saved cohorts/views/rules + versioning + forward sample; sample-size labels; bootstrap + Wilson; overlap blocks independent Δ CI; multifactor + cardinality cap; exports; quality/coverage; no Graphs/Exit/Risk/Signal regressions; tests + production build.

**Explicitly not in Step 9:** AI recommendations, auto Pine/risk changes, folder watcher, scheduled backup, screenshot workflow, weekly review automation (Step 10).

---

---

## Implementation status (2026-09-02)

Implemented. Completion report: [STEP_9_COMPLETION.md](STEP_9_COMPLETION.md).

**Do not begin Step 10.**

*End of Step 9 Plan.*
