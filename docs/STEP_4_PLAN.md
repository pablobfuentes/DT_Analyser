# Step 4 Plan — Instrument + Market Data Enrichment

**Status:** Implemented (Step 4 complete pending manual validation with live Alpaca data).

**Goal:** Populate the Step 3 Graphs engine with historical market context for **Instrument** and **Market** dimensions. No redesign of the report/filter/card architecture.

---

## A. Market-Data Architecture

```
Import (Step 1) ──► trades (unchanged)
                         │
                         ▼
              POST /api/market-data/enrich
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
   market_data/    enrichment/     reports/features
   providers        service           (join at annotate)
   cache            calculator
         │               │               │
         ▼               ▼               ▼
   market_daily_bars   instrument_day_features   trade_market_features
                       benchmark_day_features    (trade-specific)
                         │
                         ▼
              GET /api/reports (Step 3 engine, extended features)
```

**Layers:**

| Layer | Path | Responsibility |
|-------|------|----------------|
| Provider abstraction | `app/market_data/` | Fetch normalized daily bars; provenance metadata |
| Local cache | `market_daily_bars` table + `cache.py` | Persist bars; cache-first before network |
| Feature engine | `app/services/market_enrichment/` | TR, ATR, RVOL, SMA, day type, gaps; quality states |
| Enrichment orchestration | `enrichment/service.py` | Batch by symbol/range; job tracking; post-import hook |
| Report integration | Extend `reports/features.py` | Join `trade_market_features` into `AnnotatedTrade.features` |
| Graphs UI | Extend existing `ReportCard`, `GraphsPage` | Coverage badges, timing badges, quality warnings |

**Principle:** Raw daily bars are the source of truth. Derived features are recalculatable from cache without refetching.

---

## B. Provider Abstraction

**Module:** `app/market_data/base.py`

```python
class MarketDataProvider(Protocol):
    provider_name: str          # ALPACA | MASSIVE | FAKE
    feed_name: str              # sip | iex | polygon_agg
    is_consolidated: bool
    supports_splits: bool
    supports_batch_symbols: bool

    def get_daily_bars(
        self,
        symbols: list[str],
        start_date: date,
        end_date: date,
        adjustment_mode: str = "raw",
    ) -> list[DailyBar]: ...

    def get_splits(self, symbol: str, start: date, end: date) -> list[SplitEvent]: ...
        # optional; return [] if unsupported
```

**Normalized model:** `app/market_data/models.py`

```python
@dataclass
class DailyBar:
    symbol: str
    trading_date: date          # NY session date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    vwap: Decimal | None
    trade_count: int | None
    provider: str
    feed: str
    adjustment_mode: str
    is_consolidated: bool
    fetched_at: datetime
    raw_payload_json: str | None
```

**Registry:** `app/market_data/registry.py` — resolves active provider from settings. Returns `NoneProvider` (no-op) when unconfigured.

**Test provider:** `app/market_data/fake.py` — deterministic fixture series; used by all automated tests.

---

## C. Provider Selection

**Settings** (extend `app/config.py`, prefix `LTA_`):

| Variable | Purpose | Default |
|----------|---------|---------|
| `LTA_MARKET_DATA_PROVIDER` | `alpaca` \| `massive` \| `none` | `none` |
| `LTA_ALPACA_API_KEY_ID` | Alpaca key | — |
| `LTA_ALPACA_API_SECRET_KEY` | Alpaca secret | — |
| `LTA_ALPACA_DATA_FEED` | `sip` \| `iex` | `iex` |
| `LTA_MASSIVE_API_KEY` | Massive/Polygon key | — |
| `LTA_MARKET_BENCHMARK` | Benchmark symbol | `SPY` |
| `LTA_MARKET_ADJUSTMENT_MODE` | `raw` \| `split` | `raw` |
| `LTA_MARKET_LOOKBACK_CALENDAR_DAYS` | Default lookback | `120` |

**Selection logic:**

