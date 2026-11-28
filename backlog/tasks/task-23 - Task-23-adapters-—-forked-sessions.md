---
id: TASK-23
title: 'Task 23: adapters — forked sessions'
status: Done
assignee: []
created_date: '2026-11-22 11:34'
updated_date: '2026-11-27 12:03'
labels: []
milestone: m-2
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/claude-code-adapter.md
  - docs/spec/event-schema.md
priority: high
ordinal: 2300
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 23 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
adapters — forked sessions: forks.py with assign_forks (own-records decision, sorted-first tie-break with fork_original_unknown, forked_from on the fork's events at/after the instant, index pass per ADR 0023), reading.py wiring disclosed as expected. Fix round 1 (c74e69b) implemented controller Ruling 15 (shared events written with the original's session_id — origin's own copy preferred, else moved copy rewritten; no duplicate keys in one reading; forked_from guard both passes); re-review clean on all four ruled items. 7/7 TestForks, 192/192 suite, style 0 at c74e69b on stream/adapter. Deferred: index-pass guard pin, pairwise fork-chain labels, O(n²) shared-uid combination.
<!-- SECTION:FINAL_SUMMARY:END -->
