import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import { formatMoney, parseMoney } from '../../utils/money';

interface Point {
  date: string;
  daily_pnl: string;
  cumulative_pnl: string;
  trades: number;
}

export function CumulativePnlChart({ data }: { data: Point[] }) {
  if (!data.length) return <div className="empty-state">No data for chart</div>;

  const chartData = data.map((d) => ({
    date: d.date.slice(5),
    cumulative: parseMoney(d.cumulative_pnl),
    daily: parseMoney(d.daily_pnl),
    trades: d.trades,
  }));

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData}>
          <CartesianGrid stroke="#2a3441" strokeDasharray="3 3" />
          <XAxis dataKey="date" stroke="#8b9bb4" tick={{ fontSize: 11 }} />
          <YAxis stroke="#8b9bb4" tick={{ fontSize: 11 }} tickFormatter={(v) => `$${v}`} />
          <Tooltip
            contentStyle={{ background: '#1e2530', border: '1px solid #2a3441' }}
            formatter={(value: number, name: string) => [formatMoney(String(value), true), name === 'cumulative' ? 'Cumulative' : 'Daily']}
            labelFormatter={(l) => `Date: ${l}`}
          />
          <Line type="monotone" dataKey="cumulative" stroke="#539bf5" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
