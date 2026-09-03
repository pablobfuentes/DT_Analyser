# Step 1 Plan — Local Trader Analyzer

> **Supersession:** Trade reconstruction described in §E (LONG FIFO / flip-as-error) is **not** the production engine. **Step 2.5 superseded Step 1 reconstruction** with signed-position, position-cycle weighted-average reconstruction. See `docs/STEP_2_5_PLAN.md` and `docs/TRADE_RECONSTRUCTION.md`.
>
> **Equity curves:** Step 7 `equity_baseline` (account starting equity + prior realized P&L) supersedes any older dashboard logic that reset filtered-period equity to raw `accounts.starting_equity`.


## A. Proposed Architecture

```
local-trader-analyzer/
├── backend/          # FastAPI + SQLAlchemy + importers
├── frontend/         # React + Vite (minimal UI)
└── docs/
```

**Layers:**

1. **API** (`app/api/`) — HTTP endpoints, request validation via Pydantic v2.
2. **Services** (`app/services/`) — import orchestration, deduplication, trade reconstruction.
3. **Importers** (`app/importers/`) — modular CSV parsers with confidence scoring.
4. **DB** (`app/db/`) — SQLAlchemy 2.x models, session management, init/migrations.
5. **Schemas** (`app/schemas/`) — API request/response models.
6. **Utils** (`app/utils/`) — hashing, timezones, money (Decimal).

**Import pipeline:**

```
Upload CSV → SHA-256 hash → Detector (all parsers) → Best parser or UNKNOWN
  → Preview (no DB writes) → User confirms timezone/account
  → Commit (transactional) → Parse rows → Dedupe executions/trades
  → Reconstruct trades (manual) OR direct trade insert (strategy tester)
  → Persist + import_errors for bad rows
```

**Technology choices:**

- SQLite for local persistence; file at `backend/data/trader_analyzer.db`.
- Polars for fast CSV read and column detection.
- Decimal everywhere for money; NUMERIC in SQLite.
- Preview stores file temporarily on disk keyed by hash; commit re-reads same file.

---

## B. Database Schema

### accounts
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| name | TEXT UNIQUE | |
| source | TEXT | TRADINGVIEW_MANUAL, TRADINGVIEW_AUTO, etc. |
| currency | TEXT | default USD |
| is_simulated | BOOLEAN | |
| created_at, updated_at | DATETIME UTC | |

### import_batches
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| filename | TEXT | |
| file_hash | TEXT | SHA-256, indexed |
| source_type | TEXT | |
| parser_name, parser_version | TEXT | |
| account_id | FK accounts | |
| import_started_at, import_completed_at | DATETIME | |
| row_count_* | INTEGER | raw, valid, imported, duplicate, error |
| status | TEXT | PREVIEW, PROCESSING, SUCCESS, PARTIAL, FAILED |
| error_message | TEXT nullable | |
| metadata_json | TEXT | timezone choice, column mapping, etc. |

### executions
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| account_id, import_batch_id | FK | |
| external_execution_id | TEXT nullable | |
| execution_fingerprint | TEXT UNIQUE per account | SHA-256 of normalized fields |
| ticker, side | TEXT | BUY, SELL, SELL_SHORT, BUY_TO_COVER, UNKNOWN |
| execution_time_utc | DATETIME | canonical |
| execution_time_original, timezone_original | preserved | |
| quantity, price, fees | NUMERIC | Decimal |
| order_id | TEXT nullable | |
| raw_row_json | TEXT | mandatory |
| created_at | DATETIME | |

**Unique constraint:** `(account_id, execution_fingerprint)`

