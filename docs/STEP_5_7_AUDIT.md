# Step 5 + Step 7 Implementation Audit

**Date:** 2026-09-02  
**Scope:** Verify current code against `docs/STEP_5_PLAN.md` and `docs/STEP_7_PLAN.md`. Harden genuine gaps. Do not implement Step 8 or Research Lab. Step 6 permanent MANUAL-vs-AUTO comparison remains **SKIPPED**. AUTO remains a valid `source_type`.

**Overall verdict:** **PASS with documented open ends.** No remaining Step 5 or Step 7 **BLOCKING** issues in code. Real Pine log / live-trade R validation is **USER-DATA VALIDATION PENDING**.

---

## STEP 5 summary

| | |
|--|--|
| Requirements audited | 41 (§1–§41) |
| PASS | 37 |
| PARTIAL | 4 |
| FAIL | 0 |
| OBSOLETE / SUPERSEDED | Signal ID `ENTRY_BAR_UNIX_MS` wording (superseded by ARMED birth bar) |
| Signal architecture | **PASS** |
| Signal ID rule | `<STRATEGY_KEY>\|<TICKER>\|<TIMEFRAME>\|<OPPORTUNITY_BIRTH_BAR_MS>` |
| ARMED→ENTRY→EXIT stable ID | **PASS** |
| Pine logging trading-logic diff | **PASS** (trading-state `:=` assignments identical to CURRENT) |
| Schema version | `1.0` (parser contract) |
| Strategy versions found | Pine emits `Momentum Pullback Copilot v0.3.3.1 Opening Fade Research` → normalized `v0.3.3.1` |
| Realtime / historical / unknown | Contract + UI default REALTIME; no silent historical fallback |
| Unique signals / events (this repo) | No user Pine imports on disk |
| Duplicate re-import | 0 new events |
| Payload conflict | `EVENT_PAYLOAD_CONFLICT`; original kept |
| Strategy Graphs | **PASS** (CONFIRMED default) |
| Signal gap vs Step 4 gap | **PASS** |
| Signal RVOL vs Step 4 RVOL | **PASS** |
| Opening Fade support | **PARTIAL / UNAVAILABLE** extra typed fields |
| Real-data validation | **PENDING** |
| 10k performance | **PARTIAL** (see §41) |

### Signal ID (implemented)

Pine `f_analyzer_signal_id(time)` at ARMED:

```
FIRST_PULLBACK|<TICKER>|<TIMEFRAME>|<ARMED_BAR_TIME_MS>
```

`activeSignalId` is reused for ENTRY and EXIT. The future ENTRY bar is not required. Strategies without ARMED would use ENTRY bar ms. Analyzer stores the Pine value verbatim.

---

## STEP 5 requirement table

