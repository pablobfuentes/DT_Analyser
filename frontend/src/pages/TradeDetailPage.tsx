import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api, TradeDetail } from '../api/client';
import { fetchTradeExcursion, type TradeExcursion } from '../api/excursions';
import { formatMoney, formatPercent, formatR } from '../utils/money';
import { formatDuration } from '../utils/duration';
import { TradeJournal } from '../components/TradeJournal';

export function TradeDetailPage() {
  const { id } = useParams();
  const [trade, setTrade] = useState<TradeDetail | null>(null);
  const [excursion, setExcursion] = useState<TradeExcursion | null>(null);
  const [excursionMissing, setExcursionMissing] = useState(false);
  const [stop, setStop] = useState('');
  const [riskAmount, setRiskAmount] = useState('');
  const [notes, setNotes] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const load = () => {
    if (!id) return;
    const tradeId = Number(id);
    api.getTrade(tradeId).then(setTrade);
    setExcursionMissing(false);
    fetchTradeExcursion(tradeId)
      .then(setExcursion)
      .catch(() => {
        setExcursion(null);
        setExcursionMissing(true);
      });
  };

  useEffect(() => {
    load();
  }, [id]);

  useEffect(() => {
    if (trade) {
      setStop(trade.initial_stop_price ?? '');
      setRiskAmount(trade.initial_risk_amount ?? '');
      setNotes(trade.risk_notes ?? '');
    }
  }, [trade]);

  if (!trade) return <p>Loading...</p>;

  let rawRows: unknown = null;
  try {
    rawRows = trade.raw_row_json ? JSON.parse(trade.raw_row_json) : null;
  } catch {
    rawRows = trade.raw_row_json;
  }

  const saveRisk = async () => {
    setMsg(null);
    setErr(null);
    try {
      const res = await api.updateTradeRisk(trade.id, {
        initial_stop_price: stop || null,
        initial_risk_amount: riskAmount || null,
        risk_source: 'MANUAL',
        risk_notes: notes || null,
      });
      if (res.warnings?.length) setMsg(res.warnings.join(' '));
      else setMsg('Risk saved.');
      load();
    } catch (e: unknown) {
      const detail = (e as { detail?: string })?.detail;
      setErr(typeof detail === 'string' ? detail : 'Failed to save risk.');
    }
  };

  return (
    <div>
      <Link to="/trades">← Back to Trades</Link>
      <h2>TRADE #{trade.id}</h2>

      <h3>Normalized Trade</h3>
      <table border={0}>
        <tbody>
          <tr><td>Ticker:</td><td>{trade.ticker}</td></tr>
          <tr><td>Direction:</td><td>{trade.direction}</td></tr>
          <tr><td>Entry:</td><td>{trade.entry_time_utc.slice(11, 19)} @ {trade.avg_entry_price} × {trade.quantity}</td></tr>
          <tr><td>Exit:</td><td>{trade.exit_time_utc ? `${trade.exit_time_utc.slice(11, 19)} @ ${trade.avg_exit_price}` : 'OPEN'}</td></tr>
          <tr><td>Net P&L:</td><td>{trade.net_pnl ?? trade.gross_pnl ?? 'N/A'}</td></tr>
          <tr><td>Source:</td><td>{trade.source_type}</td></tr>
          {trade.pnl_mismatch_flag && (
            <tr><td colSpan={2} style={{ color: 'orange' }}>⚠ P&L mismatch flagged</td></tr>
          )}
        </tbody>
      </table>

      <h3>PLANNED (Pine / signal)</h3>
      <table>
        <tbody>
          <tr><td>Planned entry</td><td>{trade.planned?.planned_entry_price ?? '—'}</td></tr>
          <tr><td>Planned stop</td><td>{trade.planned?.planned_stop_price ?? '—'}</td></tr>
          <tr><td>Suggested shares</td><td>{trade.planned?.suggested_shares ?? '—'}</td></tr>
          <tr><td>Planned risk</td><td>{trade.planned?.planned_risk_amount ?? '—'}</td></tr>
          <tr><td>Allowed risk (budget, not 1R)</td><td>{trade.planned?.allowed_risk ?? '—'}</td></tr>
        </tbody>
      </table>

      <h3>ACTUAL Risk / R</h3>
      <table border={0}>
        <tbody>
          <tr><td>Actual avg entry</td><td>{trade.avg_entry_price}</td></tr>
          <tr><td>Opening quantity</td><td>{trade.quantity}</td></tr>
          <tr><td>Initial Stop</td><td>{String(trade.actual_risk?.initial_stop_price ?? trade.initial_stop_price ?? '—')}</td></tr>
          <tr><td>Risk / Share</td><td>{String(trade.actual_risk?.actual_risk_per_share ?? trade.initial_risk_per_share ?? '—')}</td></tr>
          <tr><td>Actual initial risk</td><td>{formatMoney(String(trade.actual_risk?.actual_initial_risk_amount ?? trade.initial_risk_amount ?? ''))}</td></tr>
          <tr><td>R Multiple</td><td>{formatR(String(trade.actual_risk?.r_multiple ?? trade.r_multiple ?? ''))}</td></tr>
          <tr><td>Risk %</td><td>{trade.actual_risk?.risk_pct_equity_at_entry != null ? `${trade.actual_risk.risk_pct_equity_at_entry}%` : '—'}</td></tr>
          <tr><td>Risk Source</td><td>{String(trade.actual_risk?.risk_source ?? trade.risk_source ?? '—')}</td></tr>
          <tr><td>Stop Source</td><td>{String(trade.actual_risk?.stop_source ?? '—')}</td></tr>
          <tr><td>P&L basis</td><td>{String(trade.actual_risk?.r_pnl_basis ?? '—')}</td></tr>
          <tr><td>Quality</td><td>{String(trade.actual_risk?.risk_quality_status ?? '—')}</td></tr>
        </tbody>
      </table>
      {trade.signal_links && trade.signal_links.length > 0 && (
        <p>
          Linked signals:{' '}
          {trade.signal_links.map((l) => (
            <Link key={l.signal_pk} to={`/signals/${l.signal_pk}`}>{l.signal_id} ({l.link_status})</Link>
          ))}
        </p>
      )}

      {trade.status === 'CLOSED' && (
        <div className="card" style={{ marginTop: '1rem', maxWidth: 420 }}>
          <h4>Initial Risk</h4>
          <label>
            Initial Stop
            <input value={stop} onChange={(e) => setStop(e.target.value)} placeholder="e.g. 4.72" />
          </label>
          <label>
            Initial Risk Amount ($)
            <input value={riskAmount} onChange={(e) => setRiskAmount(e.target.value)} placeholder="optional override" />
          </label>
          <label>
            Notes
            <input value={notes} onChange={(e) => setNotes(e.target.value)} />
          </label>
          <button type="button" onClick={saveRisk} style={{ marginTop: '0.5rem' }}>Save Risk</button>
          {msg && <p style={{ color: 'var(--profit)' }}>{msg}</p>}
          {err && <p style={{ color: 'var(--loss)' }}>{err}</p>}
        </div>
      )}

      <h3>Excursion / Exit Quality</h3>
      {excursionMissing && trade.status === 'CLOSED' && (
        <p className="text-secondary">No excursion data — enrich via Market Data page.</p>
      )}
      {excursion && (
        <div className="card" style={{ marginTop: '0.5rem', maxWidth: 640 }}>
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
            {excursion.quality_status === 'ESTIMATED_1M' && (
              <span className="timing-badge timing-end_of_day">1m estimate</span>
            )}
            {excursion.data_resolution && (
              <span className="timing-badge timing-pre_entry">{excursion.data_resolution}</span>
            )}
            <span className="timing-badge">{excursion.quality_status}</span>
            {excursion.is_consolidated === false && (
              <span className="timing-badge timing-end_of_day">Partial feed</span>
            )}
          </div>

          <dl className="kv-list">
            <dt>Inclusive MFE R</dt>
            <dd>{formatR(excursion.mfe_r)}</dd>
            <dt>Conservative MFE R</dt>
            <dd>{formatR(excursion.conservative_mfe_r)}</dd>
            <dt>Boundary spread</dt>
            <dd>
              {formatR(excursion.mfe_boundary_spread_r)}
              {excursion.mfe_boundary_spread_amount && (
                <span className="text-secondary"> ({formatMoney(excursion.mfe_boundary_spread_amount)})</span>
              )}
            </dd>
            <dt>MAE R</dt>
            <dd>{formatR(excursion.mae_r)}</dd>
            <dt>Exit efficiency</dt>
            <dd>{formatPercent(excursion.exit_efficiency_pct)}</dd>
            <dt>R left on table</dt>
            <dd>{formatR(excursion.r_left_on_table)}</dd>
            <dt>Post-exit extension (5m / 15m / 30m)</dt>
            <dd>
              {formatR(excursion.post_exit_favorable_5m_r)} / {formatR(excursion.post_exit_favorable_15m_r)} /{' '}
              {formatR(excursion.post_exit_favorable_30m_r)}
            </dd>
            <dt>Time to MFE</dt>
            <dd>{formatDuration(excursion.time_to_mfe_seconds)}</dd>
            <dt>MFE → exit</dt>
            <dd>{formatDuration(excursion.mfe_to_exit_seconds)}</dd>
            <dt>Peak giveback</dt>
            <dd>
              {formatR(excursion.peak_giveback_r)} ({formatPercent(excursion.peak_giveback_pct)})
            </dd>
            <dt>Realized R</dt>
            <dd>{formatR(excursion.gross_realized_r)}</dd>
          </dl>

          {(excursion.conservative_mfe_r || excursion.conservative_mae_r) && (
            <>
              <h4 style={{ marginTop: '1rem' }}>Conservative Estimate</h4>
              <dl className="kv-list">
                <dt>Conservative MFE R</dt>
                <dd>{formatR(excursion.conservative_mfe_r)}</dd>
                <dt>Conservative MAE R</dt>
                <dd>{formatR(excursion.conservative_mae_r)}</dd>
                <dt>Conservative MFE $</dt>
                <dd>{formatMoney(excursion.conservative_position_mfe_amount)}</dd>
                <dt>Conservative MAE $</dt>
                <dd>{formatMoney(excursion.conservative_position_mae_amount)}</dd>
                {excursion.boundary_ambiguity && (
                  <>
                    <dt>Boundary ambiguity</dt>
                    <dd>Yes — extrema may differ within entry/exit bar</dd>
                  </>
                )}
              </dl>
            </>
          )}

          {excursion.quality_flags.length > 0 && (
            <p className="text-secondary" style={{ fontSize: '0.85rem', marginTop: '0.75rem' }}>
              Flags: {excursion.quality_flags.join(', ')}
            </p>
          )}
          {excursion.calculated_at && (
            <p className="text-secondary" style={{ fontSize: '0.85rem' }}>
              Calculated {excursion.calculated_at.slice(0, 19)} · v{excursion.calculation_version}
            </p>
          )}
        </div>
      )}

      <h3>Executions</h3>
      {trade.execution_links?.length ? (
        <ol>
          {trade.execution_links.map((link, i) => (
            <li key={`${link.execution.id}-${link.role}-${i}`}>
              <strong>{link.role}</strong> {link.allocated_quantity} of {link.execution.side}{' '}
              {link.execution.quantity} @ {link.execution.price} ({link.execution.execution_time_utc.slice(11, 19)})
            </li>
          ))}
        </ol>
      ) : trade.executions.length === 0 ? (
        <p>No linked executions (direct strategy tester import)</p>
      ) : (
        <ol>
          {trade.executions.map((e) => (
            <li key={e.id}>
              {e.side} {e.quantity} @ {e.price} ({e.execution_time_utc.slice(11, 19)})
            </li>
          ))}
        </ol>
      )}

      <TradeJournal tradeId={trade.id} />

      <h3>Import Batch</h3>
      {trade.import_batches.length === 0 ? (
        <p>N/A</p>
      ) : (
        <ul>
          {trade.import_batches.map((b) => (
            <li key={b.id}>Batch #{b.id}: {b.filename} (hash: {b.file_hash.slice(0, 12)}…)</li>
          ))}
        </ul>
      )}

      <h3>Raw Source Rows</h3>
      <pre style={{ background: '#1e2530', padding: '1rem', overflow: 'auto' }}>
        {JSON.stringify(rawRows, null, 2)}
      </pre>
    </div>
  );
}
