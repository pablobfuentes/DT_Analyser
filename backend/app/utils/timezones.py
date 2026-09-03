import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from dateutil import parser as date_parser

SUPPORTED_TIMEZONES = ["America/New_York", "America/Mexico_City", "UTC"]

TZ_OFFSET_PATTERN = re.compile(r"(Z|[+-]\d{2}:?\d{2})$", re.IGNORECASE)


def has_timezone_info(timestamp_str: str) -> bool:
    s = timestamp_str.strip()
    if TZ_OFFSET_PATTERN.search(s):
        return True
    if "UTC" in s.upper():
        return True
    return False


def parse_timestamp(
    value: str,
    assumed_timezone: str | None = None,
) -> tuple[datetime, str, str | None]:
    """Parse timestamp to UTC-aware datetime.

    Returns (utc_dt, original_string, detected_or_assumed_timezone).
    """
    original = value.strip()
    if not original:
        raise ValueError("Empty timestamp")

    if has_timezone_info(original):
        dt = date_parser.isoparse(original.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        utc_dt = dt.astimezone(timezone.utc)
        tz_name = str(dt.tzinfo) if dt.tzinfo else "UTC"
        return utc_dt, original, tz_name

    if assumed_timezone is None:
        raise ValueError("Timezone required for naive timestamp")

    local_tz = ZoneInfo(assumed_timezone)
    naive = date_parser.parse(original)
    if naive.tzinfo is not None:
        naive = naive.replace(tzinfo=None)
    local_dt = naive.replace(tzinfo=local_tz)
    utc_dt = local_dt.astimezone(timezone.utc)
    return utc_dt, original, assumed_timezone


def holding_seconds(entry: datetime, exit: datetime) -> int:
    return int((exit - entry).total_seconds())
