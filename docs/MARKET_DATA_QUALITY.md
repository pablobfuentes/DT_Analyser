# Market Data Quality

Central enum: `QualityStatus` in `backend/app/market_data/quality.py`.

| Status | Meaning |
|--------|---------|
| `OK` | Full-quality consolidated data |
| `PARTIAL_FEED` | IEX or other partial feed — volume/RVOL not consolidated |
| `INSUFFICIENT_HISTORY` | Not enough prior sessions for rolling metric |
| `MISSING_BAR` | No bar for trading date |
| `CORPORATE_ACTION_AMBIGUITY` | Unsafe to compute rolling metrics (reserved; split API not wired) |
| `PROVIDER_ERROR` | Provider failure |
| `PENDING_EOD` | Current session not yet complete |

`quality_flags` (JSON list on `instrument_day_features`) can record simultaneous issues, e.g. `PARTIAL_FEED` + `INSUFFICIENT_HISTORY` + `PENDING_EOD` + `SPLIT_METADATA_UNAVAILABLE`. Primary `quality_status` is the most severe OK-overwriting status.

## Partial feed rule

If `is_consolidated = false`:

- Preserve feed name in storage
- Mark volume-derived features `PARTIAL_FEED`
- Default Graphs **omit** volume / RVOL50 / prior-day RVOL buckets (trades remain in Time / Behavior / Outcome)
- Price features (gap, SMA, ATR, movement, day type) still annotate
- `include_partial_feed=true` includes volume dimensions with an explicit warning

## Coverage display

Market-dimension reports include current-**cohort** coverage (after exploration filters):

- Matching trades
- Data available
- Coverage %
- Excluded count
- Exclusion reasons (`PARTIAL_FEED`, `INSUFFICIENT_HISTORY`, `MISSING_ENRICHMENT`, `PENDING_EOD`, …)

Filtering to Gap 10–20% makes that report’s cohort already require gap data; coverage is not a global enrichment rate.
