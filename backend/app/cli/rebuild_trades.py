"""Rebuild normalized trades from persisted executions."""

import argparse
import sys

from app.db.session import SessionLocal
from app.services.trade_rebuild import TradeRebuildService


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild trades from executions")
    parser.add_argument("--account-id", type=int, help="Account ID to rebuild")
    parser.add_argument("--ticker", action="append", dest="tickers", help="Limit to ticker(s)")
    parser.add_argument("--all", action="store_true", help="Rebuild all accounts")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    args = parser.parse_args(argv)

    db = SessionLocal()
    try:
        service = TradeRebuildService(db)
        account_ids: list[int] = []

        if args.all:
            from app.db.models.account import Account

            account_ids = [a.id for a in db.query(Account).all()]
        elif args.account_id:
            account_ids = [args.account_id]
        else:
            parser.error("Specify --account-id or --all")

        for account_id in account_ids:
            summary = service.rebuild(
                account_id=account_id,
                tickers=args.tickers,
                dry_run=args.dry_run,
            )
            print(summary.format_report())
            print()

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
