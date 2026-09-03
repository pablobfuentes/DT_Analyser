# Adding a New Import Format

This guide explains how to add a broker or CSV format beyond TradingView.

## TradingView formats (Step 1)

| Export | Parser | Columns |
|--------|--------|---------|
| Strategy Tester "List of Trades" | `tradingview_strategy` | Symbol, Entry/Exit Time, Entry/Exit Price, Qty, P&L |
| Paper Trading order history | `tradingview_manual` | Symbol, Side, Fill price, Closing time, Status, Order ID |
| Paper Trading activity log | `tradingview_activity_log` | Time, Text (execution event messages) |

Activity log lines are parsed via regex patterns in `app/importers/patterns.py`. Execution rows dedupe against order history by **Order ID**.

Regression fixtures: `tests/fixtures/tv_paper_*.csv`, `strategy_tester.csv`.

## 1. Create a Parser Class

Add a file under `backend/app/importers/`, e.g. `alpaca_manual.py`:

```python
from app.importers.base_parser import BaseParser, resolve_column
from app.importers.base import DetectionResult, ParseResult

class AlpacaManualParser(BaseParser):
    name = "alpaca_manual"
    version = "1.0.0"
    source_type = "ALPACA_MANUAL"

    def can_parse(self, df) -> DetectionResult:
        # Score based on expected columns
        ...

    def parse(self, df, timezone=None) -> ParseResult:
        # Return ParseResult with executions or trades
        ...
```

## 2. Register Column Aliases

Extend `backend/app/importers/aliases.py` or define parser-specific aliases:

```python
ALIASES.ticker  # already includes Symbol, Ticker, Instrument
```

Add new aliases if your broker uses different headers.

## 3. Register with Detector

In `backend/app/importers/detector.py`:

```python
from app.importers.alpaca_manual import AlpacaManualParser

PARSERS = [
    TradingViewStrategyParser(),
    TradingViewManualParser(),
    AlpacaManualParser(),  # add here
]
```

Order matters for tie-breaking; more specific parsers should come first.

## 4. Return the Right Record Type

- **Execution-based brokers** — Return `ParseResult(executions=[...])`. The import service will FIFO-reconstruct trades.
- **Round-trip row brokers** — Return `ParseResult(trades=[...])` directly.

Always populate `raw_row` on each record.

## 5. Add Tests

1. Create fixture CSV in `backend/tests/fixtures/`
2. Add detection test in `test_import_detection.py`
3. Add import test in `test_import_manual.py` or new file

## 6. Confidence Scoring Guidelines

- Return confidence 0.0–1.0 based on matched required columns.
- Never guess below threshold — let detector return `UNKNOWN_FORMAT`.
- Raise `AmbiguousColumnError` if multiple columns match one field.

## 7. Timezone Handling

Use `app.utils.timezones.parse_timestamp()`:

- If CSV has offset → auto-detect
- If naive → require user timezone in preview/commit

## 8. Deduplication

Fingerprints are auto-computed in `app/services/deduplication.py`. Override with `external_execution_id` or `external_trade_id` if your CSV provides stable IDs.

## 9. Account Source Type

When creating accounts for the new source, use a distinct `source` value (e.g. `ALPACA_MANUAL`).

## Checklist

- [ ] Parser class with `can_parse`, `parse`, inherits `BaseParser`
- [ ] Registered in `PARSERS`
- [ ] Column aliases documented
- [ ] Fixture CSV + tests
- [ ] Raw row JSON preserved
- [ ] Timezone behavior tested
