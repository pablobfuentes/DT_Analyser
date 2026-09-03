import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { DailyReviewPage } from './DailyReviewPage';

vi.mock('../api/workflow', () => ({
  reviewsApi: {
    daily: vi.fn().mockResolvedValue({
      date: '2026-09-02',
      status: 'NOT_STARTED',
      prompt_labels: ['What worked today?'],
      prompt_fields: {},
      live_metrics: { summary: { trades: 3, net_pnl: '100', win_rate: '50' }, average_r: '0.4' },
      trades: [{ id: 1, ticker: 'NCRA', direction: 'LONG', net_pnl: '10', journal_status: 'not_reviewed' }],
    }),
    patchDaily: vi.fn(),
    completeDaily: vi.fn(),
  },
}));

describe('Daily review', () => {
  it('renders metrics and complete action', async () => {
    render(
      <MemoryRouter initialEntries={['/review/daily?date=2026-09-02']}>
        <Routes>
          <Route path="/review/daily" element={<DailyReviewPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Daily Review/)).toBeTruthy();
    expect(screen.getByText('Complete Review')).toBeTruthy();
    expect(screen.getByText('NCRA')).toBeTruthy();
  });
});
