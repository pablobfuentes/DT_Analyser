"""CLI: finalize a NY trading day (enrichment, snapshot, backup)."""

from __future__ import annotations

import argparse
import json
from datetime import date

from app.db.init_data import initialize_app
from app.db.session import SessionLocal
from app.services.automation.pipeline import start_finalize_run
from app.utils.analytics import ny_date_from_utc
from app.utils.clock import utc_now


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize a New York trading day")
    parser.add_argument("--date", help="NY date YYYY-MM-DD (default: today in America/New_York)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    initialize_app()
    day = date.fromisoformat(args.date) if args.date else ny_date_from_utc(utc_now())
    db = SessionLocal()
    try:
        run = start_finalize_run(db, day, include_backup=not args.dry_run)
        print(json.dumps({"run_id": run.id, "status": run.status, "date": run.ny_date}))
    finally:
        db.close()


if __name__ == "__main__":
    main()
