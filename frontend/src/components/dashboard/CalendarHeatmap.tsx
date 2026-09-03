import type { DashboardDailyRow } from '../../types/dashboard';
import { formatMoney, pnlClass } from '../../utils/money';
import { Link } from 'react-router-dom';

export function CalendarHeatmap({ daily }: { daily: DashboardDailyRow[] }) {
  if (!daily.length) return null;

  const byDate = Object.fromEntries(daily.map((d) => [d.date, d]));

  const dates = daily.map((d) => d.date).sort();
  const first = new Date(dates[0] + 'T12:00:00');
  const year = first.getFullYear();
  const month = first.getMonth();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const startDow = new Date(year, month, 1).getDay();
  // Intentionally one calendar month: the month of the earliest daily P&L row
  // in the current dashboard payload (same daily net_pnl source as the charts).

  const cells = [];
  for (let i = 0; i < startDow; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) {
    const key = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
    cells.push(byDate[key] || null);
  }

  return (
    <div>
      <div className="section-title">Monthly Calendar — {first.toLocaleString('en-US', { month: 'long', year: 'numeric' })}</div>
      <div className="calendar-grid">
        {cells.map((day, i) =>
          day ? (
            <Link key={i} to={`/trades?date=${day.date}`} className="calendar-cell" style={{ textDecoration: 'none', color: 'inherit' }}>
              <div>{day.date.slice(8)}</div>
              <div className={pnlClass(day.net_pnl)}>{formatMoney(day.net_pnl, true)}</div>
              <div style={{ color: 'var(--text-secondary)' }}>{day.trades} trades</div>
            </Link>
          ) : (
            <div key={i} className="calendar-cell empty" />
          )
        )}
      </div>
    </div>
  );
}
