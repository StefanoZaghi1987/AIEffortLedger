---
id: TASK-11
title: 'Task 11: language — texts by code'
status: Done
assignee: []
created_date: '2026-11-22 11:32'
updated_date: '2026-11-27 12:04'
labels: []
milestone: m-1
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
  - GLOSSARY.md
priority: high
ordinal: 1100
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 11 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order. Last task of the milestone: the checkpoint asks gate G6.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 11 (amended per execution Ruling 6) of docs/plans/phase-1-implementation.md: language — LANGUAGES, WARNING_CODES (23, exact), CONFIGURATION_ERROR_CODES (3, exact), STOP_CODES (17, exact — the complete set from command-line.md's two tables; no later task adds codes), message() and label() with English and Italian texts; scheduler_failed shared by stop and warning; labels limited to glossary-grounded keys (measured_day, declared_day, timesheet, report) — report-table labels deliberately deferred to Task 46. Stream: stream/language, commit 0429352. Review: spec compliant, approved — every set membership, stop-code placeholder, and Italian term cross-verified against the spec tables and GLOSSARY.md; the set test pins all three sets to full literals and reads GLOSSARY.md itself. Minors deferred: no test pins _TEXTS keys to the union of the sets; message() raises bare KeyError on a missing value; wrong_use wording awaits Task 49's None-option handling; setup_required Italian keeps the command name "setup"; "sessione forkata" anglicism.
<!-- SECTION:FINAL_SUMMARY:END -->