1. If `MARKET_DATA_PROVIDER=none` or required keys missing → `NoneProvider`; app starts normally.
2. If `alpaca` and keys present → `AlpacaProvider`.
3. If `massive` and key present → `MassiveProvider`.
4. Only one active provider at a time (no dual-fetch in v1).

**Feed provenance:** Every bar stores `provider`, `feed`, `is_consolidated`. IEX → `is_consolidated=false`, volume features → `PARTIAL_FEED`.

---

## D. Data Provenance

Every persisted bar and derived feature records:

| Field | Example |
|-------|---------|
| `provider` | `ALPACA` |
| `feed` | `SIP` |
| `adjustment_mode` | `RAW` |
| `fetched_at` | ISO timestamp |
| `calculation_version` | `instrument-v1` |
| `feature_version` | `instrument-v1` |

Stored on:

- `market_daily_bars` (fetch provenance)
- `instrument_day_features` (calc provenance)
- `trade_market_features` (link + calc version)

**Unique bar key:** `(symbol, trading_date, provider, feed, adjustment_mode)`

Changing provider/feed creates parallel rows; old data retained for audit/recalc comparison.

---

## E. Daily-Bar Storage

**Table:** `market_daily_bars`

| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| symbol | VARCHAR | Uppercase; trade ticker preserved separately |
| trading_date | DATE | NY session date |
| open, high, low, close | NUMERIC(18,6) | Decimal |
| volume | INTEGER | |
| vwap | NUMERIC nullable | |
| trade_count | INTEGER nullable | |
| provider | VARCHAR | |
| feed | VARCHAR | |
| adjustment_mode | VARCHAR | |
| is_consolidated | BOOLEAN | |
| raw_payload_json | TEXT nullable | |
| fetched_at | DATETIME | |
| created_at, updated_at | DATETIME | |

**Index:** `(symbol, trading_date)`, unique `(symbol, trading_date, provider, feed, adjustment_mode)`

**SQLAlchemy model:** `app/db/models/market_daily_bar.py`  
**Migration:** `create_all` + `_ensure_market_tables()` in `migrate.py`

---

## F. Instrument Feature Schema

**Table:** `instrument_day_features`

One row per `(symbol, trading_date)` — shared by all trades on that symbol/date.

| Column | Type | Timing | Notes |
|--------|------|--------|-------|
| id | PK | | |
| symbol | VARCHAR | | |
| trading_date | DATE | | NY entry date |
| prior_close | NUMERIC | PRE_ENTRY | Previous session close |
| day_open, day_high, day_low, day_close | NUMERIC | mixed | |
| day_volume | INTEGER | END_OF_DAY | |
| opening_gap_pct | NUMERIC | PRE_ENTRY | See formulas |
| daily_movement_pct | NUMERIC | END_OF_DAY | |
| rvol_50_pct | NUMERIC nullable | END_OF_DAY | NULL if insufficient history |
| rvol_50_multiple | NUMERIC nullable | END_OF_DAY | |
| prior_day_rvol_50_pct | NUMERIC nullable | PRE_ENTRY | |
| prior_day_rvol_50_multiple | NUMERIC nullable | PRE_ENTRY | |
| true_range | NUMERIC nullable | END_OF_DAY | |
| atr14_prior | NUMERIC nullable | PRE_ENTRY | Through prior completed session |
| tr_atr_pct | NUMERIC nullable | END_OF_DAY | TR / atr14_prior × 100 |
| day_type | VARCHAR nullable | END_OF_DAY | TREND_UP, TREND_DOWN, INSIDE_RANGE, OUTSIDE_RANGE |
| sma20_prior | NUMERIC nullable | PRE_ENTRY | |
| sma50_prior | NUMERIC nullable | PRE_ENTRY | |
| quality_status | VARCHAR | | OK, PARTIAL_FEED, INSUFFICIENT_HISTORY, etc. |
| completeness_status | VARCHAR | | COMPLETE, PRE_ENTRY_ONLY, PENDING_EOD, PARTIAL, FAILED |
| provider, feed | VARCHAR | | |
| calculation_version | VARCHAR | | `instrument-v1` |
| calculated_at | DATETIME | | |

