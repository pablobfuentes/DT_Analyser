import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api, Account } from '../api/client';
import { DashboardFiltersBar } from '../components/dashboard/DashboardFilters';
import type { DashboardFiltersState } from '../types/dashboard';
import { EXPLORATION_KEYS, EXPLORATION_LABELS } from '../types/reports';
import { defaultFilters } from '../utils/dates';
import {
  isPreEntryFilter,
  isRetrospectiveFilters,
  RETROSPECTIVE_FORWARD_BLOCKED,
  swapCohorts,
} from '../utils/researchFilters';

type Filters = Record<string, string>;

const COMMON_VALUES: Record<string, string[]> = {
  setup_quality: ['A+', 'A', 'Other'],
  signal_rvol_bucket: ['lt_2', '2_5', '5_10', '10_20', '20_plus'],
  retracement_bucket: ['lt_20', '20_30', '30_40', '40_50', '50_plus'],
  weekday: ['MON', 'TUE', 'WED', 'THU', 'FRI'],
  context_5m: ['bullish', 'not_bullish'],
  rvol_bucket: ['lt_2', '2_5', '5_10', '10_20', '20_plus'],
  mfe_r_bucket: ['lt_0_5', '0_5_1', '1_1_5', '1_5_2', '2_3', '3_5', '5_plus'],
};

