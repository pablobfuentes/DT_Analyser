import { useState } from 'react';
import { Link } from 'react-router-dom';
import { api, Trade } from '../api/client';
import { formatMoney, formatR } from '../utils/money';

export function MissingRiskModal({
  trades,
  onClose,
  onSaved,
}: {
  trades: Trade[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const missing = trades.filter((t) => !t.r_multiple && t.status === 'CLOSED');
  const [edits, setEdits] = useState<Record<number, { stop: string; amount: string }>>({});
  const [error, setError] = useState<string | null>(null);

  if (!missing.length) return null;

  const save = async (t: Trade) => {
    setError(null);
    const e = edits[t.id] || { stop: '', amount: '' };
    if (!e.stop && !e.amount) {
      setError('Enter stop or risk amount.');
      return;
    }
    try {
      await api.updateTradeRisk(t.id, {
        initial_stop_price: e.stop || null,
        initial_risk_amount: e.amount || null,
        risk_source: 'MANUAL',
      });
      onSaved();
    } catch (err: unknown) {
      const detail = (err as { detail?: string })?.detail;
      setError(typeof detail === 'string' ? detail : 'Save failed');
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="card modal-panel">
        <h3>Missing Risk ({missing.length})</h3>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
          Enter initial stop and/or risk amount. Open trade detail for full notes.
        </p>
        {error && <p style={{ color: 'var(--loss)' }}>{error}</p>}
        <table>
          <thead>
            <tr>
              <th>Trade</th>
              <th>P&L</th>
              <th>Stop</th>
              <th>Risk $</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {missing.slice(0, 25).map((t) => (
              <tr key={t.id}>
                <td>
                  <Link to={`/trades/${t.id}`}>{t.ticker}</Link>
                </td>
                <td>{formatMoney(t.net_pnl || t.gross_pnl, true)}</td>
                <td>
                  <input
                    style={{ width: 80 }}
                    value={edits[t.id]?.stop ?? ''}
                    onChange={(ev) =>
                      setEdits({ ...edits, [t.id]: { ...edits[t.id], stop: ev.target.value, amount: edits[t.id]?.amount ?? '' } })
                    }
                  />
                </td>
                <td>
                  <input
                    style={{ width: 80 }}
                    value={edits[t.id]?.amount ?? ''}
                    onChange={(ev) =>
                      setEdits({ ...edits, [t.id]: { stop: edits[t.id]?.stop ?? '', amount: ev.target.value } })
                    }
                  />
                </td>
                <td>
                  <button type="button" onClick={() => save(t)}>Save</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {missing.length > 25 && <p>Showing first 25. Use filters to narrow.</p>}
        <button type="button" onClick={onClose} style={{ marginTop: '1rem' }}>
          Close
        </button>
      </div>
    </div>
  );
}
