# MFE / MAE (Step 8)

## Terminology

- **MFE:** Maximum Favorable Excursion (positive normalized)
- **MAE:** Maximum Adverse Excursion (negative normalized)

## Price excursions (reference entry = weighted avg entry)

**LONG:** `price_mfe = max_price − entry`, `price_mae = min_price − entry`

**SHORT:** `price_mfe = entry − min_price`, `price_mae = entry − max_price`

## Position excursions (preferred for R and efficiency)

Position lifecycle replay using `trade_executions.allocated_quantity`:

```
total_hypothetical_pnl = realized_gross_to_date + mark_to_market(open_qty, price)
```

**LONG marks:** favorable = bar HIGH, adverse = bar LOW  
**SHORT marks:** favorable = bar LOW, adverse = bar HIGH

Execution prices are always valid observations.

## Dual boundary estimates

| Mode | Policy |
|------|--------|
| **Inclusive (primary UI)** | Bar HIGH/LOW on any bar overlapping open position |
| **Conservative** | Boundary bars: execution prices only; interior bars: full HIGH/LOW |

**Boundary spread:**

```
mfe_boundary_spread_amount = inclusive_position_mfe − conservative_position_mfe
mfe_boundary_spread_r = inclusive_mfe_r − conservative_mfe_r
```

## R normalization

```
mfe_r = position_mfe_amount / initial_risk_amount
mae_r = position_mae_amount / initial_risk_amount
```

Requires Step 7 `initial_risk_amount > 0`.

## Post-exit extension (separate from MFE)

5m / 15m / 30m favorable extension after final exit — **not** included in canonical MFE.
