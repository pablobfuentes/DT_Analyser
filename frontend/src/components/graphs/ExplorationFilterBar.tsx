import { EXPLORATION_LABELS } from '../../types/reports';

interface Props {
  filters: Record<string, string>;
  matchingCount: number;
  bucketLabels: Record<string, string>;
  onRemove: (dimension: string) => void;
  onReset: () => void;
}

export function ExplorationFilterBar({ filters, matchingCount, bucketLabels, onRemove, onReset }: Props) {
  const entries = Object.entries(filters);

  return (
    <div className="exploration-bar">
      <div className="exploration-bar-inner">
        <span className="exploration-label">Active Exploration Filters</span>
        {entries.length === 0 ? (
          <span className="text-secondary">Click chart buckets to drill down</span>
        ) : (
          entries.map(([dim, value]) => (
            <button
              key={dim}
              type="button"
              className="filter-chip"
              onClick={() => onRemove(dim)}
              title="Remove filter"
            >
              {bucketLabels[`${dim}:${value}`] || EXPLORATION_LABELS[dim] || dim}: {bucketLabels[`${dim}:${value}`] || value} ×
            </button>
          ))
        )}
        <span className="matching-count">{matchingCount} matching trades</span>
        {entries.length > 0 && (
          <button type="button" className="btn-secondary" onClick={onReset}>
            Reset Exploration
          </button>
        )}
      </div>
    </div>
  );
}
