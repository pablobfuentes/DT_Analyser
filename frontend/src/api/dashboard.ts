import type { DashboardData } from '../types/dashboard';
import type { DashboardFiltersState } from '../types/dashboard';
import { filtersToQueryParams } from '../utils/dates';

const API_BASE = '/api';

export async function fetchDashboard(filters: DashboardFiltersState): Promise<DashboardData> {
  const params = new URLSearchParams();
  const qp = filtersToQueryParams(filters);
  Object.entries(qp).forEach(([k, v]) => {
    if (k !== 'range' && v) params.set(k, v);
  });
  const res = await fetch(`${API_BASE}/dashboard?${params}`);
  if (!res.ok) throw new Error('Unable to load dashboard');
  return res.json();
}
