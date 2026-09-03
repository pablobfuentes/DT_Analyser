import { useMemo } from 'react';
import {
  CartesianGrid,
  Customized,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { formatMoney, parseMoney } from '../../utils/money';

interface EquityPoint {
  date: string;
  equity?: string;
}

interface Props {
  equitySeries: EquityPoint[];
  startingEquity: string | null | undefined;
}

interface DayPoint {
  date: string;
  value: number;
}

/** Point on the plot; xIndex may be fractional when crossing start between days. */
interface PlotPoint {
  xIndex: number;
  value: number;
}

type Seg = { color: string; points: PlotPoint[] };

function dailyPortfolio(series: EquityPoint[]): DayPoint[] {
  const byDate = new Map<string, number>();
  for (const p of series) {
    if (!p.date || p.equity == null || p.equity === '') continue;
    const n = parseMoney(p.equity);
    if (Number.isNaN(n)) continue;
    byDate.set(p.date, n);
  }
  return [...byDate.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .slice(-30)
    .map(([date, value]) => ({ date: date.slice(5), value }));
}

function themeColors() {
  const style = getComputedStyle(document.documentElement);
  return {
    grid: style.getPropertyValue('--border').trim() || '#2a3441',
    muted: style.getPropertyValue('--text-secondary').trim() || '#8b9bb4',
    card: style.getPropertyValue('--bg-card').trim() || '#1e2530',
    profit: style.getPropertyValue('--profit').trim() || '#3dd68c',
    loss: style.getPropertyValue('--loss').trim() || '#f07178',
  };
}

/**
 * Build colored path segments. When equity crosses start between day i-1 and i,
 * the color change happens mid-edge (interpolated), never as a vertical jump on a day.
 */
function colorSegments(rows: DayPoint[], start: number | null, profit: string, loss: string): Seg[] {
  if (!rows.length) return [];
  if (start == null || !(start > 0)) {
    return [{ color: profit, points: rows.map((r, i) => ({ xIndex: i, value: r.value })) }];
  }

  const segments: Seg[] = [];
  let side: 'above' | 'below' = rows[0].value >= start ? 'above' : 'below';
  let current: PlotPoint[] = [{ xIndex: 0, value: rows[0].value }];

  for (let i = 1; i < rows.length; i++) {
    const prev = rows[i - 1];
    const cur = rows[i];
    const curSide: 'above' | 'below' = cur.value >= start ? 'above' : 'below';

    if (curSide === side) {
      current.push({ xIndex: i, value: cur.value });
      continue;
    }

    const delta = cur.value - prev.value;
    const t = Math.abs(delta) < 1e-12 ? 0.5 : (start - prev.value) / delta;
    const clamped = Math.min(1, Math.max(0, t));
    const cross: PlotPoint = { xIndex: i - 1 + clamped, value: start };

    current.push(cross);
    segments.push({ color: side === 'above' ? profit : loss, points: current });
    current = [cross, { xIndex: i, value: cur.value }];
    side = curSide;
  }

  segments.push({ color: side === 'above' ? profit : loss, points: current });
  return segments;
}

function xPixel(
  xIndex: number,
  dates: string[],
  scale: (v: string) => number,
): number {
  const left = Math.floor(xIndex);
  const right = Math.ceil(xIndex);
  if (left === right || right >= dates.length) {
    return scale(dates[Math.min(left, dates.length - 1)]);
  }
  const frac = xIndex - left;
  return scale(dates[left]) + frac * (scale(dates[right]) - scale(dates[left]));
}

function SegmentPaths({
  dates,
  segments,
  xAxisMap,
  yAxisMap,
}: {
  dates: string[];
  segments: Seg[];
  xAxisMap?: Record<string, { scale: (v: string) => number }>;
  yAxisMap?: Record<string, { scale: (v: number) => number }>;
}) {
  if (!xAxisMap || !yAxisMap || !dates.length) return null;
  const xAxis = Object.values(xAxisMap)[0];
  const yAxis = Object.values(yAxisMap)[0];
  if (!xAxis?.scale || !yAxis?.scale) return null;

  return (
    <g>
      {segments.map((seg, idx) => {
        if (seg.points.length === 1) {
          const p = seg.points[0];
          return (
            <circle
              key={idx}
              cx={xPixel(p.xIndex, dates, xAxis.scale)}
              cy={yAxis.scale(p.value)}
              r={3}
              fill={seg.color}
            />
          );
        }
        if (seg.points.length < 2) return null;
        const d = seg.points
          .map((p, i) => {
            const x = xPixel(p.xIndex, dates, xAxis.scale);
            const y = yAxis.scale(p.value);
            return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
          })
          .join(' ');
        return (
          <path
            key={idx}
            d={d}
            fill="none"
            stroke={seg.color}
            strokeWidth={2.5}
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        );
      })}
    </g>
  );
}

export function PortfolioValueChart({ equitySeries, startingEquity }: Props) {
  const start = parseMoney(startingEquity);
  const hasStart = !Number.isNaN(start) && start > 0;
  const rows = useMemo(() => dailyPortfolio(equitySeries), [equitySeries]);
  const colors = themeColors();
  const segments = useMemo(
    () => colorSegments(rows, hasStart ? start : null, colors.profit, colors.loss),
    [rows, hasStart, start, colors.profit, colors.loss],
  );
  const dates = useMemo(() => rows.map((r) => r.date), [rows]);

  if (!rows.length) {
    return (
      <div className="empty-state">
        {hasStart ? 'No portfolio history for this range.' : 'Set starting equity on Accounts to show portfolio value.'}
      </div>
    );
  }

  const values = rows.map((r) => r.value);
  if (hasStart) values.push(start);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = Math.max((max - min) * 0.08, Math.abs(max) * 0.01, 1);
  const chartData = rows.map((r) => ({ date: r.date, value: r.value }));

  return (
    <div className="chart-container">
      <ResponsiveContainer width="100%" height={280}>
        <LineChart data={chartData}>
          <CartesianGrid stroke={colors.grid} strokeDasharray="3 3" />
          <XAxis dataKey="date" stroke={colors.muted} tick={{ fontSize: 11 }} />
          <YAxis
            stroke={colors.muted}
            tick={{ fontSize: 11 }}
            domain={[min - pad, max + pad]}
            tickFormatter={(v) => `$${Number(v).toLocaleString('en-US', { maximumFractionDigits: 0 })}`}
            width={72}
          />
          <Tooltip
            contentStyle={{ background: colors.card, border: `1px solid ${colors.grid}`, color: 'var(--text-primary)' }}
            formatter={(value: number) => [formatMoney(String(value)), 'Portfolio']}
            labelFormatter={(l) => `Date: ${l}`}
          />
          {hasStart && (
            <ReferenceLine
              y={start}
              stroke={colors.muted}
              strokeDasharray="4 4"
              label={{ value: 'Start', fill: colors.muted, fontSize: 11, position: 'insideTopRight' }}
            />
          )}
          <Line
            type="monotone"
            dataKey="value"
            stroke="transparent"
            strokeWidth={2}
            dot={false}
            activeDot={{ r: 4, fill: colors.muted }}
            isAnimationActive={false}
          />
          <Customized
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            component={(props: any) => (
              <SegmentPaths
                dates={dates}
                segments={segments}
                xAxisMap={props.xAxisMap}
                yAxisMap={props.yAxisMap}
              />
            )}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