**Unique:** `(symbol, trading_date, calculation_version)` — allows future recalc with new version.

---

## G. Market/Benchmark Feature Schema

**Table:** `benchmark_day_features` (SPY by default; benchmark symbol in config)

Same shape as instrument day features for benchmark-relevant fields:

- `market_movement_pct` (END_OF_DAY)
- `market_opening_gap_pct` (PRE_ENTRY)
- `market_day_type` (END_OF_DAY)
- Optional: `market_atr14_prior`, `market_tr_atr_pct` (computed but not required for Step 4 graphs)

**Key:** `(benchmark_symbol, trading_date, calculation_version)`

Trades on the same NY date share one benchmark row (no per-trade SPY duplication).

---

## H. Trade Market Features

**Table:** `trade_market_features`

| Column | Type | Notes |
|--------|------|-------|
| id | PK | |
| trade_id | FK unique | One row per trade |
| instrument_feature_id | FK nullable | → instrument_day_features |
| benchmark_feature_id | FK nullable | → benchmark_day_features |
| entry_vs_atr_pct | NUMERIC nullable | PRE_ENTRY |
| entry_vs_sma20_pct | NUMERIC nullable | PRE_ENTRY |
| entry_vs_sma50_pct | NUMERIC nullable | PRE_ENTRY |
| enrichment_status | VARCHAR | COMPLETE, PARTIAL, FAILED, PENDING_EOD |
| missing_reason | VARCHAR nullable | MISSING_BAR, INSUFFICIENT_HISTORY, etc. |
| calculation_version | VARCHAR | |
| calculated_at | DATETIME | |

**Trade-specific** because `avg_entry_price` differs per trade on same symbol/date.

**Do not modify** `Trade` model for market fields (except optional future index); join at annotate time.

---

## I. Calculations / Formulas

All monetary math uses `Decimal`. Percentages stored as numeric (e.g. `25.0` = 25%).

### Opening Gap % (PRE_ENTRY)

```
opening_gap_pct = (day_open - prior_close) / prior_close × 100
```

Regular-session daily open from provider bar. Not premarket.

### Daily Movement % (END_OF_DAY)

```
daily_movement_pct = (day_close - prior_close) / prior_close × 100
```

### RVOL 50 % (END_OF_DAY) — `instrument_rvol50_eod`

```
rvol_50_pct = day_volume / avg(volume of previous 50 completed sessions) × 100
rvol_50_multiple = rvol_50_pct / 100
```

Current day volume **excluded** from baseline. Requires ≥50 prior sessions.

### Prior-Day RVOL (PRE_ENTRY)

For entry date D, prior session P:

```
prior_day_rvol_50_pct = volume(P) / avg(volume of 50 sessions before P) × 100
```

### True Range (END_OF_DAY)

```
TR = max(high - low, |high - prior_close|, |low - prior_close|)
```

### ATR(14) prior (PRE_ENTRY) — `atr14_prior`

Wilder smoothing:

- First ATR = simple mean of first 14 TR values (after enough history)
- ATR_t = (ATR_{t-1} × 13 + TR_t) / 14

**For analysis:** `atr14_prior` = ATR through the session **before** entry date (known pre-open).

Optional separate `atr14_eod` if ever needed; not mixed into primary graphs.

### Entry vs ATR % (PRE_ENTRY)

```
entry_vs_atr_pct = (avg_entry_price - prior_close) / atr14_prior × 100
```

Signed. NULL if `atr14_prior` unavailable.

### Relative Volatility TR/ATR % (END_OF_DAY)

```
tr_atr_pct = true_range / atr14_prior × 100
```

### Day Type (END_OF_DAY)

Precedence: TREND_UP → TREND_DOWN → INSIDE_RANGE → OUTSIDE_RANGE

