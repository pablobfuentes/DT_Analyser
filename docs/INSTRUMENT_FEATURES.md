# Instrument Features (Step 4)

All times use **America/New_York** trading dates. Features are stored in `instrument_day_features` (unique per provider/feed/adjustment_mode/calculation_version) and joined to trades via `trade_market_features`.

## Opening Gap — PRE_ENTRY

```
opening_gap_pct = (day_open - prior_close) / prior_close * 100
```

Regular-session open only (not premarket).

## Daily Movement — END_OF_DAY

```
daily_movement_pct = (day_close - prior_close) / prior_close * 100
```

## Daily Volume — END_OF_DAY

Raw integer from provider daily bar. Partial feeds → `quality_status = PARTIAL_FEED`.

## RVOL50 (instrument_rvol50_eod) — END_OF_DAY

```
rvol50_multiple = day_volume / avg(prior 50 completed sessions' volume)
```

Requires 50 prior sessions; else `NULL` + `INSUFFICIENT_HISTORY`.

## Prior-Day RVOL50 — PRE_ENTRY

Prior session volume / 50-session average before that session.

## True Range

```
TR = max(high - low, |high - prior_close|, |low - prior_close|)
```

## ATR(14) — Wilder — PRE_ENTRY (atr14_prior)

Initialization: average of first 14 TR values.  
Recursive: `ATR_t = ((ATR_{t-1} * 13) + TR_t) / 14`

Trade analysis uses ATR through the **prior** completed session.

## Entry vs ATR — PRE_ENTRY

```
entry_vs_atr_pct = (avg_entry_price - prior_close) / atr14_prior * 100
```

## Relative Volatility — END_OF_DAY

```
relative_volatility_pct = true_range / atr14_prior * 100
```

## SMA20 / SMA50 — PRE_ENTRY

`sma20_prior`, `sma50_prior` from completed sessions before trade date.

```
entry_vs_sma20_pct = (entry - sma20_prior) / sma20_prior * 100
```

## Day Type — END_OF_DAY

Precedence: TREND_UP → TREND_DOWN → INSIDE_RANGE → OUTSIDE_RANGE.

- **TREND_UP**: close > prior high, open in bottom 15% of range, close in top 15%
- **TREND_DOWN**: close < prior low, open in top 15%, close in bottom 15%
- **INSIDE_RANGE**: high ≤ prior high AND low ≥ prior low
- **OUTSIDE_RANGE**: remaining valid days

## Graph dimensions

Registered in Step 3 report engine: gap, volume, RVOL50, prior RVOL, movement, ATR, entry vs ATR, relative volatility, day type, entry vs SMA20/50.

**Note:** Full-day RVOL (`instrument_rvol50_eod`) is distinct from future Step 5 signal-time RVOL.
