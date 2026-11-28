---
id: TASK-6
title: 'Task 6: platform — folders, store identifier, installation identifier'
status: Done
assignee: []
created_date: '2026-11-22 11:31'
updated_date: '2026-11-27 12:04'
labels: []
milestone: m-1
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
  - docs/spec/ingestion.md
priority: high
ordinal: 600
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 6 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order (failing tests first, then code, then the full suite, then the checkpoint).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 6 of docs/plans/phase-1-implementation.md: platform — machine_folder/default_store_folder (pure paths per system, never resolved), store_identifier (16 lower-case hex of SHA-256 over the resolved absolute path, Windows lower-cases first), installation_identifier (winreg MachineGuid / /etc/machine-id / ioreg, only on the running system, None otherwise), parse_ioreg, new_salt (32 hex, CSPRNG), salted_hash per D11. Stream: stream/platform, commit ce09b02. Review: spec compliant, approved; digest verified independently against a precomputed literal; mixed-flavour pure-path construction verified on 3.13. Minors deferred: weak installation_identifier assertion, UnicodeDecodeError escape on machine-id read, relative XDG path used as-is. Controller rulings on two spec-silent points: empty XDG variable counts as unset (XDG convention), LOCALAPPDATA fallback to home\AppData\Local (Windows convention, keeps the function total).
<!-- SECTION:FINAL_SUMMARY:END -->
