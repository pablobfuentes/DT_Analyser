import { TradeTable } from '../components/TradeTable';
import { MonthlyDaySummary } from '../components/MonthlyDaySummary';

export function TradesPage() {
  return (
    <div>
      <h2>Trades</h2>
      <MonthlyDaySummary />
      <TradeTable />
    </div>
  );
}
