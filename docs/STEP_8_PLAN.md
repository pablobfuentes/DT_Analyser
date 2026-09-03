# Step 8 Plan — MFE / MAE + Exit Efficiency Analyzer

**Status:** Implemented (Step 8 complete).

**Goal:** Answer *what happened to the trade after I entered?* by computing **Maximum Favorable Excursion (MFE)**, **Maximum Adverse Excursion (MAE)**, **exit efficiency**, and related timing/capture metrics from **historical intraday market data** replayed against the **actual position lifecycle**. Activate the Graphs **EXECUTION QUALITY** section and add a dedicated **Exit Analyzer** page.

**Prerequisite context:** Steps 1–7 are treated as complete for planning purposes. Step 6 (permanent MANUAL vs AUTO comparison) remains **skipped** — AUTO is a valid source filter only. Step 7 provides R normalization (`initial_risk_amount`, `r_multiple`, `gross_realized_r`).

---

## Current State (Audit Summary)

| Area | Status | Notes |
|------|--------|-------|
| Intraday market data | **Missing** | `MarketDataProvider` exposes `get_daily_bars` only (`base.py`) |
| Intraday cache | **Missing** | `market_daily_bars` exists; no `market_intraday_bars` |
| Alpaca provider | Daily only | `timeframe=1Day` in `alpaca.py`; same API endpoint supports minute bars |
| Fake provider | Daily only | `FakeMarketDataProvider` + `build_flat_series`; no minute fixtures |
| Excursion model | **Missing** | No `trade_excursions` table or calculator |
| MFE/MAE anywhere | **Missing** | Grep finds only placeholders in docs/config |
| EXECUTION Graphs section | Placeholder | `("EXECUTION", "Execution Quality", False, "MFE_MAE")` in `config.py` |
| Execution metrics in METRICS | **Missing** | 6 dollar metrics only in `registry.py` |
| Exit Analyzer page | **Missing** | No `/exit-analysis` route |
| Trade Detail excursion panel | **Missing** | Risk panel exists; no MFE/MAE |
| Market Data page | Daily only | Enrich/recalculate for EOD features; no intraday stats |
| Position replay engine | **Partial foundation** | Step 2.5 `trade_executions` with `allocated_quantity`, chronological ordering documented in `TRADE_RECONSTRUCTION.md` — no mark-to-market replay yet |
| Holding interval | **Partial** | `trade.entry_time_utc` / `exit_time_utc` from reconstruction; excursion plan must use **first opening execution** and **final closing execution** timestamps (may differ slightly from normalized trade times on partial fills) |
| Step 7 risk for MFE R | **Assumed available** | `initial_risk_amount`, `r_multiple` on `Trade` (+ planned `trade_risk` per Step 7); `effective_realized_pnl` vs gross for exit efficiency |
| Step 5 Copilot exit | **Assumed available** | Plan expects linked Signal with `exit_signal_time_utc`, `mechanical_exit_price`, `mechanical_exit_reason` (per `STEP_5_PLAN.md` / `PINE_SIGNAL_EVENT_SCHEMA.md`) |
| Graphs filter engine | Ready | `TradeFilterSet`, URL serialization via `graphFilters.ts`, `apply_exploration` |
| Report aggregation | Ready | `_bucket_metrics` in `aggregation.py` — extend like Step 7 R metrics |
| Market enrichment pattern | **Reuse** | `MarketEnrichmentService`: scope → symbol-dates → cache-first → provider fetch → persist features → job tracking |
| CLI pattern | **Reuse** | `app/cli/enrich_market_data.py` — mirror for excursions |
| Quality framework | **Reuse/extend** | `QualityStatus` in `market_data/quality.py`; add excursion-specific statuses |
| Tests | **None for Step 8** | ~158 backend tests (Steps 1–4 + partial Step 3/7); no excursion tests |

### Critical constraints already documented elsewhere

- **Do NOT use daily high/low for intraday MFE** (Step 4 daily bars are EOD context only).
- **Do NOT use Pine strategy highs/lows** as market excursion substitutes.
- **Do NOT use post-exit prices in canonical MFE**.
- **Do NOT use pre-entry prices in MFE/MAE**.

### Reused foundations (do not rewrite)

- Step 2.5 signed-position reconstruction and `trade_executions.allocated_quantity`
- Step 4 provider registry, cache-first fetch, provenance (`provider`, `feed`, `is_consolidated`)
- Step 3 Graphs engine: annotate → filter → aggregate; `ReportCard` metric selector
- Step 7 risk: `initial_risk_amount`, R multiples, separate gross realized R for capture metrics
- Decimal-only money math; NY timezone via `analytics_tz()`

