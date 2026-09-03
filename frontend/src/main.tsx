import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter, NavLink, Route, Routes } from 'react-router-dom';
import { DashboardPage } from './pages/DashboardPage';
import { ImportPage } from './pages/ImportPage';
import { TradesPage } from './pages/TradesPage';
import { TradeDetailPage } from './pages/TradeDetailPage';
import { GraphsPage } from './pages/GraphsPage';
import { AccountsPage } from './pages/AccountsPage';
import { MarketDataPage } from './pages/MarketDataPage';
import { ExitAnalysisPage } from './pages/ExitAnalysisPage';
import { SignalsPage } from './pages/SignalsPage';
import { SignalDetailPage } from './pages/SignalDetailPage';
import { RiskCoveragePage } from './pages/RiskCoveragePage';
import { ResearchPage } from './pages/ResearchPage';
import { WorkflowPage } from './pages/WorkflowPage';
import { DailyReviewPage } from './pages/DailyReviewPage';
import { WeeklyReviewPage } from './pages/WeeklyReviewPage';
import { ReviewHistoryPage } from './pages/ReviewHistoryPage';
import { SettingsPage } from './pages/SettingsPage';
import { ApiStatusBanner } from './components/ApiStatusBanner';
import './index.css';

function NavItem({ to, children }: { to: string; children: React.ReactNode }) {
  return (
    <NavLink to={to} className={({ isActive }) => (isActive ? 'active' : undefined)} end={to === '/'}>
      {children}
    </NavLink>
  );
}

function App() {
  return (
    <BrowserRouter>
      <ApiStatusBanner />
      <div className="app-shell">
        <nav className="app-sidebar">
          <div className="brand">DT Analyser</div>
          <NavItem to="/">Dashboard</NavItem>
          <NavItem to="/graphs">Graphs</NavItem>
          <NavItem to="/trades">Trades</NavItem>
          <NavItem to="/signals">Signals</NavItem>
          <NavItem to="/exit-analysis">Exit Analyzer</NavItem>
          <NavItem to="/research">Research</NavItem>
          <NavItem to="/workflow">Workflow</NavItem>
          <NavItem to="/review/daily">Review</NavItem>
          <NavItem to="/risk">Risk</NavItem>
          <NavItem to="/import">Import</NavItem>
          <NavItem to="/accounts">Accounts</NavItem>
          <NavItem to="/market-data">Market Data</NavItem>
          <NavItem to="/settings">Settings</NavItem>
        </nav>
        <main className="app-main">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/trades" element={<TradesPage />} />
            <Route path="/trades/:id" element={<TradeDetailPage />} />
            <Route path="/graphs" element={<GraphsPage />} />
            <Route path="/exit-analysis" element={<ExitAnalysisPage />} />
            <Route path="/research" element={<ResearchPage />} />
            <Route path="/workflow" element={<WorkflowPage />} />
            <Route path="/review/daily" element={<DailyReviewPage />} />
            <Route path="/review/weekly" element={<WeeklyReviewPage />} />
            <Route path="/reviews" element={<ReviewHistoryPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/accounts" element={<AccountsPage />} />
            <Route path="/signals" element={<SignalsPage />} />
            <Route path="/signals/:id" element={<SignalDetailPage />} />
            <Route path="/risk" element={<RiskCoveragePage />} />
            <Route path="/market-data" element={<MarketDataPage />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