### trades
| Column | Type | Notes |
|--------|------|-------|
| id | INTEGER PK | |
| account_id | FK | |
| source_type | TEXT | |
| external_trade_id | TEXT nullable | |
| trade_fingerprint | TEXT | for dedup |
| ticker, direction | TEXT | LONG, SHORT |
| entry_time_utc, exit_time_utc | DATETIME | |
| avg_entry_price, avg_exit_price | NUMERIC | |
| quantity | NUMERIC | |
| gross_pnl, fees, net_pnl | NUMERIC nullable | |
| source_reported_pnl | NUMERIC nullable | from CSV |
| pnl_mismatch_flag | BOOLEAN | if calculated ≠ source beyond tolerance |
| holding_seconds | INTEGER nullable | |
| status | TEXT | OPEN, CLOSED |
| raw_row_json | TEXT nullable | for strategy tester direct imports |
| created_at, updated_at | DATETIME | |

**Unique constraint:** `(account_id, trade_fingerprint)`

### trade_executions
| trade_id, execution_id | composite PK |
| role | ENTRY, EXIT, ADJUSTMENT |

### import_errors
| import_batch_id, row_number, error_type, message, raw_row_json |

**Indexes:** file_hash, account_id on executions/trades, ticker, entry_time_utc.

---

## C. Import Flow

### POST /api/imports/preview
1. Save uploaded file to temp dir; compute SHA-256.
2. Run `detector.detect(file)` → list parser scores.
3. If best confidence < threshold → return `UNKNOWN_FORMAT` with diagnostics.
4. Selected parser runs `preview(file, timezone?)` → normalized records (max 10 sample).
5. Check timezone: if timestamps lack offset and no timezone in CSV → `timezone_status: REQUIRES_USER_INPUT`.
6. Return preview payload; **no DB writes**.

### POST /api/imports/commit
1. Input: file (or hash reference), account_id, parser_name, timezone, optional column overrides.
2. Begin transaction.
3. Create `import_batch` (status PROCESSING).
4. Parser `parse(file, timezone)` → list of `NormalizedExecution` or `NormalizedTrade`.
5. For each record: dedupe check → insert or skip duplicate.
6. Manual executions → FIFO reconstruction → create/update trades + trade_executions.
7. Strategy trades → insert trade directly (optional synthetic execution link if row has fill detail).
8. Log row-level errors to `import_errors`; update batch counts.
9. Set batch status SUCCESS | PARTIAL | FAILED; commit.
10. Return summary.

---

## D. Duplicate Strategy

**Level 1 — File hash:** Same SHA-256 detected → warn user; still process for new rows in overlapping export.

**Level 2 — Execution fingerprint:**
```
if external_execution_id:
    fingerprint = hash(account_id, external_execution_id)
else:
    fingerprint = hash(account_id, ticker, side, execution_time_utc ISO, quantity, price, order_id or "")
```
Unique constraint on `(account_id, execution_fingerprint)`.

**Level 3 — Trade fingerprint (strategy tester / reconstructed):**
```
if external_trade_id:
    fingerprint = hash(account_id, external_trade_id)
else:
    fingerprint = hash(source_type, ticker, direction, entry_time_utc, exit_time_utc, quantity, avg_entry, avg_exit)
```

**Overlapping CSV scenario:** File 2 contains trades 1–8; trades 1–5 match fingerprints from file 1 → skipped; 6–8 inserted.

---

## E. Trade Reconstruction Algorithm

**OBSOLETE / SUPERSEDED by Step 2.5.** The LONG FIFO queue, `TradeReconstructionError` on flips, and “SHORT not fully supported” behavior below are historical design notes. Production code uses a single `TradeReconstructor` (signed position, position-cycle weighted average). Do not implement FIFO lots.

**Scope:** Per `(account_id, ticker)`, process executions sorted by `execution_time_utc`.

**LONG FIFO queue:**
- `BUY` / `BUY_TO_COVER` → add to open long lots (quantity, price, execution_id, time).
- `SELL` → match against oldest lots (FIFO):
  - Partial exit: reduce lot quantity; accumulate exit weighted average.
  - Full lot consumed: continue to next lot.
  - When total closed quantity for a "trade session" completes (position returns to 0): emit CLOSED trade with weighted avg entry/exit, entry_time = first entry, exit_time = last exit.

