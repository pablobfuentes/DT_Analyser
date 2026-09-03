import { useEffect, useState } from 'react';
import { API_BASE } from '../api/base';

type Status = 'checking' | 'ok' | 'offline';

export function ApiStatusBanner() {
  const [status, setStatus] = useState<Status>('checking');
  const [detail, setDetail] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const check = async () => {
      try {
        const res = await fetch(`${API_BASE}/health`, { signal: AbortSignal.timeout(8000) });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        if (!cancelled) {
          setStatus('ok');
          setDetail(null);
        }
      } catch (e) {
        if (!cancelled) {
          setStatus('offline');
          setDetail(e instanceof Error ? e.message : 'Backend unreachable');
        }
      }
    };

    check();
    const id = window.setInterval(check, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  if (status === 'checking' || status === 'ok') return null;

  return (
    <div
      role="alert"
      style={{
        background: '#5c1a1a',
        color: '#ffd6d6',
        padding: '0.75rem 1.5rem',
        borderBottom: '1px solid #8b2e2e',
        fontSize: '0.9rem',
      }}
    >
      <strong>Backend not connected.</strong> Import, dashboard, and other data features need the API
      running. {detail ? `(${detail})` : null} See{' '}
      <a href="https://github.com/pablobfuentes/DT_Analyser/blob/main/docs/DEPLOYMENT.md" style={{ color: '#ffb4b4' }}>
        deployment guide
      </a>
      .
    </div>
  );
}
