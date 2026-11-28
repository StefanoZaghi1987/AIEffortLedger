---
id: TASK-64
title: 'Task 64: Benchmark through the command line'
status: Done
assignee: []
created_date: '2026-11-22 11:40'
updated_date: '2026-11-26 17:38'
labels: []
milestone: m-9
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/architecture.md
priority: high
ordinal: 6400
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 64 of docs/plans/phase-1-implementation.md exactly as written: the benchmark through the command line.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Both times run through cli.main with the script's own Context
- [x] #2 The default run's seconds go to the owner; a second failure of a target stops the task
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-25 — In progress. Round 1 landed on `stream/perf` (2f274c5: the benchmark through `cli.main`; C1–C4 figure-neutral by digests on three data sets; 728 tests). Development machine, invented data, quiet: first ingestion 28.1 s, the timesheet of a month 24.0 s, one day 5.3–5.4 s. Next: the controller's independent digests, the review of round 1, then round 2 (the selection of a period — controller Ruling 83).

2026-11-26 — Round 2 dispatched on the side stream `stream/perf` (two commits: the selection of a period reads one row once plus three indexes, without a bump of INDEX_FORMAT; the benchmark times four commands and the ten findings of the review). The implementer was killed by an API usage limit mid-work and the controller resumed it on 2026-11-26 at 09:58 from its transcript; the worktree holds one uncommitted change to `tests/test_index.py`. The ingestion dossier (which decides the index on `key`, a round of its own) was killed and resumed the same way. Waiting on the report files.

2026-11-26 11:19 — Round 2 landed (b629e40, eeff501; 736 tests, style 0) and was verified by the controller: commit shapes, the full suite, and the controller's own digests against round 1 on four data sets (identical). Selection of one day 5.7 → 1.3 s; the timesheet of a month 19.9 s through cli.main (the 30 s target of Ruling 83 holds; gate G5 stays the owner's). Round 3 dispatched (Ruling 108: a partial index on `key` for the lookups of an ingestion; Ruling 112: two docstrings in a second commit). One review covers rounds 2 and 3.

2026-11-26: round 3 (7c7c9d0 + 1df7e31, partial lines_key) and round 4 (a7efb4a, full lines_key, Ruling 122 — round 3's partial index slowed the scans) landed and verified; 740 OK. Review of rounds 2-4 in flight. Then the perf merge.

2026-11-26 18:35: rounds 1-4 + fix complete; review Approved (Ruling 128); docstring round c7e3b4b verified 740 OK; merged 7fb0e13, Task 69 tests green on the tip, main-venn suite green
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 64 complete on stream/perf, merged as 7fb0e13. Four rounds plus a fix: round 1 (2f274c5) the benchmark through cli.main with its own Context and the C1-C4 figure fixes; round 2 (b629e40, eeff501) the selection of a period reads one row once (rowid form, three indexes) and the benchmark times four commands; round 3 (7c7c9d0, 1df7e31) a partial index on key for the lookups of an ingestion — which slowed the event scans, so round 4 (a7efb4a, Ruling 122) made it a full index; the fix (c7e3b4b) two docstrings. Review of rounds 2-4: Approved (Minors 1-2 accepted by Ruling 128, 3-4 taken). Development machine, invented data: first ingestion 45-55 s (target <60), the month 22-25 s (target <30, gate G5 the owner's on a laptop), the day 1.4-1.8 s (target <5); an ingestion of 1 000 new lines 462 s -> 3.2 s; digests identical on four data sets and 19 scenario stores, and the controller's own digests on the merged tip. 740 tests on the stream; the merged tip green in the main venv.
<!-- SECTION:FINAL_SUMMARY:END -->
