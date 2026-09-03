"""Position lifecycle replay for MFE/MAE (Step 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db.models.execution import Execution
from app.db.models.trade import Trade
from app.db.models.trade_execution import TradeExecution
from app.market_data.models import IntradayBar
from app.utils.money import quantize_price


@dataclass
class ExecEvent:
    time: datetime
    role: str
    qty: Decimal
    price: Decimal


@dataclass
class PositionState:
    open_qty: Decimal = Decimal("0")
    avg_basis: Decimal = Decimal("0")
    realized_gross: Decimal = Decimal("0")


@dataclass
class ExcursionTrack:
    """Tracks inclusive and conservative position-level extrema."""

    inclusive_mfe: Decimal | None = None
    inclusive_mae: Decimal | None = None
    inclusive_mfe_time: datetime | None = None
    inclusive_mae_time: datetime | None = None

    conservative_mfe: Decimal | None = None
    conservative_mae: Decimal | None = None
    conservative_mfe_time: datetime | None = None
    conservative_mae_time: datetime | None = None

    price_high: Decimal | None = None
    price_low: Decimal | None = None
    conservative_price_high: Decimal | None = None
    conservative_price_low: Decimal | None = None

    boundary_ambiguity: bool = False
    flags: list[str] = field(default_factory=list)


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def load_exec_events(links: list[tuple[TradeExecution, Execution]]) -> list[ExecEvent]:
    events = []
    for link, ex in links:
        events.append(
            ExecEvent(
                time=_ensure_utc(ex.execution_time_utc),
                role=link.role,
                qty=link.allocated_quantity,
                price=ex.price,
            )
        )
    events.sort(key=lambda e: (e.time, e.role))
    return events


def holding_bounds(events: list[ExecEvent]) -> tuple[datetime, datetime]:
    entries = [e for e in events if e.role == "ENTRY"]
    exits = [e for e in events if e.role == "EXIT"]
    if not entries or not exits:
        raise ValueError("Trade must have at least one entry and one exit execution")
    return entries[0].time, exits[-1].time


def apply_entry(state: PositionState, qty: Decimal, price: Decimal) -> None:
    if state.open_qty <= 0:
        state.open_qty = qty
        state.avg_basis = price
        return
    total_cost = state.open_qty * state.avg_basis + qty * price
    state.open_qty += qty
    state.avg_basis = quantize_price(total_cost / state.open_qty)


def apply_exit(state: PositionState, direction: str, qty: Decimal, price: Decimal) -> None:
    if qty <= 0 or state.open_qty <= 0:
        return
    if direction == "LONG":
        state.realized_gross += qty * (price - state.avg_basis)
    else:
        state.realized_gross += qty * (state.avg_basis - price)
    state.open_qty -= qty
    if state.open_qty <= 0:
        state.open_qty = Decimal("0")
        state.avg_basis = Decimal("0")


def mark_pnl(state: PositionState, direction: str, price: Decimal) -> Decimal:
    if state.open_qty <= 0:
        return state.realized_gross
    if direction == "LONG":
        return state.realized_gross + state.open_qty * (price - state.avg_basis)
    return state.realized_gross + state.open_qty * (state.avg_basis - price)


def price_favorable(direction: str, entry: Decimal, price: Decimal) -> Decimal:
    if direction == "LONG":
        return price - entry
    return entry - price


def _update_extreme(
    track: ExcursionTrack,
    mode: str,
    kind: str,
    value: Decimal,
    at: datetime,
) -> None:
    prefix = "inclusive" if mode == "inclusive" else "conservative"
    if kind == "mfe":
        cur = getattr(track, f"{prefix}_mfe")
        if cur is None or value > cur:
            setattr(track, f"{prefix}_mfe", value)
            setattr(track, f"{prefix}_mfe_time", at)
    else:
        cur = getattr(track, f"{prefix}_mae")
        if cur is None or value < cur:
            setattr(track, f"{prefix}_mae", value)
            setattr(track, f"{prefix}_mae_time", at)


def _update_price_extreme(track: ExcursionTrack, direction: str, entry: Decimal, price: Decimal, conservative: bool) -> None:
    fav = price_favorable(direction, entry, price)
    if conservative:
        if track.conservative_price_high is None or fav > track.conservative_price_high:
            track.conservative_price_high = fav
        if track.conservative_price_low is None or fav < track.conservative_price_low:
            track.conservative_price_low = fav
    else:
        if track.price_high is None or fav > track.price_high:
            track.price_high = fav
        if track.price_low is None or fav < track.price_low:
            track.price_low = fav


def _bar_end(bar: IntradayBar) -> datetime:
    return _ensure_utc(bar.bar_time_utc) + timedelta(minutes=1)


def _minute_floor(dt: datetime) -> datetime:
    dt = _ensure_utc(dt)
    return dt.replace(second=0, microsecond=0)


def replay_excursions(
    trade: Trade,
    events: list[ExecEvent],
    bars: list[IntradayBar],
    *,
    post_exit_bars: list[IntradayBar] | None = None,
) -> tuple[ExcursionTrack, PositionState, dict]:
    """
    Replay position lifecycle with inclusive and conservative MFE/MAE.
    Returns track, final state, diagnostics.
    """
    direction = trade.direction
    entry_ref = trade.avg_entry_price
    hold_start, hold_end = holding_bounds(events)
    hold_start_min = _minute_floor(hold_start)
    hold_end_min = _minute_floor(hold_end)

    track = ExcursionTrack()
    state = PositionState()
    diag: dict = {"longest_gap_seconds": 0, "sparse": False, "bar_count": 0}

    # Filter bars to holding window (+ post-exit handled separately)
    hold_bars = sorted(
        [b for b in bars if _ensure_utc(b.bar_time_utc) < hold_end and _bar_end(b) > hold_start],
        key=lambda b: b.bar_time_utc,
    )
    diag["bar_count"] = len(hold_bars)

    if len(hold_bars) >= 2:
        max_gap = 0
        for i in range(1, len(hold_bars)):
            gap = int((_ensure_utc(hold_bars[i].bar_time_utc) - _ensure_utc(hold_bars[i - 1].bar_time_utc)).total_seconds()) - 60
            if gap > max_gap:
                max_gap = gap
        diag["longest_gap_seconds"] = max(0, max_gap)
        if max_gap > 120:
            diag["sparse"] = True
            track.flags.append("SPARSE_INTERVAL")

    event_idx = 0

    def process_exec(ev: ExecEvent) -> None:
        nonlocal state
        if ev.role == "ENTRY":
            apply_entry(state, ev.qty, ev.price)
        else:
            apply_exit(state, direction, ev.qty, ev.price)
        pnl = mark_pnl(state, direction, ev.price)
        at = ev.time
        _update_extreme(track, "inclusive", "mfe", pnl, at)
        _update_extreme(track, "inclusive", "mae", pnl, at)
        _update_extreme(track, "conservative", "mfe", pnl, at)
        _update_extreme(track, "conservative", "mae", pnl, at)
        _update_price_extreme(track, direction, entry_ref, ev.price, False)
        _update_price_extreme(track, direction, entry_ref, ev.price, True)

    # Process executions before first bar
    while event_idx < len(events) and events[event_idx].time < (hold_bars[0].bar_time_utc if hold_bars else hold_end):
        process_exec(events[event_idx])
        event_idx += 1

    for bar in hold_bars:
        bar_start = _ensure_utc(bar.bar_time_utc)
        bar_end = _bar_end(bar)
        is_entry_boundary = bar_start <= hold_start_min <= bar_end
        is_exit_boundary = bar_start <= hold_end_min <= bar_end
        if is_entry_boundary or is_exit_boundary:
            track.boundary_ambiguity = True
            if "BOUNDARY_BAR_AMBIGUITY" not in track.flags:
                track.flags.append("BOUNDARY_BAR_AMBIGUITY")

        # Executions within this bar
        while event_idx < len(events) and events[event_idx].time < bar_end:
            if events[event_idx].time >= bar_start:
                process_exec(events[event_idx])
            event_idx += 1

        if state.open_qty <= 0:
            continue

        # Inclusive: full bar extrema
        if direction == "LONG":
            fav_p, adv_p = bar.high, bar.low
        else:
            fav_p, adv_p = bar.low, bar.high

        fav_pnl = mark_pnl(state, direction, fav_p)
        adv_pnl = mark_pnl(state, direction, adv_p)
        _update_extreme(track, "inclusive", "mfe", fav_pnl, bar_start)
        _update_extreme(track, "inclusive", "mae", adv_pnl, bar_start)
        _update_price_extreme(track, direction, entry_ref, fav_p, False)
        _update_price_extreme(track, direction, entry_ref, adv_p, False)

        # Conservative: skip bar extrema on boundary bars
        if not (is_entry_boundary or is_exit_boundary):
            _update_extreme(track, "conservative", "mfe", fav_pnl, bar_start)
            _update_extreme(track, "conservative", "mae", adv_pnl, bar_start)
            _update_price_extreme(track, direction, entry_ref, fav_p, True)
            _update_price_extreme(track, direction, entry_ref, adv_p, True)

    # Remaining executions after last bar
    while event_idx < len(events):
        process_exec(events[event_idx])
        event_idx += 1

    # Post-exit favorable extension (separate from MFE)
    post_exit: dict[int, Decimal | None] = {5: None, 15: None, 30: None}
    if post_exit_bars and trade.avg_exit_price is not None:
        exit_px = trade.avg_exit_price
        for window in (5, 15, 30):
            deadline = hold_end + timedelta(minutes=window)
            best: Decimal | None = None
            for bar in post_exit_bars:
                bt = _ensure_utc(bar.bar_time_utc)
                if bt < hold_end or bt > deadline:
                    continue
                px = bar.high if direction == "LONG" else bar.low
                if direction == "LONG":
                    ext = px - exit_px
                else:
                    ext = exit_px - px
                if ext > 0 and (best is None or ext > best):
                    best = ext
            post_exit[window] = best
    diag["post_exit"] = post_exit

    return track, state, diag
