import { useEffect, useState } from 'react';
import { settingsApi } from '../api/workflow';

const INPUTS = ['ORDER_HISTORY', 'PINE_LOG', 'ACTIVITY_LOG', 'AUTO_STRATEGY_TESTER'] as const;
const POLICIES = ['REQUIRED', 'RECOMMENDED', 'OPTIONAL', 'DISABLED'];

const PATH_FIELDS: { key: string; label: string; trading?: boolean; hint?: string }[] = [
  {
    key: 'data_dir',
    label: 'Trading data directory',
    trading: true,
    hint: 'SQLite database, screenshots, inbox, and backups live under this folder unless overridden below. Restart after changing.',
  },
  { key: 'inbox', label: 'Inbox', hint: 'Drop CSVs / Pine logs here for automation' },
  { key: 'archive', label: 'Archive' },
  { key: 'screenshots', label: 'Screenshots' },
  { key: 'backups', label: 'Backups' },
  { key: 'logs', label: 'Logs' },
  { key: 'quarantine', label: 'Quarantine' },
];

export function SettingsPage() {
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [prefs, setPrefs] = useState<Record<string, unknown>>({});
  const [paths, setPaths] = useState<Record<string, string>>({});
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    settingsApi.get().then((d) => {
      setData(d);
      setPrefs((d.preferences as Record<string, unknown>) || {});
      const p = (d.paths || {}) as Record<string, string>;
      const next: Record<string, string> = {};
      for (const f of PATH_FIELDS) {
        next[f.key] = String(p[f.key] || '');
      }
      setPaths(next);
    });
  }, []);

  if (!data) return <p>Loading…</p>;
  const expected = (prefs.expected_inputs || {}) as Record<string, string>;
  const database = String((data.paths as Record<string, string>)?.database || '');

  const save = async () => {
    const res = await settingsApi.patch({
      auto_process_inbox: prefs.auto_process_inbox,
      eod_finalize_enabled: prefs.eod_finalize_enabled,
      eod_finalize_time: prefs.eod_finalize_time,
      automatic_backup: prefs.automatic_backup,
      backup_retain_daily: Number(prefs.backup_retain_daily),
      backup_retain_weekly: Number(prefs.backup_retain_weekly),
      notifications: prefs.notifications,
      expected_inputs: expected,
      paths,
    });
    setPrefs((res.preferences as Record<string, unknown>) || prefs);
    const p = (res.paths || {}) as Record<string, string>;
    const next: Record<string, string> = {};
    for (const f of PATH_FIELDS) {
      next[f.key] = String(p[f.key] || paths[f.key] || '');
    }
    setPaths(next);
    setData({ ...data, paths: res.paths });
    if (res.restart_required) {
      setMsg(String(res.note || 'Restart the app to use the new trading data directory.'));
    } else {
      setMsg('Saved. Secrets remain environment-only.');
    }
  };

  return (
    <div>
      <h2>Settings</h2>
      <p className="text-secondary">{String(data.secrets_note)}</p>

      <h3 className="section-title">Data locations</h3>
      <p className="text-secondary">
        Paste full folder paths. Leave a subfolder blank and it stays under the trading data directory.
      </p>
      {PATH_FIELDS.map((f) => (
        <div key={f.key} className={`path-field${f.trading ? ' trading-data' : ''}`}>
          <label htmlFor={`path-${f.key}`}>{f.label}</label>
          <input
            id={`path-${f.key}`}
            value={paths[f.key] || ''}
            onChange={(e) => setPaths({ ...paths, [f.key]: e.target.value })}
            placeholder={f.trading ? 'e.g. D:\\Trading\\DT_Analyser' : 'Optional override'}
          />
          {f.trading && database && (
            <div className="hint">
              Database file: <code>{database}</code>
            </div>
          )}
          {f.hint && <div className="hint">{f.hint}</div>}
        </div>
      ))}

      <h3 className="section-title">Automation</h3>
      <label>
        <input
          type="checkbox"
          checked={Boolean(prefs.auto_process_inbox)}
          onChange={(e) => setPrefs({ ...prefs, auto_process_inbox: e.target.checked })}
        />{' '}
        Auto Process Inbox
      </label>
      <br />
      <label>
        <input
          type="checkbox"
          checked={Boolean(prefs.eod_finalize_enabled)}
          onChange={(e) => setPrefs({ ...prefs, eod_finalize_enabled: e.target.checked })}
        />{' '}
        EOD Finalize
      </label>
      <label style={{ marginLeft: '1rem' }}>
        Time (NY)
        <input
          value={String(prefs.eod_finalize_time || '20:15')}
          onChange={(e) => setPrefs({ ...prefs, eod_finalize_time: e.target.value })}
        />
      </label>
      <br />
      <label>
        <input
          type="checkbox"
          checked={Boolean(prefs.automatic_backup)}
          onChange={(e) => setPrefs({ ...prefs, automatic_backup: e.target.checked })}
        />{' '}
        Automatic backup
      </label>
      <p>
        Keep{' '}
        <input
          type="number"
          value={Number(prefs.backup_retain_daily || 30)}
          onChange={(e) => setPrefs({ ...prefs, backup_retain_daily: Number(e.target.value) })}
          style={{ width: 70 }}
        />{' '}
        daily and{' '}
        <input
          type="number"
          value={Number(prefs.backup_retain_weekly || 12)}
          onChange={(e) => setPrefs({ ...prefs, backup_retain_weekly: Number(e.target.value) })}
          style={{ width: 70 }}
        />{' '}
        weekly backups. Rotation never deletes the live database.
      </p>
      <h3 className="section-title">Expected daily inputs</h3>
      <table>
        <tbody>
          {INPUTS.map((key) => (
            <tr key={key}>
              <td>{key.replace(/_/g, ' ')}</td>
              <td>
                <select
                  value={expected[key] || 'OPTIONAL'}
                  onChange={(e) =>
                    setPrefs({
                      ...prefs,
                      expected_inputs: { ...expected, [key]: e.target.value },
                    })
                  }
                >
                  {POLICIES.map((p) => (
                    <option key={p}>{p}</option>
                  ))}
                </select>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-secondary">
        Activity Log is optional after Order History. AUTO can be disabled when that experiment ends.
      </p>
      <button type="button" className="primary" onClick={save}>
        Save settings
      </button>
      {msg && <p>{msg}</p>}
    </div>
  );
}
