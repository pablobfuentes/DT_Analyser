/** Pre-entry cohort keys — keep in sync with backend FILTER_TIMING. */
export const PRE_ENTRY_FILTER_KEYS = new Set([
  'weekday',
  'entry_hour',
  'entry_30m',
  'entry_15m',
  'entry_price_bucket',
  'quantity_bucket',
  'position_value_bucket',
  'trade_number',
  'prev_outcome',
  'consec_losses',
  'daily_pnl_state',
  'symbol',
  'source_bucket',
  'direction_bucket',
  'month',
  'week',
  'day_of_month',
  'fill_count',
  'entry_style',
  'gap_bucket',
  'prior_rvol_bucket',
  'atr_bucket',
  'entry_atr_bucket',
  'entry_sma20_bucket',
  'entry_sma50_bucket',
  'market_gap_bucket',
  'strategy_key',
  'strategy_version',
  'signal_origin',
  'setup_quality',
  'signal_gap_bucket',
  'signal_rvol_bucket',
  'impulse_bucket',
  'retracement_bucket',
  'context_5m',
  'vwap_condition',
  'ema9_condition',
  'volume_confirmed',
  'suggested_shares_bucket',
  'planned_pv_bucket',
  'planned_exposure_bucket',
  'initial_risk_bucket',
  'risk_pct_equity_bucket',
  'stop_distance_pct_bucket',
]);

export function isPreEntryFilter(key: string): boolean {
  return PRE_ENTRY_FILTER_KEYS.has(key);
}

/** True if any filter is unavailable by entry (post-entry / EOD / exit). */
export function isRetrospectiveFilters(filters: Record<string, string>): boolean {
  return Object.keys(filters).some((k) => !isPreEntryFilter(k));
}

export const RETROSPECTIVE_FORWARD_BLOCKED =
  'This pattern uses information unavailable by entry and cannot be forward-tested as an entry rule.';

export function cloneFilters(filters: Record<string, string>): Record<string, string> {
  return { ...filters };
}

export function swapCohorts<T>(a: T, b: T): [T, T] {
  return [b, a];
}
