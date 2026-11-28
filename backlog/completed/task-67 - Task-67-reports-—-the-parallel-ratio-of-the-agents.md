---
id: TASK-67
title: 'Task 67: reports — the parallel ratio of the agents'
status: Done
assignee: []
created_date: '2026-11-25 16:04'
updated_date: '2026-11-26 12:39'
labels: []
milestone: m-8
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/metrics.md
  - docs/spec/command-line.md
  - GLOSSARY.md
priority: high
ordinal: 6700
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 67 of docs/plans/phase-1-implementation.md exactly as written: the parallel ratio beside every agent time of a holder, in the JSON documents and in the text, in English and Italian. Last task of the milestone: the checkpoint asks gate G6.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The parallel ratio stands beside the agent time of the person, of each project, and of each work item in `report day`, and of the context in `timesheet <day>`
- [x] #2 Every expected file is corrected by hand, English and Italian, and the full suite is green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-26 11:52 — Dispatched (opus) on `stream/cli` from 83b74b9 (Task 60 complete: 770 tests OK, style 0). A read-only re-check of the addenda against everything that landed since they were written (task-67-recheck.md: 35 items, nothing gone, 6 collisions resolved, file set +2) became the Addendum of 2026-11-26; dispatch dated task-67-dispatch-2026-11-26.md.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 67 complete on stream/cli: 25c4c14 (65 files, +722/−216) + fix round c618b2e (two docstring clauses, Ruling 119). The parallel ratio — agent time ÷ (Supervised + Unattended) from the exact millisecond figures, absent when the holder has no agent time — stands beside the agent time of the person, of each project and of each work item of `report day`, and of the context of `timesheet <day>`: the JSON key right after `agent_time`, a text column and a figure line with two decimals, the label in English and Italian. The readers of the frozen reports give the key its kind and never require it, so a frozen report written before the task is read and its ratio shows as a one-sided difference row. The renames of Ruling 74 (`_number`, `_decimal`) cover every use; the fixture store `parallel_agents` holds two agents whose turns overlap (person ratio 1.5); 40 expected files corrected by hand and 8 new, in both languages; the two › To be confirmed items closed (Rulings 54 and 62). Suite 782 OK (base 770), style 0; review round 1 Approved 0/0/2, both Minors fixed in c618b2e. Escalations 961-962 RESOLVED. Last task of milestone m-8: its checkpoint asks gate G6 (the owner's).
<!-- SECTION:FINAL_SUMMARY:END -->
