"""Step 5 — Pine signal parser, ID, merge, import, matcher."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.db.models.signal import Signal, SignalEvent, SignalEventConflict, TradeSignalLink
from app.services.signals.ids import build_signal_id, normalize_strategy_version
from app.services.signals.importer import commit_import, preview_import
from app.services.signals.matcher import confirm_link, match_one_signal, reject_link
from app.services.signals.parser import event_fingerprint, parse_event_time, parse_pine_log
from tests.dashboard_helpers import make_trade

NY = ZoneInfo("America/New_York")


def pine_line(
    *,
    signal_id: str,
    event_type: str,
    event_ms: int,
    ticker: str = "NCRA",
    strategy: str = "FIRST_PULLBACK",
    version: str = "Momentum Pullback Copilot v0.3.3.1 Opening Fade Research",
    origin: str = "REALTIME",
    direction: str = "LONG",
    timeframe: str = "1",
    planned_entry: str = "5.00",
    planned_stop: str = "4.80",
    ref2r: str = "5.40",
    shares: str = "500",
    quality: str = "A+",
    allowed: str = "100",
    gap: str = "12.5",
    rvol: str = "8.4",
    impulse: str = "7.2",
    retrace: str = "28.6",
    context: str = "BULLISH",
    vwap: str = "true",
    ema: str = "true",
    vol: str = "true",
    exit_reason: str = "",
    event_price: str | None = None,
) -> str:
    event_dt = datetime.fromtimestamp(event_ms / 1000, tz=timezone.utc).astimezone(NY)
    event_time = event_dt.strftime("%Y-%m-%dT%H:%M:%S")
    price = event_price if event_price is not None else planned_entry
    cols = [
        "PINE_SIGNAL_EVENT",
        "1.0",
        signal_id,
        strategy,
        version,
        ticker,
        direction,
        timeframe,
        origin,
        event_type,
        event_time,
        str(event_ms),
        price,
        planned_entry,
        planned_stop,
        ref2r,
        shares,
        quality,
        allowed,
        "2500",
        "7.20",
        gap,
        rvol,
        impulse,
        retrace,
        context,
        vwap,
        ema,
        vol,
        "09:30-10:00 ET",
        exit_reason,
    ]
    return "\t".join(cols)


def test_signal_id_collision_rules():
    a = build_signal_id("FIRST_PULLBACK", "NCRA", "1", 1725280860000)
    assert a == "FIRST_PULLBACK|NCRA|1|1725280860000"
    assert build_signal_id("FIRST_PULLBACK", "NCRA", "1", 1725280860000) == a
    assert build_signal_id("FIRST_PULLBACK", "NCRA", "1", 1725280920000) != a
    assert build_signal_id("OPENING_FADE", "NCRA", "1", 1725280860000) != a
    assert build_signal_id("FIRST_PULLBACK", "ABCD", "1", 1725280860000) != a
    assert build_signal_id("FIRST_PULLBACK", "NCRA", "5", 1725280860000) != a


def test_normalize_strategy_version():
    assert normalize_strategy_version("Momentum Pullback Copilot v0.3.3.1 Opening Fade Research") == "v0.3.3.1"
    assert normalize_strategy_version("v0.3.3") == "v0.3.3"
    assert normalize_strategy_version("0.3.3") == "v0.3.3"


def test_parse_event_time_unix_ms_and_dst():
    before = datetime(2026, 3, 8, 1, 30, tzinfo=NY)
    after = datetime(2026, 3, 8, 3, 30, tzinfo=NY)
    utc_b, _, _ = parse_event_time(None, int(before.timestamp() * 1000))
    utc_a, _, _ = parse_event_time(None, int(after.timestamp() * 1000))
    assert utc_b.tzinfo is not None
    assert utc_b.utcoffset().total_seconds() == 0
    assert utc_a > utc_b
    naive_est, _, _ = parse_event_time("2026-03-08T01:30:00", None)
    naive_edt, _, _ = parse_event_time("2026-03-08T03:30:00", None)
    assert naive_est.tzinfo is not None
    assert (naive_edt - naive_est).total_seconds() == 60 * 60


def test_parser_armed_entry_exit_same_id():
    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    text = "\n".join(
        [
            pine_line(signal_id=sid, event_type="ARMED", event_ms=1725280860000),
            pine_line(signal_id=sid, event_type="ENTRY", event_ms=1725280920000),
            pine_line(signal_id=sid, event_type="EXIT", event_ms=1725281100000, exit_reason="STOP LOSS", event_price="4.79"),
        ]
    )
    parsed = parse_pine_log(text)
    assert len(parsed.events) == 3
    assert {e.event_type for e in parsed.events} == {"ARMED", "ENTRY", "EXIT"}
    assert {e.signal_id for e in parsed.events} == {sid}


def test_preview_does_not_mutate(db_session):
    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    text = pine_line(signal_id=sid, event_type="ARMED", event_ms=1725280860000)
    stats = preview_import(text)
    assert stats["mutates"] is False
    assert stats["signals"] == 1
    assert db_session.query(Signal).count() == 0
    assert db_session.query(SignalEvent).count() == 0


def test_out_of_order_merge(db_session):
    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    text = "\n".join(
        [
            pine_line(signal_id=sid, event_type="EXIT", event_ms=1725281100000, exit_reason="2R", planned_entry="", planned_stop="", quality="", gap="", rvol=""),
            pine_line(signal_id=sid, event_type="ENTRY", event_ms=1725280920000, planned_entry="5.00", planned_stop="4.80", quality="A+"),
            pine_line(signal_id=sid, event_type="ARMED", event_ms=1725280860000, planned_entry="4.99", planned_stop="4.79"),
        ]
    )
    commit_import(db_session, text)
    sig = db_session.query(Signal).one()
    assert db_session.query(SignalEvent).count() == 3
    assert sig.state == "EXIT"
    assert sig.planned_entry_price == Decimal("5.00")
    assert sig.planned_stop_price == Decimal("4.80")
    assert sig.setup_quality == "A+"
    assert sig.mechanical_exit_reason == "2R"


def test_exit_does_not_erase_entry_snapshot(db_session):
    sid = "FIRST_PULLBACK|NCRA|1|1000"
    commit_import(
        db_session,
        pine_line(signal_id=sid, event_type="ENTRY", event_ms=2000, planned_entry="5.00", planned_stop="4.80", quality="A+", gap="10", rvol="6"),
    )
    commit_import(
        db_session,
        pine_line(signal_id=sid, event_type="EXIT", event_ms=3000, planned_entry="", planned_stop="", quality="", gap="", rvol="", exit_reason="STOP LOSS"),
    )
    sig = db_session.query(Signal).one()
    assert sig.planned_entry_price == Decimal("5.00")
    assert sig.setup_quality == "A+"
    assert sig.signal_gap_pct == Decimal("10")
    assert sig.mechanical_exit_reason == "STOP LOSS"


def test_duplicate_reimport_zero_new_events(db_session):
    sid = "FIRST_PULLBACK|NCRA|1|1000"
    text = "\n".join(
        [
            pine_line(signal_id=sid, event_type="ARMED", event_ms=1000),
            pine_line(signal_id=sid, event_type="ENTRY", event_ms=2000),
        ]
    )
    first = commit_import(db_session, text)
    second = commit_import(db_session, text)
    assert first["imported_events"] == 2
    assert second["imported_events"] == 0
    assert second["duplicates"] == 2
    assert db_session.query(Signal).count() == 1
    assert db_session.query(SignalEvent).count() == 2


def test_payload_conflict_preserves_original(db_session):
    sid = "FIRST_PULLBACK|NCRA|1|1000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=2000, planned_stop="4.80"))
    result = commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=2000, planned_stop="4.50"))
    assert result["conflicts"] == 1
    assert db_session.query(SignalEvent).count() == 1
    ev = db_session.query(SignalEvent).one()
    assert "4.80" in ev.raw_line
    conflict = db_session.query(SignalEventConflict).one()
    assert conflict.error_code == "EVENT_PAYLOAD_CONFLICT"
    assert "4.50" in (conflict.incoming_raw_line or "")


def test_partial_failure_nine_valid_one_bad(db_session):
    lines = [
        pine_line(signal_id=f"FIRST_PULLBACK|NCRA|1|{1000 + i}", event_type="ARMED", event_ms=1000 + i)
        for i in range(9)
    ]
    lines.append("NOT_A_RECORD\tjunk")
    result = commit_import(db_session, "\n".join(lines))
    assert result["imported_events"] == 9
    assert result["errors"] >= 1
    assert result["status"] == "PARTIAL"
    assert db_session.query(Signal).count() == 9


def test_legacy_synthetic_ids_do_not_merge():
    from app.services.signals.legacy import synthetic_legacy_id

    a = synthetic_legacy_id("UNKNOWN", "NCRA", 1000, "aaa111")
    b = synthetic_legacy_id("UNKNOWN", "NCRA", 1000, "bbb222")
    assert a != b


def test_legacy_parse_never_explicit(db_session, manual_account):
    commit_import(db_session, "TRADE_RECORD\tNCRA\tLONG\t2026-09-02T09:43:00")
    sig = db_session.query(Signal).one()
    assert sig.legacy is True
    assert sig.signal_origin == "UNKNOWN"
    make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("10"))
    match_one_signal(db_session, sig)
    db_session.commit()
    assert db_session.query(TradeSignalLink).filter(TradeSignalLink.link_status == "CONFIRMED").count() == 0


def test_wrong_ticker_and_direction_never_match(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|1000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=1000))
    t_short = make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        direction="SHORT",
        net_pnl=Decimal("5"),
        exit_time=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc),
    )
    sig = db_session.query(Signal).one()
    match_one_signal(db_session, sig)
    db_session.commit()
    assert db_session.query(TradeSignalLink).count() == 0
    try:
        confirm_link(db_session, sig, t_short)
        raise AssertionError("should reject SHORT vs LONG")
    except ValueError:
        pass


def test_auto_unique_confirmed(db_session, strategy_account):
    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=1725280860000))
    entry = datetime.fromtimestamp(1725280860000 / 1000, tz=timezone.utc)
    t = make_trade(
        db_session,
        strategy_account.id,
        source_type="TRADINGVIEW_AUTO",
        ticker="NCRA",
        direction="LONG",
        net_pnl=Decimal("20"),
        entry_time=entry,
        exit_time=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
    )
    sig = db_session.query(Signal).one()
    match_one_signal(db_session, sig)
    db_session.commit()
    link = db_session.query(TradeSignalLink).one()
    assert link.link_status == "CONFIRMED"
    assert link.trade_id == t.id


def test_auto_ambiguous_no_pick(db_session, strategy_account):
    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=1725280860000))
    entry = datetime.fromtimestamp(1725280860000 / 1000, tz=timezone.utc)
    make_trade(
        db_session,
        strategy_account.id,
        source_type="TRADINGVIEW_AUTO",
        ticker="NCRA",
        net_pnl=Decimal("10"),
        entry_time=entry,
        exit_time=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
    )
    make_trade(
        db_session,
        strategy_account.id,
        source_type="TRADINGVIEW_AUTO",
        ticker="NCRA",
        net_pnl=Decimal("11"),
        entry_time=entry,
        exit_time=datetime(2026, 9, 2, 16, 5, tzinfo=timezone.utc),
    )
    sig = db_session.query(Signal).one()
    match_one_signal(db_session, sig)
    db_session.commit()
    assert db_session.query(TradeSignalLink).filter(TradeSignalLink.link_status == "CONFIRMED").count() == 0
    db_session.refresh(sig)
    assert sig.match_status == "AMBIGUOUS"


def test_manual_suggested_not_confirmed(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=1725280860000))
    entry = datetime.fromtimestamp(1725280860000 / 1000, tz=timezone.utc)
    make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        net_pnl=Decimal("10"),
        entry_time=entry,
        exit_time=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
    )
    sig = db_session.query(Signal).one()
    match_one_signal(db_session, sig)
    db_session.commit()
    link = db_session.query(TradeSignalLink).one()
    assert link.link_status == "SUGGESTED"


def test_reject_prevents_resuggest(db_session, manual_account):
    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=1725280860000))
    entry = datetime.fromtimestamp(1725280860000 / 1000, tz=timezone.utc)
    t = make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        net_pnl=Decimal("10"),
        entry_time=entry,
        exit_time=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
    )
    sig = db_session.query(Signal).one()
    match_one_signal(db_session, sig)
    db_session.commit()
    reject_link(db_session, sig, t)
    db_session.commit()
    match_one_signal(db_session, sig)
    db_session.commit()
    statuses = [l.link_status for l in db_session.query(TradeSignalLink).all()]
    assert statuses == ["REJECTED"]


def test_explicit_id_confirm_is_confirmed(db_session, manual_account):
    from app.services.signals.matcher import MATCH_EXPLICIT, confirm_link

    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=1725280860000))
    entry = datetime.fromtimestamp(1725280860000 / 1000, tz=timezone.utc)
    t = make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        net_pnl=Decimal("10"),
        entry_time=entry,
        exit_time=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
    )
    sig = db_session.query(Signal).one()
    link = confirm_link(db_session, sig, t, match_type=MATCH_EXPLICIT)
    db_session.commit()
    assert link.match_type == "EXPLICIT_ID"
    assert link.confidence == Decimal("1.0") or link.confidence == Decimal("1.0000")
    assert link.link_status == "CONFIRMED"


def test_untraded_signal_preserved(db_session):
    commit_import(db_session, pine_line(signal_id="FIRST_PULLBACK|ZZZ|1|1", event_type="ARMED", event_ms=1, ticker="ZZZ"))
    assert db_session.query(Signal).count() == 1
    assert db_session.query(TradeSignalLink).count() == 0


def test_schema_and_strategy_version_independent():
    parsed = parse_pine_log(pine_line(signal_id="FIRST_PULLBACK|NCRA|1|1", event_type="ARMED", event_ms=1))
    ev = parsed.events[0]
    assert ev.schema_version == "1.0"
    assert ev.strategy_version != ev.schema_version


def test_fingerprint_includes_version():
    t = datetime(2026, 9, 2, 13, 43, 17, tzinfo=timezone.utc).isoformat()
    assert event_fingerprint("ID", "ENTRY", t, "v0.3.3") != event_fingerprint("ID", "ENTRY", t, "v0.4.0")


def test_graphs_confirmed_only_and_gap_rvol_keys(db_session, manual_account):
    from app.services.reports.filters import TradeFilterSet
    from app.services.reports.service import get_reports

    sid = "FIRST_PULLBACK|NCRA|1|1725280860000"
    commit_import(db_session, pine_line(signal_id=sid, event_type="ENTRY", event_ms=1725280860000, gap="12.5", rvol="8.4", quality="A+"))
    entry = datetime.fromtimestamp(1725280860000 / 1000, tz=timezone.utc)
    t = make_trade(
        db_session,
        manual_account.id,
        ticker="NCRA",
        net_pnl=Decimal("40"),
        entry_time=entry,
        exit_time=datetime(2026, 9, 2, 16, 0, tzinfo=timezone.utc),
    )
    t.avg_entry_price = Decimal("5.00")
    t.quantity = Decimal("400")
    db_session.commit()
    sig = db_session.query(Signal).one()
    confirm_link(db_session, sig, t)
    db_session.commit()
    reports = get_reports(db_session, TradeFilterSet(pine_scope="ALL"))
    features_used = []
    for sec in reports["sections"]:
        if sec["key"] == "STRATEGY":
            assert sec["available"] is True
            for r in sec["reports"]:
                features_used.append(r["feature_key"])
    assert "signal_gap_bucket" in features_used
    assert "signal_rvol_bucket" in features_used
    assert "opening_gap_bucket" not in features_used


def test_mixed_strategy_versions_not_hidden(db_session, manual_account):
    from app.services.reports.filters import TradeFilterSet
    from app.services.reports.service import get_reports

    s1 = "FIRST_PULLBACK|NCRA|1|1000"
    s2 = "FIRST_PULLBACK|NCRA|1|2000"
    commit_import(
        db_session,
        pine_line(signal_id=s1, event_type="ENTRY", event_ms=1000, version="Momentum Pullback Copilot v0.3.3")
        + "\n"
        + pine_line(signal_id=s2, event_type="ENTRY", event_ms=2000, version="Momentum Pullback Copilot v0.4.0"),
    )
    t1 = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("10"), exit_time=datetime(2026, 9, 1, 15, 0, tzinfo=timezone.utc))
    t2 = make_trade(db_session, manual_account.id, ticker="NCRA", net_pnl=Decimal("20"), exit_time=datetime(2026, 9, 2, 15, 0, tzinfo=timezone.utc))
    sigs = {s.signal_id: s for s in db_session.query(Signal).all()}
    confirm_link(db_session, sigs[s1], t1)
    confirm_link(db_session, sigs[s2], t2)
    db_session.commit()
    reports = get_reports(db_session, TradeFilterSet(pine_scope="ALL"))
    strat = next(s for s in reports["sections"] if s["key"] == "STRATEGY")
    assert strat["mixed_strategy_versions"] is not None
    assert strat["mixed_strategy_versions"]["warning"] == "MIXED STRATEGY VERSIONS"
