# Step 9 Completion Report — Advanced Research Lab (amended)

**Date:** 2026-09-02  
**Status:** Hardening pass complete. Step 9 closed for review. **Step 10 not started.**

Exploratory only. No proven-edge claims. No automatic Pine / risk / order changes.

---

## Hardening fixes (this pass)

### 1. Forward-sample cutoff — BLOCKER fixed

Canonical membership:

`trade.entry_time_utc > candidate_rule.cutoff_at` (strict)

A trade entered before the rule existed is Research Sample even if it exits afterward.

v1 decision timestamp = `entry_time_utc`. A later signal-level decision time is a documented future extension.

### 2. Retrospective rules cannot enter FORWARD_TESTING — BLOCKER fixed

POST_ENTRY / EXIT / END_OF_DAY / POST_EXIT filters may be saved as Saved Cohort, Research View, Pattern Snapshot, or Candidate Rule **RESEARCH**.

`status = FORWARD_TESTING` is rejected:

HTTP 400 `{ "code": "RETROSPECTIVE_RULE_NOT_FORWARD_TESTABLE", "keys": [...], "message": "This pattern uses information unavailable by entry and cannot be forward-tested as an entry rule." }`

Frontend disables **Start Forward Testing** with the same copy.

### 3. KNOWN BY ENTRY terminology

Stored enum remains `PRE_ENTRY_ONLY`. UI label: **KNOWN BY ENTRY**.

Allows PRE_ENTRY + SIGNAL + ENTRY (known no later than entry, including fill variables). Not a redesign.

### 4. Heatmap ticker Top-N

Enforced. Default 20 (`LTA_RESEARCH_HEATMAP_TICKER_TOP_N`). Remainder aggregated as **Other** with coverage metadata. Other is not a click-to-cohort filter.

### 5. Profit Factor CI

**Deferred.** Display PF + n. No normal-theory CI. Plan and `RESEARCH_STATISTICS.md` reconciled.

### 6. Bootstrap limitation

Documented: IID/exchangeable exploratory bootstrap. May understate uncertainty under serial dependence. No implementation change. Block/session bootstrap is future work.

### 7–8. Performance

See matrix and timing-test decision below.

### 9. Real-data validation

**USER-DATA VALIDATION PENDING.** Does not block code closure.

---

## Architecture (unchanged)

`/research` workspace. Backend `app/services/research/*`. One annotated load per request. Decimal in persistence. Graphs / Exit Analyzer / Risk / Signals paths not used as Research compute.

**24 research variables:** 14 known-by-entry, 10 retrospective-only.

---

## 10k standardized matrix

One workload: 10,000 closed trades, `_annotate_trades` + `attach_numeric`, then research transforms on that universe.

| Operation | Time (this machine) |
|-----------|---------------------|
| Base annotated universe load | 2.871s |
| Cohort A/B compare | 1.211s |
| Scatter | 0.296s |
| Heatmap | 0.082s |
| Rolling 20-trade | 0.255s |
| Distribution / ECDF | 0.021s |
| Outlier robustness | 0.174s |
| 3-factor grouping | 0.107s |
| Bootstrap on R-qualified population (n=10,000) | 0.405s |

Product target remains “practical locally.” Operations are **not** required to be &lt;1s. Pathological CI ceiling is 60s/operation.

---

## Timing-test decision (item 8)

Investigation: Research Lab does not hook `get_reports` or `RiskService`. Isolated re-runs of the old 5s / 8s asserts were 6.08s and 8.40s on this hardware after Step 9 — same order as before a code-path change.

**Decision:** hardware-sensitive thresholds, not a Research Lab regression.

| Layer | Behavior |
|-------|----------|
| Functional | Always assert correctness (trade counts, parse/import status). |
| Benchmark target | Printed (`BENCH … target=5.0s` / `risk/reports<8000ms`). Not a brittle fail. |
| Gross regression ceiling | 45s (Graphs 10k and Step 5/7 smoke). Catches pathological slowdown only. |

---

## Tests and build

| Suite | Result |
|-------|--------|
| Step 9 backend | **38 passed** (including 10k matrix) |
| Full functional backend | **319 passed**, 0 failed |
| Frontend | **38 passed** (5 files) |
| Production build | **passed** (`tsc && vite build`) |

---

## Definition of Done (hardening re-run)

| Item | Result |
|------|--------|
| Candidate Rule cutoff uses `entry_time_utc > cutoff_at` | PASS |
| No pre-cutoff entry in Forward Sample | PASS |
| Retrospective rule forward-test prevention | PASS |
| Known-by-entry timing (enum unchanged) | PASS |
| Heatmap ticker Top-N (20 + Other) | PASS |
| PF CI documentation reconciled (deferred) | PASS |
| Bootstrap IID limitation documented | PASS |
| 10k performance matrix | COMPLETE |
| Full functional backend | PASS (319) |
| Frontend | PASS (38) |
| Production build | PASS |
| Steps 1–5, 7–8, 9 regressions | PASS |

---

## Deferred to Step 10

Folder watcher, automatic daily imports, scheduled backup, journal/screenshot workflow, AI notes, weekly review automation.

**Do not begin Step 10.**
