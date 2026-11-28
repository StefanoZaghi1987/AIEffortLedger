---
id: TASK-16
title: 'Task 16: Survey of native logs (gate G2)'
status: Done
assignee: []
created_date: '2026-11-22 11:33'
updated_date: '2026-11-27 12:03'
labels: []
milestone: m-9
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/claude-code-adapter.md
  - docs/spec/ingestion.md
  - CLAUDE.md
priority: high
ordinal: 1600
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 16 of docs/plans/phase-1-implementation.md exactly as written. Gate G2: the owner makes the copy of the native logs and runs the survey, or allows the run; the findings need the owner in ruling panels. Privacy: no transcript text leaves the snapshot; prototype/out/ only.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and the research note holds ratios only
- [x] #2 The ruling panel ran; each ruling became a spec sentence and its To-be-confirmed item is deleted
<!-- AC:END -->



## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Step 1 complete (commit 765390f, review clean 2026-11-23): survey script + invented-folder self-test, no-leak property verified. Steps 2-4 blocked at gate G2: awaiting the owner's snapshot run of prototype/survey.py on real native logs and the rulings it feeds (research note, fixtures, spec sentences).

2026-11-27: milestone m-9 (Ruling 136) — a gate task lives in the milestone of the end, beside Task 66 (gate G5); milestone m-2 closes with its twelve done tasks.

2026-11-27 10:52: gate G2 EXECUTED on the owner's allowance (Ruling 137; survey on 425 files, 139 571 records, ratios only; research note 0600e90; four items closed, three keep sample triggers); Step 4 fixtures 70a4119 + 725eab4, merged 98ec0f3 (874 OK on the tip, style 0). The ruling panels became autonomous rulings under the owner's standing no-questions directive. Task 16 closes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 16 complete, merged as 98ec0f3 (with the G2 documents in 0600e90). Step 1 (765390f, 2026-11-23): the survey script with the no-leak property, self-tested on invented folders. Gate G2 executed 2026-11-27 on the owner's allowance: the controller copied the native logs outside the repository (cc/ 386 files; desktop/1-23 39 files) and ran the survey — 425 files, 139 571 records, 0 invalid lines; the output holds ratios only. Ruling 137: four To be confirmed items of claude-code-adapter.md closed (the size-counter fallback moved into the body; every interruption writes its user record — 6 prefix records, no counter-example in 28 127; the subagent link sentence for the text result — Agent results 350 object/13 text/74 absent, nested 0; the MultiEdit/NotebookEdit keys stay as the edit table pins them — 0 calls), three keep their "with a real sample" triggers. Step 4: the invented-text fixture of the text result (70a4119) and the adapter test that pins the ruled sentence cell by cell (725eab4). 874 tests on the merged tip, style 0. The snapshot copy of the logs was deleted after the run.
<!-- SECTION:FINAL_SUMMARY:END -->