Definitions use current OHLC vs **previous session** high/low:

- **TREND_UP:** close > prev_high AND open in bottom 15% of day's range AND close in top 15%
- **TREND_DOWN:** close < prev_low AND open in top 15% AND close in bottom 15%
- **INSIDE_RANGE:** high ≤ prev_high AND low ≥ prev_low
- **OUTSIDE_RANGE:** else (partially outside prior range)

Zero-range day: safe fallback → INSIDE_RANGE or NULL with quality flag.

### SMA (PRE_ENTRY)

```
sma20_prior = mean(close of 20 completed sessions before entry date)
sma50_prior = mean(close of 50 completed sessions before entry date)
```

### Entry vs SMA % (PRE_ENTRY)

```
entry_vs_sma20_pct = (avg_entry_price - sma20_prior) / sma20_prior × 100
entry_vs_sma50_pct = (avg_entry_price - sma50_prior) / sma50_prior × 100
```

### SPY / Benchmark (same formulas on benchmark bars)

- `market_opening_gap_pct` — PRE_ENTRY
- `market_movement_pct` — END_OF_DAY
- `market_day_type` — END_OF_DAY

---

## J. Split / Corporate-Action Handling

1. Persist `adjustment_mode` on every bar (`raw` default).
2. If provider returns split events, store in `corporate_actions` table (optional v1) or detect via split metadata.
3. Before computing rolling indicators (ATR, SMA, entry % ATR), verify price basis consistency between trade entry price and bar series.
4. On ambiguity → set `quality_status = CORPORATE_ACTION_AMBIGUITY`; leave affected metrics NULL.
5. Gap % and daily movement % use same-day bar + prior close from **consistent** adjustment mode only.
6. **Never** silently mix split-adjusted bars with unadjusted trade execution prices.

---

## K. Enrichment Workflow

```
1. Trade import completes (Step 1 — unchanged, never blocked)
2. Enrichment service scans closed trades for missing trade_market_features
3. User may trigger manually: [Enrich Missing Data] or CLI
4. For each unique (symbol, date_range):
   a. Cache lookup for market_daily_bars
   b. Fetch missing ranges from provider (batched symbols)
   c. Fetch benchmark (SPY) once for union date range
   d. Calculate instrument_day_features + benchmark_day_features
   e. Calculate trade_market_features per trade
   f. Record job in market_enrichment_jobs
5. Graphs reads enriched features at report time (no network)
```

**Triggers:**

- Automatic: post-import **detection only** (flag missing; optional background enrich if configured — v1: manual button preferred per spec)
- Manual: `POST /api/market-data/enrich` scope=`missing`
- CLI: `python -m app.cli.enrich_market_data --missing`

**Recalculate:** `POST /api/market-data/recalculate` — uses cached bars only, no provider calls.

**Refresh:** `POST /api/market-data/refresh` — re-fetch from provider for selected scope.

---

## L. Missing-Data Behavior

| Situation | Trade record | Feature values | Graphs |
|-----------|--------------|----------------|--------|
| No provider configured | Valid | NULL | MARKET placeholder; instrument market dims unavailable |
| Missing bar | Valid | NULL + reason | Coverage % shown; bucket excluded |
| Insufficient history (<50 sessions) | Valid | RVOL/SMA50 NULL | Quality INSUFFICIENT_HISTORY |
| Partial feed (IEX) | Valid | Volume/RVOL with PARTIAL_FEED | Excluded from default volume/RVOL graphs |
| Corporate action ambiguity | Valid | ATR/SMA distance NULL | Quality warning |
| Delisted / unknown symbol | Valid | NULL + PROVIDER_MISSING_SYMBOL | Counted in missing |
| Same-day open market | Valid | EOD fields PENDING_EOD | PRE_ENTRY may still work |

**Trades are never deleted or invalidated** by enrichment failure.

---

## M. Step 3 Dimension Integration

### Activate MARKET section

