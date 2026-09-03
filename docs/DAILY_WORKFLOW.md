# Daily Workflow

## End of trading day

1. Export **Order History** from TradingView.
2. Put it in the Local Trader Analyzer **Inbox** (`Settings` shows the path).
3. Save a Pine log into the inbox, or paste it on the Import page (paste is archived under `paste/`).
4. Activity Log and AUTO Strategy Tester only if you still use them.
5. Open **Workflow** (`/workflow?date=YYYY-MM-DD`).
6. Confirm processing (or click Process Inbox if auto-process is off).
7. Complete **Daily Review**.

Everything else (match, risk, market, excursions, backup) runs in the pipeline.

## Completeness

Status is by **America/New_York** date, from import batches / Pine batches / file events / trades — not filenames.

Defaults:

| Input | Policy |
|-------|--------|
| Order History | REQUIRED |
| Pine Logs | RECOMMENDED |
| Activity Log | OPTIONAL (not needed after Order History) |
| AUTO | OPTIONAL (disable when the experiment ends) |

**No Trading Today** stops the missing-Order-History nag. Disabled AUTO never warns. No exchange holiday calendar exists in Step 4, so none is invented.

Badges: COMPLETE, PARTIAL, NEEDS_ATTENTION, WAITING_FOR_EOD, NO_TRADES.
