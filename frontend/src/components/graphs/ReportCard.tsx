import { useMemo } from 'react';
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  Cell,
} from 'recharts';
import type { MetricKey, ReportBucket, ReportData, ReportMetric } from '../../types/reports';
import { formatMoney, formatPercent, formatR, parseMoney } from '../../utils/money';
import { formatDuration } from '../../utils/duration';

const EXECUTION_METRICS: MetricKey[] = [
  'average_mfe_r',
  'average_mae_r',
  'average_exit_efficiency',
  'average_r_left',
  'average_peak_giveback',
  'average_time_to_mfe',
];

function bucketMetricValue(bucket: ReportBucket, metric: MetricKey): number | null {
  switch (metric) {
    case 'net_pnl':
      return parseMoney(bucket.net_pnl);
    case 'avg_trade':
      return parseMoney(bucket.avg_trade);
    case 'win_rate':
      return bucket.win_rate != null ? parseFloat(bucket.win_rate) : null;
    case 'trade_count':
      return bucket.trade_count;
    case 'avg_winner':
      return bucket.avg_winner != null ? parseMoney(bucket.avg_winner) : null;
    case 'avg_loser':
      return bucket.avg_loser != null ? parseMoney(bucket.avg_loser) : null;
    case 'average_mfe_r':
      return bucket.average_mfe_r != null ? parseMoney(bucket.average_mfe_r) : null;
    case 'average_mae_r':
      return bucket.average_mae_r != null ? parseMoney(bucket.average_mae_r) : null;
    case 'average_exit_efficiency':
      return bucket.average_exit_efficiency != null ? parseMoney(bucket.average_exit_efficiency) : null;
    case 'average_r_left':
      return bucket.average_r_left != null ? parseMoney(bucket.average_r_left) : null;
    case 'average_peak_giveback':
      return bucket.average_peak_giveback != null ? parseMoney(bucket.average_peak_giveback) : null;
    case 'average_time_to_mfe':
      return bucket.average_time_to_mfe != null ? parseMoney(bucket.average_time_to_mfe) : null;
    case 'average_r':
      return bucket.average_r != null ? parseMoney(bucket.average_r) : null;
    case 'total_r':
      return bucket.total_r != null ? parseMoney(bucket.total_r) : null;
    case 'r_profit_factor':
      return bucket.r_profit_factor != null ? parseMoney(bucket.r_profit_factor) : null;
    case 'r_coverage_pct':
      return bucket.r_coverage_pct != null ? parseFloat(bucket.r_coverage_pct) : null;
    default:
      return null;
  }
}

function formatMetricValue(metric: MetricKey, value: number | null): string {
  if (value == null || Number.isNaN(value)) return '—';
  if (metric === 'trade_count') return String(value);
  if (metric === 'win_rate') return formatPercent(String(value));
  if (metric === 'average_mfe_r' || metric === 'average_mae_r' || metric === 'average_r_left' || metric === 'average_r' || metric === 'total_r') {
    return formatR(String(value));
  }
  if (metric === 'r_profit_factor') return value.toFixed(2);
  if (metric === 'r_coverage_pct' || metric === 'average_exit_efficiency' || metric === 'average_peak_giveback') {
    return formatPercent(String(value));
  }
  if (metric === 'average_time_to_mfe') return formatDuration(Math.round(value));
  return formatMoney(String(value), true);
}

interface Props {
  report: ReportData;
  metric: MetricKey;
  onMetricChange: (m: MetricKey) => void;
  activeBucketKey?: string;
  onBucketClick?: (bucketKey: string) => void;
  minSample: number;
  feedWarning?: string | null;
  metrics?: ReportMetric[];
}