---

## Architecture Overview

```
Closed Trade + TradeExecutions (Step 2.5)
    │
    ├── Step 7 trade_risk ── initial_risk_amount, r_multiple, gross_realized_r
    ├── Step 5 signal link ── mechanical_exit_time/price (Copilot comparison)
    │
    ▼
ExcursionEnrichmentService
    │
    ├── determine holding interval (first ENTRY exec → last EXIT exec)
    ├── group symbol-day windows; extend +30m if post-exit research enabled
    ├── IntradayBarCache (market_intraday_bars) — cache-first
    ├── MarketDataProvider.get_intraday_bars (1Min) — fetch missing only
    │
    ▼
PositionReplayEngine
    ├── chronological execution events with allocated_quantity
    ├── at each bar: mark open qty (LONG: high favorable / low adverse; SHORT: inverse)
    ├── track position_mfe_amount, position_mae_amount, timestamps
    │
    ▼
trade_excursions (1:1 per trade)
    │
    ├── Graphs: EXECUTION section + execution metrics on ALL reports
    ├── GET /api/exit-analysis
    └── Trade Detail / Exit Analyzer UI
```

**Parallel to Step 4:** Same layering — provider abstraction → cache → enrichment orchestration → feature join at report annotate time.

---

## A. Intraday Data Architecture

```
app/market_data/
  base.py              ← add get_intraday_bars() to protocol
  models.py            ← add IntradayBar dataclass
  cache_intraday.py    ← load/store/missing-ranges (NEW)
  alpaca.py            ← implement minute bars
  fake.py              ← deterministic minute fixtures (NEW)
  registry.py          ← unchanged selection logic

app/db/models/market_data.py
  MarketIntradayBar    ← NEW table

app/services/excursion_enrichment/
  service.py           ← orchestration (mirror market_enrichment)
  calculator.py        ← MFE/MAE/efficiency formulas
  replay.py            ← position lifecycle replay (NEW)
  coverage.py          ← coverage stats

app/services/reports/
  excursion_features.py ← join trade_excursions into AnnotatedTrade.features
```

**Principle:** Raw intraday bars are source of truth. Excursion features are **recalculatable** from cache without refetching (`calculation_version` bump → recalculate only).

---

## B. Intraday Resolution

| Setting | Value |
|---------|-------|
| Primary resolution | **1 minute** (`timeframe = "1Min"`) |
| Stored on | `market_intraday_bars.timeframe`, `trade_excursions.data_resolution` |
| Future | Architecture allows `"1Sec"`, tick trades via same provider interface |

1-minute bars are **estimates**, not tick-perfect execution analysis. UI must always show resolution badge.

**Bar timestamp convention:** `bar_time_utc` = bar **open** time (Alpaca convention). Holding interval queries include all bars where `[bar_open, bar_open + 1min)` overlaps `[holding_start, holding_end]`.

---

## C. Extended-Hours Coverage

Target session window for fetch and cache:

```
04:00 – 20:00 America/New_York
```

Rationale: premarket momentum + after-hours activity common for this strategy.

Implementation:

- Provider request uses UTC bounds derived from NY session window per trading date spanned by holding interval.
- If provider returns no extended-hours bars, quality → `NO_INTRADAY_DATA` or `MISSING_BARS` with reason — do not fall back to daily bars.
- Trades at 07:15 NY must include that period in bar fetch range.

Alpaca: `feed=sip|iex` with appropriate session params; document feed limitations in quality status.

---

## D. Excursion Terminology

| Term | Meaning |
|------|---------|
| **MFE** | Maximum Favorable Excursion — greatest favorable move while position open |
| **MAE** | Maximum Adverse Excursion — greatest adverse move while position open |
| **Price MFE/MAE** | Per-share movement vs reference entry price (normalized: MFE ≥ 0, MAE ≤ 0) |
| **Position MFE/MAE** | Gross theoretical total P&L of actual position lifecycle at best/worst mark |
| **Exit Efficiency** | `gross_realized_pnl / position_mfe_amount × 100` when MFE > 0 |
| **R Left on Table** | `mfe_r − gross_realized_r` (observed opportunity not captured) |
| **Peak Giveback** | `position_mfe_amount − gross_realized_pnl` |
| **Gross Realized R** | `gross_realized_pnl / initial_risk_amount` — separate from Step 7 net-based R |
| **Post-Exit Extension** | Favorable move in trade direction **after** final exit (research only) |
| **Copilot Exit Comparison** | Actual exit vs linked Pine mechanical exit — **not** MANUAL vs AUTO |

Direction normalization: favorable is always **positive** for MFE; adverse is always **negative** for MAE, for both LONG and SHORT.

