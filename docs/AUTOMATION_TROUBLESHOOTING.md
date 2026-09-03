# Automation Troubleshooting

| Symptom | What to do |
|---------|------------|
| Files sit in inbox | Auto Process Inbox may be off — use **Process Inbox**. Or the file is still being written (wait 2s). |
| File in quarantine | Open Workflow → Needs attention. Timezone required means pick timezone on the manual Import page. Unknown format is not imported. |
| IMPORT_SUCCESS_ARCHIVE_PENDING | Trades are already in the DB. Retry archive; do not re-drop the file expecting a new import. |
| Worker Stopped | Backend process is down. Start uvicorn. Offline machines need CLI + Task Scheduler. |
| RUNNING jobs after a crash | Restart the backend. Jobs are marked INTERRUPTED and retried. |
| Backup failed | Check disk space and `backups/` permissions. Latest verified backup is retained. |
| Restore refused | Checksum or integrity failed. Current DB is left in place. PRE_RESTORE still exists. |
| database is locked | WAL + busy_timeout should cover UI + worker. Avoid opening the live file in another exclusive tool. |
| Missing AUTO warning | Disable AUTO expected input in Settings. |
| Open trade has no MFE | Expected. Excursions run only after the position is closed and imported. |