export function ReportCard({
  report,
  metric,
  onMetricChange,
  activeBucketKey,
  onBucketClick,
  minSample,
  feedWarning,
  metrics,
}: Props) {
  const filteredBuckets = useMemo(
    () => report.buckets.filter((b) => b.trade_count >= minSample),
    [report.buckets, minSample],
  );

  const chartData = useMemo(
    () =>
      filteredBuckets.map((b) => ({
        key: b.key,
        label: b.label,
        value: bucketMetricValue(b, metric) ?? 0,
        trade_count: b.trade_count,
        net_pnl: b.net_pnl,
        excursion_coverage_pct: b.excursion_coverage_pct,
        r_coverage_pct: b.r_coverage_pct,
        r_qualified_count: b.r_qualified_count,
      })),
    [filteredBuckets, metric],
  );

  const tooltipLabel = (payload: {
    trade_count: number;
    excursion_coverage_pct?: string | null;
    r_coverage_pct?: string | null;
    r_qualified_count?: number;
  }) => {
    let label = `Trades: ${payload.trade_count}`;
    if (payload.r_qualified_count != null) {
      label += ` | R-qualified: ${payload.r_qualified_count}`;
    }
    if (payload.r_coverage_pct != null) {
      label += ` | Coverage: ${payload.r_coverage_pct}%`;
    }
    if (payload.excursion_coverage_pct != null) {
      label += ` · Excursion: ${payload.excursion_coverage_pct}%`;
    }
    return label;
  };

  const isHorizontal = report.chart_type === 'horizontal_bar' || filteredBuckets.length > 8;
  const colorFor = (v: number) => {
    if (metric === 'win_rate') return v >= 50 ? '#3dd68c' : '#f07178';
    if (metric === 'trade_count') return '#539bf5';
    if (EXECUTION_METRICS.includes(metric)) return '#539bf5';
    return v >= 0 ? '#3dd68c' : '#f07178';
  };

  const totalTrades = filteredBuckets.reduce((s, b) => s + b.trade_count, 0);

  return (
    <div className="report-card card" data-report={report.key}>
      <div className="report-card-header">
        <div>
          <h3 className="report-card-title">{report.title}</h3>
          <div className="report-card-meta">
            {report.availability_timing && (
              <span
                className={`timing-badge timing-${report.availability_timing.toLowerCase()}`}
                title={
                  report.availability_timing === 'PRE_ENTRY'
                    ? 'Known at entry. Safe for setup research.'
                    : report.availability_timing === 'EXIT'
                      ? 'Exit information. Not a pre-entry feature.'
                      : 'End-of-day information. Not known at entry — do not treat as predictive.'
                }
              >
                {report.availability_timing === 'PRE_ENTRY'
                  ? 'PRE-ENTRY'
                  : report.availability_timing === 'EXIT'
                    ? 'EXIT'
                    : 'END OF DAY'}
              </span>
            )}
            {report.description && <span className="text-secondary">{report.description}</span>}
            <span>{totalTrades} trades in chart</span>
            {report.coverage && (
              <span title="Current-cohort coverage for this dimension (after exploration filters).">
                Coverage: {report.coverage.coverage_pct}% ({report.coverage.excluded} excluded
                {report.coverage.exclusion_reasons
                  ? `; ${Object.entries(report.coverage.exclusion_reasons)
                      .map(([k, n]) => `${n} ${k.toLowerCase().replace(/_/g, ' ')}`)
                      .join(', ')}`
                  : ''}
                )
              </span>
            )}
            {report.section === 'EXECUTION' && filteredBuckets.some((b) => b.excursion_coverage_pct != null) && (
              <span title="Excursion data available per bucket">
                Excursion: avg{' '}
                {(
                  filteredBuckets.reduce((s, b) => s + parseFloat(b.excursion_coverage_pct || '0'), 0) /
                  filteredBuckets.length
                ).toFixed(0)}
                %
              </span>
            )}
          </div>
          {feedWarning &&
            (report.key === 'instrument_volume' ||
              report.key === 'instrument_rvol50' ||
              report.key === 'instrument_prior_rvol') && (
            <div className="feed-warning">{feedWarning}</div>
          )}
        </div>
        <label className="report-metric-select">
          Metric:{' '}
          <select value={metric} onChange={(e) => onMetricChange(e.target.value as MetricKey)}>
            {(metrics && metrics.length
              ? metrics
              : [
                  { key: 'net_pnl', label: 'Total P&L' },
                  { key: 'avg_trade', label: 'Average Trade' },
                  { key: 'win_rate', label: 'Win Rate' },
                  { key: 'trade_count', label: 'Trade Count' },
                  { key: 'avg_winner', label: 'Avg Winner' },
                  { key: 'avg_loser', label: 'Avg Loser' },
                ]
            ).map((m) => (
              <option key={m.key} value={m.key}>
                {m.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {!filteredBuckets.length ? (
        <div className="empty-state">No buckets meet minimum sample.</div>
      ) : (
        <div className="chart-container">
          <ResponsiveContainer width="100%" height={isHorizontal ? Math.max(180, filteredBuckets.length * 28) : 220}>
            {report.chart_type === 'line' ? (
              <LineChart data={chartData}>
                <CartesianGrid stroke="#2a3441" strokeDasharray="3 3" />
                <XAxis dataKey="label" stroke="#8b9bb4" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
                <YAxis stroke="#8b9bb4" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: '#1e2530', border: '1px solid #2a3441' }}
                  formatter={(value: number, _n, p) => [
                    formatMetricValue(metric, value),
                    tooltipLabel(p.payload as typeof chartData[number]),
                  ]}
                />
                <Line type="monotone" dataKey="value" stroke="#539bf5" dot={false} strokeWidth={2} />
              </LineChart>
            ) : (
              <BarChart data={chartData} layout={isHorizontal ? 'vertical' : 'horizontal'}>
                <CartesianGrid stroke="#2a3441" strokeDasharray="3 3" />
                {isHorizontal ? (
                  <>
                    <XAxis type="number" stroke="#8b9bb4" tick={{ fontSize: 11 }} />
                    <YAxis type="category" dataKey="label" stroke="#8b9bb4" tick={{ fontSize: 10 }} width={90} />
                  </>
                ) : (
                  <>
                    <XAxis dataKey="label" stroke="#8b9bb4" tick={{ fontSize: 10 }} interval={0} angle={-35} textAnchor="end" height={60} />
                    <YAxis stroke="#8b9bb4" tick={{ fontSize: 11 }} />
                  </>
                )}
                <Tooltip
                  contentStyle={{ background: '#1e2530', border: '1px solid #2a3441' }}
                  formatter={(value: number, _n, p) => [
                    formatMetricValue(metric, value),
                    tooltipLabel(p.payload as typeof chartData[number]),
                  ]}
                />
                <Bar
                  dataKey="value"
                  cursor={onBucketClick ? 'pointer' : 'default'}
                  onClick={(data) => {
                    if (onBucketClick && data?.key) onBucketClick(String(data.key));
                  }}
                >
                  {chartData.map((entry) => (
                    <Cell
                      key={entry.key}
                      fill={entry.key === activeBucketKey ? '#539bf5' : colorFor(entry.value)}
                      stroke={entry.key === activeBucketKey ? '#e7ecf1' : undefined}
                      strokeWidth={entry.key === activeBucketKey ? 2 : 0}
                    />
                  ))}
                </Bar>
              </BarChart>
            )}
          </ResponsiveContainer>
        </div>
      )}

      <div className="report-best-worst">
        {report.best_bucket && (
          <span className="profit">
            Best Observed: {report.best_bucket.label} {formatMoney(report.best_bucket.net_pnl, true)} n=
            {report.best_bucket.trade_count}
          </span>
        )}
        {report.worst_bucket && (
          <span className="loss">
            Worst Observed: {report.worst_bucket.label} {formatMoney(report.worst_bucket.net_pnl, true)} n=
            {report.worst_bucket.trade_count}
          </span>
        )}
      </div>
    </div>
  );
}
