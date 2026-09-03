# Step 3 + Step 4 Implementation Audit

**Date:** 2026-09-02  
**Scope:** Verify current code against `docs/STEP_3_PLAN.md` and `docs/STEP_4_PLAN.md`. Harden genuine gaps. Not a redesign. Step 8 features already joined into Graphs are documented, not expanded.

**Overall verdict:** **PASS with documented open ends** (no remaining Step 3/4 blockers in code). Live Alpaca validation is **USER-ENVIRONMENT PENDING**.

---

## STEP 3 summary

| | |
|--|--|
| Requirements audited | 33 core Step 3 items (§2–§33) plus shared Graphs items |
| PASS | 28 |
| PARTIAL | 5 |
| FAIL | 0 (after fixes) |
| OBSOLETE / SUPERSEDED | 0 |
| Single report pipeline | **PASS** |
| Global/exploration separation | **PASS** |
| URL persistence | **PASS** (history push; was `replace: true`) |
| Same-dimension replacement/toggle | **PASS** |
| Cross-section filtering | **PASS** |
| NY timezone | **PASS** |
| Trade-number no-lookahead | **PASS** |
| Previous-completed-trade no-lookahead | **PASS** |
| Consecutive-loss no-lookahead | **PASS** (BE resets streak) |
| Daily-P&L-before-entry no-lookahead | **PASS** |
| Account isolation | **PASS** |
| 10k performance | **PARTIAL** vs plan &lt;1s; suite asserts &lt;5s and passes |

---

## STEP 4 summary

| | |
|--|--|
| PASS | majority of §34–§80 after hardening |
| PARTIAL | live validation, Massive, splits API, 10k enrichment bench, CA protection |
| FAIL | 0 remaining blockers |
| Alpaca | **IMPLEMENTED** (real HTTP adapter) |
| Massive | **STUB / NOT PRESENT** |
| Fake | **IMPLEMENTED** |
| Active provider (default config) | `none` until `LTA_MARKET_DATA_PROVIDER` is set |
| Active feed | `iex` default when Alpaca configured (`LTA_ALPACA_DATA_FEED`) |
| Consolidated | `true` only for `sip` |
| Adjustment mode | `raw` (`LTA_MARKET_ADJUSTMENT_MODE`) |
| Live provider validation | **PENDING** |
| Cache-first | **PASS** |
| Second identical enrich provider calls | **0** |
| Recalculate provider calls | **0** |
| RVOL50 / prior-day RVOL / ATR14 prior / SMA20/50 / Opening Gap / Day Type / SPY / PRE_ENTRY-EOD / IEX / provider-switch / weekend cache | **PASS** |
| Corporate-action protection | **PARTIAL** |
| Coverage/reasons | **PASS** |

---

## DATABASE / PROVENANCE

| Object | Status |
|--------|--------|
| Daily bars | `market_daily_bars` unique `(symbol, trading_date, provider, feed, adjustment_mode)` |
| Instrument features | unique `(symbol, trading_date, provider, feed, adjustment_mode, calculation_version)` **fixed this audit** |
| Benchmark features | **same table** as instrument (symbol=`SPY`); no `benchmark_day_features` table — superseded by design |
| Trade market features | one **active** row per `trade_id`; overwrite on re-enrich; FKs to trade + feature rows |
| Enrichment jobs | provider/feed, counts, status, errors |
| Cache coverage | `market_cache_coverage` probed ranges |
| Migrations | `create_all` + `migrate.py` `_ensure_instrument_feature_provenance` (no data drop) |
| Provider/feed/version policy | parallel bar + derived rows per provenance; active TMF pointer updates; old derived rows retained |
| Potential collisions found | **yes** (old unique lacked provider/feed) — **fixed** |

---

## GRAPHS INTEGRATION

| | |
|--|--|
| Instrument reports active | Yes, when trades exist (market dims need enrichment) |
| Market reports active | When provider configured **or** benchmark rows exist |
| All clickable | **PASS** (filter_dimension from registry) |
| All update every section | **PASS** (one filtered list) |
| Coverage visible | **PASS** + exclusion reasons |
| Timing badges | **PASS** PRE-ENTRY / END OF DAY |
| Quality filter | **PASS** (`include_partial_feed`; default does not drop weekday trades) |
| URL persistence | **PASS** |

