import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { SettingsPage } from './SettingsPage';

vi.mock('../api/workflow', () => ({
  settingsApi: {
    get: vi.fn().mockResolvedValue({
      secrets_note: 'API keys stay in environment variables and are never shown here.',
      paths: { inbox: 'C:/data/inbox', backups: 'C:/data/backups' },
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
    expect(screen.getByText(/C:\/data\/inbox/)).toBeTruthy();
    expect(screen.getByText(/never shown here/i)).toBeTruthy();
    expect(screen.queryByText(/alpaca/i)).toBeNull();
  });
});
