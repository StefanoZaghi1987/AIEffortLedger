---
status: accepted
date: 2026-11-18
---

# A day with timesheet entries is declared as a whole

ADR 0011 makes the timesheet entry of a day and a project the total human time of that day and project, and keeps
measured human time for the projects without an entry. Two defects follow. The unattributed bucket is not a project, so
its measured human time always counts: a person who recognizes unattributed time and adds it to the entry of a project
counts it twice. And a day where the person confirms some projects adds declared values to measured values, which are a
lower bound. A timesheet is a record of a whole day, and a person confirms it as one. Therefore, when a day has at least
one confirmed timesheet entry, the sum of its timesheet entries is all the human time of the person in that day; it is a
declared day, and all its measured values, manual entries included, are evidence. A timesheet entry can have no project:
it declares the unattributed time of the day. The entries that a person confirms together are one event, a timesheet
confirmation, and the latest confirmation of a day that is not retracted gives all the entries of that day: two machines
that share a store through a file-sync service can confirm the same day before either machine sees the other, and only a
whole confirmation is a day that the person declared. This supersedes ADR 0011 where ADR 0011 keeps measured human time
for the projects of a day without an entry.

## Considered Options

- **Totals per day and project, with unattributed time as evidence on a day with entries**: no double counting, but a
  day still adds declared values to a lower bound, and the meaning of unattributed time depends on another entry.
- **Totals per day and project, with unattributed time that always counts** (ADR 0011 as written): double counting
  whenever a person assigns unattributed time.
- **Latest entry for each project**: a day can mix two confirmations and give a total that the person never declared.
- **Two confirmations of a day are an error**: the day stays in error until the person retracts one confirmation.

## Consequences

- A timesheet confirmation is one event that holds all the entries of the day, so a file-sync service never shows a part
  of it, and it can hold no entries. A change of a day is a new confirmation that names the one it replaces; a
  retraction cancels a whole confirmation, and then the confirmation before it applies again.
- Each day is measured or declared, never both; reports show the state of each day.
- A project with measured human time and no timesheet entry in a declared day has a declared value of zero, and the
  report warns that the declared value is lower than the measured value.
- A day whose timesheet confirmations are all retracted is a measured day again.
- A timesheet entry still takes no part in activity classes, in the split rule, or in the union with manual entries
  (ADR 0011).
