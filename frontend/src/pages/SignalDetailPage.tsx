import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';

export function SignalDetailPage() {
  const { id } = useParams();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const load = () => {
    if (!id) return;
    api.getSignal(Number(id)).then(setData);
  };

  useEffect(() => {
    load();
  }, [id]);

  if (!data) return <p>Loading…</p>;

  const events = (data.events as Record<string, unknown>[]) || [];
  const links = (data.links as Record<string, unknown>[]) || [];
  const candidates = (data.candidates as Record<string, unknown>[]) || [];
  const snap = (data.strategy_snapshot as Record<string, unknown>) || {};

  const act = async (kind: 'link' | 'unlink' | 'reject', tradeId: number) => {
    setMsg(null);
    try {
      if (kind === 'link') await api.linkSignal(Number(id), tradeId);
      if (kind === 'unlink') await api.unlinkSignal(Number(id), tradeId);
      if (kind === 'reject') await api.rejectSignal(Number(id), tradeId);
      load();
    } catch (e: unknown) {
      setMsg(JSON.stringify(e));
    }
  };

  return (
    <div>
      <Link to="/signals">← Signals</Link>
      <h2>{String(data.signal_id)}</h2>
      <p>
        {String(data.strategy_key)} · {String(data.strategy_version)} · {String(data.signal_origin)} · {String(data.state)} ·{' '}
        {String(data.match_status)}
      </p>
      {msg && <pre className="warning-banner">{msg}</pre>}

      <h3>Strategy Snapshot</h3>
      <table>
        <tbody>
          {Object.entries(snap).map(([k, v]) => (
            <tr key={k}><td>{k}</td><td>{v == null ? '—' : String(v)}</td></tr>
          ))}
        </tbody>
      </table>

      <h3>Events</h3>
      {events.map((e) => (
        <div key={String(e.id)} className="card" style={{ marginBottom: '0.75rem' }}>
          <strong>{String(e.event_type)}</strong> {String(e.event_time_utc)} · {String(e.event_origin)}
          <pre style={{ overflow: 'auto' }}>{String(e.raw_line || e.raw_payload_json)}</pre>
        </div>
      ))}

      <h3>Links</h3>
      <ul>
        {links.map((l) => (
          <li key={String(l.id)}>
            Trade <Link to={`/trades/${l.trade_id}`}>#{String(l.trade_id)}</Link> {String(l.link_status)} {String(l.match_type)}{' '}
            {l.link_status !== 'REJECTED' && (
              <>
                <button type="button" onClick={() => act('unlink', Number(l.trade_id))}>Unlink</button>
                {l.link_status !== 'CONFIRMED' && (
                  <button type="button" onClick={() => act('link', Number(l.trade_id))}>Confirm</button>
                )}
              </>
            )}
          </li>
        ))}
      </ul>

      <h3>Candidate Trades</h3>
      <ul>
        {candidates.map((c) => (
          <li key={String(c.trade_id)}>
            <Link to={`/trades/${c.trade_id}`}>#{String(c.trade_id)}</Link> {String(c.ticker)} {String(c.direction)} {String(c.source_type)} Δ{String(c.time_delta_seconds)}s{' '}
            <button type="button" onClick={() => act('link', Number(c.trade_id))}>Confirm</button>
            <button type="button" onClick={() => act('reject', Number(c.trade_id))}>Reject</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
