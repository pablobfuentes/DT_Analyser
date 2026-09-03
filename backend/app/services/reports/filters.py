"""Trade filter set — global + exploration filters."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

from fastapi import HTTPException

from app.services.dashboard_service import DashboardFilters


@dataclass
class TradeFilterSet:
    global_filters: DashboardFilters = field(default_factory=DashboardFilters)
    exploration: dict[str, str] = field(default_factory=dict)
    include_partial_feed: bool = False
    pine_scope: str = "REALTIME"
    include_suggested_signals: bool = False

    EXPLORATION_KEYS = frozenset({
        "weekday",
        "entry_hour",
        "entry_30m",
        "entry_15m",
        "duration_bucket",
        "entry_price_bucket",
        "quantity_bucket",
        "position_value_bucket",
        "trade_number",
        "prev_outcome",
        "consec_losses",
        "daily_pnl_state",
        "symbol",
        "source_bucket",
        "direction_bucket",
        "month",
        "week",
        "day_of_month",
        "fill_count",
        "entry_style",
        "exit_style",
        "pnl_bucket",
        "outcome",
        "gap_bucket",
        "volume_bucket",
        "rvol_bucket",
        "prior_rvol_bucket",
        "movement_bucket",
        "atr_bucket",
        "entry_atr_bucket",
        "tr_atr_bucket",
        "day_type",
        "entry_sma20_bucket",
        "entry_sma50_bucket",
        "market_movement_bucket",
        "market_gap_bucket",
        "market_day_type",
        "mfe_r_bucket",
        "mae_r_bucket",
        "exit_efficiency_bucket",
        "r_left_bucket",
        "time_to_mfe_bucket",
        "time_to_mae_bucket",
        "mfe_to_exit_bucket",
        "peak_giveback_bucket",
        "strategy_key",
        "strategy_version",
        "signal_origin",
        "setup_quality",
        "signal_gap_bucket",
        "signal_rvol_bucket",
        "impulse_bucket",
        "retracement_bucket",
        "context_5m",
        "vwap_condition",
        "ema9_condition",
        "volume_confirmed",
        "suggested_shares_bucket",
        "planned_pv_bucket",
        "planned_exposure_bucket",
        "exit_reason",
        "r_outcome_bucket",
        "initial_risk_bucket",
        "risk_pct_equity_bucket",
        "stop_distance_pct_bucket",
    })


def parse_filter_set(params: dict[str, Any]) -> TradeFilterSet:
    gf = DashboardFilters()
    try:
        if params.get("start_date"):
            gf.start_date = date.fromisoformat(str(params["start_date"]))
        if params.get("end_date"):
            gf.end_date = date.fromisoformat(str(params["end_date"]))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid date: {exc}") from exc
    if params.get("account_id"):
        gf.account_id = int(params["account_id"])
    if params.get("source_type"):
        gf.source_type = str(params["source_type"])
    if params.get("direction"):
        gf.direction = str(params["direction"])
    if params.get("ticker"):
        gf.ticker = str(params["ticker"])

    exploration: dict[str, str] = {}
    for k, v in params.items():
        if k in TradeFilterSet.EXPLORATION_KEYS and v:
            exploration[k] = str(v)

    include_partial = str(params.get("include_partial_feed") or "").lower() in ("1", "true", "yes")
    pine_scope = str(params.get("pine_scope") or "REALTIME").upper()
    if pine_scope not in ("REALTIME", "HISTORICAL_REPLAY", "BACKTEST", "UNKNOWN", "ALL"):
        pine_scope = "REALTIME"
    include_suggested = str(params.get("include_suggested_signals") or "").lower() in ("1", "true", "yes")
    return TradeFilterSet(
        global_filters=gf,
        exploration=exploration,
        include_partial_feed=include_partial,
        pine_scope=pine_scope,
        include_suggested_signals=include_suggested,
    )


def apply_exploration(trade_features: dict[str, str], filt: TradeFilterSet) -> bool:
    for key, value in filt.exploration.items():
        feat_key = _exploration_to_feature_key(key)
        if feat_key and trade_features.get(feat_key) != value:
            return False
    return True


def _exploration_to_feature_key(param: str) -> str:
    return {
        "weekday": "day_of_week",
        "entry_hour": "entry_hour",
        "entry_30m": "entry_30m",
        "entry_15m": "entry_15m",
        "duration_bucket": "duration",
        "entry_price_bucket": "entry_price",
        "quantity_bucket": "quantity",
        "position_value_bucket": "position_value",
        "trade_number": "trade_number",
        "prev_outcome": "prev_outcome",
        "consec_losses": "consec_losses",
        "daily_pnl_state": "daily_pnl_state",
        "symbol": "symbol",
        "source_bucket": "source",
        "direction_bucket": "direction",
        "month": "month",
        "week": "week",
        "day_of_month": "day_of_month",
        "fill_count": "fill_count",
        "entry_style": "entry_style",
        "exit_style": "exit_style",
        "pnl_bucket": "pnl_bucket",
        "outcome": "outcome",
        "gap_bucket": "opening_gap_bucket",
        "volume_bucket": "day_volume_bucket",
        "rvol_bucket": "rvol50_bucket",
        "prior_rvol_bucket": "prior_rvol_bucket",
        "movement_bucket": "movement_bucket",
        "atr_bucket": "atr14_bucket",
        "entry_atr_bucket": "entry_atr_bucket",
        "tr_atr_bucket": "tr_atr_bucket",
        "day_type": "day_type",
        "entry_sma20_bucket": "entry_sma20_bucket",
        "entry_sma50_bucket": "entry_sma50_bucket",
        "market_movement_bucket": "market_movement_bucket",
        "market_gap_bucket": "market_gap_bucket",
        "market_day_type": "market_day_type",
        "mfe_r_bucket": "mfe_r_bucket",
        "mae_r_bucket": "mae_r_bucket",
        "exit_efficiency_bucket": "exit_efficiency_bucket",
        "r_left_bucket": "r_left_bucket",
        "time_to_mfe_bucket": "time_to_mfe_bucket",
        "time_to_mae_bucket": "time_to_mae_bucket",
        "mfe_to_exit_bucket": "mfe_to_exit_bucket",
        "peak_giveback_bucket": "peak_giveback_bucket",
        "strategy_key": "strategy_key",
        "strategy_version": "strategy_version",
        "signal_origin": "signal_origin",
        "setup_quality": "setup_quality",
        "signal_gap_bucket": "signal_gap_bucket",
        "signal_rvol_bucket": "signal_rvol_bucket",
        "impulse_bucket": "impulse_bucket",
        "retracement_bucket": "retracement_bucket",
        "context_5m": "context_5m",
        "vwap_condition": "above_vwap",
        "ema9_condition": "above_ema9",
        "volume_confirmed": "volume_confirmed",
        "suggested_shares_bucket": "suggested_shares_bucket",
        "planned_pv_bucket": "planned_position_value_bucket",
        "planned_exposure_bucket": "planned_exposure_bucket",
        "exit_reason": "mechanical_exit_reason",
        "r_outcome_bucket": "r_outcome_bucket",
        "initial_risk_bucket": "initial_risk_bucket",
        "risk_pct_equity_bucket": "risk_pct_equity_bucket",
        "stop_distance_pct_bucket": "stop_distance_pct_bucket",
    }.get(param, param)


def filters_from_query(**params: Any) -> TradeFilterSet:
    clean = {k: v for k, v in params.items() if v is not None}
    return parse_filter_set(clean)


def exploration_param_for_feature(feature: str) -> str | None:
    return {
        "day_of_week": "weekday",
        "entry_hour": "entry_hour",
        "entry_30m": "entry_30m",
        "entry_15m": "entry_15m",
        "duration": "duration_bucket",
        "entry_price": "entry_price_bucket",
        "quantity": "quantity_bucket",
        "position_value": "position_value_bucket",
        "trade_number": "trade_number",
        "prev_outcome": "prev_outcome",
        "consec_losses": "consec_losses",
        "daily_pnl_state": "daily_pnl_state",
        "symbol": "symbol",
        "source": "source_bucket",
        "direction": "direction_bucket",
        "month": "month",
        "week": "week",
        "day_of_month": "day_of_month",
        "fill_count": "fill_count",
        "entry_style": "entry_style",
        "exit_style": "exit_style",
        "pnl_bucket": "pnl_bucket",
        "outcome": "outcome",
        "opening_gap_bucket": "gap_bucket",
        "day_volume_bucket": "volume_bucket",
        "rvol50_bucket": "rvol_bucket",
        "prior_rvol_bucket": "prior_rvol_bucket",
        "movement_bucket": "movement_bucket",
        "atr14_bucket": "atr_bucket",
        "entry_atr_bucket": "entry_atr_bucket",
        "tr_atr_bucket": "tr_atr_bucket",
        "day_type": "day_type",
        "entry_sma20_bucket": "entry_sma20_bucket",
        "entry_sma50_bucket": "entry_sma50_bucket",
        "market_movement_bucket": "market_movement_bucket",
        "market_gap_bucket": "market_gap_bucket",
        "market_day_type": "market_day_type",
        "mfe_r_bucket": "mfe_r_bucket",
        "mae_r_bucket": "mae_r_bucket",
        "exit_efficiency_bucket": "exit_efficiency_bucket",
        "r_left_bucket": "r_left_bucket",
        "time_to_mfe_bucket": "time_to_mfe_bucket",
        "time_to_mae_bucket": "time_to_mae_bucket",
        "mfe_to_exit_bucket": "mfe_to_exit_bucket",
        "peak_giveback_bucket": "peak_giveback_bucket",
        "strategy_key": "strategy_key",
        "strategy_version": "strategy_version",
        "signal_origin": "signal_origin",
        "setup_quality": "setup_quality",
        "signal_gap_bucket": "signal_gap_bucket",
        "signal_rvol_bucket": "signal_rvol_bucket",
        "impulse_bucket": "impulse_bucket",
        "retracement_bucket": "retracement_bucket",
        "context_5m": "context_5m",
        "above_vwap": "vwap_condition",
        "above_ema9": "ema9_condition",
        "volume_confirmed": "volume_confirmed",
        "suggested_shares_bucket": "suggested_shares_bucket",
        "planned_position_value_bucket": "planned_pv_bucket",
        "planned_exposure_bucket": "planned_exposure_bucket",
        "mechanical_exit_reason": "exit_reason",
        "r_outcome_bucket": "r_outcome_bucket",
        "initial_risk_bucket": "initial_risk_bucket",
        "risk_pct_equity_bucket": "risk_pct_equity_bucket",
        "stop_distance_pct_bucket": "stop_distance_pct_bucket",
    }.get(feature)


def exploration_param_for_dimension(dim: str) -> str | None:
    mapping = {
        "day_of_week": "weekday",
        "entry_hour": "entry_hour",
        "entry_30m": "entry_30m",
        "entry_15m": "entry_15m",
        "duration": "duration_bucket",
        "entry_price": "entry_price_bucket",
        "quantity": "quantity_bucket",
        "position_value": "position_value_bucket",
        "trade_number": "trade_number",
        "prev_outcome": "prev_outcome",
        "consec_losses": "consec_losses",
        "daily_pnl_state": "daily_pnl_state",
        "symbol": "symbol",
        "source": "source_bucket",
        "direction": "direction_bucket",
        "month": "month",
        "week": "week",
        "day_of_month": "day_of_month",
        "fill_count": "fill_count",
        "entry_style": "entry_style",
        "exit_style": "exit_style",
        "pnl_distribution": "pnl_bucket",
        "outcome_composition": "outcome",
    }
    return mapping.get(dim)
