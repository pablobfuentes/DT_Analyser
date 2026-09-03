# Database Schema

SQLite database: `backend/data/trader_analyzer.db`

## Tables

### accounts

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| name | TEXT UNIQUE | |
| source | TEXT | TRADINGVIEW_MANUAL, TRADINGVIEW_AUTO |
| currency | TEXT | Default USD |
| is_simulated | BOOLEAN | |
| starting_equity | NUMERIC | Nullable; for dashboard equity curve |
| created_at, updated_at | DATETIME | UTC |

### import_batches

Tracks each CSV import with counts and status (PREVIEW, PROCESSING, SUCCESS, PARTIAL, FAILED).

Key fields: `file_hash` (SHA-256), `parser_name`, `parser_version`, `metadata_json` (timezone, etc.)

### executions

Individual fills from manual/account exports.

**Unique:** `(account_id, execution_fingerprint)`

Sides: BUY, SELL, SELL_SHORT, BUY_TO_COVER, UNKNOWN

### trades

Normalized round-trip trades.

**Unique:** `(account_id, trade_fingerprint)`

Directions: LONG, SHORT  
Status: OPEN, CLOSED

Includes `pnl_mismatch_flag` when source P&L differs from calculated beyond tolerance.

Risk fields (Step 3): `initial_stop_price`, `initial_risk_per_share`, `initial_risk_amount`, `r_multiple`, `risk_source`, `risk_notes`, `risk_updated_at` — all nullable until manually entered or imported (Pine, Step 4).

### trade_executions

Join table linking trades to executions.

| Column | Notes |
|--------|-------|
| trade_id, execution_id | Composite PK |
| role | ENTRY or EXIT |
| allocated_quantity | Shares of execution allocated to this trade (flip support) |

Same execution may appear in two trades after a position flip with different allocated quantities.

### import_errors

Row-level errors from partial imports.

| Column | Notes |
|--------|-------|
| resolved_at | Nullable; set when reconstruction errors superseded by rebuild |

## Indexes

- `import_batches.file_hash`
- `executions.ticker`, `executions.execution_time_utc`
- `trades.ticker`, `trades.entry_time_utc`

## Market data (Step 4)

| Table | Unique / notes |
|-------|----------------|
| `market_daily_bars` | `(symbol, trading_date, provider, feed, adjustment_mode)` |
| `instrument_day_features` | `(symbol, trading_date, provider, feed, adjustment_mode, calculation_version)` — SPY benchmark uses this table |
| `trade_market_features` | one active row per `trade_id` (FK cascade); points at provenance-specific feature ids |
| `market_enrichment_jobs` | job stats: provider/feed, cache hits, bars fetched, success/missing/errors |
| `market_cache_coverage` | probed start/end per symbol+provenance so weekends/holidays/listing gaps are not refetched |

There is no `benchmark_day_features` table (plan conceptual table superseded).

## Research Lab (Step 9)

Lightweight saved artifacts. Candidate rules never modify Pine or risk.

### saved_cohorts

| Column | Notes |
|--------|-------|
| name, description | |
| filter_json | Graph exploration params |
| research_mode | PRE_ENTRY_ONLY / ALL_FEATURES |
| created_at, updated_at | UTC |

### research_views

| Column | Notes |
|--------|-------|
| name | |
| global_scope_json | Date/account/source/direction/ticker |
| cohort_a_json, cohort_b_json | Name + filters |
| visualization_json | Chart, X/Y, metric |
| research_mode | |
| created_at, updated_at | UTC |

### candidate_rules

| Column | Notes |
|--------|-------|
| filter_json, research_mode | Immutable original on v1 |
| research_start, research_end | Optional date strings |
| cutoff_at | Forward-sample boundary; preserved on revise |
| rule_version, parent_id | Version N+1 inserts a new row |
| status | RESEARCH / FORWARD_TESTING / RETIRED — never PROVEN |
| statistics_version, bootstrap_seed, bootstrap_iterations | Reproducibility |

### pattern_snapshots

Starred heatmap/multi-factor/comparison cells. `metrics_json` is the observed snapshot at save time.

### automation_jobs / automation_runs / automation_run_steps / automation_file_events

Persistent inbox and EOD work. File identity is SHA-256, not filename. See [AUTOMATION_WORKFLOW.md](AUTOMATION_WORKFLOW.md).

### app_preferences / daily_workflow_days

User settings (no secrets) and explicit no-trade NY dates.

### journal_entries / journal_tags / journal_entry_tags / journal_attachments

Subjective notes and screenshot metadata. Image bytes live on disk under `screenshots/`.

### daily_reviews / weekly_reviews

User reflection plus frozen `metrics_snapshot_json` at complete time.

### backup_records

MANUAL / DAILY / PRE_MIGRATION / PRE_RESTORE. Path, checksum, verification.

SQLite now uses WAL + `busy_timeout=5000`.

## Initialization

Schema created via SQLAlchemy `Base.metadata.create_all()` on startup. Incremental column/index adds via `app/db/migrate.py` (including the instrument-feature provenance unique key). Existing user rows are not dropped.
