import { Link } from 'react-router-dom';
import type { DashboardRecentTrade } from '../../types/dashboard';
import { formatMoney, pnlClass } from '../../utils/money';
import { formatDuration, formatTime } from '../../utils/duration';

export function RecentTradesTable({ trades }: { trades: DashboardRecentTrade[] }) {
  if (!trades.length) return null;

  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>Exit Time</th>
            <th>Ticker</th>
            <th>Source</th>
            <th>Dir</th>
            <th>Qty</th>
            <th>Entry</th>
            <th>Exit</th>
            <th>Net P&L</th>
            <th>Hold</th>
          </tr>
        </thead>
        <tbody>
          {trades.map((t) => (
            <tr key={t.id}>
              <td>{formatTime(t.exit_time_utc)}</td>
              <td><Link to={`/trades/${t.id}`}>{t.ticker}</Link></td>
              <td>{t.source_type.replace('TRADINGVIEW_', '')}</td>
              <td>{t.direction}</td>
              <td>{t.quantity}</td>
              <td>{t.avg_entry_price}</td>
              <td>{t.avg_exit_price ?? '—'}</td>
              <td className={pnlClass(t.net_pnl)}>{formatMoney(t.net_pnl, true)}</td>
              <td>{formatDuration(t.holding_seconds)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
