# Inbox and File Detection

Drop files into the app-owned **inbox/** only. Downloads is not watched.

## Stability

A file is ignored until size and mtime are unchanged for `LTA_FILE_STABLE_SECONDS` (default 2). Temporary names (`.tmp`, `.part`, `.crdownload`, leading `.`) are ignored.

## Content detection

Extension is not identity. `.csv` is not assumed to be Order History; `.txt` is not assumed to be Pine.

| Detected type | Detector |
|---------------|----------|
| ORDER_HISTORY | existing `TradingViewManualParser` |
| ACTIVITY_LOG | existing `TradingViewActivityLogParser` |
| AUTO_STRATEGY_TESTER | existing `TradingViewStrategyParser` |
| PINE_LOG | `RECORD_TYPE` + `SIGNAL_ID` + `SCHEMA_VERSION` header, then `parse_pine_log` |

`UNKNOWN_FORMAT`, `AMBIGUOUS_FORMAT`, `TIMEZONE_REQUIRED`, missing columns, and parser errors go to **quarantine/** with `NEEDS_REVIEW`. Automation never guesses a timezone.

## Idempotency

File SHA-256 is a first-layer skip. Execution and trade fingerprints remain authoritative, so overlapping daily exports (Tue contains Mon+Tue) import only new rows.

## Archive

After a successful import of an app-owned inbox file, the file moves to `archive/YYYY/MM/DD/`. Name collisions get a hash suffix. If the move fails after the DB commit, status is `IMPORT_SUCCESS_ARCHIVE_PENDING` and archival is retried without reimporting.
