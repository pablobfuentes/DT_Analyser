"""CLI for excursion enrichment."""

from __future__ import annotations

import argparse

from app.db.session import SessionLocal
from app.market_data.registry import get_market_data_provider
from app.services.excursion_enrichment.service import ExcursionEnrichmentService


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich trades with MFE/MAE excursion data")
    parser.add_argument("--scope", default="missing", choices=["missing", "all"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--recalculate", action="store_true")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        svc = ExcursionEnrichmentService(db, get_market_data_provider(force_fake=True))
        if args.recalculate:
            result = svc.recalculate()
        else:
            result = svc.enrich(scope=args.scope, dry_run=args.dry_run)
        print(result)
    finally:
        db.close()


if __name__ == "__main__":
    main()
