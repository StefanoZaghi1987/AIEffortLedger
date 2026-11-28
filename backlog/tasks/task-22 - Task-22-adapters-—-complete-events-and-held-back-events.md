---
id: TASK-22
title: 'Task 22: adapters — complete events and held-back events'
status: Done
assignee: []
created_date: '2026-11-22 11:34'
updated_date: '2026-11-27 12:03'
labels: []
milestone: m-2
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/ingestion.md
  - docs/spec/claude-code-adapter.md
priority: high
ordinal: 2200
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 22 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
adapters — complete events and held-back events: completeness.py with complete_events (exact signature; response waits for later record, tool call for result, provider tool for its response, subagent for its link; settled sessions store the incomplete remainder), read_sessions wiring disclosed as expected (settled propagation, held_back on held-or-unread), store idempotence proven end-to-end by a two-read pipeline test with controlled mtimes. Review approved first round; id-less-response fallback coverage gap deferred. 86/86 focused, 185/185 suite, style 0 at fa01388 on stream/adapter.
<!-- SECTION:FINAL_SUMMARY:END -->
