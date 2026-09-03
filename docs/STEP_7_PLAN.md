# Step 7 Plan — Risk, R-Multiple, Expectancy & Drawdown Analytics

**Status:** Implemented and audited 2026-09-02. See `docs/STEP_5_7_AUDIT.md`.

**Goal:** Answer *how good are my results relative to the risk I took?* using **R** (1R = actual initial dollar risk) as the normalized unit. Extend Dashboard, Graphs, Trade Detail, and Trades table with auditable risk data, cohort-aware analytics, and R metrics across every existing report dimension.

**Prerequisite context:** Steps 1–5 are treated as complete for planning purposes. Step 6 (permanent MANUAL vs AUTO comparison) is **skipped by product decision** — AUTO remains a valid trade source; do not build dedicated comparison analytics.

---

## Current State (Audit Summary)

| Area | Status | Notes |
|------|--------|-------|
| Trade model | Partial | `initial_stop_price`, `initial_risk_per_share`, `initial_risk_amount`, `r_multiple`, `risk_source`, `risk_notes`, `risk_updated_at` on `trades` |
| Dedicated `trade_risk` table | **Missing** | Spec prefers auditable model; not yet created |
| Risk calculation | **Partial** | `app/services/analytics/risk.py` — LONG/SHORT validation, explicit override, R from `effective_realized_pnl`, gross fallback warning |
| Planned vs actual risk | **Missing** | No `planned_entry`, `planned_stop`, `planned_risk_amount`, `allowed_risk` storage |
| Pine auto-population | **Blocked / partial** | `PINE` in `VALID_RISK_SOURCES`; no signal link → stop pipeline in backend yet (Step 5 backend files not present in repo at audit; Pine SIGNALLOG exists in `pine/`) |
| Manual risk API | **Done** | `PATCH /api/trades/{id}/risk` |
| Trade Detail risk panel | **Partial** | Actual fields + manual edit; no planned risk, risk % equity, P&L basis badge |
| Trades list risk filter | **Partial** | `has_risk=yes|no` query param; no R min/max columns |
| Dashboard advanced analytics | **Partial** | `build_advanced_analytics`: dollar expectancy, profit factor, payoff, R stats, streaks, drawdown $, cumulative R series, R distribution (counts only) |
| R drawdown | **Missing** | Dollar drawdown exists; no R peak/trough drawdown |
| R Profit Factor / R Payoff | **Missing** | Dollar versions only |
| Equity-at-entry / risk % equity | **Missing** | No no-lookahead equity-before-entry |
| Loss beyond 1R | **Missing** | |
| R coverage breakdown by reason | **Partial** | Count + % only; no reason taxonomy |
| Graphs RISK section | Placeholder | `("RISK", "Risk & R", False, "RISK_ANALYTICS")` in `config.py` |
| Graphs R metrics on all reports | **Missing** | `METRICS` has 6 dollar metrics only; `_bucket_metrics` has no R fields |
| `/risk` coverage page | **Missing** | |
| Source comparison advanced | Exists | `extend_source_comparison_advanced` — **deprioritize** per Step 6 skip; keep AUTO as ordinary source |
| Tests | **Partial** | `test_step_3_analytics.py` (~17 tests): R long/short, explicit risk, expectancy, PF, drawdown fixture, streaks, coverage; missing scale-in, Pine, planned risk, R PF, R DD, equity-at-entry, graph R metrics |
| Docs | **Partial** | `RISK_AND_R_MULTIPLE.md`, `EXPECTANCY.md`, `DRAWDOWN.md` — pre–Step 7 scope |

### Reused foundations (do not rewrite)

- `effective_realized_pnl`, `classify_outcome`, `win_rate_pct`, `decimal_str`, `breakeven_tolerance`
- Step 2.5 `avg_entry_price`, `quantity` (opening cycle quantity, not turnover)
- `equity_baseline`, `pre_period_realized_pnl`, `build_equity_series`, `summarize_drawdown`
- `r_statistics`, `r_distribution` buckets, `compute_streaks`
- Dashboard filter model + Graphs exploration engine
- Decimal-only money math via `app/utils/money.py`

