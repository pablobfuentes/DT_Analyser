import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { reviewsApi } from '../api/workflow';
import { formatMoney, formatR, pnlClass } from '../utils/money';

function mondayNY() {
  const raw = new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
  const d = new Date(raw + 'T12:00:00');
  const day = d.getDay();
  const diff = day === 0 ? -6 : 1 - day;
  d.setDate(d.getDate() + diff);
  return d.toISOString().slice(0, 10);
}

export function WeeklyReviewPage() {
  const [params, setParams] = useSearchParams();
  const week = params.get('week') || mondayNY();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [body, setBody] = useState('');

  useEffect(() => {
    reviewsApi.weekly(week).then((d) => {
      setData(d);
      setPrompts((d.prompt_fields as Record<string, string>) || {});
      setBody(String(d.body || ''));
    });
  }, [week]);

  if (!data) return <p>Loading…</p>;
  const live = (data.live_metrics || {}) as Record<string, unknown>;
  const summary = (live.summary || {}) as Record<string, unknown>;
  const patterns = (data.patterns || []) as { dimension: string; caption: string; buckets: { label: string; trades: number; net_pnl: string; research_href: string }[] }[];
  const labels = (data.prompt_labels || []) as string[];

  return (
    <div>
      <h2>
        Weekly Review — {String(data.week_start)} → {String(data.week_end)}
      </h2>
      <div className="filters-bar">
        <label>
          Week start
          <input
            type="date"
            value={week}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              next.set('week', e.target.value);
              setParams(next, { replace: true });
            }}
          />
        </label>
        <span>Status: {String(data.status)}</span>
        <Link to="/reviews">History</Link>
      </div>
      <div className="grid-summary">
        <div className="metric-card">
          <div className="metric-label">Trades</div>
          <div className="metric-value">{String(summary.trades ?? 0)}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">P&amp;L</div>
          <div className={`metric-value ${pnlClass(String(summary.net_pnl || ''))}`}>{formatMoney(String(summary.net_pnl || '0'), true)}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Avg R</div>
          <div className="metric-value">{formatR(String(live.average_r || ''))}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Median R</div>
          <div className="metric-value">{formatR(String(live.median_r || ''))}</div>
        </div>
      </div>
      <p className="text-secondary">
        PF {String(live.profit_factor ?? '—')} · Best day {String(live.best_day || '—')} · Worst day {String(live.worst_day || '—')} · Max DD{' '}
        {formatMoney(String(live.max_drawdown || ''))}
      </p>

      {patterns.map((p) => (
        <div key={p.dimension} className="card" style={{ marginBottom: '1rem' }}>
          <h3>{p.dimension.replace(/_/g, ' ')}</h3>
          <p className="text-secondary">{p.caption}</p>
          <ul>
            {p.buckets.map((b) => (
              <li key={b.label}>
                {b.label}: {b.trades} trades, {formatMoney(b.net_pnl, true)}{' '}
                <Link to={b.research_href}>Open in Research Lab</Link>
              </li>
            ))}
          </ul>
        </div>
      ))}

      <h3 className="section-title">Reflection</h3>
      {labels.map((label) => (
        <label key={label} style={{ display: 'block', marginBottom: '0.75rem' }}>
          {label}
          <textarea
            value={prompts[label] || ''}
            onChange={(e) => setPrompts({ ...prompts, [label]: e.target.value })}
            rows={2}
            style={{ width: '100%' }}
          />
        </label>
      ))}
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} style={{ width: '100%' }} />
      <div style={{ marginTop: '0.5rem' }}>
        <button type="button" onClick={() => reviewsApi.patchWeekly(week, { body, prompt_fields: prompts }).then(() => reviewsApi.weekly(week).then(setData))}>
          Save
        </button>{' '}
        <button type="button" className="primary" onClick={() => reviewsApi.completeWeekly(week).then(setData)}>
          Complete Review
        </button>
      </div>
    </div>
  );
}
