"""Best-effort TRADE_RECORD / AUTO_TRADE_RECORD adapters.

No repository samples exist. Conservative parsing only.
Synthetic IDs never receive EXPLICIT_ID match confidence.
Ambiguous same-ticker/time records stay separate (include line hash).
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services.signals.errors import PineParseError
from app.services.signals.ids import normalize_strategy_version
from app.services.signals.parser import (
    ParsedEvent,
    event_fingerprint,
    parse_event_time,
    payload_hash_from_fields,
)
from app.utils.hashing import sha256_bytes
from app.utils.money import to_decimal


def synthetic_legacy_id(strategy_guess: str, ticker: str, entry_ms: int | str, disambiguator: str) -> str:
    """Include a content disambiguator so two incomplete records do not merge."""
    return f"LEGACY|{strategy_guess or 'UNKNOWN'}|{ticker}|{entry_ms}|{disambiguator[:12]}"


def try_parse_legacy(record_type: str, parts: list[str], raw_line: str, line_number: int) -> ParsedEvent | PineParseError | None:
    kind = record_type.strip().upper()
    if kind not in ("TRADE_RECORD", "AUTO_TRADE_RECORD"):
        return None
    # Positional best-effort: RECORD_TYPE, TICKER, DIRECTION, ENTRY_TIME, ...
    ticker = (parts[1] if len(parts) > 1 else "").strip().upper() or "UNKNOWN"
    direction = (parts[2] if len(parts) > 2 else "LONG").strip().upper()
    time_raw = parts[3] if len(parts) > 3 else ""
    try:
        event_time_utc, original, ms = parse_event_time(time_raw, None)
    except PineParseError as exc:
        return PineParseError("LEGACY_PARSE", exc.message, raw_line, {"kind": kind})
    if not ms:
        ms = int(event_time_utc.timestamp() * 1000)
    disambiguator = sha256_bytes(raw_line.encode("utf-8"))
    signal_id = synthetic_legacy_id("UNKNOWN", ticker, ms, disambiguator)
    origin = "UNKNOWN"
    fields = {
        "event_price": to_decimal(parts[4]) if len(parts) > 4 else None,
        "planned_entry_price": to_decimal(parts[4]) if len(parts) > 4 else None,
        "planned_stop_price": to_decimal(parts[5]) if len(parts) > 5 else None,
        "event_origin": origin,
        "ticker": ticker,
        "direction": direction,
    }
    iso = event_time_utc.isoformat()
    return ParsedEvent(
        record_type=kind,
        schema_version="legacy",
        signal_id=signal_id,
        strategy_key="UNKNOWN",
        strategy_version="",
        strategy_version_normalized=normalize_strategy_version(""),
        ticker=ticker,
        direction=direction if direction in ("LONG", "SHORT") else "LONG",
        timeframe="",
        event_origin=origin,
        event_type="ENTRY",
        event_time_utc=event_time_utc,
        event_time_original=original,
        event_time_ms=ms,
        event_price=fields["event_price"],
        planned_entry_price=fields["planned_entry_price"],
        planned_stop_price=fields["planned_stop_price"],
        reference_2r_price=None,
        suggested_shares=None,
        setup_quality=None,
        allowed_risk=None,
        planned_position_value=None,
        planned_exposure_pct=None,
        signal_gap_pct=None,
        signal_rvol=None,
        impulse_pct=None,
        retracement_pct=None,
        context_5m=None,
        above_vwap=None,
        above_ema9=None,
        volume_confirmed=None,
        session_label=None,
        mechanical_exit_reason=None,
        raw_line=raw_line,
        raw_payload={"record_type": kind, "parts": parts, "validation": "USER-DATA VALIDATION PENDING"},
        event_fingerprint=event_fingerprint(signal_id, "ENTRY", iso, None),
        payload_hash=payload_hash_from_fields(fields),
        legacy=True,
        line_number=line_number,
    )
