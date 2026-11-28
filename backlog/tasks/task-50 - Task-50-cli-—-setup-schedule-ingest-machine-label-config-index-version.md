---
id: TASK-50
title: 'Task 50: cli — setup, schedule, ingest, machine label, config, index, version'
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
priority: high
ordinal: 5000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 50 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cli — the commands setup, schedule, ingest, machine label, config, index, and version (setup_actions.py, store_actions.py), built on stream/cli. Checkpoint commit b24151a (suite 549 tests OK, style 0); review approved first round. Evidence: task-50-report.md.
<!-- SECTION:FINAL_SUMMARY:END -->
