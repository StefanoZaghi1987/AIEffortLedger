---
id: TASK-24
title: 'Task 24: adapters — retention settings'
status: Done
assignee: []
created_date: '2026-11-22 11:34'
updated_date: '2026-11-27 12:03'
labels: []
milestone: m-2
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/claude-code-adapter.md
  - docs/spec/ingestion.md
  - docs/research/claude-code-settings-2026-11.md
priority: high
ordinal: 2400
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 24 of docs/plans/phase-1-implementation.md exactly as written: its Files, Interfaces, and numbered Steps are the work order. Last task of the milestone: the checkpoint asks gate G6.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every step checkbox of the plan task is checked and its named tests pass
- [x] #2 The full suite and python -I tests/style.py pass at the checkpoint commit
<!-- AC:END -->



## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
adapters — retention settings: retention.py (retention with per-folder precedence managed>local>shared>user>default and shortest across folders, default 30, minimum 1; desktop rule managed-alone / no-age-limit / longer-of-two), managed_settings_path for three systems as pure paths, ClaudeCodeAdapter(managed_file), support.adapters_for_tests(home). Retention definition moved to retention.py (import cycle, ReadContext pattern, surface unchanged). Review approved first round; minors deferred (cosmetic __all__ order, fall-through comment, JSON-float note). G6 reached, recorded, no push. 106/106 focused, 205/205 suite, style 0 at a6a9df2 on stream/adapter. Adapter stream COMPLETE.
<!-- SECTION:FINAL_SUMMARY:END -->
