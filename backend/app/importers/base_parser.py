import logging
from abc import ABC, abstractmethod
from pathlib import Path

import polars as pl

from app.importers.base import DetectionResult, ParseResult, PreviewResult
from app.importers.exceptions import AmbiguousColumnError, MissingRequiredColumnError

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    name: str = "base"
    version: str = "1.0.0"
    source_type: str = "UNKNOWN"

    @abstractmethod
    def can_parse(self, df: pl.DataFrame) -> DetectionResult:
        """Return confidence score 0.0-1.0."""

    @abstractmethod
    def parse(self, df: pl.DataFrame, timezone: str | None = None) -> ParseResult:
        """Parse full dataframe into normalized records."""

    def preview(
        self, df: pl.DataFrame, timezone: str | None = None, sample_size: int = 10
    ) -> PreviewResult:
        detection = self.can_parse(df)
        result = self.parse(df.head(sample_size * 5) if df.height > sample_size * 5 else df, timezone)
        samples = self._to_sample_records(result, sample_size)
        return PreviewResult(
            source_type=self.source_type,  # type: ignore
            parser_name=self.name,
            parser_version=self.version,
            confidence=detection.confidence,
            detected_columns=detection.detected_columns,
            row_count=df.height,
            timezone_status=result.timezone_status,
            sample_records=samples,
            warnings=result.warnings,
            errors=result.errors,
            missing_fields=detection.missing_fields,
        )

    def _to_sample_records(self, result: ParseResult, sample_size: int) -> list[dict]:
        records = []
        if result.trades:
            for t in result.trades[:sample_size]:
                records.append(
                    {
                        "type": "trade",
                        "ticker": t.ticker,
                        "direction": t.direction,
                        "entry_time": t.entry_time_utc.isoformat(),
                        "exit_time": t.exit_time_utc.isoformat() if t.exit_time_utc else None,
                        "quantity": str(t.quantity),
                        "entry_price": str(t.avg_entry_price),
                        "exit_price": str(t.avg_exit_price) if t.avg_exit_price else None,
                        "pnl": str(t.net_pnl or t.gross_pnl or ""),
                    }
                )
        elif result.executions:
            for e in result.executions[:sample_size]:
                records.append(
                    {
                        "type": "execution",
                        "ticker": e.ticker,
                        "side": e.side,
                        "time": e.execution_time_utc.isoformat(),
                        "quantity": str(e.quantity),
                        "price": str(e.price),
                    }
                )
        return records


def read_csv(path: str | Path) -> pl.DataFrame:
    return pl.read_csv(str(path), infer_schema_length=1000, ignore_errors=True)


def row_to_dict(row: dict) -> dict:
    return {k: (None if v == "" or (isinstance(v, float) and str(v) == "nan") else v) for k, v in row.items()}


def resolve_column(headers: list[str], aliases: list[str], field_name: str) -> str:
    from app.importers.aliases import find_column

    col = find_column(headers, aliases)
    if col is None:
        raise MissingRequiredColumnError(
            f"Missing required column for {field_name}",
            field=field_name,
            available_columns=headers,
        )
    if col.startswith("__AMBIGUOUS__:"):
        options = col.split(":", 1)[1].split(",")
        raise AmbiguousColumnError(
            f"Ambiguous column mapping for {field_name}",
            field=field_name,
            options=options,
        )
    return col
