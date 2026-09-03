# Step 3 Plan — Graphs + Interactive Multi-Dimensional Analysis

## A. Existing Components Reused

- `DashboardFilters` / global filter fields (date, account, source, direction, ticker)
- `build_closed_trades_query`, `utc_bounds_for_ny_range`, `ny_date_from_utc`, `analytics_tz`
- `effective_realized_pnl`, `classify_outcome`, `win_rate_pct`, `decimal_str`
- `Trade`, `TradeExecution`, `Execution` models
- Frontend: Recharts, `DashboardFiltersBar`, URL filter utils, theme CSS
- Dashboard R/expectancy analytics (separate; unchanged)

## B. Report Engine Architecture

```
GET /api/reports
  → parse TradeFilterSet (global + exploration)
  → load closed trades (+ execution counts)
  → annotate TradeAnalysisFeatures (in-memory, no lookahead)
  → apply filters
  → aggregate each registered report dimension
  → return sections + buckets + matching_trade_count
```

Single backend pass over filtered trade set; all reports computed from same annotated list.

## C. Dimension Registry

Central `REPORT_DEFINITIONS` list: key, title, section, dimension_fn, bucket_order, filter_key, available.

## D. Metric Registry

Per-bucket metrics computed once: `trade_count`, `wins`, `losses`, `breakeven`, `net_pnl`, `avg_trade`, `win_rate`, `avg_winner`, `avg_loser`.

Frontend metric selector picks display field without new API call.

## E. Bucket Definitions

Centralized in `reports/config.py` (price, quantity, position value, duration, daily P&L state).

Time buckets derived from NY `entry_time_utc`.

## F. Global Filter Model

Same as Step 2: `start_date`, `end_date`, `account_id`, `source_type`, `direction`, `ticker`.

Applied via exit-time date range + SQL query.

## G. Exploration Filter Model

Query params: `weekday`, `entry_hour`, `entry_30m`, `entry_15m`, `duration_bucket`, `entry_price_bucket`, `quantity_bucket`, `position_value_bucket`, `trade_number`, `prev_outcome`, `consec_losses`, `daily_pnl_state`, `symbol`, etc.

Single-select per dimension (replace on new click).

## H. Click-to-Filter

Bucket click toggles exploration filter; all reports re-fetch with updated URL.

## I. Collapsible Sections

Frontend-only; `sessionStorage` for section open state.

## J. Quick Navigation

Sticky nav scrolls to section + expands if collapsed.

## K. Backend Aggregation

Group annotated trades by dimension bucket key; sum/count metrics with Decimal.

## L. Frontend Report Cards

`ReportCard`: title, metric selector, bar chart, best/worst bucket, sample warning.

## M. URL Synchronization

Global params + exploration params in `/graphs?...`.

## N. Performance

Load trades once; O(trades × reports) in-memory; target <1s for 10k trades.

## O. Test Plan

Dimension tests, behavior/no-lookahead tests, filter engine tests, discovery integration fixture, 10k benchmark.

## P. Future Extension

Registry `available: false, requires: MARKET_ENRICHMENT` for MARKET/STRATEGY/EXECUTION/RISK sections.