---

## TESTS

| | |
|--|--|
| Backend | **226 passed** |
| Frontend | **24 passed** |
| Production build | **PASS** (`tsc && vite build`) |
| Performance | `test_10k_trades_performance` asserts &lt;5s |

---

## Fixes performed this audit

1. Derived-feature unique key includes provider/feed/adjustment_mode + migration.
2. `trade_market_features` FKs; benchmark join via `benchmark_feature_id` (no last-write SPY dict).
3. NYSE calendar + `market_cache_coverage` so weekends/holidays/listing gaps are not refetched.
4. Recalculate never networks; Refresh overwrites same-provenance bars and is a distinct UI/CLI/API action.
5. PRE_ENTRY metrics computed on incomplete sessions; EOD null + `PENDING_EOD` with injectable clock.
6. IEX volume/RVOL excluded from default Graphs; `include_partial_feed` opt-in; gap/ATR/SMA still apply.
7. Coverage `exclusion_reasons` + `scope: current_cohort`.
8. `_pnl_bucket` uses Decimal.
9. Alpaca: no retry of permanent 4xx; sleep patched in tests; logs redact secrets.
10. Graphs URL is source of truth (Back/Forward); Best/Worst Observed; metric options from backend registry.
11. Lookback extension when &lt;50 sessions; per-symbol enrichment errors do not abort the batch.

---

## Requirement register

For each item: Requirement / Planned / Actual / Status / Evidence / Fix / Tests.

### §2 One report engine

- **Planned:** `GET /api/reports` → filters → closed trades → annotate → filter → aggregate registry.
- **Actual:** `reports/service.py` `get_reports`; Dashboard graphs remain a separate dashboard endpoint (not a second Graphs engine). Market + excursion join the same `AnnotatedTrade` list.
- **Status:** PASS
- **Evidence:** `backend/app/services/reports/service.py`, `api/reports.py`
- **Fix:** none
- **Tests:** `test_reports_graphs.py`, `test_step3_4_audit.py`

### §3 Single filtered population

- **Planned:** every report in one response uses the same filtered trades.
- **Actual:** one `filtered` list; `coverage.matching_trades` equals `matching_trade_count`.
- **Status:** PASS
- **Evidence:** `get_reports` loop over `REPORT_DEFINITIONS`
- **Fix:** none (added assertion)
- **Tests:** `test_matching_trade_count_consistent_across_reports`

### §4 Global vs exploration

- **Planned:** global date/account/source/direction/ticker vs exploration dimensions; reset exploration preserves global.
- **Actual:** `TradeFilterSet`; frontend `resetExploration` returns `{}`.
- **Status:** PASS
- **Evidence:** `filters.py`, `graphFilters.ts`
- **Fix:** none
- **Tests:** `test_reset_exploration_leaves_global`, frontend reset serialization

### §5 URL serialization

- **Planned:** refresh + Back/Forward; unknown keys safe; old URLs usable.
- **Actual:** was `setSearchParams(..., { replace: true })` (broke history). Now URL is source of truth. Unknown keys ignored. Invalid dates 400.
- **Status:** PASS (fixed)
- **Evidence:** `GraphsPage.tsx`, `parse_filter_set`
- **Fix:** push history; invalid date HTTP 400
- **Tests:** `graphFilters.test.ts`, `test_unknown_keys_ignored`, `test_invalid_date_400`

### §6 Single-select dimension semantics

- **Planned:** replace within dimension; toggle off; different dimensions coexist.
- **Actual:** `toggleExplorationFilter`
- **Status:** PASS
- **Tests:** frontend toggle tests + coexist test

### §7 Click-to-filter cross-section

- **Planned:** any click updates all sections.
- **Actual:** one exploration set → one `get_reports` call.
- **Status:** PASS
- **Tests:** `test_combined_exploration_cross_section`, `test_discovery_workflow`

### §8 Report registry

- **Planned:** central `REPORT_DEFINITIONS`.
- **Actual:** backend registry; frontend `EXPLORATION_KEYS` / labels mirror keys (not a second calculator). Metric labels come from API.
- **Status:** PASS
- **Fix:** ReportCard options from `metrics` payload