| # | Requirement | Result | Notes |
|---|-------------|--------|-------|
| 1 | Signal domain model; Trade independent | **PASS** | `signals`, `signal_events`, `trade_signal_links`, `pine_import_batches` (+ conflicts/errors). No strategy snapshot columns on Trade. |
| 2 | Snapshot immutability | **PASS** | Imported Pine `signal_gap_pct` / `signal_rvol` are stored; never replaced by Step 4 EOD/session values. |
| 3 | Deterministic Signal ID at ARMED | **PASS** | See rule above. `ENTRY_BAR_UNIX_MS` language removed from the plan. |
| 4 | ID collision matrix | **PASS** | `test_signal_id_collision_rules` |
| 5 | SIGNALLOG observer-only | **PASS** | Trading-state assignments match CURRENT Copilot. Logging block + `activeSignalId` flags only. Title string differs (SIGNALLOG vs Opening Fade Research). |
| 6 | Log each transition once | **PASS** | `loggedArmed/Entry/ExitThisOpportunity`; reset on new ARMED. Analyzer idempotency is extra. |
| 7 | schema_version ≠ strategy_version | **PASS** | Independent columns and parser fields. |
| 8 | Version normalization | **PASS** | Original string kept; `strategy_version_normalized` (`v0.3.3.1`). |
| 9 | Mixed strategy versions | **PASS** | Banner `MIXED STRATEGY VERSIONS` with versions + n. No auto-picked default version. |
| 10 | REALTIME / HISTORICAL_REPLAY / BACKTEST / UNKNOWN | **PASS** | Pine `barstate.isrealtime`. Default graphs `pine_scope=REALTIME`. Empty: “No realtime Pine signals in this cohort”. No silent fallback. |
| 11 | Origin in URL/filter/chip | **PASS** | `pine_scope` always serialized; chip on Graphs. |
| 12 | Pine timestamps UTC | **PASS** | Offset-aware + UNIX ms; DST test. Stored UTC. |
| 13 | Event fingerprint | **PASS** | `sha256(signal_id\|event_type\|event_time_iso\|strategy_version)` |
| 14 | EVENT_PAYLOAD_CONFLICT | **PASS** | Same fingerprint, different payload → conflict row; original event unchanged. |
| 15 | Out-of-order merge | **PASS** | EXIT/ENTRY/ARMED → 1 Signal, 3 events. |
| 16 | Field ownership | **PASS** | ARMED fills unplanned snapshot if null; ENTRY owns snapshot; EXIT owns exit fields only. Documented in `merger.py`. |
| 17 | raw_line / raw_payload_json | **PASS** | On every event; malformed rows keep `raw_line` on import error. |
| 18 | Preview no mutate | **PASS** | |
| 19 | Partial import 9+1 | **PASS** | Status `PARTIAL`. |
| 20 | Legacy TRADE_RECORD | **PARTIAL** | Best-effort parser exists. **No samples in repo.** USER-DATA VALIDATION PENDING. `legacy=true`, origin UNKNOWN, never EXPLICIT_ID. |
| 21 | Legacy synthetic ID collisions | **PASS** | `LEGACY\|…\|<line-hash>` so same ticker/time stay separate. |
| 22 | trade_signal_links auditable | **PASS** | trade, signal, match_type, confidence, time_delta, status. Not a Trade.signal_id column. |
| 23 | EXPLICIT_ID | **PARTIAL** | `confirm_link(..., EXPLICIT_ID)` → confidence 1.0 CONFIRMED. Trades do not carry a Pine ID today, so there is no automatic EXPLICIT path from CSV. |
| 24 | AUTO time match | **PASS** | Unique → CONFIRMED. Multiple → AMBIGUOUS, no pick. |
| 25 | MANUAL time match | **PASS** | Unique → SUGGESTED. User confirm → CONFIRMED / MANUAL_REVIEW. |
| 26 | Wrong ticker / direction | **PASS** | Hard reject. |
| 27 | Multiple MANUAL | **PASS** | Second MANUAL not auto-linked. |
| 28 | Rejected not re-suggested | **PASS** | |
| 29 | Ambiguous storage | **PASS** | `Signal.match_status` + link rows. No imaginary `ambiguous` column. |
| 30 | Link/unlink → RiskService | **PASS** | Confirm / reject / unlink / import all recalc. |
| 31 | Later ENTRY after ARMED+link | **PASS** | Importer `recalculate_for_signal`. Manual override wins. |
| 32 | Strategy graphs CONFIRMED | **PASS** | SUGGESTED only if `include_suggested_signals` + URL. |
| 33 | Coverage reconcile; missing ≠ negative | **PASS** | `exclude_missing`; missing `above_vwap` is not “Not Above VWAP”; missing quality is not “Other”. |
| 34 | signal_gap vs opening_gap | **PASS** | Distinct keys. No generic `gap` overwrite. |
| 35 | signal_rvol vs rvol50 | **PASS** | Distinct keys. BLOCKING collision not found. |
| 36 | Timing badges | **PASS** | Setup dims PRE-ENTRY; mechanical exit EXIT. |
| 37 | Opening Fade | **PARTIAL** | SIGNALLOG always `FIRST_PULLBACK`. Extra OF dims **UNAVAILABLE** (not invented). Retracement **PARTIAL** (First Pullback field only). |
| 38 | /signals UX | **PASS** | Pagination, filters, detail (events, raw, links, candidates, snapshot). |
| 39 | Untraded signals kept | **PASS** | |
| 40 | Coverage by NY date | **PASS** | Trades / Signals / Linked / Coverage. |
| 41 | 10k performance | **PARTIAL** | See performance section. No N+1 trade→signal query. |

