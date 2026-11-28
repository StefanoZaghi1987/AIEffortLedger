---
id: TASK-69
title: 'Task 69: cli — a purge by writer version holds no purge event'
status: Done
assignee: []
created_date: '2026-11-25 20:02'
updated_date: '2026-11-25 21:37'
labels: []
milestone: m-8
dependencies: []
documentation:
  - docs/plans/phase-1-implementation.md
  - docs/spec/command-line.md
  - docs/adr/0015-a-purge-names-the-corrected-version.md
  - GLOSSARY.md
priority: high
ordinal: 6900
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Execute Task 69 of docs/plans/phase-1-implementation.md exactly as written: a selection by writer version holds no purge event, so `purge --writer-version-below` runs in one command on a store with a purge history; a `--key` that names a purge still stops the command (controller Ruling 87). A side stream from the tip of the fix round 1 of Task 59; it merges into stream/cli before Task 60 when it is ready.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 `LocalIndex.keys_written_below` returns no key whose winning copy is a purge, and the command leaves a purge event alone in a selection by writer version
- [x] #2 A `--key` whose event is a purge still stops the command with the exit code for wrong use; the full suite is green
<!-- AC:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
2026-11-25 — In progress. Implemented on the side stream `stream/purge` (94381de, on controller Ruling 87); review round 1: Approved, one Minor (a clause of a class docstring). Fix round 1 in flight on controller Ruling 91: a selection by writer version that holds no key writes nothing and asks nothing; the command completes with the warning `no_key_selected`. Merged into `stream/cli` before Task 60.

2026-11-25 — Complete: `94381de` (Ruling 87) and its fix round `520b2fe` (Ruling 91: a selection that holds no key writes nothing and asks nothing, warning `no_key_selected`). Review round 1 Approved with one Minor, taken in the fix round; the fix round verified by the controller. 740 tests, style 0.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Task 69 is complete on the side stream `stream/purge` and merges into `stream/cli` before Task 60.

**What changed.** A purge by writer version runs in one command on a store with a purge history: `LocalIndex.keys_written_below` returns no key whose winning copy is a purge event, so the correction of ADR 0015 no longer stops on the purge events that older versions wrote. A `--key` that names a purge still stops the command with the exit code for wrong use, and the guard `_refuse_purge_of_purge` runs on every selection. Its fix round adds the rule for a selection that holds no key: nothing is written and nobody is asked; the command completes with the new warning `no_key_selected` (controller Ruling 91).

**Commits.** `94381de` (the task, on controller Ruling 87) and `520b2fe` (the fix round).

**Specification.** `command-line.md` › Purge: "A selection by writer version holds no purge event." and the sentence of the empty selection; › JSON documents: the row of `no_key_selected`.

**Tests.** The tests of the index and of the command were written red first in the task (one test replaced by one); one new test in the fix round. The full suite has 740 tests, green through Python 3.12; the style check gives 0.

**Review.** Round 1 (sonnet, ten exact checks): Approved, one Minor, taken in the fix round; the fix round was verified by the controller (every hunk read, the suite run on the landed commit).

**Follow-ups.** The report tests of `purge` (by key, by writer version, and of the empty selection) are Task 60's; the item of `command-line.md` › To be confirmed closes at the merge of Milestone 8.
<!-- SECTION:FINAL_SUMMARY:END -->
