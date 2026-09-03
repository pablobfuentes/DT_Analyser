"""Parse Pine Logs into typed signal events. Observer import only — no market recalc."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.services.signals.errors import PineParseError
from app.services.signals.ids import normalize_strategy_version
from app.utils.analytics import analytics_tz
from app.utils.money import to_decimal

SCHEMA_1_COLUMNS = [
    "RECORD_TYPE",
    "SCHEMA_VERSION",
    "SIGNAL_ID",
    "STRATEGY_KEY",
    "STRATEGY_VERSION",
    "TICKER",
    "DIRECTION",
    "TIMEFRAME",
    "ORIGIN",
    "EVENT_TYPE",
    "EVENT_TIME",
    "EVENT_TIME_MS",
    "EVENT_PRICE",
    "PLANNED_ENTRY",
    "PLANNED_STOP",
    "REFERENCE_2R",
    "SUGGESTED_SHARES",
    "SETUP_QUALITY",
    "ALLOWED_RISK",
    "PLANNED_POSITION_VALUE",
    "PLANNED_EXPOSURE_PCT",
    "SIGNAL_GAP_PCT",
    "SIGNAL_RVOL",
    "IMPULSE_PCT",
    "RETRACEMENT_PCT",
    "CONTEXT_5M",
    "ABOVE_VWAP",
    "ABOVE_EMA9",
    "VOLUME_CONFIRMED",
    "SESSION",
    "EXIT_REASON",
]

SUPPORTED_SCHEMA = frozenset({"1.0"})
EVENT_TYPES = frozenset({"ARMED", "ENTRY", "EXIT"})
ORIGINS = frozenset({"REALTIME", "HISTORICAL_REPLAY", "BACKTEST", "UNKNOWN"})

EVENT_TYPE_ALIASES = {
    "ARMED-1": "ARMED",
    "ENTRY-1": "ENTRY",
    "EXIT-1": "EXIT",
}

SNAPSHOT_KEYS = (
    "event_price",
    "planned_entry_price",
    "planned_stop_price",
    "reference_2r_price",
    "suggested_shares",
    "setup_quality",
    "allowed_risk",
    "planned_position_value",
    "planned_exposure_pct",
    "signal_gap_pct",
    "signal_rvol",
    "impulse_pct",
    "retracement_pct",
    "context_5m",
    "above_vwap",
    "above_ema9",
    "volume_confirmed",
    "session_label",
    "mechanical_exit_reason",
    "event_origin",
    "ticker",
    "direction",
)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def event_fingerprint(signal_id: str, event_type: str, event_time_iso: str, strategy_version: str | None) -> str:
    if strategy_version:
        payload = f"{signal_id}|{event_type}|{event_time_iso}|{strategy_version}"
    else:
        payload = f"{signal_id}|{event_type}|{event_time_iso}"
    return _sha(payload)


def payload_hash_from_fields(fields: dict) -> str:
    parts = []
    for key in SNAPSHOT_KEYS:
        val = fields.get(key)
        if val is None:
            parts.append("")
        elif isinstance(val, Decimal):
            parts.append(format(val, "f"))
        elif isinstance(val, bool):
            parts.append("true" if val else "false")
        else:
            parts.append(str(val))
    return _sha("|".join(parts))


def parse_event_time(event_time: str | None, event_time_ms: str | None | int) -> tuple[datetime, str | None, int | None]:
    """Return (utc datetime, original string, unix ms). Prefer Pine unix milliseconds."""
    original = (event_time or "").strip() or None
    ms: int | None = None
    if event_time_ms not in (None, ""):
        try:
            ms = int(str(event_time_ms).strip())
        except (TypeError, ValueError):
            ms = None
    if ms is not None:
        return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc), original, ms
    if not original:
        raise PineParseError("MISSING_EVENT_TIME", "EVENT_TIME and EVENT_TIME_MS are both missing")
    text = original
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PineParseError("INVALID_EVENT_TIME", f"Cannot parse EVENT_TIME: {original}", details={"error": str(exc)}) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=analytics_tz())
    return dt.astimezone(timezone.utc), original, int(dt.timestamp() * 1000)


def _bool_field(value: str | None) -> bool | None:
    if value is None or str(value).strip() == "":
        return None
    low = str(value).strip().lower()
    if low in ("true", "1", "yes"):
        return True
    if low in ("false", "0", "no"):
        return False
    return None


def _split_line(line: str) -> list[str]:
    if "\t" in line:
        return line.split("\t")
    return [p.strip() for p in line.split(",")]


@dataclass
class ParsedEvent:
    record_type: str
    schema_version: str
    signal_id: str
    strategy_key: str
    strategy_version: str
    strategy_version_normalized: str
    ticker: str
    direction: str
    timeframe: str
    event_origin: str
    event_type: str
    event_time_utc: datetime
    event_time_original: str | None
    event_time_ms: int | None
    event_price: Decimal | None
    planned_entry_price: Decimal | None
    planned_stop_price: Decimal | None
    reference_2r_price: Decimal | None
    suggested_shares: Decimal | None
    setup_quality: str | None
    allowed_risk: Decimal | None
    planned_position_value: Decimal | None
    planned_exposure_pct: Decimal | None
    signal_gap_pct: Decimal | None
    signal_rvol: Decimal | None
    impulse_pct: Decimal | None
    retracement_pct: Decimal | None
    context_5m: str | None
    above_vwap: bool | None
    above_ema9: bool | None
    volume_confirmed: bool | None
    session_label: str | None
    mechanical_exit_reason: str | None
    raw_line: str
    raw_payload: dict
    event_fingerprint: str
    payload_hash: str
    legacy: bool = False
    line_number: int = 0


@dataclass
class ParseResult:
    events: list[ParsedEvent] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    header_present: bool = False
    skipped_headers: int = 0
    unknown_records: int = 0
    legacy_records: int = 0


def _row_to_dict(parts: list[str], columns: list[str]) -> dict[str, str]:
    row = {}
    for i, col in enumerate(columns):
        row[col] = parts[i].strip() if i < len(parts) else ""
    return row


def _parse_pine_event(row: dict[str, str], raw_line: str, line_number: int) -> ParsedEvent:
    schema = (row.get("SCHEMA_VERSION") or "").strip()
    if schema not in SUPPORTED_SCHEMA:
        raise PineParseError("UNKNOWN_SCHEMA", f"Unsupported schema_version {schema!r}", raw_line)

    signal_id = (row.get("SIGNAL_ID") or "").strip()
    if not signal_id:
        raise PineParseError("MISSING_SIGNAL_ID", "SIGNAL_ID is required", raw_line)

    event_type_raw = (row.get("EVENT_TYPE") or "").strip().upper()
    event_type = EVENT_TYPE_ALIASES.get(event_type_raw, event_type_raw)
    if event_type not in EVENT_TYPES:
        raise PineParseError("UNKNOWN_EVENT_TYPE", f"Unknown EVENT_TYPE {event_type_raw!r}", raw_line)

    origin = (row.get("ORIGIN") or "").strip().upper() or "UNKNOWN"
    if origin not in ORIGINS:
        origin = "UNKNOWN"

    event_time_utc, original, ms = parse_event_time(row.get("EVENT_TIME"), row.get("EVENT_TIME_MS"))
    event_time_iso = event_time_utc.isoformat()
    strategy_version = (row.get("STRATEGY_VERSION") or "").strip()

    fields = {
        "event_price": to_decimal(row.get("EVENT_PRICE")),
        "planned_entry_price": to_decimal(row.get("PLANNED_ENTRY")),
        "planned_stop_price": to_decimal(row.get("PLANNED_STOP")),
        "reference_2r_price": to_decimal(row.get("REFERENCE_2R")),
        "suggested_shares": to_decimal(row.get("SUGGESTED_SHARES")),
        "setup_quality": (row.get("SETUP_QUALITY") or "").strip() or None,
        "allowed_risk": to_decimal(row.get("ALLOWED_RISK")),
        "planned_position_value": to_decimal(row.get("PLANNED_POSITION_VALUE")),
        "planned_exposure_pct": to_decimal(row.get("PLANNED_EXPOSURE_PCT")),
        "signal_gap_pct": to_decimal(row.get("SIGNAL_GAP_PCT")),
        "signal_rvol": to_decimal(row.get("SIGNAL_RVOL")),
        "impulse_pct": to_decimal(row.get("IMPULSE_PCT")),
        "retracement_pct": to_decimal(row.get("RETRACEMENT_PCT")),
        "context_5m": (row.get("CONTEXT_5M") or "").strip() or None,
        "above_vwap": _bool_field(row.get("ABOVE_VWAP")),
        "above_ema9": _bool_field(row.get("ABOVE_EMA9")),
        "volume_confirmed": _bool_field(row.get("VOLUME_CONFIRMED")),
        "session_label": (row.get("SESSION") or "").strip() or None,
        "mechanical_exit_reason": (row.get("EXIT_REASON") or "").strip() or None,
        "event_origin": origin,
        "ticker": (row.get("TICKER") or "").strip().upper(),
        "direction": (row.get("DIRECTION") or "").strip().upper(),
    }
    payload = {**row, **{k: (format(v, "f") if isinstance(v, Decimal) else v) for k, v in fields.items()}}
    fp = event_fingerprint(signal_id, event_type, event_time_iso, strategy_version)
    return ParsedEvent(
        record_type="PINE_SIGNAL_EVENT",
        schema_version=schema,
        signal_id=signal_id,
        strategy_key=(row.get("STRATEGY_KEY") or "").strip(),
        strategy_version=strategy_version,
        strategy_version_normalized=normalize_strategy_version(strategy_version),
        ticker=fields["ticker"],
        direction=fields["direction"] or "LONG",
        timeframe=(row.get("TIMEFRAME") or "").strip(),
        event_origin=origin,
        event_type=event_type,
        event_time_utc=event_time_utc,
        event_time_original=original,
        event_time_ms=ms,
        event_price=fields["event_price"],
        planned_entry_price=fields["planned_entry_price"],
        planned_stop_price=fields["planned_stop_price"],
        reference_2r_price=fields["reference_2r_price"],
        suggested_shares=fields["suggested_shares"],
        setup_quality=fields["setup_quality"],
        allowed_risk=fields["allowed_risk"],
        planned_position_value=fields["planned_position_value"],
        planned_exposure_pct=fields["planned_exposure_pct"],
        signal_gap_pct=fields["signal_gap_pct"],
        signal_rvol=fields["signal_rvol"],
        impulse_pct=fields["impulse_pct"],
        retracement_pct=fields["retracement_pct"],
        context_5m=fields["context_5m"],
        above_vwap=fields["above_vwap"],
        above_ema9=fields["above_ema9"],
        volume_confirmed=fields["volume_confirmed"],
        session_label=fields["session_label"],
        mechanical_exit_reason=fields["mechanical_exit_reason"],
        raw_line=raw_line,
        raw_payload=payload,
        event_fingerprint=fp,
        payload_hash=payload_hash_from_fields(fields),
        line_number=line_number,
    )


def parse_pine_log(text: str) -> ParseResult:
    from app.services.signals.legacy import try_parse_legacy

    result = ParseResult()
    columns = SCHEMA_1_COLUMNS
    lines = text.splitlines()
    for i, raw in enumerate(lines, start=1):
        line = raw.strip("\ufeff").rstrip("\r")
        if not line.strip():
            continue
        parts = _split_line(line)
        first = (parts[0] if parts else "").strip()
        if first in ("PINE_SIGNAL_EVENT_HEADER", "RECORD_TYPE") or first.startswith("PINE_SIGNAL_EVENT_HEADER"):
            result.header_present = True
            result.skipped_headers += 1
            if first == "PINE_SIGNAL_EVENT_HEADER" and len(parts) > 1:
                columns = ["RECORD_TYPE"] + [p.strip() for p in parts[1:]]
            elif first == "RECORD_TYPE":
                columns = [p.strip() for p in parts]
            continue
        if first == "PINE_SIGNAL_EVENT":
            try:
                row = _row_to_dict(parts, columns if columns[0] == "RECORD_TYPE" else SCHEMA_1_COLUMNS)
                result.events.append(_parse_pine_event(row, line, i))
            except PineParseError as exc:
                result.errors.append({**exc.to_dict(), "line_number": i, "raw_line": line})
            except Exception as exc:  # noqa: BLE001 — structured import error, continue batch
                result.errors.append(
                    {
                        "code": "MALFORMED",
                        "message": str(exc),
                        "raw_line": line,
                        "line_number": i,
                        "details": {},
                    }
                )
            continue
        legacy = try_parse_legacy(first, parts, line, i)
        if legacy is not None:
            if isinstance(legacy, PineParseError):
                result.errors.append({**legacy.to_dict(), "line_number": i, "raw_line": line})
            else:
                result.events.append(legacy)
                result.legacy_records += 1
            continue
        result.unknown_records += 1
        result.errors.append(
            {
                "code": "UNKNOWN_RECORD",
                "message": f"Unrecognized record type {first!r}",
                "raw_line": line,
                "line_number": i,
                "details": {},
            }
        )
    return result


def preview_stats(parsed: ParseResult) -> dict:
    events = parsed.events
    signal_ids = {e.signal_id for e in events}
    return {
        "records": len(events) + len(parsed.errors),
        "valid_events": len(events),
        "signals": len(signal_ids),
        "armed": sum(1 for e in events if e.event_type == "ARMED"),
        "entry": sum(1 for e in events if e.event_type == "ENTRY"),
        "exit": sum(1 for e in events if e.event_type == "EXIT"),
        "realtime": sum(1 for e in events if e.event_origin == "REALTIME"),
        "historical": sum(1 for e in events if e.event_origin == "HISTORICAL_REPLAY"),
        "backtest": sum(1 for e in events if e.event_origin == "BACKTEST"),
        "unknown": sum(1 for e in events if e.event_origin == "UNKNOWN"),
        "legacy": sum(1 for e in events if e.legacy),
        "errors": len(parsed.errors),
        "unknown_records": parsed.unknown_records,
        "error_samples": parsed.errors[:20],
    }
