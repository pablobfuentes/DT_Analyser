# Backup and Restore

Uses the **SQLite backup API** (`Connection.backup`), not a copy of a live file while writers are active. WAL is enabled on the main engine (`journal_mode=WAL`, `busy_timeout=5000`).

Each backup folder:

```
backups/{id}/
  trader.db
  attachments/
  manifest.json
```

SUCCESS requires `PRAGMA integrity_check = ok` on the **copy**. Missing screenshots mark PARTIAL / ATTACHMENT_WARNING; the DB backup can still be valid.

Manifest includes hashes and a settings snapshot. Alpaca keys and other secrets are omitted.

Types: MANUAL, DAILY, PRE_MIGRATION, PRE_RESTORE.

## Retention (deterministic)

When automatic backups are created daily, rotation preserves exactly:

1. **Newest verified backup** (SUCCESS or PARTIAL) — always.
2. **All eligible verified DAILY backups** whose America/New_York calendar date falls in the **most recent 30 days**, inclusive of today (dates `today_ny - 29` through `today_ny`).
3. **One verified DAILY backup per NY/calendar week** (Monday–Sunday) for each of the **preceding 12 weeks** ending at the Monday of `today_ny`. The newest DAILY in that week is kept.

`today_ny` is the NY date of the newest verified backup when rotation runs after a new backup (or an explicit `today_ny` in tests).

Never delete:

- the live primary database
- the newest verified backup
- the only remaining verified backup
- PRE_RESTORE or PRE_MIGRATION backups
- a backup currently being verified or restored (in-process protect set)

MANUAL backups are not daily-eligible; they are kept if they are the newest verified backup, otherwise they may rotate. A 100-day synthetic of one verified DAILY per day keeps the last 30 calendar days in full plus one DAILY per week for the 12-week window (weeks that overlap the 30-day window are already covered).

## Restore sequence

Restore is never a casual one-click (`confirm=true` / `--confirm`).

1. Verify selected backup manifest  
2. Verify database SHA-256  
3. Verify SQLite `integrity_check`  
4. Verify attachment manifest (existence + SHA-256)  
5. Create PRE_RESTORE safety backup — **current state is not destroyed until this succeeds and the incoming copy is valid**  
6. Enter maintenance mode  
7. Mutating and other API calls receive `MAINTENANCE_MODE` (HTTP 503). `/api/health` and `/api/workflow/health` stay available  
8. Pause watcher  
9. Pause scheduler  
10. Stop/drain automation worker  
11. Dispose the SQLAlchemy engine / pooled connections  
12. Stage restored DB and attachment files  
13. Validate staged state (integrity + SHA)  
14. Swap the live database via the backup API  
15. Restore attachments  
16. Recreate/rebind the DB engine  
17. Run required migrations  
18. `PRAGMA integrity_check`  
19. Validate key row counts  
20. Resume automation if this process is the automation owner  
21. Leave maintenance mode  

### Attachment policy

Preview always reports `attachments_ok`, missing/corrupt paths, and `can_restore_db`.

- Missing or corrupt screenshots in the backup: **warn**, `policy: PARTIAL_ALLOWED`. Database restore is allowed. Result status is **PARTIAL**. SUCCESS requires every `journal_attachment` file to exist after restore and match SHA-256.  
- Restore does not invent screenshot files. It does not silently report SUCCESS when rows would point at missing images.

CLI: `python -m app.cli.restore_backup ID --verify-only` then `--confirm`.

## PRE_MIGRATION backups

A schema-migration safety backup is taken **once per pending-mutation signature** when:

- the migration runner sees a pending schema mutation (listed ALTER columns in `migrate.py`, or a SQLAlchemy model table that is not in the file yet), **and**
- the user database has meaningful data (trades, executions, signals, or journal rows).

It is **not** taken on every startup. It is **not** keyed only to `automation_jobs` being absent.

- If `backup_records` does not exist yet, a file-level copy is written under `backups/pre-migration-…`.  
- If tables already exist, a recorded `PRE_MIGRATION` backup is created through the normal backup service.

**Limitation:** index-only changes and data backfills (for example `_backfill_trade_risk`) do not trigger a backup. `create_all` adding empty new tables is treated as a pending `table:…` mutation only when those tables are missing *and* user data exists. Future authors must add new ALTER checks to `pending_schema_mutations` when they add migrations — the runner does not invent a general schema-diff engine.
