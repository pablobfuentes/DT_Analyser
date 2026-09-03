# Exit Efficiency (Step 8)

## Formula

```
exit_efficiency_pct = gross_realized_pnl / position_mfe_amount × 100
```

Only when `position_mfe_amount > 0`. Uses **gross** P&L (not net fees).

## Related metrics

```
gross_realized_r = gross_realized_pnl / initial_risk_amount
r_left_on_table = mfe_r − gross_realized_r
peak_giveback_amount = position_mfe_amount − gross_realized_pnl
peak_giveback_pct = peak_giveback_amount / position_mfe_amount × 100
```

Step 7 **actual R** may remain net-based; do not mix with MFE gross capture.

## Edge cases

- **Negative efficiency:** allowed (e.g. +$100 MFE, −$20 exit → −20%)
- **>100%:** preserved; flagged `EFFICIENCY_OVER_100`
- **No positive MFE:** efficiency = NULL

## Best Capture table

Minimum MFE for eligibility: **0.50R** (`BEST_CAPTURE_MIN_MFE_R` in backend config).
