---
id: TASK-21
title: 'Task 21: adapters — subagents, copies of one record'
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
ordinal: 2100
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 21 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
adapters — subagents, copies of one record: subagents.py (deduplicate keeps the copy in the file of the agent the record names, record_copies_differ names fields only; link_subagents sets parent_agent_id + subagent_mode), wired into read_sessions (disclosed minimal reading.py hunk), exported from both surfaces. Review approved first round (no Critical/Important); four coverage/polish minors deferred to the ledger; the plan's Files-line imprecision flagged. 78/78 focused, 177/177 suite, style 0 at ea6e0a6 on stream/adapter.
<!-- SECTION:FINAL_SUMMARY:END -->
