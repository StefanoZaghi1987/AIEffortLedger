---
id: TASK-4
title: 'Task 4: events — values, encoding, and reading of newer schema versions'
status: Done
assignee: []
created_date: '2026-11-22 11:31'
updated_date: '2026-11-27 12:04'
labels: []
milestone: m-1
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/event-schema.md
  - docs/spec/architecture.md
priority: high
ordinal: 400
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 4 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 4 of docs/plans/phase-1-implementation.md: events — SCHEMA_VERSION, Event, KINDS (17), FIELDS (57, verified one-for-one against the spec table), FIXED_VALUES (11 fields), REQUIRED_FIELDS (9), format_instant/parse_instant (RFC 3339 UTC ms, truncate), version_key (PEP 440-shaped ordering, ValueError on wrong form), writer_version, encode_event (D2: sorted keys, no spaces, ensure_ascii=False, one line ending \n, ValueError on None at any depth with path diagnosis), Decoded(event/left_out/broken, newer flag), decode_line. Stream: stream/events, commit a9e13bd. Review: spec compliant, approved — constants verified spec-complete row by row; version_key traced for boundary orderings; bool guard for schema_version; the four disclosed choices all grounded in spec/ADR 0023. Minors deferred: parse_instant truncates in source zone (equivalent for RFC 3339 whole-minute offsets, sub-minute offsets unhandled); truncation not pinned by a committed test; schema-1 unknown-field-drop vs unknown-value-broken asymmetry deserves a docstring sentence.
<!-- SECTION:FINAL_SUMMARY:END -->
