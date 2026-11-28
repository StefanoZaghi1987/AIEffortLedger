---
id: TASK-27
title: 'Task 27: days — local days'
status: Done
assignee: []
created_date: '2026-11-22 11:34'
updated_date: '2026-11-27 12:03'
labels: []
milestone: m-3
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/metrics.md
  - docs/spec/configuration.md
  - docs/spec/command-line.md
priority: high
ordinal: 2700
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 27 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order. Last task of the milestone: the checkpoint asks gate G6.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
days — local days: days.py with use_tzdata_only / tzdata_version / LocalDays (local_day, day_parts, local_instant, parse_day) and the three stop errors (no_local_day {instant}, dated_fact_conflict {first,second}, time_zone_missing); the composable transition walk (history segments × offset runs) hand-verified by the reviewer against every normative value (DST 23 h/25 h, the 28 h day-start-change day, both west-journey interval lists, first-occurrence/after-change resolutions). Review approved first round; parsing-leniency family escalated (To be confirmed in command-line.md); five polish minors deferred. 13/13 focused, 261/261 suite, style 0 at 3dbbae6 on stream/days — DAYS STREAM DONE.
<!-- SECTION:FINAL_SUMMARY:END -->
