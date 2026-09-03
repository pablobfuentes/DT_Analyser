# Dashboard Metrics

All metrics use **CLOSED trades only** unless noted. Date grouping uses **America/New_York**.

## Net P&L

Sum of `effective_realized_pnl` across filtered closed trades.

- Prefers `net_pnl` when available (`includes_fees: true`)
- Falls back to `gross_pnl` when `net_pnl` is null
- Warning shown when trades lack fee data

## Win Rate

`wins / (wins + losses) × 100`

Breakeven trades are **excluded** from the denominator.

Returns null (displayed as "—") when wins + losses = 0.

## Breakeven Classification

Tolerance: **$0.01** (configurable via `LTA_BREAKEVEN_TOLERANCE`)

- `pnl > +0.01` → WIN
- `pnl < -0.01` → LOSS
- otherwise → BREAKEVEN

## Avg Trade

`net_pnl_sum / trade_count` (includes breakeven trades in count)

## Avg Winner / Avg Loser

Mean P&L of winning / losing trades only.

## Trading Day

Any New York calendar date with at least one closed trade exit.

## Green / Red / Breakeven Day

Daily net P&L classification using same $0.01 tolerance.

## Realized Equity

`starting_equity + cumulative realized net P&L`

- Shown only when all selected accounts have `starting_equity` configured
- **Not** broker account equity — excludes open positions, deposits, withdrawals

## Cumulative P&L

Trades sorted by `exit_time_utc` ascending; running sum of daily net P&L by NY date.

## Manual vs Auto

Independent aggregation by `source_type`. No trade matching between sources.

## Open Trades

Counted separately; excluded from all realized statistics.
