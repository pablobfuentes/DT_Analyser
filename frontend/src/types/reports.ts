export interface ReportBucket {
  key: string;
  label: string;
  trade_count: number;
  wins: number;
  losses: number;
  breakeven: number;
  net_pnl: string;
  avg_trade: string;
  win_rate: string | null;
  avg_winner: string | null;
  avg_loser: string | null;
  excursion_available?: number;
  r_qualified_count?: number;
  excursion_coverage_pct?: string | null;
  r_coverage_pct?: string | null;
  average_mfe_r?: string | null;
  average_mae_r?: string | null;
  average_exit_efficiency?: string | null;
  average_r_left?: string | null;
  average_peak_giveback?: string | null;
  average_time_to_mfe?: string | null;
  average_r?: string | null;
  total_r?: string | null;
  r_profit_factor?: string | null;
  r_profit_factor_status?: string | null;
}

export interface ReportMetric {
  key: string;
  label: string;
}

export interface ReportData {
  key: string;
  title: string;
  section: string;
  available: boolean;
  default_metric: string;
  chart_type: 'bar' | 'line' | 'horizontal_bar';
  buckets: ReportBucket[];
  best_bucket: { key: string; label: string; net_pnl: string; trade_count: number } | null;
  worst_bucket: { key: string; label: string; net_pnl: string; trade_count: number } | null;
  filter_dimension: string | null;
  feature_key?: string;
  availability_timing?: 'PRE_ENTRY' | 'END_OF_DAY' | 'EXIT' | null;
  description?: string | null;
  coverage?: {
    matching_trades: number;
    data_available: number;
    coverage_pct: number;
    excluded: number;
    exclusion_reasons?: Record<string, number>;
    scope?: string;
  };
}

export interface ReportSection {
  key: string;
  label: string;
  available: boolean;
  requires?: string | null;
  reports: ReportData[];
  pine_scope?: string;
  mixed_strategy_versions?: {
    warning: string;
    versions: { normalized: string; original: string; sample_size: number }[];
  } | null;
  empty_realtime_message?: string | null;
  empty_r_message?: string | null;
}

export interface ReportsResponse {
  matching_trade_count: number;
  active_exploration_filters: Record<string, string>;
  global_filters: Record<string, string | number | null>;
  metrics: ReportMetric[];
  sections: ReportSection[];
  market_data?: {
    configured: boolean;
    provider: string;
    feed: string | null;
    is_consolidated: boolean | null;
    include_partial_feed?: boolean;
    cohort_market_available?: number;
  };
}

export type MetricKey =
  | 'net_pnl'
  | 'avg_trade'
  | 'win_rate'
  | 'trade_count'
  | 'avg_winner'
  | 'avg_loser'
  | 'average_mfe_r'
  | 'average_mae_r'
  | 'average_exit_efficiency'
  | 'average_r_left'
  | 'average_peak_giveback'
  | 'average_time_to_mfe'
  | 'average_r'
  | 'total_r'
  | 'r_profit_factor'
  | 'r_coverage_pct';

export const EXPLORATION_KEYS = [
  'weekday',
  'entry_hour',
  'entry_30m',
  'entry_15m',
  'duration_bucket',
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
  'exit_style',
  'pnl_bucket',
  'outcome',
  'gap_bucket',
  'volume_bucket',
  'rvol_bucket',
  'prior_rvol_bucket',
  'movement_bucket',
  'atr_bucket',
  'entry_atr_bucket',
  'tr_atr_bucket',
  'day_type',
  'entry_sma20_bucket',
  'entry_sma50_bucket',
  'market_movement_bucket',
  'market_gap_bucket',
  'market_day_type',
  'mfe_r_bucket',
  'mae_r_bucket',
  'exit_efficiency_bucket',
  'r_left_bucket',
  'time_to_mfe_bucket',
  'time_to_mae_bucket',
  'mfe_to_exit_bucket',
  'peak_giveback_bucket',
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
  'exit_reason',
  'r_outcome_bucket',
  'initial_risk_bucket',
  'risk_pct_equity_bucket',
  'stop_distance_pct_bucket',
] as const;

export type ExplorationKey = (typeof EXPLORATION_KEYS)[number];

export const EXPLORATION_LABELS: Record<string, string> = {
  weekday: 'Day of Week',
  entry_hour: 'Entry Hour',
  entry_30m: '30-Min Window',
  entry_15m: '15-Min Window',
  duration_bucket: 'Duration',
  entry_price_bucket: 'Entry Price',
  quantity_bucket: 'Quantity',
  position_value_bucket: 'Position Value',
  trade_number: 'Trade # of Day',
  prev_outcome: 'After Previous',
  consec_losses: 'Consecutive Losses',
  daily_pnl_state: 'Daily P&L Before Entry',
  symbol: 'Symbol',
  source_bucket: 'Source',
  direction_bucket: 'Direction',
  month: 'Month',
  week: 'Week',
  day_of_month: 'Day of Month',
  fill_count: 'Fill Count',
  entry_style: 'Entry Style',
  exit_style: 'Exit Style',
  pnl_bucket: 'P&L Range',
  outcome: 'Outcome',
  gap_bucket: 'Gap',
  volume_bucket: 'Daily Volume',
  rvol_bucket: 'RVOL50',
  prior_rvol_bucket: 'Prior-Day RVOL',
  movement_bucket: 'Daily Movement',
  atr_bucket: 'ATR(14)',
  entry_atr_bucket: 'Entry vs ATR',
  tr_atr_bucket: 'Relative Volatility',
  day_type: 'Instrument Day Type',
  entry_sma20_bucket: 'Entry vs SMA20',
  entry_sma50_bucket: 'Entry vs SMA50',
  market_movement_bucket: 'SPY Movement',
  market_gap_bucket: 'SPY Gap',
  market_day_type: 'SPY Day Type',
  mfe_r_bucket: 'MFE R',
  mae_r_bucket: 'MAE R',
  exit_efficiency_bucket: 'Exit Efficiency',
  r_left_bucket: 'R Left on Table',
  time_to_mfe_bucket: 'Time to MFE',
  time_to_mae_bucket: 'Time to MAE',
  mfe_to_exit_bucket: 'MFE to Exit',
  peak_giveback_bucket: 'Peak Giveback',
  strategy_key: 'Strategy',
  strategy_version: 'Strategy Version',
  signal_origin: 'Signal Origin',
  setup_quality: 'Setup Quality',
  signal_gap_bucket: 'Signal-Time Gap',
  signal_rvol_bucket: 'Signal-Time RVOL',
  impulse_bucket: 'Impulse',
  retracement_bucket: 'Retracement',
  context_5m: '5m Context',
  vwap_condition: 'VWAP',
  ema9_condition: 'EMA9',
  volume_confirmed: 'Volume Confirmation',
  suggested_shares_bucket: 'Suggested Shares',
  planned_pv_bucket: 'Planned Position Value',
  planned_exposure_bucket: 'Planned Exposure',
  exit_reason: 'Copilot Exit Reason',
  r_outcome_bucket: 'R Outcome (retrospective)',
  initial_risk_bucket: 'Initial Risk $',
  risk_pct_equity_bucket: 'Risk % Equity',
  stop_distance_pct_bucket: 'Stop Distance %',
};
