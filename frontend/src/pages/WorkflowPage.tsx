import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { backupsApi, workflowApi } from '../api/workflow';

function todayNYGuess() {
  return new Date().toLocaleDateString('en-CA', { timeZone: 'America/New_York' });
}

export function WorkflowPage() {
  const [params, setParams] = useSearchParams();
  const date = params.get('date') || todayNYGuess();
  const [status, setStatus] = useState<Record<string, unknown> | null>(null);
  const [health, setHealth] = useState<Record<string, unknown> | null>(null);
  const [runs, setRuns] = useState<Record<string, unknown>[]>([]);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [backups, setBackups] = useState<Record<string, unknown>[]>([]);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    workflowApi.status(date).then(setStatus);
    workflowApi.health().then(setHealth);
    workflowApi.runs().then((r) => setRuns(r.items || []));
    backupsApi.list().then((r) => setBackups(r.items || []));
  };

  useEffect(() => {
    load();
  }, [date]);

  const setDate = (v: string) => {
    const next = new URLSearchParams(params);
    next.set('date', v);
    setParams(next, { replace: true });
  };

  const act = async (fn: () => Promise<unknown>, label: string) => {
    setMsg(null);
    try {
      await fn();
      setMsg(label);
      load();
    } catch (e) {
      setMsg(JSON.stringify(e));
    }
  };

  const inputs = (status?.inputs || {}) as Record<string, { state?: string; policy?: string }>;
  const coverage = (status?.coverage || {}) as Record<string, unknown>;
  const attention = (status?.attention || []) as { message?: string }[];
  const lastBackup = status?.last_backup as Record<string, unknown> | null;

  return (
    <div>
      <h2>TODAY — {date}</h2>
      <div className="filters-bar">
        <label>
          NY date
          <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        </label>
        <button type="button" className="primary" onClick={() => act(() => workflowApi.processInbox(), 'Inbox queued')}>
          Process Inbox
        </button>
        <button type="button" onClick={() => act(() => workflowApi.finalize(date), 'Finalize queued')}>
          Finalize Today
        </button>
        <button type="button" onClick={() => act(() => backupsApi.create(), 'Backup queued')}>
          Create Backup
        </button>
        <button
          type="button"
          onClick={() => act(() => workflowApi.noTrade(date, !status?.no_trading), 'No-trade updated')}
        >
          {status?.no_trading ? 'Clear No Trading' : 'No Trading Today'}
        </button>
        <Link to={`/review/daily?date=${date}`}>Daily Review</Link>
        <Link to="/settings">Settings</Link>
      </div>
      {msg && <p className="warning-banner">{msg}</p>}

      <div className="grid-summary">
        <div className="metric-card">
          <div className="metric-label">Status</div>
          <div className="metric-value">{String(status?.badge || '…')}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Trades</div>
          <div className="metric-value">{String(status?.trades ?? '—')}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Review</div>
          <div className="metric-value">{String(status?.review_status || '—')}</div>
        </div>
        <div className="metric-card">
          <div className="metric-label">Worker</div>
          <div className="metric-value">{String(health?.worker || '—')}</div>
        </div>
      </div>

      <h3 className="section-title">Expected inputs</h3>
      <table>
        <thead>
          <tr>
            <th>Input</th>
            <th>Policy</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(inputs).map(([k, v]) => (
            <tr key={k}>
              <td>{k.replace(/_/g, ' ')}</td>
              <td>{v.policy}</td>
              <td>{v.state}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <h3 className="section-title">Coverage</h3>
      <p>
        Market {String(coverage.market_pct ?? '—')}% · Risk {String(coverage.risk_pct ?? '—')}% · Signals{' '}
        {String(coverage.signal_pct ?? '—')}% · Excursions {String(coverage.excursion_pct ?? '—')}%
      </p>
      <p className="text-secondary">
        Last backup: {lastBackup ? `${String(lastBackup.created_at || '')} — ${String(lastBackup.status)}` : 'none'}
      </p>

      <h3 className="section-title">Needs attention</h3>
      {attention.length === 0 ? (
        <p className="text-secondary">Nothing requiring a decision.</p>
      ) : (
        <ul>
          {attention.map((a, i) => (
            <li key={i}>{a.message}</li>
          ))}
        </ul>
      )}

      <h3 className="section-title">Automation health</h3>
      <p>
        Automation Ownership:{' '}
        {health?.automation_ownership === 'OWNER'
          ? 'OWNER'
          : `STANDBY / ${String(health?.automation_ownership_detail || 'OWNED BY ANOTHER PROCESS')}`}
      </p>
      <p>
        Watcher {String(health?.watcher)} · Worker {String(health?.worker)} · Pending jobs{' '}
        {String(health?.pending_jobs)} · Failed jobs {String(health?.failed_jobs)}
      </p>
      <p className="text-secondary">{String(health?.scheduler_note || '')}</p>
      <p className="text-secondary">Inbox: {String(health?.inbox || '')}</p>

      <h3 className="section-title">Recent runs</h3>
      <table>
        <thead>
          <tr>
            <th>When</th>
            <th>Type</th>
            <th>Status</th>
            <th>Date</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={String(r.id)}>
              <td>
                <button type="button" onClick={() => workflowApi.run(Number(r.id)).then(setDetail)}>
                  {String(r.created_at || '').slice(0, 19)}
                </button>
              </td>
              <td>{String(r.run_type)}</td>
              <td>{String(r.status)}</td>
              <td>{String(r.ny_date || '')}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {detail && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3>Run #{String(detail.id)}</h3>
          <p>
            {String(detail.run_type)} — {String(detail.status)}
          </p>
          <table>
            <thead>
              <tr>
                <th>Step</th>
                <th>Status</th>
                <th>Created</th>
                <th>Errors</th>
              </tr>
            </thead>
            <tbody>
              {((detail.steps || []) as Record<string, unknown>[]).map((s) => (
                <tr key={String(s.step_key)}>
                  <td>{String(s.step_key)}</td>
                  <td>{String(s.status)}</td>
                  <td>{String(s.records_created)}</td>
                  <td>{String(s.error_message || s.error_count || '')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="section-title">Backups</h3>
      <ul>
        {backups.slice(0, 8).map((b) => (
          <li key={String(b.id)}>
            {String(b.created_at)} — {String(b.status)} — {String(b.path)}
          </li>
        ))}
      </ul>
    </div>
  );
}
