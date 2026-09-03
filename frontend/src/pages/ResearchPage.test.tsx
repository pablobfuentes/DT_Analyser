import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ResearchPage } from './ResearchPage';

vi.mock('../api/client', () => ({
  api: {
    getAccounts: vi.fn().mockResolvedValue([]),
    listResearchViews: vi.fn().mockResolvedValue({ items: [] }),
    researchCompare: vi.fn(),
    researchScatter: vi.fn(),
    researchHeatmap: vi.fn(),
    researchRolling: vi.fn(),
    researchDistribution: vi.fn(),
    researchRobustness: vi.fn(),
    researchMultifactor: vi.fn(),
    saveResearchView: vi.fn(),
    createCandidateRule: vi.fn(),
    starPattern: vi.fn(),
    getResearchView: vi.fn(),
  },
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <ResearchPage />
    </MemoryRouter>,
  );
}

describe('ResearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the Research Lab route chrome', () => {
    renderPage();
    expect(screen.getByText('Research Lab')).toBeTruthy();
    expect(screen.getByText(/Exploratory comparison only/)).toBeTruthy();
    expect(screen.getByText(/Exploring many combinations/)).toBeTruthy();
  });

  it('defaults to KNOWN BY ENTRY (PRE_ENTRY_ONLY)', () => {
    renderPage();
    const mode = screen.getByDisplayValue('KNOWN BY ENTRY') as HTMLSelectElement;
    expect(mode.value).toBe('PRE_ENTRY_ONLY');
  });

  it('shows retrospective warning when switching mode', () => {
    renderPage();
    const mode = screen.getByDisplayValue('KNOWN BY ENTRY');
    fireEvent.change(mode, { target: { value: 'ALL_FEATURES' } });
    expect(screen.getByText(/only known after entry/)).toBeTruthy();
  });

  it('exposes cohort builders, clone, and swap', () => {
    renderPage();
    expect(screen.getByDisplayValue('Cohort A')).toBeTruthy();
    expect(screen.getByDisplayValue('Cohort B')).toBeTruthy();
    expect(screen.getByText('Clone A → B')).toBeTruthy();
    expect(screen.getByText('Swap A / B')).toBeTruthy();
    expect(screen.getByText('Force A/B Exclusive')).toBeTruthy();
  });

  it('clones A filters into B', () => {
    renderPage();
    const addButtons = screen.getAllByText('Add');
    fireEvent.click(addButtons[0]);
    fireEvent.click(screen.getByText('Clone A → B'));
    const chips = screen.getAllByText(/Setup Quality: A\+/);
    expect(chips.length).toBeGreaterThanOrEqual(2);
  });

  it('has visual research tabs and save actions', () => {
    renderPage();
    expect(screen.getByText('scatter')).toBeTruthy();
    expect(screen.getByText('heatmap')).toBeTruthy();
    expect(screen.getByText('rolling')).toBeTruthy();
    expect(screen.getByText('distribution')).toBeTruthy();
    expect(screen.getByText('Save View')).toBeTruthy();
    expect(screen.getByText('Create Candidate Rule')).toBeTruthy();
    expect(screen.getByText('Start Forward Testing')).toBeTruthy();
    expect(screen.getByText('★ Candidate Pattern')).toBeTruthy();
  });
});