---

## E. MFE Formula

### Price MFE (reference entry = `trade.avg_entry_price`)

**LONG:**

```
price_mfe = max_valid_price_during_hold − entry
price_mfe_pct = price_mfe / entry × 100
```

**SHORT:**

```
price_mfe = entry − min_valid_price_during_hold
price_mfe_pct = price_mfe / entry × 100
```

`max_valid_price` / `min_valid_price` from intraday bars **while position qty ≠ 0**, plus execution prices as known observations (§100).

---

## F. MAE Formula

**LONG:**

```
price_mae = min_valid_price_during_hold − entry    (≤ 0)
price_mae_pct = price_mae / entry × 100
```

**SHORT:**

```
price_mae = entry − max_valid_price_during_hold    (≤ 0)
price_mae_pct = price_mae / entry × 100
```

---

## G. LONG/SHORT Normalization

| Direction | Favorable mark | Adverse mark |
|-----------|----------------|--------------|
| LONG | bar **HIGH** (open qty) | bar **LOW** |
| SHORT | bar **LOW** | bar **HIGH** |

Position-level marking uses same bar extrema applied to **current open signed quantity** at each replay step.

All stored `price_mfe` / `position_mfe_amount` values use **positive favorable** convention regardless of direction.

---

## H. Scale-In / Scale-Out Behavior

**Do not** use opening quantity × best price if partial exits occurred.

Use **Position P&L Replay** (§15):

1. Load `trade_executions` ordered by `execution.execution_time_utc`, tie-break per reconstruction rules.
2. For each event, apply `allocated_quantity` to signed position state.
3. Maintain: open qty, weighted avg cost basis, cumulative **realized gross P&L**.
4. At each bar boundary (and execution instant), compute:

```
total_hypothetical_pnl = realized_gross_to_date + mark_to_market(open_qty, bar_extreme)
```

5. Track max (MFE) and min (MAE) of `total_hypothetical_pnl`.

Scale-in updates cost basis before subsequent marks. Scale-out locks realized P&L; remaining qty continues to be marked.

**Tests:** Fixtures #106 (partial exit), #107 (scale-in).

---

## I. Partial-Position P&L Path

Example from spec:

```
LONG: BUY 100 @ 5.00
      SELL 50 @ 5.50   → realized +$25
      market → 5.80 on remaining 50
      SELL 50 @ 5.60
```

During open 50 @ basis 5.00, favorable mark at 5.80 → unrealized +$40 → total hypothetical +$65.

Position MFE = max over lifecycle (likely +$65), not 100 × (5.80 − 5.00).

Replay engine lives in `app/services/excursion_enrichment/replay.py` — **single source of truth**; must align with Step 2.5 allocation semantics.

---

## J. Boundary-Bar Ambiguity

1-minute OHLC does not reveal intra-bar sequence. An execution at 09:43:24 shares the 09:43 bar with unknown high/low ordering.

### Policy (v1 — dual estimates, approved)

Store **both** inclusive and conservative excursion estimates:

**Inclusive estimate (primary UI):**
- Use bar HIGH/LOW from every 1-minute bar overlapping a period in which some position was open.
- Badge: `1m estimate`.

**Conservative estimate (Trade Detail / diagnostics):**
- On entry/exit boundary bars where intra-bar ordering is unknowable, do **not** assume bar high/low occurred while the relevant position state existed.
- Use actual execution prices as known observations on ambiguous boundary portions.
- Interior bars (position open for full bar interval) use HIGH/LOW normally.
- Multiple executions within one minute: remain conservative; do not invent intra-bar ordering.

**Boundary uncertainty (diagnostic):**
```
mfe_boundary_spread_amount = inclusive_position_mfe − conservative_position_mfe
mfe_boundary_spread_r = inclusive_mfe_r − conservative_mfe_r
```
MAE spread uses directionally sensible equivalent. Not in main Graphs section v1; used in Trade Detail and completion audit.

Completion report must include: median/95th percentile MFE boundary spread R; counts where spread >0.25R and >0.50R.

**Never claim tick precision.**

---

## K. Exit Efficiency Formula

```
exit_efficiency_pct = gross_realized_pnl / position_mfe_amount × 100
```

Conditions:

- Only when `position_mfe_amount > 0`
- Use **gross** realized P&L (no fees) — measures price capture, not commission structure
- **Do not clamp** to [0, 100]
- Negative efficiency allowed (MFE positive, closed red)
- If result > 100%: preserve value; flag `EFFICIENCY_OVER_100` in quality/warnings

When `position_mfe_amount <= 0`: `exit_efficiency_pct = NULL`.

