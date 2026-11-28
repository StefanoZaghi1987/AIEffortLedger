---
id: TASK-2
title: 'Task 2: Static check tests/style.py (gate G1)'
status: Done
assignee: []
created_date: '2026-11-22 11:31'
updated_date: '2026-11-27 12:04'
labels: []
milestone: m-0
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
  - GLOSSARY.md
  - docs/research/lint-tool-2026-11.md
priority: high
ordinal: 200
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 2 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint). Gate G1 is ruled; apply it as the plan states.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 2 of docs/plans/phase-1-implementation.md: static check tests/style.py + tests/test_style.py (gate G1). Splits identifiers, parses GLOSSARY.md _Avoid_ entries (paren text stripped from the whole line before the comma split; multi-word entries as sequences), checks defined identifiers only (not names used from other code), enforces type hints on public defs (self/cls/vararg/kwarg/nested/overload exempt), 99-column lines, syntax faults; main() reads GLOSSARY.md beside tests/, checks src/ and tests/, skips __pycache__. Folded in the Task-1 follow-up (entry-point target assertion) and -> None on all test_package.py methods. Review: one fix round (vararg/kwarg exemption, paren-comma parsing of the real transcript entry, test output capture) — re-review: all addressed, no new breakage. Suite 16/16 pristine, style exit 0 on the tree.
<!-- SECTION:FINAL_SUMMARY:END -->