### Pine SIGNALLOG vs CURRENT (diff summary)

Compared trading-state assignments (`:=` on non-analyzer variables).

| Area | Result |
|------|--------|
| State machine (`state :=`) | Identical |
| Impulse / pullback / ARMED / ENTRY / stop / 2R / exit | Identical assignment set |
| Position sizing / VWAP / EMA9 / 5m / volume / alerts / cooldown / labels | No trading-assignment drift |
| Added in SIGNALLOG only | Observer helpers, `activeSignalId`, once-per-opportunity flags, `PINE_SIGNAL_EVENT` lines |
| Script title | SIGNALLOG vs “Opening Fade Research” (display only) |

Any trading-logic difference would have been **BLOCKING**. None found.

### Merge ownership (exact)

| Stage | Owns | May fill if null | Must not overwrite |
|-------|------|------------------|--------------------|
| ARMED | `armed_time_utc`; early plan | Snapshot fields if currently null | ENTRY-owned snapshot after ENTRY exists |
| ENTRY | Entry time + signal-time snapshot (`planned_*`, gap, RVOL, impulse, retrace, 5m, VWAP, EMA9, volume, quality, shares, allowed_risk) | — | EXIT-owned exit fields |
| EXIT | `exit_signal_time_utc`, mechanical exit price/reason | Snapshot only if still null | ENTRY snapshot |

---

## STEP 7 summary

| | |
|--|--|
| Requirements audited | 54 (§42–§95) |
| PASS | 51 |
| PARTIAL | 3 |
| FAIL | 0 |
| trade_risk | **PASS** (1:1 + Trade cache) |
| Trade cache sync | **PASS** (RiskService atomic write) |
| risk_audit_log | **PASS** |
| Manual override | **PASS** |
| Pine auto-population | **PASS** |
| LONG / SHORT / invalid / scale-in | **PASS** |
| Planned vs actual | **PASS** |
| R P&L basis | **PASS** (`NET` \| `GROSS`, `fees_known`) |
| Real equity baseline vs analytical cohort | **PASS** |
| Equity-at-entry no-lookahead | **PASS** |
| Multi-account isolation | **PASS** |
| RISK Graphs | **PASS** |
| /risk page | **PASS** |
| Real-data audit | **PENDING** |
| 10k performance | **PARTIAL** |

R aggregates on **synthetic fixtures** (not user journal): Average R / Median / Expectancy / PF / payoff are covered by unit tests (`test_expectancy_pf_payoff_r`). Live journal percents are **N/A** until user data is imported.

---

## STEP 7 requirement table

