---
id: TASK-20
title: 'Task 20: adapters — size counters (gate G4)'
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
ordinal: 2000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 20 of docs/plans/phase-1-implementation.md exactly as written. Gate G4 is ruled (an empty text has no lines); apply it as the plan states.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
adapters — size counters (gate G4): size.py with count_lines / file_extension / size_counters, wired into mapping.py at the tool-result site; 13 brief tests + 2 extras; fixture size_counters.jsonl. Review approved first round (no Critical/Important); one spec corner escalated (file_ext without size_basis on a text-key-less edit call — To be confirmed), two polish minors deferred to the ledger. 70/70 focused, 169/169 suite, style 0 at 1cdd4d7 on stream/adapter.
<!-- SECTION:FINAL_SUMMARY:END -->
