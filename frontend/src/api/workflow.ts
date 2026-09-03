const API = '/api';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, options);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw err;
  }
  return res.json();
}

export const workflowApi = {
  status: (date?: string) => request<Record<string, unknown>>(`/workflow/status${date ? `?date=${date}` : ''}`),
  health: () => request<Record<string, unknown>>('/workflow/health'),
  processInbox: () => request<Record<string, unknown>>('/workflow/process-inbox', { method: 'POST' }),
  finalize: (date?: string) =>
    request<Record<string, unknown>>(`/workflow/finalize${date ? `?date=${date}` : ''}`, { method: 'POST' }),
  noTrade: (date: string, no_trading: boolean) =>
    request<Record<string, unknown>>('/workflow/no-trade-day', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ date, no_trading }),
    }),
  runs: () => request<{ items: Record<string, unknown>[] }>('/workflow/runs'),
  run: (id: number) => request<Record<string, unknown>>(`/workflow/runs/${id}`),
  attention: (date?: string) =>
    request<{ items: Record<string, unknown>[] }>(`/workflow/attention${date ? `?date=${date}` : ''}`),
};

export const journalApi = {
  trade: (id: number) => request<Record<string, unknown>>(`/journal/trades/${id}`),
  saveTrade: (id: number, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/journal/trades/${id}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  search: (q: string) => request<{ items: Record<string, unknown>[] }>(`/journal/search?q=${encodeURIComponent(q)}`),
  tags: () => request<{ items: { id: number; name: string }[] }>('/journal/tags'),
  tradeStatus: (ids: number[]) =>
    request<Record<string, boolean>>(`/journal/trade-status?ids=${ids.join(',')}`),
  upload: async (file: File, tradeId: number, caption?: string) => {
    const form = new FormData();
    form.append('file', file);
    form.append('trade_id', String(tradeId));
    if (caption) form.append('caption', caption);
    return request<Record<string, unknown>>('/journal/attachments', { method: 'POST', body: form });
  },
  caption: (id: number, caption: string) =>
    request<Record<string, unknown>>(`/journal/attachments/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caption }),
    }),
  remove: (id: number) => request<Record<string, unknown>>(`/journal/attachments/${id}`, { method: 'DELETE' }),
};

export const reviewsApi = {
  daily: (d: string) => request<Record<string, unknown>>(`/reviews/daily/${d}`),
  patchDaily: (d: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/reviews/daily/${d}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  completeDaily: (d: string) =>
    request<Record<string, unknown>>(`/reviews/daily/${d}/complete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }),
  weekly: (w: string) => request<Record<string, unknown>>(`/reviews/weekly/${w}`),
  patchWeekly: (w: string, body: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/reviews/weekly/${w}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  completeWeekly: (w: string) =>
    request<Record<string, unknown>>(`/reviews/weekly/${w}/complete`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' }),
  history: () => request<{ daily: Record<string, unknown>[]; weekly: Record<string, unknown>[] }>('/reviews/history'),
};

export const backupsApi = {
  list: () => request<{ items: Record<string, unknown>[] }>('/backups'),
  create: () => request<Record<string, unknown>>('/backups', { method: 'POST' }),
  preview: (id: string) => request<Record<string, unknown>>(`/backups/${id}/restore-preview`, { method: 'POST' }),
};

export const settingsApi = {
  get: () => request<Record<string, unknown>>('/settings'),
  patch: (body: Record<string, unknown>) =>
    request<Record<string, unknown>>('/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
};
