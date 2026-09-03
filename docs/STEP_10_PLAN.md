# Step 10 Plan — Automation + Journal Workflow

**Status:** Implemented 2026-09-02. See [STEP_10_COMPLETION.md](STEP_10_COMPLETION.md).

**Goal:** Make the analyzer practical for daily use for years. Reduce the manual export → import → match → enrich → review → backup loop to: drop files / paste Pine → automatic processing → today's review ready. Remain local-first, auditable, idempotent, crash-safe, reversible, and non-destructive.

**Prerequisite:** Steps 1–5, 7–9 implemented and audited. Step 6 remains skipped. Step 9 candidate rules stay research objects.

---

## Current State (Audit)

| Area | Location | Reuse decision |
|------|----------|----------------|
| Import commit | `ImportService.commit_import` | **Authoritative.** Automation calls this after internal preview. |
| Preview / detect | `importers/detector.py` `preview_file` / `detect_format` | **Authoritative.** Content-based. Never guess UNKNOWN / AMBIGUOUS / TIMEZONE_REQUIRED. |
| Order History | `TradingViewManualParser` | Inbox type `ORDER_HISTORY`. |
| Activity Log | `TradingViewActivityLogParser` | Optional alternative execution source. Same Order IDs as Order History → fingerprint skip. **Not required** for reconstruction after Order History. |
| Strategy Tester / AUTO | `TradingViewStrategyParser` | Optional temporary source. Writes trades directly (no reconstruction). |
| Execution / trade fingerprints | `deduplication.py` | Authoritative idempotency. File SHA-256 is first-layer only. |
| Reconstruction | `TradeRebuildService` inside `_import_manual_executions` | Already runs on execution import. Pipeline must **not** call a second full rebuild (rebuild deletes/recreates trades and would break journal `trade_id` FKs). |
| Pine import | `signals.importer.commit_import` | Authoritative. Already matches + `RiskService.recalculate_for_signal` for touched signals. |
| Pine parser | `signals.parser.parse_pine_log` | Content detect via `RECORD_TYPE` / `SCHEMA_VERSION` / `SIGNAL_ID` header, not `.txt`. |
| Signal matcher | `signals.matcher.match_signals_batch` | Reuse for unmatched leftover after Pine commit. |
| Risk | `RiskService.recalculate_many` / `compute` | Manual override survives recalc. Automation must not call `apply_manual`. |
| Market | `MarketEnrichmentService.enrich` | Callable with `Session`. Scope `missing`. |
| Excursions | `ExcursionEnrichmentService.enrich` | Closed trades only. OPEN excluded. |
| Research forward sample | `evaluate_rule` query-time | **No persisted refresh.** Pipeline step is a documented no-op. |
| Candidate rules | `revise_candidate_rule` versions rows | Automation must not mutate filters, cutoff, version, or snapshots. |
| Dashboard metrics | `dashboard_service._summary_stats` + reports annotate | Daily/weekly review **reuse** these formulas. No new P&L/R math. |
| NY dates | `utils.analytics.ny_date_from_utc` / `ny_day_utc_bounds` | EOD and completeness use America/New_York. |
| SQLite | `session.py` | FK on. **No WAL today.** Enable WAL + busy timeout for UI + worker. |
| Migrations | `migrate.py` `run_migrations` | Continue imperative ALTER + `create_all` for new tables. |
| Startup | `initialize_app` | No jobs, no scheduler. Step 10 starts worker + watcher + scheduler here. |
| CLI | `rebuild_trades`, `enrich_market_data`, `enrich_excursions` | Add process_inbox / finalize_day / backup / restore. |
| Uploads | `./data/uploads` hash dirs | Keep for manual Import page. Inbox is a separate app-owned folder. |
| Background jobs | None | Do not use FastAPI `BackgroundTasks` as the job store. |
| Frontend | `main.tsx` routes | Add `/workflow`, `/review/daily`, `/review/weekly`, `/reviews`, `/settings`. |

### Activity Log role (must be honest in UI)