| # | Requirement | Result | Notes |
|---|-------------|--------|-------|
| 42 | Dedicated `trade_risk` | **PASS** | 1:1 + denormalized Trade cache. |
| 43 | Dual source of truth | **PARTIAL** | RiskService is the only production writer (PATCH, import, link). Legacy `apply_risk_to_trade` still writes Trade cache only for old Step 3 unit tests. Invariant test covers RiskService path. |
| 44 | Backfill | **PASS** | Copies known cache; does not label unknown as PINE. |
| 45 | Source hierarchy | **PASS** | MANUAL amount → MANUAL stop → PINE_SIGNAL confirmed stop → IMPORTED → CALCULATED → UNKNOWN. `allowed_risk` is never the R denominator. |
| 46 | Manual override survives | **PASS** | Import, link, unlink, recalc. |
| 47 | risk_audit_log | **PASS** | Append-only: trade_id, field, old, new, source, created_at. |
| 48 | Planned vs actual | **PASS** | Independent columns. |
| 49 | LONG risk | **PASS** | entry − stop; stop < entry. |
| 50 | SHORT risk | **PASS** | stop − entry; no `abs()` hide. |
| 51 | Invalid stop | **PASS** | `INVALID_STOP`, R=NULL. |
| 52 | Scale-in | **PASS** | Weighted avg entry × opening qty; one initial stop. Unrounded rps × qty then money quantize. |
| 53 | Explicit $ risk | **PASS** | Authoritative; stop-derived preserved. |
| 54 | R P&L basis | **PASS** | NET when fees known (including zero); GROSS when fees null. |
| 55 | R precision | **PASS** | Decimal; store 8 dp; UI 2 dp; aggregates unrounded. |
| 56 | R coverage | **PASS** | R-qualified / closed in cohort. Not signal coverage. |
| 57 | Missing-R taxonomy | **PASS** | INVALID_STOP / MISSING_ENTRY / MISSING_QUANTITY / AMBIGUOUS_SCALE_IN / MANUAL_REVIEW / MISSING_STOP. `NO_SIGNAL_AVAILABLE` is context only. |
| 58 | Pine auto-pop | **PASS** | CONFIRMED planned stop → default initial stop; actual uses avg entry × qty. |
| 59 | Unlink / relink | **PASS** | Stale `PINE_SIGNAL` not reused after unlink. Manual preserved. |
| 60 | Dollar expectancy | **PASS** | Sum effective P&L / closed count (BE in denom). |
| 61 | R expectancy | **PASS** | Sum R / R-qualified = Average R. |
| 62 | Median R | **PASS** | Exact Decimal; even → mean of middle two. |
| 63 | Avg winning / losing R | **PASS** | R>0 / R<0; BE excluded; loser stays negative. |
| 64 | Dollar PF | **PASS** | No trades NULL; no winners 0; no losses NULL + `NO_LOSSES`. No Infinity JSON. |
| 65 | R PF | **PASS** | Same semantics on R values. |
| 66 | Payoff ratios | **PASS** | |
| 67 | Real equity baseline | **PASS** | Pre-period = selected account(s) only. Direction/ticker/strategy/source do **not** rewrite opening equity. Plan wording superseded. |
| 68 | Selected Cohort Drawdown | **PASS** | Labeled. Sequence uses current filters. |
| 69 | Account drawdown | **PASS** | Dashboard uses explicit dashboard filters; no hidden strategy filters. |
| 70 | Equity-at-entry no lookahead | **PASS** | `exit_time < entry_time`. Same timestamp excluded. |
| 71 | Account isolation | **PASS** | |
| 72 | Risk % equity | **PASS** | NULL if starting equity missing or ≤0. No invented default. |
| 73 | Multi-account risk % | **PASS** | Per-trade uses that trade’s account equity. |
| 74 | Realized equity order | **PASS** | `exit_time_utc`, then trade id. |
| 75 | Drawdown $ | **PASS** | ≤0; max is most negative. |
| 76 | Drawdown % | **PASS** | Only with valid starting equity. |
| 77 | R drawdown | **PASS** | Independent of equity. |
| 78 | Duration label | **PASS** | **Calendar Days Underwater**. Compat fields still named `*_trading_days` but `duration_label` is calendar. Not exchange-session counting. |
| 79 | Current drawdown | **PASS** | CURRENT while underwater. |
| 80 | Streaks | **PASS** | BE breaks both; same Dashboard tolerance. |
| 81 | Loss Beyond Initial Risk | **PASS** | Default R < −1.05; `LTA_LOSS_BEYOND_R_THRESHOLD`. Not “rule violation”. |
| 82 | 2R+ / 3R+ | **PASS** | Unrounded R. |
| 83 | RISK section | **PASS** | Infrastructure always on; empty cohort: “No R-qualified trades in current cohort”. |
| 84 | R metrics in registry | **PASS** | Average R, Total R, R Profit Factor, R Coverage on all report dimensions. |
| 85 | Per-bucket R coverage | **PASS** | Tooltip: Trades \| R-qualified \| Coverage. |
| 86 | Risk bucket boundaries | **PASS** | Inclusive lo, exclusive hi; last open. R outcome same. |
| 87 | R outcome retrospective | **PASS** | Description + no PRE-ENTRY badge. |
| 88 | Dashboard R summary | **PASS** | Same `build_advanced_analytics` / expectancy helpers. Average R card added. |
| 89 | Equity chart modes | **PASS** | P&L ≠ Equity ≠ R. |
| 90 | Drawdown chart modes | **PASS** | $ / % (disabled without equity) / R. |
| 91 | /risk coverage | **PASS** | Closed, R-qualified, coverage, reasons, source mix, links to missing. |
| 92 | Trades table | **PARTIAL** | Initial Risk, R, Has Risk / Missing Risk, `r_min`/`r_max`. Risk % column not on the list (detail has it). |
| 93 | Trade detail planned vs actual | **PASS** | Allowed risk labeled as budget, not 1R. |
| 94 | Source comparison | **PASS** | De-emphasized; Step 6 skipped; AUTO ordinary source. |
| 95 | 10k performance | **PARTIAL** | `/api/reports` 10k trades **< 5s** after O(n log n) equity-at-entry. RiskService 400 trades ~6.7s. Full 10k signal+30k event bench not run. |

