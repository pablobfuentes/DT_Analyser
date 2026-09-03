const API_BASE = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw err;
  }
  return res.json();
}

export interface Account {
  id: number;
  name: string;
  source: string;
  currency: string;
  is_simulated: boolean;
  starting_equity?: string | null;
}

export interface ImportPreview {
  filename: string;
  file_hash: string;
  detected_source_type?: string;
  parser?: string;
  confidence?: number;
  detected_columns: string[];
  row_count: number;
  timezone_status: string;
  sample_normalized_records: Record<string, string>[];
  warnings: string[];
  errors: Record<string, unknown>[];
  error?: string;
  message?: string;
  options?: string[];
}

export interface ImportResult {
  import_batch_id: number;
  raw_rows: number;
  valid_rows: number;
  imported_executions: number;
  imported_trades: number;
  duplicate_executions: number;
  duplicate_trades: number;
  errors: number;
}

export interface Trade {
  id: number;
  account_id: number;
  source_type: string;
  ticker: string;
  direction: string;
  entry_time_utc: string;
  exit_time_utc: string | null;
  avg_entry_price: string;
  avg_exit_price: string | null;
  quantity: string;
  gross_pnl: string | null;
  fees: string | null;
  net_pnl: string | null;
  holding_seconds: number | null;
  status: string;
  raw_row_json: string | null;
  pnl_mismatch_flag?: boolean;
  initial_stop_price?: string | null;
  initial_risk_per_share?: string | null;
  initial_risk_amount?: string | null;
  r_multiple?: string | null;
  risk_source?: string | null;
  risk_notes?: string | null;
}

export interface TradeExecutionLink {
  execution: Execution;
  role: string;
  allocated_quantity: string;
}

export interface TradeDetail extends Trade {
  executions: Execution[];
  execution_links: TradeExecutionLink[];
  import_batches: { id: number; filename: string; file_hash: string }[];
  planned?: Record<string, string | null> | null;
  actual_risk?: Record<string, unknown> | null;
  signal_links?: { signal_pk: number; signal_id: string; link_status: string; match_type: string; confidence: string }[];
}

export interface Execution {
  id: number;
  ticker: string;
  side: string;
  execution_time_utc: string;
  quantity: string;
  price: string;
  raw_row_json: string;
}

export interface PaginatedTrades {
  items: Trade[];
  total: number;
  page: number;
  page_size: number;
}

export const api = {
  health: () => request<{ status: string }>('/health'),
  getAccounts: () => request<Account[]>('/accounts'),
  createAccount: (data: Partial<Account>) =>
    request<Account>('/accounts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  updateAccount: (id: number, data: { name?: string; starting_equity?: string | null; currency?: string }) =>
    request<Account>(`/accounts/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  clearAllData: () =>
    request<{ status: string; deleted: Record<string, number> }>('/accounts/clear-data', {
      method: 'POST',
    }),
  previewImport: (file: File, parser?: string, timezone?: string) => {
    const form = new FormData();
    form.append('file', file);
    if (parser) form.append('parser_name', parser);
    if (timezone) form.append('timezone', timezone);
    return request<ImportPreview>('/imports/preview', { method: 'POST', body: form });
  },
  commitImport: (file: File, accountId: number, parserName: string, timezone?: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('account_id', String(accountId));
    form.append('parser_name', parserName);
    if (timezone) form.append('timezone', timezone);
    return request<ImportResult>('/imports/commit', { method: 'POST', body: form });
  },
  getTrades: (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString();
    return request<PaginatedTrades>(`/trades?${qs}`);
  },
  getTrade: (id: number) => request<TradeDetail>(`/trades/${id}`),
  updateTradeRisk: (
    id: number,
    data: {
      initial_stop_price?: string | null;
      initial_risk_amount?: string | null;
      risk_source?: string;
      risk_notes?: string | null;
    },
  ) =>
    request<{
      id: number;
      initial_stop_price: string | null;
      initial_risk_amount: string | null;
      r_multiple: string | null;
      warnings: string[];
    }>(`/trades/${id}/risk`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  previewPine: (text: string) =>
    request<Record<string, unknown>>('/signals/import/preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    }),
  commitPine: (text: string, source = 'PASTE') =>
    request<Record<string, unknown>>('/signals/import/commit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, source }),
    }),
  listSignals: (params: Record<string, string>) => {
    const qs = new URLSearchParams(params).toString();
    return request<{ items: Record<string, unknown>[]; total: number }>(`/signals?${qs}`);
  },
  getSignal: (id: number) => request<Record<string, unknown>>(`/signals/${id}`),
  linkSignal: (id: number, tradeId: number) =>
    request<Record<string, unknown>>(`/signals/${id}/link`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trade_id: tradeId }),
    }),
  unlinkSignal: (id: number, tradeId: number) =>
    request<Record<string, unknown>>(`/signals/${id}/unlink`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trade_id: tradeId }),
    }),
  rejectSignal: (id: number, tradeId: number) =>
    request<Record<string, unknown>>(`/signals/${id}/reject`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trade_id: tradeId }),
    }),
  signalCoverage: () => request<{ summary: Record<string, unknown>; by_date: { date: string; trades: number; signals: number; linked: number; coverage_pct: string | null }[] }>('/signals/coverage'),
  riskCoverage: () => request<Record<string, unknown>>('/risk/coverage'),
  getMarketDataStatus: () =>
    request<{
      configured: boolean;
      provider: string;
      feed: string | null;
      is_consolidated: boolean | null;
      benchmark: string;
      total_trades: number;
      instrument_enriched: number;
      market_enriched: number;
      coverage_pct: number;
    }>('/market-data/status'),
  enrichMarketData: (scope = 'missing') =>
    request<Record<string, unknown>>('/market-data/enrich', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope }),
    }),
  recalculateMarketFeatures: () =>
    request<Record<string, unknown>>('/market-data/recalculate', { method: 'POST' }),
  refreshMarketData: (scope = 'all') =>
    request<Record<string, unknown>>('/market-data/refresh', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope }),
    }),
  researchVariables: (mode = 'PRE_ENTRY_ONLY') =>
    request<{
      variables: Record<string, unknown>[];
      heatmap_dimensions: Record<string, unknown>[];
      heatmap_metrics: string[];
      multiple_comparison_warning: string;
    }>(`/research/variables?research_mode=${encodeURIComponent(mode)}`),
  researchCompare: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/compare', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  researchScatter: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/scatter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  researchHeatmap: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/heatmap', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  researchRolling: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/rolling', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  researchDistribution: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/distribution', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  researchMultifactor: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/multifactor', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  researchRobustness: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/robustness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  researchExport: (kind: string, body: Record<string, unknown>) =>
    fetch(`/api/research/export/${kind}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }).then((r) => r.text()),
  saveResearchCohort: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/saved-cohorts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  listResearchCohorts: () => request<{ items: Record<string, unknown>[] }>('/research/saved-cohorts'),
  saveResearchView: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/views', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  listResearchViews: () => request<{ items: Record<string, unknown>[] }>('/research/views'),
  getResearchView: (id: number) => request<Record<string, unknown>>(`/research/views/${id}`),
  createCandidateRule: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/candidate-rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  listCandidateRules: () => request<{ items: Record<string, unknown>[] }>('/research/candidate-rules'),
  evaluateCandidateRule: (id: number, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/research/candidate-rules/${id}/evaluate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  reviseCandidateRule: (id: number, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/research/candidate-rules/${id}/revise`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  starPattern: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/research/patterns', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
};