Activity Log is an **optional alternative execution source**. If Order History is imported, Activity Log fills share TradingView Order IDs and are skipped as duplicates. It is **not** required for Step 2.5 reconstruction. Default expected-input: **OPTIONAL**. Missing Activity Log must not block daily completeness.

### AUTO role

AUTO Strategy Tester is a temporary experiment source. Architecture treats it as an ordinary optional input. Default: **OPTIONAL**. User can set **DISABLED** without schema changes.

### Reconstruction / journal identity

`TradeRebuildService.rebuild` deletes and recreates trades in scope. Journal `trade_id` would dangle. Therefore the pipeline **RECONSTRUCT** step records that reconstruction already occurred inside `ImportService` and does **not** invoke a second rebuild.

---

## A. Automation philosophy

1. **Orchestrate, do not recalculate.** Call existing services. No second importer, matcher, R calculator, or reconstruction engine.
2. **Local-first.** FastAPI + SQLite + React + local filesystem. Market providers remain the only optional external I/O.
3. **Never guess.** Unknown / ambiguous / timezone-required files go to quarantine or `NEEDS_REVIEW`.
4. **Idempotent.** Overlapping exports and duplicate drops must produce 0 new financial records.
5. **Crash-safe.** Persistent jobs. Interrupted `RUNNING` jobs recovered on startup.
6. **Reversible / non-destructive.** Archive and quarantine are moves/copies, not deletes of analytical history. Restore requires confirmation + PRE_RESTORE safety backup.
7. **One worker.** A single automation worker processes the queue. Watcher and scheduler only enqueue.
8. **Never:** place trades, change Pine, change strategy rules, change risk automatically, delete analytical history silently, infer missing executions, fabricate files, auto-apply research findings, OCR screenshots, or require cloud storage.

---

## B. Inbox architecture

Config key: `LTA_DATA_DIR` (`settings.data_dir`).

Resolution:

1. If `LTA_DATA_DIR` is set → use it.
2. Else if `./data` already exists (current installs) → keep `./data` so existing DBs/uploads are not abandoned.
3. Else → platform default:
   - Windows: `%LOCALAPPDATA%/LocalTraderAnalyzer`
   - macOS: `~/Library/Application Support/LocalTraderAnalyzer`
   - Linux: `~/.local/share/local-trader-analyzer`

Layout (all resolved through settings, never hard-coded in services):

```
{data_dir}/
  trader_analyzer.db          # if using default SQLite URL
  uploads/                    # existing preview staging
  inbox/
  archive/YYYY/MM/DD/
  quarantine/
  screenshots/YYYY/MM/
  backups/
  logs/
  paste/                      # archived pasted Pine text
```

Default watch target is **app-owned `inbox/` only**. Do not watch Downloads.

If a custom external watch directory is added later: **copy** into inbox/processing. Never delete or move the user's original.

`Auto Process Inbox` preference default **ON**. If OFF, watcher records the file event and waits for `[Process Inbox]`.

---

## C. File detection

Content detection, not extension.

| Input | Detector | Existing parser |
|-------|----------|-----------------|
| Order History | `detect_format` / `preview_file` | `tradingview_manual` |
| Activity Log | same | `tradingview_activity_log` |
| Strategy Tester / AUTO | same | `tradingview_strategy` |
| Pine Signal Log | new `detect_pine_text` wrapping `parse_pine_log` | `signals.parser` |

Allowed extensions for watcher candidates: `.csv`, `.tsv`, `.txt`, `.log`. Ignore `.tmp`, `.part`, `.crdownload`, and names starting with `.`.

Stability: size + mtime unchanged for `file_stable_seconds` (default 2). Centralized in settings.

Detection outcomes:

| Result | Action |
|--------|--------|
| Authoritative parser + timezone OK | Auto-commit via `ImportService` / Pine `commit_import` |
| `UNKNOWN_FORMAT` / `AMBIGUOUS_FORMAT` / `TIMEZONE_REQUIRED` / missing columns / parse error | Quarantine + `NEEDS_REVIEW`. No guess. |
| Duplicate SHA-256 of a successfully processed file | Record `DUPLICATE_FILE`. Do not re-commit unless user retries. Importer would still be safe. |

