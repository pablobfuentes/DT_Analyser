"""Timezone parsing: DST, premarket, regular session, explicit zones."""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from app.utils.timezones import has_timezone_info, parse_timestamp


def test_offset_timestamps_convert_to_utc():
    utc_dt, original, _tz = parse_timestamp("2026-02-01 09:30:00-05:00")
    assert utc_dt.tzinfo == timezone.utc
    assert utc_dt == datetime(2026, 2, 1, 14, 30, tzinfo=timezone.utc)
    assert original == "2026-02-01 09:30:00-05:00"


def test_naive_requires_timezone():
    with pytest.raises(ValueError, match="Timezone required"):
        parse_timestamp("2026-02-01 09:30:00")


@pytest.mark.parametrize(
    "zone,local,expected_utc",
    [
        ("America/New_York", "2026-02-01 09:30:00", datetime(2026, 2, 1, 14, 30, tzinfo=timezone.utc)),
        ("America/Mexico_City", "2026-02-01 09:30:00", datetime(2026, 2, 1, 15, 30, tzinfo=timezone.utc)),
        ("UTC", "2026-02-01 09:30:00", datetime(2026, 2, 1, 9, 30, tzinfo=timezone.utc)),
    ],
)
def test_supported_zones(zone, local, expected_utc):
    utc_dt, _, tz_name = parse_timestamp(local, zone)
    assert utc_dt == expected_utc
    assert tz_name == zone


def test_dst_spring_forward_new_york():
    """2026-03-08 02:00 US clocks spring forward; 09:30 EDT is UTC 13:30."""
    utc_dt, _, _ = parse_timestamp("2026-03-09 09:30:00", "America/New_York")
    local = utc_dt.astimezone(ZoneInfo("America/New_York"))
    assert local.hour == 9 and local.minute == 30
    assert utc_dt == datetime(2026, 3, 9, 13, 30, tzinfo=timezone.utc)


def test_dst_fall_back_new_york():
    """2026-11-01 02:00 US clocks fall back; 09:30 EST is UTC 14:30."""
    utc_dt, _, _ = parse_timestamp("2026-11-02 09:30:00", "America/New_York")
    assert utc_dt == datetime(2026, 11, 2, 14, 30, tzinfo=timezone.utc)


def test_premarket_new_york():
    utc_dt, _, _ = parse_timestamp("2026-09-02 04:00:00", "America/New_York")
    assert utc_dt == datetime(2026, 9, 2, 8, 0, tzinfo=timezone.utc)


def test_regular_session_new_york():
    utc_dt, _, _ = parse_timestamp("2026-09-02 09:30:00", "America/New_York")
    assert utc_dt == datetime(2026, 9, 2, 13, 30, tzinfo=timezone.utc)


def test_does_not_reinterpret_aware_utc():
    utc_dt, _, _ = parse_timestamp("2026-09-02T13:30:00+00:00", "America/New_York")
    assert utc_dt == datetime(2026, 9, 2, 13, 30, tzinfo=timezone.utc)


def test_has_timezone_info():
    assert has_timezone_info("2026-01-01T10:00:00Z")
    assert has_timezone_info("2026-01-01 10:00:00-05:00")
    assert not has_timezone_info("2026-01-01 10:00:00")
