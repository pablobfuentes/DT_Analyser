"""CLI: process the inbox. Suitable for Task Scheduler / cron / launchd."""

from __future__ import annotations

import argparse
import json

from app.db.init_data import initialize_app
from app.db.session import SessionLocal
from app.services.automation.inbox import classify_path, list_inbox_candidates, process_inbox
from app.services.automation.pipeline import start_inbox_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Process Local Trader Analyzer inbox")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--file", dest="file_path")
    parser.add_argument("--date")
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    initialize_app()
    db = SessionLocal()
    try:
        if args.dry_run and not args.file_path:
            files = list_inbox_candidates()
            rows = []
            for p in files:
                c = classify_path(p)
                rows.append({
                    "file": p.name,
                    "detected_type": c.detected_type,
                    "needs_review": c.needs_review,
                    "error_code": c.error_code,
                })
            print(json.dumps({"dry_run": True, "files": rows}, indent=2))
            return
        if args.retry_failed:
            from app.db.models.automation import AutomationRun
            from app.services.automation.pipeline import retry_failed_steps

            run = db.query(AutomationRun).order_by(AutomationRun.id.desc()).first()
            if run:
                retry_failed_steps(db, run.id)
                print(json.dumps({"retried_run": run.id, "status": run.status}))
            return
        run = start_inbox_run(db, dry_run=args.dry_run)
        print(json.dumps({"run_id": run.id, "status": run.status, "date": run.ny_date}))
    finally:
        db.close()


if __name__ == "__main__":
    main()
