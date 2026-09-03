"""CLI for market data enrichment."""

from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.market_data.registry import get_market_data_provider
from app.services.market_enrichment.service import MarketEnrichmentService


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich trades with market data")
    parser.add_argument("--scope", default="missing", choices=["missing", "all", "selected"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recalculate", action="store_true")
    parser.add_argument("--refresh", action="store_true", help="Re-fetch bars from the provider")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        svc = MarketEnrichmentService(db, get_market_data_provider())
        if args.recalculate:
            result = svc.recalculate()
        elif args.refresh:
            result = svc.refresh(scope=args.scope)
        else:
            result = svc.enrich(scope=args.scope, dry_run=args.dry_run)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
