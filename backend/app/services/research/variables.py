"""RESEARCH_VARIABLES and heatmap dimensions. No arbitrary DB columns."""

from __future__ import annotations

# Timing: PRE_ENTRY | SIGNAL | ENTRY | POST_ENTRY | EXIT | END_OF_DAY | POST_EXIT
# SIGNAL and ENTRY are allowed in PRE_ENTRY_ONLY mode.

PRE_ENTRY_CLASSES = frozenset({"PRE_ENTRY", "SIGNAL", "ENTRY"})

# Graph exploration param → timing. Used to block lookahead cohort filters.
FILTER_TIMING: dict[str, str] = {
    "weekday": "PRE_ENTRY",
    "entry_hour": "ENTRY",
    "entry_30m": "ENTRY",
    "entry_15m": "ENTRY",
    "duration_bucket": "EXIT",
    "entry_price_bucket": "ENTRY",
    "quantity_bucket": "ENTRY",
    "position_value_bucket": "ENTRY",
    "trade_number": "PRE_ENTRY",
    "prev_outcome": "PRE_ENTRY",
    "consec_losses": "PRE_ENTRY",
    "daily_pnl_state": "PRE_ENTRY",
    "symbol": "ENTRY",
    "source_bucket": "ENTRY",
    "direction_bucket": "ENTRY",
    "month": "PRE_ENTRY",
    "week": "PRE_ENTRY",
    "day_of_month": "PRE_ENTRY",
    "fill_count": "ENTRY",
    "entry_style": "ENTRY",
    "exit_style": "EXIT",
    "pnl_bucket": "EXIT",
    "outcome": "EXIT",
    "gap_bucket": "PRE_ENTRY",
    "volume_bucket": "END_OF_DAY",
    "rvol_bucket": "END_OF_DAY",
    "prior_rvol_bucket": "PRE_ENTRY",
    "movement_bucket": "END_OF_DAY",
    "atr_bucket": "PRE_ENTRY",
    "entry_atr_bucket": "PRE_ENTRY",
    "tr_atr_bucket": "END_OF_DAY",
    "day_type": "END_OF_DAY",
    "entry_sma20_bucket": "PRE_ENTRY",
    "entry_sma50_bucket": "PRE_ENTRY",
    "market_movement_bucket": "END_OF_DAY",
    "market_gap_bucket": "PRE_ENTRY",
    "market_day_type": "END_OF_DAY",
    "mfe_r_bucket": "POST_ENTRY",
    "mae_r_bucket": "POST_ENTRY",
    "exit_efficiency_bucket": "POST_ENTRY",
    "r_left_bucket": "POST_ENTRY",
    "time_to_mfe_bucket": "POST_ENTRY",
    "time_to_mae_bucket": "POST_ENTRY",
    "mfe_to_exit_bucket": "POST_ENTRY",
    "peak_giveback_bucket": "POST_ENTRY",
    "strategy_key": "SIGNAL",
    "strategy_version": "SIGNAL",
    "signal_origin": "SIGNAL",
    "setup_quality": "SIGNAL",
    "signal_gap_bucket": "SIGNAL",
    "signal_rvol_bucket": "SIGNAL",
    "impulse_bucket": "SIGNAL",
    "retracement_bucket": "SIGNAL",
    "context_5m": "SIGNAL",
    "vwap_condition": "SIGNAL",
    "ema9_condition": "SIGNAL",
    "volume_confirmed": "SIGNAL",
    "suggested_shares_bucket": "SIGNAL",
    "planned_pv_bucket": "SIGNAL",
    "planned_exposure_bucket": "SIGNAL",
    "exit_reason": "EXIT",
    "r_outcome_bucket": "EXIT",
    "initial_risk_bucket": "ENTRY",
    "risk_pct_equity_bucket": "ENTRY",
    "stop_distance_pct_bucket": "ENTRY",
}


