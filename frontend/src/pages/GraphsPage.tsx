import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, Account } from '../api/client';
import { fetchReports } from '../api/reports';
import { DashboardFiltersBar } from '../components/dashboard/DashboardFilters';
import { ExplorationFilterBar } from '../components/graphs/ExplorationFilterBar';
import { QuickNav } from '../components/graphs/QuickNav';
import { ReportSection, useSectionExpansion } from '../components/graphs/ReportSection';
import type { MetricKey, ReportsResponse } from '../types/reports';
import type { DashboardFiltersState } from '../types/dashboard';
import { defaultFilters, filtersToQueryParams } from '../utils/dates';
import {
  graphFiltersToQueryParams,
  parseGraphFiltersFromUrl,
  resetExploration,
  toggleExplorationFilter,
  removeExplorationFilter,
  explorationToTradesParams,
} from '../utils/graphFilters';

export function GraphsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const graphState = useMemo(() => parseGraphFiltersFromUrl(searchParams), [searchParams]);
  const [data, setData] = useState<ReportsResponse | null>(null);
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reportMetrics, setReportMetrics] = useState<Record<string, MetricKey>>({});
  const [activeSection, setActiveSection] = useState<string>('TIME');

  const sectionKeys = useMemo(
    () => data?.sections.map((s) => s.key) || [],
    [data?.sections],
  );
  const { expanded, toggle, expandAll, collapseAll, ensureExpanded } = useSectionExpansion(sectionKeys);

  useEffect(() => {
    api.getAccounts().then(setAccounts);
  }, []);

  const updateGraphState = useCallback(
    (updater: (s: typeof graphState) => typeof graphState) => {
      setSearchParams(graphFiltersToQueryParams(updater(graphState)));
    },
    [graphState, setSearchParams],
  );

  const load = useCallback(async (state: typeof graphState) => {
    setLoading(true);
    setError(null);
    try {
      const d = await fetchReports(state);
      setData(d);
    } catch {
      setError('Unable to load reports.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(graphState);
  }, [graphState, load]);

  const handleGlobalChange = (f: DashboardFiltersState) => {
    updateGraphState((s) => ({ ...s, global: f }));
  };

  const handleBucketClick = (dimension: string | null, bucketKey: string) => {
    if (!dimension) return;
    updateGraphState((s) => ({
      ...s,
      exploration: toggleExplorationFilter(s.exploration, dimension, bucketKey),
    }));
  };

  const bucketLabels = useMemo(() => {
    const labels: Record<string, string> = {};
    data?.sections.forEach((sec) =>
      sec.reports.forEach((r) =>
        r.buckets.forEach((b) => {
          if (r.filter_dimension) labels[`${r.filter_dimension}:${b.key}`] = b.label;
        }),
      ),
    );
    return labels;
  }, [data]);

  const navigateSection = (key: string) => {
    ensureExpanded(key);
    setActiveSection(key);
    document.getElementById(`section-${key}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const tradesLinkParams = useMemo(() => {
    const global = filtersToQueryParams(graphState.global);
    const explore = explorationToTradesParams(graphState.exploration);
    const merged = { ...global, ...explore };
    delete merged.range;
    return new URLSearchParams(Object.entries(merged).filter(([, v]) => v)).toString();
  }, [graphState]);

  const globalForBar: DashboardFiltersState =
    graphState.global.range === 'all' && !searchParams.get('range')
      ? { ...graphState.global, range: 'all' }
      : graphState.global.range
        ? graphState.global
        : defaultFilters();

  const feedWarning = useMemo(() => {
    const md = data?.market_data;
    if (!md?.configured || md.is_consolidated) return null;
    return `Data feed: ${md.feed || 'partial'} — volume/RVOL is IEX/partial, not consolidated SIP. Excluded from volume reports unless Include Partial Feed is on.`;
  }, [data?.market_data]);

  const marketBanner = useMemo(() => {
    const md = data?.market_data;
    if (!md) return null;
    if (!md.configured) {
      return 'Provider Not Configured — Time, Behavior, and Outcome reports still work. Instrument/Market enrichment needs a provider.';
    }
    if ((data?.matching_trade_count ?? 0) > 0 && (md.cohort_market_available ?? 0) === 0) {
      return 'Filtered Cohort Has No Market Data — the current filters match trades, but none have instrument/market features.';
    }
    if (md.configured && (md.cohort_market_available ?? 0) === 0 && (data?.matching_trade_count ?? 0) === 0) {
      return null;
    }
    return null;
  }, [data]);

  return (
    <div className="graphs-page">
      <header className="graphs-page-header">
        <h1>Graphs</h1>
        <p className="text-secondary">Discover patterns by scrolling reports and clicking buckets to drill down.</p>
      </header>

      <DashboardFiltersBar filters={globalForBar} accounts={accounts} onChange={handleGlobalChange} />

      <ExplorationFilterBar
        filters={graphState.exploration}
        matchingCount={data?.matching_trade_count ?? 0}
        bucketLabels={bucketLabels}
        onRemove={(dim) =>
          updateGraphState((s) => ({ ...s, exploration: removeExplorationFilter(s.exploration, dim) }))
        }
        onReset={() => updateGraphState((s) => ({ ...s, exploration: resetExploration(s.exploration) }))}
      />

      <div className="graphs-toolbar">
        <QuickNav activeSection={activeSection} onNavigate={navigateSection} />
        <div className="graphs-toolbar-actions">
          <button type="button" className="btn-secondary" onClick={expandAll}>
            Expand All
          </button>
          <button type="button" className="btn-secondary" onClick={collapseAll}>
            Collapse All
          </button>
          <label>
            Min sample:{' '}
            <select
              value={graphState.minSample}
              onChange={(e) => updateGraphState((s) => ({ ...s, minSample: parseInt(e.target.value, 10) }))}
            >
              {[1, 2, 3, 5, 10].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          {data && data.matching_trade_count > 0 && (
            <Link to={`/trades?${tradesLinkParams}`} className="btn-secondary">
              View Matching Trades
            </Link>
          )}
          {data?.market_data && !data.market_data.is_consolidated && data.market_data.configured && (
            <label>
              <input
                type="checkbox"
                checked={!!graphState.includePartialFeed}
                onChange={(e) => updateGraphState((s) => ({ ...s, includePartialFeed: e.target.checked }))}
              />{' '}
              Include Partial Feed volume
            </label>
          )}
          <label>
            Signal origin{' '}
            <select
              value={graphState.pineScope}
              onChange={(e) => updateGraphState((s) => ({ ...s, pineScope: e.target.value }))}
            >
              <option value="REALTIME">REALTIME (default)</option>
              <option value="HISTORICAL_REPLAY">HISTORICAL_REPLAY</option>
              <option value="ALL">ALL origins</option>
            </select>
          </label>
          <span className="filter-chip">Signal Origin: {graphState.pineScope}</span>
          <label>
            <input
              type="checkbox"
              checked={!!graphState.includeSuggestedSignals}
              onChange={(e) => updateGraphState((s) => ({ ...s, includeSuggestedSignals: e.target.checked }))}
            />{' '}
            Include SUGGESTED links in Strategy
          </label>
        </div>
      </div>

          {error && <div className="warning-banner">{error}</div>}
      {marketBanner && <div className="warning-banner">{marketBanner}</div>}
      {data?.sections.map((section) =>
        section.key === 'STRATEGY' && section.empty_realtime_message ? (
          <div key="rt-empty" className="warning-banner">
            {section.empty_realtime_message} — change Signal Origin to include historical/replay. Historical data is not mixed in silently.
          </div>
        ) : null,
      )}
      {data?.sections.map((section) =>
        section.key === 'STRATEGY' && section.mixed_strategy_versions ? (
          <div key="mixed-ver" className="warning-banner">
            MIXED STRATEGY VERSIONS:{' '}
            {section.mixed_strategy_versions.versions
              .map((v) => `${v.original} (n=${v.sample_size})`)
              .join(', ')}
          </div>
        ) : null,
      )}
      {data?.sections.map((section) =>
        section.key === 'RISK' && section.empty_r_message ? (
          <div key="empty-r" className="warning-banner">{section.empty_r_message}</div>
        ) : null,
      )}
      {loading && !data && <div className="empty-state">Loading reports…</div>}

      {data?.sections.map((section) => (
        <ReportSection
          key={section.key}
          sectionKey={section.key}
          label={section.label}
          available={section.available}
          requires={section.requires}
          reports={section.reports}
          expanded={expanded[section.key] ?? false}
          onToggle={() => toggle(section.key)}
          reportMetrics={reportMetrics}
          onReportMetricChange={(rk, m) => setReportMetrics((s) => ({ ...s, [rk]: m }))}
          exploration={graphState.exploration}
          onBucketClick={handleBucketClick}
          minSample={graphState.minSample}
          feedWarning={feedWarning}
          metrics={data?.metrics}
        />
      ))}

      {data && data.matching_trade_count === 0 && !loading && (
        <div className="empty-state">No closed trades match the current filters.</div>
      )}
    </div>
  );
}
