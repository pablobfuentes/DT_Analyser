# Step 10 Completion — Automation + Journal Workflow

**Date:** 2026-09-02 (hardening 2026-09-03)  
**Status:** Implemented and operationally hardened. Plan: [STEP_10_PLAN.md](STEP_10_PLAN.md).  
**Real-export checklist:** **USER-DATA VALIDATION PENDING** (does not block code completion).

No further product phase was started after this report.

---

## 1. Automation architecture

Orchestration only. A filesystem watcher and NY-time scheduler **enqueue** persistent `automation_jobs`. A single in-process worker runs them. Pipeline steps call existing services: `ImportService`, Pine `commit_import`, `match_signals_batch`, `RiskService.recalculate_many`, `MarketEnrichmentService.enrich`, `ExcursionEnrichmentService.enrich`. No second reconstruction, matcher, or R calculator. Research refresh is a documented no-op (forward samples are query-time).

## 2. Data directory

Resolved by `LTA_DATA_DIR` → existing `./data` → platform default. Subfolders: `inbox/`, `archive/`, `quarantine/`, `screenshots/`, `backups/`, `logs/`, `paste/`. See [DATA_DIRECTORY.md](DATA_DIRECTORY.md).

## 3–4. Watcher and stability

`watchdog` Observer with polling fallback. Callback only enqueues `PROCESS_INBOX`. Files ignored until size/mtime stable for `file_stable_seconds` (default 2). `.tmp` / `.part` / `.crdownload` ignored.

## 5–6. Job queue and crash recovery

`automation_jobs` with PENDING/RUNNING/SUCCESS/PARTIAL/FAILED/RETRY/INTERRUPTED/CANCELLED. Startup marks leftover RUNNING as INTERRUPTED and retries when `attempt_count < 5`. Successful import file events are not reimported.

## 7–8. File detection / formats

Content detection via existing CSV parsers plus Pine header (`RECORD_TYPE` + `SIGNAL_ID` + `SCHEMA_VERSION`). Extensions `.csv/.tsv/.txt/.log` are candidates only.

## 9–13. Inbox, archive, quarantine, duplicates, overlaps

App-owned inbox only. Authoritative detect → commit; UNKNOWN / AMBIGUOUS / TIMEZONE_REQUIRED → quarantine. Successful inbox files move to `archive/YYYY/MM/DD/`. Archive failure after commit → `IMPORT_SUCCESS_ARCHIVE_PENDING` (no reimport). Duplicate SHA-256 → `DUPLICATE_FILE`. Overlapping Order History uses existing fingerprints.

## 14–16. Pipeline, retry, coalescing

Steps listed in the plan. Failed Pine does not roll back trades (PARTIAL). Debounced inbox files share one downstream pass. `RETRY_STEP` re-runs failed non-import steps.

## 17–19. Expected inputs

Defaults: Order History REQUIRED, Pine RECOMMENDED, Activity Log OPTIONAL, AUTO OPTIONAL. AUTO can be DISABLED without schema changes. Completeness uses import batches / Pine batches / file events / trade NY dates.

## 20–22. EOD scheduler, offline limit, CLI

APScheduler **Monday–Friday** cron at 20:15 America/New_York (`zoneinfo`, DST-safe). No exchange-holiday calendar; a holiday weekday may no-op. In-process only while the **owning** backend is up. CLI: `app.cli.process_inbox`, `finalize_day`, `backup`, `restore_backup` (`--confirm` / `--verify-only`).

## 23–25. Workflow UI

`/workflow?date=YYYY-MM-DD`: Process Inbox, Finalize Today, Create Backup, No Trading Today, input checklist, coverage, attention queue, run list + detail, health (including automation ownership), backup paths.

## 26–32. Journal, tags, screenshots, reviews, search

Trade Detail journal + tags + PNG/JPEG/WEBP attachments (extension allowlist **and** magic bytes; traversal / absolute / double-extension / renamed executable rejected; SHA-256 reuse). Daily/weekly reviews reuse dashboard/expectancy/coverage math. Snapshots freeze on Complete. History at `/reviews`. LIKE search on notes/tags/captions.

## 33–38. Backup / restore

SQLite `Connection.backup` API. WAL + `busy_timeout=5000` on the live engine. Manifest + integrity_check. Missing screenshots → PARTIAL / ATTACHMENT_WARNING. Exact retention in [BACKUP_AND_RESTORE.md](BACKUP_AND_RESTORE.md). Restore follows the maintenance/engine sequence below.

## 39–41. Settings, security, health

`app_preferences` for safe settings. Secrets stay in `LTA_*` env. Paths displayed. Workflow health: ownership, watcher/worker/scheduler, pending/failed jobs, last backup.