---

## Architecture Overview

```
Trades (Step 1/2.5)
    │
    ├── trade_risk (NEW 1:1) ── planned + actual + quality + sources
    │       ▲
    │       │ populate / recalc
    ├── Signal link (Step 5) ── planned_stop, planned_entry, suggested_shares, allowed_risk
    ├── Manual PATCH /api/trades/{id}/risk
    └── Import (future authoritative stop)
            │
            ▼
    RiskService.recalculate(trade)  →  cache on trades.* + trade_risk.*
            │
            ├── R = effective_realized_pnl / actual_initial_risk
            ├── risk_pct_equity (no-lookahead equity at entry)
            └── stop_distance_pct
            │
            ▼
    Analytics layers
    ├── Dashboard (Edge summary, charts)
    ├── GET /api/risk/coverage (NEW)
    └── Graphs aggregation (_bucket_metrics + RISK section reports)
```

**Design choice — `trade_risk` vs `trades` columns:**

- Add **`trade_risk`** (1:1, FK `trade_id` UNIQUE) for auditable planned/actual distinction, quality enums, and derived snapshots.
- **Keep denormalized cache** on `trades` (`initial_stop_price`, `initial_risk_amount`, `r_multiple`, …) for list queries and backward-compatible API — updated atomically by `RiskService`.
- Optional lightweight **`risk_audit_log`** (append-only) for manual edits; reuse pattern from `apply_risk_to_trade` logging if table omitted in v1.

---

## A. Risk Terminology

| Term | Definition |
|------|------------|
| **1R** | Actual initial dollar risk of the trade at entry — the R denominator |
| **R-multiple** | `effective_realized_pnl / actual_initial_risk_amount` |
| **R-qualified trade** | Closed trade with `actual_initial_risk_amount > 0` and usable realized P&L |
| **Planned risk** | What Pine/signal suggested before fill (entry, stop, shares, allowed budget) |
| **Actual initial risk** | From **actual** avg entry, **opening** quantity, and **initial stop** (or explicit override) |
| **Initial stop** | Stop price in effect at trade open — not exit, not trailing, not reconstructed day low |
| **Opening quantity** | Position size at open (Step 2.5 cycle qty; scale-in → total opening qty) |
| **Risk / share** | Direction-specific distance entry → stop |
| **R coverage** | `R-qualified / closed trades in cohort` |
| **Equity at entry** | Account starting equity + realized P&L from prior **closed** trades with `exit_time < entry_time` |
| **Risk % equity** | `actual_initial_risk / equity_at_entry × 100` |
| **Loss beyond initial risk** | R &lt; breach threshold (default −1.05R) — discipline metric, not automatic rule violation |

---

## B. Actual vs Planned Risk Distinction

These are **independently stored and displayed**.

| Field | Source | Use |
|-------|--------|-----|
| `planned_entry_price` | Pine signal | Display + planned risk calc |
| `planned_stop_price` | Pine signal | Initial stop default when linked |
| `suggested_shares` | Pine signal | Planned risk calc |
| `planned_risk_amount` | Calculated | `(planned entry − planned stop) × shares` (direction-aware) |
| `allowed_risk` | Pine signal | Budget metadata — **not** R denominator |
| `actual_*` | Trade entry/qty + initial stop | **Authoritative for R** |

**UI rule:** Trade Detail shows both blocks. If `|planned − actual| > tolerance`, show non-blocking discrepancy note.

**Tests:** Fixtures #75 (Pine actual ≠ allowed), #76 (planned 100 vs actual 150 both preserved).

---

## C. Risk-Source Hierarchy

Precedence for **authoritative actual risk**:

1. **MANUAL** explicit `explicit_initial_risk_amount` (user override)
2. **MANUAL** explicit initial stop → derived amount
3. **PINE_SIGNAL** linked signal `planned_stop_price` → derived from actual entry/qty
4. **IMPORTED** authoritative stop from import metadata (if/when available)
5. **CALCULATED** from stored stop without signal link
6. **UNKNOWN** — no stop, no explicit amount