---

## L. R Left on Table

Requires Step 7 initial risk and MFE R:

```
mfe_r = position_mfe_amount / initial_risk_amount
gross_realized_r = gross_realized_pnl / initial_risk_amount
r_left_on_table = mfe_r − gross_realized_r
```

If risk missing: `mfe_r`, `mae_r`, `r_left_on_table` = NULL (price/dollar MFE still valid).

UI label: **Observed R Opportunity Not Captured** with tooltip explaining 1m estimate limitations.

Negative R left can occur when realized exceeds minute-bar estimated MFE — flag quality.

---

## M. Time-to-MFE / MAE

```
time_to_mfe_seconds = mfe_time_utc − holding_start_utc
time_to_mae_seconds = mae_time_utc − holding_start_utc
mfe_to_exit_seconds = holding_end_utc − mfe_time_utc
```

**Tie policy:** If same extreme on multiple bars, store **first** occurrence timestamp (§37).

**Precision:** Limited to bar resolution (~±60s). Display humanized (`42 sec`, `2m 15s`). Quality note on all timing fields.

`holding_start` = timestamp of first ENTRY allocation execution (not signal time).

---

## N. Giveback Analysis

```
peak_giveback_amount = position_mfe_amount − gross_realized_pnl
peak_giveback_r = peak_giveback_amount / initial_risk_amount   (if risk exists)
peak_giveback_pct = peak_giveback_amount / position_mfe_amount × 100   (when MFE > 0)
```

Relationship: when both defined, `peak_giveback_pct ≈ 100 − exit_efficiency_pct`.

Use for Graph **Peak Giveback %** and Exit Analyzer tables.

---

## O. Copilot Exit Comparison

**Not** MANUAL vs AUTO. Compare actual trade exit to **linked Pine Signal** mechanical exit when available.

From Step 5 signal fields:

- `exit_signal_time_utc` (or EXIT event time)
- `mechanical_exit_price`
- `mechanical_exit_reason`

Calculations:

```
exit_timing_delta_seconds = actual_exit_time − copilot_exit_time
```

**Price quality (direction-normalized):**

```
LONG:  copilot_exit_delta_price = actual_avg_exit − copilot_exit_price
SHORT: copilot_exit_delta_price = copilot_exit_price − actual_avg_exit
```

Positive = actual exit better than Copilot.

Coverage metrics separate from excursion coverage:

```
Trades / Linked Signals / Copilot Exit Available / Coverage %
```

Panel hidden when Copilot exit unavailable.

---

## P. Graph Integration

### P1. Activate EXECUTION section

Set `("EXECUTION", "Execution Quality", True, None)` when excursion data exists.

| Report key | Title | Feature key |
|------------|-------|-------------|
| `mfe_r_distribution` | MFE Distribution | `mfe_r_bucket` |
| `mae_r_distribution` | MAE Distribution | `mae_r_bucket` |
| `exit_efficiency` | Performance by Exit Efficiency | `exit_efficiency_bucket` |
| `r_left_on_table` | R Left on Table | `r_left_bucket` |
| `time_to_mfe` | Time to MFE | `time_to_mfe_bucket` |
| `time_to_mae` | Time to MAE | `time_to_mae_bucket` |
| `mfe_to_exit` | Time from MFE to Final Exit | `mfe_to_exit_bucket` |
| `peak_giveback` | Peak Giveback % | `peak_giveback_bucket` |
| `copilot_exit_timing` | Actual Exit vs Copilot Exit Time | `copilot_timing_bucket` |
| `copilot_exit_price` | Actual Exit Price vs Copilot Exit | `copilot_price_bucket` |

Centralize bucket definitions in `reports/config.py` (like Step 4/7).

### P2. Extend METRICS registry

Add to `registry.py` METRICS (and `_bucket_metrics`):

| key | label |
|-----|-------|
| `average_mfe_r` | Average MFE R |
| `average_mae_r` | Average MAE R |
| `average_exit_efficiency` | Average Exit Efficiency % |
| `average_r_left` | Average R Left on Table |
| `average_peak_giveback` | Average Peak Giveback % |
| `average_time_to_mfe` | Average Time to MFE |
| `average_time_to_mae` | Average Time to MAE |
| `excursion_coverage_pct` | Excursion Coverage (tooltip) |

Every existing report (TIME, INSTRUMENT, STRATEGY, etc.) gains these metrics via extended aggregation — **no duplicate dimension reports**.

### P3. Bucket coverage tooltips

Per bucket:

```
Trades: 20
Excursion Available: 17
R-qualified: 14
Avg Exit Efficiency: 42%
Avg MFE R: 2.1R
```

