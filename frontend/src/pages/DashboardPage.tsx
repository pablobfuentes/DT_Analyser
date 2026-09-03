import { useCallback, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, Account } from '../api/client';
import { fetchDashboard } from '../api/dashboard';
import type { DashboardData, DashboardFiltersState } from '../types/dashboard';
import { defaultFilters, filtersToQueryParams, parseFiltersFromUrl } from '../utils/dates';
import { DashboardFiltersBar } from '../components/dashboard/DashboardFilters';
import { PortfolioValueChart } from '../components/dashboard/PortfolioValueChart';
import { DailyResultsTable } from '../components/dashboard/DailyResultsTable';
import { RecentTradesTable } from '../components/dashboard/RecentTrades';
import { CalendarHeatmap } from '../components/dashboard/CalendarHeatmap';
import { MetricCard } from '../components/dashboard/MetricCard';
import { formatMoney, formatPercent, parseMoney, pnlClass } from '../utils/money';

export function DashboardPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<DashboardFiltersState>(() => {
    const parsed = parseFiltersFromUrl(searchParams);
    if (!searchParams.get('range')) return defaultFilters();
    return parsed;
  });
  const [data, setData] = useState<DashboardData | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getAccounts().then(setAccounts);
  }, []);

  const syncUrl = useCallback(
    (f: DashboardFiltersState) => {
      const qp = filtersToQueryParams(f);
      setSearchParams(qp, { replace: true });
    },
    [setSearchParams],
  );

  const load = useCallback(async (f: DashboardFiltersState) => {
    setLoading(true);
    setError(null);
    try {
      const d = await fetchDashboard(f);
      setData(d);
    } catch {
      setError('Unable to load dashboard.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    syncUrl(filters);
    load(filters);
  }, [filters, load, syncUrl]);

  const handleFilterChange = (f: DashboardFiltersState) => setFilters(f);

  const startingCapital = data?.equity.account_starting_equity ?? data?.equity.starting_equity ?? null;
  const portfolioValue = data?.equity.current_realized_equity ?? null;
  const periodReturnPct = data?.equity.realized_return_pct ?? null;

  const tradingDays = data?.secondary.trading_days || 0;
  const dailyAvgPct =
    periodReturnPct != null && tradingDays > 0 && !Number.isNaN(parseMoney(periodReturnPct))
      ? (parseMoney(periodReturnPct) / tradingDays).toFixed(2)
      : null;
  const avgDailyTrades =
    data && tradingDays > 0 ? (data.summary.trades / tradingDays).toFixed(1) : '—';

  const equitySeries = useMemo(() => data?.equity_series ?? [], [data]);

  return (
    <div>
      <DashboardFiltersBar filters={filters} accounts={accounts} onChange={handleFilterChange} />

      {error && <div className="warning-banner">{error}</div>}

      {loading && !data && <div className="empty-state">Loading dashboard…</div>}

      {data && data.empty && !loading && (
        <div className="empty-state">No closed trades match the current filters.</div>
      )}

      {data && !data.empty && (
        <div className="dashboard-layout">
          <div className="dashboard-left">
            <div className="dashboard-hero">
              <div className="metric-card dashboard-hero-main">
                <div className="metric-label">Portfolio value</div>
                <div className="portfolio-value-row">
                  <span className="metric-value">
                    {data.equity.available && portfolioValue != null
                      ? formatMoney(portfolioValue)
                      : '—'}
                  </span>
                  {data.equity.available && periodReturnPct != null ? (
                    <span className={`portfolio-change ${pnlClass(periodReturnPct)}`}>
                      {formatPercent(periodReturnPct)}
                    </span>
                  ) : (
                    <span className="portfolio-change neutral">Set equity on Accounts</span>
                  )}
                </div>
                {data.equity.available && startingCapital != null && (
                  <div className="metric-sub">Starting {formatMoney(startingCapital)}</div>
                )}
              </div>
              <MetricCard
                label="Daily avg % change"
                value={dailyAvgPct != null ? `${Number(dailyAvgPct) > 0 ? '+' : ''}${dailyAvgPct}%` : '—'}
                valueClass={pnlClass(dailyAvgPct)}
                sub={`${tradingDays} trading days`}
              />
              <MetricCard label="Win rate" value={formatPercent(data.summary.win_rate)} />
            </div>

            <div className="section-title">Portfolio — last 30 trading days</div>
            <PortfolioValueChart
              equitySeries={equitySeries}
              startingEquity={startingCapital}
            />

            <div className="section-title">Daily results</div>
            <DailyResultsTable rows={data.daily} />

            <div className="section-title">Trade stats</div>
            <div className="grid-secondary">
              <MetricCard label="Avg # daily trades" value={avgDailyTrades} />
              <MetricCard
                label="Best trade"
                value={formatMoney(data.summary.best_trade, true)}
                valueClass="profit"
              />
              <MetricCard
                label="Worst trade"
                value={formatMoney(data.summary.worst_trade, true)}
                valueClass="loss"
              />
              <MetricCard
                label="Avg winner"
                value={formatMoney(data.summary.avg_winner, true)}
                valueClass="profit"
              />
              <MetricCard
                label="Avg loser"
                value={formatMoney(data.summary.avg_loser, true)}
                valueClass="loss"
              />
              <MetricCard
                label="Avg trade"
                value={formatMoney(data.summary.avg_trade, true)}
                valueClass={pnlClass(data.summary.avg_trade)}
              />
              <MetricCard label="Trades" value={String(data.summary.trades)} />
              <MetricCard
                label="Net P&L"
                value={formatMoney(data.summary.net_pnl, true)}
                valueClass={pnlClass(data.summary.net_pnl)}
              />
            </div>
          </div>

          <div className="dashboard-right">
            <CalendarHeatmap daily={data.daily} />
            <div className="section-title">Recent trades</div>
            <RecentTradesTable trades={data.recent_trades} />
          </div>
        </div>
      )}
    </div>
  );
}
