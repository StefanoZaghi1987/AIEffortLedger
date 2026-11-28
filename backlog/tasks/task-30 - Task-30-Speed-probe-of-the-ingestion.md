---
id: TASK-30
title: 'Task 30: Speed probe of the ingestion'
status: Done
assignee: []
created_date: '2026-11-22 11:35'
updated_date: '2026-11-27 22:46'
labels: []
milestone: m-4
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
  - docs/spec/product.md
priority: high
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 30 of docs/plans/phase-1-implementation.md exactly as written: the speed probe of the ingestion, isolated from the machine's real logs, store, and configuration.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The script runs with --days 1 --sessions 2 --lines 50 and prints one time
- [x] #2 The default run's seconds go to the owner; a second run above 60 s stops the task for the owner
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Speed probe of the ingestion: tests/benchmark.py, built on stream/ingestion. Checkpoint commit 796a645 (suite 318 tests OK, style 0); the default run took 43.088 s, below the 60 s target, on one development machine. Review approved first round; evidence: task-30-report.md.

Re-measured at the owner's panel ruling (Ruling 176 (8), 2026-11-27): the first ingestion of the G5 benchmark run holds 47.739 s at the tip 5072db2 — under this criterion's 60 s. Evidence: docs/research/benchmark-g5-2026-11.md.
<!-- SECTION:FINAL_SUMMARY:END -->
