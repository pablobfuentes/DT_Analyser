import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MetricCard } from '../components/dashboard/MetricCard';
import { formatMoney, formatPercent, formatProfitFactor, formatR, formatCoverage, pnlClass } from './money';
import { formatDuration } from './duration';

describe('formatMoney', () => {
  it('formats positive with sign', () => {
    expect(formatMoney('1284.32', true)).toBe('+$1,284.32');
  });
  it('returns dash for null', () => {
    expect(formatMoney(null)).toBe('—');
  });
});

describe('pnlClass', () => {
  it('classifies profit and loss', () => {
    expect(pnlClass('10')).toBe('profit');
    expect(pnlClass('-5')).toBe('loss');
    expect(pnlClass('0')).toBe('neutral');
  });
});

describe('formatDuration', () => {
  it('formats minutes and seconds', () => {
    expect(formatDuration(318)).toBe('5m 18s');
  });
});

describe('MetricCard', () => {
  it('renders label and value', () => {
    render(<MetricCard label="Net P&L" value="+$100.00" />);
    expect(screen.getByText('Net P&L')).toBeTruthy();
    expect(screen.getByText('+$100.00')).toBeTruthy();
  });
});

describe('formatPercent', () => {
  it('formats win rate', () => {
    expect(formatPercent('67.2')).toBe('67.2%');
  });
});

describe('formatR', () => {
  it('formats positive and negative R', () => {
    expect(formatR('1.73642857')).toBe('+1.74R');
    expect(formatR('-1')).toBe('-1.00R');
  });
  it('returns dash for missing R', () => {
    expect(formatR(null)).toBe('—');
  });
});

describe('formatProfitFactor', () => {
  it('shows infinity for no losses', () => {
    expect(formatProfitFactor(null, 'NO_LOSSES')).toBe('∞');
  });
  it('formats finite PF', () => {
    expect(formatProfitFactor('2.14', 'FINITE')).toBe('2.14');
  });
});

describe('formatCoverage', () => {
  it('shows count and percent', () => {
    expect(formatCoverage(38, 4)).toBe('38 / 42 (90.5%)');
  });
});

describe('empty dashboard state', () => {
  it('formatMoney handles zero', () => {
    expect(formatMoney('0', true)).toBe('$0.00');
  });
});