### §9 Metric registry

- **Planned:** one metric registry; backend authoritative.
- **Actual:** `METRICS` in `registry.py`; aggregation in `_bucket_metrics`; frontend formats only.
- **Status:** PASS

### §10 Decimal aggregation

- **Planned:** Decimal for P&L/averages.
- **Actual:** `_bucket_metrics` Decimal; `_pnl_bucket` was float.
- **Status:** PASS (fixed)
- **Fix:** Decimal `_pnl_bucket`
- **Tests:** `test_aggregation_metrics`

### §11 Win/loss/BE

- **Planned:** same classifier as Dashboard; win rate excludes BE.
- **Actual:** `classify_outcome` / `win_rate_pct` from `analytics.py`
- **Status:** PASS

### §12 Global date range

- **Planned:** closed trades, NY date bounds.
- **Actual:** **exit-time NY date** via `build_closed_trades_query` (same as Dashboard). Time dimensions use **entry** NY time. Multi-day trades belong to the exit date for the global universe.
- **Status:** PASS (documented supersession of any “entry-date global” reading)
- **Evidence:** `dashboard_service.build_closed_trades_query`, `compute_base_features`

### §13 NY timezone

- **Planned:** `America/New_York` via zoneinfo.
- **Actual:** `analytics_tz()` / `ZoneInfo(settings.analytics_timezone)`
- **Status:** PASS

### §14 Entry-hour boundaries

- **Planned:** 09:29:59 … 10:00:00 agree with labels; 09:45:00 not in 09:30–09:45.
- **Actual:** minute floors; 09:45:00 → `09:45-10:00`
- **Status:** PASS
- **Tests:** `test_entry_hour_edges`

### §15 Price/qty/duration/Step 4 bucket boundaries

- **Planned:** no overlap; $2.00 in exactly one bucket.
- **Actual:** inclusive lo, exclusive hi in `config.py`
- **Status:** PASS
- **Tests:** `test_price_quantity_boundaries`

### §16 Missing / unknown

- **Planned:** do not coerce missing market features into Neutral/$0.
- **Actual:** omitted keys → aggregator `"unknown"`; duration None → Unknown; prices on trades are NOT NULL.
- **Status:** PASS

### §17 Symbol vs ticker

- **Planned:** no conflict or document distinction.
- **Actual:** both match `Trade.ticker`. Global `ticker` is SQL; exploration `symbol` is post-annotation. Combined AND if both set. Clicking symbol does not write the global ticker chip.
- **Status:** PASS (documented)

### §18 Trade number of day

- **Planned:** per account+NY entry day, sort by entry, id tie-break; not exit.
- **Actual:** `apply_behavior_features`
- **Status:** PASS
- **Tests:** `test_trade_number_of_day`, `test_same_timestamp_trade_number_tie_break`

### §19 Previous completed trade

- **Planned:** most recent same-account exit &lt; entry; overlapping open does not count.
- **Actual:** event sweep kind 0 exit before kind 1 entry
- **Status:** PASS
- **Tests:** `test_overlapping_no_lookahead`

### §20 Consecutive losses

- **Planned:** completed trades only; document BE.
- **Actual:** BE **resets** streak (`else: loss_streak = 0`). Step 7 dashboard streaks are separate.
- **Status:** PASS
- **Tests:** `test_consecutive_losses`, `test_breakeven_breaks_loss_streak`

### §21 Daily P&amp;L before entry

- **Planned:** same account, same NY date, exits before entry only.
- **Actual:** PnL added on exit events
- **Status:** PASS
- **Tests:** `test_daily_pnl_before_entry_excludes_current`, `test_overlapping_no_lookahead`

### §22 Account isolation

- **Status:** PASS
- **Tests:** `test_two_accounts_independent`

### §23 Best/Worst Observed

- **Planned:** not “Best Edge”.
- **Actual:** labels were “Best/Worst”.
- **Status:** PASS (fixed)
- **Fix:** “Best Observed” / “Worst Observed”
- **Evidence:** `ReportCard.tsx`

### §24 Minimum sample