**Stop source** (separate enum): `PINE_SIGNAL | MANUAL | IMPORTED | UNKNOWN`

**Important:** `allowed_risk` from Pine is never substituted for actual initial risk merely because it exists.

Map existing `risk_source` values: keep `PINE` → alias `PINE_SIGNAL` in API/UI for clarity.

---

## D. Initial-Stop Logic

For Pine-linked trades with **CONFIRMED** link:

- Default `initial_stop_price` = signal `planned_stop_price`
- User manual stop override → `stop_source=MANUAL`, `risk_source=MANUAL`, preserve prior Pine stop in `trade_risk` for audit
- Do **not** substitute: exit price, day low, ATR stop, pullback low reconstructed post hoc

On signal link change/unlink: recalculate derived fields unless manual override flag set (`risk_quality_status=MANUAL_OVERRIDE`).

---

## E. LONG/SHORT Risk Formulas

**LONG**

```
risk_per_share = avg_entry_price − initial_stop_price   (stop < entry)
actual_initial_risk = risk_per_share × opening_quantity
```

**SHORT**

```
risk_per_share = initial_stop_price − avg_entry_price   (stop > entry)
actual_initial_risk = risk_per_share × opening_quantity
```

Implementation: extend existing `risk_per_share_from_stop` / `validate_stop_for_direction` in `risk.py`. **Never** use `abs(entry − stop)` when orientation invalid.

---

## F. Scaled-Entry Handling

When `entry_style = scale_in` (from `features.py` behavior):

- Use `trade.avg_entry_price` and `trade.quantity` (already weighted opening totals from Step 2.5)
- Single initial stop applies to full opening position
- If future evidence suggests mid-scale stop change: set `risk_quality_status=AMBIGUOUS_SCALE_IN`; do not invent multi-leg risk

**Test:** Fixture #77 — 100@4.00 + 200@4.10, stop 3.90 → avg 4.066…, qty 300, Decimal risk.

---

## G. R Formula

```
R = effective_realized_pnl / actual_initial_risk_amount
```

- Use **unrounded** Decimal for aggregates; store ≥8 decimal places; display 2 decimals (`+0.74R`)
- `actual_initial_risk_amount <= 0` or missing → `R = NULL`
- P&L basis: NET if fees included in effective P&L, else GROSS with `r_pnl_basis=GROSS` flag

Existing `compute_r_multiple` already implements core logic — extend to persist basis on `trade_risk`.

---

## H. Dollar Expectancy

```
Dollar Expectancy = sum(effective_realized_pnl) / count(closed trades in cohort)
```

Breakevens included in denominator. **Already implemented** in `expectancy.dollar_expectancy`.

---

## I. R Expectancy

```
R Expectancy = sum(R) / count(R-qualified trades)
```

Same as Average R over R-qualified set. **Already implemented** as `r_statistics.expectancy` — ensure Graphs use same function.

---

## J. Profit Factor

Dollar PF (all closed trades in cohort):

```
Gross Profit = sum(positive P&L)
Gross Loss   = abs(sum(negative P&L))
PF = Gross Profit / Gross Loss
```

Special cases: `NO_TRADES`, `NO_LOSSES` (∞ display, null serialize), `NO_WINS` → 0. **Already implemented.**

---

## K. Payoff Ratio

```
Dollar Payoff = avg(winner P&L) / abs(avg(loser P&L))
```

Null if no winners or losers. **Already implemented.**

Add **R Payoff Ratio** (new):

```
avg(winning R) / abs(avg(losing R))   — R-qualified only
```

---

## L. Drawdown

**Realized equity curve** (chronological by `exit_time_utc`, tie-break `trade.id`):

```
equity = period_baseline_equity + cumulative realized P&L (cohort trades only for DD sequence)
running_peak = max(prev_peak, equity)
drawdown_$ = equity − running_peak   (≤ 0)
drawdown_% = drawdown_$ / running_peak × 100
```

**Filtered period baseline** (already in `equity_baseline`):

