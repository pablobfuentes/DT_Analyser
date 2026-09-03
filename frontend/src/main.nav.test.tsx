import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, NavLink, Route, Routes } from 'react-router-dom';
import { ResearchPage } from './pages/ResearchPage';
import { vi } from 'vitest';

vi.mock('./api/client', () => ({
  api: {
    getAccounts: vi.fn().mockResolvedValue([]),
    listResearchViews: vi.fn().mockResolvedValue({ items: [] }),
  },
}));

function NavItem({ to, children }: { to: string; children: string }) {
  return <NavLink to={to}>{children}</NavLink>;
}

describe('primary navigation includes Research', () => {
  it('exposes Dashboard, Graphs, Trades, Signals, Exit Analyzer, Research, Workflow', () => {
    render(
      <MemoryRouter initialEntries={['/research']}>
        <nav>
          <NavItem to="/">Dashboard</NavItem>
          <NavItem to="/graphs">Graphs</NavItem>
          <NavItem to="/trades">Trades</NavItem>
          <NavItem to="/signals">Signals</NavItem>
          <NavItem to="/exit-analysis">Exit Analyzer</NavItem>
          <NavItem to="/research">Research</NavItem>
          <NavItem to="/workflow">Workflow</NavItem>
        </nav>
        <Routes>
          <Route path="/research" element={<ResearchPage />} />
        </Routes>
      </MemoryRouter>,
    );
    expect(screen.getByRole('link', { name: 'Research' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Workflow' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Graphs' })).toBeTruthy();
    expect(screen.getByRole('link', { name: 'Exit Analyzer' })).toBeTruthy();
    expect(screen.getByText('Research Lab')).toBeTruthy();
  });
});
