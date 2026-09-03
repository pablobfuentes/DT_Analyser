import { useState } from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { formatMoney, formatR, parseMoney } from '../../utils/money';
import type { DashboardData } from '../../types/dashboard';

type Mode = 'pnl' | 'equity' | 'r';

export function CurveToggleChart({
  cumulative,
  equitySeries,
  rSeries,
  rQualified,
  rTotal,
}: {
  cumulative: DashboardData['cumulative'];
  equitySeries: DashboardData['equity_series'];
  rSeries: DashboardData['cumulative_r_series'];
  rQualified: number;
  rTotal: number;
}) {
  const [mode, setMode] = useState<Mode>('pnl');

  let chartData: { label: string; value: number }[] = [];
  let yFmt = (v: number) => `$${v}`;
  let tooltipNote = '';

  if (mode === 'pnl') {
    chartData = cumulative.map((d) => ({ label: d.date.slice(5), value: parseMoney(d.cumulative_pnl) }));
    tooltipNote = 'Cumulative realized P&L';
  } else if (mode === 'equity') {
    if (!equitySeries.some((e) => e.equity)) {
      tooltipNote = 'Starting equity required';
    } else {
      chartData = equitySeries.map((d) => ({ label: (d.date || '').slice(5), value: parseMoney(d.equity) }));
      tooltipNote = 'Realized equity (period baseline + P&L)';
    }
  } else {
    chartData = rSeries.map((d) => ({ label: (d.date || '').slice(5), value: parseMoney(d.cumulative_r) }));
    yFmt = (v) => `${v.toFixed(2)}R`;
    tooltipNote = `${rQualified} of ${rTotal} trades contain risk data`;
  }

  return (
    <div>
      <div className="filters-bar" style={{ marginBottom: '0.5rem' }}>
        {(['pnl', 'equity', 'r'] as Mode[]).map((m) => (
          <button key={m} className={mode === m ? 'active-toggle' : ''} onClick={() => setMode(m)}>
            {m === 'pnl' ? 'P&L' : m === 'equity' ? 'Equity' : 'R'}
          </button>
        ))}
      </div>
      {mode === 'equity' && !equitySeries.some((e) => e.equity) ? (
        <div className="empty-state">Percentage drawdown and equity curve require starting equity on all selected accounts.</div>
      ) : !chartData.length ? (
        <div className="empty-state">No data for chart</div>
      ) : (
        <>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>{tooltipNote}</p>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={chartData}>
                <CartesianGrid stroke="#2a3441" strokeDasharray="3 3" />
                <XAxis dataKey="label" stroke="#8b9bb4" tick={{ fontSize: 11 }} />
                <YAxis stroke="#8b9bb4" tick={{ fontSize: 11 }} tickFormatter={yFmt} />
                <Tooltip
                  contentStyle={{ background: '#1e2530', border: '1px solid #2a3441' }}
                  formatter={(value: number) => [mode === 'r' ? formatR(String(value)) : formatMoney(String(value), true), '']}
                />
                <Line type="monotone" dataKey="value" stroke="#539bf5" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </div>
  );
}