### P4. Exploration filters (click-to-filter)

Add to `TradeFilterSet.EXPLORATION_KEYS` + `EXPLORATION_KEYS` frontend:

- `mfe_r_bucket`
- `mae_r_bucket`
- `exit_efficiency_bucket`
- `r_left_bucket`
- `time_to_mfe_bucket`
- `time_to_mae_bucket`
- `mfe_to_exit_bucket`
- `peak_giveback_bucket`
- `copilot_timing_bucket` (when applicable)
- `excursion_quality` (quality tier filter — §92)

URL serialization via existing `graphFilters.ts` pattern.

### P5. Quality filter (§92)

Exploration or global control:

| Level | Includes |
|-------|----------|
| Full / Consolidated | `OK`, boundary ambiguous only |
| Include Estimated | + `ESTIMATED_1M` |
| Include Partial Feed | + `PARTIAL_FEED` |
| All | all statuses except hard failures |

Default: do not silently mix partial-feed extrema with consolidated without user opt-in.

---

## Q. Exit Analyzer UX

**Route:** `/exit-analysis` (nav: Dashboard | Graphs | Trades | Signals | Exit Analyzer | Market Data)

### Layout

1. **Global filters** — reuse `DashboardFiltersBar` + exploration chips
2. **Summary cards** — Avg MFE R, Avg MAE R, Avg Actual R, Avg/Median Exit Efficiency, Avg R Left, Avg Peak Giveback %, Median Time to MFE, coverage stats
3. **Capture thresholds** — % trades capturing ≥25/50/75/90% of MFE
4. **Opportunity metrics** — Positive MFE → losing exit; reached ≥1R/≥2R MFE but closed below thresholds
5. **Scatter charts** (purpose-built, not Research Lab):
   - MFE R vs Actual R (diagonal Y=X reference if feasible)
   - MAE R vs Actual R
6. **Efficiency distribution** histogram
7. **Tables:**
   - Biggest R Left on Table (sort desc)
   - Biggest Peak Giveback
   - Best Capture (min MFE threshold centralized, e.g. ≥0.5R)
8. **Optional:** simple intraday price chart on Trade Detail (§84) — deferrable

**API:** `GET /api/exit-analysis` — summary + table payloads; graphs reuse `/api/reports`.

---

## R. Data-Quality Model

### Quality model (approved)

**Primary tier** (`quality_status`): e.g. `OK`, `ESTIMATED_1M`, `NO_INTRADAY_DATA`, `PROVIDER_ERROR`, `CORPORATE_ACTION_AMBIGUITY`, `OPEN_TRADE`, `PENDING`.

**Flags array** (`quality_flags_json`): non-exclusive, e.g. `["BOUNDARY_BAR_AMBIGUITY", "PARTIAL_FEED", "SPARSE_INTERVAL", "EFFICIENCY_OVER_100"]`.

Hard failures: `NO_INTRADAY_DATA`, `PROVIDER_ERROR`, `CORPORATE_ACTION_AMBIGUITY`. Boundary warnings do not erase feed-quality information.

### Additional fields

| Field | Purpose |
|-------|---------|
| `boundary_ambiguity` | bool — entry/exit bar issue |
| `efficiency_over_100` | bool |
| `missing_bar_count` | int |
| `data_provider`, `data_feed`, `data_resolution`, `is_consolidated` | provenance |
| `calculation_version` | e.g. `"1"` — recalc without refetch |

### Coverage API (`GET /api/excursions/coverage`)

Report:

- Closed trades / excursion enriched / MFE-MAE coverage %
- R-qualified excursion coverage %
- Consolidated vs partial feed counts
- Boundary ambiguous count
- Missing / no-data breakdown

### Sparse intervals vs missing data (approved correction)

**Absent minute bar ≠ missing data.** Low-float stocks may have minutes with no executions and therefore no bar.

Rules:
- Never create synthetic/interpolated bars.
- Use observed bars only; execution prices remain authoritative observations.
- Sparse bar sequences are allowed.
- Do **not** infer LULD halt solely from bar absence.
- `MISSING_BARS` = positive evidence provider data is incomplete/unavailable — not merely absent consecutive timestamps.
- Optional `SPARSE_INTERVAL` diagnostic flag when useful.
- Halt status unknown unless metadata available.

Post-halt execution prices remain valid observation points.

### Corporate actions

If intraday prices and execution prices may be on incompatible bases (split mismatch) → `CORPORATE_ACTION_AMBIGUITY`; skip or null excursion metrics.

---

## S. Tests

### Backend (`tests/test_step_8_excursions.py` + fixtures)

