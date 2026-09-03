# Step 2.5 Plan — SHORT Trade Reconstruction + Position Flip Hardening

## A. Current Reconstruction Algorithm

`TradeReconstructor` in `app/services/trade_reconstruction.py`:

1. Group executions by ticker, sort by `execution_time_utc` only.
2. Maintain `position_qty` (implicit LONG-only, always ≥ 0).
3. `BUY` → append entry fill, increase position.
4. `SELL` → append exit fill if position > 0; error if flat/short.
5. Position flip remainder → **error** (`Position flip unsupported`).
6. `SELL_SHORT` / `BUY_TO_COVER` → **error** (`not fully supported in Step 1`).
7. When position hits zero → emit one **LONG** CLOSED trade via weighted-average entry/exit.
8. Remaining open LONG → emit OPEN trade.

Import path (`ImportService._import_manual_executions`):

- Inserts new executions, reconstructs **all** executions for affected tickers.
- Persists **CLOSED trades only** via fingerprint dedup.
- Logs reconstruction errors to `import_errors`.

## B. Why SHORT Trades Currently Fail

TradingView paper exports use generic `Buy` / `Sell` sides only — no `SELL_SHORT` or `BUY_TO_COVER`.

A flat-account `Sell` is treated as invalid (`SELL without open LONG position`) instead of opening a SHORT.

Explicit SHORT sides are rejected outright with a Step 1 error message.

## C. Why Position Flips Currently Fail

When `SELL qty > position_qty` (e.g. LONG 100, SELL 150):

- Engine closes 100 shares then errors on the remaining 50.
- The 50-share SHORT leg is never opened.
- No trade is emitted for the closed LONG portion in some paths because error handling uses `continue` before `emit_trade` in edge cases.

Same pattern for `BUY qty > |short position|` (SHORT → LONG flip).

## D. Proposed Signed-Position Model

```
position_qty > 0  → LONG exposure
position_qty == 0 → FLAT
position_qty < 0  → SHORT exposure
```

Process each execution chronologically per `(account, ticker)`:

- **BUY** when flat or long → add LONG entry.
- **BUY** when short → cover SHORT (exit fill), possibly flip to LONG.
- **SELL** when flat or short → add SHORT entry.
- **SELL** when long → close LONG (exit fill), possibly flip to SHORT.

Zero-crossing executions are **split internally** into close + open portions at the same price/timestamp.

Accounting method: **position-cycle weighted average** (not FIFO tax lots).

## E. Execution Splitting Rules

Original `Execution` row is never modified or duplicated in the database.

During reconstruction, each source execution may produce 1–2 **internal allocations**:

| Scenario | Allocation A | Allocation B |
|----------|--------------|--------------|
| LONG 100, SELL 150 | EXIT 100 → close LONG | ENTRY 50 → open SHORT |
| SHORT 100, BUY 150 | EXIT 100 → close SHORT | ENTRY 50 → open LONG |
| Normal fill | Single ENTRY or EXIT | — |

Persisted via `trade_executions.allocated_quantity` (+ existing `role` ENTRY/EXIT).

## F. Weighted-Price Rules

**LONG**

- `avg_entry_price` = Σ(q×p) / Σq over ENTRY allocations
- `avg_exit_price` = Σ(q×p) / Σq over EXIT allocations

**SHORT**

- `avg_entry_price` = weighted average of SHORT opening sells (ENTRY)
- `avg_exit_price` = weighted average of covers (EXIT)

All calculations use `Decimal`; persist via `quantize_price`.

## G. P&L Formulas

```
LONG:  gross_pnl = (avg_exit - avg_entry) × quantity
SHORT: gross_pnl = (avg_entry - avg_exit) × quantity
net_pnl = gross_pnl - fees
```

`trade.quantity` = total shares opened in the position cycle (not entry+exit sum).

Fees split proportionally by allocated quantity when one execution spans two trades.

## H. Duplicate Implications

- Execution fingerprints unchanged — one imported row = one `executions` record.
- Flip allocations link the same `execution_id` to two trades with different `allocated_quantity`.
- Trade fingerprints unchanged formula — rebuilt trades replace old rows via rebuild command.
- Re-import idempotency preserved: duplicate executions skipped before reconstruction.

## I. Raw-Data Preservation Strategy

- `executions.raw_row_json` — untouched.
- No synthetic execution rows inserted.
- Allocations are reconstruction metadata in `trade_executions` only.

## J. Regression Test Plan

### Unit tests (`test_trade_reconstruction.py`, `test_step_2_5_reconstruction.py`)

All 24 scenarios from spec §28: LONG/SHORT simple, multi-entry, partial exit, flips, scale-in/out, Decimal precision, ordering, errors.

### Real-data regression fixtures

| Fixture | Symbol | Pattern |
|---------|--------|---------|
| `regression_petz_short.csv` | PETZ | Flat SELL → BUY cover |
| `regression_aehl_short.csv` | AEHL | Short round-trip |
| `regression_ssm_flip.csv` | SSM | LONG→SHORT flip + scale |
| `regression_flye_flip.csv` | FLYE | LONG→SHORT→cover sequence |

### Integration tests

- Full paper order history import → 0 reconstruction errors
- Duplicate/overlapping import idempotency
- `rebuild_trades` dry-run + commit idempotency
- Dashboard with LONG/SHORT mix, direction filter, net P&L

### Side normalization tests

- Generic BUY/SELL inferred from position state
- Contradictory UNKNOWN side → controlled error

## Side Normalization

Priority:

1. If position state makes role deterministic → infer (SELL from flat = open SHORT).
2. If explicit side contradicts impossible state → log `TradeReconstructionError`.
3. `UNKNOWN` without inferable state → error.

## Import Error Cleanup

Add `import_errors.resolved_at` (nullable UTC timestamp).

On successful rebuild for an account:

- Set `resolved_at` on unresolved `TradeReconstructionError` rows linked to that account's import batches.

Parsing/import errors (malformed rows) are untouched.

## Rebuild CLI

```
python -m app.cli.rebuild_trades [--account-id N] [--ticker T] [--all] [--dry-run]
```

Transactional: delete trades + trade_executions for scope, reconstruct from executions, persist OPEN + CLOSED.

## Schema Changes

1. `trade_executions.allocated_quantity NUMERIC(18,6) NOT NULL` (default = full execution qty for backfill)
2. `import_errors.resolved_at DATETIME NULL`

## Frontend Impact (Minimal)

- Trade detail: show allocation qty + role per linked execution (flip debug).
- No dashboard metric changes.

## Definition of Done

See spec §37 — all reconstruction errors from SHORT/flips eliminated on real paper export; rebuild CLI operational; full test suites green.
