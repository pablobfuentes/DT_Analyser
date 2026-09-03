# Expectancy

## Dollar Expectancy

```
Dollar Expectancy = sum(effective_realized_pnl) / count(closed trades)
```

Breakeven trades are included in the trade count.

Equivalent to:

```
(win_rate × avg_winner) + (loss_rate × avg_loser)
```

when breakevens are handled consistently.

## R Expectancy

```
R Expectancy = sum(r_multiple) / count(trades with valid R)
```

Only R-qualified trades are included in the denominator.

## Profit Factor

```
Gross Profits = sum(positive P&L)
Gross Losses = abs(sum(negative P&L))
Profit Factor = Gross Profits / Gross Losses
```

Special cases: `NO_LOSSES` (display ∞), `NO_WINS` (0), `NO_TRADES` (—).

## Payoff Ratio

```
Average Winner / |Average Loser|
```

Null when no winners or no losers.

## Streaks

Chronological by exit time. **BREAKEVEN breaks both** win and loss streaks.
