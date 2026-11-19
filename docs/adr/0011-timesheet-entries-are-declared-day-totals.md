---
status: superseded in part by 0014
date: 2026-11-18
---

# Timesheet entries are declared day totals that the ledger proposes and the person confirms

Measured human time is a lower bound: in the validation it covered a median fifth of the presence span, because no
source sees reading, testing, discussion, or work outside the agent tools. A timesheet asks for the human time per day
and per project, and a person knows those totals better than the clock times of each activity. A timesheet entry
therefore declares the human time of a person for one day and one project, with no start and no end. The ledger
proposes the entries of a day from measured values; the person confirms or changes them, and only confirmed entries
enter the store. Where a timesheet entry exists for a day and a project, total human time is its declared value;
measured human time and manual entries stay in their own columns as evidence. The report warns when a
declared value is lower than the measured value of the same day and project.

## Considered Options

- **Interval manual entries only**: the person must reconstruct clock times that nobody recorded, and the precision of
  the intervals is false.
- **Presence span or another upper bound as the total**: the span contains breaks and work for other purposes; it is an
  estimate, not a declaration.
- **Measured human time scaled by a factor**: the factor is an estimate presented as a measurement (ADR 0001).

## Consequences

- A timesheet entry has no position in the day: it takes no part in activity classes, in the split rule, or in the
  union with manual entries.
- The ratio of declared to measured human time of a person becomes a calibration value for estimates.
- A report that a person gave to someone freezes its timesheet entries with its period.
