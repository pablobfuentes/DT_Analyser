import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api } from '../api/client';

export function SignalsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [data, setData] = useState<{ items: Record<string, unknown>[]; total: number } | null>(null);

  const ticker = searchParams.get('ticker') || '';
  const strategy = searchParams.get('strategy') || '';
  const version = searchParams.get('version') || '';
  const origin = searchParams.get('origin') || '';
  const direction = searchParams.get('direction') || '';
  const state = searchParams.get('state') || '';
  const linkStatus = searchParams.get('link_status') || '';
  const dateFrom = searchParams.get('date_from') || '';
  const dateTo = searchParams.get('date_to') || '';
  const page = Math.max(1, parseInt(searchParams.get('page') || '1', 10) || 1);
  const pageSize = 50;

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  useEffect(() => {
    const params: Record<string, string> = { page: String(page), page_size: String(pageSize) };
    if (ticker) params.ticker = ticker;
    if (strategy) params.strategy = strategy;
    if (version) params.version = version;
    if (origin) params.origin = origin;
    if (direction) params.direction = direction;
    if (state) params.state = state;
    if (linkStatus) params.link_status = linkStatus;
    if (dateFrom) params.date_from = dateFrom;
    if (dateTo) params.date_to = dateTo;
    api.listSignals(params).then(setData);
  }, [ticker, strategy, version, origin, direction, state, linkStatus, dateFrom, dateTo, page]);

  return (
    <div>
      <h2>Signals</h2>
      <p className="text-secondary">Untraded and incomplete Pine signals stay here. They are not deleted when unlinked.</p>
      <div className="filters-bar">
        <label>Ticker <input value={ticker} onChange={(e) => setFilter('ticker', e.target.value)} /></label>
        <label>Strategy <input value={strategy} onChange={(e) => setFilter('strategy', e.target.value)} /></label>
        <label>Version <input value={version} onChange={(e) => setFilter('version', e.target.value)} /></label>
        <label>
          Origin
          <select value={origin} onChange={(e) => setFilter('origin', e.target.value)}>
            <option value="">All</option>
            <option value="REALTIME">REALTIME</option>
            <option value="HISTORICAL_REPLAY">HISTORICAL_REPLAY</option>
            <option value="BACKTEST">BACKTEST</option>
            <option value="UNKNOWN">UNKNOWN</option>
          </select>
        </label>
        <label>
          Direction
          <select value={direction} onChange={(e) => setFilter('direction', e.target.value)}>
            <option value="">All</option>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
          </select>
        </label>
        <label>
          State
          <select value={state} onChange={(e) => setFilter('state', e.target.value)}>
            <option value="">All</option>
            <option value="ARMED">ARMED</option>
            <option value="ENTRY">ENTRY</option>
            <option value="INCOMPLETE">INCOMPLETE</option>
            <option value="EXIT">EXIT</option>
          </select>
        </label>
        <label>
          Link
          <select value={linkStatus} onChange={(e) => setFilter('link_status', e.target.value)}>
            <option value="">All</option>
            <option value="UNLINKED">UNLINKED</option>
            <option value="SUGGESTED">SUGGESTED</option>
            <option value="CONFIRMED">CONFIRMED</option>
            <option value="AMBIGUOUS">AMBIGUOUS</option>
          </select>
        </label>
        <label>From <input type="date" value={dateFrom} onChange={(e) => setFilter('date_from', e.target.value)} /></label>
        <label>To <input type="date" value={dateTo} onChange={(e) => setFilter('date_to', e.target.value)} /></label>
      </div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Signal ID</th>
              <th>Ticker</th>
              <th>Strategy</th>
              <th>Version</th>
              <th>Origin</th>
              <th>Dir</th>
              <th>State</th>
              <th>Link</th>
            </tr>
          </thead>
          <tbody>
            {(data?.items || []).map((s) => (
              <tr key={String(s.id)}>
                <td><Link to={`/signals/${s.id}`}>{String(s.signal_id)}</Link></td>
                <td>{String(s.ticker)}</td>
                <td>{String(s.strategy_key)}</td>
                <td>{String(s.strategy_version_normalized || s.strategy_version)}</td>
                <td>{String(s.signal_origin)}</td>
                <td>{String(s.direction)}</td>
                <td>{String(s.state)}</td>
                <td>{String(s.match_status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="text-secondary">
          {data?.total ?? 0} signals
          {(data?.total ?? 0) > pageSize && (
            <>
              {' '}
              <button type="button" disabled={page <= 1} onClick={() => setFilter('page', String(page - 1))}>
                Prev
              </button>{' '}
              page {page}{' '}
              <button
                type="button"
                disabled={page * pageSize >= (data?.total ?? 0)}
                onClick={() => setFilter('page', String(page + 1))}
              >
                Next
              </button>
            </>
          )}
        </p>
      </div>
      <SignalCoverageByDate />
    </div>
  );
}

function SignalCoverageByDate() {
  const [rows, setRows] = useState<{ date: string; trades: number; signals: number; linked: number; coverage_pct: string | null }[]>([]);
  useEffect(() => {
    api.signalCoverage().then((r) => setRows(r.by_date || []));
  }, []);
  if (!rows.length) return null;
  return (
    <div className="card" style={{ marginTop: '1rem' }}>
      <h3>Signal Coverage by NY Date</h3>
      <table>
        <thead>
          <tr><th>Date</th><th>Trades</th><th>Signals</th><th>Linked</th><th>Coverage</th></tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.date}>
              <td>{r.date}</td>
              <td>{r.trades}</td>
              <td>{r.signals}</td>
              <td>{r.linked}</td>
              <td>{r.coverage_pct != null ? `${parseFloat(r.coverage_pct).toFixed(0)}%` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
