# Trade Reconstruction

Step 2.5 implements **position-cycle weighted-average** reconstruction using a **signed position** model.

## Signed Position State

```
position_qty > 0  → LONG exposure
position_qty == 0 → FLAT
position_qty < 0  → SHORT exposure
```

Each execution updates signed quantity per ticker (within an account).

## Side Normalization

TradingView paper exports often use only `Buy` / `Sell`. The reconstructor infers effective role from position state:

| Position | Buy | Sell |
|----------|-----|------|
| Flat | Open LONG | Open SHORT |
| Long | Add LONG | Close LONG (may flip) |
| Short | Cover SHORT (may flip) | Add SHORT |

Explicit `SELL_SHORT` / `BUY_TO_COVER` are honored when consistent. Contradictory combinations log `TradeReconstructionError`.

## Position Cycles (Not FIFO Tax Lots)

One journal trade per round-trip position cycle:

```
BUY 100 @ 4.00
BUY 100 @ 4.10
SELL 50 @ 4.30
SELL 150 @ 4.50
→ ONE LONG trade, qty 200
```

## LONG Reconstruction

- **Entry fills:** BUY allocations while building LONG
- **Exit fills:** SELL allocations closing LONG
- **avg_entry** = weighted average of entry fills
- **avg_exit** = weighted average of exit fills
- **gross_pnl** = (avg_exit − avg_entry) × quantity

## SHORT Reconstruction

- **Entry fills:** SELL / SELL_SHORT allocations opening SHORT
- **Exit fills:** BUY / BUY_TO_COVER allocations covering SHORT
- **gross_pnl** = (avg_entry − avg_exit) × quantity

## Position Flips

When an execution crosses zero, it is **split internally** (original execution row unchanged):

```
LONG 100, SELL 150 @ 4.50
→ CLOSE 100 LONG @ 4.50 (closed trade)
→ OPEN 50 SHORT @ 4.50 (open trade)
```

Allocations persisted in `trade_executions.allocated_quantity`.

## Trade Quantity

`trade.quantity` = total shares **opened** in the cycle (not entry + exit sum).

## OPEN Trades

Unclosed cycles persist as `status = OPEN` with `avg_exit_price = null`. Dashboard realized metrics exclude OPEN trades (unchanged from Step 2).

## Ordering

Executions are sorted deterministically by:

1. `execution_time_utc ASC`
2. `row_number` (CSV source row at parse time; persisted `executions.id` on rebuild)
3. `external_execution_id`
4. `order_id`

Same-timestamp BUY/SELL and flip allocations follow this key. Reconstruction does **not** rely on unordered database scans.

## Truncated history / UNKNOWN_OPENING_POSITION

Reconstruction always starts each ticker at **FLAT relative to the earliest persisted execution**, not relative to the true broker account open.

- First observed **BUY** → open LONG (conventional default).
- First observed **SELL** / **SELL_SHORT** → open SHORT **and** emit a non-fatal `UNKNOWN_OPENING_POSITION` warning (stored on `import_errors`, not counted as a hard import error).

A truncated export whose first row is SELL may actually have closed a LONG opened before the file. The warning makes that assumption visible. Importing an overlapping file that contains **earlier** fills rebuilds the ticker; if the new earliest fill is no longer SELL-family, the warning is resolved via `import_errors.resolved_at` and the position cycle is reclassified.

Do not treat this warning as a `TradeReconstructionError`. Rebuild only auto-resolves `TradeReconstructionError` rows when the rebuild itself produced zero reconstruction errors.

## Rebuild Command

Repair historical trades from existing executions:

```powershell
cd backend
python -m app.cli.rebuild_trades --account-id 1
python -m app.cli.rebuild_trades --account-id 1 --dry-run
python -m app.cli.rebuild_trades --all --ticker PETZ
```

Does not modify source executions or import batches. Marks stale `TradeReconstructionError` rows resolved via `import_errors.resolved_at`.

## Examples

### Simple SHORT (generic sides)

```
SELL 100 @ 5.00   (flat → short)
BUY 100 @ 4.50    (cover)
→ SHORT CLOSED, qty 100, P&L +50
```

### LONG → SHORT flip

```
BUY 100 @ 4.00
SELL 150 @ 4.50
→ LONG CLOSED +50, SHORT OPEN 50 @ 4.50
```

### SHORT → LONG flip

```
SELL 100 @ 5.00
BUY 150 @ 4.70
→ SHORT CLOSED +30, LONG OPEN 50 @ 4.70
```

## Error Cases

Reserved for genuinely invalid data:

- quantity ≤ 0
- missing price or timestamp
- UNKNOWN side
- impossible explicit side vs position (e.g. BUY_TO_COVER while LONG)

Position flips, partial covers, and SHORT entries are **not** errors.
