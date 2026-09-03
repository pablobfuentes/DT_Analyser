import { useCallback, useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { api, Account } from '../api/client';
import { fetchDashboard } from '../api/dashboard';
import type { DashboardData, DashboardFiltersState } from '../types/dashboard';
import { defaultFilters, filtersToQueryParams, parseFiltersFromUrl } from '../utils/dates';
import { DashboardFiltersBar } from '../components/dashboard/DashboardFilters';
import { SummaryGrid } from '../components/dashboard/SummaryGrid';
import { CumulativePnlChart } from '../components/dashboard/CumulativePnlChart';
import { DailyPnlChart } from '../components/dashboard/DailyPnlChart';
import { SourceComparison } from '../components/dashboard/SourceComparison';
import { DailyResultsTable } from '../components/dashboard/DailyResultsTable';
import { RecentTradesTable } from '../components/dashboard/RecentTrades';
import { CalendarHeatmap } from '../components/dashboard/CalendarHeatmap';
import { TradingEdgeGrid } from '../components/dashboard/TradingEdgeGrid';
import { CurveToggleChart } from '../components/dashboard/CurveToggleChart';
import { DrawdownChart } from '../components/dashboard/DrawdownChart';
import { RDistributionChart } from '../components/dashboard/RDistributionChart';
import { ROutcomesTable } from '../components/dashboard/ROutcomesTable';
import { MetricCard } from '../components/dashboard/MetricCard';
import { formatMoney, formatPercent } from '../utils/money';

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

  const syncUrl = useCallback((f: DashboardFiltersState) => {
    const qp = filtersToQueryParams(f);
    setSearchParams(qp, { replace: true });
  }, [setSearchParams]);

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

  return (
    <div>
      <DashboardFiltersBar filters={filters} accounts={accounts} onChange={handleFilterChange} />

      {error && <div className="warning-banner">{error}</div>}
      {data?.warnings.map((w, i) => (
        <div key={i} className="warning-banner">{w}</div>
      ))}

      {loading && !data && <div className="empty-state">Loading dashboard…</div>}

      {data && data.empty && !loading && (
        <div className="empty-state">No closed trades match the current filters.</div>
      )}

      {data && !data.empty && data.advanced && (
        <>
          <SummaryGrid summary={data.summary} secondary={data.secondary} />

          {data.equity.available && (
            <div className="grid-secondary" style={{ marginTop: '0.5rem' }}>
              <MetricCard
                label="Starting Equity"
                value={formatMoney(data.equity.starting_equity)}
                sub="Realized equity basis"
              />
              <MetricCard
                label="Realized Equity"
                value={formatMoney(data.equity.current_realized_equity)}
                sub="Starting + realized P&L (excludes open positions)"
              />
              <MetricCard label="Realized Return" value={formatPercent(data.equity.realized_return_pct)} />
            </div>
          )}
          {!data.equity.available && data.equity.reason && (
            <p style={{ color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
              Realized Equity: — ({data.equity.reason})
            </p>
          )}

          <TradingEdgeGrid advanced={data.advanced} />

          <div className="section-title">Equity / P&L / R</div>
          <CurveToggleChart
            cumulative={data.cumulative}
            equitySeries={data.equity_series}
            rSeries={data.cumulative_r_series}
            rQualified={data.advanced.r.trade_count}
            rTotal={data.advanced.r.trade_count + data.advanced.r.missing_count}
          />

          <div className="section-title">Drawdown</div>
          <DrawdownChart
            series={data.drawdown_series}
            pctAvailable={data.advanced.drawdown.pct_available}
            rSeries={data.cumulative_r_series}
          />

          <div className="section-title">R Distribution</div>
          <RDistributionChart data={data.r_distribution} />

          <div className="section-title">R Outcomes</div>
          <ROutcomesTable r={data.advanced.r} streaks={data.advanced.streaks} />

          <div className="section-title">Cumulative Realized P&L (Daily)</div>
          <CumulativePnlChart data={data.cumulative} />

          <div className="section-title">Daily P&L</div>
          <DailyPnlChart data={data.daily} />

          <div className="section-title">Source (ordinary filter — Step 6 comparison skipped)</div>
          <p className="text-secondary">AUTO remains a normal source_type. Dedicated MANUAL-vs-AUTO pairing analytics are not a product focus.</p>
          <SourceComparison
            manual={data.source_comparison.manual}
            auto={data.source_comparison.auto}
            manualAdvanced={data.source_comparison_advanced?.manual ?? null}
            autoAdvanced={data.source_comparison_advanced?.auto ?? null}
          />

          <div className="section-title">Daily Results</div>
          <DailyResultsTable rows={data.daily} />

          <CalendarHeatmap daily={data.daily} />

          <div className="section-title">Recent Trades</div>
          <RecentTradesTable trades={data.recent_trades} />
        </>
      )}
    </div>
  );
}
