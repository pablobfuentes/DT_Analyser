"""Pine signal import, list, detail, matching, coverage."""

from __future__ import annotations

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.db.models.signal import PineImportBatch, Signal, SignalEvent, SignalEventConflict, TradeSignalLink
from app.db.models.trade import Trade
from app.db.session import get_db
from app.services.signals.coverage import coverage_by_date, coverage_summary
from app.services.signals.importer import commit_import, preview_import
from app.services.signals.matcher import (
    STATUS_CONFIRMED,
    candidates_for_signal,
    confirm_link,
    reject_link,
    unlink,
)
from app.utils.analytics import utc_bounds_for_ny_range

router = APIRouter(prefix="/api/signals", tags=["signals"])


class PinePreviewRequest(BaseModel):
    text: str


class PineCommitRequest(BaseModel):
    text: str
    source: str = "PASTE"
    filename: str | None = None


class LinkRequest(BaseModel):
    trade_id: int


def _signal_dict(s: Signal, *, extra: dict | None = None) -> dict:
    payload = {
        "id": s.id,
        "signal_id": s.signal_id,
        "schema_version": s.schema_version,
        "strategy_key": s.strategy_key,
        "strategy_version": s.strategy_version,
        "strategy_version_normalized": s.strategy_version_normalized,
        "ticker": s.ticker,
        "direction": s.direction,
        "timeframe": s.timeframe,
        "signal_origin": s.signal_origin,
        "armed_time_utc": s.armed_time_utc.isoformat() if s.armed_time_utc else None,
        "entry_signal_time_utc": s.entry_signal_time_utc.isoformat() if s.entry_signal_time_utc else None,
        "exit_signal_time_utc": s.exit_signal_time_utc.isoformat() if s.exit_signal_time_utc else None,
        "state": s.state,
        "match_status": s.match_status,
        "planned_entry_price": str(s.planned_entry_price) if s.planned_entry_price is not None else None,
        "planned_stop_price": str(s.planned_stop_price) if s.planned_stop_price is not None else None,
        "reference_2r_price": str(s.reference_2r_price) if s.reference_2r_price is not None else None,
        "suggested_shares": str(s.suggested_shares) if s.suggested_shares is not None else None,
        "allowed_risk": str(s.allowed_risk) if s.allowed_risk is not None else None,
        "setup_quality": s.setup_quality,
        "signal_gap_pct": str(s.signal_gap_pct) if s.signal_gap_pct is not None else None,
        "signal_rvol": str(s.signal_rvol) if s.signal_rvol is not None else None,
        "impulse_pct": str(s.impulse_pct) if s.impulse_pct is not None else None,
        "retracement_pct": str(s.retracement_pct) if s.retracement_pct is not None else None,
        "context_5m": s.context_5m,
        "above_vwap": s.above_vwap,
        "above_ema9": s.above_ema9,
        "volume_confirmed": s.volume_confirmed,
        "session_label": s.session_label,
        "mechanical_exit_price": str(s.mechanical_exit_price) if s.mechanical_exit_price is not None else None,
        "mechanical_exit_reason": s.mechanical_exit_reason,
        "legacy": s.legacy,
    }
    if extra:
        payload.update(extra)
    return payload


@router.post("/import/preview")
def pine_preview(payload: PinePreviewRequest):
    return preview_import(payload.text)


@router.post("/import/commit")
def pine_commit(payload: PineCommitRequest, db: Session = Depends(get_db)):
    result = commit_import(db, payload.text, source=payload.source, filename=payload.filename)
    if payload.source.upper() == "PASTE":
        try:
            from app.services.automation.inbox import archive_paste_text

            archive_paste_text(payload.text, payload.filename or "pine-paste.txt")
        except Exception:
            pass
    return result


