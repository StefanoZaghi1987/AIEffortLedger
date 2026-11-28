---
id: TASK-44
title: 'Task 44: setup — setup steps and the scheduled ingestion'
status: Done
assignee: []
created_date: '2026-11-22 11:37'
updated_date: '2026-11-27 12:06'
labels: []
milestone: m-6
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
  - docs/spec/ingestion.md
  - docs/spec/configuration.md
priority: high
ordinal: 4400
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 44 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order. Last task of the milestone: the checkpoint asks gate G6. The on-machine schtasks check of Step 4 needs the owner's consent.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
setup — the setup steps and the scheduled ingestion (setup.py), built on stream/setup. Checkpoint commit 111b225 (suite 447 tests OK, style 0, controller verification) plus fix 886551b (cron-guarded tests, the shown existing entry, the empty --label); re-review approved. Evidence: task-44-fix-report.md and task-44-fix-review-1.md (no first report file).
<!-- SECTION:FINAL_SUMMARY:END -->
