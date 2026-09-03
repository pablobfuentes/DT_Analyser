"""Merge Signal summary from events. Order-independent. Field ownership is by lifecycle stage.

ARMED-owned: armed_time_utc; may fill planned snapshot only if currently null.
ENTRY-owned: entry time + signal-time setup snapshot. ENTRY overwrites ARMED snapshot fields.
EXIT-owned: exit time, mechanical exit price/reason.
EXIT never overwrites ENTRY-owned snapshot fields. EXIT may fill them only if still null.

Non-null later data may enrich null fields but must not erase another stage's owned values.
"""

from __future__ import annotations

from datetime import datetime

from app.db.models.signal import Signal
from app.services.signals.parser import ParsedEvent

ENTRY_OWNED = (
    "planned_entry_price",
    "planned_stop_price",
    "reference_2r_price",
    "suggested_shares",
    "allowed_risk",
    "planned_position_value",
    "planned_exposure_pct",
    "setup_quality",
    "signal_gap_pct",
    "signal_rvol",
    "impulse_pct",
    "retracement_pct",
    "context_5m",
    "above_vwap",
    "above_ema9",
    "volume_confirmed",
    "session_label",
)

EXIT_OWNED = (
    "mechanical_exit_price",
    "mechanical_exit_reason",
)


def _set_if_null(signal: Signal, attr: str, value) -> None:
    if value is None:
        return
    if getattr(signal, attr) is None:
        setattr(signal, attr, value)


def _apply_entry_snapshot(signal: Signal, event: ParsedEvent, overwrite: bool) -> None:
    mapping = {
        "planned_entry_price": event.planned_entry_price,
        "planned_stop_price": event.planned_stop_price,
        "reference_2r_price": event.reference_2r_price,
        "suggested_shares": event.suggested_shares,
        "allowed_risk": event.allowed_risk,
        "planned_position_value": event.planned_position_value,
        "planned_exposure_pct": event.planned_exposure_pct,
        "setup_quality": event.setup_quality,
        "signal_gap_pct": event.signal_gap_pct,
        "signal_rvol": event.signal_rvol,
        "impulse_pct": event.impulse_pct,
        "retracement_pct": event.retracement_pct,
        "context_5m": event.context_5m,
        "above_vwap": event.above_vwap,
        "above_ema9": event.above_ema9,
        "volume_confirmed": event.volume_confirmed,
        "session_label": event.session_label,
    }
    for attr, value in mapping.items():
        if value is None:
            continue
        if overwrite or getattr(signal, attr) is None:
            setattr(signal, attr, value)


def apply_event_to_signal(signal: Signal, event: ParsedEvent) -> None:
    """Apply one event onto an existing Signal using ownership rules."""
    if event.ticker:
        signal.ticker = event.ticker
    if event.direction:
        signal.direction = event.direction
    if event.timeframe:
        signal.timeframe = event.timeframe
    if event.strategy_key:
        signal.strategy_key = event.strategy_key
    if event.strategy_version:
        signal.strategy_version = event.strategy_version
        signal.strategy_version_normalized = event.strategy_version_normalized
    if event.schema_version:
        signal.schema_version = event.schema_version
    signal.legacy = signal.legacy or event.legacy

    if event.event_type == "ARMED":
        if signal.armed_time_utc is None or event.event_time_utc < signal.armed_time_utc:
            signal.armed_time_utc = event.event_time_utc
        _apply_entry_snapshot(signal, event, overwrite=False)
        if signal.signal_origin in (None, "", "UNKNOWN") or signal.signal_origin == "HISTORICAL_REPLAY":
            if event.event_origin:
                # Origin is Pine-provided; do not infer. Prefer first non-unknown, do not upgrade later.
                if signal.signal_origin in (None, "", "UNKNOWN"):
                    signal.signal_origin = event.event_origin
    elif event.event_type == "ENTRY":
        signal.entry_signal_time_utc = event.event_time_utc
        _apply_entry_snapshot(signal, event, overwrite=True)
        if signal.signal_origin in (None, "", "UNKNOWN"):
            signal.signal_origin = event.event_origin
    elif event.event_type == "EXIT":
        signal.exit_signal_time_utc = event.event_time_utc
        if event.event_price is not None:
            signal.mechanical_exit_price = event.event_price
        if event.mechanical_exit_reason:
            signal.mechanical_exit_reason = event.mechanical_exit_reason
        _apply_entry_snapshot(signal, event, overwrite=False)
        if signal.signal_origin in (None, "", "UNKNOWN"):
            signal.signal_origin = event.event_origin

    refresh_signal_state(signal)


def refresh_signal_state(signal: Signal) -> None:
    if signal.exit_signal_time_utc is not None:
        signal.state = "EXIT"
    elif signal.entry_signal_time_utc is not None:
        signal.state = "INCOMPLETE"
    elif signal.armed_time_utc is not None:
        signal.state = "ARMED"
    else:
        signal.state = "INCOMPLETE"


def new_signal_from_event(event: ParsedEvent, import_batch_id: int | None = None) -> Signal:
    signal = Signal(
        signal_id=event.signal_id,
        schema_version=event.schema_version,
        strategy_key=event.strategy_key or "UNKNOWN",
        strategy_version=event.strategy_version or "",
        strategy_version_normalized=event.strategy_version_normalized or "",
        ticker=event.ticker or "UNKNOWN",
        direction=event.direction or "LONG",
        timeframe=event.timeframe or "",
        signal_origin=event.event_origin or "UNKNOWN",
        legacy=event.legacy,
        import_batch_id=import_batch_id,
        state="INCOMPLETE",
        match_status="UNLINKED",
    )
    apply_event_to_signal(signal, event)
    return signal
