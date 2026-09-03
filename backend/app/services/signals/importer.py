"""Pine log import: preview (no writes) and commit with partial-failure semantics."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models.signal import (
    PineImportBatch,
    PineImportError,
    Signal,
    SignalEvent,
    SignalEventConflict,
)
from app.services.signals.merger import apply_event_to_signal, new_signal_from_event
from app.services.signals.parser import ParseResult, ParsedEvent, parse_pine_log, preview_stats
from app.utils.hashing import json_dumps, sha256_bytes


def preview_import(text: str) -> dict:
    parsed = parse_pine_log(text)
    stats = preview_stats(parsed)
    stats["mutates"] = False
    stats["duplicates"] = 0
    stats["content_hash"] = sha256_bytes(text.encode("utf-8"))
    return stats


def _event_row(signal: Signal, event: ParsedEvent) -> SignalEvent:
    return SignalEvent(
        signal_pk=signal.id,
        external_signal_id=event.signal_id,
        event_type=event.event_type,
        event_time_utc=event.event_time_utc,
        event_time_original=event.event_time_original,
        event_time_ms=event.event_time_ms,
        event_price=event.event_price,
        bar_time_utc=event.event_time_utc,
        event_origin=event.event_origin,
        raw_payload_json=json_dumps(event.raw_payload),
        raw_line=event.raw_line,
        event_fingerprint=event.event_fingerprint,
        payload_hash=event.payload_hash,
        schema_version=event.schema_version,
        strategy_version=event.strategy_version,
    )


def commit_import(db: Session, text: str, source: str = "PASTE", filename: str | None = None) -> dict:
    parsed = parse_pine_log(text)
    content_hash = sha256_bytes(text.encode("utf-8"))
    batch = PineImportBatch(
        source=source,
        filename=filename,
        content_hash=content_hash,
        status="PENDING",
        row_count_raw=len(parsed.events) + len(parsed.errors),
        import_started_at=datetime.now(timezone.utc),
    )
    db.add(batch)
    db.flush()

    for err in parsed.errors:
        db.add(
            PineImportError(
                batch_id=batch.id,
                line_number=err.get("line_number"),
                error_code=err.get("code") or "MALFORMED",
                raw_line=err.get("raw_line"),
                details_json=json_dumps(err),
            )
        )

    existing_fps = {
        fp for (fp,) in db.query(SignalEvent.event_fingerprint).all()
    }
    existing_by_fp: dict[str, SignalEvent] = {}
    if parsed.events:
        fps = [e.event_fingerprint for e in parsed.events]
        for ev in db.query(SignalEvent).filter(SignalEvent.event_fingerprint.in_(fps)).all():
            existing_by_fp[ev.event_fingerprint] = ev
            existing_fps.add(ev.event_fingerprint)

    signals_by_id: dict[str, Signal] = {}
    needed = {e.signal_id for e in parsed.events}
    if needed:
        for sig in db.query(Signal).filter(Signal.signal_id.in_(needed)).all():
            signals_by_id[sig.signal_id] = sig

    imported = 0
    duplicates = 0
    conflicts = 0
    touched_signals: list[Signal] = []

    for event in parsed.events:
        prior = existing_by_fp.get(event.event_fingerprint)
        if prior is not None:
            if prior.payload_hash != event.payload_hash:
                db.add(
                    SignalEventConflict(
                        existing_event_id=prior.id,
                        import_batch_id=batch.id,
                        error_code="EVENT_PAYLOAD_CONFLICT",
                        incoming_raw_line=event.raw_line,
                        incoming_payload_json=json_dumps(event.raw_payload),
                    )
                )
                db.add(
                    PineImportError(
                        batch_id=batch.id,
                        line_number=event.line_number,
                        error_code="EVENT_PAYLOAD_CONFLICT",
                        raw_line=event.raw_line,
                        details_json=json_dumps(
                            {
                                "existing_event_id": prior.id,
                                "signal_id": event.signal_id,
                                "event_type": event.event_type,
                            }
                        ),
                    )
                )
                conflicts += 1
            else:
                duplicates += 1
            continue

        signal = signals_by_id.get(event.signal_id)
        if signal is None:
            signal = new_signal_from_event(event, import_batch_id=batch.id)
            db.add(signal)
            db.flush()
            signals_by_id[event.signal_id] = signal
        else:
            apply_event_to_signal(signal, event)

        row = _event_row(signal, event)
        db.add(row)
        db.flush()
        existing_by_fp[event.event_fingerprint] = row
        existing_fps.add(event.event_fingerprint)
        imported += 1
        touched_signals.append(signal)

    batch.row_count_valid = len(parsed.events)
    batch.row_count_imported = imported
    batch.row_count_duplicate = duplicates
    batch.row_count_conflict = conflicts
    batch.row_count_error = len(parsed.errors) + conflicts
    batch.signal_count = len({s.signal_id for s in touched_signals}) if touched_signals else 0
    batch.armed_count = sum(1 for e in parsed.events if e.event_type == "ARMED")
    batch.entry_count = sum(1 for e in parsed.events if e.event_type == "ENTRY")
    batch.exit_count = sum(1 for e in parsed.events if e.event_type == "EXIT")
    batch.realtime_count = sum(1 for e in parsed.events if e.event_origin == "REALTIME")
    batch.historical_count = sum(1 for e in parsed.events if e.event_origin == "HISTORICAL_REPLAY")
    batch.unknown_count = sum(1 for e in parsed.events if e.event_origin == "UNKNOWN")
    batch.import_completed_at = datetime.now(timezone.utc)

    if imported and parsed.errors:
        batch.status = "PARTIAL"
    elif imported and conflicts:
        batch.status = "PARTIAL"
    elif imported:
        batch.status = "COMPLETE"
    elif parsed.events and duplicates and not parsed.errors and not conflicts:
        batch.status = "COMPLETE"
    elif parsed.errors and not imported:
        batch.status = "FAILED"
    else:
        batch.status = "COMPLETE" if not parsed.errors else "PARTIAL"

    db.commit()
    db.refresh(batch)

    from app.services.signals.matcher import match_signals_batch
    from app.services.risk.service import RiskService

    match_signals_batch(db, list(signals_by_id.values()))
    risk = RiskService(db)
    for sig in signals_by_id.values():
        risk.recalculate_for_signal(sig.id)
    db.commit()

    return {
        "import_batch_id": batch.id,
        "status": batch.status,
        "raw_rows": batch.row_count_raw,
        "valid_events": batch.row_count_valid,
        "imported_events": imported,
        "duplicates": duplicates,
        "conflicts": conflicts,
        "errors": batch.row_count_error,
        "signals": batch.signal_count,
        "armed": batch.armed_count,
        "entry": batch.entry_count,
        "exit": batch.exit_count,
        "realtime": batch.realtime_count,
        "historical": batch.historical_count,
        "unknown": batch.unknown_count,
        "content_hash": content_hash,
        "error_samples": parsed.errors[:20],
    }
