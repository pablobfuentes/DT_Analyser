import { Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';
import { formatMoney, parseMoney } from '../../utils/money';

interface EquityPoint {
  date: string;
  equity?: string;
}

interface Props {
  equitySeries: EquityPoint[];
  startingEquity: string | null | undefined;
}

/** Last equity reading per calendar day, then last 30 days. */
function dailyPortfolio(series: EquityPoint[]): { date: string; value: number }[] {
  const byDate = new Map<string, number>();
  for (const p of series) {
    if (!p.date || p.equity == null || p.equity === '') continue;
    const n = parseMoney(p.equity);
    if (Number.isNaN(n)) continue;
    byDate.set(p.date, n);
  }
  return [...byDate.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(-30)
    .map(([date, value]) => ({ date: date.slice(5), value }));
}

export function PortfolioValueChart({ equitySeries, startingEquity }: Props) {
  const start = parseMoney(startingEquity);
  const hasStart = !Number.isNaN(start) && start > 0;
  const rows = dailyPortfolio(equitySeries);

  if (!rows.length) {
    return (
      <div className="empty-state">
        {hasStart ? 'No portfolio history for this range.' : 'Set starting equity on Accounts to show portfolio value.'}
      </div>
    );
  }

  const chartData = rows.map((r) => ({
    date: r.date,
    value: r.value,
    above: hasStart ? (r.value >= start ? r.value : null) : r.value,
    below: hasStart ? (r.value < start ? r.value : null) : null,
  }));

  for (let i = 0; i < chartData.length; i++) {
    const cur = chartData[i];
    if (!hasStart) continue;
    if (cur.above != null && cur.below == null) {
      const prev = chartData[i - 1];
      const next = chartData[i + 1];
      if (prev?.below != null || next?.below != null) {
        cur.below = start;
      }
    }
    if (cur.below != null && cur.above == null) {
      const prev = chartData[i - 1];
      const next = chartData[i + 1];
      if (prev?.above != null || next?.above != null) {
        cur.above = start;
      }
    }
  }

  const values = rows.map((r) => r.value);
  if (hasStart) values.push(start);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = Math.max((max - min) * 0.08, Math.abs(max) * 0.01, 1);

  const grid = getComputedStyle(document.documentElement).getPropertyValue('--border').trim() || '#2a3441';
  const muted = getComputedStyle(document.documentElement).getPropertyValue('--text-secondary').trim() || '#8b9bb4';
  const card = getComputedStyle(document.documentElement).getPropertyValue('--bg-card').trim() || '#1e2530';
  const profit = getComputedStyle(document.documentElement).getPropertyValue('--profit').trim() || '#3dd68c';
  const loss = getComputedStyle(document.documentElement).getPropertyValue('--loss').trim() || '#f07178';

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData}>
          <CartesianGrid stroke={grid} strokeDasharray="3 3" />
          <XAxis dataKey="date" stroke={muted} tick={{ fontSize: 11 }} />
          <YAxis
            stroke={muted}
            tick={{ fontSize: 11 }}
            domain={[min - pad, max + pad]}
            tickFormatter={(v) => `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
            width={72}
          />
          <Tooltip
            contentStyle={{ background: card, border: `1px solid ${grid}`, color: 'var(--text-primary)' }}
            formatter={(value: number) => [formatMoney(String(value)), 'Portfolio']}
            labelFormatter={(l) => `Date: ${l}`}
          />
          {hasStart && (
            <ReferenceLine
              y={start}
              stroke={muted}
              strokeDasharray="4 4"
              label={{ value: 'Start', fill: muted, fontSize: 11, position: 'insideTopRight' }}
            />
          )}
          <Line
            type="monotone"
            dataKey="above"
            stroke={profit}
            strokeWidth={2.5}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="below"
            stroke={loss}
            strokeWidth={2.5}
            dot={false}
            connectNulls={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
