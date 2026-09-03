import { useEffect, useMemo, useState } from 'react';
import { api, Trade } from '../api/client';
import { formatMoney, parseMoney, pnlClass } from '../utils/money';
import { presetToDateRange } from '../utils/dates';

export interface DaySummary {
  date: string;
  trades: number;
  longs: number;
  shorts: number;
  winners: number;
  losers: number;
  netPnl: number;
  longPnl: number;
  shortPnl: number;
  bestSide: 'LONG' | 'SHORT' | 'TIE' | '—';
}

function nyDate(iso: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  return d.toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
}

export function summarizeByDay(trades: Trade[]): DaySummary[] {
  const map = new Map<string, DaySummary>();
  for (const t of trades) {
    const day = nyDate(t.exit_time_utc || t.entry_time_utc);
    if (!day) continue;
    let row = map.get(day);
    if (!row) {
      row = {
        date: day,
        trades: 0,
        longs: 0,
        shorts: 0,
        winners: 0,
        losers: 0,
        netPnl: 0,
        longPnl: 0,
        shortPnl: 0,
        bestSide: '—',
      };
      map.set(day, row);
    }
    const pnl = parseMoney(t.net_pnl);
    const pnlN = Number.isNaN(pnl) ? 0 : pnl;
    row.trades += 1;
    row.netPnl += pnlN;
    if (t.direction === 'LONG') {
      row.longs += 1;
      row.longPnl += pnlN;
    } else if (t.direction === 'SHORT') {
      row.shorts += 1;
      row.shortPnl += pnlN;
    }
    if (pnlN > 0) row.winners += 1;
    else if (pnlN < 0) row.losers += 1;
  }
  return [...map.values()]
    .map((r) => {
      let bestSide: DaySummary['bestSide'] = '—';
      if (r.longs && r.shorts) {
        if (r.longPnl > r.shortPnl) bestSide = 'LONG';
        else if (r.shortPnl > r.longPnl) bestSide = 'SHORT';
        else bestSide = 'TIE';
      } else if (r.longs) bestSide = 'LONG';
      else if (r.shorts) bestSide = 'SHORT';
      return { ...r, bestSide };
    })
    .sort((a, b) => b.date.localeCompare(a.date));
}

export function MonthlyDaySummary() {
  const [open, setOpen] = useState(true);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [loading, setLoading] = useState(true);
  const { start, end } = presetToDateRange('this_month');

  useEffect(() => {
    setLoading(true);
    const params: Record<string, string> = { page: '1', page_size: '500' };
    if (start) params.date_from = start;
    if (end) params.date_to = end;
    api
      .getTrades(params)
      .then((res) => setTrades(res.items))
      .finally(() => setLoading(false));
  }, [start, end]);

  const rows = useMemo(() => summarizeByDay(trades), [trades]);
  const monthLabel = new Date().toLocaleString('en-US', {
    month: 'long',
    year: 'numeric',
    timeZone: 'America/New_York',
  });

  return (
    <div className="collapsible">
      <button type="button" className="collapsible-header" onClick={() => setOpen((v) => !v)}>
        <span>This month by day — {monthLabel}</span>
        <span className="text-secondary">{open ? '▾' : '▸'}</span>
      </button>
      {open && (
        <div className="collapsible-body">
          {loading && <p className="text-secondary">Loading…</p>}
          {!loading && !rows.length && <p className="text-secondary">No closed trades this month.</p>}
          {!loading && rows.length > 0 && (
            <table>
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Trades</th>
                  <th>Long</th>
                  <th>Short</th>
                  <th>Winners</th>
                  <th>Losers</th>
                  <th>Net P&L</th>
                  <th>Best side</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.date}>
                    <td>{r.date}</td>
                    <td>{r.trades}</td>
                    <td>{r.longs}</td>
                    <td>{r.shorts}</td>
                    <td className="profit">{r.winners}</td>
                    <td className="loss">{r.losers}</td>
                    <td className={pnlClass(String(r.netPnl))}>{formatMoney(String(r.netPnl), true)}</td>
                    <td>{r.bestSide}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