In `config.py` `SECTIONS`: flip `MARKET` to `available=True` when provider configured **and** at least one benchmark feature exists (or always show section with coverage message when configured).

Remove from `FUTURE_SECTIONS` path once active.

### Add INSTRUMENT market reports (same INSTRUMENT section)

New entries in `REPORT_DEFINITIONS`:

| Report key | Feature key | Timing | Default quality filter |
|------------|-------------|--------|------------------------|
| instrument_gap | opening_gap_bucket | PRE_ENTRY | OK only |
| instrument_volume | day_volume_bucket | END_OF_DAY | OK, exclude PARTIAL_FEED |
| instrument_rvol50 | rvol50_bucket | END_OF_DAY | OK, exclude PARTIAL_FEED |
| instrument_prior_rvol | prior_rvol_bucket | PRE_ENTRY | OK, exclude PARTIAL_FEED |
| instrument_movement | movement_bucket | END_OF_DAY | OK only |
| instrument_atr14 | atr14_bucket | PRE_ENTRY | OK, not CORPORATE_ACTION_AMBIGUITY |
| entry_vs_atr | entry_atr_bucket | PRE_ENTRY | same |
| instrument_rel_vol | tr_atr_bucket | END_OF_DAY | OK only |
| instrument_day_type | day_type | END_OF_DAY | OK only |
| entry_vs_sma20 | entry_sma20_bucket | PRE_ENTRY | OK only |
| entry_vs_sma50 | entry_sma50_bucket | PRE_ENTRY | OK only |

### Add MARKET section reports

| Report key | Feature key | Timing |
|------------|-------------|--------|
| market_movement | market_movement_bucket | END_OF_DAY |
| market_gap | market_gap_bucket | PRE_ENTRY |
| market_day_type | market_day_type | END_OF_DAY |

### Bucket definitions (centralized in `reports/config.py`)

**Gap %:** `<0`, `0–2`, `2–5`, `5–10`, `10–20`, `20–50`, `50–100`, `100%+`

**Volume:** `<500K`, `500K–1M`, `1M–2M`, `2M–5M`, `5M–10M`, `10M–25M`, `25M–50M`, `50M+`

**RVOL multiple:** `<1x`, `1–2x`, `2–5x`, `5–10x`, `10–20x`, `20x+` (prior-day: `<1x` … `10x+`)

**Movement:** `<-20%`, `-20 to -10`, …, `+50%+`

**ATR $:** `<$0.10`, `$0.10–0.25`, …, `$2+`

**Entry % ATR:** `<-100%`, `-100 to -50`, …, `200%+`

**TR/ATR:** `<50%`, `50–75%`, …, `300%+`

**SMA distance:** same pattern as movement buckets

**Market movement:** `<-2%`, `-2 to -1`, …, `+2%+`

**Market gap:** `<-1%`, `-1 to -0.5`, …, `+1%+`

**Day type labels:** Trend Up, Trend Down, Inside Range, Outside Range

### Feature join in `_annotate_trades`

After `compute_base_features` + behavior:

```python
market_feats = load_trade_market_features(db, trade_ids)
for at in annotated:
    at.features.update(market_feats.get(at.trade.id, {}))
```

Feature keys match filter mapping in `filters.py`.

### Dimension registry metadata (extend `REPORT_DEFINITIONS`)

Each market report adds:

```python
{
    "availability_timing": "PRE_ENTRY" | "END_OF_DAY",
    "description": "...",
    "quality_requirement": "FULL_FEED",  # optional
    "requires_enrichment": True,
}
```

### Exploration filter params (URL-stable IDs)

