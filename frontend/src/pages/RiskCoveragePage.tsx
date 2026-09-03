import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api/client';

export function RiskCoveragePage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    api.riskCoverage().then(setData);
  }, []);

  if (!data) return <p>Loading…</p>;

  const reasons = (data.reasons as Record<string, number>) || {};
  const mix = (data.risk_source_mix as Record<string, number>) || {};
  const missingIds = (data.missing_trade_ids as number[]) || [];

  return (
    <div>
      <h2>Risk Coverage</h2>
      <div className="grid-secondary">
        <div className="metric-card"><div>Closed trades</div><strong>{String(data.closed_trades)}</strong></div>
        <div className="metric-card"><div>R-qualified</div><strong>{String(data.r_qualified)}</strong></div>
        <div className="metric-card"><div>R Coverage</div><strong>{data.r_coverage_pct != null ? `${parseFloat(String(data.r_coverage_pct)).toFixed(0)}%` : '—'}</strong></div>
      </div>
      <h3>Missing-R reasons</h3>
      <p className="text-secondary">NO_SIGNAL_AVAILABLE is context ({String(data.no_signal_available_context)}), not a substitute for MISSING_STOP.</p>
      <ul>
        {Object.entries(reasons).map(([k, n]) => (
          <li key={k}>{k}: {n}</li>
        ))}
      </ul>
      <h3>Risk source mix</h3>
      <ul>
        {Object.entries(mix).map(([k, n]) => (
          <li key={k}>{k}: {n}</li>
        ))}
      </ul>
      <h3>Missing-risk trades</h3>
      <p>
        {missingIds.slice(0, 30).map((id) => (
          <span key={id}><Link to={`/trades/${id}`}>#{id}</Link> </span>
        ))}
      </p>
      {missingIds.length > 0 && (
        <Link to="/trades?has_risk=no">Open missing-risk trades</Link>
      )}
    </div>
  );
}
