import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { api, Trade } from '../api/client';
import { journalApi } from '../api/workflow';
import { MissingRiskModal } from './MissingRiskModal';
import { formatDuration } from '../utils/duration';
import { formatMoney, formatR, pnlClass } from '../utils/money';

export function TradeTable() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [trades, setTrades] = useState<Trade[]>([]);
  const [total, setTotal] = useState(0);
  const [showRiskModal, setShowRiskModal] = useState(false);
  const [journalMap, setJournalMap] = useState<Record<string, boolean>>({});

  const ticker = searchParams.get('ticker') || '';
  const source = searchParams.get('source') || '';
  const direction = searchParams.get('direction') || '';
  const date = searchParams.get('date') || '';
  const hasRisk = searchParams.get('has_risk') || '';
  const rMin = searchParams.get('r_min') || '';
  const rMax = searchParams.get('r_max') || '';
  const sortAsc = searchParams.get('sort') === 'asc';

  const setFilter = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next, { replace: true });
  };

  useEffect(() => {
    const params: Record<string, string> = { page: '1', page_size: '200' };
    if (ticker) params.ticker = ticker;
    if (source) params.source = source;
    if (direction) params.direction = direction;
    if (date) params.date = date;
    if (hasRisk) params.has_risk = hasRisk;
    if (rMin) params.r_min = rMin;
    if (rMax) params.r_max = rMax;
    api.getTrades(params).then((res) => {
      const sorted = [...res.items].sort((a, b) => {
        const ta = a.exit_time_utc || a.entry_time_utc;
        const tb = b.exit_time_utc || b.entry_time_utc;
        const cmp = ta.localeCompare(tb);
        return sortAsc ? cmp : -cmp;
      });
      setTrades(sorted);
      setTotal(res.total);
      if (sorted.length) {
        journalApi.tradeStatus(sorted.map((t) => t.id)).then((m) => setJournalMap(m));
      }
    });
  }, [ticker, source, direction, date, hasRisk, rMin, rMax, sortAsc]);

  return (
    <div>
      <div className="filters-bar">
        <label>
          Ticker
          <input placeholder="Filter ticker" value={ticker} onChange={(e) => setFilter('ticker', e.target.value)} />
        </label>
        <label>
          Source
          <select value={source} onChange={(e) => setFilter('source', e.target.value)}>
            <option value="">All sources</option>
            <option value="TRADINGVIEW_MANUAL">Manual</option>
            <option value="TRADINGVIEW_AUTO">Strategy Tester</option>
          </select>
        </label>
        <label>
          Direction
          <select value={direction} onChange={(e) => setFilter('direction', e.target.value)}>
            <option value="">All</option>
            <option value="LONG">LONG</option>
            <option value="SHORT">SHORT</option>
          </select>
        </label>
        <label>
          Risk Data
          <select value={hasRisk} onChange={(e) => setFilter('has_risk', e.target.value)}>
            <option value="">All</option>
            <option value="yes">Has Risk</option>
            <option value="no">Missing Risk</option>
          </select>
        </label>
        <label>
          R min
          <input value={rMin} onChange={(e) => setFilter('r_min', e.target.value)} placeholder="e.g. -1" style={{ width: 60 }} />
        </label>
        <label>
          R max
          <input value={rMax} onChange={(e) => setFilter('r_max', e.target.value)} placeholder="e.g. 2" style={{ width: 60 }} />
        </label>
        <label>
          Date (NY)
          <input type="date" value={date} onChange={(e) => setFilter('date', e.target.value)} />
        </label>
        <button type="button" onClick={() => setShowRiskModal(true)}>Missing Risk</button>
        <button onClick={() => setFilter('sort', sortAsc ? '' : 'asc')}>Sort {sortAsc ? '↑' : '↓'}</button>
        <span style={{ alignSelf: 'center' }}>{total} trades</span>
      </div>
      {showRiskModal && (
        <MissingRiskModal
          trades={trades}
          onClose={() => setShowRiskModal(false)}
          onSaved={() => {
            setFilter('has_risk', 'no');
            setShowRiskModal(false);
          }}
        />
      )}
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Date</th>
              <th>Ticker</th>
              <th>Source</th>
              <th>Dir</th>
              <th>Entry</th>
              <th>Exit</th>
              <th>Qty</th>
              <th>Net P&L</th>
              <th>Risk</th>
              <th>R</th>
              <th>Hold</th>
              <th>Journal</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id}>
                <td>{(t.exit_time_utc || t.entry_time_utc).slice(0, 10)}</td>
                <td><Link to={`/trades/${t.id}`}>{t.ticker}</Link></td>
                <td>{t.source_type.replace('TRADINGVIEW_', '')}</td>
                <td>{t.direction}</td>
                <td>{t.avg_entry_price}</td>
                <td>{t.avg_exit_price ?? '—'}</td>
                <td>{t.quantity}</td>
                <td className={pnlClass(t.net_pnl || t.gross_pnl)}>{formatMoney(t.net_pnl || t.gross_pnl, true)}</td>
                <td>{t.initial_risk_amount ? formatMoney(t.initial_risk_amount) : '—'}</td>
                <td>{t.r_multiple ? formatR(t.r_multiple) : '—'}</td>
                <td>{formatDuration(t.holding_seconds)}</td>
                <td>
                  <Link to={`/trades/${t.id}`}>{journalMap[String(t.id)] ? '✓' : '○'}</Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
