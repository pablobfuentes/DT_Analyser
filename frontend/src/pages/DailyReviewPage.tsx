import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { reviewsApi } from '../api/workflow';
import { formatMoney, formatR, pnlClass } from '../utils/money';

function todayNYGuess() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
}

export function DailyReviewPage() {
  const [params, setParams] = useSearchParams();
  const date = params.get('date') || todayNYGuess();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [prompts, setPrompts] = useState<Record<string, string>>({});
  const [body, setBody] = useState('');

  const load = () => {
    reviewsApi.daily(date).then((d) => {
      setData(d);
      setPrompts((d.prompt_fields as Record<string, string>) || {});
      setBody(String(d.body || ''));
    });
  };

  useEffect(() => {
    load();
  }, [date]);

  if (!data) return <p>Loading…</p>;
  const live = (data.live_metrics || {}) as Record<string, unknown>;
  const summary = (live.summary || {}) as Record<string, unknown>;
  const trades = (data.trades || []) as Record<string, unknown>[];
  const labels = (data.prompt_labels || []) as string[];

  return (
    <div>
      <h2>Daily Review — {date}</h2>
      <div className="filters-bar">
        <label>
          Date
          <input
            type="date"
            value={date}
            onChange={(e) => {
              const next = new URLSearchParams(params);
              next.set('date', e.target.value);
              setParams(next, { replace: true });
            }}
          />
        </label>
        <span>Status: {String(data.status)}</span>
        <Link to={`/workflow?date=${date}`}>Workflow</Link>
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
          <div className="metric-label">Win rate</div>
          <div className="metric-value">{String(summary.win_rate ?? '—')}</div>
        </div>
      </div>
      <p className="text-secondary">
        Strategy {String(live.strategy_coverage_pct ?? '—')}% · R {String(live.r_coverage_pct ?? '—')}% · Excursions{' '}
        {String(live.excursion_coverage_pct ?? '—')}% · Loss beyond R: {String(live.loss_beyond_initial_risk_count ?? 0)}
      </p>

      <table>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Dir</th>
            <th>P&amp;L</th>
            <th>R</th>
            <th>MFE R</th>
            <th>MAE R</th>
            <th>Eff</th>
            <th>Setup</th>
            <th>Journal</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={String(t.id)}>
              <td>
                <Link to={`/trades/${t.id}`}>{String(t.ticker)}</Link>
              </td>
              <td>{String(t.direction)}</td>
              <td className={pnlClass(String(t.net_pnl || ''))}>{formatMoney(String(t.net_pnl || ''), true)}</td>
              <td>{formatR(String(t.r_multiple || ''))}</td>
              <td>{formatR(String(t.mfe_r || ''))}</td>
              <td>{formatR(String(t.mae_r || ''))}</td>
              <td>{t.exit_efficiency_pct != null ? `${t.exit_efficiency_pct}%` : '—'}</td>
              <td>{String(t.setup_quality || '—')}</td>
              <td>{t.journal_status === 'reviewed' ? '✓' : '○'}</td>
            </tr>
          ))}
        </tbody>
      </table>

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
      <label style={{ display: 'block', marginBottom: '0.75rem' }}>
        Notes
        <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={3} style={{ width: '100%' }} />
      </label>
      <button
        type="button"
        onClick={() => reviewsApi.patchDaily(date, { body, prompt_fields: prompts }).then(() => load())}
      >
        Save
      </button>{' '}
      <button type="button" className="primary" onClick={() => reviewsApi.completeDaily(date).then(() => load())}>
        Complete Review
      </button>
      {data.metrics_snapshot ? <p className="text-secondary">Snapshot stored at completion. Live numbers above may change later.</p> : null}
    </div>
  );
}
