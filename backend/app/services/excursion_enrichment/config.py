"""Centralized Step 8 excursion configuration."""

from decimal import Decimal

CALCULATION_VERSION = "1"

# NY extended session window for symbol-day cache (04:00–20:00 America/New_York)
SESSION_START_HOUR = 4
SESSION_END_HOUR = 20

INTRADAY_TIMEFRAME = "1Min"

# Best Capture table — minimum MFE R for eligibility
BEST_CAPTURE_MIN_MFE_R = Decimal("0.50")

# Post-exit research windows (minutes)
POST_EXIT_WINDOWS_MIN = (5, 15, 30)

# Loss-beyond-style tolerance for efficiency over 100 flag (informational)
EFFICIENCY_OVER_100_FLAG = True