- **Planned:** display/interpretation; does not change population.
- **Actual:** backend omits low-n **buckets**; `matching_trade_count` unchanged. Frontend also filters chart buckets.
- **Status:** PASS (display-only for population; buckets hidden)
- **Tests:** `test_min_sample_does_not_change_population`

### §25 Collapsible sections

- **Planned:** presentation-only; sessionStorage.
- **Actual:** `useSectionExpansion` + sessionStorage; filters/URL unchanged.
- **Status:** PASS

### §26 Quick navigation

- **Planned:** expand + scroll; unique ids.
- **Actual:** `section-${key}`; `ensureExpanded`; placeholders still have ids.
- **Status:** PASS

### §27 Placeholder / availability

- **Planned:** ACTIVE / empty / requires enrichment / not implemented.
- **Actual:** MARKET active if provider configured or SPY rows exist (even if current cohort has 0 features — banner “Filtered Cohort Has No Market Data”). STRATEGY/RISK placeholders. EXECUTION when excursion rows exist. Not “Requires Pine Signals” for unmatched filters.
- **Status:** PASS (fixed banners)
- **Evidence:** `GraphsPage.tsx` `marketBanner`, `ReportSection` MARKET copy

### §28 Coverage semantics

- **Planned:** matching / data_available / excluded reconcile.
- **Actual:** plus `exclusion_reasons` and `scope=current_cohort`
- **Status:** PASS (fixed)
- **Tests:** IEX exclusion reasons

### §29 Coverage after exploration

- **Planned:** current-cohort, not global enrichment %.
- **Actual:** computed on `filtered`; documented in UI title.
- **Status:** PASS

### §30 / §75 Report performance

- **Planned:** &lt;1s for ~10k trades.
- **Actual:** `test_10k_trades_performance` **&lt;5s**. Full suite 226 tests in ~32s including 10k.
- **Status:** PARTIAL vs original 1s target (not a blocker; no N×reports DB loop)
- **Tests:** `test_10k_trades_performance`

### §31 N+1

- **Planned:** load supporting data once.
- **Actual:** exec meta one grouped query; market TMF+inst+bench one join; no per-report queries.
- **Status:** PASS

### §32 Frontend API calls

- **Planned:** metric change local; filter change refetch.
- **Actual:** `reportMetrics` local; `graphState`/URL triggers `fetchReports`
- **Status:** PASS

### §33 Determinism

- **Status:** PASS
- **Tests:** `test_report_order_deterministic`

### §34 Real providers

- **Alpaca:** IMPLEMENTED (`alpaca.py` HTTP). **Massive:** not in registry. **Fake:** IMPLEMENTED.
- **Status:** PARTIAL (Massive stub by absence)
- **Evidence:** `market_data/registry.py`

### §35 / §73 Live validation

- **Planned:** manual Alpaca check.
- **Actual:** no local credentials (`.env` absent). Fake ≠ live.
- **Status:** NON-BLOCKING USER-ENVIRONMENT VALIDATION PENDING
- **Procedure:**
  1. Set `LTA_MARKET_DATA_PROVIDER=alpaca`, key, secret, `LTA_ALPACA_DATA_FEED=sip` (or iex).
  2. Import ≥5 real closed trades including one high-gap name if available.
  3. Market Data → Enrich Missing.
  4. Compare ticker, trade date, prior close, regular open, close, volume, gap %, RVOL50, prior RVOL, ATR14 prior, entry vs ATR, SMA20/50, day type, and SPY prior/open/close/gap/movement/day type against a reputable chart.
  5. Record discrepancies in this file.

### §36 Provenance on bars/features

- **Status:** PASS (bars + derived provider/feed/adjustment/version/calculated_at; flags JSON)

### §37 Derived unique keys — HIGH PRIORITY

- **Planned risk:** unique `(symbol, date, version)` mixes IEX/SIP.
- **Actual:** **was FAIL**; now unique includes provider/feed/adjustment_mode.
- **Status:** PASS (fixed)
- **Fix:** model + `migrate.py` + persist/lookup
- **Tests:** `test_provider_switch_does_not_mix_feeds`

### §38 Trade market feature versioning

