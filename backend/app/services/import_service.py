import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models.account import Account
from app.db.models.execution import Execution
from app.db.models.import_batch import ImportBatch
from app.db.models.import_error import ImportError
from app.db.models.trade import Trade
from app.importers.base import NormalizedExecution, ParseResult
from app.importers.base_parser import read_csv
from app.importers.detector import get_parser
from app.importers.exceptions import TimezoneRequiredError
from app.services.deduplication import (
    execution_exists,
    execution_fingerprint,
    trade_exists,
    trade_fingerprint,
)
from app.services.trade_rebuild import TradeRebuildService
from app.utils.hashing import json_dumps, sha256_file
from app.utils.money import calculate_gross_pnl, pnl_mismatch, to_decimal
from app.utils.timezones import holding_seconds

logger = logging.getLogger(__name__)


class ImportService:
    def __init__(self, db: Session):
        self.db = db
        self.pnl_tolerance = to_decimal(settings.pnl_tolerance, Decimal("0.01"))

    @staticmethod
    def _ensure_utc(dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    def commit_import(
        self,
        file_path: Path,
        filename: str,
        account_id: int,
        parser_name: str,
        user_timezone: str | None = None,
    ) -> dict:
        account = self.db.get(Account, account_id)
        if not account:
            raise ValueError(f"Account {account_id} not found")

        parser = get_parser(parser_name)
        if not parser:
            raise ValueError(f"Parser {parser_name} not found")

        file_hash = sha256_file(file_path)
        df = read_csv(file_path)
        parse_result = parser.parse(df, user_timezone)

        if parse_result.timezone_status == "REQUIRES_USER_INPUT" and user_timezone is None:
            raise TimezoneRequiredError()

        batch = ImportBatch(
            filename=filename,
            file_hash=file_hash,
            source_type=parser.source_type,
            parser_name=parser.name,
            parser_version=parser.version,
            account_id=account_id,
            row_count_raw=parse_result.row_count,
            status="PROCESSING",
            metadata_json=json.dumps({"timezone": user_timezone}),
        )
        self.db.add(batch)
        self.db.flush()

        stats = {
            "import_batch_id": batch.id,
            "raw_rows": parse_result.row_count,
            "valid_rows": 0,
            "imported_executions": 0,
            "imported_trades": 0,
            "duplicate_executions": 0,
            "duplicate_trades": 0,
            "errors": 0,
        }

        try:
            if parse_result.trades:
                self._import_strategy_trades(batch, account_id, parser.source_type, parse_result, stats)
            else:
                self._import_manual_executions(batch, account_id, parser.source_type, parse_result, stats)

            for err in parse_result.errors:
                self._log_error(batch.id, err)
                stats["errors"] += 1

            batch.row_count_valid = stats["valid_rows"]
            batch.row_count_imported = stats["imported_executions"] + stats["imported_trades"]
            batch.row_count_duplicate = stats["duplicate_executions"] + stats["duplicate_trades"]
            batch.row_count_error = stats["errors"]
            batch.import_completed_at = datetime.now(timezone.utc)

            if stats["errors"] > 0 and (stats["imported_executions"] + stats["imported_trades"]) > 0:
                batch.status = "PARTIAL"
            elif stats["errors"] > 0:
                batch.status = "FAILED"
            else:
                batch.status = "SUCCESS"

            self.db.commit()
            logger.info(
                "Import batch %s completed: %s trades, %s executions, %s duplicates, %s errors",
                batch.id,
                stats["imported_trades"],
                stats["imported_executions"],
                stats["duplicate_executions"] + stats["duplicate_trades"],
                stats["errors"],
            )
        except Exception as e:
            self.db.rollback()
            logger.exception("Import failed for batch")
            raise

        return stats

    def _import_strategy_trades(
        self,
        batch: ImportBatch,
        account_id: int,
        source_type: str,
        result: ParseResult,
        stats: dict,
    ):
        for trade in result.trades:
            stats["valid_rows"] += 1
            fp = trade_fingerprint(account_id, source_type, trade)
            if trade_exists(self.db, account_id, fp):
                stats["duplicate_trades"] += 1
                continue

            gross = trade.gross_pnl
            if gross is None and trade.avg_exit_price is not None:
                gross = calculate_gross_pnl(
                    trade.direction, trade.avg_entry_price, trade.avg_exit_price, trade.quantity
                )

            mismatch = False
            if gross is not None and trade.source_reported_pnl is not None:
                mismatch = pnl_mismatch(gross, trade.source_reported_pnl, self.pnl_tolerance)

            hold = None
            if trade.exit_time_utc:
                hold = holding_seconds(trade.entry_time_utc, trade.exit_time_utc)

            db_trade = Trade(
                account_id=account_id,
                source_type=source_type,
                external_trade_id=trade.external_trade_id,
                trade_fingerprint=fp,
                ticker=trade.ticker,
                direction=trade.direction,
                entry_time_utc=trade.entry_time_utc,
                exit_time_utc=trade.exit_time_utc,
                avg_entry_price=trade.avg_entry_price,
                avg_exit_price=trade.avg_exit_price,
                quantity=trade.quantity,
                gross_pnl=gross,
                fees=trade.fees,
                net_pnl=trade.net_pnl,
                source_reported_pnl=trade.source_reported_pnl,
                pnl_mismatch_flag=mismatch,
                holding_seconds=hold,
                status=trade.status,
                raw_row_json=json_dumps(trade.raw_row),
            )
            self.db.add(db_trade)
            stats["imported_trades"] += 1

    def _import_manual_executions(
        self,
        batch: ImportBatch,
        account_id: int,
        source_type: str,
        result: ParseResult,
        stats: dict,
    ):
        new_executions: list[tuple[NormalizedExecution, Execution]] = []

        for ex in result.executions:
            stats["valid_rows"] += 1
            fp = execution_fingerprint(account_id, ex)
            if execution_exists(self.db, account_id, fp):
                stats["duplicate_executions"] += 1
                continue

            db_ex = Execution(
                account_id=account_id,
                import_batch_id=batch.id,
                external_execution_id=ex.external_execution_id,
                execution_fingerprint=fp,
                ticker=ex.ticker,
                side=ex.side,
                execution_time_utc=ex.execution_time_utc,
                execution_time_original=ex.execution_time_original,
                timezone_original=ex.timezone_original,
                quantity=ex.quantity,
                price=ex.price,
                fees=ex.fees,
                order_id=ex.order_id,
                raw_row_json=json_dumps(ex.raw_row),
            )
            self.db.add(db_ex)
            self.db.flush()
            new_executions.append((ex, db_ex))
            stats["imported_executions"] += 1

        if not new_executions:
            return

        tickers = {ex.ticker for ex, _ in new_executions}
        trades_before = (
            self.db.query(Trade)
            .filter(Trade.account_id == account_id, Trade.ticker.in_(tickers))
            .count()
        )
        rebuild = TradeRebuildService(self.db)
        summary = rebuild.rebuild(account_id, tickers=list(tickers), dry_run=False, commit=False)
        trades_after = (
            self.db.query(Trade)
            .filter(Trade.account_id == account_id, Trade.ticker.in_(tickers))
            .count()
        )
        stats["imported_trades"] += max(0, trades_after - trades_before)
        stats["errors"] += summary.errors
        for err in summary.reconstruction_errors:
            self._log_error(batch.id, err)
        for warn in summary.reconstruction_warnings:
            self._log_error(batch.id, warn)

    def _log_error(self, batch_id: int, err: dict):
        self.db.add(
            ImportError(
                import_batch_id=batch_id,
                row_number=err.get("row_number", 0),
                error_type=err.get("error_type", "ERROR"),
                message=err.get("message", "Unknown error"),
                raw_row_json=json_dumps(err.get("raw_row")) if err.get("raw_row") else None,
            )
        )