```
baseline = sum(starting_equity of selected ACCOUNT(S)) + all prior realized P&L of those accounts
          (exit_time < period start; NOT filtered by direction/ticker/strategy/source/setup)
```

**SUPERSEDED:** older wording that applied source/direction/ticker filters to the pre-period equity baseline. Account selection is the capital identity. Analytical cohort filters must not rewrite historical account equity.

**Cohort semantics:** Drawdown **sequence** may include only trades matching current analysis filters; label *Selected Cohort Drawdown*. This is not true account drawdown unless the cohort is unfiltered.

**Without starting equity:** cumulative P&L drawdown $ only; no %.

**Duration:** v1 uses calendar-date difference. Label **Calendar Days Underwater**. Do not call this Trading Days.

**Tests:** Fixtures #82, #94 (multi-account), filtered baseline.

---

## M. R Drawdown

Build cumulative R series (R-qualified trades only, chronological):

```
cumulative_R += R_i
peak_R = max(prev_peak_R, cumulative_R)
r_drawdown = cumulative_R − peak_R
```

Metrics: Max R Drawdown, Current R Drawdown. Independent of account equity.

**Test:** Fixture #83 → −2.5R max.

New module: `app/services/analytics/r_drawdown.py` or extend `drawdown.py`.

---

## N. Equity-at-Entry Calculation

Per trade, per account:

```
equity_before_entry =
    account.starting_equity
  + sum(effective_realized_pnl for closed trades
        where account matches
        and exit_time_utc < this_trade.entry_time_utc)
```

**No lookahead:** Open or same-time-unrealized P&L excluded.

Implementation: sort closed trades by exit time; prefix-sum P&L per account; lookup at entry. Batch in one pass when annotating trades for reports (O(n log n)).

**Test:** Fixture #84 — Trade B entry while Trade A open → equity still $10,000.

---

## O. Risk % Equity

```
risk_pct_equity = actual_initial_risk / equity_before_entry × 100
```

Only when both values known and `equity_before_entry > 0`. Store on `trade_risk.risk_pct_equity_at_entry` (cached).

**Test:** Fixture #85 — $100 risk on $10,000 → 1%.

---

## P. Streak Calculations

Chronological by exit time within filtered cohort. **BREAKEVEN breaks both streaks.** **Already implemented** in `streaks.py`.

Outputs: longest win, longest loss, current streak (type + count). Label cohort when filters active.

---

## Q. Graph Integration

### Q1. Extend metric registry (`registry.py` METRICS)

Add:

| key | label | Notes |
|-----|-------|-------|
| `average_r` | Average R | R-qualified only; null if none |
| `total_r` | Total R | Sum R in bucket |
| `r_profit_factor` | R Profit Factor | Optional; null if no losses |
| `r_coverage_pct` | R Coverage | For tooltips primarily |

Extend `_bucket_metrics` in `aggregation.py`:

- Track `r_qualified_count`, `r_values[]`
- Compute R metrics with same Decimal rules
- Every bucket tooltip: `Trades: N | R-qualified: M | R Coverage: X%`

### Q2. Activate RISK section reports (`config.py` + `registry.py`)

| Report key | Dimension | Buckets |
|------------|-----------|---------|
| `r_outcome` | R outcome bands | Central `R_BUCKETS` from `r_distribution.py` |
| `initial_risk_dollar` | actual_initial_risk | &lt;$25, $25–50, $50–100, $100–200, $200–500, $500+ |
| `risk_pct_equity` | risk_pct_equity | &lt;0.25%, 0.25–0.50%, … 2.00%+ |
| `stop_distance_pct` | stop distance | &lt;1%, 1–2%, … 10%+ |
| `cumulative_r` | time sequence | Line chart (reuse OUTCOMES pattern) |
| `r_drawdown` | time sequence | Line chart |

Set `("RISK", "Risk & R", True, None)` when risk module active.

### Q3. Feature keys (extend `features.py` or `risk_features.py`)

Derive per trade:

