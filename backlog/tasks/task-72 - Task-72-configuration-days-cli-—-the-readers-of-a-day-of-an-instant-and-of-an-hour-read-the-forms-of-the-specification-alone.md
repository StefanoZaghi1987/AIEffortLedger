---
id: TASK-72
title: >-
  Task 72: configuration, days, cli — the readers of a day, of an instant and of
  an hour read the forms of the specification alone
status: Done
assignee: []
created_date: '2026-11-25 21:40'
updated_date: '2026-11-26 23:05'
labels: []
milestone: m-9
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
  - docs/spec/configuration.md
priority: high
ordinal: 7200
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 72 of docs/plans/phase-1-implementation.md exactly as written: one definition of each form of `command-line.md` › Form, read by every reader of a text that a person gives — the command line, the configuration file and the checks before an append; every other text is a wrong value (controller Ruling 92). Today the readers accept everything `fromisoformat` accepts. A side stream from the tip of Milestone 8 after the merge of `stream/perf`; it merges into the feature branch before Task 65.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each reader of a person's text accepts the forms of `command-line.md` › Form alone and refuses a compact date, a week date, a space for `T`, seconds in a local instant, a day where an instant is read, and an hour that is not `HH:MM` — with the exit code for wrong use on the command line and the line of the entry in the configuration file
- [x] #2 No reader of a person's text calls `fromisoformat`; the item of `command-line.md` › To be confirmed is closed by deletion; the full suite is green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-26 23:05: implemented 384c48c on stream/forms (861 OK on 3.11/3.12/3.13, +6 tests RED first; the readers item deleted; the store and every expected file unchanged); review round 1 Approved (Minor 1: one over-general docstring clause — Ruling 135); fix 180be70 (docstring alone) read by the controller; merged 988f4ac (873 OK on the tip, style 0); escalation 948 RESOLVED. Ledger: .superpowers/sdd/phase-1-implementation/progress.md
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 72 complete on stream/forms, merged as 988f4ac. 384c48c: one public definition per form in the new configuration/forms.py — a day, a local instant, an offset instant, an hour — each a shape regular expression followed, for the three date-and-time forms, by a calendar step; every reader of a person's text sits behind a definition (the command-line readers, the checks before an append, the `--from` of config add time-zone, the `_TIME` and `--time` hour readers). Compact dates, week dates, a space for `T`, seconds, a date-only text where an instant is read, a local time in `--from`, and an hour that is not `HH:MM` are refused; no reader takes fromisoformat's verdict on a person's text (the definitions alone use it for the calendar, after the shape). Review round 1 Approved (all ten checks SOUND; the merge-hazard check empty — no import of the diff can fail Task 70's static check, proven on the merged tree). Fix 180be70 (Ruling 135): the calendar sentence scoped to the day and instant definitions. 873 tests on the merged tip, style 0; the readers item of command-line.md › To be confirmed closed by deletion.
<!-- SECTION:FINAL_SUMMARY:END -->
