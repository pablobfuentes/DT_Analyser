# Report Dimensions

Central registry: `backend/app/services/reports/registry.py`  
Bucket thresholds: `backend/app/services/reports/config.py`  
Feature derivation: `backend/app/services/reports/features.py`

All trading-time dimensions use **America/New_York** (`settings.analytics_timezone`).

## TIME

| Key | Feature | Buckets | Filter param |
|-----|---------|---------|--------------|
| day_of_week | day_of_week | MON–SUN (weekdays with data) | weekday |
| entry_hour | entry_hour | 07–15, 16+ | entry_hour |
| entry_30m | entry_30m | 30-min windows from entry | entry_30m |
| entry_15m | entry_15m | 15-min windows from entry | entry_15m |
| month | month | YYYY-MM | month |
| week | week | Mon–Fri week label | week |
| day_of_month | day_of_month | 1–31 | day_of_month |
| duration | duration | &lt;1m, 1–2m, 2–5m, 5–10m, 10–20m, 20–60m, 60+m | duration_bucket |
| entry_hour_activity | entry_hour | same as entry hour | entry_hour |

## TRADE CHARACTERISTICS

| Key | Feature | Buckets | Filter param |
|-----|---------|---------|--------------|
| entry_price | entry_price | &lt;$2, $2–3, $3–5, $5–10, $10–20, $20+ | entry_price_bucket |
| quantity | quantity | &lt;100 … 2,000+ | quantity_bucket |
| position_value | position_value | avg_entry × qty buckets | position_value_bucket |
| fill_count | fill_count | 1–4, 5+ (from executions) | fill_count |
| entry_style | entry_style | single, scale_in | entry_style |
| exit_style | exit_style | single, scale_out | exit_style |

## INSTRUMENT

| Key | Feature | Notes |
|-----|---------|-------|
| symbol | symbol | Top 20 by net P&L. Exploration `symbol` vs global `ticker` both match `Trade.ticker`; global is SQL universe, symbol is click-to-filter. |
| symbol_avg | symbol | Top 20, min sample 2 |
| symbol_winrate | symbol | Top 20, min sample 2 |
| instrument_gap … entry_vs_sma50 | market buckets | Step 4; PRE_ENTRY vs END_OF_DAY badges |

## MARKET

SPY gap (PRE_ENTRY), SPY movement (EOD), SPY day type (EOD).

## SOURCE & DIRECTION

| Key | Feature | Filter param |
|-----|---------|--------------|
| source | source | source_bucket |
| direction | direction | direction_bucket |
| source_winrate | source | source_bucket |
| direction_winrate | direction | direction_bucket |

## TRADER BEHAVIOR (no lookahead)

| Key | Feature | Definition |
|-----|---------|------------|
| trade_number | trade_number | Entry order within account + NY day |
| prev_outcome | prev_outcome | Last trade with exit &lt; current entry |
| consec_losses | consec_losses | Consecutive losses before entry |
| daily_pnl_state | daily_pnl_state | Sum of same-day realized P&L from exits before entry |

Behavior uses event-sweep: exit events update state before entry events at the same timestamp.

Consecutive losses: a **breakeven resets the loss streak** (same as a win). Only completed exits before entry count.

## OUTCOMES

| Key | Feature | Notes |
|-----|---------|-------|
| pnl_distribution | pnl_bucket | Fixed P&L histogram buckets |
| outcome_composition | outcome | WIN / LOSS / BREAKEVEN |
| pnl_sequence | _sequence | Line chart, one point per trade |
| avg_trade_week | week | Average trade by week |

## Future (unavailable placeholders)

| Dimension | Requires | Step |
|-----------|----------|------|
| setup, pine_signal, vwap | PINE_SIGNALS | 5 |
| r_multiple reports in Graphs | RISK_ANALYTICS | 7 |

Step 4 market dimensions and Step 8 execution reports are **implemented** when their enrichment data exists.

## Availability metadata

Future dimensions register in `registry.py` with `available: false` and `requires` feature flag. Sections render compact placeholders without fake charts.

## Research Lab dimensions

Research reuses the same exploration keys and feature buckets as this document. Numeric scatter axes live in `RESEARCH_VARIABLES` (`backend/app/services/research/variables.py`), not arbitrary DB columns.

Heatmap / multi-factor dimensions: weekday, entry_15m, entry price, gap, RVOL50 EOD, prior-day RVOL, ATR, market gap, setup quality, signal RVOL, impulse, retracement, 5m context, strategy version, risk % equity, MFE/MAE (retrospective only), ticker (Top 20), day type.

Timing and pre-entry eligibility: [RESEARCH_TIMING_AND_LOOKAHEAD.md](RESEARCH_TIMING_AND_LOOKAHEAD.md).