- `initial_risk_bucket`
- `risk_pct_equity_bucket`
- `stop_distance_pct` (valid stop only)
- `r_outcome_bucket` (from `classify_r`)

Join `trade_risk` in report annotation pass (eager load, avoid N+1).

### Q4. Dashboard / charts

- Equity chart toggle: P&L | Equity | R (partial exists)
- Drawdown chart toggle: $ | % | R
- Compact Risk section on Dashboard (Avg R, R Expectancy, PF, Max DD, R Coverage)

### Q5. Strategy + Instrument dimensions

Once Step 5 STRATEGY reports exist, R metrics apply automatically via extended `_bucket_metrics`. Same for Step 4 instrument/market dimensions — **no duplicate R-by-X reports**.

---

## R. Missing-Risk Behavior

| Analytics | Includes missing-risk trades? |
|-----------|----------------------------|
| Dollar P&L, Win Rate, Dollar Expectancy, PF, Payoff | Yes |
| Dollar drawdown (P&L mode) | Yes |
| Average R, R Expectancy, Total R, R PF, R distribution, Cumulative R, R DD | **No** |
| Risk % equity, stop distance graphs | **No** |

`r_multiple = NULL` on trade. Trades table shows `—` for R columns.

Filter: `has_risk=all|yes|no` (exists); add optional `r_min`, `r_max`.

---

## S. Data-Quality Flags

### `risk_quality_status` enum

`OK | MISSING_STOP | INVALID_STOP | MISSING_ENTRY | MISSING_QUANTITY | AMBIGUOUS_SCALE_IN | MANUAL_OVERRIDE | SIGNAL_MISMATCH`

### `r_pnl_basis`

`NET | GROSS`

### Coverage breakdown API

Group missing-risk closed trades by primary reason for `/api/risk/coverage`:

- No Pine Signal
- Missing Stop
- Invalid Stop
- Missing Quantity
- Manual Review
- Other

Separate **Strategy Coverage** (signal linked) from **R Coverage** (valid R).

### Warnings (aggregate)

- `"N R value(s) use gross P&L because fee data is unavailable."`
- `"Percentage drawdown requires starting equity."`

---

## T. Tests

### Backend (new / extend `tests/test_step_7_risk.py`)

| # | Topic | Fixture ref |
|---|-------|---------------|
| 1 | LONG R winner | #71 |
| 2 | SHORT R winner | #72 |
| 3 | Losing R | #73 |
| 4 | Invalid LONG/SHORT stops | #74 |
| 5 | Pine stop → actual risk | #75 |
| 6 | Planned vs actual preserved | #76 |
| 7 | Scale-in Decimal risk | #77 |
| 8 | Manual explicit override | #78 |
| 9 | Expectancy / median / avg win/loss R | #79 |
| 10 | Dollar PF + expectancy | #80 |
| 11 | R PF | #81 |
| 12 | Dollar drawdown $ and % | #82 |
| 13 | R drawdown | #83 |
| 14 | Equity-at-entry no lookahead | #84 |
| 15 | Risk % equity | #85 |
| 16 | Streaks | #86 |
| 17 | Missing-risk inclusion/exclusion | #87 |
| 18 | Gross P&L R basis | #88 |
| 19 | Graph Average R by weekday | #89 |
| 20 | Average R by gap bucket | #90 |
| 21 | Average R by setup quality | #91 |
| 22 | SHORT-only filter | #92 |
| 23 | R coverage % filtered cohort | #93 |
| 24 | Loss beyond 1R (threshold −1.05) | #94 |
| 25 | Multi-account % DD | #95 |
| 26 | 10k-trade performance smoke | #98 |

Retain all Step 1–5 regression tests.

### Frontend (`tests/` or Vitest)

- Risk section placeholder vs active
- Trade Detail planned/actual panel, invalid stop errors
- R formatting, missing R, coverage display
- Metric selectors: Average R, Total R, R PF
- Charts: cumulative R, drawdown toggles
- No Recharts internal assertions

---

## U. Known Limitations

