# Cohort Comparison

## Global scope vs cohort conditions

**Global scope** limits the universe (date, account, source, direction, ticker, optional strategy version).

**Cohort conditions** are Graph exploration params applied *inside* that universe.

Do not copy global filters into every cohort.

## Membership

```
load_universe → _annotate_trades → attach_numeric
apply_exploration(features, TradeFilterSet(exploration=cohort.filters))
```

Identical filter keys and bucket values as Graphs (`signal_rvol_bucket=10_20`, not `10-20x`).

## Summary metrics

Shown when valid, with n and coverage:

Trades, R-qualified, excursion-qualified, Net P&L, Average Trade, Win Rate, Average R, Median R, Total R, Profit Factor, R Profit Factor, Avg Winner/Loser R, Max Drawdown R/$, Average MFE/MAE R, Exit Efficiency, R Left on Table.

Win rate excludes breakevens from the denominator (same as Dashboard).

## Observed Difference

Difference = Cohort A − Cohort B.

The column is labeled **Observed Difference**. It is not labeled “better strategy.”

## Overlap

`overlap_ids` / `overlap_count` are computed from trade IDs.

If overlap > 0:

- Warning: “These cohorts are not independent.”
- Independent bootstrap Δ mean R is unavailable.

Optional exclusive mode drops overlap from both cohorts. Default off.

## Unequal coverage

If A and B excursion coverage differ by ≥ 20 percentage points:

“Comparison may be affected by unequal data availability.”

## Sample size labels

These describe **n only**, not result quality:

| n | Label |
|---|-------|
| < 10 | N<10 |
| 10–19 | N10-19 |
| 20–49 | N20-49 |
| 50–99 | N50-99 |
| 100+ | N100+ |

Every comparison row, heatmap cell, scatter, rolling point, and interval displays n.
