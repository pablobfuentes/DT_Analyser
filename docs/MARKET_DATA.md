# Market Data

Step 4 adds optional historical market data enrichment via a provider abstraction.

## Configuration

| Variable | Description |
|----------|-------------|
| `LTA_MARKET_DATA_PROVIDER` | `none`, `alpaca`, or `fake` (tests) |
| `LTA_ALPACA_API_KEY_ID` | Alpaca API key |
| `LTA_ALPACA_API_SECRET_KEY` | Alpaca secret |
| `LTA_ALPACA_DATA_FEED` | `sip` (consolidated) or `iex` (partial) |
| `LTA_MARKET_BENCHMARK` | Default `SPY` |

Credentials are backend-only; never exposed to the frontend.

## Architecture

```
backend/app/market_data/
  base.py       MarketDataProvider interface
  models.py     DailyBar, FetchStats
  registry.py   Provider resolution + status
  alpaca.py     Alpaca historical bars
  fake.py       Offline test provider
  cache.py      market_daily_bars persistence
  quality.py    QualityStatus enums
```

## Workflow

1. **Enrich Missing** — fetch missing bars, compute features, link trades
2. **Recalculate Features** — recompute from cached bars only (no network)
3. **Refresh** — deliberate re-fetch from provider

## API

- `GET /api/market-data/status`
- `GET /api/market-data/coverage`
- `POST /api/market-data/enrich`
- `POST /api/market-data/recalculate`
- `POST /api/market-data/refresh`

## CLI

```bash
python -m app.cli.enrich_market_data --scope missing
python -m app.cli.enrich_market_data --recalculate
python -m app.cli.enrich_market_data --dry-run
```

## Data provenance

Every cached bar stores: `provider`, `feed`, `is_consolidated`, `adjustment_mode`, `fetched_at`.

Derived `instrument_day_features` (including SPY benchmark rows) are unique on:

`(symbol, trading_date, provider, feed, adjustment_mode, calculation_version)`

Switching IEX → SIP therefore stores a **new** derived row. `trade_market_features` keeps one active row per trade and points at the provenance-specific feature ids (overwrite-active policy).

There is no separate `benchmark_day_features` table; SPY uses the same table keyed by symbol + provenance.

## IEX / partial feed

Volume, RVOL50, and prior-day RVOL are marked `PARTIAL_FEED` and **excluded from default Graphs**. Price features (opening gap, SMA, ATR, day type, movement) remain available. Enable `include_partial_feed=true` to include partial volume dimensions.

## Corporate actions

`get_splits` is **not implemented** for Alpaca (`supports_splits=False`). Features carry `SPLIT_METADATA_UNAVAILABLE` in `quality_flags`. Rolling ATR/SMA across an undetected split can be wrong; this is documented, not silently claimed safe.

## Recalculate vs Refresh

| Action | Network | Bars |
|--------|---------|------|
| Enrich missing | Yes, only unprobed trading-day gaps | Insert / update today |
| Recalculate | **Never** | Cached only |
| Refresh | Yes, intentional | Overwrite same provenance |

Weekends and NYSE holidays are not missing bars. Provider fetch ranges are recorded in `market_cache_coverage` so newly listed symbols and holidays are not refetched forever.

## Live validation

FakeProvider tests ≠ live Alpaca validation. If `LTA_ALPACA_API_KEY_ID` / `LTA_ALPACA_API_SECRET_KEY` are unset, validation is **PENDING** (see STEP_3_4_AUDIT.md).