Pine paste from the existing UI: after commit, write the raw text under `{data_dir}/paste/` as a source artifact (same provenance as a dropped file).

---

## D. Persistent job queue

Table `automation_jobs`:

| Field | Notes |
|-------|-------|
| id | PK |
| job_type | `INGEST_FILE`, `PROCESS_INBOX`, `PIPELINE_RUN`, `FINALIZE_DAY`, `BACKUP`, `ARCHIVE_FILE`, `RETRY_STEP` |
| status | PENDING, RUNNING, SUCCESS, PARTIAL, FAILED, RETRY, INTERRUPTED, CANCELLED |
| created_at, started_at, completed_at | UTC |
| attempt_count | |
| payload_json | Paths, dates, run id. **No secrets.** |
| error_code, error_message | |
| next_retry_at | nullable |
| parent_job_id | nullable |
| correlation_id | run/job log correlation |
| priority | optional, default 100 |

Single in-process worker thread. Poll + `next_retry_at`. Manual Process Inbox and watcher enqueue into the **same** queue.

Retryable vs permanent (see Q / §92): timeouts, 429, filesystem locks retry with bound; unknown format / timezone / missing column do not.

Cancel: PENDING → CANCELLED. RUNNING canonical import finishes its existing transaction; later pipeline steps may skip.

---

## E. Pipeline orchestration

Tables `automation_runs` + `automation_run_steps`.

Run types: `INBOX_PROCESSING`, `EOD_FINALIZE`, `MANUAL_FINALIZE`, `MANUAL_BACKUP`.

Recommended steps (skip if no applicable data):

| # | step_key | Calls | Notes |
|---|----------|-------|-------|
| 1 | INPUT_DETECTION | classify inbox | |
| 2 | TRADE_IMPORT | `ImportService.commit_import` | Per file. Existing transaction unchanged. |
| 3 | RECONSTRUCT | none | Record that import already reconstructed. **Do not** call `TradeRebuildService`. |
| 4 | PINE_IMPORT | `signals.importer.commit_import` | File or archived paste. |
| 5 | SIGNAL_MATCHING | `match_signals_batch` | Only unmatched leftover; Pine commit already matches new signals. |
| 6 | RISK_RECALC | `RiskService.recalculate_many` | Manual overrides survive. |
| 7 | MARKET_ENRICHMENT | `MarketEnrichmentService.enrich(scope="missing")` | |
| 8 | EXCURSION_ENRICHMENT | `ExcursionEnrichmentService.enrich(scope="missing")` | Closed only. |
| 9 | RESEARCH_REFRESH | no-op | Forward samples are query-time (`entry_time_utc > cutoff_at`). |
| 10 | REVIEW_SNAPSHOT | compute daily metrics via dashboard/reports | Stored only when a review exists or finalize requests a draft snapshot. Does not auto-complete the review. |
| 11 | BACKUP | SQLite backup API | If automatic backup ON (EOD only by default). |

Dependencies are **not** one giant transaction. Pine failure → PARTIAL; trades/market may still succeed. Retry failed steps only.

**Coalescing:** Files arriving within `inbox_debounce_seconds` (default 5) become one `INBOX_PROCESSING` run: N imports, then **one** match / risk / enrich / backup pass.

**Archive after import:** Successful app-owned inbox files move to `archive/YYYY/MM/DD/` (process date). Collision → suffix/hash. Never overwrite. If move fails after DB commit: file event `IMPORT_SUCCESS_ARCHIVE_PENDING`; separate `ARCHIVE_FILE` retry. Do not reimport.

---

## F. Daily completeness model

Keyed by **NY trading date**.

Expected inputs (preferences, not schema enums that require migrations to change):

| Type | Default |
|------|---------|
| ORDER_HISTORY | REQUIRED |
| PINE_LOG | RECOMMENDED |
| ACTIVITY_LOG | OPTIONAL |
| AUTO_STRATEGY_TESTER | OPTIONAL |