- **Policy:** one **active** row per trade; overwrite pointer + trade-specific entry-vs fields; old `instrument_day_features` rows retained by provenance/version. Reproducibility of *active* Graphs is current provider+version. Historical derived rows remain queryable in DB.
- **Status:** PASS (documented)

### §39 Cache-first

- **Status:** PASS
- **Tests:** `test_cache_avoids_second_provider_call`, `test_weekend_holiday_not_refetched`

### §40 Weekends/holidays not missing bars

- **Actual:** was “any cache ⇒ no fetch” (wrong holes) **and** calendar-day gaps. Now NYSE trading days + probed coverage.
- **Status:** PASS (fixed)
- **Tests:** `test_weekend_holiday_not_refetched`, `missing_date_ranges` weekend/Labor Day

### §41 Lookback sufficiency

- **Actual:** 120 calendar days heuristic; extend +365 days if &lt;50 sessions before trade date; else `INSUFFICIENT_HISTORY` (no shortened RVOL/SMA).
- **Status:** PASS

### §42 RVOL50

- **Formula:** current volume / avg(previous 50 completed session volumes); current excluded; None if &lt;50.
- **Status:** PASS
- **Tests:** `test_rvol50_5x`, `test_rvol50_excludes_current_and_requires_50`

### §43 Prior-day RVOL

- **Formula:** P volume / avg 50 sessions **before P** (one extra layer).
- **Status:** PASS
- **Tests:** `test_prior_day_rvol_session_index`

### §44 IEX partial feed

- **Planned:** PARTIAL_FEED; exclude from default volume analysis.
- **Actual:** was still bucketed in Graphs.
- **Status:** PASS (fixed)
- **Tests:** `test_iex_rvol_excluded_from_default_graphs`

### §45 Price-only with partial feed

- **Status:** PASS (gap/ATR/SMA still applied on IEX)

### §46 Quality model

- **Actual:** primary `quality_status` + `quality_flags` JSON (simultaneous PARTIAL_FEED / INSUFFICIENT_HISTORY / PENDING_EOD / SPLIT_METADATA_UNAVAILABLE).
- **Status:** PASS (smallest extension, not a flags-engine redesign)

### §47 Opening gap

- **Formula:** `(day_open - prior_close) / prior_close * 100` on daily session bar (Alpaca 1Day = regular session).
- **Status:** PASS
- **Tests:** `test_opening_gap_25_pct`

### §48 Daily movement

- **Status:** PASS
- **Tests:** `test_daily_movement_20_pct`

### §49 ATR Wilder / atr14_prior

- **Actual:** TR max of three; SMA of first 14 TR; Wilder after; ATR from **prior sessions only** (current day excluded from denominator series).
- **Status:** PASS
- **Tests:** `test_wilder_atr_init`, incomplete-day keeps `atr14_prior`

### §50 Entry vs ATR signed

- **Status:** PASS
- **Tests:** `test_entry_vs_atr`

### §51 TR/ATR EOD

- **Status:** PASS (current TR / atr14_prior)

### §52 SMA20/50 prior

- **Status:** PASS (closes before trade date; full 20/50 or None)

### §53 Day type precedence

- **Status:** PASS
- **Tests:** `test_trend_up_day_type`, `test_zero_range_day_type`

### §54 Benchmark SPY sharing

- **Status:** PASS (one SPY feature row per date+provenance; two trades share `instrument_feature` for NCRA and same bench id)
- **Tests:** `test_same_symbol_day_reuses_instrument_row`

### §55–§56 Timing badges / no leakage

- **Status:** PASS (registry `availability_timing`; UI tooltips)

### §57 Current-day PENDING_EOD

- **Actual:** was never passed `is_today_incomplete`.
- **Status:** PASS (fixed; `freeze_time`)
- **Tests:** `test_pending_eod_with_frozen_clock`, `test_incomplete_day_keeps_pre_entry`

### §58 Same symbol/day reuse

- **Status:** PASS
- **Tests:** `test_same_symbol_day_reuses_instrument_row`

### §59 Missing symbol

- **Status:** PASS (trade remains; batch continues)
- **Tests:** `test_symbol_failure_does_not_drop_trade`

### §60 Symbol mapping

- **Actual:** provider lookup uses `Trade.ticker`; ticker never overwritten. No alias table (renames/delisted remain the historical ticker).
- **Status:** PASS (documented)