---

## STEP 5 ↔ STEP 7 integration

| Check | Result |
|-------|--------|
| Confirmed Signal → Risk recalc | **PASS** |
| Later ENTRY → Risk recalc without relink | **PASS** |
| Signal unlink clears PINE_SIGNAL authority | **PASS** |
| Manual override survives signal reprocess | **PASS** |
| Old strategy version risk isolated | **PASS** |
| Strategy coverage ≠ R coverage | **PASS** |
| §96 planned 100 / actual 100 / allowed 100 | **PASS** |
| §97 planned 100 / actual 150 | **PASS** |
| §98 SHORT orientation | **PASS** |

---

## DATABASE

| Object | Status |
|--------|--------|
| signals | Present; unique `signal_id`; indexes ticker/entry, strategy, version, origin, match_status |
| signal_events | Present; unique `event_fingerprint`; FK → signals CASCADE |
| signal_event_conflicts | Present; incoming raw preserved |
| trade_signal_links | Present; unique (trade, signal); FK trades/signals CASCADE |
| pine_import_batches / pine_import_errors | Present |
| trade_risk | 1:1 unique `trade_id`; FK CASCADE |
| risk_audit_log | Present; FK CASCADE |
| FK: delete Trade | Does **not** delete Signal; link + trade_risk cascade. Tested. |
| FK: delete Signal | Events/links cascade. |
| Migration | `create_all` + `migrate.py` additive columns + trade_risk backfill. Restart-safe (IF NOT EXISTS / column probes). |
| Docs status | Plans no longer say “Plan only”. |

---

## Performance

Measured on this machine (SQLite test DB):

| Path | N | Time |
|------|---|------|
| Pine parse | 400 signals / 1,200 events | 123 ms |
| Preview (no mutate) | same | 155 ms |
| Import + merge + match | same | 2.7 s |
| RiskService.recalculate_many | 400 trades | 6.7 s |
| `get_reports` after that | 400+ | 179 ms |
| `get_reports` 10k trades (no risk/signals) | 10,000 | **< 5 s** (suite assertion) |

Fixes this audit: equity-at-entry uses bisect (was O(n²) scan); Graphs skip equity map when no risk amount. Signal/risk annotation uses batched `IN` queries (no per-trade signal lookup).

---

## TESTS

| Suite | Result |
|-------|--------|
| Backend (full) | **281 passed** |
| Frontend vitest | **25 passed** (graphFilters 13, money 12) |
| Production build | **PASS** (`tsc && vite build`) |
| Step 1 / 2 / 2.5 | `test_step_1_to_2_5_audit` 20, reconstruction 28, imports/TV parsers — included in 281 |
| Step 3 | `test_reports_graphs` 28, `test_step_3_analytics` 17, `test_dashboard` 28 |
| Step 4 | `test_step3_4_audit` 24, market_* 12 |
| Step 5 | `test_step_5_signals` 23, `test_pine_signallog_observer` 2 |
| Step 7 | `test_step_7_risk` 20 |
| Step 5↔7 | `test_step_5_7_integration` 9 |
| Perf smoke | `test_step_5_7_performance` 1 |

