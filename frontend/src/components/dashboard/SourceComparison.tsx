import type { SourceAdvancedStats, SourceStats } from '../../types/dashboard';
import { formatMoney, formatPercent, formatProfitFactor, formatR } from '../../utils/money';
import { formatDuration } from '../../utils/duration';

interface Props {
  manual: SourceStats | null;
  auto: SourceStats | null;
  manualAdvanced: SourceAdvancedStats | null;
  autoAdvanced: SourceAdvancedStats | null;
}

const BASE_ROWS: { key: keyof SourceStats; label: string; fmt?: (v: unknown) => string }[] = [
  { key: 'trades', label: 'Trades', fmt: (v) => String(v) },
  { key: 'net_pnl', label: 'Net P&L', fmt: (v) => formatMoney(v as string, true) },
  { key: 'win_rate', label: 'Win Rate', fmt: (v) => formatPercent(v as string) },
  { key: 'avg_trade', label: 'Avg Trade', fmt: (v) => formatMoney(v as string, true) },
  { key: 'avg_winner', label: 'Avg Winner', fmt: (v) => formatMoney(v as string, true) },
  { key: 'avg_loser', label: 'Avg Loser', fmt: (v) => formatMoney(v as string, true) },
  { key: 'best_trade', label: 'Best Trade', fmt: (v) => formatMoney(v as string, true) },
  { key: 'worst_trade', label: 'Worst Trade', fmt: (v) => formatMoney(v as string, true) },
  { key: 'avg_hold_seconds', label: 'Avg Hold', fmt: (v) => formatDuration(v as number) },
];

const ADV_ROWS: {
  label: string;
  fmt: (m: SourceAdvancedStats | null) => string;
}[] = [
  { label: 'Expectancy', fmt: (m) => formatMoney(m?.dollar_expectancy, true) },
  { label: 'Profit Factor', fmt: (m) => formatProfitFactor(m?.profit_factor ?? null, m?.profit_factor_status) },
  { label: 'Payoff Ratio', fmt: (m) => (m?.payoff_ratio ? parseFloat(m.payoff_ratio).toFixed(2) : '—') },
  { label: 'Avg R', fmt: (m) => formatR(m?.average_r ?? null) },
  { label: 'R Expectancy', fmt: (m) => formatR(m?.r_expectancy ?? null) },
  { label: 'Max DD $', fmt: (m) => formatMoney(m?.max_drawdown_dollars, true) },
  { label: 'Max DD %', fmt: (m) => (m?.max_drawdown_pct ? formatPercent(m.max_drawdown_pct) : '—') },
  { label: 'Longest L Streak', fmt: (m) => (m ? String(m.longest_losing_streak) : '—') },
  { label: 'R Coverage', fmt: (m) => (m?.r_coverage_pct ? `${parseFloat(m.r_coverage_pct).toFixed(0)}%` : '—') },
];

export function SourceComparison({ manual, auto, manualAdvanced, autoAdvanced }: Props) {
  if (!manual && !auto) {
    return <div className="empty-state">No MANUAL or AUTO data for current filters.</div>;
  }

  return (
    <div className="card">
      <table>
        <thead>
          <tr>
            <th>Metric</th>
            <th style={{ color: 'var(--manual)' }}>MANUAL</th>
            <th style={{ color: 'var(--auto)' }}>AUTO</th>
          </tr>
        </thead>
        <tbody>
          {BASE_ROWS.map(({ key, label, fmt }) => (
            <tr key={key}>
              <td>{label}</td>
              <td>{manual ? (fmt ? fmt(manual[key]) : String(manual[key])) : '—'}</td>
              <td>{auto ? (fmt ? fmt(auto[key]) : String(auto[key])) : '—'}</td>
            </tr>
          ))}
          {ADV_ROWS.map(({ label, fmt }) => (
            <tr key={label}>
              <td>{label}</td>
              <td>{fmt(manualAdvanced)}</td>
              <td>{fmt(autoAdvanced)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
