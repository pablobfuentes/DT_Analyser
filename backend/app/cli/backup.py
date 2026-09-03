"""CLI: create a verified local backup."""

from __future__ import annotations

import argparse
import json

from app.db.init_data import initialize_app
from app.db.session import SessionLocal
from app.services.backup.service import create_backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a local SQLite backup")
    parser.add_argument("--type", default="MANUAL", dest="backup_type")
    args = parser.parse_args()
    initialize_app()
    db = SessionLocal()
    try:
        rec = create_backup(db, backup_type=args.backup_type)
        print(json.dumps(rec, indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
