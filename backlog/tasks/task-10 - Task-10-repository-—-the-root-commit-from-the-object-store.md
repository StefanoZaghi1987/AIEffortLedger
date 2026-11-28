---
id: TASK-10
title: 'Task 10: repository — the root commit from the object store'
status: Done
assignee: []
created_date: '2026-11-22 11:32'
updated_date: '2026-11-27 12:04'
labels: []
milestone: m-1
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/ingestion.md
priority: high
ordinal: 1000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 10 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
repository — the root commit read from the object store (loose and packed objects, no git command), built on stream/repository. Checkpoint commit a723adc (suite 39 tests OK, style 0); review clean. Evidence: task-10-report.md.
<!-- SECTION:FINAL_SUMMARY:END -->
