export interface DashboardSummary {
  trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  net_pnl: string | null;
  gross_pnl: string | null;
  fees: string | null;
  win_rate: string | null;
  avg_trade: string | null;
  avg_winner: string | null;
  avg_loser: string | null;
  best_trade: string | null;
  worst_trade: string | null;
  avg_hold_seconds: number | null;
}

export interface DashboardEquity {
  starting_equity: string | null;
  account_starting_equity?: string | null;
  current_realized_equity: string | null;
  realized_return_pct: string | null;
  available: boolean;
  reason?: string;
}

export interface DashboardDailyRow {
  date: string;
  trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  win_rate: string | null;
  gross_pnl: string;
  fees: string;
  net_pnl: string;
  cumulative_pnl: string;
  day_type: string;
}

export interface DashboardRecentTrade {
  id: number;
  exit_time_utc: string | null;
  ticker: string;
  source_type: string;
  direction: string;
  quantity: string;
  avg_entry_price: string;
  avg_exit_price: string | null;
  net_pnl: string;
  holding_seconds: number | null;
}

export interface SourceStats {
  trades: number;
  wins: number;
  losses: number;
  breakeven: number;
  net_pnl: string | null;
  win_rate: string | null;
  avg_trade: string | null;
  avg_winner: string | null;
  avg_loser: string | null;
  best_trade: string | null;
  worst_trade: string | null;
  avg_hold_seconds: number | null;
}

export interface RMetrics {
  trade_count: number;
  missing_count: number;
  coverage_pct: string | null;
  average: string | null;
  median: string | null;
  expectancy: string | null;
  avg_winner: string | null;
  avg_loser: string | null;
  best: string | null;
  worst: string | null;
}

export interface DrawdownMetrics {
  max_dollars: string | null;
  max_pct: string | null;
  max_duration_trading_days: number;
  current_dollars: string | null;
  current_pct: string | null;
  current_duration_trading_days: number;
  current_is_active: boolean;
  label: string;
  pct_available: boolean;
}

export interface StreakMetrics {
  longest_win: number;
  longest_loss: number;
  current_type: string | null;
  current_count: number;
}

export interface AdvancedAnalytics {
  dollar_expectancy: string | null;
  profit_factor: string | null;
  profit_factor_status: string;
  payoff_ratio: string | null;
  r: RMetrics;
  drawdown: DrawdownMetrics;
  streaks: StreakMetrics;
}

export interface RDistributionBucket {
  bucket: string;
  label: string;
  count: number;
  pct: string | null;
}

export interface SourceAdvancedStats {
  dollar_expectancy: string | null;
  profit_factor: string | null;
  profit_factor_status: string;
  payoff_ratio: string | null;
  r_expectancy: string | null;
  average_r: string | null;
  max_drawdown_dollars: string | null;
  max_drawdown_pct: string | null;
  longest_losing_streak: number;
  r_coverage_pct: string | null;
}

export interface DashboardData {
  filters: Record<string, unknown>;
  summary: DashboardSummary;
  secondary: {
    trading_days: number;
    green_days: number;
    red_days: number;
    breakeven_days: number;
    open_trades: number;
  };
  equity: DashboardEquity;
  daily: DashboardDailyRow[];
  cumulative: { date: string; daily_pnl: string; cumulative_pnl: string; trades: number }[];
  source_comparison: { manual: SourceStats | null; auto: SourceStats | null };
  source_comparison_advanced: { manual: SourceAdvancedStats | null; auto: SourceAdvancedStats | null };
  recent_trades: DashboardRecentTrade[];
  warnings: string[];
  empty: boolean;
  advanced: AdvancedAnalytics;
  r_distribution: RDistributionBucket[];
  drawdown_series: {
    date: string;
    drawdown_dollars: string;
    drawdown_pct: string | null;
    peak: string;
    equity: string;
    trades_since_peak: number;
    mode: string;
  }[];
  equity_series: {
    date: string;
    cumulative_pnl: string;
    equity?: string;
    r_trades_included?: number;
  }[];
  cumulative_r_series: {
    date: string;
    cumulative_r: string;
    r_trades_included: number;
  }[];
}

export type DateRangePreset =
  | 'today'
  | 'yesterday'
  | 'this_week'
  | 'last_7'
  | 'this_month'
  | 'last_30'
  | 'all'
  | 'custom';

export interface DashboardFiltersState {
  range: DateRangePreset;
  startDate: string;
  endDate: string;
  accountId: string;
  source: string;
  direction: string;
  ticker: string;
}
