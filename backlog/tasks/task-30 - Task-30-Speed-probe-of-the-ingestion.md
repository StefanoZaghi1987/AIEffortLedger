---
id: TASK-30
title: 'Task 30: Speed probe of the ingestion'
status: To Do
assignee: []
created_date: '2026-11-22 11:35'
labels: []
milestone: m-4
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
  - docs/spec/product.md
priority: high
ordinal: 3000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 30 of docs/plans/phase-1-implementation.md exactly as written: the speed probe of the ingestion, isolated from the machine's real logs, store, and configuration.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The script runs with --days 1 --sessions 2 --lines 50 and prints one time
- [ ] #2 The default run's seconds go to the owner; a second run above 60 s stops the task for the owner
<!-- AC:END -->
