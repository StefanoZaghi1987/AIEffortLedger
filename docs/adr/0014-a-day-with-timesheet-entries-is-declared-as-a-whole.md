---
status: accepted
date: 2026-11-18
---

# A day with timesheet entries is declared as a whole

ADR 0011 makes the timesheet entry of a day and a project the total human time of that day and project, and keeps
measured human time for the projects without an entry. Two defects follow. The unattributed bucket is not a project,
so its measured human time always counts: a person who recognizes unattributed time and adds it to the entry of a
project counts it twice. And a day where the person confirms some projects adds declared values to measured values,
which are a lower bound. A timesheet is a record of a whole day, and a person confirms it as one. Therefore, when a day
has at least one confirmed timesheet entry, the sum of its timesheet entries is all the human time of the person in
that day; it is a declared day, and all its measured values, manual entries included, are evidence. A timesheet entry
can have no project: it declares the unattributed time of the day. This supersedes ADR 0011 where ADR 0011 keeps
measured human time for the projects of a day without an entry.

## Considered Options

- **Totals per day and project, with unattributed time as evidence on a day with entries**: no double counting, but a
  day still adds declared values to a lower bound, and the meaning of unattributed time depends on another entry.
- **Totals per day and project, with unattributed time that always counts** (ADR 0011 as written): double counting
  whenever a person assigns unattributed time.

## Consequences

- Each day is measured or declared, never both; reports show the state of each day.
- A project with measured human time and no timesheet entry in a declared day has a declared value of zero, and the
  report warns that the declared value is lower than the measured value.
- A day whose timesheet entries are all retracted is a measured day again.
- A timesheet entry still takes no part in activity classes, in the split rule, or in the union with manual entries
  (ADR 0011).
