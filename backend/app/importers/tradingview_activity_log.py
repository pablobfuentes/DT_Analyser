import logging
from datetime import datetime
from decimal import Decimal

import polars as pl

from app.importers.aliases import ALIASES, find_column
from app.importers.base import DetectionResult, NormalizedExecution, ParseResult
from app.importers.base_parser import BaseParser, resolve_column, row_to_dict
from app.importers.exceptions import InvalidExecutionError
from app.importers.normalization import normalize_ticker
from app.importers.patterns import EXECUTED_PATTERN, ORDER_CALL_PATTERN
from app.utils.money import quantize_price, quantize_quantity, to_decimal
from app.utils.timezones import has_timezone_info, parse_timestamp

logger = logging.getLogger(__name__)

SIDE_MAP = {
    "buy": "BUY",
    "sell": "SELL",
}


def _parse_naive_time(value: str) -> datetime | None:
    value = value.strip()
    if not value:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _resolve_side(
    time_str: str,
    ticker: str,
    qty: Decimal,
    side_lookup: dict[tuple[str, str, str], str],
    *,
    max_seconds: int = 2,
) -> str | None:
    qty_key = str(int(qty)) if qty == int(qty) else str(qty)
    side = side_lookup.get((time_str, ticker, qty_key))
    if side:
        return side

    exec_dt = _parse_naive_time(time_str)
    if exec_dt is None:
        return None

    for (t, sym, q), s in side_lookup.items():
        if sym != ticker:
            continue
        q_dec = to_decimal(q)
        if q_dec is None or q_dec != qty:
            continue
        call_dt = _parse_naive_time(t)
        if call_dt is None:
            continue
        if abs((exec_dt - call_dt).total_seconds()) <= max_seconds:
            return s
    return None


class TradingViewActivityLogParser(BaseParser):
    """TradingView Paper Trading activity log (Time + Text event stream)."""

    name = "tradingview_activity_log"
    version = "1.0.0"
    source_type = "TRADINGVIEW_MANUAL"

    def can_parse(self, df: pl.DataFrame) -> DetectionResult:
        headers = df.columns
        time_col = find_column(headers, ALIASES.timestamp)
        text_col = find_column(headers, ALIASES.message)

        missing = []
        if not time_col:
            missing.append("timestamp")
        if not text_col:
            missing.append("message")

        if missing:
            return DetectionResult(
                parser_name=self.name,
                parser_version=self.version,
                source_type=self.source_type,  # type: ignore
                confidence=0.0,
                detected_columns=headers,
                missing_fields=missing,
            )

        rows = df.to_dicts()
        execution_hits = 0
        for row in rows:
            text = str(row.get(text_col, "") or "")
            if EXECUTED_PATTERN.search(text):
                execution_hits += 1

        if execution_hits == 0:
            confidence = 0.2 if time_col and text_col else 0.0
        elif time_col and text_col and execution_hits >= 3:
            confidence = 0.95
        else:
            ratio = execution_hits / max(len(rows), 1)
            confidence = min(1.0, 0.7 + ratio * 0.3)

        return DetectionResult(
            parser_name=self.name,
            parser_version=self.version,
            source_type=self.source_type,  # type: ignore
            confidence=confidence,
            detected_columns=headers,
            missing_fields=missing,
            diagnostics=f"execution_messages={execution_hits}/{len(rows)}",
        )

    def parse(self, df: pl.DataFrame, timezone: str | None = None) -> ParseResult:
        headers = df.columns
        time_col = resolve_column(headers, ALIASES.timestamp, "timestamp")
        text_col = resolve_column(headers, ALIASES.message, "message")

        rows = df.to_dicts()

        # Build side lookup from companion "Call to place market order" lines
        side_lookup: dict[tuple[str, str, str], str] = {}
        for row in rows:
            raw = row_to_dict(row)
            text = str(raw.get(text_col, "") or "")
            match = ORDER_CALL_PATTERN.search(text)
            if not match:
                continue
            side = SIDE_MAP.get(match.group(1).lower(), "UNKNOWN")
            qty = match.group(2)
            ticker = normalize_ticker(match.group(3))
            time_key = str(raw.get(time_col, "") or "").strip()
            side_lookup[(time_key, ticker, qty)] = side

        executions: list[NormalizedExecution] = []
        errors: list[dict] = []
        warnings: list[str] = []
        timezone_status = "OK"
        skipped_rows = 0

        for i, row in enumerate(rows, start=1):
            raw = row_to_dict(row)
            text = str(raw.get(text_col, "") or "")
            match = EXECUTED_PATTERN.search(text)
            if not match:
                skipped_rows += 1
                continue

            try:
                order_id = match.group(1)
                ticker = normalize_ticker(match.group(2))
                price = to_decimal(match.group(3))
                qty = to_decimal(match.group(4))
                time_str = str(raw.get(time_col, "") or "").strip()

                if not time_str:
                    raise InvalidExecutionError("Missing timestamp")
                if price is None or price <= 0:
                    raise InvalidExecutionError(f"Invalid price in: {text}")
                if qty is None or qty <= 0:
                    raise InvalidExecutionError(f"Invalid quantity in: {text}")

                if not has_timezone_info(time_str) and timezone is None:
                    timezone_status = "REQUIRES_USER_INPUT"
                    continue

                utc_dt, original, tz = parse_timestamp(time_str, timezone)

                side = _resolve_side(time_str, ticker, qty, side_lookup)
                if not side:
                    raise InvalidExecutionError(f"Could not determine side for order {order_id}")

                executions.append(
                    NormalizedExecution(
                        ticker=ticker,
                        side=side,
                        execution_time_utc=utc_dt,
                        execution_time_original=original,
                        timezone_original=tz,
                        quantity=quantize_quantity(qty),
                        price=quantize_price(price),
                        order_id=order_id,
                        external_execution_id=order_id,
                        raw_row=raw,
                        row_number=i,
                    )
                )
            except (InvalidExecutionError, ValueError) as e:
                errors.append({"row_number": i, "error_type": type(e).__name__, "message": str(e), "raw_row": raw})

        if skipped_rows:
            warnings.append(f"Skipped {skipped_rows} non-execution log lines")

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
