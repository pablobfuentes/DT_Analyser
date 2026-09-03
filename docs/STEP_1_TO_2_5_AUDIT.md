# Steps 1 → 2.5 Implementation Audit

**Date:** 2026-09-02  
**Scope:** Verify current code against `docs/STEP_1_PLAN.md`, `docs/STEP_2_PLAN.md`, `docs/STEP_2_5_PLAN.md`. Not a redesign.  
**Verdict:** **PASS with non-blocking open ends.** No remaining blockers from §49.

This report is based on inspection of live code, SQLAlchemy models, `app/db/migrate.py`, real TradingView CSVs under `docs/TradeData/` and `backend/tests/fixtures/`, and a full test run (202 backend / 20 frontend).

**Authoritative reconstruction:** Step 2.5 signed-position, position-cycle weighted average in `app/services/trade_reconstruction.py`. Step 1 LONG FIFO is obsolete. Day-to-day import and `rebuild_trades` both call `TradeRebuildService`.

---

## Fingerprints (current fields)

**Execution** (`app/services/deduplication.py`):

- If `external_execution_id` is set: `SHA-256(account_id | external_execution_id)`
- Else: `SHA-256(account_id | ticker | side | execution_time_utc.isoformat() | quantity | price | order_id or "")`
- Unique: `(account_id, execution_fingerprint)`

TradingView Order History parser sets `external_execution_id = Order ID`. Activity Log uses the order id parsed from “has been executed” lines. Same Order ID → same fingerprint → overlapping Order History + Activity Log does not duplicate fills.

Identical fills with **no** order/external id collapse (required for overlapping-export idempotency). Distinct Order IDs never collapse even if ticker/time/qty/price match.

**Trade:**

- If `external_trade_id` is set: `SHA-256(account_id | external_trade_id)`
- Else: `SHA-256(account_id | source_type | ticker | direction | entry ISO | exit ISO or "" | quantity | avg_entry | avg_exit or "")`
- Unique: `(account_id, trade_fingerprint)`

Rebuild deletes trades in scope then inserts; fingerprints identify the cycle, not a FIFO lot.

---

## TradingView column variants currently recognized

Aliases in `app/importers/aliases.py` (headers normalized: trim, lower, `_` → space):

| Logical field | Aliases |
|---------------|---------|
| ticker | ticker, symbol, instrument, sym |
| side | side, action, buy/sell, direction |
| order type | type, order type, ordertype |
| status | status, state, order status |
| quantity | quantity, qty, shares, size, amount |
| price | fill price, price, execution price, avg price, fillprice |
| fees | fees, fee, commission |
| timestamp | closing time, close time, execution time, fill time, date/time, datetime, date time, placing time, place time, timestamp, time, date |
| order id | order id, order_id, orderid |
| execution id | execution id, execution_id, trade id, id |
| pnl | p&l, pnl, profit, net p&l, net pnl, pl |
| entry time | entry time, entry date, entry datetime, date/time |
| exit time | exit time, exit date, exit datetime |
| entry price | entry price, entry, avg entry price |
| exit price | exit price, exit, avg exit price |
| trade # | trade #, trade#, trade number |
| activity message | text, message, description, event, details |

**Real files validated:**

- Order History: `Symbol,Side,Type,Quantity,Limit price,Stop price,Fill price,Status,Commission,Placing time,Closing time,Order ID,...`
- Activity Log: `Time,Text`
- Strategy Tester fixture: `Symbol,Entry Time,Exit Time,Entry Price,Exit Price,Qty,P&L,Trade #`

---

## Requirement-by-requirement

### STEP 1 — Import architecture

