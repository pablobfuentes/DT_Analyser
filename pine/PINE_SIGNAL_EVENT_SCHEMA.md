# PINE_SIGNAL_EVENT Schema (Momentum Pullback Copilot SIGNALLOG)

Schema version: **1.0**  
Strategy key: **FIRST_PULLBACK**  
Producer script: `Momentum_Pullback_Copilot_SIGNALLOG.pine`

## Signal ID

```
FIRST_PULLBACK|<TICKER>|<TIMEFRAME>|<ARMED_BAR_TIME_MS>
```

Example: `FIRST_PULLBACK|NCRA|1|1725280860000`

Generated once when the setup becomes **ARMED** (state 3). The same ID is reused for ARMED, ENTRY, and EXIT events.

## Line format

Tab-separated. Every machine-readable row starts with:

```
PINE_SIGNAL_EVENT
```

Optional header row (on script load):

```
PINE_SIGNAL_EVENT_HEADER
```

## Column order (schema 1.0)

| # | Column | Example |
|---|--------|---------|
| 1 | RECORD_TYPE | PINE_SIGNAL_EVENT |
| 2 | SCHEMA_VERSION | 1.0 |
| 3 | SIGNAL_ID | FIRST_PULLBACK\|NCRA\|1\|1725280860000 |
| 4 | STRATEGY_KEY | FIRST_PULLBACK |
| 5 | STRATEGY_VERSION | Momentum Pullback Copilot v0.3.3.1 Opening Fade Research |
| 6 | TICKER | NCRA |
| 7 | DIRECTION | LONG |
| 8 | TIMEFRAME | 1 |
| 9 | ORIGIN | REALTIME or HISTORICAL_REPLAY |
| 10 | EVENT_TYPE | ARMED, ENTRY, or EXIT |
| 11 | EVENT_TIME | 2026-09-02T09:43:17 (America/New_York) |
| 12 | EVENT_TIME_MS | 1725280997000 |
| 13 | EVENT_PRICE | 4.82 |
| 14 | PLANNED_ENTRY | 4.82 |
| 15 | PLANNED_STOP | 4.70 |
| 16 | REFERENCE_2R | 5.06 |
| 17 | SUGGESTED_SHARES | 238 |
| 18 | SETUP_QUALITY | A+ |
| 19 | ALLOWED_RISK | 12.50 |
| 20 | PLANNED_POSITION_VALUE | 1147.16 |
| 21 | PLANNED_EXPOSURE_PCT | 7.20 |
| 22 | SIGNAL_GAP_PCT | 12.50 |
| 23 | SIGNAL_RVOL | 8.40 |
| 24 | IMPULSE_PCT | 7.20 |
| 25 | RETRACEMENT_PCT | 28.60 |
| 26 | CONTEXT_5M | BULLISH or NOT_BULLISH |
| 27 | ABOVE_VWAP | true / false |
| 28 | ABOVE_EMA9 | true / false |
| 29 | VOLUME_CONFIRMED | true / false |
| 30 | SESSION | 09:30-10:00 ET |
| 31 | EXIT_REASON | empty for ARMED/ENTRY; STOP LOSS, TOPPING TAIL, etc. for EXIT |

## Field sources (First Pullback)

| Field | Source in Copilot |
|-------|-------------------|
| SIGNAL_GAP_PCT | Planned entry vs prior daily close |
| SIGNAL_RVOL | Current daily volume / 50-day avg daily volume |
| IMPULSE_PCT | Impulse high-low vs impulse low |
| RETRACEMENT_PCT | Pullback retracement at event time |
| CONTEXT_5M | 5-minute higher-timeframe context |
| SETUP_QUALITY | Existing f_quality() grading |

## Origin

- `REALTIME` when `barstate.isrealtime`
- `HISTORICAL_REPLAY` otherwise

## Import

Paste Pine Logs into Local Trader Analyzer → Import → Strategy Signals (Step 5).
