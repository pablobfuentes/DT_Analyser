import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Cell } from 'recharts';
import { formatMoney, parseMoney } from '../../utils/money';

interface Point {
  date: string;
  net_pnl: string;
  trades: number;
  wins: number;
  losses: number;
}

export function DailyPnlChart({ data }: { data: Point[] }) {
  if (!data.length) return <div className="empty-state">No data for chart</div>;

  const chartData = [...data].reverse().map((d) => ({
    date: d.date.slice(5),
    pnl: parseMoney(d.net_pnl),
    trades: d.trades,
    wins: d.wins,
    losses: d.losses,
  }));

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={chartData}>
          <CartesianGrid stroke="#2a3441" strokeDasharray="3 3" />
          <XAxis dataKey="date" stroke="#8b9bb4" tick={{ fontSize: 11 }} />
          <YAxis stroke="#8b9bb4" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
          <Tooltip
            contentStyle={{ background: '#1e2530', border: '1px solid #2a3441' }}
            formatter={(value: number) => [formatMoney(String(value), true), 'Daily P&L']}
          />
          <Bar dataKey="pnl">
            {chartData.map((entry, i) => (
              <Cell key={i} fill={entry.pnl >= 0 ? '#3dd68c' : '#f07178'} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
