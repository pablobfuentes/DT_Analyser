"""TradingView activity-log message patterns (extensible, not tied to specific files)."""

import re

# Order 3478788000 for symbol NASDAQ:OLOX has been executed at price 1.1300 for 100 units
EXECUTED_PATTERN = re.compile(
    r"Order\s+(\d+)\s+for\s+symbol\s+(\S+)\s+has\s+been\s+executed\s+at\s+price\s+([\d.]+)\s+for\s+(\d+)\s+units",
    re.IGNORECASE,
)

# Call to place market order to buy 100 units of symbol NASDAQ:OLOX
ORDER_CALL_PATTERN = re.compile(
    r"Call\s+to\s+place\s+market\s+order\s+to\s+(buy|sell)\s+(\d+)\s+units\s+of\s+symbol\s+(\S+)",
    re.IGNORECASE,
)

# Future: closed position / realized P&L lines when present in exports
CLOSED_POSITION_PATTERN = re.compile(
    r"(?:position\s+closed|realized\s+p\s*&?\s*l|closed\s+position)",
    re.IGNORECASE,
)

REALIZED_PNL_PATTERN = re.compile(
    r"(?:realized\s+p\s*&?\s*l|p\s*&?\s*l)[:\s]+(-?[\d,.]+)",
    re.IGNORECASE,
)