| # | Topic | Spec ref |
|---|-------|----------|
| 1 | Simple LONG MFE/MAE/efficiency | #101 |
| 2 | Simple SHORT | #102 |
| 3 | R normalization | #103 |
| 4 | Negative exit efficiency | #104 |
| 5 | No positive MFE → NULL efficiency | #105 |
| 6 | Partial exit replay | #106 |
| 7 | Scale-in replay | #107 |
| 8 | Boundary bar entry | #108 |
| 9 | Boundary bar exit | #109 |
| 10 | Missing bar / halt gap | #110 |
| 11 | Time to MFE | #111 |
| 12 | MFE tie → first timestamp | #112 |
| 13 | Copilot exit LONG | #113 |
| 14 | Copilot exit SHORT | #114 |
| 15 | Post-exit not in MFE | #115 |
| 16 | Exploration filters | #116 |
| 17 | Day-of-week Avg Exit Efficiency | #117 |
| 18 | Signal RVOL Avg MFE R | #117 |
| 19 | Coverage stats | #118 |
| 20 | Cache — second enrich no provider calls | #119 |
| 21 | Same symbol/day batching | #120 |
| 22 | Fake intraday provider offline | #121 |
| 23 | 10k-trade performance smoke | #123 |

Extend `FakeMarketDataProvider`:

```python
register_fake_intraday_series(symbol, bars: list[IntradayBar])
build_minute_series(symbol, start, minutes, ohlc_path)
```

Deterministic fixtures under `tests/fixtures/intraday/`.

### Frontend (Vitest)

- EXECUTION placeholder vs active
- Each new graph report renders
- Coverage + quality badges
- Exit Analyzer route + summary + tables
- Trade Detail excursion + Copilot panels
- Filter chips + URL persistence
- No Recharts internal assertions

---

## T. Known Limitations

1. **1-minute resolution** — not tick-perfect; boundary bars inherently ambiguous.
2. **Partial feeds (IEX)** — may understate true MFE/MAE vs consolidated SIP.
3. **Inclusive boundary policy** — may overestimate extremes on entry/exit minute; flagged not hidden.
4. **Efficiency > 100%** — possible due to bar ambiguity, scale effects, feed gaps; flagged for review.
5. **R left on table** — descriptive, not proof of executable profit at MFE timestamp.
6. **Post-exit extension** — research context only; separate from MFE.
7. **Copilot comparison** — only when Step 5 signal EXIT exists; not a behavior score.
8. **Multi-day holds** — supported but minute-bar cache grows; session-spanning fetch required.
9. **SQLite storage** — minute bars can grow large; monitor symbol-day counts; document expected DB size.
10. **Halts / LULD** — gaps remain gaps; no synthetic fill.
11. **Stop-then-run pattern** (§75) — only when adverse/recovery ordering clear across distinct bars.
12. **Step 6 skipped** — no MANUAL-vs-AUTO exit comparison.
13. **Research Lab deferred** — no custom scatter builder, Sharpe, Monte Carlo, etc.

---

## Data Model

### `market_intraday_bars`

```sql
CREATE TABLE market_intraday_bars (
    id INTEGER PRIMARY KEY,
    symbol TEXT NOT NULL,
    bar_time_utc TIMESTAMPTZ NOT NULL,
    timeframe TEXT NOT NULL DEFAULT '1Min',
    open NUMERIC(18,6) NOT NULL,
    high NUMERIC(18,6) NOT NULL,
    low NUMERIC(18,6) NOT NULL,
    close NUMERIC(18,6) NOT NULL,
    volume INTEGER NOT NULL,
    vwap NUMERIC(18,6),
    trade_count INTEGER,
    provider TEXT NOT NULL,
    feed TEXT NOT NULL,
    is_consolidated BOOLEAN NOT NULL,
    adjustment_mode TEXT NOT NULL,
    session_type TEXT,
    raw_payload_json TEXT,
    fetched_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    UNIQUE(symbol, bar_time_utc, timeframe, provider, feed, adjustment_mode)
);
CREATE INDEX ix_intraday_symbol_time ON market_intraday_bars(symbol, bar_time_utc);
```

### `trade_excursions`