| Param | Feature |
|-------|---------|
| `gap_bucket` | opening_gap_bucket |
| `volume_bucket` | day_volume_bucket |
| `rvol_bucket` | rvol50_bucket |
| `prior_rvol_bucket` | prior_rvol_bucket |
| `movement_bucket` | movement_bucket |
| `atr_bucket` | atr14_bucket |
| `entry_atr_bucket` | entry_atr_bucket |
| `tr_atr_bucket` | tr_atr_bucket |
| `day_type` | day_type |
| `entry_sma20_bucket` | entry_sma20_bucket |
| `entry_sma50_bucket` | entry_sma50_bucket |
| `market_movement_bucket` | market_movement_bucket |
| `market_gap_bucket` | market_gap_bucket |
| `market_day_type` | market_day_type |

Extend `EXPLORATION_KEYS` in backend `filters.py` and frontend `types/reports.ts`.

### Report response extensions

Each report in API response adds:

```json
{
  "coverage": {
    "matching_trades": 142,
    "data_available": 131,
    "coverage_pct": "92.3",
    "excluded": 11,
    "exclusion_reasons": {"insufficient_history": 7, "partial_feed": 3, "missing_bar": 1}
  },
  "availability_timing": "END_OF_DAY",
  "description": "..."
}
```

### Frontend ReportCard extensions

- Timing badge: `PRE-ENTRY` / `END OF DAY`
- Coverage line under title
- Partial-feed warning icon when applicable
- No Recharts redesign

### Quality global control (Graphs toolbar)

```
Market Data Quality: [Verified / Full ▼]  Include Partial | All
```

Default: Full-quality only for volume/RVOL dimensions; price-only reports unaffected.

---

## N. Caching / Local Persistence

1. **Cache-first:** `cache.py` queries `market_daily_bars` before any HTTP call.
2. **Range merge:** Compute union of required `(symbol, start, end)` including 120 calendar day lookback; fetch only gaps.
3. **Immutability:** Completed historical bars not refetched unless explicit Refresh.
4. **Today's bar:** If session incomplete, EOD features stay `PENDING_EOD`; re-enrich after close.
5. **Second enrichment run:** Provider call count = 0 for cached ranges (verified by test).

---

## O. API-Key / Security Design

- Secrets only in backend `.env` / environment (`LTA_ALPACA_*`, `LTA_MASSIVE_*`).
- Never returned to frontend.
- `GET /api/market-data/status` returns:

```json
{
  "configured": true,
  "provider": "ALPACA",
  "feed": "SIP",
  "quality_level": "CONSOLIDATED",
  "benchmark": "SPY",
  "last_enrichment_at": "...",
  "coverage_pct": 94.2
}
```

- No generic provider proxy endpoint.
- Logs never include secrets.

**Frontend route:** `/market-data` — settings/status page (read-only config display).

---

## P. Retry / Rate-Limit Design

In `app/market_data/http_client.py` or per-provider:

- Batch symbols per request (provider limits respected)
- On HTTP 429: exponential backoff (1s, 2s, 4s, 8s, max 5 retries)
- Max retry cap; then mark job `FAILED` with `error_message`
- Log: provider, symbol, date range, attempt, cache hit/miss
- No infinite loops

---

## Q. Tests

### Backend (`tests/test_market_*.py`)

| Area | Tests |
|------|-------|
| Formulas | Gap 25%, movement 20%, RVOL 500%, prior RVOL 300%, TR=3, ATR Wilder, entry % ATR, TR/ATR 200% |
| Day type | TREND_UP, TREND_DOWN, INSIDE, OUTSIDE, zero-range, precedence |
| SMA | SMA20/50, entry vs SMA % |
| Benchmark | SPY gap/movement/day type shared per date |
| Partial feed | IEX → PARTIAL_FEED; excluded from default RVOL graphs |
| Insufficient history | 20 sessions → RVOL50 NULL, SMA50 NULL |
| Corporate action | Split ambiguity → NULL + quality flag |
| Cache | Second enrich → 0 provider calls |
| Batching | 10 same symbol/date trades → 1 symbol fetch |
| Filter engine | All new exploration params + combinations |
| Discovery | Gap + RVOL + market gap → all reports narrow |
| Provider | FakeMarketDataProvider only in CI |
| Performance | 10k trades enrichment scales by unique symbol-dates |
| Regression | Step 1–3 test files unchanged and passing |

