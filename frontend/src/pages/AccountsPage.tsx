import { useEffect, useState } from 'react';
import { api, Account } from '../api/client';

export function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [editing, setEditing] = useState<Record<number, string>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    api.getAccounts().then((accts) => {
      setAccounts(accts);
      const init: Record<number, string> = {};
      accts.forEach((a) => {
        init[a.id] = a.starting_equity != null ? String(a.starting_equity) : '';
      });
      setEditing(init);
    });
  }, []);

  const save = async (id: number) => {
    const raw = editing[id]?.trim();
    const starting_equity = raw === '' ? null : raw;
    if (starting_equity !== null && (isNaN(Number(starting_equity)) || Number(starting_equity) < 0)) {
      setMessage('Invalid starting equity');
      return;
    }
    try {
      await api.updateAccount(id, { starting_equity: starting_equity });
      setMessage('Saved');
      const accts = await api.getAccounts();
      setAccounts(accts);
    } catch {
      setMessage('Failed to save');
    }
  };

  const clearAllData = async () => {
    if (
      !window.confirm(
        'Delete ALL trades, executions, and import history? Accounts and settings will be kept. This cannot be undone.',
      )
    ) {
      return;
    }
    setClearing(true);
    setMessage(null);
    try {
      const res = await api.clearAllData();
      setMessage(
        `Cleared: ${res.deleted.trades} trades, ${res.deleted.executions} executions, ${res.deleted.import_batches} import batches.`,
      );
    } catch {
      setMessage('Failed to clear data');
    } finally {
      setClearing(false);
    }
  };

  return (
    <div>
      <h2 style={{ marginTop: 0 }}>Accounts</h2>
      <p style={{ color: 'var(--text-secondary)' }}>
        Configure starting equity for realized return calculations. No default is applied.
      </p>
      {message && <div className="warning-banner">{message}</div>}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Name</th>
              <th>Source</th>
              <th>Currency</th>
              <th>Starting Equity</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {accounts.map((a) => (
              <tr key={a.id}>
                <td>{a.name}</td>
                <td>{a.source.replace('TRADINGVIEW_', '')}</td>
                <td>{a.currency}</td>
                <td>
                  <input
                    type="text"
                    value={editing[a.id] ?? ''}
                    placeholder="Not set"
                    onChange={(e) => setEditing({ ...editing, [a.id]: e.target.value })}
                    style={{ width: '120px' }}
                  />
                </td>
                <td>
                  <button onClick={() => save(a.id)}>Save</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h3 style={{ marginTop: 0, fontSize: '0.95rem' }}>Data management</h3>
        <p style={{ color: 'var(--text-secondary)', margin: '0 0 0.75rem' }}>
          Remove all imported trades and executions. Account names and starting equity are preserved.
        </p>
        <button type="button" className="btn-danger" onClick={clearAllData} disabled={clearing}>
          {clearing ? 'Clearing…' : 'Clear All Data'}
        </button>
      </div>
    </div>
  );
}
