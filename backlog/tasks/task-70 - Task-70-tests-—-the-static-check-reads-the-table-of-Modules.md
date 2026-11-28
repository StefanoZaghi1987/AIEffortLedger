---
id: TASK-70
title: 'Task 70: tests — the static check reads the table of Modules'
status: Done
assignee: []
created_date: '2026-11-25 20:03'
updated_date: '2026-11-26 23:05'
labels: []
milestone: m-9
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
  - GLOSSARY.md
priority: high
ordinal: 7000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 70 of docs/plans/phase-1-implementation.md exactly as written: `tests/style.py` names an import that the row of its module in architecture.md › Modules does not list, a dependency of the row that no file of the module imports, and a dependency below its module in the build order; the rows that diverge are corrected (controller Ruling 86). It runs on the feature branch after the merge of Milestone 8 and the merge of stream/perf, before Task 65.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every row of architecture.md › Modules names exactly the modules that its files import, read on the merged tip
- [x] #2 The check fails on an import the row does not list, on a stale dependency and on an inverted one, each proven by a test of tests/test_style.py
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-26 23:05: implemented 2ed3cc6 on stream/modules (865 OK, +10 tests RED first; the eight rows corrected, the four items deleted); review round 1 Approved (Minor 1: the document readers unanchored — Ruling 134); fix 155f1e1 (867 OK, +2 decoy tests) read by the controller; merged 4fcd58a (867 OK on the tip, style 0 with the new check); escalations 900, 901, 904, 906, 929 RESOLVED. Ledger: .superpowers/sdd/phase-1-implementation/progress.md
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 70 complete on stream/modules, merged as 4fcd58a. 2ed3cc6: a pass of tests/style.py reads the table of Modules and the build-order line of architecture.md beside GLOSSARY.md (never a copy), collects every import statement of the package, maps each to the first module of the package it loads (the root rule of Ruling 120, case-exact file and folder matching), and names an unlisted import, an unimported dependency, a dependency below its module in the build order, and a cycle; the eight rows that differed are corrected (configuration, index, ingestion, selection, attribution, declared, setup, reports) and the four flagged To be confirmed items closed. Review round 1 Approved (all ten checks SOUND; the eight cells verified against an independent grep). Fix 155f1e1 (Ruling 134): both document readers anchor to the `## Modules` section, decoy tables and outside build-order lines are not read (+2 tests). 867 tests on the merged tip, style 0 with the new check running on the real tree.
<!-- SECTION:FINAL_SUMMARY:END -->
