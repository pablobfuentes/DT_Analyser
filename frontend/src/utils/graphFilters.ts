import type { DashboardFiltersState } from '../types/dashboard';
import { EXPLORATION_KEYS, type ExplorationKey } from '../types/reports';
import { filtersToQueryParams } from './dates';

export interface GraphFiltersState {
  global: DashboardFiltersState;
  exploration: Record<string, string>;
  minSample: number;
  includePartialFeed?: boolean;
  pineScope: string;
  includeSuggestedSignals?: boolean;
}

export function defaultGraphFilters(): GraphFiltersState {
  return {
    global: { range: 'all', startDate: '', endDate: '', accountId: '', source: 'ALL', direction: 'ALL', ticker: '' },
    exploration: {},
    minSample: 1,
    includePartialFeed: false,
    pineScope: 'REALTIME',
    includeSuggestedSignals: false,
  };
}

export function parseGraphFiltersFromUrl(search: URLSearchParams): GraphFiltersState {
  const exploration: Record<string, string> = {};
  for (const key of EXPLORATION_KEYS) {
    const v = search.get(key);
    if (v) exploration[key] = v;
  }
  const minSample = parseInt(search.get('min_sample') || '1', 10);
  const includePartial = ['1', 'true', 'yes'].includes((search.get('include_partial_feed') || '').toLowerCase());
  return {
    global: {
      range: (search.get('range') as DashboardFiltersState['range']) || 'all',
      startDate: search.get('start_date') || '',
      endDate: search.get('end_date') || '',
      accountId: search.get('account_id') || '',
      source: search.get('source') || search.get('source_type') || 'ALL',
      direction: search.get('direction') || 'ALL',
      ticker: search.get('ticker') || '',
    },
    exploration,
    minSample: Number.isFinite(minSample) ? minSample : 1,
    includePartialFeed: includePartial,
    pineScope: (search.get('pine_scope') || 'REALTIME').toUpperCase(),
    includeSuggestedSignals: ['1', 'true', 'yes'].includes((search.get('include_suggested_signals') || '').toLowerCase()),
  };
}

export function graphFiltersToQueryParams(state: GraphFiltersState): Record<string, string> {
  const params = filtersToQueryParams(state.global);
  Object.entries(state.exploration).forEach(([k, v]) => {
    if (v) params[k] = v;
  });
  if (state.minSample > 1) params.min_sample = String(state.minSample);
  if (state.includePartialFeed) params.include_partial_feed = 'true';
  params.pine_scope = state.pineScope || 'REALTIME';
  if (state.includeSuggestedSignals) params.include_suggested_signals = 'true';
  return params;
}

export function toggleExplorationFilter(
  exploration: Record<string, string>,
  dimension: string,
  bucketKey: string,
): Record<string, string> {
  const next = { ...exploration };
  if (next[dimension] === bucketKey) {
    delete next[dimension];
  } else {
    next[dimension] = bucketKey;
  }
  return next;
}

export function removeExplorationFilter(
  exploration: Record<string, string>,
  dimension: string,
): Record<string, string> {
  const next = { ...exploration };
  delete next[dimension];
  return next;
}

export function resetExploration(exploration: Record<string, string>): Record<string, string> {
  void exploration;
  return {};
}

export function explorationToTradesParams(exploration: Record<string, string>): Record<string, string> {
  const params: Record<string, string> = {};
  const map: Record<string, (v: string) => Record<string, string>> = {
    weekday: (v) => ({ weekday: v }),
    entry_15m: (v) => {
      const [start, end] = v.split('-');
      return { entry_time_start: start, entry_time_end: end };
    },
    entry_30m: (v) => {
      const [start, end] = v.split('-');
      return { entry_time_start: start, entry_time_end: end };
    },
    symbol: (v) => ({ ticker: v }),
    direction_bucket: (v) => ({ direction: v }),
    source_bucket: (v) => ({ source_type: v === 'MANUAL' ? 'TRADINGVIEW_MANUAL' : 'TRADINGVIEW_AUTO' }),
  };
  for (const [k, v] of Object.entries(exploration)) {
    if (map[k]) Object.assign(params, map[k](v));
    else params[k] = v;
  }
  return params;
}

export function isExplorationKey(key: string): key is ExplorationKey {
  return (EXPLORATION_KEYS as readonly string[]).includes(key);
}
