import type { AdvancedAnalytics } from '../../types/dashboard';
import { MetricCard } from './MetricCard';
import { formatCoverage, formatMoney, formatPercent, formatProfitFactor, formatR } from '../../utils/money';

export function TradingEdgeGrid({ advanced }: { advanced: AdvancedAnalytics }) {
  const { r, drawdown } = advanced;
  const ddSub = drawdown.pct_available && drawdown.max_pct
    ? `${formatMoney(drawdown.max_dollars, true)} / ${formatPercent(drawdown.max_pct)}`
    : formatMoney(drawdown.max_dollars, true);

  return (
    <>
      <div className="section-title">Trading Edge</div>
      <div className="grid-secondary">
        <MetricCard label="Average R" value={formatR(advanced.r.average)} sub="unrounded R-qualified" />
        <MetricCard label="Expectancy" value={formatMoney(advanced.dollar_expectancy, true)} sub="/ trade" />
        <MetricCard label="R Expectancy" value={formatR(advanced.r.expectancy)} sub="/ trade (R-qualified)" />
        <MetricCard
          label="Profit Factor"
          value={formatProfitFactor(advanced.profit_factor, advanced.profit_factor_status)}
        />
        <MetricCard label="Payoff" value={advanced.payoff_ratio ? parseFloat(advanced.payoff_ratio).toFixed(2) : '—'} />
        <MetricCard label="Max DD" value={ddSub} sub={drawdown.label} />
        <MetricCard
          label="R Coverage"
          value={formatCoverage(r.trade_count, r.missing_count)}
          sub="trades with risk data"
        />
      </div>
    </>
  );
}