def _v(
    key: str,
    label: str,
    source: str,
    timing: str,
    units: str,
    description: str,
    *,
    quality: str | None = None,
    numeric: bool = True,
    x: bool = True,
    y: bool = True,
) -> dict:
    return {
        "key": key,
        "label": label,
        "source": source,
        "data_type": "numeric" if numeric else "categorical",
        "timing_class": timing,
        "units": units,
        "description": description,
        "quality_requirement": quality,
        "nullable": True,
        "allowed_as_x": x and numeric,
        "allowed_as_y": y and numeric,
        "allowed_pre_entry": timing in PRE_ENTRY_CLASSES,
    }


RESEARCH_VARIABLES: list[dict] = [
    _v("actual_r", "Actual R", "Trade + Risk", "EXIT", "R", "Realized R = effective P&L / initial risk."),
    _v("net_pnl", "Net P&L", "Trade", "EXIT", "USD", "Effective realized P&L."),
    _v("hold_seconds", "Hold Duration", "Trade", "EXIT", "seconds", "Holding interval seconds."),
    _v("minutes_since_open", "Minutes Since Open", "Trade", "ENTRY", "minutes", "NY minutes after 09:30 on entry bar."),
    _v("entry_price", "Entry Price", "Trade", "ENTRY", "USD", "Weighted average entry."),
    _v("quantity", "Opening Quantity", "Trade", "ENTRY", "shares", "Position-cycle opening quantity."),
    _v("position_value", "Position Value", "Trade", "ENTRY", "USD", "avg entry × quantity."),
    _v("initial_risk_amount", "Initial Risk $", "Risk", "ENTRY", "USD", "Actual initial dollar risk."),
    _v("risk_pct_equity", "Risk % Equity", "Risk", "ENTRY", "%", "Initial risk / equity-at-entry."),
    _v("stop_distance_pct", "Stop Distance %", "Risk", "ENTRY", "%", "Risk per share / entry."),
    _v("signal_rvol", "Signal RVOL", "Pine", "SIGNAL", "x", "Pine signal-time RVOL.", quality="PINE_SIGNAL"),
    _v("signal_gap_pct", "Signal Gap %", "Pine", "SIGNAL", "%", "Pine signal-time gap.", quality="PINE_SIGNAL"),
    _v("impulse_pct", "Impulse %", "Pine", "SIGNAL", "%", "Pine impulse.", quality="PINE_SIGNAL"),
    _v("retracement_pct", "Retracement %", "Pine", "SIGNAL", "%", "Pine retracement.", quality="PINE_SIGNAL"),
    _v("opening_gap_pct", "Opening Gap %", "Market", "PRE_ENTRY", "%", "Regular-session open vs prior close."),
    _v("prior_rvol50", "Prior-Day RVOL50", "Market", "PRE_ENTRY", "x", "Prior session RVOL50.", quality="FULL_FEED"),
    _v("rvol50_eod", "Instrument RVOL50 EOD", "Market", "END_OF_DAY", "x", "Same-day RVOL50.", quality="FULL_FEED"),
    _v("atr14_prior", "ATR(14) Prior", "Market", "PRE_ENTRY", "USD", "Prior ATR14."),
    _v("mfe_r", "MFE R", "Intraday + Risk", "POST_ENTRY", "R", "Maximum favorable excursion in R.", quality="EXCURSION"),
    _v("mae_r", "MAE R", "Intraday + Risk", "POST_ENTRY", "R", "Maximum adverse excursion in R.", quality="EXCURSION"),
    _v("exit_efficiency_pct", "Exit Efficiency %", "Intraday + Risk", "POST_ENTRY", "%", "Capture of MFE.", quality="EXCURSION"),
    _v("r_left_on_table", "R Left on Table", "Intraday + Risk", "POST_ENTRY", "R", "MFE R minus realized R.", quality="EXCURSION"),
    _v("time_to_mfe_seconds", "Time to MFE", "Intraday", "POST_ENTRY", "seconds", "Seconds from entry to MFE.", quality="EXCURSION"),
    _v("post_exit_favorable_15m_r", "Post-Exit +15m R", "Intraday", "POST_EXIT", "R", "Favorable extension after exit.", quality="EXCURSION"),
]

