---
id: TASK-61
title: 'Task 61: Store tests with two machines'
status: Done
assignee: []
created_date: '2026-11-22 11:39'
updated_date: '2026-11-27 12:06'
labels: []
milestone: m-9
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
priority: high
ordinal: 6100
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 61 of docs/plans/phase-1-implementation.md exactly as written: the store tests with two machines and a file-sync delay.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 A fix goes into one module with a test there; a fix across modules stops the task for the owner
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 61 complete on stream/machines: 8b35f6d (the store tests with two machines; the consolidated world of tests/support.py) + fix fd54abc (copy_segments delivers the segments of the source machine alone — Ruling 52; six minors). 668 tests OK, style 0. Review 1 Needs fixes (I1), review 2 clean. Ruling 51: ingest exits 0 on a broken line. Merges into stream/cli after Task 57.
<!-- SECTION:FINAL_SUMMARY:END -->