| Requirement | Planned | Actual | Status | Evidence | Fix performed | Tests |
|-------------|---------|--------|--------|----------|---------------|-------|
| Layered FastAPI / service / importers / models / schemas | API → ImportService → parsers → SQLAlchemy / Pydantic | Present under `backend/app/{api,services,importers,db,schemas,utils}` | **PASS** | `main.py`, `api/imports.py`, `services/import_service.py` | None | Existing import tests |
| Decimal money | Decimal everywhere; NUMERIC SQLite | `Numeric(18,6)` on qty/price/fees/P&L; `app/utils/money.py` | **PASS** | models; no `float()` in reconstruction | None | penny_stock, decimal_precision |
| Timezone utils | zoneinfo; NY / Mexico City / UTC | `app/utils/timezones.py` | **PASS** | `ZoneInfo`; no hard-coded offsets | DST/premarket tests added | `test_timezones.py` |
| Raw row preservation | `executions.raw_row_json` mandatory | NOT NULL Text; parser `raw_row` | **PASS** | `Execution.raw_row_json`; rebuild does not rewrite executions | None | `test_rebuild_does_not_delete_executions` |
| Preview vs commit | Preview: hash, detect, sample, TZ; no trade/execution writes | Preview writes hash-keyed temp file only; `preview_file` has no DB writes | **PASS** | `api/imports.py` preview; commit creates `import_batch` | Hash-dir sanitization + 24h cleanup | `test_preview_does_not_mutate_persistent_data`, `test_uploads.py` |
| Preview TZ | Ambiguous naive timestamps require user TZ | `timezone_status=REQUIRES_USER_INPUT`; commit raises `TimezoneRequiredError` | **PASS** | manual/strategy/activity parsers | Structured 422 via `ImporterError` handler | `test_no_timezone_*`, TV paper preview |
| Commit transactional | batch, parse, dedupe, reconstruct, row errors, status | Single session; rollback on crash; SUCCESS/PARTIAL/FAILED | **PASS** | `ImportService.commit_import` | Dead Step 1 persist path removed; import now always rebuilds | import + paper tests |
| File hash | Same SHA-256 warns, still processes; record-level idempotency | Preview warns if hash exists; commit never rejects on hash | **PASS** | preview queries `import_batches.file_hash` | Warning added | duplicate file tests |
| Same file twice | 0 new execs/trades, no corruption | Duplicate fingerprints skipped; rebuild no-ops if no new execs | **PASS** | `test_duplicate_file_import`, TV paper duplicate | Session allocation persist fix (see 2.5) | those tests |
| Overlapping export | 1–5 then 1–8 → 8 unique, no double P&L | Exec fingerprints skip overlap; rebuild from full ticker history | **PASS** | `overlapping_exec_5/8.csv` | Allocation persist fix | `test_overlapping_executions_1_to_5_then_1_to_8` |
| Temp preview lifecycle | 24h retention implemented, not only documented; expired → re-upload; no delete outside upload dir | `cleanup_stale_uploads` on save/startup; hash-only dirs; `PREVIEW_EXPIRED` | **PASS** | `init_data.py`, `config.upload_retention_hours=24` | Implemented | `test_uploads.py` |
| Path safety | Filename cannot escape temp dir | `sanitize_upload_filename` + hash regex on `get_upload_path` | **PASS** | `init_data.py` | Implemented | `test_save_upload_cannot_escape` |
| Format detection | Order History vs Strategy Tester vs Activity Log; no silent ST misclass; ambiguous → don’t guess | ST requires full entry/exit set; OH signature capped; two high scores → `AMBIGUOUS_FORMAT` | **PASS** | `detector.py`, `tradingview_strategy.py` | Strengthened ST heuristics | lookalike + real OH tests, `test_three_formats.py` |
| Activity Log role | Document actual use | Optional **alternative execution source**. Side from “Call to place market order”. After Order History, same Order IDs duplicate-skip. Not used for reconstruction math, fee fill-in, or timestamp repair of Order History. | **PASS** | `tradingview_activity_log.py`; Import page note | UI/docs note | `test_tv_activity_log.py` |
| API error shapes | Structured codes | `ImporterError.to_dict()` `{error, message, ...}`; FastAPI handler returns that JSON (400/422) | **PASS** | `exceptions.py`, `main.py` | Handler so frontend is not forced to unwrap `detail` for importer errors | timezone + unknown format tests |
| Schema / indexes | starting_equity, allocated_quantity, resolved_at, fingerprints unique, trade indexes | Models + `migrate.py` additive ALTERs; `ix_trades_account_status` added | **PASS** | `migrate.py`, models | Composite account/status index | implicit via create_all tests |
| Referential integrity | Rebuild must not delete executions; no orphan allocs; SQLite FK on | FK pragma on engine and tests; rebuild deletes allocs then trades only | **PASS** | `session.py`, rebuild | ORM-delete + expunge ghosts; link by `Execution.id` | FK + rebuild execution tests |
| Decimal audit | No float money in core recon | Reconstruction/dashboard/money.py use Decimal. Frontend Number is display-only. `float()` only in later report/excursion display helpers | **PASS** | grep `float(` under `app/` | None | penny + fee Decimal tests |

