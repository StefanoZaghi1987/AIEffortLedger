---
id: TASK-68
title: >-
  Task 68: metrics — the activity classes of a holder on its human time with
  manual entries
status: Done
assignee: []
created_date: '2026-11-25 20:02'
updated_date: '2026-11-25 22:14'
labels: []
milestone: m-8
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/metrics.md
  - docs/spec/command-line.md
  - GLOSSARY.md
priority: high
ordinal: 6800
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 68 of docs/plans/phase-1-implementation.md exactly as written: the activity classes of a project, of a work item, of a bucket and of the unattributed time come from the human time with manual entries of the holder, as those of the person do (controller Ruling 88). A side stream from the tip of the fix round 1 of Task 59; it merges into stream/cli before Task 60 when it is ready.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 For every holder, on every fixture store, Person only + Supervised equals its human time with manual entries
- [x] #2 The eight expected files that change are recomputed by hand, English and Italian, and the full suite is green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-25 — In progress. Implementer at work on the side stream `stream/classes` from 31a45b2, on controller Ruling 88: one rule for every holder (the classes come from the human time WITH manual entries); the whole seconds of the JSON document add up by the largest-remainder method. Merged into `stream/cli` before Task 60.

2026-11-25 — Landed on `stream/classes` (`420d360`, 742 tests): one rule for every holder, and the whole seconds of the JSON document by the largest-remainder method; eight expected files recomputed by hand. Review round 1 (opus): the figures right at every level it recomputed by hand; Needs fixes — one Important (a docstring made untrue by the change), two Minor (the reason in `metrics.md` made whole; the shapes of two hand-built test figures). All three taken; the fix round is in flight.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Complete on `stream/classes` (`420d360` + the fix round `04a54d2`), verified by the controller: 743 tests, style 0. The activity classes of a project, of a work item, of a bucket and of the unattributed time come from the human time with manual entries of the holder, as those of the person do; in the JSON document the classes person only and supervised of every holder add up to its human time, and the five classes of the person to the length of its day (two-step largest-remainder division, one cell recomputed by hand by the controller). The eight expected files that change were recomputed by hand, English and Italian. Review round 1 (opus) found no Critical; its one Important and two Minor findings are closed. Merges into `stream/cli` before Task 60.
<!-- SECTION:FINAL_SUMMARY:END -->