Evidence is **import records**, not filenames:

- `import_batches` (parser_name, completed_at, file_hash)
- `pine_import_batches`
- `automation_file_events`
- Trades with `ny_date_from_utc(entry_time_utc)` or `exit_time_utc` on that day

Coverage panels reuse existing:

- Market: `MarketEnrichmentService.get_coverage`
- Risk: `missing_r_breakdown`
- Signals: `coverage_summary`
- Excursions: existing excursion coverage

Statuses: COMPLETE / PARTIAL / NEEDS_ATTENTION / WAITING_FOR_EOD / NO_TRADES.

**No-trade day:** explicit `daily_workflow_days` (or preference row) `NO_TRADING`. Suppresses missing Order History nag.

**Not expected ≠ missing.** DISABLED AUTO never warns.

Market holidays: only if Step 4 already has a calendar. **It does not.** Do not fabricate one.

---

## G. End-of-day processing

Optional scheduled finalize. Default **20:15 America/New_York** via `zoneinfo` (EST/EDT, no fixed UTC offset).

Scheduler (APScheduler) **only enqueues** `FINALIZE_DAY`. Worker runs the pipeline.

`[Finalize Today]` enqueues the same job for the NY date (not OS date).

If EOD provider data is incomplete: step PARTIAL / run `PENDING_EOD`. Later scheduled run completes it.

**Honest limitation:** in-process scheduler runs only while the backend is up. CLI `python -m app.cli.finalize_day` is the Task Scheduler / cron / launchd entry.

---

## H. Backup model

Use **SQLite backup API** (`sqlite3.Connection.backup`), never a naive copy of a live DB.

Directory: `{data_dir}/backups/{backup_id}/`

```
trader.db
attachments/          # journal screenshots, relative layout
manifest.json
```

`backup_records`: MANUAL / DAILY / PRE_MIGRATION / PRE_RESTORE.

Manifest: backup_id, created_at, app_version, schema_version, database_sha256, database_size, attachments_count, attachments_manifest_hash, archive_included, settings_snapshot (**no API secrets**).

After copy: `PRAGMA integrity_check` on the **backup** file. SUCCESS only if OK. Missing historical screenshots → PARTIAL / `ATTACHMENT_WARNING`, not a failed DB backup.

Automatic: once after successful EOD finalize if enabled (default ON).

PRE_MIGRATION: when `run_migrations` detects pending ALTERs **and** user tables have rows. Not on every startup.

Retention default: 30 daily + 12 weekly. Never delete the primary DB. Never delete the most recent successful backup, the only verified backup, or a backup being restored. Log deletions.

---

## I. Restore model

High consequence. Not one-click.

1. Select backup → verify manifest + checksum + integrity.
2. Preview: date, size, schema, trade/signal/attachment counts.
3. User confirms (`--confirm` on CLI).
4. PRE_RESTORE backup of current state.
5. Stop worker writes (maintenance flag).
6. Restore DB + attachments (relative paths).
7. Run migrations if needed. Verify integrity.
8. If restore fails: keep current data + PRE_RESTORE. Do not delete current until replacement validates.

---

## J. Journal model

`journal_entries`: id, trade_id nullable, review_date nullable, entry_type (`TRADE_NOTE` / `DAILY_NOTE` / `WEEKLY_NOTE` / `GENERAL`), title, body, followed_plan (`YES`/`NO`/`PARTIAL`/`NOT_ASSESSED`), prompt_fields_json (thesis, why entered/exited, what went well, what I would change), created_at, updated_at.

`journal_tags`: id, name (unique case-insensitive), description, created_at.

`journal_entry_tags`: entry_id, tag_id.

Trade notes are subjective. Do not infer. Do not score Step 6 compliance.

Tags are user-defined. Not injected into Step 3 Graphs. Not a Step 9 research variable in this step.

Search: SQLite `LIKE` on body/title/captions/tag names. FTS5 not required.