**Step 1 reconstruction (§E FIFO):** **OBSOLETE / SUPERSEDED** by Step 2.5. Note added at top of `STEP_1_PLAN.md`. Production has one engine; leftover `_persist_reconstructed_trade` removed.

---

### STEP 2 — Dashboard

| Requirement | Planned | Actual | Status | Evidence | Fix performed | Tests |
|-------------|---------|--------|--------|----------|---------------|-------|
| CLOSED-only P&L | Open counted separately; no unrealized leak | `build_closed_trades_query` status=CLOSED; open_count separate | **PASS** | `dashboard_service.py` | None | `test_open_trades_excluded` |
| Effective realized P&L | Prefer net; fallback gross; warn if fees missing | `effective_realized_pnl`; missing-fees warning | **PASS** | `utils/analytics.py` | None | missing fees + prefers net |
| Win rate | wins/(wins+losses); BE excluded; $0.01 configurable; one implementation | `classify_outcome` + `win_rate_pct`; used by dashboard, graphs, risk | **PASS** | analytics, reports, dashboard | None | BE tests; reports use same helpers |
| Analytics TZ | America/New_York; UTC in DB; zoneinfo DST | `ANALYTICS_TIMEZONE`; `ny_date_from_utc` / bounds | **PASS** | config + analytics | None | `test_daily_aggregation_ny_timezone`, DST |
| Starting equity | Nullable; no fake default; multi-account only if all set | `accounts.starting_equity` nullable; unavailable if any missing | **PASS** | Account model, `_equity_section` | None | starting equity tests |
| Filtered equity | Do not reset to raw starting if prior realized P&L exists; reuse Step 7 baseline | `_equity_section` uses `equity_baseline` / `pre_period_realized_pnl` | **PASS** | `drawdown.py` + dashboard | Wired dashboard card to Step 7 helper | `test_filtered_equity_uses_pre_period_baseline` |
| Filters | date/account/source/direction/ticker; URL; all widgets one endpoint | `GET /api/dashboard`; frontend URL sync | **PASS** | DashboardPage + filters | None | per-filter tests |
| AUTO source | Remain valid; no new pair-comparison feature | Simple `source_comparison` kept; no new MANUAL vs AUTO product | **PASS** | dashboard source_comparison | None | manual/auto filter tests |
| Daily metrics | NY date with ≥1 closed trade; green/red/BE vs tolerance | `_classify_day` uses breakeven tolerance | **PASS** | dashboard_service | None | green/red test |
| Recent trades | Last 10 CLOSED, exit DESC, ID tie-break, link to detail | Sort `(exit_time, id)` DESC; link `/trades/:id` | **PASS** | dashboard + RecentTrades.tsx | ID tie-break | `test_recent_trades_id_tie_break` |
| Calendar heatmap | Same daily P&L; if one month, document | Uses `daily[].net_pnl`; **one month: earliest date in payload** | **PASS** | CalendarHeatmap.tsx comment | Documented, not redesigned | visual/component only |

