import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { api, Account, ImportPreview, ImportResult } from '../api/client';
import { CsvDropzone } from '../components/CsvDropzone';
import { ImportPreviewPanel } from '../components/ImportPreview';

const TZ_OPTIONS = ['America/New_York', 'America/Mexico_City', 'UTC'];

function formatImportError(e: unknown): string {
  if (e && typeof e === 'object' && 'detail' in e) {
    const detail = (e as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (detail && typeof detail === 'object') {
      const d = detail as { message?: string; error?: string; options?: string[] };
      if (d.message) {
        const opts = d.options?.length ? ` Select timezone: ${d.options.join(', ')}.` : '';
        return `${d.message}${opts}`;
      }
    }
  }
  return JSON.stringify(e);
}

export function ImportPage() {
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<ImportPreview | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [accountId, setAccountId] = useState<number>(0);
  const [timezone, setTimezone] = useState('America/New_York');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.getAccounts().then((accts) => {
      setAccounts(accts);
      if (accts.length) setAccountId(accts[0].id);
    });
  }, []);

  const handleFile = async (f: File) => {
    setFile(f);
    setResult(null);
    setError(null);
    setLoading(true);
    try {
      const p = await api.previewImport(f, undefined, timezone);
      setPreview(p);
    } catch (e: unknown) {
      setError(formatImportError(e));
    } finally {
      setLoading(false);
    }
  };

  const handleImport = async () => {
    if (!file || !preview?.parser) return;
    setLoading(true);
    setError(null);
    try {
      // Always pass timezone: preview may show OK because preview used it, but commit re-parses the file.
      const res = await api.commitImport(file, accountId, preview.parser, timezone);
      setResult(res);
    } catch (e: unknown) {
      setError(formatImportError(e));
    } finally {
      setLoading(false);
    }
  };

  if (result) {
    return (
      <div>
        <h2>Import Result</h2>
        <p>Import successful (batch #{result.import_batch_id})</p>
        <ul>
          <li>Raw rows: {result.raw_rows}</li>
          <li>New executions: {result.imported_executions}</li>
          <li>New trades: {result.imported_trades}</li>
          <li>Duplicates skipped: {result.duplicate_executions + result.duplicate_trades}</li>
          <li>Errors: {result.errors}</li>
        </ul>
        <button onClick={() => navigate('/trades')}>View Trades</button>
        <button onClick={() => { setResult(null); setPreview(null); setFile(null); }}>
          Import Another
        </button>
      </div>
    );
  }

  return (
    <div>
      <h2>Import CSV</h2>
      <p style={{ color: 'var(--text-secondary)', fontSize: '0.9rem', maxWidth: '52rem' }}>
        Primary source is TradingView <strong>Order History</strong>. Activity Log is optional
        after Order History is imported — fills share Order IDs and are skipped as duplicates.
        Activity Log is an alternative fill source (and side context from “Call to place market
        order” lines) when Order History is not available. Strategy Tester List of Trades imports
        as AUTO round-trips, not reconstructed executions.
      </p>
      <label>
        Account:{' '}
        <select value={accountId} onChange={(e) => setAccountId(Number(e.target.value))}>
          {accounts.map((a) => (
            <option key={a.id} value={a.id}>
              {a.name}
            </option>
          ))}
        </select>
      </label>
      <label style={{ display: 'block', marginBottom: '0.75rem' }}>
        Timestamp timezone (for CSVs without offset):{' '}
        <select value={timezone} onChange={(e) => setTimezone(e.target.value)}>
          {TZ_OPTIONS.map((tz) => (
            <option key={tz} value={tz}>
              {tz}
            </option>
          ))}
        </select>
      </label>
      <CsvDropzone onFile={handleFile} disabled={loading} />
      {loading && !preview && <p>Analyzing...</p>}
      {error && <pre style={{ color: 'red' }}>{error}</pre>}
      {preview && (
        <ImportPreviewPanel
          preview={preview}
          timezone={timezone}
          onTimezoneChange={setTimezone}
          onImport={handleImport}
          loading={loading}
        />
      )}
      <PineSignalImport />
    </div>
  );
}

function PineSignalImport() {
  const [text, setText] = useState('');
  const [preview, setPreview] = useState<Record<string, unknown> | null>(null);
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const runPreview = async () => {
    setErr(null);
    setLoading(true);
    try {
      setPreview(await api.previewPine(text));
    } catch (e) {
      setErr(JSON.stringify(e));
    } finally {
      setLoading(false);
    }
  };

  const runCommit = async () => {
    setErr(null);
    setLoading(true);
    try {
      setResult(await api.commitPine(text));
    } catch (e) {
      setErr(JSON.stringify(e));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card" style={{ marginTop: '2rem' }}>
      <h3>Strategy Signals (Pine Logs)</h3>
      <p className="text-secondary">Paste PINE_SIGNAL_EVENT lines. Preview does not write signals, events, links, or trades.</p>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        style={{ width: '100%', fontFamily: 'monospace' }}
        placeholder="PINE_SIGNAL_EVENT	1.0	FIRST_PULLBACK|NCRA|1|…"
      />
      <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
        <button type="button" onClick={runPreview} disabled={loading || !text.trim()}>Preview</button>
        <button type="button" onClick={runCommit} disabled={loading || !text.trim()}>Import Signals</button>
      </div>
      {err && <pre className="warning-banner">{err}</pre>}
      {preview && <pre>{JSON.stringify(preview, null, 2)}</pre>}
      {result && (
        <p>
          Batch #{String(result.import_batch_id)} {String(result.status)} — imported {String(result.imported_events)} events,{' '}
          {String(result.duplicates)} duplicates, {String(result.conflicts)} conflicts, {String(result.errors)} errors.{' '}
          <a href="/signals">View Signals</a>
        </p>
      )}
    </div>
  );
}