`JournalAssistantProvider` abstraction with `NoneProvider` default. **Not implemented** beyond the stub. No external AI in Step 10.

---

## K. Screenshot model

`journal_attachments`: trade_id / journal_entry_id / daily_review_id / weekly_review_id nullable, relative_path (from data_dir), original_filename, mime_type, size_bytes, sha256, width/height nullable, caption, created_at.

Store files under `screenshots/YYYY/MM/{sha256}{safe_ext}`. Never trust user filename. Reject `..`, absolute paths, executables.

v1 types: PNG, JPEG, WEBP. SHA-256 dedup: second upload references the same file. Delete reference; unlink file only if unused.

No OCR. Viewer: thumbnail grid + modal. Clipboard paste + drag-drop + file upload.

---

## L. Daily review

Route `/review/daily?date=YYYY-MM-DD` (NY date).

Auto summary = existing analytics (dashboard `_summary_stats`, risk/signal/excursion coverage, best/worst trade and R, max MFE, largest giveback, loss-beyond-R count). **Same formulas.**

Trade table: ticker, direction, P&L, R, MFE R, MAE R, exit efficiency, setup, journal status → Trade Detail.

Prompts (config defaults, not a migration): What worked / hurt / follow process / repeat / avoid / unusual market. User writes answers. No generated text.

Status: NOT_STARTED / IN_PROGRESS / COMPLETED. `[Complete Review]` stamps `completed_at` and `metrics_snapshot_json` + `calculation_versions_json`. Edits after complete keep original `completed_at`; snapshot refresh is explicit only.

---

## M. Weekly review

Route `/review/weekly?week=YYYY-MM-DD` (NY week start Monday).

Summary from the same analytics stack: trades, net P&L, avg/median R, profit factor, win rate, best/worst day, max drawdown, avg MFE, exit efficiency, R left, coverage percents.

Pattern panels: descriptive “Observed this week” via existing report/research filters (day, time, setup quality, signal RVOL, retracement). **No** “you should stop trading X.”

`[Open in Research Lab]` = navigate with corresponding filter query. No duplicated research math.

Prompts: what improved / repeated mistake / easiest setups / Research Lab candidates / next-week focus.

`weekly_reviews` snapshot on complete, same edit rules as daily.

History list at `/reviews`.

---

## N. Settings

`app_preferences` key-value (JSON values). **Secrets stay environment variables** (`LTA_ALPACA_*`). Never in preferences, job payloads, or backup manifests.

User-visible: inbox/archive/backup paths (display + optional override), Auto Process Inbox, EOD enabled/time, automatic backup, retention, expected daily inputs, notifications, no-trade helper.

Path validation: writable, normalized absolute internally, no traversal from API input.

---

## O. Notifications

Optional browser Notification API. Default **important only**: EOD complete, needs attention, backup failed. Not per-file.

---

## P. Security

- Path traversal blocked on inbox, archive, screenshots, restore.
- Attachment allow-list MIME + magic-byte sniff.
- No API keys in frontend.
- No secrets in `payload_json` or `backup_manifest.json`.
- Journal notes not written to INFO logs in full.
- Restore confirmation required.

---

## Q. Crash recovery

On startup:

1. Jobs `RUNNING` → `INTERRUPTED`.
2. Retry if the failed step is idempotent (all downstream services are).
3. Resume remaining pipeline steps; do not blindly re-import if the file event is already `IMPORTED` / `IMPORT_SUCCESS_ARCHIVE_PENDING`.

---

## R. Performance

- Watcher idle ≈ 0 (OS events; poll fallback interval 2s).
- One worker.
- Backup async via worker (does not block request thread beyond enqueue).
- Enable WAL + `busy_timeout=5000` so UI reads do not hit “database is locked”.
- Workflow/journal queries indexed by date, trade_id, status.
- 10-file / 10k-trade daily workflow: **report** timings; no brittle sub-second CI gate.

---

## S. Tests

Backend `tests/test_step_10_*.py` covering spec items 115–142, 144–145:

