---
id: TASK-42
title: 'Task 42: Speed probe of the timesheet figures'
status: To Do
assignee: []
created_date: '2026-11-22 11:36'
labels: []
milestone: m-6
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
  - docs/spec/product.md
priority: high
ordinal: 4200
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 42 of docs/plans/phase-1-implementation.md exactly as written: the speed probe of the timesheet figures, without reports and cli.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The script prints two times with --days 1 --sessions 2 --lines 50
- [ ] #2 The default run's seconds go to the owner; a second run above 5 s stops the task for the owner
<!-- AC:END -->
