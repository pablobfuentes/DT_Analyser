import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { reviewsApi } from '../api/workflow';

export function ReviewHistoryPage() {
  const [data, setData] = useState<{ daily: Record<string, unknown>[]; weekly: Record<string, unknown>[] } | null>(null);
  useEffect(() => {
    reviewsApi.history().then(setData);
  }, []);
  if (!data) return <p>Loading…</p>;
  return (
    <div>
      <h2>Review History</h2>
      <h3 className="section-title">Daily</h3>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>P&amp;L</th>
            <th>Avg R</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data.daily.map((r) => (
            <tr key={String(r.date)}>
              <td>
                <Link to={`/review/daily?date=${r.date}`}>{String(r.date)}</Link>
              </td>
              <td>{String(r.net_pnl ?? '—')}</td>
              <td>{String(r.average_r ?? '—')}</td>
              <td>{String(r.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h3 className="section-title">Weekly</h3>
      <table>
        <thead>
          <tr>
            <th>Week</th>
            <th>P&amp;L</th>
            <th>Avg R</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {data.weekly.map((r) => (
            <tr key={String(r.week_start)}>
              <td>
                <Link to={`/review/weekly?week=${r.week_start}`}>
                  {String(r.week_start)} → {String(r.week_end)}
                </Link>
              </td>
              <td>{String(r.net_pnl ?? '—')}</td>
              <td>{String(r.average_r ?? '—')}</td>
              <td>{String(r.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
