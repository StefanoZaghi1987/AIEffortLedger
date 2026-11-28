---
id: TASK-3
title: 'Task 3: GitHub Actions workflow'
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
priority: high
ordinal: 300
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 3 of docs/plans/phase-1-implementation.md exactly as written: its Files and numbered Steps are the work order. Ends with gate G6 (ask the owner whether to push the branch).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked
- [x] #2 The workflow file passes the pin checks of Step 3 and gate G6 is asked
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 3 of docs/plans/phase-1-implementation.md: GitHub Actions workflow (.github/workflows/tests.yml) — push + pull_request, 3-OS × 2-Python matrix (six jobs), actions/checkout@3d3c42e (v7.0.1) and actions/setup-python@6d4fd22 (v7.1.0) pinned to commit hashes, install with `python -m pip install -e .` (D9), suite and style check verbatim; job-level `permissions: contents: read`, no secrets. Review: spec compliant, approved (one deferred minor: matrix fail-fast default). Gate G6 (push) recorded for the owner; acceptance criterion 8 stays unmet until a push.
<!-- SECTION:FINAL_SUMMARY:END -->
