---
id: TASK-25
title: 'Task 25: index — update, chained hash, broken lines, the winning copy'
status: Done
assignee: []
created_date: '2026-11-22 11:34'
updated_date: '2026-11-27 12:03'
labels: []
milestone: m-3
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
  - docs/spec/event-schema.md
  - docs/spec/ingestion.md
priority: high
ordinal: 2500
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 25 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
index — update, chained hash, broken lines, the winning copy: index.py with INDEX_FORMAT, SegmentState, BrokenLine, IndexUpdate, IndexBusy (LockUnavailable precedent), LocalIndex (WAL, 30 s busy timeout) with update/rebuild/segment_states/broken_lines/has_newer/has_key/counts and the private _winning merge point; binding schema, INSERT OR IGNORE, PK (segment, offset), BEGIN IMMEDIATE before the stored-state read, first_number resume. Review approved first round; three minors (connection close + temp-folder leak, atomic _wipe, COMMIT failure mode) ride Task 26 per reviewer suggestion. 13/13 focused, 261/261 suite, style 0 at 739aeab on stream/index.
<!-- SECTION:FINAL_SUMMARY:END -->