```sql
CREATE TABLE trade_excursions (
    id INTEGER PRIMARY KEY,
    trade_id INTEGER NOT NULL UNIQUE REFERENCES trades(id) ON DELETE CASCADE,

    data_provider TEXT,
    data_feed TEXT,
    data_resolution TEXT NOT NULL DEFAULT '1Min',
    is_consolidated BOOLEAN,

    holding_start_utc TIMESTAMPTZ NOT NULL,
    holding_end_utc TIMESTAMPTZ NOT NULL,

    -- Price excursions (normalized)
    price_mfe NUMERIC(18,6),
    price_mae NUMERIC(18,6),
    price_mfe_pct NUMERIC(18,8),
    price_mae_pct NUMERIC(18,8),

    -- Position excursions (gross, preferred for efficiency)
    position_mfe_amount NUMERIC(18,6),
    position_mae_amount NUMERIC(18,6),
    mfe_r NUMERIC(18,8),
    mae_r NUMERIC(18,8),

    mfe_time_utc TIMESTAMPTZ,
    mae_time_utc TIMESTAMPTZ,
    time_to_mfe_seconds INTEGER,
    time_to_mae_seconds INTEGER,
    mfe_to_exit_seconds INTEGER,

    exit_efficiency_pct NUMERIC(18,8),
    r_left_on_table NUMERIC(18,8),
    gross_realized_r NUMERIC(18,8),

    peak_giveback_amount NUMERIC(18,6),
    peak_giveback_r NUMERIC(18,8),
    peak_giveback_pct NUMERIC(18,8),

    -- Post-exit research (optional)
    post_exit_favorable_5m NUMERIC(18,6),
    post_exit_favorable_15m NUMERIC(18,6),
    post_exit_favorable_30m NUMERIC(18,6),
    post_exit_favorable_5m_r NUMERIC(18,8),
    post_exit_favorable_15m_r NUMERIC(18,8),
    post_exit_favorable_30m_r NUMERIC(18,8),

    -- Copilot comparison
    copilot_exit_time_utc TIMESTAMPTZ,
    copilot_exit_price NUMERIC(18,6),
    copilot_exit_delta_seconds INTEGER,
    copilot_exit_delta_price NUMERIC(18,6),
    copilot_exit_delta_pct NUMERIC(18,8),

    quality_status TEXT NOT NULL,
    quality_flags_json TEXT,
    boundary_ambiguity BOOLEAN DEFAULT FALSE,
    efficiency_over_100 BOOLEAN DEFAULT FALSE,
    missing_bar_count INTEGER DEFAULT 0,

    calculation_version TEXT NOT NULL DEFAULT '1',
    calculated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX ix_trade_excursions_trade_id ON trade_excursions(trade_id);
CREATE INDEX ix_trade_excursions_quality ON trade_excursions(quality_status);
```

### `excursion_enrichment_jobs` (mirror `market_enrichment_jobs`)

Track: trades requested, symbol-days, bars fetched, cache hits, provider requests, success/missing/error counts.

---

## Provider Extension

```python
# app/market_data/models.py
@dataclass
class IntradayBar:
    symbol: str
    bar_time_utc: datetime  # bar open, UTC
    timeframe: str          # "1Min"
    open, high, low, close: Decimal
    volume: int
    provider, feed, adjustment_mode: str
    is_consolidated: bool
    fetched_at: datetime
    vwap: Decimal | None = None
    trade_count: int | None = None
    session_type: str | None = None
    raw_payload_json: str | None = None

# app/market_data/base.py
def get_intraday_bars(
    self,
    symbols: list[str],
    start_utc: datetime,
    end_utc: datetime,
    timeframe: str = "1Min",
    adjustment_mode: str = "raw",
    stats: FetchStats | None = None,
) -> list[IntradayBar]: ...
```

**Alpaca implementation:** Same `/v2/stocks/bars` endpoint, `timeframe=1Min`, `start`/`end` as ISO8601 UTC.

**Cache strategy (approved):** **Full symbol-day session cache** for each NY trading date touched (04:00–20:00 America/New_York). Keep for v1; benchmark with 10k-trade test. Do not switch to fragmented trade-window caching unless benchmark shows material storage problem.

**Raw payload:** Do NOT store full provider JSON per minute bar by default. Persist normalized OHLCV + provenance fields only. Optional raw payload behind `LTA_INTRADAY_STORE_RAW_PAYLOAD` debug flag.

**Fetch range:** `holding_start` → `holding_end` (+ 30 min if post-exit enabled). Never fetch unrelated weeks.

---

## Enrichment Workflow

Mirror `MarketEnrichmentService`:

```
POST /api/excursions/enrich?scope=missing|all|selected
POST /api/excursions/recalculate   ← cache only, bump calculation_version
GET  /api/excursions/coverage
GET  /api/excursions/trades/{trade_id}
```

Steps per trade:

1. Skip if `OPEN` → status `OPEN_TRADE`
2. Load executions + allocations; compute `holding_start`, `holding_end`
3. Determine symbol-days + UTC fetch window
4. Load cached intraday bars; fetch missing ranges only
5. Run position replay + excursion calculator
6. Upsert `trade_excursions`
7. Update job stats

