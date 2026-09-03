import { describe, it, expect } from 'vitest';
import {
  cloneFilters,
  isPreEntryFilter,
  isRetrospectiveFilters,
  PRE_ENTRY_FILTER_KEYS,
  swapCohorts,
} from './researchFilters';

describe('pre-entry filter keys', () => {
  it('allows setup quality and signal RVOL', () => {
    expect(isPreEntryFilter('setup_quality')).toBe(true);
    expect(isPreEntryFilter('signal_rvol_bucket')).toBe(true);
    expect(isPreEntryFilter('prior_rvol_bucket')).toBe(true);
  });

  it('rejects MFE, MAE, outcomes, and full-day RVOL', () => {
    expect(isPreEntryFilter('mfe_r_bucket')).toBe(false);
    expect(isPreEntryFilter('mae_r_bucket')).toBe(false);
    expect(isPreEntryFilter('r_outcome_bucket')).toBe(false);
    expect(isPreEntryFilter('rvol_bucket')).toBe(false);
    expect(isPreEntryFilter('outcome')).toBe(false);
  });

  it('covers weekday and entry windows', () => {
    expect(PRE_ENTRY_FILTER_KEYS.has('weekday')).toBe(true);
    expect(PRE_ENTRY_FILTER_KEYS.has('entry_15m')).toBe(true);
  });

  it('detects retrospective cohort filters', () => {
    expect(isRetrospectiveFilters({ setup_quality: 'A+' })).toBe(false);
    expect(isRetrospectiveFilters({ mfe_r_bucket: '1_1_5' })).toBe(true);
  });
});

describe('clone and swap', () => {
  it('clones without sharing the object', () => {
    const a = { setup_quality: 'A+' };
    const b = cloneFilters(a);
    b.setup_quality = 'A';
    expect(a.setup_quality).toBe('A+');
  });

  it('swaps cohorts', () => {
    const [newA, newB] = swapCohorts({ setup_quality: 'A+' }, { setup_quality: 'A' });
    expect(newA.setup_quality).toBe('A');
    expect(newB.setup_quality).toBe('A+');
  });
});
