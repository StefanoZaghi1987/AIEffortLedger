---
id: TASK-58
title: 'Task 58: Report tests of setup, schedule, ingest, and machine label'
status: Done
assignee: []
created_date: '2026-11-22 11:39'
updated_date: '2026-11-27 12:06'
labels: []
milestone: m-8
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
priority: high
ordinal: 5800
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 58 of docs/plans/phase-1-implementation.md exactly as written: expected files for setup, schedule, ingest, and machine label, English and Italian.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every expected file is written by hand with the fixed now, new_uid, and version of Task 54
- [x] #2 The code is fixed where a test fails, never the expected file without support
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Report tests of setup, schedule, ingest, and machine label, with expected files written by hand on the fixed now, new_uid, and version of Task 54. Checkpoint commit 45e3237 plus four fixes (1666ed2, efa9934, c6c5706, e79f151; one two-line change of language.py with its test); 708 tests OK, style 0 after three review rounds. Evidence: task-58-report.md, task-58-review-1.md to task-58-review-3.md.
<!-- SECTION:FINAL_SUMMARY:END -->
