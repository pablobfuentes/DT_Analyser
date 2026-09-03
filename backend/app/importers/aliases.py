"""Column alias configuration for CSV parsers."""

from dataclasses import dataclass, field


@dataclass
class ColumnAliases:
    ticker: list[str] = field(default_factory=lambda: ["ticker", "symbol", "instrument", "sym"])
    side: list[str] = field(
        default_factory=lambda: ["side", "action", "buy/sell", "direction"]
    )
    order_type: list[str] = field(
        default_factory=lambda: ["type", "order type", "ordertype"]
    )
    status: list[str] = field(
        default_factory=lambda: ["status", "state", "order status"]
    )
    quantity: list[str] = field(
        default_factory=lambda: ["quantity", "qty", "shares", "size", "amount"]
    )
    price: list[str] = field(
        default_factory=lambda: [
            "fill price",
            "price",
            "execution price",
            "avg price",
            "fillprice",
        ]
    )
    fees: list[str] = field(default_factory=lambda: ["fees", "fee", "commission"])
    timestamp: list[str] = field(
        default_factory=lambda: [
            "closing time",
            "close time",
            "execution time",
            "fill time",
            "date/time",
            "datetime",
            "date time",
            "placing time",
            "place time",
            "timestamp",
            "time",
            "date",
        ]
    )
    order_id: list[str] = field(default_factory=lambda: ["order id", "order_id", "orderid"])
    execution_id: list[str] = field(
        default_factory=lambda: ["execution id", "execution_id", "trade id", "id"]
    )
    pnl: list[str] = field(
        default_factory=lambda: ["p&l", "pnl", "profit", "net p&l", "net pnl", "pl"]
    )

    # Strategy tester specific
    entry_time: list[str] = field(
        default_factory=lambda: ["entry time", "entry date", "entry datetime", "date/time"]
    )
    exit_time: list[str] = field(
        default_factory=lambda: ["exit time", "exit date", "exit datetime"]
    )
    entry_price: list[str] = field(
        default_factory=lambda: ["entry price", "entry", "avg entry price"]
    )
    exit_price: list[str] = field(
        default_factory=lambda: ["exit price", "exit", "avg exit price"]
    )
    trade_num: list[str] = field(default_factory=lambda: ["trade #", "trade#", "trade number"])

    # Activity log
    message: list[str] = field(
        default_factory=lambda: ["text", "message", "description", "event", "details"]
    )


ALIASES = ColumnAliases()


def normalize_header(header: str) -> str:
    return header.strip().lower().replace("_", " ")


def find_column(headers: list[str], aliases: list[str]) -> str | None:
    """Return the first header matching aliases in priority order."""
    normalized = {normalize_header(h): h for h in headers}
    for alias in aliases:
        key = normalize_header(alias)
        if key in normalized:
            return normalized[key]
    return None


def find_all_columns(headers: list[str], aliases: list[str]) -> list[str]:
    """Return all headers matching any alias (for ambiguity detection)."""
    normalized = {normalize_header(h): h for h in headers}
    matches: list[str] = []
    for alias in aliases:
        key = normalize_header(alias)
        if key in normalized and normalized[key] not in matches:
            matches.append(normalized[key])
    return matches
