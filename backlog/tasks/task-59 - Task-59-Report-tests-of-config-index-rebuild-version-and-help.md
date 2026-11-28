---
id: TASK-59
title: 'Task 59: Report tests of config, index rebuild, version, and help'
status: Done
assignee: []
created_date: '2026-11-22 11:39'
updated_date: '2026-11-26 09:11'
labels: []
milestone: m-8
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
priority: high
ordinal: 5900
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 59 of docs/plans/phase-1-implementation.md exactly as written: expected files for config, index rebuild, version, and help, English and Italian.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every expected file is written by hand; --help has text files only
- [x] #2 The code is fixed where a test fails, never the expected file without support
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-25 — In progress. Implemented and landed on `stream/cli` (98e6d3e); fix round 1 landed (31a45b2: the usage line of the help of a command, laid out by the ledger); review round 1: Approved, no Critical, no Important, six Minor, all taken in fix round 2 (in flight: the main help within 96 columns — controller Ruling 84 — and the six findings). 739 tests, style 0; the 46 help files identical through Python 3.11, 3.12 and 3.13.

2026-11-25 — Fix round 2 landed (`6be4bae`: the metavar `<command>` on the main help, no help line over 96 columns; the six Minor findings of the review; the Italian of the glossary, Ruling 90) and fix round 3 landed (`b775084`: the help of `--hour` names the Day start hour, Ruling 96). The controller proved the 46 help files identical through Python 3.11, 3.12 and 3.13 after each round. The scoped re-review of the two rounds is in flight; Task 59 is complete when it is clean.

2026-11-26 — The scoped re-review approved (Critical 0, Important 0, Minor 2 — both comments of `tests/test_cli.py`: four counts no assertion reads; "under 96 columns" where five usage rows stand at exactly 96). Fix round 4 is ruled: ONE commit, `tests/test_cli.py` alone, then the controller reads the two hunks — no further review; then Task 59 is complete (Backlog Done, RESOLVED line of escalations 944).

2026-11-26 — Fix round 4 landed (`cfd2a57`: the comment of the main-help test without the counts no assertion reads; the docstring of `TestHelpUsage` says "within 96 columns"). The controller read the two hunks and ran its verification: 741 tests OK, style 0. Task 59 is complete.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 59 adds the report tests of `config`, `index rebuild`, `version` and the help of every command, in English and Italian, on `stream/cli`.

- Expected files written by hand: the 46 help files (text only), and the text and JSON pairs of `config show`, `index rebuild` and `version`.
- Code fixed where a test failed: the ledger lays out the usage line of a command's help by one rule on every interpreter (31a45b2). The main help shows the metavar `<command>`/`<comando>`, and no help line goes over 96 columns (6be4bae, Ruling 84). The help of `--hour` names the day start hour (b775084, Ruling 96). The Italian of Event identifier is "identificativo dell'evento" (Ruling 90).
- Reviews: round 1 approved with six Minor findings, all taken. The scoped re-review approved with two Minor findings, taken in fix round 4 (cfd2a57).
- Proof: the 46 help files are identical through Python 3.11, 3.12 and 3.13. 741 tests OK, style 0.
<!-- SECTION:FINAL_SUMMARY:END -->