stability, duplicate file, overlapping OH, multi-file debounce, unknown file, timezone required, crash recovery, archive failure, pipeline partial, disabled AUTO, no-trade day, EOD NY vs machine TZ, DST wall clock, WAL backup, checksum, corrupted backup, restore roundtrip, PRE_RESTORE, path traversal, screenshot hash, daily snapshot immutability, weekly reuse of analytics, journal search, orchestration spies on existing services, manual risk survives, candidate rule immutability, open trade not excursion-finalized, no secrets in payload/manifest.

Frontend: Workflow, review, journal, tags, screenshot controls, settings, backup preview. Do not test watchdog internals in React.

Soak (optional): 30 NY days overlapping exports — unique fingerprints, no orphan RUNNING jobs, retention respected.

---

## T. Known limitations

1. Scheduler and watcher run only while the backend process is alive.
2. No broker / webhook / Pine / risk auto-trading.
3. No cloud backup sync.
4. No OCR. No AI journal assistant (stub only).
5. No FTS5 / semantic search.
6. No exchange-holiday calendar (Step 4 has none).
7. Research refresh is a no-op; forward samples update when the user opens a rule.
8. Pipeline does not invoke `TradeRebuildService` (identity / journal FK).
9. Excursion copilot exit remains unavailable (Step 8 stub).
10. Custom Downloads-folder watch is not in v1.
11. WAL is new; first start may create `-wal`/`-shm` beside the DB.
12. User-data real-export validation remains a manual checklist (spec §155).

---

## Implementation map

| Piece | Module |
|-------|--------|
| Paths | `app/paths.py` + `settings.data_dir` |
| Models | `app/db/models/automation.py`, `journal.py`, `reviews.py` |
| Preferences | `app/services/preferences.py` |
| Classify | `app/services/automation/classify.py` |
| Jobs / worker | `app/services/automation/jobs.py`, `worker.py` |
| Inbox | `app/services/automation/inbox.py` |
| Pipeline | `app/services/automation/pipeline.py` |
| Completeness | `app/services/automation/completeness.py` |
| Watcher / scheduler | `app/services/automation/watcher.py`, `scheduler.py` |
| Journal | `app/services/journal/` |
| Reviews | `app/services/reviews/` |
| Backup | `app/services/backup/` |
| API | `app/api/workflow.py`, `journal.py`, `reviews.py`, `backups.py`, `settings.py` |
| CLI | `app/cli/process_inbox.py`, `finalize_day.py`, `backup.py`, `restore_backup.py` |
| UI | `WorkflowPage`, `DailyReviewPage`, `WeeklyReviewPage`, `ReviewHistoryPage`, `SettingsPage`, trade journal panel |

### API (existing conventions)

`GET/POST /api/workflow/*`, `/api/journal/*`, `/api/reviews/daily/{date}`, `/api/reviews/weekly/{week}`, `/api/backups`, `/api/settings`.

### Docs to write after implementation

`AUTOMATION_WORKFLOW.md`, `INBOX_AND_FILE_DETECTION.md`, `DAILY_WORKFLOW.md`, `JOURNAL.md`, `DAILY_REVIEW.md`, `WEEKLY_REVIEW.md`, `BACKUP_AND_RESTORE.md`, `DATA_DIRECTORY.md`, `AUTOMATION_TROUBLESHOOTING.md`, `STEP_10_COMPLETION.md`. Update ARCHITECTURE, DATABASE_SCHEMA, README.

---

## Definition of done

Matches the product checklist (inbox, watcher, stability, content detect, persistent queue, crash recovery, idempotent overlapping exports, quarantine, archive-without-reimport, coalesced pipeline, reused services, configurable expected inputs, no-trade day, EOD NY/DST, workflow UI, journal/tags/screenshots, daily/weekly reviews + snapshots, SQLite backup + restore + PRE_RESTORE, settings/secrets, health, open-trade + manual-risk + candidate-rule preservation, all prior-step regressions, frontend tests, production build).

**Out of scope:** broker execution, cloud sync, automatic strategy modification, Step 6 compliance scoring, OCR, AI recommendations.