@router.get("")
def list_signals(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    ticker: str | None = None,
    strategy: str | None = None,
    version: str | None = None,
    origin: str | None = None,
    direction: str | None = None,
    state: str | None = None,
    link_status: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(Signal)
    if ticker:
        q = q.filter(Signal.ticker.ilike(f"%{ticker}%"))
    if strategy:
        q = q.filter(Signal.strategy_key == strategy)
    if version:
        q = q.filter(
            (Signal.strategy_version == version) | (Signal.strategy_version_normalized == version)
        )
    if origin:
        q = q.filter(Signal.signal_origin == origin.upper())
    if direction:
        q = q.filter(Signal.direction == direction.upper())
    if state:
        q = q.filter(Signal.state == state.upper())
    if link_status:
        q = q.filter(Signal.match_status == link_status.upper())
    if date_from:
        d = date.fromisoformat(date_from)
        utc_start, _ = utc_bounds_for_ny_range(d, d)
        if utc_start:
            q = q.filter(
                (Signal.entry_signal_time_utc >= utc_start) | (Signal.armed_time_utc >= utc_start)
            )
    if date_to:
        d = date.fromisoformat(date_to)
        _, utc_end = utc_bounds_for_ny_range(d, d)
        if utc_end:
            q = q.filter(
                (Signal.entry_signal_time_utc <= utc_end) | (Signal.armed_time_utc <= utc_end)
            )
    total = q.count()
    items = (
        q.order_by(Signal.entry_signal_time_utc.desc().nullslast(), Signal.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"items": [_signal_dict(s) for s in items], "total": total, "page": page, "page_size": page_size}


@router.get("/coverage")
def signal_coverage(db: Session = Depends(get_db)):
    summary = coverage_summary(db)
    from app.db.models.signal import SignalEvent

    summary["signal_events"] = db.query(SignalEvent).count()
    return {"summary": summary, "by_date": coverage_by_date(db)}


@router.get("/{signal_pk}")
def signal_detail(signal_pk: int, db: Session = Depends(get_db)):
    s = db.get(Signal, signal_pk)
    if not s:
        raise HTTPException(status_code=404, detail="Signal not found")
    events = (
        db.query(SignalEvent)
        .filter(SignalEvent.signal_pk == s.id)
        .order_by(SignalEvent.event_time_utc)
        .all()
    )
    links = db.query(TradeSignalLink).filter(TradeSignalLink.signal_id == s.id).all()
    conflicts = (
        db.query(SignalEventConflict)
        .filter(SignalEventConflict.existing_event_id.in_([e.id for e in events] or [0]))
        .all()
    )
    return {
        **_signal_dict(s),
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "event_time_utc": e.event_time_utc.isoformat(),
                "event_time_original": e.event_time_original,
                "event_time_ms": e.event_time_ms,
                "event_origin": e.event_origin,
                "raw_line": e.raw_line,
                "raw_payload_json": e.raw_payload_json,
                "event_fingerprint": e.event_fingerprint,
                "strategy_version": e.strategy_version,
                "schema_version": e.schema_version,
            }
            for e in events
        ],
        "links": [
            {
                "id": l.id,
                "trade_id": l.trade_id,
                "match_type": l.match_type,
                "confidence": str(l.confidence),
                "time_delta_seconds": l.time_delta_seconds,
                "link_status": l.link_status,
            }
            for l in links
        ],
        "candidates": candidates_for_signal(db, s),
        "conflicts": [
            {
                "id": c.id,
                "existing_event_id": c.existing_event_id,
                "error_code": c.error_code,
                "incoming_raw_line": c.incoming_raw_line,
            }
            for c in conflicts
        ],
        "strategy_snapshot": {
            "planned_entry_price": str(s.planned_entry_price) if s.planned_entry_price is not None else None,
            "planned_stop_price": str(s.planned_stop_price) if s.planned_stop_price is not None else None,
            "reference_2r_price": str(s.reference_2r_price) if s.reference_2r_price is not None else None,
            "suggested_shares": str(s.suggested_shares) if s.suggested_shares is not None else None,
            "allowed_risk": str(s.allowed_risk) if s.allowed_risk is not None else None,
            "setup_quality": s.setup_quality,
            "signal_gap_pct": str(s.signal_gap_pct) if s.signal_gap_pct is not None else None,
            "signal_rvol": str(s.signal_rvol) if s.signal_rvol is not None else None,
        },
    }


@router.post("/{signal_pk}/link")
def link_signal(signal_pk: int, payload: LinkRequest, db: Session = Depends(get_db)):
    s = db.get(Signal, signal_pk)
    trade = db.get(Trade, payload.trade_id)
    if not s or not trade:
        raise HTTPException(status_code=404, detail="Signal or trade not found")
    try:
        link = confirm_link(db, s, trade)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return {"trade_id": trade.id, "signal_id": s.id, "link_status": link.link_status, "match_type": link.match_type}


@router.post("/{signal_pk}/unlink")
def unlink_signal(signal_pk: int, payload: LinkRequest, db: Session = Depends(get_db)):
    s = db.get(Signal, signal_pk)
    trade = db.get(Trade, payload.trade_id)
    if not s or not trade:
        raise HTTPException(status_code=404, detail="Signal or trade not found")
    unlink(db, s, trade)
    db.commit()
    return {"status": "unlinked"}


@router.post("/{signal_pk}/reject")
def reject_signal_link(signal_pk: int, payload: LinkRequest, db: Session = Depends(get_db)):
    s = db.get(Signal, signal_pk)
    trade = db.get(Trade, payload.trade_id)
    if not s or not trade:
        raise HTTPException(status_code=404, detail="Signal or trade not found")
    reject_link(db, s, trade)
    db.commit()
    return {"status": "rejected"}
