---
id: TASK-19
title: 'Task 19: adapters — records of the person and the system to events'
status: Done
assignee: []
created_date: '2026-11-22 11:33'
updated_date: '2026-11-27 12:03'
labels: []
milestone: m-2
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/claude-code-adapter.md
  - docs/spec/event-schema.md
  - docs/spec/product.md
priority: high
ordinal: 1900
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 19 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
adapters — records of the person and the system to events: prompt/scripted/origin-kind/parent/queued/interruption rows, the invalid_record prose correction (both languages), unconditional origin classification with dedup, Ruling 13 + Ruling 14 precedence pinned by tests. Two fix rounds (0a77b57, 347b178); re-review round 2 clean. 55/55 focused, 154/154 suite, style 0 at 347b178 on stream/adapter. Deferred minors and the out-of-scope observations are recorded in the SDD ledger.
<!-- SECTION:FINAL_SUMMARY:END -->
