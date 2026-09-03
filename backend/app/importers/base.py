from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal


SourceType = Literal["TRADINGVIEW_MANUAL", "TRADINGVIEW_AUTO", "UNKNOWN"]


@dataclass
class NormalizedExecution:
    ticker: str
    side: str
    execution_time_utc: datetime
    execution_time_original: str
    timezone_original: str | None
    quantity: Decimal
    price: Decimal
    fees: Decimal | None = None
    order_id: str | None = None
    external_execution_id: str | None = None
    raw_row: dict[str, Any] = field(default_factory=dict)
    row_number: int = 0


@dataclass
class NormalizedTrade:
    ticker: str
    direction: str
    entry_time_utc: datetime
    exit_time_utc: datetime | None
    avg_entry_price: Decimal
    avg_exit_price: Decimal | None
    quantity: Decimal
    gross_pnl: Decimal | None = None
    fees: Decimal | None = None
    net_pnl: Decimal | None = None
    source_reported_pnl: Decimal | None = None
    status: str = "CLOSED"
    external_trade_id: str | None = None
    raw_row: dict[str, Any] = field(default_factory=dict)
    row_number: int = 0
    executions: list[NormalizedExecution] = field(default_factory=list)


@dataclass
class ParseResult:
    source_type: SourceType
    executions: list[NormalizedExecution] = field(default_factory=list)
    trades: list[NormalizedTrade] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    timezone_status: str = "OK"  # OK, REQUIRES_USER_INPUT
    row_count: int = 0


@dataclass
class PreviewResult:
    source_type: SourceType
    parser_name: str
    parser_version: str
    confidence: float
    detected_columns: list[str]
    row_count: int
    timezone_status: str
    sample_records: list[dict[str, Any]]
    warnings: list[str] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    parser_name: str
    parser_version: str
    source_type: SourceType
    confidence: float
    detected_columns: list[str]
    missing_fields: list[str] = field(default_factory=list)
    diagnostics: str = ""
