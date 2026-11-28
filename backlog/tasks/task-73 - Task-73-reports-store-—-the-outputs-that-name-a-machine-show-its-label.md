---
id: TASK-73
title: 'Task 73: reports, store — the outputs that name a machine show its label'
status: Done
assignee: []
created_date: '2026-11-25 21:41'
updated_date: '2026-11-26 18:03'
labels: []
milestone: m-9
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
  - docs/spec/ingestion.md
  - GLOSSARY.md
priority: high
ordinal: 7300
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 73 of docs/plans/phase-1-implementation.md exactly as written: where an output names a machine to a person it shows the machine label when the store holds one, and the identifier otherwise — the text and the document of `frozen list`, the text of `entries`, the stop error `frozen_other_machine` (controller Ruling 94). Today `read_label` has no caller and `machine label` changes a text that nothing reads. A side stream from the tip of Milestone 8 after the merge of `stream/perf`; it merges into the feature branch before Task 65.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 With a label in the store metadata of a machine, the text of `frozen list` and of `entries` shows the label, each row of the document of `frozen list` adds `machine_label` beside `machine`, and the message and the values of `frozen_other_machine` name it; without a label the identifier shows
- [x] #2 The expected files are corrected by hand, English and Italian; the item of `ingestion.md` › To be confirmed is closed by deletion; the full suite is green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-26: implemented cb1231c on stream/label (819 OK); review round 1 Needs Fix (Important 1, Minor 2); fix round 1 in flight (Rulings 124, 126). Ledger: .superpowers/sdd/phase-1-implementation/progress.md

2026-11-26 19:05: fix 1 (12cce1a, 824 OK) verified + re-review Approved; fix 2 (bb8aa65, 824 OK) verified and read; merged 4d8c079, 842 OK on the tip, style 0; escalation 912 RESOLVED
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 73 complete on stream/label, merged as 4d8c079. cb1231c: every output that names a machine shows its machine label when the store holds one and the identifier otherwise — the rows of frozen list (machine_label only when held), the column Machine of the text of frozen list and of entries, the stop error frozen_other_machine (one code, a variant text that names the label), the label line of setup's text. Fix round 12cce1a (Rulings 124, 126): one reader store.machine_labels (each store metadata read once per command) with the warning machine_label_unreadable for a file that cannot be read (also for its depth), the outputs showing the identifier; a blank label is no label and machine label refuses one with wrong_value; the setup document holds machine_label when the store holds one. Fix round bb8aa65: the docstring names the depth cause. Review round 1 Needs Fix (1 Important, 2 Minor — all taken); scoped re-review of the fix: Approved. 842 tests on the merged tip, style 0; fixtures frozen_period and annotations hold a label, declared_day none, so the expected files pin both branches.
<!-- SECTION:FINAL_SUMMARY:END -->
