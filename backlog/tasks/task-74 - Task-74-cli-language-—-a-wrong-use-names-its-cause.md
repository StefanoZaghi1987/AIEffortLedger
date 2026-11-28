---
id: TASK-74
title: 'Task 74: cli, language — a wrong use names its cause'
status: Done
assignee: []
created_date: '2026-11-26 09:17'
updated_date: '2026-11-27 11:55'
labels: []
milestone: m-9
dependencies:
  - TASK-60
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
  - GLOSSARY.md
priority: high
ordinal: 7400
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 74 of docs/plans/phase-1-implementation.md (controller Rulings 102-107). The stop error `wrong_use` is replaced by one code for each cause: `no_command`, `missing_argument`, `unknown_argument` and `conflicting_arguments`. A name that two entries of the person configuration give stops with `ambiguous_name`. A list value is written as its items in the text. The texts that name an event identifier use the term of the glossary. It runs on a side stream `stream/wrong-use` from the tip of Task 60, beside Task 67.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every situation of the wrong-use dossier, and the stop that Task 60 adds, is pinned by a test through cli.main, in English and Italian, with its code, values and line
- [x] #2 The values are derived from the words of the command line: the same output on Python 3.11, 3.12 and 3.13
- [x] #3 GLOSSARY.md has the entry Argument, and command-line.md has the rows of the new stop errors; no wrong_use remains
- [x] #4 The texts of an event identifier use the term of the glossary; the expected files they move are corrected by hand
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-26 — Dispatched (opus) on the side stream `stream/wrong-use` (worktree `D:\Work\Product\wrong-use`) from `c2b8e52`, the tip of Task 60 (767 tests OK, style 0). It proves its runs on Python 3.11, 3.12 and 3.13.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 74 complete on `stream/wrong-use`: af990b3 (the four causes `no_command`, `missing_argument`, `unknown_argument`, `conflicting_arguments`; `ambiguous_name`; the glossary entry Argument; the rows of command-line.md), c7c4881 (the event identifier texts, Ruling 106), ef584dc (Rulings 114 and 117: the two help sentences; the unreachable fallback narrowed). 796 tests (+29), style 0; the 39 situations pinned through cli.main; byte-identical values on 3.11/3.12/3.13 (the one argparse text read is the `unrecognized arguments: ` prefix). Review round 1: Approved, 0 Critical, 0 Important, 1 Minor (fixed). Survived an account-limit kill mid-commit-2 and resumed from its transcript. The merge into `stream/cli` follows Task 67 (schedule step 4).
<!-- SECTION:FINAL_SUMMARY:END -->