### Step 5 test map

parser, schema vs strategy version, signal ID collisions, ARMED/ENTRY/EXIT same ID, DST timestamps, preview, out-of-order, EXIT vs ENTRY snapshot, duplicate reimport, payload conflict, partial 9+1, legacy synthetic IDs, never EXPLICIT on legacy, matcher ticker/direction, AUTO unique/ambiguous, MANUAL suggested, reject, EXPLICIT_ID confirm, untraded, fingerprint, Graphs CONFIRMED + gap/RVOL keys, mixed versions, Pine observer.

### Step 7 test map

LONG, SHORT, invalid stop, scale-in, manual override, explicit amount, R NET/GROSS, expectancy/PF/payoff/R, PF special cases, R drawdown, equity-at-entry, same-timestamp excluded, multi-account, risk % null/with equity, **real baseline ignores direction filter**, missing-R reasons, graph Average R, loss beyond −1.05, cache invariant.

---

## Real data

| Check | Status |
|-------|--------|
| ≥5 real Pine signals vs Logs | **USER-DATA VALIDATION PENDING** — no imported Pine logs / `.sqlite` journal in the workspace |
| ≥5 real trades recalculated by hand | **USER-DATA VALIDATION PENDING** |
| TRADE_RECORD / AUTO_TRADE_RECORD samples | **None in repo** — do not claim full legacy support |

---

## Fixes made this audit

- Scale-in risk: multiply **unrounded** risk/share × quantity, then quantize money (stops invented cents).
- Dashboard now exposes `loss_beyond_initial_risk`, R PF, R payoff, R drawdown (was computed then dropped).
- Trading Edge shows **Average R** from the same backend stats.
- Equity-at-entry batch is O(n log n) via bisect; Graphs do not compute equity for trades without risk.
- Aggregation `r_multiple` uses `getattr` so Step 3 namespace fixtures still work.
- Pine observer regression: trading-state assignments must match CURRENT.
- EXPLICIT_ID confirm test; AUTO CONFIRMED does not auto-suggest MANUAL (Step 6 pairing skipped).
- `/signals` pagination + ENTRY state filter; trade list `r_min`/`r_max`; drawdown $/%/R.
- Plan docs: Signal ID ARMED-bar rule; real equity baseline supersession; `risk_audit_log` resolved; status Implemented/Audited.

---

## OPEN ENDS

| Item | Class |
|------|--------|
| No user Pine logs in workspace — cannot validate 5 live signals | **USER-DATA VALIDATION** |
| No live journal — cannot hand-check 5 real R/% figures | **USER-DATA VALIDATION** |
| TRADE_RECORD / AUTO_TRADE_RECORD samples absent | **USER-DATA VALIDATION** |
| Automatic EXPLICIT_ID from trade-carried Signal ID (trades have no Pine ID field) | **DEFERRED BY DESIGN** until a source emits it |
| Opening Fade typed dimensions | **DEFERRED BY DESIGN** until Pine emits `OPENING_FADE` fields |
| Full 10k signals / 30k events bench | **NON-BLOCKING** (400×3 + 10k reports measured) |
| Trades table missing Risk % column | **NON-BLOCKING** (detail + Graphs have it) |
| Legacy `apply_risk_to_trade` cache-only helper | **NON-BLOCKING** (not on API/import path) |
| Drawdown duration is calendar days, not exchange sessions | **DEFERRED BY DESIGN** (labeled correctly) |
| Compat JSON fields `max_duration_trading_days` still exist | **NON-BLOCKING** (`duration_label` is authoritative) |
| Step 6 MANUAL-vs-AUTO pairing analytics | **DEFERRED BY DESIGN** (skipped) |
| Step 8 / Research Lab | **DEFERRED BY DESIGN** (not in this audit) |

No **BLOCKING** items remain.

Step 5 and Step 7 are **implemented and audited**. They are not claimed “complete against live user data” until the USER-DATA VALIDATION rows are filled.

**Do not begin Step 8 as part of this audit.**
