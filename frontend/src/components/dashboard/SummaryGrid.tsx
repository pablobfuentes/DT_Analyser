import type { DashboardSummary } from '../../types/dashboard';
import { formatMoney, formatPercent, pnlClass } from '../../utils/money';
import { formatDuration } from '../../utils/duration';
import { MetricCard } from './MetricCard';

interface Props {
  summary: DashboardSummary;
  secondary: {
    trading_days: number;
    green_days: number;
    red_days: number;
    breakeven_days: number;
    open_trades: number;
  };
}

export function SummaryGrid({ summary, secondary }: Props) {
  const wl = `${summary.wins} W / ${summary.losses} L / ${summary.breakeven} BE`;

  return (
    <>
      <div className="grid-summary">
        <MetricCard label="Net P&L" value={formatMoney(summary.net_pnl, true)} valueClass={pnlClass(summary.net_pnl)} sub={wl} />
        <MetricCard label="Trades" value={String(summary.trades)} sub={secondary.open_trades ? `Open: ${secondary.open_trades}` : undefined} />
        <MetricCard label="Win Rate" value={formatPercent(summary.win_rate)} />
        <MetricCard label="Avg Trade" value={formatMoney(summary.avg_trade, true)} valueClass={pnlClass(summary.avg_trade)} />
        <MetricCard label="Avg Winner" value={formatMoney(summary.avg_winner, true)} valueClass="profit" />
        <MetricCard label="Avg Loser" value={formatMoney(summary.avg_loser, true)} valueClass="loss" />
      </div>
      <div className="grid-secondary">
        <MetricCard label="Gross P&L" value={formatMoney(summary.gross_pnl, true)} valueClass={pnlClass(summary.gross_pnl)} />
        <MetricCard label="Fees" value={formatMoney(summary.fees)} />
        <MetricCard label="Best Trade" value={formatMoney(summary.best_trade, true)} valueClass="profit" />
        <MetricCard label="Worst Trade" value={formatMoney(summary.worst_trade, true)} valueClass="loss" />
        <MetricCard label="Avg Hold" value={formatDuration(summary.avg_hold_seconds)} />
        <MetricCard label="Trading Days" value={String(secondary.trading_days)} sub={`${secondary.green_days} green / ${secondary.red_days} red`} />
      </div>
    </>
  );
}
