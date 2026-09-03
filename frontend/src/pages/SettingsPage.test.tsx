import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SettingsPage } from './SettingsPage';

vi.mock('../api/workflow', () => ({
  settingsApi: {
    get: vi.fn().mockResolvedValue({
      secrets_note: 'API keys stay in environment variables and are never shown here.',
      paths: {
        data_dir: 'C:/data',
        database: 'C:/data/trader_analyzer.db',
        inbox: 'C:/data/inbox',
        backups: 'C:/data/backups',
        archive: 'C:/data/archive',
        screenshots: 'C:/data/screenshots',
        logs: 'C:/data/logs',
        quarantine: 'C:/data/quarantine',
      },
      preferences: {
        auto_process_inbox: true,
        expected_inputs: { ORDER_HISTORY: 'REQUIRED', AUTO_STRATEGY_TESTER: 'OPTIONAL' },
        backup_retain_daily: 30,
        backup_retain_weekly: 12,
        eod_finalize_time: '20:15',
      },
    }),
    patch: vi.fn(),
  },
}));

describe('Settings', () => {
  it('shows paths and does not render API secrets', async () => {
    render(<SettingsPage />);
    expect(await screen.findByText(/Data locations/)).toBeTruthy();
    expect(screen.getByDisplayValue('C:/data')).toBeTruthy();
    expect(screen.getByLabelText(/Trading data directory/i)).toBeTruthy();
    expect(screen.getByText(/never shown here/i)).toBeTruthy();
    expect(screen.queryByText(/alpaca/i)).toBeNull();
  });
});
