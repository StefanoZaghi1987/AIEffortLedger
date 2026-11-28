---
id: TASK-42
title: 'Task 42: Speed probe of the timesheet figures'
status: Done
assignee: []
created_date: '2026-11-22 11:36'
updated_date: '2026-11-27 22:47'
labels: []
milestone: m-6
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
  - docs/spec/product.md
priority: high
ordinal: 4200
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 42 of docs/plans/phase-1-implementation.md exactly as written: the speed probe of the timesheet figures, without reports and cli.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The script prints two times with --days 1 --sessions 2 --lines 50
- [x] #2 The default run's seconds go to the owner; a second run above 5 s stops the task for the owner
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Speed probe of the timesheet figures (tests/benchmark.py), built on stream/declared. Checkpoint commit fafd4f1 (suite 467 tests OK, style 0): the small run prints two times (0.140 s and 0.027 s); the default run fell from 375.281 s to 65.995 s after three performance fixes, still above the 5 s criterion, which went to the owner as a flag. Review approved first round; evidence: the Task 42 entries of progress.md (no report file).

Re-measured at the owner's panel ruling (Ruling 176 (8), 2026-11-27): the criterion's protocol ran — the 65.995 s went to the owner as a flag and the task stopped for the owner (Ruling 83's three targets stand). The re-measured product criteria of product.md (10) now pass: the daily timesheet of one month holds 20.607 s against its 30 s at the tip 5072db2. Evidence: docs/research/benchmark-g5-2026-11.md.
<!-- SECTION:FINAL_SUMMARY:END -->
