from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AccountCreate(BaseModel):
    name: str
    source: str = "TRADINGVIEW_MANUAL"
    currency: str = "USD"
    is_simulated: bool = False
    starting_equity: Decimal | None = None


class AccountUpdate(BaseModel):
    name: str | None = None
    starting_equity: Decimal | None = None
    currency: str | None = None


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    source: str
    currency: str
    is_simulated: bool
    starting_equity: Decimal | None = None
    created_at: datetime
    updated_at: datetime


class ImportPreviewResponse(BaseModel):
    filename: str
    file_hash: str
    detected_source_type: str | None = None
    parser: str | None = None
    confidence: float | None = None
    detected_columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    timezone_status: str = "OK"
    sample_normalized_records: list[dict] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    error: str | None = None
    message: str | None = None
    options: list[str] | None = None


class ImportCommitRequest(BaseModel):
    file_hash: str
    account_id: int
    parser_name: str
    timezone: str | None = None


class ImportCommitResponse(BaseModel):
    import_batch_id: int
    raw_rows: int
    valid_rows: int
    imported_executions: int
    imported_trades: int
    duplicate_executions: int
    duplicate_trades: int
    errors: int


class ImportBatchResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    file_hash: str
    source_type: str
    parser_name: str
    parser_version: str
    account_id: int
    import_started_at: datetime
    import_completed_at: datetime | None
    row_count_raw: int
    row_count_valid: int
    row_count_imported: int
    row_count_duplicate: int
    row_count_error: int
    status: str
    error_message: str | None
    metadata_json: str | None


class TradeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    source_type: str
    ticker: str
    direction: str
    entry_time_utc: datetime
    exit_time_utc: datetime | None
    avg_entry_price: Decimal
    avg_exit_price: Decimal | None
    quantity: Decimal
    gross_pnl: Decimal | None
    fees: Decimal | None
    net_pnl: Decimal | None
    source_reported_pnl: Decimal | None
    pnl_mismatch_flag: bool
    holding_seconds: int | None
    status: str
    raw_row_json: str | None
    initial_stop_price: Decimal | None = None
    initial_risk_per_share: Decimal | None = None
    initial_risk_amount: Decimal | None = None
    r_multiple: Decimal | None = None
    risk_source: str | None = None
    risk_notes: str | None = None
    risk_updated_at: datetime | None = None
    created_at: datetime


class TradeRiskUpdate(BaseModel):
    initial_stop_price: Decimal | None = None
    initial_risk_amount: Decimal | None = None
    risk_source: str = "MANUAL"
    risk_notes: str | None = None


class TradeRiskResponse(BaseModel):
    id: int
    initial_stop_price: Decimal | None
    initial_risk_per_share: Decimal | None
    initial_risk_amount: Decimal | None
    r_multiple: Decimal | None
    risk_source: str | None
    risk_notes: str | None
    risk_updated_at: datetime | None
    warnings: list[str] = Field(default_factory=list)


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    account_id: int
    import_batch_id: int
    ticker: str
    side: str
    execution_time_utc: datetime
    execution_time_original: str
    timezone_original: str | None
    quantity: Decimal
    price: Decimal
    fees: Decimal | None
    order_id: str | None
    raw_row_json: str
    created_at: datetime


class TradeExecutionLink(BaseModel):
    execution: ExecutionResponse
    role: str
    allocated_quantity: Decimal


class PaginatedTrades(BaseModel):
    items: list[TradeResponse]
    total: int
    page: int
    page_size: int


class PaginatedExecutions(BaseModel):
    items: list[ExecutionResponse]
    total: int
    page: int
    page_size: int


class TradeDetailResponse(TradeResponse):
    executions: list[ExecutionResponse] = Field(default_factory=list)
    execution_links: list[TradeExecutionLink] = Field(default_factory=list)
    import_batches: list[ImportBatchResponse] = Field(default_factory=list)
    planned: dict | None = None
    actual_risk: dict | None = None
    signal_links: list[dict] = Field(default_factory=list)
