import type { RMetrics, StreakMetrics } from '../../types/dashboard';
import { formatR } from '../../utils/money';

export function ROutcomesTable({ r, streaks }: { r: RMetrics; streaks: StreakMetrics }) {
  const rows: [string, string][] = [
    ['Average R', formatR(r.average)],
    ['Median R', formatR(r.median)],
    ['R Expectancy', formatR(r.expectancy)],
    ['Avg Winner R', formatR(r.avg_winner)],
    ['Avg Loser R', formatR(r.avg_loser)],
    ['Best R', formatR(r.best)],
    ['Worst R', formatR(r.worst)],
    ['R Trades', String(r.trade_count)],
    ['Missing R', String(r.missing_count)],
    ['Coverage', r.coverage_pct ? `${parseFloat(r.coverage_pct).toFixed(1)}%` : '—'],
    ['Longest Win Streak', String(streaks.longest_win)],
    ['Longest Loss Streak', String(streaks.longest_loss)],
    [
      'Current Streak',
      streaks.current_type === 'BE'
        ? 'BE'
        : streaks.current_type
          ? `${streaks.current_type.charAt(0)}${streaks.current_count}`
          : '—',
    ],
  ];

  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>R Outcomes</th>
            <th>Value</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <td>{label}</td>
              <td>{value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
