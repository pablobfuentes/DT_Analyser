# Step 2 Plan — Overview Dashboard

## A. Existing Components Reused

- **Models:** `Trade`, `Account` (extend with `starting_equity`)
- **Utils:** `app/utils/money.py` (Decimal helpers)
- **Config:** `app/config.py` (extend with analytics settings)
- **API patterns:** Pydantic v2 schemas, `/api` prefix, Decimal as JSON strings
- **Frontend:** React Router, `api/client.ts` fetch wrapper, page/component structure
- **Tests:** pytest + in-memory SQLite fixtures from Step 1

## B. New Backend Services/Endpoints

| Component | Purpose |
|-----------|---------|
| `app/utils/analytics.py` | `effective_realized_pnl`, win/loss classification, NY date boundaries |
| `app/services/dashboard_service.py` | All dashboard aggregations |
| `app/api/dashboard.py` | `GET /api/dashboard` (single optimized endpoint) |
| `app/api/accounts.py` | `PATCH /api/accounts/{id}` for starting equity |
| `app/db/migrate.py` | SQLite migration for `starting_equity` column |
| `app/schemas/dashboard.py` | Dashboard response models |

## C. Dashboard Calculations

- **Scope:** CLOSED trades only (filtered by `exit_time_utc` in NY date range)
- **Summary:** net P&L, trade count, win rate, averages, best/worst, gross/fees/shares/hold time
- **Daily:** group by NY calendar date of exit
- **Cumulative:** daily cumulative realized P&L
- **Source comparison:** aggregate by `TRADINGVIEW_MANUAL` vs `TRADINGVIEW_AUTO`
- **Recent:** last 10 closed trades by exit time

## D. Date/Time Grouping Rules

- `ANALYTICS_TIMEZONE = America/New_York`
- Filter `start_date`/`end_date` = NY calendar dates → converted to UTC boundaries via `zoneinfo`
- Daily grouping uses exit time converted to NY date
- DST handled by `zoneinfo`, not fixed offsets

## E. Equity Calculation Rules

- `current_realized_equity = starting_equity + cumulative_net_pnl` (filtered period or all-time for display)
- Single account: show if `starting_equity` set
- Multiple accounts: show only if ALL selected accounts have `starting_equity`
- Label: "Realized Equity" with tooltip explanation
- Filtered periods use Step 7 `equity_baseline`: displayed starting equity = account starting + realized P&L from closed trades before the filter start (not a reset to raw starting equity)
- No default $10,000

## F. Frontend Component Structure

```
src/pages/DashboardPage.tsx
src/components/dashboard/  (filters, cards, charts, tables)
src/hooks/useDashboard.ts
src/api/dashboard.ts
src/types/dashboard.ts
src/utils/money.ts, duration.ts
```

## G. Filtering Behavior

Centralized `DashboardFilters` synced to URL query params.
Default: This Month, All Accounts, All Sources, All Directions, no ticker.
All widgets consume one API response from `GET /api/dashboard`.

## H. Test Plan

- Backend: 30+ tests in `tests/test_dashboard.py` with synthetic trades fixture
- Frontend: Vitest for MetricCard, formatters, empty states
- Step 1 tests must still pass unchanged

## I. Schema Migration

- Add nullable `starting_equity NUMERIC(18,6)` to `accounts`
- Add indexes: `ix_trades_exit_time`, `ix_trades_account_status`

## J. Assumptions

- `MANUAL` filter maps to `TRADINGVIEW_MANUAL`; `AUTO` to `TRADINGVIEW_AUTO`
- Breakeven tolerance = $0.01 (configurable)
- Open trades counted separately, excluded from P&L stats
- Calendar heatmap optional — include if time permits after core tests pass
