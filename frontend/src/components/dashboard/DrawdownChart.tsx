import { useState } from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, ReferenceLine } from 'recharts';
import { formatMoney, formatPercent, formatR, parseMoney } from '../../utils/money';
import type { DashboardData } from '../../types/dashboard';

export function DrawdownChart({
  series,
  pctAvailable,
  rSeries,
}: {
  series: DashboardData['drawdown_series'];
  pctAvailable: boolean;
  rSeries?: { date: string; cumulative_r: string }[];
}) {
  const [mode, setMode] = useState<'$' | '%' | 'R'>('$');

  if (!series.length && !rSeries?.length) return <div className="empty-state">No drawdown data</div>;

  const useR = mode === 'R' && rSeries && rSeries.length > 0;
  const chartData = useR
    ? rSeries!.map((d, i) => {
        const cum = parseMoney(d.cumulative_r) ?? 0;
        return { label: (d.date || '').slice(5), dd: cum, peak: '', equity: '', trades: i };
      })
    : series.map((d) => ({
        label: (d.date || '').slice(5),
        dd: mode === '%' && d.drawdown_pct ? parseMoney(d.drawdown_pct) : parseMoney(d.drawdown_dollars),
        peak: d.peak,
        equity: d.equity,
        trades: d.trades_since_peak,
      }));

  return (
    <div>
      <div className="filters-bar" style={{ marginBottom: '0.5rem' }}>
        <button type="button" className={mode === '$' ? 'active-toggle' : ''} onClick={() => setMode('$')}>$</button>
        <button type="button" className={mode === '%' ? 'active-toggle' : ''} disabled={!pctAvailable} onClick={() => setMode('%')}>%</button>
        <button type="button" className={mode === 'R' ? 'active-toggle' : ''} disabled={!rSeries?.length} onClick={() => setMode('R')}>R</button>
      </div>
      {!pctAvailable && mode !== 'R' && (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
          Percentage drawdown requires starting equity. Label: Calendar Days Underwater (not trading sessions).
        </p>
      )}
      <div className="chart-container">
        <ResponsiveContainer width="100%" height={220}>
          <AreaChart data={chartData}>
            <CartesianGrid stroke="#2a3441" strokeDasharray="3 3" />
            <ReferenceLine y={0} stroke="#8b9bb4" />
            <XAxis dataKey="label" stroke="#8b9bb4" tick={{ fontSize: 11 }} />
            <YAxis
              stroke="#8b9bb4"
              tick={{ fontSize: 11 }}
              tickFormatter={(v) => (mode === '%' ? `${v}%` : mode === 'R' ? `${v}R` : `$${v}`)}
            />
            <Tooltip
              contentStyle={{ background: '#1e2530', border: '1px solid #2a3441' }}
              formatter={(value: number) => [
                mode === '%' ? formatPercent(String(value)) : mode === 'R' ? formatR(String(value)) : formatMoney(String(value), true),
                mode === 'R' ? 'Cumulative R' : 'Drawdown',
              ]}
            />
            <Area type="monotone" dataKey="dd" stroke="#e5534b" fill="#e5534b33" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
