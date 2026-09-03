# Risk and R-Multiple

## Principle

**Never invent risk.** R-multiple requires a known initial trade risk from manual entry (Step 3) or future Pine import (Step 4).

If risk is unknown: `r_multiple = NULL`. The trade still counts in dollar analytics.

## R Formula

```
R = effective_realized_pnl / initial_risk_amount
```

`effective_realized_pnl` = `net_pnl` if available, else `gross_pnl`.

## Risk Precedence

1. Explicit `initial_risk_amount` (authoritative)
2. Derived: `|avg_entry − stop| × quantity` (direction-specific)

If both are provided and differ beyond tolerance → warning, explicit amount kept.

## Direction Rules

**LONG:** stop must be **below** entry. Risk/share = entry − stop.

**SHORT:** stop must be **above** entry. Risk/share = stop − entry.

## API

`PATCH /api/trades/{id}/risk`

## Coverage

R analytics exclude trades without `initial_risk_amount`. Dashboard shows coverage count and percentage.