---

### STEP 2.5 — Reconstruction

| Requirement | Planned | Actual | Status | Evidence | Fix performed | Tests |
|-------------|---------|--------|--------|----------|---------------|-------|
| One engine; no leftover FIFO | Search FIFO / long_lots / unsupported short | No production hits; dead persist path removed | **PASS** | grep `backend/app` | Removed `_persist_reconstructed_trade` | suite still green |
| Signed position | >0 LONG, 0 FLAT, <0 SHORT; generic BUY/SELL | `_resolve_side` + signed `position_qty` | **PASS** | `trade_reconstruction.py` | None | step 2.5 unit tests |
| Flips | Split allocations; one Execution row; two trade_executions | Internal split; `allocated_quantity`; no synthetic executions | **PASS** | reconstructor + TradeExecution | Persist-by-execution-id | flip + FLYE/SSM |
| Allocated qty | Decimal, never 0/null; sum ≤ execution.qty; flip sum = qty | NUMERIC NOT NULL; backfill in migrate.py | **PASS** | model + migrate | Identity-map persist bug fixed | `test_allocation_sum_does_not_exceed_execution_qty` |
| Flip fees | Proportional by allocated qty; Decimal | `allocate_fee`: `fees * portion / ex.quantity` | **PASS** | reconstructor | Exact test added | `test_flip_fee_allocation_proportional` → $1.00 + $0.50 |
| Weighted avg / P&L | LONG (exit−entry)×qty; SHORT (entry−exit)×qty; net = gross − fees | `calculate_gross_pnl` / `calculate_net_pnl` | **PASS** | money.py | None | short/long/flip PnL tests |
| Cycle quantity | Opened qty, not turnover | CLOSED: Σ entry fills. OPEN: remaining exposure (`entry−exit`) | **PASS** (OPEN remaining is intentional for open size) | `emit_closed_cycle` / `emit_open_cycle` | Documented | scale-in closed = 200 |
| Deterministic same-timestamp order | Prefer export row/id, not DB scan or lex order_id | Sort `(time, row_number, external_id, order_id)`; rebuild `row_number=Execution.id` | **PASS** | `_execution_sort_key` | Row/id before order_id string | `test_same_timestamp_uses_row_order_not_order_id` |
| Truncated history | Do not silently invent SHORT from first SELL | Assume FLAT at earliest persisted fill; first SELL/SELL_SHORT → **UNKNOWN_OPENING_POSITION** warning (not a hard error); overlapping earlier BUY rebuilds and resolves | **PASS** | reconstructor warnings; import_errors; dashboard warning | Implemented | truncated history + PETZ still 0 hard errors |
| Open trade persistence | Normal import persists OPEN; later close resolves | Import → `TradeRebuildService` persists OPEN+CLOSED | **PASS** | import_service | Was already rebuild-based; allocation persist fixed | `test_open_trade_persists_then_closes` |
| Incremental vs rebuild parity | Same trades/P&L/allocations except DB ids | Same engine; snapshot compare | **PASS** | rebuild from executions | Ghost TradeExecution merge bug | `test_incremental_import_matches_rebuild` |
| Rebuild CLI | `--account-id --ticker --all --dry-run`; dry-run no mutate; transactional; idempotent | `app/cli/rebuild_trades.py` | **PASS** | CLI + service | Error-resolve scoping | dry-run + idempotent tests |
| Import error resolution | Only fixed TradeReconstructionError; not parser/TZ/malformed | Rebuild resolves TRE only if rebuild errors==0, ticker-scoped; never InvalidExecutionError | **PASS** | `_resolve_errors` | Was resolving all TRE unconditionally | `test_rebuild_does_not_resolve_parser_errors` |
| PETZ/AEHL/SSM/FLYE | 0 SHORT/flip reconstruction **errors** | Hard errors 0; PETZ/AEHL SELL-first carry UNKNOWN_OPENING_POSITION **warnings** (fixtures are complete shorts, but policy flags any SELL-first) | **PASS** | regression fixtures | Warning is non-fatal | `test_step_2_5_reconstruction.py` |
| 3-day overlapping workflow | Day1 not duplicated; Day2 added; opens update; dashboard from CLOSED | Synthetic 3-day CSV in audit test | **PASS** | audit test | Same persist fix | `test_incremental_import_matches_rebuild` |
| Performance 10k | Practical benchmark | reconstruct **0.143s**; persist **1.341s**; rebuild **6.764s**; dashboard **0.474s**; 5000 trades | **PASS** | `test_10k_execution_benchmark` | None required | that test |
| UI warnings | Meaningful; not stale Step 1 flip errors | Fees, P&L mismatch, OPEN excluded, missing equity, UNKNOWN_OPENING_POSITION | **PASS** | dashboard warnings | Opening-position warning | dashboard tests |

