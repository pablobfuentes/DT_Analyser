# Research Timing and Lookahead

Every research variable and cohort filter has a timing class:

`PRE_ENTRY` | `SIGNAL` | `ENTRY` | `POST_ENTRY` | `EXIT` | `END_OF_DAY` | `POST_EXIT`

Stored enum `PRE_ENTRY_ONLY` (user-facing **KNOWN BY ENTRY**) allows filters and predictor axes whose class is `PRE_ENTRY`, `SIGNAL`, or `ENTRY` — **known no later than entry**, not strictly “before fill.”

**Selection-time** variables (SIGNAL / PRE_ENTRY): gap, prior RVOL, Pine signal RVOL, setup quality, retracement, 5m context.

**Entry/fill** variables (ENTRY): entry time window, fill price, quantity, initial risk, stop distance.

Both are allowed in KNOWN BY ENTRY. EXIT / POST_ENTRY / END_OF_DAY / POST_EXIT are not.

Analyzing a pre-entry X against a post-entry Y (example: Signal RVOL → Actual R) is normal.

Selecting a cohort *with* a post-entry filter (Actual R, MFE, full-day RVOL) marks **RETROSPECTIVE COHORT**.

## Research variables

| Variable | Source | Timing | Allowed Pre-entry? | Quality | Units |
|----------|--------|--------|--------------------|---------|-------|
| minutes_since_open | Trade | ENTRY | YES | — | minutes |
| entry_price | Trade | ENTRY | YES | — | USD |
| quantity | Trade | ENTRY | YES | — | shares |
| position_value | Trade | ENTRY | YES | — | USD |
| initial_risk_amount | Risk | ENTRY | YES | — | USD |
| risk_pct_equity | Risk | ENTRY | YES | — | % |
| stop_distance_pct | Risk | ENTRY | YES | — | % |
| signal_rvol | Pine | SIGNAL | YES | PINE_SIGNAL | x |
| signal_gap_pct | Pine | SIGNAL | YES | PINE_SIGNAL | % |
| impulse_pct | Pine | SIGNAL | YES | PINE_SIGNAL | % |
| retracement_pct | Pine | SIGNAL | YES | PINE_SIGNAL | % |
| opening_gap_pct | Market | PRE_ENTRY | YES | — | % |
| prior_rvol50 | Market | PRE_ENTRY | YES | FULL_FEED | x |
| atr14_prior | Market | PRE_ENTRY | YES | — | USD |
| actual_r | Trade + Risk | EXIT | NO | — | R |
| net_pnl | Trade | EXIT | NO | — | USD |
| hold_seconds | Trade | EXIT | NO | — | seconds |
| rvol50_eod | Market (Alpaca SIP) | END_OF_DAY | NO | FULL_FEED | x |
| mfe_r | Intraday + Risk | POST_ENTRY | NO | EXCURSION | R |
| mae_r | Intraday + Risk | POST_ENTRY | NO | EXCURSION | R |
| exit_efficiency_pct | Intraday + Risk | POST_ENTRY | NO | EXCURSION | % |
| r_left_on_table | Intraday + Risk | POST_ENTRY | NO | EXCURSION | R |
| time_to_mfe_seconds | Intraday | POST_ENTRY | NO | EXCURSION | seconds |
| post_exit_favorable_15m_r | Intraday | POST_EXIT | NO | EXCURSION | R |

Registry: `backend/app/services/research/variables.py` (`RESEARCH_VARIABLES`).

## Cohort filter timing (Graph keys)

| Filter key | Timing | Allowed Pre-entry? | Notes |
|------------|--------|--------------------|-------|
| weekday, month, week, day_of_month | PRE_ENTRY | YES | Calendar of entry |
| trade_number, prev_outcome, consec_losses, daily_pnl_state | PRE_ENTRY | YES | Known before this entry |
| gap_bucket, prior_rvol_bucket, atr_bucket, entry_atr_bucket | PRE_ENTRY | YES | Opening / prior session |
| entry_sma20_bucket, entry_sma50_bucket, market_gap_bucket | PRE_ENTRY | YES | |
| entry_hour, entry_30m, entry_15m | ENTRY | YES | |
| entry_price_bucket, quantity_bucket, position_value_bucket | ENTRY | YES | |
| symbol, source_bucket, direction_bucket, fill_count, entry_style | ENTRY | YES | |
| initial_risk_bucket, risk_pct_equity_bucket, stop_distance_pct_bucket | ENTRY | YES | |
| strategy_*, setup_quality, signal_*_bucket, impulse, retrace, context_5m | SIGNAL | YES | Pine at signal |
| vwap_condition, ema9_condition, volume_confirmed | SIGNAL | YES | |
| suggested_shares_bucket, planned_pv_bucket, planned_exposure_bucket | SIGNAL | YES | |
| rvol_bucket | END_OF_DAY | NO | Full-day instrument RVOL50 |
| volume_bucket, movement_bucket, day_type, tr_atr_bucket | END_OF_DAY | NO | Same-day complete |
| market_movement_bucket, market_day_type | END_OF_DAY | NO | Benchmark full day |
| mfe_r_bucket, mae_r_bucket, exit_efficiency_bucket, r_left_bucket | POST_ENTRY | NO | |
| time_to_mfe_bucket, time_to_mae_bucket, mfe_to_exit_bucket, peak_giveback_bucket | POST_ENTRY | NO | |
| duration_bucket, exit_style, pnl_bucket, outcome, exit_reason, r_outcome_bucket | EXIT | NO | |

**Exact distinction:** `prior_rvol_bucket` is pre-entry. `rvol_bucket` (full-day RVOL50) is end-of-day and cannot be used as an entry-selection filter in PRE-ENTRY ONLY.

## Lookahead enforcement

`validate_cohort_filters` raises `LookaheadFilterError` in PRE-ENTRY ONLY.

API response: HTTP 400 `{ "code": "LOOKAHEAD_FILTER", "keys": [...], "message": "Not available before trade entry: ..." }`.

Frontend disables those condition options and shows the same tooltip.