HEATMAP_DIMENSIONS: list[dict] = [
    {"key": "weekday", "feature": "day_of_week", "label": "Day of Week", "timing_class": "PRE_ENTRY", "top_n": None},
    {"key": "entry_15m", "feature": "entry_15m", "label": "15m Entry Window", "timing_class": "ENTRY", "top_n": None},
    {"key": "entry_price_bucket", "feature": "entry_price", "label": "Entry Price", "timing_class": "ENTRY", "top_n": None},
    {"key": "gap_bucket", "feature": "opening_gap_bucket", "label": "Opening Gap", "timing_class": "PRE_ENTRY", "top_n": None},
    {"key": "rvol_bucket", "feature": "rvol50_bucket", "label": "RVOL50 EOD", "timing_class": "END_OF_DAY", "top_n": None},
    {"key": "prior_rvol_bucket", "feature": "prior_rvol_bucket", "label": "Prior-Day RVOL", "timing_class": "PRE_ENTRY", "top_n": None},
    {"key": "atr_bucket", "feature": "atr14_bucket", "label": "ATR(14)", "timing_class": "PRE_ENTRY", "top_n": None},
    {"key": "market_gap_bucket", "feature": "market_gap_bucket", "label": "Market Gap", "timing_class": "PRE_ENTRY", "top_n": None},
    {"key": "setup_quality", "feature": "setup_quality", "label": "Setup Quality", "timing_class": "SIGNAL", "top_n": None},
    {"key": "signal_rvol_bucket", "feature": "signal_rvol_bucket", "label": "Signal RVOL", "timing_class": "SIGNAL", "top_n": None},
    {"key": "impulse_bucket", "feature": "impulse_bucket", "label": "Impulse", "timing_class": "SIGNAL", "top_n": None},
    {"key": "retracement_bucket", "feature": "retracement_bucket", "label": "Retracement", "timing_class": "SIGNAL", "top_n": None},
    {"key": "context_5m", "feature": "context_5m", "label": "5m Context", "timing_class": "SIGNAL", "top_n": None},
    {"key": "strategy_version", "feature": "strategy_version", "label": "Strategy Version", "timing_class": "SIGNAL", "top_n": None},
    {"key": "risk_pct_equity_bucket", "feature": "risk_pct_equity_bucket", "label": "Risk % Equity", "timing_class": "ENTRY", "top_n": None},
    {"key": "mfe_r_bucket", "feature": "mfe_r_bucket", "label": "MFE R", "timing_class": "POST_ENTRY", "top_n": None},
    {"key": "mae_r_bucket", "feature": "mae_r_bucket", "label": "MAE R", "timing_class": "POST_ENTRY", "top_n": None},
    {"key": "symbol", "feature": "symbol", "label": "Ticker", "timing_class": "ENTRY", "top_n": 20},
    {"key": "day_type", "feature": "day_type", "label": "Instrument Day Type", "timing_class": "END_OF_DAY", "top_n": None},
]

HEATMAP_METRICS = [
    "trade_count",
    "net_pnl",
    "avg_trade",
    "win_rate",
    "average_r",
    "total_r",
    "profit_factor",
    "r_profit_factor",
    "average_mfe_r",
    "average_mae_r",
    "average_exit_efficiency",
    "average_r_left",
]


def variable_by_key(key: str) -> dict | None:
    return next((v for v in RESEARCH_VARIABLES if v["key"] == key), None)


def heatmap_dim(key: str) -> dict | None:
    return next((d for d in HEATMAP_DIMENSIONS if d["key"] == key), None)


def list_variables() -> list[dict]:
    return list(RESEARCH_VARIABLES)


def list_heatmap_dimensions(*, research_mode: str) -> list[dict]:
    if research_mode != "PRE_ENTRY_ONLY":
        return list(HEATMAP_DIMENSIONS)
    return [d for d in HEATMAP_DIMENSIONS if d["timing_class"] in PRE_ENTRY_CLASSES]