## 42–44. Open trades, manual risk, candidate rules

Excursion enrichment still closed-only. `RiskService` keeps `manual_override`. Pipeline does not mutate candidate rule filters, cutoff, or version.

---

## Automation single-owner implementation

`{LTA_DATA_DIR}/automation.lock` is an OS exclusive lock (`msvcrt.locking` on Windows, `fcntl.flock` elsewhere). The handle stays open for process lifetime. PID JSON in the file is informational only.

Only the lock holder starts watcher, worker, and APScheduler. Other processes (second uvicorn worker, reload overlap, accidental second backend on the same data dir) may serve HTTP as **STANDBY / OWNED BY ANOTHER PROCESS**.

Health/UI: `Automation Ownership: OWNER` or `STANDBY / OWNED BY ANOTHER PROCESS`.

Clean shutdown unlocks. A crash cannot leave permanent ownership — the OS releases the lock with the handle. Tests: A holds; B cannot acquire; A release or simulated crash; a new instance acquires.

This is an extra orchestration layer. Execution/signal idempotency is unchanged.

## Restore maintenance / engine handling

Canonical sequence implemented in `restore_backup`:

1. Verify manifest  
2. Verify database SHA-256  
3. `PRAGMA integrity_check`  
4. Verify attachment checksums  
5. PRE_RESTORE safety backup (live state is not destroyed until this exists and the incoming copy is valid)  
6. Enter maintenance mode  
7. API reads/writes return HTTP 503 `{code: MAINTENANCE_MODE}` except `/api/health` and `/api/workflow/health`  
8–10. Pause watcher, pause scheduler, drain worker  
11. Dispose SQLAlchemy engine / pool  
12–13. Stage DB + attachments; validate staged integrity + SHA  
14–15. Swap live DB via backup API; copy attachments  
16. Recreate engine (`SessionLocal.configure`)  
17. `run_migrations`  
18. `integrity_check`  
19. Key row counts  
20. Resume automation if this process is owner  
21. Leave maintenance mode  

## Attachment restore validation

Happy path (trade + journal + PNG): backup → mutate DB and file → restore restores trade, journal, metadata, file bytes, SHA-256, relative path, readable PNG. No orphan attachment after SUCCESS.

Backup DB valid but screenshot missing/corrupt: preview `attachment_warning`, `attachments_ok=false`, `can_restore_db=true`, `policy=PARTIAL_ALLOWED`. Restore is **PARTIAL** with `missing_attachments`. SUCCESS is not returned when restored rows would point at missing files.

## Exact retention semantics

Verified = status SUCCESS or PARTIAL.

Preserve:

- newest verified backup always  
- all verified **DAILY** backups whose NY calendar date is in the most recent **30 days** (inclusive: `today_ny-29` … `today_ny`)  
- one verified **DAILY** per NY/calendar week (Monday–Sunday) for each of the **12 weeks** ending at the Monday of `today_ny` (newest in that week)

Never delete: live primary DB, newest verified, only verified backup, PRE_RESTORE, PRE_MIGRATION, backup currently being verified/restored.

100-day synthetic (one verified DAILY per day ending 2026-09-02): **37 kept**, 63 rotated. Kept set = last 30 calendar days plus one Sunday (or latest day) per historical week in the 12-week window.

## 10k benchmark (this machine)

Fixture: 10,000 existing closed trades, 10 Order History files (100 new executions), 20 Pine events, daily/intraday cache rows for existing ticker, NONE provider.

| Step | Seconds |
|------|---------|
| File stability | 0.006 |
| Classification | 0.109 |
| Canonical import + reconstruction inside ImportService | 1.362 |
| Pine import | 0.539 |
| Signal matching | 0.199 |
| RiskService (newly imported closed trades; equity map still sees 10k) | 110.357 |
| Market missing-only | 2.397 |
| Excursion missing-only | 1.690 |
| Daily completeness | 0.615 |
| Daily review snapshot | 0.122 |
| Verified backup | 2.450 |
| Duplicate file pass | 1.085 |
| **Total timed pipeline** | **120.935** |

- Database size ~ **6.10 MB** (before/after WAL checkpoint not forced)  
- Jobs created: this fixture called services directly (not the worker); soak below created 1 job / 61 runs  
- Imported executions: **100**; duplicates skipped: **0**; Pine events: **20**  
- Provider `get_daily_bars` calls: **22**; market `trades_requested`: 50; excursion `trades_requested`: 50  
- Peak tracemalloc: **~51 MB**  

Pathological CI ceilings only (not an SLA). A full `RiskService.recalculate_many` over all 10k closed trades (what the inbox pipeline currently does) exceeded **11 minutes** in a hardening run and is **not** a CI gate.

## 30-day soak result