1. **Single initial stop for scale-ins** — cannot detect stop moves mid-scale without manual notes.
2. **Pine planned fill vs actual slippage** — planned risk is informational; R uses actual entry/qty.
3. **Gross P&L R** — slightly biased when fees missing; flagged, not blocked.
4. **Filtered cohort drawdown** — sequence is subset; not identical to account-level DD unless unfiltered.
5. **Trading-day DD duration** — uses calendar day diff on NY exit dates; not exchange holiday calendar v1.
6. **Multi-account combined equity %** — requires all accounts have `starting_equity`.
7. **Step 5 dependency** — Pine auto-population requires signal tables + link pipeline; manual risk works without it.
8. **Step 8 deferred** — no MFE/MAE/exit efficiency.
9. **Research Lab deferred** — no SQN, Sharpe, Monte Carlo.
10. **Step 6 skipped** — source comparison advanced panel may remain but is not a product focus; no new MANUAL-vs-AUTO analytics.

---

## Data Model — `trade_risk`

```sql
CREATE TABLE trade_risk (
    id INTEGER PRIMARY KEY,
    trade_id INTEGER NOT NULL UNIQUE REFERENCES trades(id) ON DELETE CASCADE,

    -- Actual (authoritative for R)
    initial_stop_price NUMERIC(18,6),
    actual_risk_per_share NUMERIC(18,6),
    actual_initial_risk_amount NUMERIC(18,6),
    explicit_initial_risk_amount NUMERIC(18,6),  -- if user override
    stop_derived_risk_amount NUMERIC(18,6),      -- preserved when explicit wins

    -- Planned (Pine / signal)
    planned_entry_price NUMERIC(18,6),
    planned_stop_price NUMERIC(18,6),
    planned_risk_per_share NUMERIC(18,6),
    planned_risk_amount NUMERIC(18,6),
    allowed_risk NUMERIC(18,6),
    suggested_shares NUMERIC(18,6),

    -- Derived analytics cache
    stop_distance_pct NUMERIC(18,8),
    risk_pct_equity_at_entry NUMERIC(18,8),
    r_multiple NUMERIC(18,8),
    r_pnl_basis TEXT,  -- NET | GROSS

    -- Provenance
    risk_source TEXT,      -- PINE_SIGNAL | MANUAL | IMPORTED | CALCULATED | UNKNOWN
    stop_source TEXT,
    risk_quality_status TEXT,
    risk_notes TEXT,
    calculation_version TEXT DEFAULT '1',
    manual_override BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ
);

CREATE INDEX ix_trade_risk_trade_id ON trade_risk(trade_id);
CREATE INDEX ix_trade_risk_quality ON trade_risk(risk_quality_status);
```

Optional `risk_audit_log(trade_id, field, old_value, new_value, source, created_at)`.

Migration via `app/db/migrate.py`; backfill from existing `trades` risk columns.

---

## RiskService (new)

`app/services/risk/service.py`:

```python
def recalculate_trade_risk(db, trade, *, force=False) -> TradeRisk
def recalculate_for_signal_link(db, signal_id) -> int
def batch_equity_at_entry(trades, accounts) -> dict[int, Decimal]
def coverage_report(db, filters) -> RiskCoverageResponse
def loss_beyond_initial_risk(r_values, threshold=Decimal("-1.05")) -> dict
```

Called from:

- `PATCH /api/trades/{id}/risk`
- Signal link confirm/unlink (Step 5 hook)
- Optional admin `POST /api/risk/recalculate`

---

