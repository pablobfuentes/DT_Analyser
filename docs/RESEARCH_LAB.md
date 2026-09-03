# Research Lab

The Research Lab at `/research` answers: **is this pattern worth investigating further?**

Graphs at `/graphs` answers: **where do patterns appear?**

The two pages stay separate. Research is an exploratory workspace. It does **not** claim a proven edge, a statistically guaranteed result, an optimal strategy, or a future profitable rule.

Preferred language: Observed Pattern, Candidate Pattern, Exploratory Difference, Research Finding, Needs More Samples.

## Layout

1. **Global Scope** — date, account, source, direction, ticker, optional strategy version. Same `DashboardFilters` as Graphs.
2. **Cohort A / Cohort B** — independent Graph exploration filters. Clone A→B and Swap A/B are UX only.
3. **Summary Comparison** — Observed Difference (A − B), coverage, overlap warning.
4. **Visual Research** — scatter, 2D heatmap, rolling, distribution (ECDF + histogram).
5. **Robustness & Sample Quality** — trim, concentration, halves, month matrix, stability split, chronological validation split.

## Research mode

Default enum remains `PRE_ENTRY_ONLY` (URLs/storage unchanged). User-facing label: **KNOWN BY ENTRY**.

Meaning: information **known no later than entry** — PRE_ENTRY, SIGNAL, and ENTRY (selection-time plus actual entry/fill variables). Future path, exit, and end-of-day information is excluded.

Tooltip: “Allows information known before the trade or at the time the position is entered. Future path, exit and end-of-day information is excluded.”

Cohort filters whose values were unavailable by entry are rejected (`LOOKAHEAD_FILTER`).

**ALL FEATURES / RETROSPECTIVE** unlocks post-entry / end-of-day filters and shows a persistent warning: results are descriptive and must not be read as entry-selection rules.

A cohort that itself filters on a post-entry key is marked **RETROSPECTIVE COHORT**. Analyzing a pre-entry X against Actual R Y is normal and does not by itself mark the cohort retrospective.

## Filter reuse

Cohort membership calls the same `apply_exploration` used by Graphs. `Gap 10–20%`, `RVOL 5–10x`, and `Wednesday` mean the same thing on both pages.

See [COHORT_COMPARISON.md](COHORT_COMPARISON.md) and [REPORT_FILTER_ENGINE.md](REPORT_FILTER_ENGINE.md).

## Overlap

If A and B share trade IDs, the UI reports the overlap count and: “These cohorts are not independent.”

Independent bootstrap Δ mean R is disabled while they overlap.

**Force A/B Exclusive** (default off) drops overlapping trades from **both** sides.

## APIs

All compute on the backend. The annotated universe is loaded once per request.

| Method | Path |
|--------|------|
| GET | `/api/research/variables` |
| POST | `/api/research/compare` |
| POST | `/api/research/scatter` |
| POST | `/api/research/heatmap` |
| POST | `/api/research/rolling` |
| POST | `/api/research/cumulative` |
| POST | `/api/research/distribution` |
| POST | `/api/research/multifactor` |
| POST | `/api/research/robustness` |
| POST | `/api/research/export/{trades\|scatter\|heatmap\|multifactor}` |
| CRUD | `/api/research/saved-cohorts` |
| GET/POST | `/api/research/views` |
| POST | `/api/research/candidate-rules` |
| POST | `/api/research/candidate-rules/{id}/revise` |
| POST | `/api/research/candidate-rules/{id}/evaluate` |
| POST | `/api/research/patterns` |

## Quality

Data Quality: Recommended / Include Partial / All. Exclusion remains variable-aware (partial volume can invalidate RVOL without invalidating weekday). Reuses Step 4/8 `include_partial_feed` and enrichment quality flags.

## What this is not

- No AI recommendations.
- No automatic Pine / Copilot / risk mutation.
- No “find best RVOL” optimizer.
- No Step 10 watchers, backups, or weekly-review automation.

Further reading: [RESEARCH_TIMING_AND_LOOKAHEAD.md](RESEARCH_TIMING_AND_LOOKAHEAD.md), [RESEARCH_STATISTICS.md](RESEARCH_STATISTICS.md), [CANDIDATE_RULES.md](CANDIDATE_RULES.md).
