import { ImportPreview } from '../api/client';

interface ImportPreviewProps {
  preview: ImportPreview;
  timezone: string;
  onTimezoneChange: (tz: string) => void;
  onImport: () => void;
  loading?: boolean;
}

const TZ_OPTIONS = ['America/New_York', 'America/Mexico_City', 'UTC'];

export function ImportPreviewPanel({
  preview,
  timezone,
  onTimezoneChange,
  onImport,
  loading,
}: ImportPreviewProps) {
  if (preview.error) {
    return (
      <div style={{ color: 'red', marginTop: '1rem' }}>
        <strong>{preview.error}</strong>: {preview.message}
        {preview.detected_columns?.length > 0 && (
          <p>Columns: {preview.detected_columns.join(', ')}</p>
        )}
      </div>
    );
  }

  return (
    <div style={{ marginTop: '1rem' }}>
      <p>
        <strong>Detected:</strong> {preview.detected_source_type} ({preview.parser})
      </p>
      <p>
        <strong>Confidence:</strong> {preview.confidence != null ? (preview.confidence * 100).toFixed(0) + '%' : 'N/A'}
      </p>
      <p>
        <strong>Rows:</strong> {preview.row_count}
      </p>
      <p>
        <strong>Timezone status:</strong> {preview.timezone_status}
      </p>
      {(preview.timezone_status === 'REQUIRES_USER_INPUT' || preview.options) && (
        <label>
          Timezone:{' '}
          <select value={timezone} onChange={(e) => onTimezoneChange(e.target.value)}>
            {(preview.options || TZ_OPTIONS).map((tz) => (
              <option key={tz} value={tz}>
                {tz}
              </option>
            ))}
          </select>
        </label>
      )}
      {preview.warnings.map((w, i) => (
        <p key={i} style={{ color: 'orange' }}>
          {w}
        </p>
      ))}
      <h3>Preview (first records)</h3>
      <table border={1} cellPadding={6} style={{ borderCollapse: 'collapse', width: '100%' }}>
        <thead>
          <tr>
            <th>Ticker</th>
            <th>Direction/Side</th>
            <th>Entry Time</th>
            <th>Exit Time</th>
            <th>Quantity</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>P&L</th>
          </tr>
        </thead>
        <tbody>
          {preview.sample_normalized_records.map((r, i) => (
            <tr key={i}>
              <td>{r.ticker}</td>
              <td>{r.direction || r.side}</td>
              <td>{r.entry_time || r.time}</td>
              <td>{r.exit_time || ''}</td>
              <td>{r.quantity}</td>
              <td>{r.entry_price || r.price}</td>
              <td>{r.exit_price || ''}</td>
              <td>{r.pnl || ''}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <button
        style={{ marginTop: '1rem', padding: '0.5rem 1.5rem' }}
        onClick={onImport}
        disabled={loading || preview.timezone_status === 'REQUIRES_USER_INPUT' && !timezone}
      >
        {loading ? 'Importing...' : 'IMPORT'}
      </button>
    </div>
  );
}
