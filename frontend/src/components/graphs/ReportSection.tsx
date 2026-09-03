import { useEffect, useState } from 'react';
import type { MetricKey, ReportData, ReportMetric } from '../../types/reports';
import { ReportCard } from './ReportCard';

const SESSION_KEY = 'graphs-section-expanded';

function loadSectionState(): Record<string, boolean> {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

function saveSectionState(state: Record<string, boolean>) {
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(state));
}

const DEFAULT_OPEN = new Set(['TIME', 'TRADE', 'INSTRUMENT', 'SOURCE', 'BEHAVIOR', 'OUTCOMES']);

interface SectionProps {
  sectionKey: string;
  label: string;
  available: boolean;
  requires?: string | null;
  reports: ReportData[];
  expanded: boolean;
  onToggle: () => void;
  reportMetrics: Record<string, MetricKey>;
  onReportMetricChange: (reportKey: string, metric: MetricKey) => void;
  exploration: Record<string, string>;
  onBucketClick: (dimension: string | null, bucketKey: string) => void;
  minSample: number;
  feedWarning?: string | null;
  metrics?: ReportMetric[];
}

export function ReportSection({
  sectionKey,
  label,
  available,
  requires,
  reports,
  expanded,
  onToggle,
  reportMetrics,
  onReportMetricChange,
  exploration,
  onBucketClick,
  minSample,
  feedWarning,
  metrics,
}: SectionProps) {
  const count = reports.length;

  if (!available) {
    return (
      <section id={`section-${sectionKey}`} className="report-section report-section-future">
        <button type="button" className="report-section-header" onClick={onToggle}>
          <span>{expanded ? '▼' : '▶'}</span>
          <span>{label}</span>
          <span className="report-section-count">
            Requires {requires === 'MARKET_ENRICHMENT' ? 'market data enrichment' : requires?.replace(/_/g, ' ').toLowerCase()}
          </span>
        </button>
        {expanded && (
          <div className="future-section-placeholder card">
            Requires enrichment — {requires === 'MARKET_ENRICHMENT'
              ? 'configure a provider on Market Data and enrich trades. This is not a filtered-cohort empty state.'
              : requires?.replace(/_/g, ' ') || 'future step'}
          </div>
        )}
      </section>
    );
  }

  return (
    <section id={`section-${sectionKey}`} className="report-section">
      <button type="button" className="report-section-header" onClick={onToggle}>
        <span>{expanded ? '▼' : '▶'}</span>
        <span>{label}</span>
        <span className="report-section-count">{count} reports</span>
      </button>
      {expanded && (
        <div className="report-grid">
          {reports.map((report) => (
            <ReportCard
              key={report.key}
              report={report}
              metric={reportMetrics[report.key] || (report.default_metric as MetricKey)}
              onMetricChange={(m) => onReportMetricChange(report.key, m)}
              activeBucketKey={report.filter_dimension ? exploration[report.filter_dimension] : undefined}
              onBucketClick={
                report.filter_dimension
                  ? (key) => onBucketClick(report.filter_dimension, key)
                  : undefined
              }
              minSample={minSample}
              feedWarning={feedWarning}
              metrics={metrics}
            />
          ))}
        </div>
      )}
    </section>
  );
}

export function useSectionExpansion(sectionKeys: string[]) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>(() => {
    const saved = loadSectionState();
    const initial: Record<string, boolean> = {};
    for (const key of sectionKeys) {
      initial[key] = saved[key] ?? DEFAULT_OPEN.has(key);
    }
    return initial;
  });

  useEffect(() => {
    setExpanded((s) => {
      const saved = loadSectionState();
      const next = { ...s };
      let changed = false;
      for (const key of sectionKeys) {
        if (!(key in next)) {
          next[key] = saved[key] ?? DEFAULT_OPEN.has(key);
          changed = true;
        }
      }
      return changed ? next : s;
    });
  }, [sectionKeys]);

  useEffect(() => {
    saveSectionState(expanded);
  }, [expanded]);

  const toggle = (key: string) => setExpanded((s) => ({ ...s, [key]: !s[key] }));
  const expandAll = () => setExpanded(Object.fromEntries(sectionKeys.map((k) => [k, true])));
  const collapseAll = () => setExpanded(Object.fromEntries(sectionKeys.map((k) => [k, false])));
  const ensureExpanded = (key: string) => setExpanded((s) => ({ ...s, [key]: true }));

  return { expanded, toggle, expandAll, collapseAll, ensureExpanded };
}
