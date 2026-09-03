import type { DashboardFiltersState, DateRangePreset } from '../types/dashboard';

export function presetToDateRange(preset: DateRangePreset): { start: string; end: string } {
  const now = new Date();
  const ny = new Date(now.toLocaleString('en-US', { timeZone: 'America/New_York' }));
  const fmt = (d: Date) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}-${m}-${day}`;
  };

  const startOfWeek = (d: Date) => {
    const copy = new Date(d);
    const day = copy.getDay();
    copy.setDate(copy.getDate() - day);
    return copy;
  };

  const startOfMonth = (d: Date) => new Date(d.getFullYear(), d.getMonth(), 1);

  switch (preset) {
    case 'today':
      return { start: fmt(ny), end: fmt(ny) };
    case 'yesterday': {
      const y = new Date(ny);
      y.setDate(y.getDate() - 1);
      return { start: fmt(y), end: fmt(y) };
    }
    case 'this_week':
      return { start: fmt(startOfWeek(ny)), end: fmt(ny) };
    case 'last_7': {
      const s = new Date(ny);
      s.setDate(s.getDate() - 6);
      return { start: fmt(s), end: fmt(ny) };
    }
    case 'this_month':
      return { start: fmt(startOfMonth(ny)), end: fmt(ny) };
    case 'last_30': {
      const s = new Date(ny);
      s.setDate(s.getDate() - 29);
      return { start: fmt(s), end: fmt(ny) };
    }
    case 'all':
      return { start: '', end: '' };
    case 'custom':
    default:
      return { start: '', end: '' };
  }
}

export function filtersToQueryParams(f: DashboardFiltersState): Record<string, string> {
  const params: Record<string, string> = { range: f.range };
  if (f.range === 'custom') {
    if (f.startDate) params.start_date = f.startDate;
    if (f.endDate) params.end_date = f.endDate;
  } else if (f.range !== 'all') {
    const { start, end } = presetToDateRange(f.range);
    if (start) params.start_date = start;
    if (end) params.end_date = end;
  }
  if (f.accountId) params.account_id = f.accountId;
  if (f.source && f.source !== 'ALL') params.source_type = f.source;
  if (f.direction && f.direction !== 'ALL') params.direction = f.direction;
  if (f.ticker.trim()) params.ticker = f.ticker.trim();
  return params;
}

export function parseFiltersFromUrl(search: URLSearchParams): DashboardFiltersState {
  const range = (search.get('range') as DateRangePreset) || 'this_month';
  return {
    range,
    startDate: search.get('start_date') || '',
    endDate: search.get('end_date') || '',
    accountId: search.get('account_id') || '',
    source: search.get('source') || 'ALL',
    direction: search.get('direction') || 'ALL',
    ticker: search.get('ticker') || '',
  };
}

export function defaultFilters(): DashboardFiltersState {
  const { start, end } = presetToDateRange('this_month');
  return {
    range: 'this_month',
    startDate: start,
    endDate: end,
    accountId: '',
    source: 'ALL',
    direction: 'ALL',
    ticker: '',
  };
}