**Mismatch flags** for LONG/SHORT/partial/flip/scale: strategy-tester path compares calculated vs `source_reported_pnl`. Reconstructed manual trades typically have no source P&L (Order History has no round-trip P&L column). Logic is shared `pnl_mismatch()`.

---

## Data integrity snapshot (from tests / design)

| Item | Result |
|------|--------|
| Executions | Authoritative; never deleted by rebuild |
| Trades | Rebuilt from executions (OPEN+CLOSED) |
| Open trades | Persisted on incomplete cycles |
| Closed trades | Position cycle when signed qty returns to 0 |
| Allocations | Linked by execution id; flip may use two rows; sum ≤ source qty |
| Unresolved reconstruction errors | Only genuine invalid data; SHORT/flip are not errors |
| UNKNOWN_OPENING_POSITION | Warning while ticker history still starts with SELL |
| P&L mismatch flags | Strategy tester / source_reported_pnl path |

---

## Fixes made in this audit

1. **UNKNOWN_OPENING_POSITION** for SELL-first ticker history (non-fatal warning; resolves when earlier BUY arrives).
2. **Same-timestamp ordering** uses source row / `executions.id` before lexicographic order id.
3. **Rebuild allocation persist:** stop `merge()` onto identity-map ghosts after SQLite PK reuse; ORM-delete trades; link allocations by `Execution.id`; `sqlite_autoincrement` on `trades`.
4. **Rebuild error resolve:** only `TradeReconstructionError` when rebuild has 0 recon errors; never parser errors; ticker-scoped; opening warnings resolved only when first fill is no longer SELL-family.
5. **Removed leftover Step 1 persist path**; import always uses `TradeRebuildService`.
6. **Preview:** duplicate file-hash warning; 24h hash-dir cleanup; filename/path sanitization; expired hash → `PREVIEW_EXPIRED`.
7. **Detector:** Strategy Tester needs full entry/exit columns; Order History signature cannot win as ST; `AMBIGUOUS_FORMAT` when two parsers are both confident.
8. **Dashboard equity** uses Step 7 `equity_baseline`; recent trades ID tie-break; opening-position warning.
9. **API:** `ImporterError` JSON body `{error, message, ...}`.
10. **Docs:** Step 1 FIFO superseded; Activity Log optional; truncated-history policy; calendar one-month behavior.

---

## Tests

| Suite | Result |
|-------|--------|
| Backend `pytest` | **202 passed** |
| Frontend `vitest` | **20 passed** |
| Frontend `tsc && vite build` | **PASS** |
| 10k executions | reconstruct 0.143s / persist 1.341s / rebuild 6.764s / dashboard 0.474s |

Browser E2E of the Import page copy change was not run (no browser session in this audit). Behavior is covered by backend tests.

---

## Final scores

### STEP 1

