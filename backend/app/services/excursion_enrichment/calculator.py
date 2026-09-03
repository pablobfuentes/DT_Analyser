"""Excursion metric assembly from replay results."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.db.models.trade import Trade
from app.db.models.market_data import TradeExcursion
from app.services.excursion_enrichment.config import CALCULATION_VERSION, POST_EXIT_WINDOWS_MIN
from app.services.excursion_enrichment.replay import ExcursionTrack, PositionState, price_favorable
from app.utils.money import quantize_price


@dataclass
class CopilotExitInfo:
    exit_time_utc: datetime | None = None
    exit_price: Decimal | None = None
    exit_reason: str | None = None


def _r_value(amount: Decimal | None, risk: Decimal | None) -> Decimal | None:
    if amount is None or risk is None or risk <= 0:
        return None
    return amount / risk


def build_excursion_record(
    trade: Trade,
    track: ExcursionTrack,
    final_state: PositionState,
    diag: dict,
    *,
    holding_start: datetime,
    holding_end: datetime,
    provider: str,
    feed: str,
    is_consolidated: bool,
    initial_risk: Decimal | None,
    copilot: CopilotExitInfo | None = None,
    provider_missing: bool = False,
) -> TradeExcursion:
    gross_pnl = trade.gross_pnl if trade.gross_pnl is not None else final_state.realized_gross
    entry = trade.avg_entry_price

    inc_mfe = track.inclusive_mfe
    inc_mae = track.inclusive_mae
    con_mfe = track.conservative_mfe if track.conservative_mfe is not None else inc_mfe
    con_mae = track.conservative_mae if track.conservative_mae is not None else inc_mae

    price_mfe = track.price_high if track.price_high is not None else Decimal("0")
    price_mae = track.price_low if track.price_low is not None else Decimal("0")
    con_price_mfe = track.conservative_price_high if track.conservative_price_high is not None else price_mfe
    con_price_mae = track.conservative_price_low if track.conservative_price_low is not None else price_mae

    mfe_r = _r_value(inc_mfe, initial_risk)
    mae_r = _r_value(inc_mae, initial_risk)
    con_mfe_r = _r_value(con_mfe, initial_risk)
    con_mae_r = _r_value(con_mae, initial_risk)

    mfe_spread_amt = (inc_mfe - con_mfe) if inc_mfe is not None and con_mfe is not None else None
    mae_spread_amt = (inc_mae - con_mae) if inc_mae is not None and con_mae is not None else None
    mfe_spread_r = (mfe_r - con_mfe_r) if mfe_r is not None and con_mfe_r is not None else None
    mae_spread_r = (mae_r - con_mae_r) if mae_r is not None and con_mae_r is not None else None

    gross_r = _r_value(gross_pnl, initial_risk)

    exit_eff: Decimal | None = None
    eff_over_100 = False
    if inc_mfe is not None and inc_mfe > 0 and gross_pnl is not None:
        exit_eff = (gross_pnl / inc_mfe) * Decimal("100")
        if exit_eff > Decimal("100"):
            eff_over_100 = True
            track.flags.append("EFFICIENCY_OVER_100")

    r_left = (mfe_r - gross_r) if mfe_r is not None and gross_r is not None else None

    peak_gb_amt: Decimal | None = None
    peak_gb_pct: Decimal | None = None
    peak_gb_r: Decimal | None = None
    if inc_mfe is not None and inc_mfe > 0 and gross_pnl is not None:
        peak_gb_amt = inc_mfe - gross_pnl
        peak_gb_pct = (peak_gb_amt / inc_mfe) * Decimal("100")
        peak_gb_r = _r_value(peak_gb_amt, initial_risk)

    def _seconds(start: datetime, end: datetime | None) -> int | None:
        if end is None:
            return None
        return int((_ensure_utc(end) - _ensure_utc(start)).total_seconds())

    flags = list(track.flags)
    if not is_consolidated:
        flags.append("PARTIAL_FEED")
    if provider_missing:
        flags.append("PROVIDER_MISSING_DATA")

    quality = "ESTIMATED_1M"
    if provider_missing and diag.get("bar_count", 0) == 0:
        quality = "NO_INTRADAY_DATA"
    elif not provider_missing and diag.get("bar_count", 0) == 0:
        quality = "NO_INTRADAY_DATA"

    post = diag.get("post_exit") or {}

    rec = TradeExcursion(
        trade_id=trade.id,
        data_provider=provider,
        data_feed=feed,
        data_resolution="1Min",
        is_consolidated=is_consolidated,
        holding_start_utc=_ensure_utc(holding_start),
        holding_end_utc=_ensure_utc(holding_end),
        reference_entry_price=entry,
        price_mfe=quantize_price(price_mfe),
        price_mae=quantize_price(price_mae),
        price_mfe_pct=(price_mfe / entry * Decimal("100")) if entry > 0 else None,
        price_mae_pct=(price_mae / entry * Decimal("100")) if entry > 0 else None,
        conservative_price_mfe=quantize_price(con_price_mfe),
        conservative_price_mae=quantize_price(con_price_mae),
        position_mfe_amount=inc_mfe,
        position_mae_amount=inc_mae,
        mfe_r=mfe_r,
        mae_r=mae_r,
        conservative_position_mfe_amount=con_mfe,
        conservative_position_mae_amount=con_mae,
        conservative_mfe_r=con_mfe_r,
        conservative_mae_r=con_mae_r,
        mfe_boundary_spread_amount=mfe_spread_amt,
        mfe_boundary_spread_r=mfe_spread_r,
        mae_boundary_spread_amount=mae_spread_amt,
        mae_boundary_spread_r=mae_spread_r,
        mfe_time_utc=track.inclusive_mfe_time,
        mae_time_utc=track.inclusive_mae_time,
        time_to_mfe_seconds=_seconds(holding_start, track.inclusive_mfe_time),
        time_to_mae_seconds=_seconds(holding_start, track.inclusive_mae_time),
        mfe_to_exit_seconds=_seconds(track.inclusive_mfe_time, holding_end) if track.inclusive_mfe_time else None,
        gross_realized_pnl=gross_pnl,
        gross_realized_r=gross_r,
        exit_efficiency_pct=exit_eff,
        r_left_on_table=r_left,
        peak_giveback_amount=peak_gb_amt,
        peak_giveback_r=peak_gb_r,
        peak_giveback_pct=peak_gb_pct,
        post_exit_favorable_5m=post.get(5),
        post_exit_favorable_15m=post.get(15),
        post_exit_favorable_30m=post.get(30),
        post_exit_favorable_5m_r=_r_value(post.get(5), initial_risk),
        post_exit_favorable_15m_r=_r_value(post.get(15), initial_risk),
        post_exit_favorable_30m_r=_r_value(post.get(30), initial_risk),
        quality_status=quality,
        quality_flags_json=json.dumps(sorted(set(flags))) if flags else None,
        boundary_ambiguity=track.boundary_ambiguity,
        efficiency_over_100=eff_over_100,
        sparse_interval=diag.get("sparse", False),
        longest_bar_gap_seconds=diag.get("longest_gap_seconds"),
        provider_missing_data=provider_missing,
        calculation_version=CALCULATION_VERSION,
        calculated_at=datetime.now(timezone.utc),
    )

    if copilot and copilot.exit_time_utc and copilot.exit_price is not None and trade.avg_exit_price is not None:
        rec.copilot_exit_time_utc = _ensure_utc(copilot.exit_time_utc)
        rec.copilot_exit_price = copilot.exit_price
        rec.copilot_exit_delta_seconds = int(
            (_ensure_utc(holding_end) - _ensure_utc(copilot.exit_time_utc)).total_seconds()
        )
        if trade.direction == "LONG":
            rec.copilot_exit_delta_price = trade.avg_exit_price - copilot.exit_price
        else:
            rec.copilot_exit_delta_price = copilot.exit_price - trade.avg_exit_price
        if copilot.exit_price > 0:
            rec.copilot_exit_delta_pct = (rec.copilot_exit_delta_price / copilot.exit_price) * Decimal("100")

    return rec


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)
