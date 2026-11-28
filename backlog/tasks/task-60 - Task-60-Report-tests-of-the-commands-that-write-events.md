---
id: TASK-60
title: 'Task 60: Report tests of the commands that write events'
status: Done
assignee: []
created_date: '2026-11-22 11:39'
updated_date: '2026-11-26 10:48'
labels: []
milestone: m-8
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
priority: high
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 60 of docs/plans/phase-1-implementation.md exactly as written: expected files for the commands that write events, English and Italian.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every expected file is written by hand with the fixed now and new_uid of Task 54
- [x] #2 The code is fixed where a test fails, never the expected file without support
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-26 — Dispatched (opus) on `stream/cli` from `36b3478` (after the fix round 4 of Task 59 and the merges of `stream/purge` and `stream/classes`; 746 tests OK, style 0). The addenda carry an addendum of 2026-11-26: `wrong_use` is replaced after this task, by Task 74.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 60 complete on `stream/cli`: c2b8e52 (the 14 expected pairs, English and Italian, of the commands that write events, and the code fixes of Rulings 43-47 and 63-65), fix round 1 8c459c2 (Rulings 109-111: the fixture's timesheet confirmation one hour before FIXTURE_NOW; `Attribution.repository_hints` and `work_item_name`, one rule written once; an end of the input is no answer, one `_ask` path, the clause of command-line.md), fix round 2 83b74b9 (Ruling 113, one docstring clause). Review round 1 Needs Fix (1 Important, answered), round 2 Approved (0 Critical, 0 Important, 1 Minor, fixed). 770 tests OK, style 0 on 83b74b9. Escalations 957-958 resolved, confirmed by the review.
<!-- SECTION:FINAL_SUMMARY:END -->
