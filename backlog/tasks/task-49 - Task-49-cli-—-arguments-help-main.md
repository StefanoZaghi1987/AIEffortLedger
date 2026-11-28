---
id: TASK-49
title: 'Task 49: cli — arguments, help, main'
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
ordinal: 4900
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 49 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
cli — arguments, help, and main (arguments.py), built on stream/cli. Checkpoint commit ec49679 (13 new tests, suite and style green); review approved first round; a later fix fc0bfc6 makes the language of the output follow the default of the person configuration. Evidence: task-49-report.md, task-49-fix-report.md.
<!-- SECTION:FINAL_SUMMARY:END -->
