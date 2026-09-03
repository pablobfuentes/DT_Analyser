# Automation Workflow

Step 10 orchestrates existing services. It does not recalculate P&L, R, signals, or reconstruction.

## Single automation owner

Across processes sharing one data directory there is exactly one automation owner.

`{LTA_DATA_DIR}/automation.lock` is acquired at startup. Only the lock holder starts the filesystem watcher, the automation worker, and APScheduler. Other processes may serve HTTP as **STANDBY / OWNED BY ANOTHER PROCESS**. Workflow health shows `Automation Ownership: OWNER` or that standby string.

The lock is released on clean shutdown. A crash cannot leave permanent stale ownership because the OS drops the lock with the process handle. This is in addition to execution/signal idempotency — it does not replace it.

## Worker

One in-process worker (on the owning process only) reads `automation_jobs`. The watcher and APScheduler only **enqueue**. FastAPI `BackgroundTasks` are not the job store.

Statuses: PENDING, RUNNING, SUCCESS, PARTIAL, FAILED, RETRY, INTERRUPTED, CANCELLED.

On startup, leftover RUNNING jobs become INTERRUPTED and are retried when safe (downstream steps are idempotent).

## Pipeline (`automation_runs` / `automation_run_steps`)

1. INPUT_DETECTION  
2. TRADE_IMPORT — `ImportService.commit_import` / Pine `commit_import`  
3. RECONSTRUCT — skipped (already inside import; a second rebuild would break journal `trade_id`)  
4. PINE_IMPORT — recorded with the import pass  
5. SIGNAL_MATCHING — `match_signals_batch`  
6. RISK_RECALC — `RiskService.recalculate_many` (manual overrides survive)  
7. MARKET_ENRICHMENT — `MarketEnrichmentService.enrich(missing)`  
8. EXCURSION_ENRICHMENT — closed trades only  
9. RESEARCH_REFRESH — no-op (forward samples are query-time)  
10. REVIEW_SNAPSHOT — live metrics for the NY date  
11. BACKUP — after EOD if automatic backup is on  

Files arriving within the debounce window share one run: N imports, one downstream pass.

## Scheduler limitation

The in-process EOD job (default 20:15 America/New_York, **Monday–Friday**) runs only while the owning backend is up. There is no exchange-holiday calendar; a holiday weekday run may no-op. For a closed UI use:

```
python -m app.cli.process_inbox
python -m app.cli.finalize_day --date YYYY-MM-DD
python -m app.cli.backup
python -m app.cli.restore_backup BACKUP_ID --verify-only
python -m app.cli.restore_backup BACKUP_ID --confirm
```

## Never

Place orders, change Pine, change candidate rules, change risk automatically, delete history silently, infer missing executions, or fabricate files.
