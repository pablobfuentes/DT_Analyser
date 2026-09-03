import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts';
import type { RDistributionBucket } from '../../types/dashboard';

export function RDistributionChart({ data }: { data: RDistributionBucket[] }) {
  const total = data.reduce((s, b) => s + b.count, 0);
  if (!total) return <div className="empty-state">No R-qualified trades for histogram</div>;

  const chartData = data.filter((b) => b.count > 0 || true).map((b) => ({
    label: b.label,
    count: b.count,
    pct: b.pct,
  }));

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={240}>
        <BarChart data={chartData} layout="vertical" margin={{ left: 100 }}>
          <CartesianGrid stroke="#2a3441" strokeDasharray="3 3" />
          <XAxis type="number" stroke="#8b9bb4" tick={{ fontSize: 11 }} />
          <YAxis type="category" dataKey="label" stroke="#8b9bb4" tick={{ fontSize: 10 }} width={95} />
          <Tooltip
            contentStyle={{ background: '#1e2530', border: '1px solid #2a3441' }}
            formatter={(value: number, _n, item) => {
              const pct = (item.payload as { pct: string | null }).pct;
              return [`${value} (${pct ?? '0'}%)`, 'Trades'];
            }}
          />
          <Bar dataKey="count" fill="#539bf5" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
