---
id: TASK-18
title: 'Task 18: adapters — records of the agent to events'
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
priority: high
ordinal: 1800
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 18 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
adapters — records of the agent to events: map_session agent rows, event_identifiers, TOOL_CATEGORIES (26 names). Fix round 1 (8c4e67f) addressed all three review-round-1 findings (malformed-record guards via _message_of/_native_id_of, shared _model_of, invocation_of restored); scoped re-review clean. 33/33 focused, 132/132 suite, style 0 at 8c4e67f on stream/adapter. Deferred minors and the invalid_record prose correction are recorded in the SDD ledger.
<!-- SECTION:FINAL_SUMMARY:END -->
