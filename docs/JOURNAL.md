# Journal

Notes are written by you. The app does not infer thesis, psychology, or rule violations.

## Entries

Types: TRADE_NOTE, DAILY_NOTE, WEEKLY_NOTE, GENERAL.

Trade Detail → Journal: thesis, why entered/exited, what went well, what you would change, additional notes, and a manual **Followed my plan?** field (YES / NO / PARTIAL / NOT_ASSESSED). This is not Step 6 compliance scoring.

## Tags

User-defined, case-insensitive unique names. Filter/search locally. Tags are not injected into Step 3 Graphs.

## Screenshots

PNG / JPEG / WEBP only. Acceptance requires **both** an allowlisted extension (`.png` / `.jpg` / `.jpeg` / `.webp`) **and** matching magic bytes. Filename and `Content-Type` are never trusted alone. `../` traversal, absolute paths, double extensions, and renamed executables are rejected. Stored under `screenshots/YYYY/MM/{sha256}.ext`. The database keeps a relative path. Duplicate bytes reuse the same file. Delete removes the file only when no other row references it. No OCR.

## Search / export

SQLite `LIKE` on notes, captions, and tags. CSV and Markdown export omit image bytes.
