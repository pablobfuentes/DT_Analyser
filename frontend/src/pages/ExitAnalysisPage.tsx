import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, Account } from '../api/client';
import { fetchExitAnalysis } from '../api/excursions';
import type { ExitAnalysisResponse, ExitAnalysisTableRow } from '../api/excursions';
import { DashboardFiltersBar } from '../components/dashboard/DashboardFilters';
import { MetricCard } from '../components/dashboard/MetricCard';
import type { DashboardFiltersState } from '../types/dashboard';
import { defaultFilters, filtersToQueryParams, parseFiltersFromUrl } from '../utils/dates';
import { formatDuration } from '../utils/duration';
import { formatPercent, formatR } from '../utils/money';

function pctDisplay(value: number | null | undefined): string {
  if (value == null) return '—';
  return `${value.toFixed(1)}%`;
}

function tableSection(title: string, rows: ExitAnalysisTableRow[], columns: 'left' | 'giveback' | 'capture') {
  if (!rows.length) {
    return (
      <div className="card" style={{ marginTop: '1rem' }}>
        <h3 className="section-title">{title}</h3>
        <div className="empty-state">No trades in this view.</div>
      </div>
    );
  }

  return (
    <div className="card" style={{ marginTop: '1rem' }}>
      <h3 className="section-title">{title}</h3>
      <table>
        <thead>
          <tr>
            <th>Date</th>
            <th>Ticker</th>
            <th>Actual R</th>
            <th>MFE R</th>
            {columns === 'giveback' && <th>Giveback R</th>}
            {columns !== 'giveback' && <th>Efficiency</th>}
            {columns === 'left' && <th>R Left</th>}
            {columns === 'giveback' && <th>Giveback %</th>}
            {columns === 'capture' && <th>Efficiency</th>}
            <th>MFE→Exit</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.trade_id}>
              <td>{row.exit_date ?? '—'}</td>
              <td>
                <Link to={`/trades/${row.trade_id}`}>{row.ticker}</Link>
              </td>
              <td>{formatR(row.actual_r)}</td>
              <td>{formatR(row.mfe_r)}</td>
              {columns === 'giveback' && <td>{formatR(row.peak_giveback_r)}</td>}
              {columns !== 'giveback' && <td>{formatPercent(row.exit_efficiency_pct)}</td>}
              {columns === 'left' && <td>{formatR(row.r_left_on_table)}</td>}
              {columns === 'giveback' && <td>{formatPercent(row.peak_giveback_pct)}</td>}
              {columns === 'capture' && <td>{formatPercent(row.exit_efficiency_pct)}</td>}
              <td>{formatDuration(row.mfe_to_exit_seconds)}</td>
              <td>{row.quality_status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ExitAnalysisPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [filters, setFilters] = useState<DashboardFiltersState>(() => {
    const parsed = parseFiltersFromUrl(searchParams);
    if (!searchParams.get('range')) return defaultFilters();
    return parsed;
  });
  const [data, setData] = useState<ExitAnalysisResponse | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getAccounts().then(setAccounts);
  }, []);

  const syncUrl = useCallback(
    (f: DashboardFiltersState) => {
      setSearchParams(filtersToQueryParams(f), { replace: true });
    },
    [setSearchParams],
  );

  const load = useCallback(async (f: DashboardFiltersState) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchExitAnalysis(f));
    } catch {
      setError('Unable to load exit analysis.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    syncUrl(filters);
    load(filters);
  }, [filters, load, syncUrl]);

  const summary = data?.summary ?? {};
  const coverage = data?.coverage;
  const hasSummary = Object.keys(summary).length > 0;

  return (
    <div className="exit-analysis-page">
      <header style={{ marginBottom: '1rem' }}>
        <h1>Exit Analyzer</h1>
        <p className="text-secondary">MFE/MAE, exit efficiency, and capture quality for closed trades.</p>
      </header>

      <DashboardFiltersBar filters={filters} accounts={accounts} onChange={setFilters} />

      {error && <div className="warning-banner">{error}</div>}
      {loading && !data && <div className="empty-state">Loading exit analysis…</div>}

      {data && (
        <>
          {coverage && (
            <div className="card" style={{ marginTop: '1rem' }}>
              <h3>Coverage</h3>
              <dl className="kv-list">
                <dt>Closed trades</dt>
                <dd>{coverage.total_closed_trades}</dd>
                <dt>Excursion enriched</dt>
                <dd>
                  {coverage.excursion_enriched} ({pctDisplay(coverage.excursion_coverage_pct)})
                </dd>
                <dt>R-qualified</dt>
                <dd>
                  {coverage.r_qualified_excursions} ({pctDisplay(coverage.mfe_r_coverage_pct)})
                </dd>
                <dt>Missing</dt>
                <dd>{coverage.missing_count}</dd>
                <dt>Boundary ambiguous</dt>
                <dd>{coverage.boundary_ambiguous_count}</dd>
              </dl>
            </div>
          )}

          {!hasSummary && !loading && (
            <div className="empty-state">No closed trades match the current filters.</div>
          )}

          {hasSummary && (
            <>
              <div className="section-title">Summary</div>
              <div className="grid-secondary">
                <MetricCard label="Avg MFE R" value={formatR(summary.average_mfe_r)} />
                <MetricCard label="Avg MAE R" value={formatR(summary.average_mae_r)} />
                <MetricCard label="Avg Exit Efficiency" value={formatPercent(summary.average_exit_efficiency)} />
                <MetricCard label="Median Exit Efficiency" value={formatPercent(summary.median_exit_efficiency)} />
                <MetricCard label="Avg R Left" value={formatR(summary.average_r_left_on_table)} />
                <MetricCard label="Avg Peak Giveback" value={formatPercent(summary.average_peak_giveback_pct)} />
                <MetricCard
                  label="Median Time to MFE"
                  value={formatDuration(
                    summary.median_time_to_mfe_seconds != null
                      ? parseInt(summary.median_time_to_mfe_seconds, 10)
                      : null,
                  )}
                />
              </div>

              <div className="section-title">Capture Thresholds</div>
              <div className="grid-secondary">
                <MetricCard label="Capture ≥25%" value={pctDisplay(summary.capture_ge_25_pct)} />
                <MetricCard label="Capture ≥50%" value={pctDisplay(summary.capture_ge_50_pct)} />
                <MetricCard label="Capture ≥75%" value={pctDisplay(summary.capture_ge_75_pct)} />
                <MetricCard label="Capture ≥90%" value={pctDisplay(summary.capture_ge_90_pct)} />
              </div>

              <div className="section-title">Opportunity Metrics</div>
              <div className="grid-secondary">
                <MetricCard
                  label="Positive MFE → Loss"
                  value={String(summary.positive_mfe_to_loss_count ?? '—')}
                  sub={pctDisplay(summary.positive_mfe_to_loss_pct)}
                />
                <MetricCard label="Reached 2R, closed &lt;1R" value={String(summary.reached_2r_closed_lt_1r ?? '—')} />
                <MetricCard label="Reached 2R, closed losing" value={String(summary.reached_2r_closed_losing ?? '—')} />
              </div>

              <div className="section-title">MFE R vs Actual R</div>
              <div className="card">
                {data.scatter.length === 0 ? (
                  <div className="empty-state">No scatter data for current filters.</div>
                ) : (
                  <table>
                    <thead>
                      <tr>
                        <th>Ticker</th>
                        <th>MFE R</th>
                        <th>MAE R</th>
                        <th>Actual R</th>
                        <th>Capture Gap</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.scatter.slice(0, 50).map((pt) => {
                        const mfe = parseFloat(pt.mfe_r);
                        const actual = parseFloat(pt.actual_r);
                        const gap = Number.isFinite(mfe) && Number.isFinite(actual) ? mfe - actual : NaN;
                        return (
                          <tr key={pt.trade_id}>
                            <td>
                              <Link to={`/trades/${pt.trade_id}`}>{pt.ticker}</Link>
                            </td>
                            <td>{formatR(pt.mfe_r)}</td>
                            <td>{formatR(pt.mae_r)}</td>
                            <td>{formatR(pt.actual_r)}</td>
                            <td>{Number.isFinite(gap) ? formatR(String(gap)) : '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
                {data.scatter.length > 50 && (
                  <p className="text-secondary" style={{ marginTop: '0.5rem', fontSize: '0.85rem' }}>
                    Showing first 50 of {data.scatter.length} trades.
                  </p>
                )}
              </div>

              {tableSection('Biggest R Left on Table', data.worst_left_on_table, 'left')}
              {tableSection('Biggest Peak Giveback', data.worst_giveback, 'giveback')}
              {tableSection(
                `Best Capture (MFE ≥ ${summary.best_capture_min_mfe_r ?? '0.5'}R)`,
                data.best_capture,
                'capture',
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