## API Additions

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/api/risk/coverage` | Coverage stats + reason breakdown + source mix |
| GET | `/api/risk/missing-trades` | Paginated closed trades missing R |
| POST | `/api/risk/recalculate` | Batch recompute (optional, dev/admin) |
| PATCH | `/api/trades/{id}/risk` | Extend response with planned fields, quality, basis |

Extend `GET /api/dashboard` advanced block:

- `r_profit_factor`, `r_payoff_ratio`
- `max_r_drawdown`, `current_r_drawdown`
- `loss_beyond_initial_risk` count/_pct
- `large_winners` (2R+, 3R+)
- `best_r_trade_id`, `worst_r_trade_id`

Extend `GET /api/reports` bucket schema with R metric fields.

---

## Frontend Work

| Component | Change |
|-----------|--------|
| `TradeDetailPage` | Full Risk/R panel: planned vs actual, risk % equity, P&L basis, edit |
| `TradesPage` | Columns: Initial Risk, Risk %, R; filters |
| `DashboardPage` | Compact Risk summary cards; chart mode toggles |
| `DrawdownChart` / equity chart | $ / % / R modes |
| `GraphsPage` / `ReportCard` | R metrics in selector; R coverage tooltip |
| `RiskCoveragePage` (`/risk`) | Coverage dashboard + link to missing trades |
| `MissingRiskModal` | Wire to coverage API |

Remove or de-emphasize `SourceComparison` advanced block per Step 6 (keep basic source stats).

---

## Documentation Deliverables (implementation phase)

Create/update:

- `docs/RISK_MODEL.md` — table, enums, hierarchy
- `docs/R_MULTIPLE.md` — formulas, qualification, gross fallback
- `docs/EXPECTANCY_AND_PROFIT_FACTOR.md` — merge/extend EXPECTANCY.md
- `docs/DRAWDOWN.md` — extend with R DD + cohort semantics
- `docs/REPORT_DIMENSIONS.md` — RISK section + new metrics
- `docs/GRAPHS_AND_REPORTS.md` — R metric selector
- `docs/DATABASE_SCHEMA.md` — trade_risk
- `docs/ARCHITECTURE.md` — RiskService
- `README.md` — Step 7 summary

---

## Implementation Phases

### Phase 1 — Data model + RiskService core

- Migration `trade_risk` + backfill
- Refactor `risk.py` → use TradeRisk; planned fields
- Pine hook stub (populate when signal linked)
- Unit tests fixtures #71–#78

### Phase 2 — Portfolio analytics

- R PF, R payoff, R drawdown, loss beyond 1R
- Equity-at-entry batch + risk % equity
- Extend `build_advanced_analytics` + dashboard API
- Tests #79–#86, #94–#95

### Phase 3 — Graphs integration

- Extend `_bucket_metrics` + METRICS registry
- RISK section reports + bucket constants
- R coverage per bucket tooltips
- Tests #89–#93

### Phase 4 — Frontend

- Trade Detail, Trades table, Dashboard cards, charts, `/risk` page
- Graph metric selectors
- Frontend tests

### Phase 5 — Docs + validation

- All doc files
- 10k performance smoke
- Manual validation checklist (spec §104)
- Real-data audit (5 trades, spec §105)
- Completion report (spec §106)

---

## Definition of Done

Matches spec §103 (53 items): planned ≠ actual, Pine auto-populate, manual override, LONG/SHORT/scale-in/invalid stop, R NULL when missing, coverage visible, all expectancy/PF/payoff/DD metrics, equity-at-entry no lookahead, R graphs active, **Avg R / Total R / R PF on all existing report dimensions**, filters respected, Step 1–5 tests pass, Step 7 tests pass, production build passes.

**Explicitly NOT in Step 7:** MFE/MAE (Step 8), SQN/Sharpe/Monte Carlo (Research Lab), permanent MANUAL-vs-AUTO comparison (Step 6 skipped).

---

## Open Questions — resolved 2026-09-02

1. **`trade_risk` vs widen `trades`** — 1:1 `trade_risk` + denormalized Trade cache. RiskService is the authoritative writer.
2. **Step 5 backend** — signal tables, matcher, and Pine→risk hook are implemented.
3. **`risk_audit_log`** — implemented (append-only: trade_id, field, old, new, source, created_at).
4. **Source comparison panel** — de-emphasized; Step 6 MANUAL-vs-AUTO pairing remains skipped. AUTO is a normal `source_type`.
5. **Loss beyond 1R** — default −1.05 via `LTA_LOSS_BEYOND_R_THRESHOLD`. Label is Loss Beyond Initial Risk, not a rule violation.

---

*End of Step 7 Plan — awaiting review before implementation.*
