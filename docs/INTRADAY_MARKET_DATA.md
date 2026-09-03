# Intraday Market Data (Step 8)

## Architecture

Extends Step 4 `MarketDataProvider` with `get_intraday_bars()`.

```
Provider (Alpaca / Fake)
    ↓
market_intraday_bars (cache, normalized OHLCV)
    ↓
ExcursionEnrichmentService
    ↓
trade_excursions
```

## Cache policy (approved)

- **Full symbol-day session:** 04:00–20:00 America/New_York per ticker/trading date touched
- **No raw JSON by default** — normalized fields only; optional `LTA_INTRADAY_STORE_RAW_PAYLOAD=true`
- **No auto-pruning** — track DB size; advisories at ~1GB and ~2GB

## Sparse vs missing

Absent minute bars (no trades in that minute) are **not** provider failures. `SPARSE_INTERVAL` flag may apply. `MISSING_BARS` / `provider_missing_data` only when fetch genuinely failed or returned no usable data for required range.

## API

- `POST /api/excursions/enrich`
- `POST /api/excursions/recalculate` (cache-only)
- `GET /api/excursions/coverage`

## CLI

```bash
python -m app.cli.enrich_excursions --missing
python -m app.cli.enrich_excursions --recalculate --dry-run
```
