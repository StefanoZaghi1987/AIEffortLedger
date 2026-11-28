---
id: TASK-48
title: 'Task 48: cli — output, Context, exit codes, guards'
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
  - docs/spec/architecture.md
priority: high
ordinal: 4800
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 48 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cli — output, Context, exit codes, and guards (cli/__init__.py, cli/output.py), built on stream/cli. Checkpoint commit c4da519 (suite 522 tests OK, style 0, controller verification) plus fix 03a19ef (a stop in JSON mode writes the error line); re-review clean. Evidence: task-48-report.tracked.md.
<!-- SECTION:FINAL_SUMMARY:END -->
