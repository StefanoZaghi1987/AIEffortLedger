---
id: TASK-71
title: 'Task 71: platform — `schedule show` reads the entry of launchd and of systemd'
status: Done
assignee: []
created_date: '2026-11-25 21:40'
updated_date: '2026-11-26 21:15'
labels: []
milestone: m-9
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
  - docs/spec/ingestion.md
priority: high
ordinal: 7100
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 71 of docs/plans/phase-1-implementation.md exactly as written: `schedule show` and step 6 of `setup` read the entry of the scheduled ingestion on every scheduler that keeps one — the Task Scheduler, and on macOS and Linux the definition file that `schedule create` wrote (controller Ruling 93). Today both commands return no entry on macOS and Linux while one exists. A side stream from the tip of Milestone 8 after the merge of `stream/perf`; it merges into the feature branch before Task 65.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 On launchd and on systemd the entry that `schedule create` wrote is read back — name, command and time; no file, or a file that cannot be read, gives no entry; cron gives no entry
- [x] #2 `schedule show` and `setup` show the entry after a create on every system; the item of `command-line.md` › To be confirmed is closed by deletion; the full suite is green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-26: implemented a21d32b on stream/schedule (816 OK on 3.11/3.12/3.13); review round 1 Needs Fix (Important 2, Minor 2); fix round 1 in flight (Rulings 125, 127). Ledger: .superpowers/sdd/phase-1-implementation/progress.md

2026-11-26 21:15: fix 1 (a165091, 823 OK on three interpreters) re-reviewed Needs Fix (Ruling 131: cron refuses the percent; the resolved store joins the guard); fix 2 (0823347, 824 OK) re-reviewed Approved (Ruling 133); fix 3 (1449810, docstring) read by the controller; merged 0156bab (with the two open-point flags of Rulings 131/133 in e081f32), 855 OK on the tip, style 0; escalation 886 RESOLVED
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 71 complete on stream/schedule, merged as 0156bab (the spec flags of Rulings 131 and 133 — the setup step 6 point and the executable-word point — ride e081f32). a21d32b: `schedule show` and step 6 of `setup` read the entry back on every scheduler that keeps one — the Task Scheduler through its XML, launchd through its plist, systemd through its unit line; no file, or a file that cannot be read, gives no entry; cron gives no entry. Fix a165091 (Rulings 125, 127): the writer and the reader of each scheduler carry every word (Windows by the CommandLineToArgvW rules, systemd by its quoting and escapes, cron by single quotes), the readers catch LookupError and RecursionError, `schedule create` refuses a word the kind cannot carry. Fix 0823347 (Rulings 131-132): cron refuses the percent sign (the families of cron read its two escapes oppositely — cronie strips the backslash itself, busybox processes none) and the refusal sees the store that will be written from `--store` or the machine configuration. Fix 1449810 (Ruling 133): the docstring of the cron word claims what the function holds. Two open points flagged for the owner: setup's step 6 (escalation 970) and the executable word of the line (escalation 972). 855 tests on the merged tip, style 0.
<!-- SECTION:FINAL_SUMMARY:END -->
