import type { GraphFiltersState } from '../utils/graphFilters';
import { graphFiltersToQueryParams } from '../utils/graphFilters';
import type { ReportsResponse } from '../types/reports';

import { API_BASE } from './base';

export async function fetchReports(filters: GraphFiltersState): Promise<ReportsResponse> {
  const params = new URLSearchParams();
  const qp = graphFiltersToQueryParams(filters);
  Object.entries(qp).forEach(([k, v]) => {
    if (k !== 'range' && v) params.set(k, v);
  });
  const res = await fetch(`${API_BASE}/reports?${params}`);
  if (!res.ok) throw new Error('Unable to load reports');
  return res.json();
}
