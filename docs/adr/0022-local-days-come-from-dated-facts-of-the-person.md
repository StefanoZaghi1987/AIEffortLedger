---
status: accepted
date: 2026-11-19
---

# Local days come from dated facts of the person, with time zones only from tzdata

The store keeps instants in UTC (ADR 0002), but a timesheet is a list of local days, and a timesheet confirmation stores
its day as a date (ADR 0014). A person travels and moves; a person who works after midnight wants that work on the day
before; and two machines of one person must put each instant in the same local day, also when they run different
operating systems or different updates of their time-zone data. Therefore the time zone and the day start hour are dated
facts of the person in the person configuration (ADR 0017): a time-zone history of IANA time zones, each valid from an
instant, and a list of day start hours, each valid from a local date. The local day of an instant comes from the time
zone valid at that instant and the day start hour valid on that date. The ledger reads time zones only from the `tzdata`
package, on every operating system, and every report records the version of `tzdata` that it used.

## Considered Options

- **Time zone of the machine that runs the report**: a report on a laptop in another time zone moves work to other days,
  and a confirmation names a day that the report no longer shows.
- **Time zone of the machine of each event, stored in the event**: needs a field in every event and still gives wrong
  days after a journey with the same machine.
- **Time-zone data of the operating system where it exists**: Linux and macOS update their data at other times than
  `tzdata`, so two machines can disagree on the days around a change of rules.
- **Day start hour as a report parameter**: two reports with different values put one confirmation on different days.

## Consequences

- A journey or a move is one new entry in the time-zone history, and every report recomputes.
- A day at a change of daylight saving has 23 or 25 hours, and a journey west across the start of a day can give a day
  two parts.
- An instant before the first entry of the time-zone history or of the day start hours has no local day; setup writes
  entries valid from 1970.
- `tzdata` is a dependency on every operating system. This supersedes ADR 0005 where it says that `tzdata` is needed on
  Windows.
