import logging
from decimal import Decimal

import polars as pl

from app.importers.aliases import ALIASES, find_column
from app.importers.base import DetectionResult, NormalizedTrade, ParseResult
from app.importers.base_parser import BaseParser, resolve_column, row_to_dict
from app.importers.exceptions import InvalidExecutionError
from app.utils.money import (
    calculate_gross_pnl,
    calculate_net_pnl,
    pnl_mismatch,
    quantize_price,
    quantize_quantity,
    to_decimal,
)
from app.utils.timezones import has_timezone_info, parse_timestamp

logger = logging.getLogger(__name__)


class TradingViewStrategyParser(BaseParser):
    name = "tradingview_strategy"
    version = "1.0.0"
    source_type = "TRADINGVIEW_AUTO"

    def can_parse(self, df: pl.DataFrame) -> DetectionResult:
        headers = df.columns
        missing = []

        checks = [
            ("ticker", ALIASES.ticker),
            ("entry_time", ALIASES.entry_time),
            ("exit_time", ALIASES.exit_time),
            ("entry_price", ALIASES.entry_price),
            ("exit_price", ALIASES.exit_price),
        ]
        score = 0.0
        for field, aliases in checks:
            col = find_column(headers, aliases)
            if col is None:
                missing.append(field)
            else:
                score += 1.0

        qty_col = find_column(headers, ALIASES.quantity)
        if qty_col:
            score += 0.5

        confidence = score / (len(checks) + 0.5)

        # Require the full entry/exit pair — do not silently classify execution
        # exports that merely share a similarly named column.
        if missing:
            confidence = min(confidence, 0.4)

        side_col = find_column(headers, ALIASES.side)
        if side_col and find_column(headers, ALIASES.order_type):
            confidence *= 0.5

        # Paper order-history signature is never Strategy Tester.
        if (
            find_column(headers, ALIASES.status)
            and find_column(headers, ALIASES.order_id)
            and find_column(headers, ["fill price"])
        ):
            confidence = min(confidence, 0.2)

        return DetectionResult(
            parser_name=self.name,
            parser_version=self.version,
            source_type=self.source_type,  # type: ignore
            confidence=min(1.0, max(0.0, confidence)),
            detected_columns=headers,
            missing_fields=missing,
            diagnostics="Strategy tester format detection",
        )

    def parse(self, df: pl.DataFrame, timezone: str | None = None) -> ParseResult:
        headers = df.columns
        ticker_col = resolve_column(headers, ALIASES.ticker, "ticker")
        entry_time_col = resolve_column(headers, ALIASES.entry_time, "entry_time")
        exit_time_col = resolve_column(headers, ALIASES.exit_time, "exit_time")
        entry_price_col = resolve_column(headers, ALIASES.entry_price, "entry_price")
        exit_price_col = resolve_column(headers, ALIASES.exit_price, "exit_price")

        qty_col = find_column(headers, ALIASES.quantity)
        pnl_col = find_column(headers, ALIASES.pnl)
        fees_col = find_column(headers, ALIASES.fees)
        trade_num_col = find_column(headers, ALIASES.trade_num)

        trades: list[NormalizedTrade] = []
        errors: list[dict] = []
        warnings: list[str] = []
        timezone_status = "OK"

        rows = df.to_dicts()
        for i, row in enumerate(rows, start=1):
            raw = row_to_dict(row)
            try:
                entry_ts = str(raw.get(entry_time_col, "") or "").strip()
                exit_ts = str(raw.get(exit_time_col, "") or "").strip()
                if not entry_ts:
                    raise InvalidExecutionError("Missing entry time")

                if (not has_timezone_info(entry_ts) or (exit_ts and not has_timezone_info(exit_ts))) and timezone is None:
                    timezone_status = "REQUIRES_USER_INPUT"

                entry_utc, _, entry_tz = parse_timestamp(entry_ts, timezone)
                exit_utc = None
                if exit_ts:
                    exit_utc, _, _ = parse_timestamp(exit_ts, timezone)

                entry_price = to_decimal(raw.get(entry_price_col))
                exit_price = to_decimal(raw.get(exit_price_col)) if raw.get(exit_price_col) not in (None, "") else None
                if entry_price is None or entry_price <= 0:
                    raise InvalidExecutionError("Invalid entry price")

                quantity = Decimal("1")
                if qty_col:
                    q = to_decimal(raw.get(qty_col))
                    if q and q > 0:
                        quantity = q

                direction = "LONG"
                dir_col = find_column(headers, ["signal", "direction"])
                if dir_col:
                    d = str(raw.get(dir_col, "")).lower()
                    if "short" in d:
                        direction = "SHORT"
                    elif "long" in d:
                        direction = "LONG"

                fees = None
                if fees_col:
                    fees = to_decimal(raw.get(fees_col))

                source_pnl = None
                if pnl_col:
                    source_pnl = to_decimal(raw.get(pnl_col))

                ext_id = None
                if trade_num_col:
                    ext_id = str(raw.get(trade_num_col))

                avg_entry = quantize_price(entry_price)
                avg_exit = quantize_price(exit_price) if exit_price else None
                qty = quantize_quantity(quantity)

                gross = None
                net = None
                if avg_exit is not None:
                    gross = calculate_gross_pnl(direction, avg_entry, avg_exit, qty)
                    net = calculate_net_pnl(gross, fees)

                trades.append(
                    NormalizedTrade(
                        ticker=str(raw.get(ticker_col, "")).strip().upper(),
                        direction=direction,
                        entry_time_utc=entry_utc,
                        exit_time_utc=exit_utc,
                        avg_entry_price=avg_entry,
                        avg_exit_price=avg_exit,
                        quantity=qty,
                        gross_pnl=gross,
                        fees=fees,
                        net_pnl=net if net is not None else source_pnl,
                        source_reported_pnl=source_pnl,
                        status="CLOSED" if exit_utc else "OPEN",
                        external_trade_id=ext_id if ext_id and ext_id != "None" else None,
                        raw_row=raw,
                        row_number=i,
                    )
                )
            except (InvalidExecutionError, ValueError) as e:
                errors.append({"row_number": i, "error_type": type(e).__name__, "message": str(e), "raw_row": raw})

        if timezone_status == "REQUIRES_USER_INPUT" and timezone is None:
            warnings.append("Timestamps lack timezone; user must select timezone before import.")

        return ParseResult(
            source_type=self.source_type,  # type: ignore
            trades=trades,
            errors=errors,
            warnings=warnings,
            timezone_status=timezone_status,
            row_count=len(rows),
        )