**Batching:** Group trades by `(symbol, ny_trading_date)` before provider calls (§47, #120).

**Automatic vs manual:** Mark new closed trades `PENDING`; user triggers **Enrich Missing** from Market Data page or CLI. No blocking on import.

---

## CLI

```bash
python -m app.cli.enrich_excursions --missing
python -m app.cli.enrich_excursions --dry-run --ticker NCRA --start 2026-09-01 --end 2026-09-02
python -m app.cli.enrich_excursions --recalculate
```

Dry-run output: trades needing enrichment, unique symbol-days, cache coverage, estimated provider requests/bar count — no mutation.

---

## Frontend Work

| File | Change |
|------|--------|
| `pages/ExitAnalysisPage.tsx` | NEW — summary, scatters, tables |
| `pages/MarketDataPage.tsx` | Intraday section + enrich excursions buttons |
| `pages/TradeDetailPage.tsx` | Excursion panel, Copilot comparison, post-exit panel, resolution badge |
| `pages/GraphsPage.tsx` | EXECUTION section active |
| `types/reports.ts` | Execution metrics + bucket coverage fields |
| `types/excursions.ts` | NEW |
| `api/excursions.ts` | NEW |
| `utils/graphFilters.ts` | New exploration keys |
| `main.tsx` | Route + nav link |
| `components/graphs/ReportCard.tsx` | Execution metric formatting, coverage tooltip |

---

## Documentation Deliverables (implementation phase)

Create:

- `docs/INTRADAY_MARKET_DATA.md`
- `docs/MFE_MAE.md`
- `docs/EXIT_EFFICIENCY.md`
- `docs/EXIT_ANALYZER.md`

Update:

- `docs/MARKET_DATA.md`
- `docs/REPORT_DIMENSIONS.md`
- `docs/GRAPHS_AND_REPORTS.md`
- `docs/DATABASE_SCHEMA.md`
- `docs/ARCHITECTURE.md`
- `README.md`

---

## Implementation Phases

### Phase 1 — Intraday infrastructure

- `IntradayBar` model + `MarketIntradayBar` table + cache module
- Extend `MarketDataProvider` + Alpaca + Fake minute provider
- Unit tests for cache, fetch range, extended hours

### Phase 2 — Position replay + excursion calculator

- `replay.py` + `calculator.py`
- `trade_excursions` table
- Core tests #101–#115

### Phase 3 — Enrichment service + API + CLI

- `ExcursionEnrichmentService`, jobs, coverage API
- Market Data page integration
- Cache/batch tests #119–#121

### Phase 4 — Graphs integration

- Bucket constants, EXECUTION reports, METRICS extension, `_bucket_metrics`
- Exploration filters + quality filter
- Report tests #116–#118

### Phase 5 — Exit Analyzer + Trade Detail UI

- `/exit-analysis` page, scatters, tables
- Trade Detail panels
- Frontend tests

### Phase 6 — Docs + validation

- All doc files
- 10k performance/storage audit (#123)
- Manual real-data validation (#131) — 5 trades vs TradingView
- Quality audit (#132)
- Completion report (#133)

---

## Definition of Done

Matches spec §130 (63 items): intraday provider + cache, extended hours, LONG/SHORT price and position MFE/MAE, partial exit/scale-in, boundary honesty, exit efficiency (including negative and >100%), R metrics, timing metrics, giveback, Copilot comparison, post-exit separated, EXECUTION graphs active, execution metrics on all existing reports, exploration filters, Exit Analyzer page, Trade Detail panel, cache efficiency, all prior step tests pass, Step 8 tests pass, production build passes.

**Explicitly NOT in Step 8:** Research Lab (custom scatter, Sharpe, Monte Carlo, etc.), MANUAL-vs-AUTO comparison, MFE from daily bars or Pine highs.

---

## Open Questions for Review

1. ~~Cache granularity~~ → **Full symbol-day 04:00–20:00 NY** (approved).
2. ~~Boundary estimates~~ → **Both inclusive + conservative** with spread diagnostics (approved).
3. ~~Post-exit~~ → **5/15/30m included in v1** (approved).
4. ~~Intraday chart~~ → **Optional; lowest priority**; API structured for future chart.
5. ~~Step 5~~ → **Audit at Phase 1/2**; Copilot comparison only if fields exist.
6. ~~Best capture threshold~~ → **0.50R centralized config**, no user setting yet.
7. ~~SQLite limit~~ → **No hard limit**; track size + advisories only.

---

*End of Step 8 Plan — awaiting review before implementation.*
