import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { WorkflowPage } from './WorkflowPage';

vi.mock('../api/workflow', () => ({
  workflowApi: {
    status: vi.fn().mockResolvedValue({
      date: '2026-09-02',
      badge: 'PARTIAL',
      trades: 2,
      review_status: 'NOT_STARTED',
      no_trading: false,
      inputs: {
        ORDER_HISTORY: { policy: 'REQUIRED', state: 'IMPORTED' },
        AUTO_STRATEGY_TESTER: { policy: 'OPTIONAL', state: 'NOT_EXPECTED' },
      },
      coverage: { market_pct: 100, risk_pct: '90', signal_pct: '80', excursion_pct: 70 },
      attention: [{ message: '1 file requires timezone' }],
    }),
    health: vi.fn().mockResolvedValue({
      watcher: 'Running',
      worker: 'Running',
      automation_ownership: 'OWNER',
      pending_jobs: 0,
      failed_jobs: 0,
      inbox: '/data/inbox',
      scheduler_note: 'In-process only',
    }),
    runs: vi.fn().mockResolvedValue({
      items: [{ id: 1, run_type: 'INBOX_PROCESSING', status: 'SUCCESS', created_at: '2026-09-02T20:00:00', ny_date: '2026-09-02' }],
    }),
    run: vi.fn().mockResolvedValue({
      id: 1,
      run_type: 'INBOX_PROCESSING',
      status: 'SUCCESS',
      steps: [{ step_key: 'TRADE_IMPORT', status: 'SUCCESS', records_created: 2, error_count: 0 }],
    }),
    processInbox: vi.fn().mockResolvedValue({ job_id: 9 }),
    finalize: vi.fn().mockResolvedValue({ job_id: 10 }),
    noTrade: vi.fn().mockResolvedValue({ no_trading: true, badge: 'NO_TRADES' }),
  },
  backupsApi: {
    list: vi.fn().mockResolvedValue({ items: [] }),
    create: vi.fn().mockResolvedValue({ job_id: 11 }),
  },
}));

describe('Workflow page', () => {
  it('shows today status, inputs, process inbox, and attention', async () => {
    render(
      <MemoryRouter initialEntries={['/workflow?date=2026-09-02']}>
        <Routes>
          <Route path="/workflow" element={<WorkflowPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/TODAY/)).toBeTruthy();
    expect(screen.getByText('Process Inbox')).toBeTruthy();
    expect(screen.getByText('Finalize Today')).toBeTruthy();
    expect(await screen.findByText('ORDER HISTORY')).toBeTruthy();
    expect(await screen.findByText('1 file requires timezone')).toBeTruthy();
    expect(await screen.findByText(/Automation Ownership:\s*OWNER/)).toBeTruthy();
    fireEvent.click(screen.getByText('Process Inbox'));
    expect(await screen.findByText(/Inbox queued/)).toBeTruthy();
  });
});
