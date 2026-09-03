import type { DashboardFiltersState } from '../types/dashboard';
import { filtersToQueryParams } from '../utils/dates';

import { apiRequest as request } from './base';

export interface ExcursionCoverage {
  total_closed_trades: number;
  excursion_enriched: number;
  excursion_coverage_pct: number | null;
  r_qualified_excursions: number;
  mfe_r_coverage_pct: number | null;
  consolidated_count: number;
  partial_feed_count: number;
  boundary_ambiguous_count: number;
  sparse_interval_count: number;
  missing_count: number;
  copilot_exit_available: number;
  copilot_coverage_pct: number | null;
  copilot_status: string;
  intraday_bars_cached: number;
  unique_symbol_days: number;
  avg_mfe_spread_amount?: number | null;
  avg_mfe_spread_r?: number | null;
  median_mfe_spread_r?: number | null;
  p95_mfe_spread_r?: number | null;
  count_spread_gt_025r?: number;
  count_spread_gt_050r?: number;
  database_size_bytes?: number;
  database_size_mb?: number;
  intraday_bar_count?: number;
  avg_bars_per_symbol_day?: number;
  storage_advisory?: string | null;
}

export interface TradeExcursion {
  trade_id: number;
  data_provider: string | null;
  data_feed: string | null;
  data_resolution: string | null;
  is_consolidated: boolean | null;
  holding_start_utc: string | null;
  holding_end_utc: string | null;
  reference_entry_price: string | null;
  price_mfe: string | null;
  price_mae: string | null;
  conservative_price_mfe: string | null;
  conservative_price_mae: string | null;
  position_mfe_amount: string | null;
  position_mae_amount: string | null;
  mfe_r: string | null;
  mae_r: string | null;
  conservative_position_mfe_amount: string | null;
  conservative_position_mae_amount: string | null;
  conservative_mfe_r: string | null;
  conservative_mae_r: string | null;
  mfe_boundary_spread_amount: string | null;
  mfe_boundary_spread_r: string | null;
  mae_boundary_spread_amount: string | null;
  mae_boundary_spread_r: string | null;
  mfe_time_utc: string | null;
  mae_time_utc: string | null;
  time_to_mfe_seconds: number | null;
  time_to_mae_seconds: number | null;
  mfe_to_exit_seconds: number | null;
  gross_realized_pnl: string | null;
  gross_realized_r: string | null;
  exit_efficiency_pct: string | null;
  r_left_on_table: string | null;
  peak_giveback_amount: string | null;
  peak_giveback_r: string | null;
  peak_giveback_pct: string | null;
  post_exit_favorable_5m: string | null;
  post_exit_favorable_15m: string | null;
  post_exit_favorable_30m: string | null;
  post_exit_favorable_5m_r: string | null;
  post_exit_favorable_15m_r: string | null;
  post_exit_favorable_30m_r: string | null;
  copilot_exit_time_utc: string | null;
  copilot_exit_price: string | null;
  copilot_exit_delta_seconds: number | null;
  copilot_exit_delta_price: string | null;
  copilot_exit_delta_pct: string | null;
  quality_status: string;
  quality_flags: string[];
  boundary_ambiguity: boolean;
  efficiency_over_100: boolean;
  sparse_interval: boolean;
  longest_bar_gap_seconds: number | null;
  provider_missing_data: boolean;
  calculation_version: string | null;
  calculated_at: string | null;
}

export interface ExitAnalysisSummary {
  average_mfe_r?: string | null;
  average_mae_r?: string | null;
  average_exit_efficiency?: string | null;
  median_exit_efficiency?: string | null;
  average_r_left_on_table?: string | null;
  average_peak_giveback_pct?: string | null;
  median_time_to_mfe_seconds?: string | null;
  capture_ge_25_pct?: number | null;
  capture_ge_50_pct?: number | null;
  capture_ge_75_pct?: number | null;
  capture_ge_90_pct?: number | null;
  positive_mfe_to_loss_count?: number;
  positive_mfe_to_loss_pct?: number | null;
  reached_2r_closed_lt_1r?: number;
  reached_2r_closed_losing?: number;
  best_capture_min_mfe_r?: string;
}

export interface ExitAnalysisScatterPoint {
  trade_id: number;
  mfe_r: string;
  mae_r: string | null;
  actual_r: string;
  ticker: string;
}

export interface ExitAnalysisTableRow {
  trade_id: number;
  ticker: string;
  exit_date: string | null;
  actual_r: string | null;
  mfe_r: string | null;
  mae_r: string | null;
  r_left_on_table: string | null;
  exit_efficiency_pct: string | null;
  peak_giveback_r: string | null;
  peak_giveback_pct: string | null;
  mfe_to_exit_seconds: number | null;
  quality_status: string;
}

export interface ExitAnalysisResponse {
  summary: ExitAnalysisSummary;
  coverage: ExcursionCoverage;
  scatter: ExitAnalysisScatterPoint[];
  worst_left_on_table: ExitAnalysisTableRow[];
  worst_giveback: ExitAnalysisTableRow[];
  best_capture: ExitAnalysisTableRow[];
}

export interface EnrichResult {
  status?: string;
  trades_requested?: number;
  enriched?: number;
  skipped?: number;
  errors?: number;
}

export function fetchExcursionCoverage(): Promise<ExcursionCoverage> {
  return request<ExcursionCoverage>('/excursions/coverage');
}

export function enrichExcursions(scope = 'missing', dryRun = false): Promise<EnrichResult> {
  return request<EnrichResult>('/excursions/enrich', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scope, dry_run: dryRun }),
  });
}

export function recalculateExcursions(): Promise<EnrichResult> {
  return request<EnrichResult>('/excursions/recalculate', { method: 'POST' });
}

export function fetchTradeExcursion(tradeId: number): Promise<TradeExcursion> {
  return request<TradeExcursion>(`/excursions/trades/${tradeId}`);
}

export function fetchExitAnalysis(filters: DashboardFiltersState): Promise<ExitAnalysisResponse> {
  const params = new URLSearchParams();
  const qp = filtersToQueryParams(filters);
  Object.entries(qp).forEach(([k, v]) => {
    if (k !== 'range' && v) params.set(k, v);
  });
  return request<ExitAnalysisResponse>(`/exit-analysis?${params}`);
}
