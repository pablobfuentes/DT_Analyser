export function parseMoney(value: string | null | undefined): number {
  if (value == null || value === '') return NaN;
  return parseFloat(value);
}

export function formatMoney(value: string | null | undefined, showSign = false): string {
  const n = parseMoney(value);
  if (Number.isNaN(n)) return '—';
  const abs = Math.abs(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  if (n > 0) return showSign ? `+$${abs}` : `$${abs}`;
  if (n < 0) return `-$${abs}`;
  return '$0.00';
}

export function formatPercent(value: string | null | undefined): string {
  const n = parseMoney(value);
  if (Number.isNaN(n)) return '—';
  return `${n.toFixed(1)}%`;
}

export function pnlClass(value: string | null | undefined): string {
  const n = parseMoney(value);
  if (Number.isNaN(n) || n === 0) return 'neutral';
  return n > 0 ? 'profit' : 'loss';
}

export function formatR(value: string | null | undefined): string {
  if (value == null || value === '') return '—';
  const n = parseFloat(value);
  if (Number.isNaN(n)) return '—';
  const sign = n > 0 ? '+' : '';
  return `${sign}${n.toFixed(2)}R`;
}

export function formatProfitFactor(value: string | null | undefined, status?: string): string {
  if (status === 'NO_LOSSES') return '∞';
  if (value == null || value === '') return '—';
  const n = parseFloat(value);
  if (Number.isNaN(n)) return '—';
  return n.toFixed(2);
}

export function formatCoverage(tradeCount: number, missing: number): string {
  const total = tradeCount + missing;
  if (total === 0) return '—';
  const pct = ((tradeCount / total) * 100).toFixed(1);
  return `${tradeCount} / ${total} (${pct}%)`;
}