export function ResearchPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [global, setGlobal] = useState<DashboardFiltersState>(defaultFilters());
  const [mode, setMode] = useState<'PRE_ENTRY_ONLY' | 'ALL_FEATURES'>('PRE_ENTRY_ONLY');
  const [exclusive, setExclusive] = useState(false);
  const [quality, setQuality] = useState('RECOMMENDED');
  const [filtersA, setFiltersA] = useState<Filters>({});
  const [filtersB, setFiltersB] = useState<Filters>({});
  const [nameA, setNameA] = useState('Cohort A');
  const [nameB, setNameB] = useState('Cohort B');
  const [compare, setCompare] = useState<Record<string, unknown> | null>(null);
  const [scatter, setScatter] = useState<Record<string, unknown> | null>(null);
  const [heatmap, setHeatmap] = useState<Record<string, unknown> | null>(null);
  const [rolling, setRolling] = useState<Record<string, unknown> | null>(null);
  const [dist, setDist] = useState<Record<string, unknown> | null>(null);
  const [robust, setRobust] = useState<Record<string, unknown> | null>(null);
  const [multi, setMulti] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [xVar, setXVar] = useState('signal_rvol');
  const [yVar, setYVar] = useState('actual_r');
  const [hx, setHx] = useState('signal_rvol_bucket');
  const [hy, setHy] = useState('retracement_bucket');
  const [hMetric, setHMetric] = useState('average_r');
  const [rollMetric, setRollMetric] = useState('average_r');
  const [rollWindow, setRollWindow] = useState(20);
  const [distVar, setDistVar] = useState('actual_r');
  const [minSample, setMinSample] = useState(1);
  const [mfDims, setMfDims] = useState('setup_quality,signal_rvol_bucket,retracement_bucket');
  const [views, setViews] = useState<Record<string, unknown>[]>([]);
  const [tab, setTab] = useState<'scatter' | 'heatmap' | 'rolling' | 'distribution'>('scatter');
  const [strategyVersion, setStrategyVersion] = useState('');

  useEffect(() => {
    api.getAccounts().then(setAccounts);
    api.listResearchViews().then((r) => setViews(r.items || []));
  }, []);

  const body = useMemo(
    () => ({
      global: {
        start_date: global.startDate || null,
        end_date: global.endDate || null,
        account_id: global.accountId || null,
        source_type: global.source === 'ALL' ? null : global.source,
        direction: global.direction === 'ALL' ? null : global.direction,
        ticker: global.ticker || null,
        strategy_version: strategyVersion || null,
      },
      research_mode: mode,
      quality_mode: quality,
      exclusive,
      include_partial_feed: quality !== 'RECOMMENDED',
      cohort_a: { name: nameA, filters: filtersA },
      cohort_b: { name: nameB, filters: filtersB },
    }),
    [global, mode, quality, exclusive, nameA, nameB, filtersA, filtersB, strategyVersion],
  );

  const run = async () => {
    setError(null);
    try {
      const [c, s, h, r, d, rb, mf] = await Promise.all([
        api.researchCompare(body),
        api.researchScatter({ ...body, x: xVar, y: yVar, which: 'A' }),
        api.researchHeatmap({ ...body, x: hx, y: hy, metric: hMetric, min_sample: minSample, on: 'universe' }),
        api.researchRolling({ ...body, metric: rollMetric, window: rollWindow, which: 'A' }),
        api.researchDistribution({ ...body, variable: distVar }),
        api.researchRobustness({ ...body, which: 'A', research_pct: 70 }),
        api.researchMultifactor({
          ...body,
          dimensions: mfDims.split(',').map((x) => x.trim()).filter(Boolean),
          min_sample: minSample,
          on: 'universe',
        }),
      ]);
      setCompare(c);
      setScatter(s);
      setHeatmap(h);
      setRolling(r);
      setDist(d);
      setRobust(rb);
      setMulti(mf);
    } catch (e: unknown) {
      setError(JSON.stringify(e));
    }
  };

  const addFilter = (target: 'A' | 'B', key: string, value: string) => {
    if (mode === 'PRE_ENTRY_ONLY' && !isPreEntryFilter(key)) {
      setError(`Not available before trade entry: ${key}`);
      return;
    }
    const setter = target === 'A' ? setFiltersA : setFiltersB;
    setter((prev) => ({ ...prev, [key]: value }));
  };

  const removeFilter = (target: 'A' | 'B', key: string) => {
    const setter = target === 'A' ? setFiltersA : setFiltersB;
    setter((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });
  };

  const applyHeatmapCell = (cell: Record<string, unknown>, target: 'A' | 'B') => {
    if (cell.is_other || !cell.filters) return;
    const f = cell.filters as Filters;
    if (target === 'A') setFiltersA(f);
    else setFiltersB(f);
  };

  const filtersARetrospective = isRetrospectiveFilters(filtersA);

  const saveView = async () => {
    const name = window.prompt('Research view name?');
    if (!name) return;
    await api.saveResearchView({
      name,
      research_mode: mode,
      global_scope: body.global,
      cohort_a: body.cohort_a,
      cohort_b: body.cohort_b,
      visualization: { tab, xVar, yVar, hx, hy, hMetric },
    });
    const listed = await api.listResearchViews();
    setViews(listed.items || []);
  };

  const loadView = async (id: number) => {
    const v = await api.getResearchView(id);
    const gs = (v.global_scope || {}) as Record<string, string>;
    setGlobal((g) => ({
      ...g,
      startDate: gs.start_date || '',
      endDate: gs.end_date || '',
      accountId: gs.account_id ? String(gs.account_id) : '',
      source: gs.source_type || 'ALL',
      direction: gs.direction || 'ALL',
      ticker: gs.ticker || '',
    }));
    setMode((v.research_mode as 'PRE_ENTRY_ONLY' | 'ALL_FEATURES') || 'PRE_ENTRY_ONLY');
    const ca = (v.cohort_a || {}) as { name?: string; filters?: Filters };
    const cb = (v.cohort_b || {}) as { name?: string; filters?: Filters };
    setNameA(ca.name || 'Cohort A');
    setNameB(cb.name || 'Cohort B');
    setFiltersA(ca.filters || {});
    setFiltersB(cb.filters || {});
  };

  const saveRule = async (status: 'RESEARCH' | 'FORWARD_TESTING' = 'RESEARCH') => {
    if (status === 'FORWARD_TESTING' && filtersARetrospective) {
      setError(RETROSPECTIVE_FORWARD_BLOCKED);
      return;
    }
    const name = window.prompt(status === 'FORWARD_TESTING' ? 'Forward-testing rule name?' : 'Candidate rule name?');
    if (!name) return;
    try {
      await api.createCandidateRule({
        name,
        filters: filtersA,
        research_mode: mode,
        research_start: global.startDate,
        research_end: global.endDate,
        status,
      });
    } catch (e: unknown) {
      setError(JSON.stringify(e));
    }
  };

  const star = async () => {
    const name = window.prompt('Pattern name?');
    if (!name || !compare) return;
    const a = compare.cohort_a as Record<string, unknown>;
    await api.starPattern({
      name,
      filters: filtersA,
      research_mode: mode,
      metrics: a,
      sample_size: a.trades,
      starred_from: 'compare',
      date_start: global.startDate,
      date_end: global.endDate,
    });
  };

  const points = ((scatter?.points as Record<string, unknown>[]) || []).map((p) => ({
    x: Number(p.x),
    y: Number(p.y),
    trade_id: p.trade_id,
  }));

  return (
    <div>
      <h2>Research Lab</h2>
      <p className="text-secondary">
        Exploratory comparison only. Observed Pattern / Candidate Pattern — not a proven edge.
      </p>
      <div className="warning-banner">
        Exploring many combinations increases the chance of finding patterns that occur by chance. Forward
        validation is recommended.
      </div>

      <div className="filters-bar">
        <label title="Allows information known before the trade or at the time the position is entered. Future path, exit and end-of-day information is excluded.">
          Research Mode
          <select value={mode} onChange={(e) => setMode(e.target.value as 'PRE_ENTRY_ONLY' | 'ALL_FEATURES')}>
            <option value="PRE_ENTRY_ONLY">KNOWN BY ENTRY</option>
            <option value="ALL_FEATURES">ALL FEATURES / RETROSPECTIVE</option>
          </select>
        </label>
        <label>
          Data Quality
          <select value={quality} onChange={(e) => setQuality(e.target.value)}>
            <option value="RECOMMENDED">Recommended</option>
            <option value="INCLUDE_PARTIAL">Include Partial</option>
            <option value="ALL">All</option>
          </select>
        </label>
        <label>
          <input type="checkbox" checked={exclusive} onChange={(e) => setExclusive(e.target.checked)} /> Force A/B
          Exclusive
        </label>
      </div>
      {mode !== 'PRE_ENTRY_ONLY' && (
        <div className="warning-banner">
          Some selected variables were only known after entry. Results are descriptive and should not be interpreted
          as entry-selection rules.
        </div>
      )}
      {filtersARetrospective && (
        <div className="warning-banner">{RETROSPECTIVE_FORWARD_BLOCKED}</div>
      )}

      <h3>Global Scope</h3>
      <DashboardFiltersBar filters={global} accounts={accounts} onChange={setGlobal} />
      <div className="filters-bar">
        <label>
          Strategy Version
          <input
            value={strategyVersion}
            onChange={(e) => setStrategyVersion(e.target.value)}
            placeholder="optional, e.g. v0.3.4"
          />
        </label>
      </div>

      <div className="grid-secondary" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <CohortBuilder
          title={nameA}
          onName={setNameA}
          filters={filtersA}
          mode={mode}
          onAdd={(k, v) => addFilter('A', k, v)}
          onRemove={(k) => removeFilter('A', k)}
        />
        <CohortBuilder
          title={nameB}
          onName={setNameB}
          filters={filtersB}
          mode={mode}
          onAdd={(k, v) => addFilter('B', k, v)}
          onRemove={(k) => removeFilter('B', k)}
        />
      </div>
      <div className="filters-bar">
        <button type="button" onClick={() => { setFiltersB({ ...filtersA }); setNameB(`${nameA} copy`); }}>
          Clone A → B
        </button>
        <button
          type="button"
          onClick={() => {
            const [nb, na] = swapCohorts(filtersA, filtersB);
            const [nB, nA] = swapCohorts(nameA, nameB);
            setFiltersA(na);
            setFiltersB(nb);
            setNameA(nA);
            setNameB(nB);
          }}
        >
          Swap A / B
        </button>
        <button type="button" className="active-toggle" onClick={run}>
          Run comparison
        </button>
        <label>
          Min trades
          <select value={minSample} onChange={(e) => setMinSample(Number(e.target.value))}>
            {[1, 5, 10, 20, 30, 50].map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </label>
        <button type="button" onClick={saveView}>Save View</button>
        <button type="button" onClick={() => saveRule('RESEARCH')}>Create Candidate Rule</button>
        <button
          type="button"
          disabled={filtersARetrospective}
          title={filtersARetrospective ? RETROSPECTIVE_FORWARD_BLOCKED : 'Only filters known by entry can be forward-tested.'}
          onClick={() => saveRule('FORWARD_TESTING')}
        >
          Start Forward Testing
        </button>
        <button type="button" onClick={star}>★ Candidate Pattern</button>
      </div>

      {error && <pre className="warning-banner">{error}</pre>}

      {compare && (
        <>
          {(compare.overlap_count as number) > 0 && (
            <div className="warning-banner">
              Cohort Overlap: {String(compare.overlap_count)} trades. These cohorts are not independent.
            </div>
          )}
          {(compare.cohort_a_retrospective || compare.cohort_b_retrospective) && (
            <span className="timing-badge">RETROSPECTIVE COHORT</span>
          )}
          <h3>Summary Comparison</h3>
          <p className="text-secondary">Observed Difference = A − B. Not a better-strategy label.</p>
          <table>
            <thead>
              <tr><th>Metric</th><th>{nameA}</th><th>{nameB}</th><th>Observed Difference</th></tr>
            </thead>
            <tbody>
              {((compare.comparison as { rows: Record<string, unknown>[] })?.rows || []).map((row) => (
                <tr key={String(row.metric)}>
                  <td>{String(row.metric)}</td>
                  <td>{row.cohort_a == null ? '—' : String(row.cohort_a)}</td>
                  <td>{row.cohort_b == null ? '—' : String(row.cohort_b)}</td>
                  <td>{row.observed_difference == null ? '—' : String(row.observed_difference)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {Boolean((compare.coverage as Record<string, unknown>)?.unequal_coverage_warning) && (
            <div className="warning-banner">{String((compare.coverage as Record<string, unknown>).unequal_coverage_warning)}</div>
          )}
          <p className="text-secondary">
            Base {String((compare.coverage as Record<string, unknown>)?.base_trades)} · A {String((compare.cohort_a as Record<string, unknown>)?.trades)} · B{' '}
            {String((compare.cohort_b as Record<string, unknown>)?.trades)} · R {String((compare.coverage as Record<string, unknown>)?.r_available_pct)}%
          </p>
          {(compare.comparison as { mean_r_difference?: Record<string, unknown> })?.mean_r_difference?.interpretation && (
            <p>
              Mean R difference CI: {String((compare.comparison as { mean_r_difference: Record<string, unknown> }).mean_r_difference.interpretation)}
            </p>
          )}
        </>
      )}

      <div className="filters-bar">
        {(['scatter', 'heatmap', 'rolling', 'distribution'] as const).map((t) => (
          <button key={t} type="button" className={tab === t ? 'active-toggle' : ''} onClick={() => setTab(t)}>
            {t}
          </button>
        ))}
      </div>

      {tab === 'scatter' && (
        <div className="card">
          <div className="filters-bar">
            <label>X <input value={xVar} onChange={(e) => setXVar(e.target.value)} /></label>
            <label>Y <input value={yVar} onChange={(e) => setYVar(e.target.value)} /></label>
          </div>
          {scatter && (
            <>
              <p className="text-secondary">
                Total {String(scatter.total)} · Plotted {String(scatter.plotted)} · Missing X {String(scatter.missing_x)} · Missing Y{' '}
                {String(scatter.missing_y)} · Both {String(scatter.missing_both)}
                {(scatter.spearman as Record<string, unknown>)?.available
                  ? ` · Spearman ρ=${String((scatter.spearman as Record<string, unknown>).rho)} n=${String((scatter.spearman as Record<string, unknown>).n)}`
                  : ''}
              </p>
              <p className="text-secondary">Descriptive relationship only.</p>
              <div className="chart-container">
                <ResponsiveContainer width="100%" height={260}>
                  <ScatterChart>
                    <CartesianGrid stroke="#2a3441" />
                    <XAxis dataKey="x" name={xVar} stroke="#8b9bb4" />
                    <YAxis dataKey="y" name={yVar} stroke="#8b9bb4" />
                    <Tooltip />
                    <Scatter data={points} fill="#539bf5" />
                  </ScatterChart>
                </ResponsiveContainer>
              </div>
              <ul>
                {points.slice(0, 8).map((p) => (
                  <li key={String(p.trade_id)}>
                    <Link to={`/trades/${p.trade_id}`}>Trade #{String(p.trade_id)}</Link>
                  </li>
                ))}
              </ul>
            </>
          )}
        </div>
      )}

      {tab === 'heatmap' && (
        <div className="card">
          <div className="filters-bar">
            <label>X dim <input value={hx} onChange={(e) => setHx(e.target.value)} /></label>
            <label>Y dim <input value={hy} onChange={(e) => setHy(e.target.value)} /></label>
            <label>Metric <input value={hMetric} onChange={(e) => setHMetric(e.target.value)} /></label>
          </div>
          {heatmap?.sparse_message ? <div className="warning-banner">{String(heatmap.sparse_message)}</div> : null}
          <table>
            <thead>
              <tr><th>Y \ X</th><th>cell</th><th>n</th><th>metric</th><th></th></tr>
            </thead>
            <tbody>
              {((heatmap?.cells as Record<string, unknown>[]) || []).map((c, i) => (
                <tr key={i}>
                  <td>{String(c.y_label)} / {String(c.x_label)}</td>
                  <td>{String(c.value ?? '—')}</td>
                  <td>{String(c.trade_count)}</td>
                  <td>cov {String(c.r_coverage_pct ?? '—')}</td>
                  <td>
                    {c.is_other ? (
                      <span className="text-secondary">Other (not a filter)</span>
                    ) : (
                      <>
                        <button type="button" onClick={() => applyHeatmapCell(c, 'A')}>Set as Cohort A</button>{' '}
                        <button type="button" onClick={() => applyHeatmapCell(c, 'B')}>Set as Cohort B</button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {tab === 'rolling' && rolling && (
        <div className="card">
          <div className="filters-bar">
            <label>Metric <input value={rollMetric} onChange={(e) => setRollMetric(e.target.value)} /></label>
            <label>
              Window
              <select value={rollWindow} onChange={(e) => setRollWindow(Number(e.target.value))}>
                {[10, 20, 30, 50, 100].map((n) => <option key={n} value={n}>{n} trades</option>)}
              </select>
            </label>
          </div>
          <p className="text-secondary">{String(rolling.note)}</p>
          {((rolling.version_markers as Record<string, unknown>[]) || []).map((m) => (
            <span key={String(m.index)} className="filter-chip">v {String(m.strategy_version)} @ {String(m.index)}</span>
          ))}
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={((rolling.points as Record<string, unknown>[]) || []).map((p) => ({ i: p.index, v: p.value != null ? Number(p.value) : null }))}>
              <CartesianGrid stroke="#2a3441" />
              <XAxis dataKey="i" stroke="#8b9bb4" />
              <YAxis stroke="#8b9bb4" />
              <Tooltip />
              <Line type="monotone" dataKey="v" stroke="#539bf5" dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {tab === 'distribution' && dist && (
        <div className="card">
          <label>Variable <input value={distVar} onChange={(e) => setDistVar(e.target.value)} /></label>
          <p className="text-secondary">
            ECDF n A={String((dist.cohort_a as Record<string, unknown>)?.n)} B={String((dist.cohort_b as Record<string, unknown>)?.n)}
          </p>
        </div>
      )}

      {robust && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3>Robustness & Sample Quality</h3>
          <pre style={{ whiteSpace: 'pre-wrap' }}>{JSON.stringify({ outlier: robust.outlier, concentration: robust.concentration, chrono: (robust.chrono_split as Record<string, unknown>)?.note }, null, 2)}</pre>
        </div>
      )}

      {multi && (
        <div className="card" style={{ marginTop: '1rem' }}>
          <h3>Multi-factor (max 3)</h3>
          <label>Dimensions <input value={mfDims} onChange={(e) => setMfDims(e.target.value)} style={{ minWidth: 360 }} /></label>
          {multi.blocked ? <div className="warning-banner">{String(multi.message)}</div> : null}
          <p>{String(multi.n_groups ?? 0)} groups</p>
        </div>
      )}

      {views.length > 0 && (
        <p>
          Saved views:{' '}
          {views.map((v) => (
            <button key={String(v.id)} type="button" onClick={() => loadView(Number(v.id))}>
              {String(v.name)}
            </button>
          ))}
        </p>
      )}
    </div>
  );
}

function CohortBuilder({
  title,
  onName,
  filters,
  mode,
  onAdd,
  onRemove,
}: {
  title: string;
  onName: (n: string) => void;
  filters: Filters;
  mode: string;
  onAdd: (k: string, v: string) => void;
  onRemove: (k: string) => void;
}) {
  const [key, setKey] = useState('setup_quality');
  const [value, setValue] = useState('A+');
  const disabled = mode === 'PRE_ENTRY_ONLY' && !isPreEntryFilter(key);
  return (
    <div className="card">
      <input value={title} onChange={(e) => onName(e.target.value)} />
      <div className="filters-bar">
        <label>
          Condition
          <select value={key} onChange={(e) => setKey(e.target.value)}>
            {EXPLORATION_KEYS.map((k) => (
              <option key={k} value={k} disabled={mode === 'PRE_ENTRY_ONLY' && !isPreEntryFilter(k)}>
                {EXPLORATION_LABELS[k] || k}
                {mode === 'PRE_ENTRY_ONLY' && !isPreEntryFilter(k) ? ' (not pre-entry)' : ''}
              </option>
            ))}
          </select>
        </label>
        <label>
          Value
          <select value={value} onChange={(e) => setValue(e.target.value)}>
            {(COMMON_VALUES[key] || ['']).map((v) => (
              <option key={v} value={v}>{v || 'type below'}</option>
            ))}
          </select>
        </label>
        <input value={value} onChange={(e) => setValue(e.target.value)} />
        <button type="button" disabled={disabled} title={disabled ? 'Not available before trade entry.' : ''} onClick={() => onAdd(key, value)}>
          Add
        </button>
      </div>
      <div>
        {Object.entries(filters).map(([k, v]) => (
          <span key={k} className="filter-chip">
            {EXPLORATION_LABELS[k] || k}: {v}{' '}
            <button type="button" onClick={() => onRemove(k)}>×</button>
          </span>
        ))}
      </div>
    </div>
  );
}
