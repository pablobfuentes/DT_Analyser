# Drawdown

## Definition

Drawdown is calculated from the **realized equity curve** (or cumulative P&L when starting equity is unavailable).

At each closed trade (chronological by `exit_time_utc`):

```
running_peak = max(previous_peak, current_equity)
drawdown_$ = current_equity − running_peak   (≤ 0)
drawdown_% = drawdown_$ / running_peak × 100
```

## Filtered Period

Label: **Max Drawdown — selected period**

Period baseline equity:

```
sum(starting_equity) + sum(pre-period realized P&L)
```

Pre-period P&L includes all closed trades before the filter start date for selected account(s), even though those trades are excluded from period performance metrics.

## Without Starting Equity

- Cumulative P&L drawdown ($) is still computed
- Drawdown **%** is unavailable (no valid capital base)

## Duration

Drawdown period starts after leaving an equity peak and ends when equity recovers to or exceeds the prior peak. Primary display: **trading days underwater**.
