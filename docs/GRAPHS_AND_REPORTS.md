# Graphs and Reports

Step 3 delivers a Tradervue Reports–style discovery experience at `/graphs`.

## Purpose

- Scroll through many fixed analytical report cards
- Click chart buckets to add **exploration filters**
- All reports recalculate on the filtered subset
- Global filters (date, account, source, direction, ticker) remain independent

## Architecture

```
GET /api/reports
  ↓
reports/service.py
  ├── load closed trades (dashboard query)
  ├── annotate features (NY timezone, behavior)
  ├── apply exploration filters
  └── aggregate all registered dimensions
```

Single API call returns all sections, reports, buckets, and metrics. The browser never receives raw trade rows.

## Page Layout

1. Global filters (reused from Dashboard)
2. Active exploration filter bar + matching trade count
3. Sticky quick navigation (TIME, TRADE, INSTRUMENT, …)
4. Collapsible sections with report grid (2 columns desktop)

## Report Cards

Each card has a **fixed dimension** and optional **metric selector**:

- Total P&L, Average Trade, Win Rate, Trade Count, Avg Winner, Avg Loser

Changing metric does not change the dimension. Backend returns all measures per bucket.

## Sections (current)

| Section | Status |
|---------|--------|
| TIME | 9 reports |
| TRADE CHARACTERISTICS | 6 reports |
| INSTRUMENT | Symbol reports + Step 4 gap/volume/RVOL/ATR/SMA/day-type (when enriched) |
| SOURCE & DIRECTION | 4 reports |
| TRADER BEHAVIOR | 4 reports |
| OUTCOMES | 4 reports |
| MARKET | SPY gap / movement / day type when a provider is configured or benchmark rows exist |
| STRATEGY | Placeholder — Step 5 |
| EXECUTION QUALITY | Active when excursion enrichment exists (Step 8) |
| RISK & R | Placeholder — Step 7 |

## Date range

Global `start_date` / `end_date` select **closed trades by exit-time New York date** (same as Dashboard). Time/calendar dimensions (weekday, entry hour, 15m/30m, month, week, day of month, trade # of day) use **entry time** in `America/New_York`.

## Performance

For ~10,000 closed trades locally:

- Trades loaded and annotated once
- Behavior features use event-sweep O(n log n)
- All dimensions aggregated in one pass
- Suite assertion: **&lt;5s** (Step 3 plan target was &lt;1s; current runtime is typically a few seconds)

Related: [STEP_3_4_AUDIT.md](./STEP_3_4_AUDIT.md)

## Related Docs

- [REPORT_DIMENSIONS.md](./REPORT_DIMENSIONS.md)
- [REPORT_FILTER_ENGINE.md](./REPORT_FILTER_ENGINE.md)
- [STEP_3_PLAN.md](./STEP_3_PLAN.md)
