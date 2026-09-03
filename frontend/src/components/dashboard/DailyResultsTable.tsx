import { Link } from 'react-router-dom';
import type { DashboardDailyRow } from '../../types/dashboard';
import { formatMoney, formatPercent, pnlClass } from '../../utils/money';

export function DailyResultsTable({ rows }: { rows: DashboardDailyRow[] }) {
  if (!rows.length) return null;

  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Trades</th>
            <th>W</th>
            <th>L</th>
            <th>BE</th>
            <th>Win Rate</th>
            <th>Gross</th>
            <th>Fees</th>
            <th>Net P&L</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((d) => (
            <tr key={d.date}>
              <td>
                <Link to={`/trades?date=${d.date}`}>{d.date}</Link>
              </td>
              <td>{d.trades}</td>
              <td>{d.wins}</td>
              <td>{d.losses}</td>
              <td>{d.breakeven}</td>
              <td>{formatPercent(d.win_rate)}</td>
              <td>{formatMoney(d.gross_pnl, true)}</td>
              <td>{formatMoney(d.fees)}</td>
              <td className={pnlClass(d.net_pnl)}>{formatMoney(d.net_pnl, true)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