30 NY weekdays (2026-07-20 …). Overlapping Order History, Pine, daily process + finalize + DAILY backup. Injected: exact duplicate file, unknown file, TIMEZONE_REQUIRED, archive-move failure, temporary market then excursion provider failure, interrupted RUNNING job + recover, OPENX opened day 1 / closed day 9, manual risk override, Candidate Rule with forward evaluation.

Asserted: unique execution fingerprints, unique signal-event fingerprints, unique reconstructed trades, no P&L inflation (30 `D*` closed + OPENX closed), manual override intact, candidate rule filters/cutoff/version unchanged, no RUNNING jobs, no orphan run steps / signal links / TradeRisk / journal files, 30 dailies all kept (inside 30-day window), latest backup verifies, `integrity_check = ok`.

- DB size: **978,944 bytes** (~0.96 MB)  
- Backup tree size: **22,240,295 bytes** (~21.2 MB)  
- Trades 31, executions 62, jobs 1, runs 61  

## Security magic-byte result

`store_attachment` requires:

- allowlisted last extension `.png` / `.jpg` / `.jpeg` / `.webp`  
- **and** magic bytes PNG / JPEG / WEBP  

`Content-Type` is ignored. Rejected: `../` traversal, absolute paths, double extensions (`photo.jpg.png`, `image.png.exe`), renamed executable (`nice.png` with `MZ` bytes). Tests in `test_step_10_journal.py`.

## Migration-backup policy

PRE_MIGRATION is **one backup per pending-mutation signature** when schema mutation is pending **and** the file has meaningful user data (trades/executions/signals/journal). Not every startup. Not keyed only to `automation_jobs` absent.

Pending mutations = listed ALTER columns in `migrate.py` plus missing SQLAlchemy model tables. Index-only changes and data backfills do **not** trigger a backup. If `backup_records` is missing, a file-level copy is written; otherwise a recorded PRE_MIGRATION backup is created.

**Limitation (non-blocking):** this is not a general schema-diff engine. Future ALTERs must be added to `pending_schema_mutations`. That is honest coverage for future migrations, not a guarantee that every possible SQLite change is detected.

## Final test counts (this machine, 2026-09-03)

| Check | Result |
|-------|--------|
| Backend full `pytest` | **358 passed** |
| Frontend `vitest run` | **41 passed** (8 files) |
| Production `npm run build` | **Pass** |
| Single-instance automation ownership | **Pass** (3 tests) |
| Restore DB + attachment roundtrip | **Pass** |
| Missing/corrupt attachment preview | **Pass** (PARTIAL) |
| 100-backup retention fixture | **Pass** (37 kept) |
| 10k benchmark | **Pass** (numbers above; generous ceilings) |
| 30-day soak | **Pass** |
| SQLite `integrity_check` (soak + restore) | **ok** |
| Step 1 / 2 / 2.5 files | **Pass** (in full suite) |
| Step 3 / 4 files | **Pass** |
| Step 5 / 7 files | **Pass** |
| Step 8 / 9 files | **Pass** |
| Step 10 regression files | **Pass** |

## Remaining USER-DATA validation only

Does **not** block code completion. Do not fabricate TradingView results.

**DAY 1:** drop real Order History + Pine log (+ Activity/AUTO if configured) into the inbox; Process Inbox / Finalize; confirm trades, journal, completeness badge.

**DAY 2:** overlapping exports for the next session; confirm no duplicate reconstructed trades and no P&L inflation.

**DUPLICATE:** drop the same files again; expect `DUPLICATE_FILE` / zero new rows.

**FAILURE:** temporary market or excursion provider outage; pipeline PARTIAL; retry after recovery.

**CRASH:** restart the backend mid-pipeline; leftover RUNNING → INTERRUPTED/RETRY; no duplicate import.

**RESTORE:** create a verified backup, restore with confirm; PRE_RESTORE exists; data + screenshots match.

Until those real exports are run on this machine, status remains **USER-DATA VALIDATION PENDING**.

## Known limitations (unchanged product scope)

1. Watcher/scheduler/worker live only while the **owning** uvicorn process is running.  
2. No broker, webhook, Pine, or risk auto-trading.  
3. No cloud backup.  
4. No OCR / no AI journal assistant.  
5. No FTS5.  
6. No exchange-holiday calendar.  
7. Research refresh is a no-op.  
8. Pipeline does not call `TradeRebuildService` (journal FK / identity).  
9. Custom Downloads watch is not in v1.  
10. Inbox pipeline still calls `RiskService.recalculate_many` on **all** closed trades (10k full pass is slow; not changed in this hardening).  

**Out of scope (honored):** broker execution, cloud sync, automatic strategy modification. No new product phase started.
