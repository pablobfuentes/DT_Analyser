import { describe, it, expect } from 'vitest';
import {
  toggleExplorationFilter,
  removeExplorationFilter,
  resetExploration,
  parseGraphFiltersFromUrl,
  graphFiltersToQueryParams,
  isExplorationKey,
} from './graphFilters';

describe('exploration filter toggle', () => {
  it('adds filter on first click', () => {
    const next = toggleExplorationFilter({}, 'weekday', 'WED');
    expect(next.weekday).toBe('WED');
  });

  it('removes filter on same bucket click', () => {
    const next = toggleExplorationFilter({ weekday: 'WED' }, 'weekday', 'WED');
    expect(next.weekday).toBeUndefined();
  });

  it('replaces sibling bucket same dimension', () => {
    const next = toggleExplorationFilter({ weekday: 'WED' }, 'weekday', 'THU');
    expect(next.weekday).toBe('THU');
  });

  it('allows different dimensions to coexist', () => {
    const wed = toggleExplorationFilter({}, 'weekday', 'WED');
    const both = toggleExplorationFilter(wed, 'entry_15m', '09:30-09:45');
    expect(both.weekday).toBe('WED');
    expect(both.entry_15m).toBe('09:30-09:45');
  });
});

describe('reset exploration', () => {
  it('clears exploration only', () => {
    expect(resetExploration({ weekday: 'WED', entry_15m: '09:30-09:45' })).toEqual({});
  });
});

describe('remove exploration chip', () => {
  it('removes one dimension', () => {
    const next = removeExplorationFilter({ weekday: 'WED', entry_15m: '09:30-09:45' }, 'weekday');
    expect(next.weekday).toBeUndefined();
    expect(next.entry_15m).toBe('09:30-09:45');
  });
});

describe('URL serialization', () => {
  it('round trips exploration params', () => {
    const params = new URLSearchParams('weekday=WED&entry_15m=09:30-09:45&range=all');
    const parsed = parseGraphFiltersFromUrl(params);
    expect(parsed.exploration.weekday).toBe('WED');
    const back = graphFiltersToQueryParams(parsed);
    expect(back.weekday).toBe('WED');
    expect(back.entry_15m).toBe('09:30-09:45');
  });

  it('round trips market and price params', () => {
    const params = new URLSearchParams(
      'entry_price_bucket=5_10&gap_bucket=20_50&rvol_bucket=5_10&market_gap_bucket=lt_neg_1',
    );
    const parsed = parseGraphFiltersFromUrl(params);
    const back = graphFiltersToQueryParams(parsed);
    expect(back.entry_price_bucket).toBe('5_10');
    expect(back.gap_bucket).toBe('20_50');
    expect(back.rvol_bucket).toBe('5_10');
    expect(back.market_gap_bucket).toBe('lt_neg_1');
  });

  it('round trips pine_scope in URL', () => {
    const params = new URLSearchParams('pine_scope=HISTORICAL_REPLAY');
    const parsed = parseGraphFiltersFromUrl(params);
    expect(parsed.pineScope).toBe('HISTORICAL_REPLAY');
    const back = graphFiltersToQueryParams(parsed);
    expect(back.pine_scope).toBe('HISTORICAL_REPLAY');
  });

  it('ignores unknown exploration params', () => {
    const parsed = parseGraphFiltersFromUrl(new URLSearchParams('foo=bar&weekday=WED'));
    expect(parsed.exploration.weekday).toBe('WED');
    expect(parsed.exploration.foo).toBeUndefined();
  });

  it('reset exploration preserves global serialization', () => {
    const parsed = parseGraphFiltersFromUrl(
      new URLSearchParams('ticker=NCRA&direction=LONG&weekday=WED&account_id=1'),
    );
    const reset = { ...parsed, exploration: resetExploration(parsed.exploration) };
    const back = graphFiltersToQueryParams(reset);
    expect(back.ticker).toBe('NCRA');
    expect(back.direction).toBe('LONG');
    expect(back.account_id).toBe('1');
    expect(back.weekday).toBeUndefined();
  });
});

describe('exploration keys', () => {
  it('validates known keys', () => {
    expect(isExplorationKey('weekday')).toBe(true);
    expect(isExplorationKey('invalid')).toBe(false);
  });
});

describe('session section keys', () => {
  it('default open sections include TIME', () => {
    const DEFAULT_OPEN = new Set(['TIME', 'TRADE', 'INSTRUMENT', 'SOURCE', 'BEHAVIOR', 'OUTCOMES']);
    expect(DEFAULT_OPEN.has('TIME')).toBe(true);
    expect(DEFAULT_OPEN.has('MARKET')).toBe(false);
  });
});
