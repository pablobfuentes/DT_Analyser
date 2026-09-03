"""CLI restore. Requires --confirm. Use --verify-only to inspect."""

from __future__ import annotations

import argparse
import json

from app.db.init_data import initialize_app
from app.db.session import SessionLocal
from app.services.backup.service import restore_backup, restore_preview, verify_backup


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore a Local Trader Analyzer backup")
    parser.add_argument("backup_id")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()

    initialize_app()
    db = SessionLocal()
    try:
        if args.verify_only:
            print(json.dumps(verify_backup(db, args.backup_id), indent=2, default=str))
            return
        if not args.confirm:
            preview = restore_preview(db, args.backup_id)
            print(json.dumps({"preview": preview, "hint": "Re-run with --confirm to restore"}, indent=2))
            return
        print(json.dumps(restore_backup(db, args.backup_id, confirm=True), indent=2, default=str))
    finally:
        db.close()


if __name__ == "__main__":
    main()