### §61–§62 Corporate actions / get_splits

- **Actual:** `get_splits` returns `[]`; `supports_splits=False`; flag `SPLIT_METADATA_UNAVAILABLE`. No heuristic that would false-flag 100% gaps. Alpaca split API **not wired**.
- **Status:** PARTIAL
- **Fix:** honest flag + docs; do not claim split-safe ATR/SMA history

### §63 Job tracking

- **Status:** PASS (success/missing/error counts; failed symbol does not roll back prior committed jobs; in-transaction per-symbol catch)

### §64 Retry / 429

- **Status:** PASS (1/2/4/8… via `2**attempt`; no 401 retry; sleep mockable)
- **Tests:** `test_alpaca_does_not_retry_401`

### §65 Secrets

- **Status:** PASS
- **Tests:** `test_status_hides_secrets`

### §66 Settings status differentiation

- **Status:** PASS (Provider Not Configured vs cohort has no market data vs partial-feed warning)

### §67 Recalculate vs Refresh

- **Actual:** Recalculate had no Refresh button; refresh API used enrich without overwrite.
- **Status:** PASS (fixed)
- **Tests:** `test_refresh_calls_provider_recalculate_does_not`

### §68 EOD immutability

- **Status:** PASS (historical bars skipped unless refresh or today’s session)

### §69 Bucket boundaries Step 4

- **Status:** PASS (`config.py` + `bucket_key_for_value` tests)

### §70 Step 4 click-to-filter

- **Status:** PASS
- **Tests:** `test_combined_exploration_cross_section`, `test_gap_exploration_filter`

### §71 Quality filter vs unrelated reports

- **Status:** PASS (IEX still in Day of Week)

### §72 Coverage reasons

- **Status:** PASS (fixed)

### §74 IEX vs SIP sanity

- **Status:** PASS via FakeProvider two feeds (SIP live optional)
- **Tests:** `test_provider_switch_does_not_mix_feeds`

### §76 Migrations

- **Convention:** still `create_all` + `migrate.py`. Step 4 tables created by metadata; provenance unique migrated in place.
- **Status:** PASS (documented; not a new migration framework)

### §77 Referential integrity

- **Status:** PASS for new DBs (FKs + ON DELETE CASCADE on trade_id). Existing SQLite files get new columns/index via migrate; table rebuild for FKs is not performed (SQLite limitation) — application still uses ids.

### §78 Provider switch

- **Status:** PASS (fixed unique key)
- **Tests:** `test_provider_switch_does_not_mix_feeds`

### §79 Calculation version

- **Status:** PASS
- **Tests:** `test_calculation_version_recalc_no_network`

### §80 Timing badges

- **Status:** PASS

### §81 Documentation

- **Status:** PASS (this file + MARKET_DATA, QUALITY, SCHEMA, GRAPHS, README, ARCHITECTURE, INSTRUMENT/MARKET features)

---

## Open ends

| Item | Class |
|------|--------|
| Live Alpaca comparison of ≥5 real trades / high-gap name | USER-ENVIRONMENT VALIDATION |
| Live IEX vs SIP on Alpaca SIP entitlement | USER-ENVIRONMENT VALIDATION |
| Massive provider | DEFERRED BY DESIGN (not in registry) |
| `get_splits` / true CORPORATE_ACTION_AMBIGUITY from issuer events | PARTIAL / NON-BLOCKING |
| Reports 10k &lt;1s (suite &lt;5s) | NON-BLOCKING |
| Dedicated 10k **enriched** symbol-day benchmark numbers | NON-BLOCKING |
| Separate `benchmark_day_features` table | DEFERRED BY DESIGN (SPY in `instrument_day_features`) |
| Versioned Alembic-style migrations | DEFERRED BY DESIGN (`create_all` + `migrate.py`) |
| Step 8 excursion query params not all on FastAPI `/api/reports` signature | NON-BLOCKING (out of this audit’s feature scope) |
| Ticker rename alias table | DEFERRED BY DESIGN |

No remaining **BLOCKING** Step 3/4 issues after this pass.

Do not start Step 8 or other roadmap work from this audit.