### Frontend (`marketData.test.ts`, `graphsMarket.test.tsx`)

- Instrument/Market sections render reports when data exists
- Placeholder removed when `available=true`
- Click bucket → filter chip → URL
- Coverage display, timing badges, partial-feed warning
- Reset exploration preserves global filters

### Fixture

`tests/fixtures/market_data/` — 60+ session synthetic series with known gap/RVOL/day-type days + attached trades.

---

## Known Provider Limitations (Q supplement)

| Provider | Limitation |
|----------|------------|
| Alpaca IEX | Non-consolidated volume; RVOL not equivalent to SIP |
| Alpaca SIP | Requires appropriate subscription |
| Massive/Polygon | Rate limits; symbol coverage varies |
| All | Delisted tickers may 404; no yfinance fallback |
| All | Same-day EOD unavailable until session close |
| Raw adjustment | Split/reverse-split stocks may need manual review |

---

## Implementation Phases (after plan approval)

### Phase 1 — Foundation
- Settings, models, migrations, `market_data/` providers (Fake + Alpaca + Massive stubs)
- `market_daily_bars` cache
- Feature calculator (pure functions + tests)

### Phase 2 — Enrichment
- Enrichment service, job tracking, API endpoints, CLI
- Post-import missing detection
- `/market-data` status UI

### Phase 3 — Graphs integration
- Join features into reports pipeline
- Registry buckets + filters + URL params
- ReportCard coverage/timing badges
- Activate INSTRUMENT market reports + MARKET section

### Phase 4 — Validation
- Full test suite, 10k perf, manual sanity check on 5 real trades
- Documentation updates

---

## Files to Create / Modify

### New

```
backend/app/market_data/
  base.py, models.py, registry.py, cache.py, quality.py
  alpaca.py, massive.py, fake.py, http_client.py
backend/app/services/market_enrichment/
  calculator.py, service.py, batching.py, coverage.py
backend/app/db/models/
  market_daily_bar.py, instrument_day_feature.py
  benchmark_day_feature.py, trade_market_feature.py
  market_enrichment_job.py
backend/app/api/market_data.py
backend/app/cli/enrich_market_data.py
frontend/src/pages/MarketDataPage.tsx
frontend/src/api/marketData.ts
docs/MARKET_DATA.md
docs/INSTRUMENT_FEATURES.md
docs/MARKET_FEATURES.md
docs/MARKET_DATA_QUALITY.md
```

### Modify

```
backend/app/config.py
backend/app/db/migrate.py
backend/app/db/models/__init__.py
backend/app/main.py
backend/app/services/reports/config.py
backend/app/services/reports/registry.py
backend/app/services/reports/features.py
backend/app/services/reports/filters.py
backend/app/services/reports/service.py
backend/app/services/import_service.py  (post-import hook, non-blocking)
frontend/src/main.tsx
frontend/src/types/reports.ts
frontend/src/utils/graphFilters.ts
frontend/src/components/graphs/ReportCard.tsx
frontend/src/pages/GraphsPage.tsx
docs/REPORT_DIMENSIONS.md
docs/GRAPHS_AND_REPORTS.md
docs/DATABASE_SCHEMA.md
docs/ARCHITECTURE.md
README.md
```

---

## Explicitly Out of Scope (Step 5+)

- Pine signal RVOL (`signal_rvol`) — distinct from `instrument_rvol50_eod`
- Signal-time gap, VWAP, EMA9, setup quality, A/A+
- Manual vs AUTO matching, psychology tags
- R-multiple, expectancy, drawdown, MFE/MAE
- yfinance / web scraping as production source

---

## Definition of Done Mapping

See spec §94–96. This plan addresses all 44 criteria via the architecture above. Completion requires plan approval, then phased implementation and manual validation workflow (A–U).

**Next step after review:** Implement Phase 1 (foundation + formula tests with FakeProvider).
