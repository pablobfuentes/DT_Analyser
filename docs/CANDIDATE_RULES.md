# Candidate Rules

A Candidate Rule is a **saved research concept**. It never modifies Pine, Copilot parameters, orders, or risk.

## Status

`RESEARCH` | `FORWARD_TESTING` | `RETIRED`

There is no `PROVEN` status.

## Stored fields

name, description, filter_json, research_mode, research_start, research_end, cutoff_at, created_at, rule_version, status, parent_id, statistics_version, bootstrap seed/iterations, notes.

`cutoff_at` is set at creation and is the forward-sample boundary.

## Versioning

Editing calls `POST /api/research/candidate-rules/{id}/revise`.

That inserts version N+1 with `parent_id` pointing at the previous row. The original filter JSON and `cutoff_at` are not rewritten.

## Forward sample

`POST /api/research/candidate-rules/{id}/evaluate`

**Forward Sample (v1):** `trade.entry_time_utc > cutoff_at` (strict).

`entry_time_utc` is the decision timestamp. A trade that entered before the rule existed is Research Sample even if it exits afterward.

Example: rule created 10:00. Entry 09:55 / exit 10:08 → Research. Entry 10:01 / exit 10:08 → Forward.

A future signal-level validation architecture may use a more precise decision time (armed/signal bar). Not in v1.

Research Sample and Forward Sample are never merged by default.

## Retrospective filters are not forward-testable

Filters whose timing is POST_ENTRY, EXIT, END_OF_DAY, or POST_EXIT (MFE, MAE, Actual R, full-day RVOL, day type, …) may be saved as a Saved Cohort, Research View, Pattern Snapshot, or a Candidate Rule in status **RESEARCH**.

They **cannot** transition to `FORWARD_TESTING`.

API: HTTP 400 `{ "code": "RETROSPECTIVE_RULE_NOT_FORWARD_TESTABLE", "keys": [...], "message": "This pattern uses information unavailable by entry and cannot be forward-tested as an entry rule." }`

Observed Change = Forward Avg R − Research Avg R. Label: **Observed Change**, not Decay.

## Pattern shortlist

★ Candidate Pattern stores an immutable metrics snapshot at star time.

Later: Original Research Snapshot vs Current Results.

## Saved artifacts

| Table | Purpose |
|-------|---------|
| `saved_cohorts` | named filter sets |
| `research_views` | full workspace (scope, A/B, chart, mode) |
| `candidate_rules` | versioned rules + cutoff |
| `pattern_snapshots` | starred cells/rows with frozen metrics |
