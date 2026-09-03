# Local Trader Analyzer

A local-first trading journal and CSV importer inspired by Tradervue. Step 1 focuses on importing and normalizing TradingView CSV exports into a SQLite database.

## Requirements

- Python 3.12+
- Node.js 18+
- npm

## Installation

```bash
git clone <repo-url>
cd local-trader-analyzer
```

### Backend

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### Frontend

```bash
cd frontend
npm install
```

## Database Initialization

The SQLite database is created automatically on first backend startup at:

```
backend/data/trader_analyzer.db
```

Default accounts seeded:

- **Manual TradingView Account** (`TRADINGVIEW_MANUAL`)
- **AUTO Strategy Tester** (`TRADINGVIEW_AUTO`)

## Running Locally

Start the backend (from `backend/` with venv activated):

```bash
uvicorn app.main:app --reload --port 8001
```

Start the frontend (from `frontend/`):

```bash
npm run dev
```

Open http://localhost:5173

API docs: http://127.0.0.1:8001/docs

## Deploying (Netlify + Render)

The web UI deploys to **Netlify**; the API deploys to **Render** (Docker + SQLite on a persistent disk). See [Deployment](docs/DEPLOYMENT.md) for step-by-step setup and required environment variables (`BACKEND_URL` on Netlify, `LTA_CORS_ORIGINS` on Render).

## Dashboard (Step 2)

The dashboard is the default landing page at http://localhost:5173/

- Summary metrics (Net P&L, Win Rate, Avg Trade, etc.)
- Cumulative and daily P&L charts
- MANUAL vs AUTO comparison
- Daily results table with links to filtered trades
- Recent trades
- Account starting equity configuration at `/accounts`

See [Dashboard Metrics](docs/DASHBOARD_METRICS.md) for definitions.

Filter presets sync to URL query parameters.

## Graphs (Step 3)

Multi-dimensional report discovery at http://localhost:5173/graphs

- Fixed report cards by topic (Time, Trade Characteristics, Instrument, …)
- Click chart buckets to filter all reports (exploration filters)
- Collapsible sections, sticky navigation, URL bookmarking
- Reset Exploration preserves global date/account filters

See [Graphs and Reports](docs/GRAPHS_AND_REPORTS.md).

## Research Lab (Step 9)

Exploratory cohort comparison at http://localhost:5173/research

- Cohort A vs Cohort B using the same filter semantics as Graphs
- Default **PRE-ENTRY ONLY** (lookahead filters blocked)
- Scatter, 2D heatmap, rolling, ECDF, robustness, chronological validation
- Saved cohorts, research views, candidate rules (never auto-change Pine)

This is researcher tooling. Language stays Observed Pattern / Needs More Samples — not proven edge.

See [Research Lab](docs/RESEARCH_LAB.md), [Cohort Comparison](docs/COHORT_COMPARISON.md), [Research Timing](docs/RESEARCH_TIMING_AND_LOOKAHEAD.md), [Research Statistics](docs/RESEARCH_STATISTICS.md), [Candidate Rules](docs/CANDIDATE_RULES.md).

## Daily Workflow (Step 10)

After trading: drop Order History (and Pine) into the **Inbox**, open `/workflow`, complete Daily Review. Matching, risk, market/excursion enrichment, and backup run automatically while the backend is up.

```
python -m app.cli.process_inbox
python -m app.cli.finalize_day
python -m app.cli.backup
```

Set `LTA_DATA_DIR` for a production data root. Default still honors an existing `./data` folder.

See [Daily Workflow](docs/DAILY_WORKFLOW.md), [Automation](docs/AUTOMATION_WORKFLOW.md), [Journal](docs/JOURNAL.md), [Backup](docs/BACKUP_AND_RESTORE.md), [Data Directory](docs/DATA_DIRECTORY.md).

## Market Data Enrichment (Step 4)

Optional instrument and SPY benchmark enrichment at http://localhost:5173/market-data

Configure Alpaca (backend env only):

```bash
LTA_MARKET_DATA_PROVIDER=alpaca
LTA_ALPACA_API_KEY_ID=...
LTA_ALPACA_API_SECRET_KEY=...
LTA_ALPACA_DATA_FEED=sip   # or iex (partial feed)
```

Use **Enrich Missing Data** after import. Graphs Instrument and Market sections populate from cached daily bars.

- **Recalculate Features** — cached bars only, never hits the network
- **Refresh From Provider** — deliberate network fetch for the same provenance

IEX (`LTA_ALPACA_DATA_FEED=iex`) is a **partial feed**: volume/RVOL is excluded from default Graphs unless **Include Partial Feed** is enabled. Price features (gap, SMA, ATR) still apply.

Live Alpaca validation is environment-dependent; FakeProvider tests do not replace it.

See [Market Data](docs/MARKET_DATA.md), [Instrument Features](docs/INSTRUMENT_FEATURES.md), [Market Features](docs/MARKET_FEATURES.md), [Step 3/4 Audit](docs/STEP_3_4_AUDIT.md).

## Running Tests

### Backend

```bash
cd backend
pytest -v
```

### Frontend

```bash
cd frontend
npm test
```

## How CSV Import Works

1. **Upload** — Drop a TradingView CSV on the Import page.
2. **Detect** — The detector scores parsers (`tradingview_manual`, `tradingview_strategy`) by column aliases.
3. **Preview** — Normalized sample records shown; no database writes.
4. **Timezone** — If timestamps lack offset, you must choose `America/New_York`, `America/Mexico_City`, or `UTC`.
5. **Commit** — Select account, confirm, import transactionally.
6. **Dedupe** — Executions and trades fingerprinted; duplicates skipped.
7. **Reconstruct** — Manual execution rows are FIFO-matched into round-trip trades per ticker.

## Supported CSV Types

| Type | Source | Parser |
|------|--------|--------|
| Manual / Account export | Paper trading, order history | `tradingview_manual` |
| Strategy Tester | List of Trades export | `tradingview_strategy` |

Column names are matched via aliases (Symbol/Ticker, Qty/Quantity, etc.) — see `backend/app/importers/aliases.py`.

## Project Structure

```
local-trader-analyzer/
├── backend/          # FastAPI + SQLAlchemy + importers
├── frontend/         # React + Vite
└── docs/             # Architecture and guides
```

## Documentation

- [Step 1 Plan](docs/STEP_1_PLAN.md)
- [Step 3/4 Audit](docs/STEP_3_4_AUDIT.md)
- [Step 3 Plan — Graphs](docs/STEP_3_PLAN.md)
- [Graphs and Reports](docs/GRAPHS_AND_REPORTS.md)
- [Report Dimensions](docs/REPORT_DIMENSIONS.md)
- [Report Filter Engine](docs/REPORT_FILTER_ENGINE.md)
- [Research Lab](docs/RESEARCH_LAB.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Database Schema](docs/DATABASE_SCHEMA.md)
- [Adding a New Import Format](docs/ADDING_A_NEW_IMPORT_FORMAT.md)

## Environment Variables

Optional prefix `LTA_`:

| Variable | Default |
|----------|---------|
| `LTA_DATABASE_URL` | `sqlite:///./data/trader_analyzer.db` |
| `LTA_PNL_TOLERANCE` | `0.01` |
| `LTA_RESEARCH_MIN_SAMPLE` | `10` |
| `LTA_RESEARCH_BOOTSTRAP_SEED` | `20260902` |
| `LTA_RESEARCH_BOOTSTRAP_ITERATIONS` | `2000` |

## License

Private / local use.
