import logging
from decimal import Decimal

import polars as pl

from app.importers.aliases import ALIASES, find_column
from app.importers.base import DetectionResult, NormalizedExecution, ParseResult
from app.importers.base_parser import BaseParser, resolve_column, row_to_dict
from app.importers.exceptions import InvalidExecutionError
from app.importers.normalization import normalize_ticker
from app.utils.money import quantize_price, quantize_quantity, to_decimal
from app.utils.timezones import has_timezone_info, parse_timestamp

logger = logging.getLogger(__name__)

SIDE_MAP = {
    "buy": "BUY",
    "sell": "SELL",
    "sell short": "SELL_SHORT",
    "short": "SELL_SHORT",
    "buy to cover": "BUY_TO_COVER",
    "cover": "BUY_TO_COVER",
    "b": "BUY",
    "s": "SELL",
}

FILLED_STATUS = {"filled", "fill", "executed", "complete", "completed"}


class TradingViewManualParser(BaseParser):
    name = "tradingview_manual"
    version = "1.1.0"
    source_type = "TRADINGVIEW_MANUAL"

    REQUIRED = ["ticker", "side", "quantity", "price", "timestamp"]

    def can_parse(self, df: pl.DataFrame) -> DetectionResult:
        headers = df.columns
        missing = []
        scores = {}

        for field, aliases in [
            ("ticker", ALIASES.ticker),
            ("side", ALIASES.side),
            ("quantity", ALIASES.quantity),
            ("price", ALIASES.price),
            ("timestamp", ALIASES.timestamp),
        ]:
            col = find_column(headers, aliases)
            if col is None:
                missing.append(field)
                scores[field] = 0.0
            else:
                scores[field] = 1.0

        entry_col = find_column(headers, ALIASES.entry_time)
        exit_col = find_column(headers, ALIASES.exit_time)
        if (
            entry_col
            and exit_col
        ):
            strategy_penalty = 0.3
        else:
            strategy_penalty = 0.0

        # Paper trading order history signature
        paper_bonus = 0.0
        status_col = find_column(headers, ALIASES.status)
        order_id_col = find_column(headers, ALIASES.order_id)
        if (
            status_col
            and order_id_col
            and find_column(headers, ["fill price"])
        ):
            paper_bonus = 0.05

        confidence = sum(scores.values()) / len(scores) - strategy_penalty + paper_bonus
        confidence = max(0.0, min(1.0, confidence))

        return DetectionResult(
            parser_name=self.name,
            parser_version=self.version,
            source_type=self.source_type,  # type: ignore
            confidence=confidence,
            detected_columns=headers,
            missing_fields=missing,
            diagnostics=f"Field scores: {scores}",
        )

    def parse(self, df: pl.DataFrame, timezone: str | None = None) -> ParseResult:
        headers = df.columns
        ticker_col = resolve_column(headers, ALIASES.ticker, "ticker")
        side_col = resolve_column(headers, ALIASES.side, "side")
        qty_col = resolve_column(headers, ALIASES.quantity, "quantity")
        price_col = resolve_column(headers, ALIASES.price, "price")
        time_col = resolve_column(headers, ALIASES.timestamp, "timestamp")

        fees_col = find_column(headers, ALIASES.fees)
        order_col = find_column(headers, ALIASES.order_id)
        status_col = find_column(headers, ALIASES.status)
        placing_time_col = find_column(headers, ["placing time", "place time"])

        executions: list[NormalizedExecution] = []
        errors: list[dict] = []
        warnings: list[str] = []
        timezone_status = "OK"
        skipped_non_filled = 0

        rows = df.to_dicts()
        for i, row in enumerate(rows, start=1):
            raw = row_to_dict(row)
            try:
                if status_col:
                    status = str(raw.get(status_col, "") or "").strip().lower()
                    if status and status not in FILLED_STATUS:
                        skipped_non_filled += 1
                        continue

                ts_str = str(raw.get(time_col, "") or "").strip()
                if not ts_str and placing_time_col:
                    ts_str = str(raw.get(placing_time_col, "") or "").strip()
                if not ts_str:
                    raise InvalidExecutionError("Missing timestamp")

                if not has_timezone_info(ts_str) and timezone is None:
                    timezone_status = "REQUIRES_USER_INPUT"
                    continue

                utc_dt, original, tz = parse_timestamp(ts_str, timezone)

                side_raw = str(raw.get(side_col, "") or "").strip().lower()
                side = SIDE_MAP.get(side_raw, "UNKNOWN")
                if side == "UNKNOWN":
                    raise InvalidExecutionError(f"Unknown side: {side_raw}")

                qty = to_decimal(raw.get(qty_col))
                price = to_decimal(raw.get(price_col))
                if qty is None or qty <= 0:
                    raise InvalidExecutionError(f"Invalid quantity: {raw.get(qty_col)}")
                if price is None or price <= 0:
                    raise InvalidExecutionError(f"Invalid price: {raw.get(price_col)}")

                fees = None
                if fees_col:
                    fees = to_decimal(raw.get(fees_col))

                order_id = (
                    str(raw.get(order_col)).strip()
                    if order_col
                    else None
                )
                if order_id in (None, "", "None"):
                    order_id = None

                executions.append(
                    NormalizedExecution(
                        ticker=normalize_ticker(raw.get(ticker_col, "")),
                        side=side,
                        execution_time_utc=utc_dt,
                        execution_time_original=original,
                        timezone_original=tz,
                        quantity=quantize_quantity(abs(qty)),
                        price=quantize_price(price),
                        fees=fees,
                        order_id=order_id,
                        external_execution_id=order_id,
                        raw_row=raw,
                        row_number=i,
                    )
                )
            except (InvalidExecutionError, ValueError) as e:
                errors.append({"row_number": i, "error_type": type(e).__name__, "message": str(e), "raw_row": raw})

        if skipped_non_filled:
            warnings.append(f"Skipped {skipped_non_filled} non-filled orders (Cancelled/Rejected/etc.)")

        if timezone_status == "REQUIRES_USER_INPUT" and timezone is None:
            warnings.append("Timestamps lack timezone; user must select timezone before import.")

        return ParseResult(
            source_type=self.source_type,  # type: ignore
            executions=executions,
            errors=errors,
            warnings=warnings,
            timezone_status=timezone_status,
            row_count=len(rows),
        )
