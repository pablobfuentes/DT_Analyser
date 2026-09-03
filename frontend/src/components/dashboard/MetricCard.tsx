interface MetricCardProps {
  label: string;
  value: string;
  sub?: string;
  valueClass?: string;
}

export function MetricCard({ label, value, sub, valueClass = '' }: MetricCardProps) {
  return (
    <div className="metric-card">
      <div className="metric-label">{label}</div>
      <div className={`metric-value ${valueClass}`}>{value}</div>
      {sub && <div className="metric-sub">{sub}</div>}
    </div>
  );
}