- Requirements audited: architecture, preview/commit, hash, overlap, fingerprints, raw rows, TZ, temp files, TV detection, ST detection, Activity Log, schema, FK, Decimal, API errors, security
- **PASS:** all current (non-obsolete) requirements after fixes
- **PARTIAL:** none remaining that affect correctness
- **FAIL:** none
- **OBSOLETE/SUPERSEDED:** Step 1 LONG FIFO reconstruction; “SHORT not supported” / flip-as-error

Real TradingView formats: Order History, Activity Log, Strategy Tester — classified correctly.

Duplicate import: 0 new executions/trades.  
Overlapping 5 then 8: 8 unique executions, 4 closed trades, no P&L double count.  
Timezone: offset, NY/Mexico City/UTC, DST, premarket, regular session — pass.  
Preview mutation: no persistent trade/execution writes.  
Strategy Tester detection: missing entry/exit pair cannot exceed threshold; lookalike OH not classified as ST.

### STEP 2

- **PASS:** CLOSED scope, net/gross fallback, win rate, NY TZ, starting equity, filtered baseline, filters, AUTO source, daily metrics, recent trades, calendar (one month documented)
- **PARTIAL:** none blocking
- **FAIL:** none

### STEP 2.5

- **PASS:** LONG, SHORT, both flip directions, scale-in/out, allocation invariants, proportional fees, same-timestamp order, open persistence, incremental=rebuild, PETZ/AEHL/SSM/FLYE (0 hard SHORT/flip errors), resolved-error scoping
- **PARTIAL:** none blocking
- **FAIL:** none

---

## Open ends

| Item | State | Notes |
|------|-------|--------|
| First **BUY** in a truncated export could cover a pre-file SHORT | **DEFERRED BY DESIGN** | Conventional default remains “earliest BUY opens LONG”. Only first SELL is flagged; documented in `TRADE_RECONSTRUCTION.md`. |
| Identical fills with no order/external id collapse | **DEFERRED BY DESIGN** | Required for overlapping CSV idempotency. TV paper always has Order ID. |
| Calendar heatmap shows only the month of the earliest daily row | **DEFERRED BY DESIGN** | Same daily P&L source; not a second calculator. Multi-month calendar would be a later UX change. |
| `AmbiguousColumnError` almost never fires | **NON-BLOCKING** | First matching alias wins (needed because OH has Placing time + Closing time). `AMBIGUOUS_FORMAT` is parser-level. |
| Rebuild persist still inserts trades/allocations in a Python loop | **NON-BLOCKING** | 10k exec / 5k trades rebuild 6.8s; no N+1 query storm on dashboard aggregations (one closed-trade query). |
| No Alembic; `migrate.py` additive ALTERs + `create_all` | **NON-BLOCKING** | Safe for local SQLite; does not destroy data. |
| OPEN `trade.quantity` after partial exit is remaining size, not cycle opened size | **NON-BLOCKING** | CLOSED cycles use opened qty. OPEN remaining is the live position. |
| UNKNOWN_OPENING_POSITION on genuine shorts (PETZ/AEHL) | **DEFERRED BY DESIGN** | Warning stays until history no longer starts with SELL. Not a reconstruction error; PETZ/AEHL still import with `errors==0`. |
| Activity Log unused once Order History exists | **DEFERRED BY DESIGN** | Optional duplicate source; not required for reconstruction. |

No **BLOCKING** open ends remain.

---

## Policy notes (must not be re-litigated as “Step 1 FIFO”)

1. Trade reconstruction was superseded by Step 2.5 signed-position, position-cycle weighted-average reconstruction.
2. Step 7 `equity_baseline` supersedes older dashboard equity that added filtered P&L to raw starting equity.
3. Reconstruction assumes FLAT only at the **earliest persisted execution** for `(account, ticker)`. A first SELL is a SHORT **and** an `UNKNOWN_OPENING_POSITION` warning. Import earlier history to reclassify.
4. Stop after this audit; do not start Step 8 from this workstream.
