# Exit Analyzer (Step 8)

Route: `/exit-analysis`

## Purpose

Answer: *How good are my exits?* using MFE/MAE, exit efficiency, R left on table, and peak giveback.

## Summary cards

- Average MFE R / MAE R
- Average & median exit efficiency
- Average R left on table / peak giveback %
- Capture thresholds (≥25/50/75/90% of MFE)
- Positive MFE → losing exit count
- Reached 2R but closed <1R / losing

## Tables

- Biggest observed R opportunity not captured
- Biggest peak giveback
- Best capture (MFE ≥ 0.50R)

## Scatter views

- MFE R vs Actual R (table of points; chart optional future)
- MAE R vs Actual R

## Filters

Reuses global dashboard filters (date, account, source, direction, ticker).

## Copilot exit comparison

**Status:** Unavailable — Step 5 signal tables (`signals`, `trade_signal_links`) not present in database at implementation time. Coverage reported as 0%; MFE/MAE unaffected.

When Step 5 lands: compare actual exit time/price vs `mechanical_exit_price` / `exit_signal_time_utc`.
