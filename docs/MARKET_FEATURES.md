# Market (Benchmark) Features

Default benchmark: **SPY** (`LTA_MARKET_BENCHMARK`).

Computed with the same daily-feature engine as instruments and stored in `instrument_day_features` for symbol `SPY` under the same provider/feed/adjustment provenance. All trades on a given NY date share that one benchmark row (via `trade_market_features.benchmark_feature_id`).

## SPY Opening Gap — PRE_ENTRY

```
market_gap_pct = (spy_open - prior_spy_close) / prior_spy_close * 100
```

Report dimension: `market_gap_bucket`

## SPY Movement — END_OF_DAY

```
market_movement_pct = (spy_close - prior_spy_close) / prior_spy_close * 100
```

Report dimension: `market_movement_bucket`

## SPY Day Type — END_OF_DAY

Same classification engine as instrument day type.

Report dimension: `market_day_type`

All trades on the same NY trading date share identical benchmark context.

## Graphs section

The **Market** section is unavailable until a provider is configured or benchmark features exist. Once enriched, three reports activate in Graphs.
