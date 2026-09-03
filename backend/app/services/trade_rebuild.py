"""Rebuild normalized trades from persisted executions."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.db.models.account import Account
from app.db.models.execution import Execution
from app.db.models.import_batch import ImportBatch
from app.db.models.import_error import ImportError
from app.db.models.trade import Trade
from app.db.models.trade_execution import TradeExecution
from app.importers.base import NormalizedExecution
from app.services.deduplication import execution_fingerprint, trade_exists, trade_fingerprint
from app.services.trade_reconstruction import ReconstructedTrade, TradeReconstructor, reconstructed_to_normalized
from app.utils.timezones import holding_seconds

logger = logging.getLogger(__name__)


@dataclass
class RebuildSummary:
    account_id: int
    account_name: str
    executions_examined: int = 0
    trades_removed: int = 0
    trades_created: int = 0
    long_trades: int = 0
    short_trades: int = 0
    open_positions: int = 0
    flips_handled: int = 0
    errors: int = 0
    reconstruction_errors: list[dict] = field(default_factory=list)
    reconstruction_warnings: list[dict] = field(default_factory=list)
    tickers: list[str] = field(default_factory=list)
    ticker_details: list[dict] = field(default_factory=list)
    dry_run: bool = False

    def format_report(self) -> str:
        lines = [
            f"Account: {self.account_name} (id={self.account_id})",
            f"Executions examined: {self.executions_examined}",
            f"Existing trades removed/rebuilt: {self.trades_removed}",
            f"Trades created: {self.trades_created}",
            f"LONG trades: {self.long_trades}",
            f"SHORT trades: {self.short_trades}",
            f"Open positions: {self.open_positions}",
            f"Position flips handled: {self.flips_handled}",
            f"Errors: {self.errors}",
        ]
        if self.ticker_details:
            lines.append("")
            lines.append("Per-ticker:")
            for d in self.ticker_details:
                lines.append(
                    f"  {d['ticker']}: execs={d['executions']} "
                    f"old_trades={d['old_trades']} new_trades={d['new_trades']} "
                    f"flips={d['flips']} open={d['open_position']}"
                )
        if self.dry_run:
            lines.append("")
            lines.append("DRY RUN — no changes written")
        return "\n".join(lines)


class TradeRebuildService:
    def __init__(self, db: Session):
        self.db = db
        self.reconstructor = TradeReconstructor()

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def rebuild(
        self,
        account_id: int,
        tickers: list[str] | None = None,
        dry_run: bool = False,
        commit: bool = True,
    ) -> RebuildSummary:
        account = self.db.get(Account, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")
        source_type = account.source
        account_name = account.name

        summary = RebuildSummary(
            account_id=account_id,
            account_name=account_name,
            dry_run=dry_run,
        )

        exec_query = self.db.query(Execution).filter(Execution.account_id == account_id)
        if tickers:
            exec_query = exec_query.filter(Execution.ticker.in_(tickers))
        all_execs = exec_query.order_by(Execution.execution_time_utc, Execution.id).all()
        summary.executions_examined = len(all_execs)

        if tickers:
            summary.tickers = sorted(set(tickers))
        else:
            summary.tickers = sorted({e.ticker for e in all_execs})

        old_trade_query = self.db.query(Trade).filter(Trade.account_id == account_id)
        if tickers:
            old_trade_query = old_trade_query.filter(Trade.ticker.in_(tickers))
        old_trades = old_trade_query.all()
        old_trade_count = len(old_trades)

        by_ticker_execs: dict[str, list[Execution]] = {}
        for ex in all_execs:
            by_ticker_execs.setdefault(ex.ticker, []).append(ex)

        new_trades_all: list[ReconstructedTrade] = []
        all_errors: list[dict] = []
        all_warnings: list[dict] = []
        total_flips = 0
        sell_first_tickers: set[str] = set()

        for ticker in summary.tickers:
            ticker_execs = by_ticker_execs.get(ticker, [])
            normalized = [self._to_normalized(e) for e in ticker_execs]
            recon = self.reconstructor.reconstruct(normalized)
            new_trades_all.extend(recon.trades)
            all_errors.extend(recon.errors)
            all_warnings.extend(recon.warnings)
            total_flips += recon.flips_handled
            if any(w.get("error_type") == "UNKNOWN_OPENING_POSITION" for w in recon.warnings):
                sell_first_tickers.add(ticker)

            old_for_ticker = [t for t in old_trades if t.ticker == ticker]
            open_pos = Decimal("0")
            for ex in normalized:
                if ex.side in ("BUY", "BUY_TO_COVER"):
                    open_pos += ex.quantity
                else:
                    open_pos -= ex.quantity

            summary.ticker_details.append(
                {
                    "ticker": ticker,
                    "executions": len(ticker_execs),
                    "old_trades": len(old_for_ticker),
                    "new_trades": len(recon.trades),
                    "old_errors": 0,
                    "new_errors": len(recon.errors),
                    "flips": recon.flips_handled,
                    "open_position": str(open_pos),
                }
            )

        summary.trades_removed = old_trade_count
        summary.trades_created = len(new_trades_all)
        summary.long_trades = sum(1 for t in new_trades_all if t.direction == "LONG")
        summary.short_trades = sum(1 for t in new_trades_all if t.direction == "SHORT")
        summary.open_positions = sum(1 for t in new_trades_all if t.status == "OPEN")
        summary.flips_handled = total_flips
        summary.errors = len(all_errors)
        summary.reconstruction_errors = all_errors
        summary.reconstruction_warnings = all_warnings

        if dry_run:
            return summary

        exec_id_by_fp = {e.execution_fingerprint: e.id for e in all_execs}

        old_trade_ids = [t.id for t in old_trades]
        if old_trade_ids:
            self.db.query(TradeExecution).filter(TradeExecution.trade_id.in_(old_trade_ids)).delete(
                synchronize_session="fetch"
            )
            for t in old_trades:
                self.db.delete(t)
            self.db.flush()
            for inst in list(self.db.identity_map.values()):
                if isinstance(inst, (Trade, TradeExecution)):
                    self.db.expunge(inst)

        for rt in new_trades_all:
            self._persist_trade(account_id, source_type, rt, exec_id_by_fp)

        rebuilt_tickers = list(summary.tickers)
        if not all_errors:
            self._resolve_errors(
                account_id,
                error_types=["TradeReconstructionError"],
                tickers=tickers,
            )
        resolved_opening = [t for t in rebuilt_tickers if t not in sell_first_tickers]
        if resolved_opening:
            self._resolve_errors(
                account_id,
                error_types=["UNKNOWN_OPENING_POSITION"],
                tickers=resolved_opening,
            )
        if commit:
            self.db.commit()
        return summary

    def _to_normalized(self, e: Execution) -> NormalizedExecution:
        return NormalizedExecution(
            ticker=e.ticker,
            side=e.side,
            execution_time_utc=self._ensure_utc(e.execution_time_utc),
            execution_time_original=e.execution_time_original,
            timezone_original=e.timezone_original,
            quantity=e.quantity,
            price=e.price,
            fees=e.fees,
            order_id=e.order_id,
            external_execution_id=e.external_execution_id,
            raw_row=json.loads(e.raw_row_json) if e.raw_row_json else {},
            row_number=e.id,
        )

    def _persist_trade(
        self,
        account_id: int,
        source_type: str,
        rt: ReconstructedTrade,
        exec_id_by_fp: dict[str, int],
    ):
        nt = reconstructed_to_normalized(rt)
        fp = trade_fingerprint(account_id, source_type, nt)
        if trade_exists(self.db, account_id, fp):
            return

        hold = None
        if rt.exit_time_utc:
            hold = holding_seconds(rt.entry_time_utc, rt.exit_time_utc)

        from app.utils.money import calculate_net_pnl

        net = None
        if rt.gross_pnl is not None:
            net = calculate_net_pnl(rt.gross_pnl, rt.fees)

        raw_rows = [a.execution.raw_row for a in rt.allocations]

        db_trade = Trade(
            account_id=account_id,
            source_type=source_type,
            trade_fingerprint=fp,
            ticker=rt.ticker,
            direction=rt.direction,
            entry_time_utc=rt.entry_time_utc,
            exit_time_utc=rt.exit_time_utc,
            avg_entry_price=rt.avg_entry_price,
            avg_exit_price=rt.avg_exit_price,
            quantity=rt.quantity,
            gross_pnl=rt.gross_pnl,
            fees=rt.fees,
            net_pnl=net,
            holding_seconds=hold,
            status=rt.status,
            raw_row_json=json.dumps(raw_rows),
        )
        self.db.add(db_trade)
        self.db.flush()

        for alloc in rt.allocations:
            execution_id = alloc.execution.row_number
            if not execution_id:
                fp_ex = execution_fingerprint(account_id, alloc.execution)
                execution_id = exec_id_by_fp.get(fp_ex, 0)
            if not execution_id:
                continue
            self.db.add(
                TradeExecution(
                    trade_id=db_trade.id,
                    execution_id=execution_id,
                    role=alloc.role,
                    allocated_quantity=alloc.quantity,
                )
            )

    def _error_ticker(self, err: ImportError) -> str | None:
        if err.message and err.message.startswith("[") and "]" in err.message:
            return err.message[1 : err.message.index("]")].strip().upper()
        if not err.raw_row_json:
            return None
        try:
            raw = json.loads(err.raw_row_json)
        except json.JSONDecodeError:
            return None
        from app.importers.normalization import normalize_ticker

        for key in ("ticker", "Symbol", "symbol", "Ticker"):
            if raw.get(key):
                return normalize_ticker(str(raw[key]))
        return None

    def _resolve_errors(
        self,
        account_id: int,
        error_types: list[str],
        tickers: list[str] | None,
    ):
        """Resolve only the given reconstruction-related error types.

        Parser errors (malformed CSV, missing field, timezone) are never passed here.
        Ticker-scoped rebuilds only resolve errors that belong to those tickers.
        """
        now = datetime.now(timezone.utc)
        ticker_set = {t.upper() for t in tickers} if tickers else None
        errors = (
            self.db.query(ImportError)
            .join(ImportBatch, ImportError.import_batch_id == ImportBatch.id)
            .filter(
                ImportBatch.account_id == account_id,
                ImportError.error_type.in_(error_types),
                ImportError.resolved_at.is_(None),
            )
            .all()
        )
        for err in errors:
            if ticker_set is not None:
                err_ticker = self._error_ticker(err)
                if err_ticker is None or err_ticker not in ticker_set:
                    continue
            err.resolved_at = now
