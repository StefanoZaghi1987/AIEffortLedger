---
id: TASK-52
title: 'Task 52: cli — the figures of days, and timesheet confirmations'
status: Done
assignee: []
created_date: '2026-11-22 11:38'
updated_date: '2026-11-27 12:06'
labels: []
milestone: m-8
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
  - docs/spec/metrics.md
  - docs/spec/architecture.md
priority: high
ordinal: 5200
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 52 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cli — the figures of days and the timesheet confirmations (figures.py), built on stream/cli. Checkpoint commit d8b2ef8 (suite 573 tests OK, style 0); review approved first round. Evidence: task-52-report.md.
<!-- SECTION:FINAL_SUMMARY:END -->
