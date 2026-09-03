import { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import {
  enrichExcursions,
  fetchExcursionCoverage,
  recalculateExcursions,
  type ExcursionCoverage,
} from '../api/excursions';

interface MarketStatus {
  configured: boolean;
  provider: string;
  feed: string | null;
  is_consolidated: boolean | null;
  benchmark: string;
  total_trades: number;
  instrument_enriched: number;
  market_enriched: number;
  coverage_pct: number;
}

function pctDisplay(value: number | null | undefined): string {
  if (value == null) return '—';
  return `${value.toFixed(1)}%`;
}

export function MarketDataPage() {
  const [status, setStatus] = useState<MarketStatus | null>(null);
  const [excursionCoverage, setExcursionCoverage] = useState<ExcursionCoverage | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [marketStatus, coverage] = await Promise.all([
        api.getMarketDataStatus(),
        fetchExcursionCoverage().catch(() => null),
      ]);
      setStatus(marketStatus);
      setExcursionCoverage(coverage);
    } catch {
      setError('Unable to load market data status.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const runMarket = async (action: 'enrich' | 'recalculate' | 'refresh', scope?: string) => {
    setBusy(`market-${action}`);
    setMessage(null);
    setError(null);
    try {
      const result =
        action === 'enrich'
          ? await api.enrichMarketData(scope || 'missing')
          : action === 'refresh'
            ? await api.refreshMarketData(scope || 'all')
            : await api.recalculateMarketFeatures();
      setMessage(`Market job ${String(result.status || 'done')} — ${String(result.trades_requested ?? '')} trades`);
      await load();
    } catch {
      setError(`Failed to ${action} market data.`);
    } finally {
      setBusy(null);
    }
  };

  const runExcursion = async (action: 'enrich' | 'recalculate') => {
    setBusy(`excursion-${action}`);
    setMessage(null);
    setError(null);
    try {
      const result = action === 'enrich' ? await enrichExcursions('missing') : await recalculateExcursions();
      setMessage(
        `Excursion ${action} ${String(result.status || 'done')} — ${String(result.enriched ?? result.trades_requested ?? '')} trades`,
      );
      await load();
    } catch {
      setError(`Failed to ${action} excursions.`);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="market-data-page">
      <header>
        <h1>Market Data</h1>
        <p className="text-secondary">Instrument and benchmark enrichment for Graphs analytics.</p>
      </header>

      {loading && <div className="loading">Loading…</div>}
      {error && <div className="error-banner">{error}</div>}
      {message && <div className="success-banner">{message}</div>}

      {status && (
        <div className="card market-data-grid">
          <div>
            <h3>Provider</h3>
            <dl className="kv-list">
              <dt>Provider</dt>
              <dd>{status.provider}</dd>
              <dt>Feed</dt>
              <dd>{status.feed || '—'}</dd>
              <dt>Consolidated</dt>
              <dd>{status.is_consolidated == null ? '—' : status.is_consolidated ? 'Yes' : 'No (partial)'}</dd>
              <dt>Configured</dt>
              <dd>{status.configured ? 'Yes' : 'No'}</dd>
              <dt>Benchmark</dt>
              <dd>{status.benchmark}</dd>
            </dl>
          </div>
          <div>
            <h3>Daily Coverage</h3>
            <dl className="kv-list">
              <dt>Trades</dt>
              <dd>{status.total_trades}</dd>
              <dt>Instrument enriched</dt>
              <dd>{status.instrument_enriched}</dd>
              <dt>Market enriched</dt>
              <dd>{status.market_enriched}</dd>
              <dt>Coverage</dt>
              <dd>{status.coverage_pct}%</dd>
            </dl>
          </div>
        </div>
      )}

      <div className="market-data-actions">
        <button type="button" className="btn-primary" disabled={!!busy} onClick={() => runMarket('enrich', 'missing')}>
          {busy === 'market-enrich' ? 'Enriching…' : 'Enrich Missing Data'}
        </button>
        <button type="button" className="btn-secondary" disabled={!!busy} onClick={() => runMarket('recalculate')}>
          {busy === 'market-recalculate' ? 'Recalculating…' : 'Recalculate Features'}
        </button>
        <button
          type="button"
          className="btn-secondary"
          disabled={!!busy}
          title="Fetches bars from the provider. Recalculate never uses the network."
          onClick={() => runMarket('refresh', 'all')}
        >
          {busy === 'market-refresh' ? 'Refreshing…' : 'Refresh From Provider'}
        </button>
      </div>

      {excursionCoverage && (
        <>
          <div className="section-title">Intraday / Excursions</div>
          <div className="card market-data-grid">
            <div>
              <h3>Excursion Coverage</h3>
              <dl className="kv-list">
                <dt>Closed trades</dt>
                <dd>{excursionCoverage.total_closed_trades}</dd>
                <dt>Excursion enriched</dt>
                <dd>
                  {excursionCoverage.excursion_enriched} ({pctDisplay(excursionCoverage.excursion_coverage_pct)})
                </dd>
                <dt>R-qualified</dt>
                <dd>
                  {excursionCoverage.r_qualified_excursions} ({pctDisplay(excursionCoverage.mfe_r_coverage_pct)})
                </dd>
                <dt>Missing</dt>
                <dd>{excursionCoverage.missing_count}</dd>
                <dt>Boundary ambiguous</dt>
                <dd>{excursionCoverage.boundary_ambiguous_count}</dd>
              </dl>
            </div>
            <div>
              <h3>Intraday Cache</h3>
              <dl className="kv-list">
                <dt>Bars cached</dt>
                <dd>{excursionCoverage.intraday_bars_cached ?? excursionCoverage.intraday_bar_count ?? '—'}</dd>
                <dt>Symbol-days</dt>
                <dd>{excursionCoverage.unique_symbol_days}</dd>
                <dt>Avg bars / day</dt>
                <dd>{excursionCoverage.avg_bars_per_symbol_day ?? '—'}</dd>
                <dt>DB size</dt>
                <dd>{excursionCoverage.database_size_mb != null ? `${excursionCoverage.database_size_mb} MB` : '—'}</dd>
                <dt>Consolidated / partial</dt>
                <dd>
                  {excursionCoverage.consolidated_count} / {excursionCoverage.partial_feed_count}
                </dd>
              </dl>
            </div>
          </div>

          <div className="market-data-actions">
            <button
              type="button"
              className="btn-primary"
              disabled={!!busy}
              onClick={() => runExcursion('enrich')}
            >
              {busy === 'excursion-enrich' ? 'Enriching…' : 'Enrich Missing Excursions'}
            </button>
            <button
              type="button"
              className="btn-secondary"
              disabled={!!busy}
              onClick={() => runExcursion('recalculate')}
            >
              {busy === 'excursion-recalculate' ? 'Recalculating…' : 'Recalculate Excursions'}
            </button>
          </div>
        </>
      )}

      {!status?.configured && (
        <p className="text-secondary">
          Market Data: Not configured. Set <code>LTA_MARKET_DATA_PROVIDER</code> and Alpaca credentials to enable live
          enrichment. Graphs Market section remains unavailable until configured and enriched.
        </p>
      )}
    </div>
  );
}
