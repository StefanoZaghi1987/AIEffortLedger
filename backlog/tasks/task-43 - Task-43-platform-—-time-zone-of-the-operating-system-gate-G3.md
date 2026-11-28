---
id: TASK-43
title: 'Task 43: platform — time zone of the operating system (gate G3)'
status: Done
assignee: []
created_date: '2026-11-22 11:37'
updated_date: '2026-11-27 12:06'
labels: []
milestone: m-6
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/configuration.md
priority: high
ordinal: 4300
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 43 of docs/plans/phase-1-implementation.md exactly as written. Gate G3: the research note and the ruling panel on the CLDR release come before the code.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The research note names its primary sources and the ruled release
- [x] #2 The ruling became a sentence of configuration.md and its To-be-confirmed item is deleted
- [x] #3 Every named test passes and the full suite is green
<!-- AC:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
platform — the time zone of the operating system (gate G3): zones.py and the table of the 142 territory 001 rows of CLDR release 49 (windows_zones.py), built on stream/zones. Checkpoint commit 86a7ad2 (suite 392 tests OK, style 0); research note docs/research/windows-zones-2026-11.md, ruling in configuration.md; review approved first round. Evidence: task-43-report.md.
<!-- SECTION:FINAL_SUMMARY:END -->
