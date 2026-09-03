from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class DashboardSummary(BaseModel):
    trades: int = 0
    wins: int = 0
    losses: int = 0
    breakeven: int = 0
    net_pnl: str | None = None
    gross_pnl: str | None = None
    fees: str | None = None
    win_rate: str | None = None
    avg_trade: str | None = None
    avg_winner: str | None = None
    avg_loser: str | None = None
    best_trade: str | None = None
    worst_trade: str | None = None
    avg_hold_seconds: int | None = None


class DashboardEquity(BaseModel):
    starting_equity: str | None = None
    account_starting_equity: str | None = None
    current_realized_equity: str | None = None
    realized_return_pct: str | None = None
    available: bool = False
    reason: str | None = None


class DashboardDailyRow(BaseModel):
    date: str
    trades: int
    wins: int
    losses: int
    breakeven: int
    win_rate: str | None = None
    gross_pnl: str
    fees: str
    net_pnl: str
    cumulative_pnl: str
    day_type: str


class DashboardRecentTrade(BaseModel):
    id: int
    exit_time_utc: str | None
    ticker: str
    source_type: str
    direction: str
    quantity: str
    avg_entry_price: str
    avg_exit_price: str | None
    net_pnl: str
    holding_seconds: int | None = None


class DashboardResponse(BaseModel):
    filters: dict
    summary: DashboardSummary
    secondary: dict
    equity: DashboardEquity
    daily: list[DashboardDailyRow] = Field(default_factory=list)
    cumulative: list[dict] = Field(default_factory=list)
    source_comparison: dict
    source_comparison_advanced: dict = Field(default_factory=dict)
    recent_trades: list[DashboardRecentTrade] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    empty: bool = False
    advanced: dict = Field(default_factory=dict)
    r_distribution: list[dict] = Field(default_factory=list)
    drawdown_series: list[dict] = Field(default_factory=list)
    equity_series: list[dict] = Field(default_factory=list)
    cumulative_r_series: list[dict] = Field(default_factory=list)
