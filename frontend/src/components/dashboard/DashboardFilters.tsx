import type { Account } from '../../api/client';
import type { DashboardFiltersState, DateRangePreset } from '../../types/dashboard';
import { presetToDateRange } from '../../utils/dates';

interface Props {
  filters: DashboardFiltersState;
  accounts: Account[];
  onChange: (f: DashboardFiltersState) => void;
}

const PRESETS: { value: DateRangePreset; label: string }[] = [
  { value: 'today', label: 'Today' },
  { value: 'yesterday', label: 'Yesterday' },
  { value: 'this_week', label: 'This Week' },
  { value: 'last_7', label: 'Last 7 Days' },
  { value: 'this_month', label: 'This Month' },
  { value: 'last_30', label: 'Last 30 Days' },
  { value: 'all', label: 'All Time' },
  { value: 'custom', label: 'Custom' },
];

export function DashboardFiltersBar({ filters, accounts, onChange }: Props) {
  const set = (partial: Partial<DashboardFiltersState>) => {
    const next = { ...filters, ...partial };
    if (partial.range && partial.range !== 'custom') {
      const { start, end } = presetToDateRange(partial.range);
      next.startDate = start;
      next.endDate = end;
    }
    onChange(next);
  };

  return (
    <div className="filters-bar">
      <label>
        Date Range
        <select value={filters.range} onChange={(e) => set({ range: e.target.value as DateRangePreset })}>
          {PRESETS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}</option>
          ))}
        </select>
      </label>
      {filters.range === 'custom' && (
        <>
          <label>
            From
            <input type="date" value={filters.startDate} onChange={(e) => set({ startDate: e.target.value })} />
          </label>
          <label>
            To
            <input type="date" value={filters.endDate} onChange={(e) => set({ endDate: e.target.value })} />
          </label>
        </>
      )}
      <label>
        Account
        <select value={filters.accountId} onChange={(e) => set({ accountId: e.target.value })}>
          <option value="">All Accounts</option>
          {accounts.map((a) => (
            <option key={a.id} value={String(a.id)}>{a.name}</option>
          ))}
        </select>
      </label>
      <label>
        Source
        <select value={filters.source} onChange={(e) => set({ source: e.target.value })}>
          <option value="ALL">All</option>
          <option value="MANUAL">MANUAL</option>
          <option value="AUTO">AUTO</option>
        </select>
      </label>
      <label>
        Direction
        <select value={filters.direction} onChange={(e) => set({ direction: e.target.value })}>
          <option value="ALL">All</option>
          <option value="LONG">LONG</option>
          <option value="SHORT">SHORT</option>
        </select>
      </label>
      <label>
        Ticker
        <input
          type="text"
          placeholder="Filter ticker"
          value={filters.ticker}
          onChange={(e) => set({ ticker: e.target.value })}
        />
      </label>
    </div>
  );
}
