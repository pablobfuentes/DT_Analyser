# Data Directory

All Step 10 files live under one configurable root. Nothing is hard-coded to the git repo.

## Resolution (`LTA_DATA_DIR`)

1. If `LTA_DATA_DIR` is set, that path is used.
2. Else if `./data` already exists (current installs), it is kept so the existing SQLite file is not abandoned.
3. Else a platform default:
   - Windows: `%LOCALAPPDATA%/LocalTraderAnalyzer`
   - macOS: `~/Library/Application Support/LocalTraderAnalyzer`
   - Linux: `~/.local/share/local-trader-analyzer`

The database URL (`LTA_DATABASE_URL`) is independent and still defaults to `sqlite:///./data/trader_analyzer.db`.

## Layout

```
{data_dir}/
  trader_analyzer.db     # if using the default URL beside ./data
  automation.lock        # OS file lock — only the holder starts watcher/worker/scheduler
  uploads/               # manual Import page staging
  inbox/                 # drop TradingView / Pine files here
  archive/YYYY/MM/DD/    # successfully processed inbox files
  quarantine/            # needs review — never deleted
  screenshots/YYYY/MM/   # journal images (relative paths in DB)
  backups/{backup_id}/   # SQLite-consistent copies + manifest
  logs/
  paste/                 # archived pasted Pine text
```

`automation.lock` is an inter-process exclusive lock (Windows `msvcrt.locking`, Unix `fcntl.flock`). PID text inside the file is informational only. A crashed process does not leave permanent ownership — the OS releases the lock when the handle dies. Extra uvicorn workers and a second backend against the same `LTA_DATA_DIR` may serve HTTP as **STANDBY**; they must not start automation.

Settings and the Workflow page display these paths. There is no cloud dependency.
