# Architecture

## Overview

Local Trader Analyzer is a monorepo with a Python/FastAPI backend and React/Vite frontend. All data stays on your machine in SQLite.

## Backend Layers

```
API (FastAPI routers)
  ↓
Services (import, dashboard, reports, reconstruction)
  ↓
Importers (detector + parsers)
  ↓
Database (SQLAlchemy models)
```

Reports service (`services/reports/`): registry, features, filters, aggregation, service.

Automation (`services/automation/`): inbox classify → persistent jobs → single worker → pipeline that **calls** ImportService, Pine importer, matcher, RiskService, market/excursion enrichment. Journal, reviews, and SQLite backup live beside it. Route `/workflow`. See [AUTOMATION_WORKFLOW.md](AUTOMATION_WORKFLOW.md) and [DATA_DIRECTORY.md](DATA_DIRECTORY.md).

Research Lab (`services/research/`): cohort reuse of `apply_exploration`, numeric sidecar, comparison / scatter / heatmap / rolling / distributions / robustness / statistics. Route `/research`. See [RESEARCH_LAB.md](RESEARCH_LAB.md).

## Importer Architecture

Each parser implements:

- `can_parse(df) → DetectionResult` with confidence 0–1
- `parse(df, timezone) → ParseResult`
- `preview(df, timezone) → PreviewResult`

The detector runs all parsers and selects the highest confidence above threshold (0.5). Below threshold → `UNKNOWN_FORMAT`. If two parsers are both above threshold and within `parser_ambiguous_margin` (0.15), preview returns `AMBIGUOUS_FORMAT` and requires an explicit parser. Strategy Tester detection requires the full entry/exit time and price set; Order History signatures (Status + Order ID + Fill Price) cannot be classified as Strategy Tester.

## Data Flow

**Manual exports:** CSV rows → executions → **Step 2.5** signed-position reconstruction → trades + trade_executions (allocated_quantity for flips). Step 1 FIFO reconstruction is obsolete.

**Activity Log:** Optional. If Order History is already imported, Activity Log fills share TradingView Order IDs and are skipped as duplicates. It is an alternative execution source (side inferred from “Call to place market order” lines) when Order History is not imported — not required for reconstruction after Order History.

**Strategy tester:** CSV rows → trades directly (one row = one round-trip)

## Key Design Decisions

1. **Raw preservation** — Every execution/trade stores `raw_row_json`.
2. **Decimal money** — No float for prices/P&L in persistence.
3. **UTC canonical** — All times stored as UTC; original string + timezone preserved.
4. **Fingerprint dedup** — Unique constraints on `(account_id, execution_fingerprint)` and `(account_id, trade_fingerprint)`.
5. **Idempotent imports** — Re-importing same file or overlapping export is safe.

## API

REST JSON under `/api/`. See OpenAPI at `/docs` when backend is running.

## Frontend

React SPA with Dashboard, Graphs, Trades, Signals, Exit Analyzer, Research, **Workflow**, Daily/Weekly Review, Risk, Import, Accounts, Market Data, and Settings. Proxies `/api` to backend via Vite dev server.

## Graphs (Step 3)

Interactive report discovery at `/graphs`:

- Many fixed report cards grouped by analytical topic
- Click buckets to drill down (exploration filters)
- Collapsible sections, sticky navigation, URL state
- See [docs/GRAPHS_AND_REPORTS.md](docs/GRAPHS_AND_REPORTS.md)
- Single pipeline: `GET /api/reports` → annotate once (behavior + market + excursion) → filter → aggregate `REPORT_DEFINITIONS`
- Market enrichment provenance: bars and derived features keyed by provider/feed/adjustment_mode (see [MARKET_DATA.md](docs/MARKET_DATA.md))