**Position flip (BUY 100, SELL 150):**
- Close LONG 100 → emit trade.
- Remaining 50 SELL → attempt SHORT open; if SHORT not fully supported in Step 1, log `TradeReconstructionError` and store remainder in import_errors with raw context (do not corrupt).

**Strategy tester rows:** One row = one round-trip → create `Trade` directly; no artificial execution splitting unless row contains explicit fill columns.

---

## F. Timezone Strategy

1. Parser inspects timestamp columns for embedded offset (`Z`, `+00:00`, `-05:00`).
2. If offset present → parse to UTC; store original string + detected timezone.
3. If no offset → mark `timezone_status: AMBIGUOUS`; preview requires user selection from:
   - `America/New_York`
   - `America/Mexico_City`
   - `UTC`
4. User choice stored in `import_batch.metadata_json`.
5. All canonical times stored as UTC naive datetime (documented convention) or timezone-aware UTC.

**Conservative rule:** Never assume NY time without user confirmation or explicit CSV timezone column.

---

## G. Error-Handling Strategy

**Custom exceptions** (mapped to HTTP 400/422):
- `UnknownCSVFormatError` — no parser above confidence threshold.
- `MissingRequiredColumnError` — required field unmapped.
- `AmbiguousColumnError` — multiple columns match one logical field.
- `TimezoneRequiredError` — commit without timezone when required.
- `TradeReconstructionError` — flip/unsupported pattern.
- `InvalidExecutionError` — bad quantity, price, side.

**Row-level errors:** Catch per row; log to `import_errors`; continue import → PARTIAL status.

**Transactional:** Catastrophic failure (DB error, parser crash) → rollback entire batch.

**API error shape:**
```json
{
  "error": "TIMEZONE_REQUIRED",
  "message": "...",
  "options": ["America/New_York", ...]
}
```

---

## H. Test Plan

| # | Fixture | Assertion |
|---|---------|-------------|
| 1 | simple_long.csv | 1 trade, 2 executions |
| 2 | multi_entry.csv | 1 trade, weighted avg entry |
| 3 | partial_exit.csv | 1 trade, 3 executions |
| 4 | duplicate_file | second import: 0 new trades |
| 5 | overlapping_1 + overlapping_2 | 8 total trades |
| 6 | alias_columns.csv | Symbol/Qty/Fill Price mapped |
| 7 | missing_field.csv | error, no import |
| 8 | unknown.csv | UNKNOWN_FORMAT |
| 9 | no_timezone.csv | REQUIRES_USER_INPUT |
| 10 | strategy_tester.csv | direct trades |
| 11 | pnl_mismatch.csv | pnl_mismatch_flag true |
| 12 | penny_stock.csv | 0.4875 price preserved |
| 13 | malformed_mixed.csv | PARTIAL, some errors |

Run: `cd backend && pytest -v`

---

## I. Unresolved Assumptions

1. **TradingView CSV formats** are approximated in fixtures; real exports may differ — aliases in `aliases.py` are designed for easy extension.
2. **UTC storage:** We store `execution_time_utc` as timezone-aware UTC in Python; SQLite stores ISO strings.
3. **SHORT reconstruction:** Superseded by Step 2.5 signed-position model.
4. **Preview file retention:** Temp files kept 24h by hash path; commit accepts re-upload or same hash. Stale hash directories under `upload_dir` are deleted by `cleanup_stale_uploads`.
5. **Default accounts** seeded on DB init: "Manual TradingView Account" (TRADINGVIEW_MANUAL), "AUTO Strategy Tester" (TRADINGVIEW_AUTO).
6. **P&L tolerance:** Default 0.01 USD for mismatch flag.
7. **Strategy tester** detected by presence of Entry/Exit time + Entry/Exit price columns and absence of row-by-row execution side column pattern.

**Will STOP and ask user if:** Real CSV requires choosing between two equally valid column mappings with no parser rule to disambiguate.
