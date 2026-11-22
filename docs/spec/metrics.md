# Metrics

How the ledger turns events into effort. Terms follow [GLOSSARY.md](../../GLOSSARY.md); events follow
[event-schema.md](event-schema.md); the reasons behind the main choices are in [docs/adr](../adr).

## Quantities

| Quantity | Unit | Across parallel sessions of a person | Across persons | Source |
|---|---|---|---|---|
| Human time | person-hours | union | sum | human signals, agent outputs, manual entries, timesheet entries |
| Agent time | agent-hours | sum over agents | sum | turns, declared usage |
| Blocked time | hours | union | sum | decision requests and their decisions |
| Calendar time (Phase 2) | elapsed time (see To be confirmed) | first to last event | first to last event | all events of a work item |
| Token usage | tokens per category and model | sum | sum | agent outputs, declared usage |
| List-price cost (Phase 2) | currency | sum | sum | token usage, request counts, and price factors × price table |
| Actual cost (Phase 2) | currency | sum | sum | cost sources, declared usage |
| Person cost (Phase 2) | currency | sum | sum | human time × hourly rate |

The quantities are never added together or converted into each other (ADR 0001). Agent-hours of parallel agents add
up, so agent time can be longer than the clock time in which it happens; activity classes are clock time of one
person.

## Human time

Human signals are prompts, queued messages, interruptions, and decisions whose source is the person, from any agent of
any session of the person. A decision made by a configured rule is not a human signal, and neither is a prompt of a
session that a script, a schedule, or an orchestrator started (see [event-schema.md](event-schema.md)). A headless
prompt is the exception: no source shows whether a person or a script typed it, so the report parameter *headless
prompts* decides whether it is a human signal; the default is no. Measured human time of a person is the union of three
kinds of interval (ADR 0021):

- **signal gap**: two consecutive human signals of the person, from any of the sessions of the person, not more than
  the idle gap apart;
- **response interval**: from the last agent output or decision request of the main agent, or of a foreground
  subagent, of a session to the human signal of the same session that follows it, when not longer than the idle gap;
  an output of a background subagent starts no response interval, because the person does not watch it while it
  runs, and a subagent whose `subagent_mode` is absent, because the settle time completed a session without the event
  that links it, counts as a foreground subagent;
- **minimum attention**: an interval of the minimum attention time that ends at a human signal that ends no signal gap
  and no response interval.

The default idle gap is 10 minutes, and the default minimum attention time is 1 minute. The human signals of all
sessions, agent tools, and machines of the person form one stream, so a person who moves between parallel sessions stays
present, and an instant counts once. Signal gaps between sessions of different projects, and overlaps of their
intervals, go to projects through the split rule. Reports show the share of human signals that come from sessions of
unknown invocation.

### Declared values

A manual entry is an interval with a start, an end, a project, an optional work item, and a note; like every declared
interval, it includes its start instant and excludes its end instant. It is not a human signal. Its mode decides how it
combines with measured human time:

- `overlapping`: the entry merges with measured human time by union, and its attribution applies to the whole
  interval; where it overlaps measured human time of another project or work item, the report warns about the change;
- `additional`: the entry counts only where it does not overlap measured human time, and the report warns about every
  overlap it removed.

A timesheet entry declares the human time of one day for one project, with an optional work item, or for the
unattributed time of the day, which has no work item, with a duration and a note, and no start or end (ADR 0011). The
entries that the person confirms together for a day form one event, a timesheet confirmation, with at most one entry for
each project and work item (ADR 0014); a confirmation without entries declares a day without human time. For each day,
the latest timesheet confirmation that is not retracted gives all the timesheet entries of the day, and the earlier
confirmations do not count. A change of a day is a new confirmation, which names the latest confirmation of the day that
its machine has; a retraction of the latest confirmation brings back the one before it. The latest confirmation is the
one with the latest `timestamp`, and equal instants resolve by event key. When an earlier confirmation of the day that
is not retracted is not named by the latest one, directly or through the confirmations between them, two machines
confirmed the day without seeing each other, and the report warns. A retracted confirmation still carries the chain of
`replaces`: the confirmations between two are every confirmation of the day that the chain names, retracted or not. The
declared value of a project is the sum of its entries; an entry without a work item stays in the part of the project
that has no work item, and the ledger does not divide it among work items. A timesheet entry takes no part in activity
classes, in the split rule, or in the union with manual entries.

The ledger computes the timesheet proposal of a day; the person confirms or changes it, and only a timesheet
confirmation enters the store. The proposal has one entry for each project and work item whose measured human time with
manual entries in the day is not zero, and one for the unattributed time when that value is not zero. Each proposed
value is the measured human time with manual entries, after the split rule, rounded up to the timesheet granularity
(default 15 minutes): measured human time is a lower bound, so a proposal without a given total is never lower than it.
When the person gives the total human time of the day, the proposal divides that total by the shares of measured human
time with manual entries, in units of the timesheet granularity, with the largest-remainder method, so that the entries
add up to the total; a part of the total smaller than one unit goes to the entry with the largest remainder. Between
equal remainders, the entry with the larger measured human time with manual entries comes first, then the entry whose
project and work item identifiers come first as text; the entry of the unattributed time comes last. The total can be
lower than the measured human time: then an entry can be lower than the measured human time of its project, and the
report warns, as on every declared day. When the person gives the value of some entries and a total, the rest of the
total divides among the other entries in the same way; when no other entry exists, the rest becomes the entry of the
unattributed time. Agent time and the presence span appear next to the proposal as context, never as proposed values.

When the milliseconds of the parts of a day do not divide into whole seconds, the report divides the whole
seconds of the total among the parts with the largest-remainder method, ties in the order above, so that the
parts add up to the total in the JSON document.

A day with a timesheet confirmation that is not retracted is a declared day (ADR 0014): the sum of the timesheet
entries of its latest confirmation is all the human time of the person in that day, and its measured human time and
manual entries are evidence. A day whose confirmations are all retracted is a measured day again.

Declared usage (Phase 2) gives agent time, token usage, or actual cost of work that no source recorded, such as a cloud
session. Its values appear in their own quantities as declared values; declared token usage with a model gets a
list-price cost like measured usage.

Reports show the state of each day, measured or declared, and for each project, work item, and the unattributed time
three values in separate columns: the measured human time after the split rule, without manual entries; the measured
human time with manual entries, which is the basis of the timesheet proposal; and the timesheet entry of a declared day.
Total human time of a declared day is the sum of its timesheet entries; total human time of a measured day is the union
of measured human time and manual entries. The report warns when the declared value of a project in a declared day, the
sum of its timesheet entries, is lower than its measured human time, also when the project has no entry; the comparison
is for each project, never for each work item. The comparison, and the division of the proposal, use the values
in whole seconds that the report shows ([command-line.md](command-line.md) › Output). Measured human time is a lower
bound: no source sees thinking,
discussion, or reading away from the tools.

## Agent time

An input to an agent is a prompt, a queued message, a tool result, or a notification. A turn starts at an input that
reaches an agent with no turn in progress. Tool results, queued messages, and notifications that arrive while a turn is
in progress continue it, so the execution of a tool is part of the turn. A turn ends at the last agent output before the
agent waits, with no tool call pending, for a prompt or a notification, at an interruption, or at the end of the
session. A turn with no event for longer than the stale limit (default 4 hours) ends at its last event. A subagent has
its own turns, from its own events.

The agent time of an agent is the duration of its turns without two kinds of wait:

- its blocked time;
- the time in which it waits for its own subagents, which the subagents count as their own agent time.

A wait for a subagent is the interval from a tool call of the category `delegate` to its tool result; a background
subagent returns its tool result at once, so its wait is near zero. A `delegate` call that gets no tool result,
because the settle time completed the session without it, waits until the next event of its agent, an interruption,
or the last event of the session, as a decision request without a decision does (see Blocked time).

The agent time of a set of agents is the sum over the agents. The ratio of this sum to the union of the same intervals
shows how much agents work in parallel.

## Blocked time

Blocked time runs from a decision request to its decision: a permission request, a question to the person, or a plan
approval. It is a state of the agent and counts whether or not the person is present. A decision request that gets no
decision ends at the next event of its agent, at an interruption, or at the last event of the session. A decision
request that a configured rule answers produces no blocked time worth reporting, because the rule answers at once.

## Activity classes

Each instant of a person's day falls in exactly one activity class. The classes come from three unions: measured human
time with manual entries, agent time, and blocked time.

| Class | Human time | Agent time | Blocked time |
|---|---|---|---|
| Person only | yes | no | any |
| Supervised | yes | yes | any |
| Unattended | no | yes | any |
| Blocked | no | no | yes |
| Idle | no | no | no |

The Blocked class is therefore blocked time with no person present and no agent working. An instant in which the
person is present and an agent is blocked is person only: the person is the one who must act.

A project, or a work item, has its own activity classes: they use the human time that the split rule gives to it and
the agent time and blocked time attributed to it, and they have no Idle class. While the person works on one project
and an agent works on another, the first project is person only and the second is unattended. The classes of the
projects therefore do not add up to the classes of the person, and reports say so.

## Calendar time

Calendar time (Phase 2) of a work item runs from its first to its last event of work, from any source: human signals,
agent events, tool events, decisions, manual entries by their interval, timesheet entries by their day, and declared
usage by its interval or by the local day of its timestamp. Annotations, retractions, and purges record bookkeeping, not
work, and do not count.

## Attribution

Each event is attributed to independent dimensions: person, machine, tool, model, project, and work item; provider,
release, and milestone from Phase 2; cost centre from Phase 4. A report is a grouping over a
period. Identity rules resolve the project of each event at
report time from its repository identity, folder, branch, and date; by default one repository is one project (ADR 0009).
A project is a project identifier with a name (ADR 0019): by default the identifier is the repository identity, and the
name is the last part of its path, or the first 12 characters of a root-commit hash; a project identifier that is not a
repository identity is its own name; an entry of the person configuration gives another name. When two project
identifiers have the same default name, reports show as many parts of the path as make the names different; a name that
the person configuration gives to two project identifiers is a configuration error, and the report shows both
identifiers. Reports group by project identifier and show the name, and they warn about declared events whose project
identifier no identity rule, no entry of the person configuration, and no repository identity gives (ADR 0019). A work
item has a work item identifier and a name in the same way; without an entry of the person configuration, its name is
its identifier. Work items come from annotations and declared events, and a work item always belongs to one project. An
event without its own folder, branch, or repository identity takes those of the previous event of its session; events
with the same `timestamp` take them in the order of their event keys.
Annotations override the derived attribution of a session or an interval. An annotation that gives a work item and no
project keeps the project that attribution gives to the event; an annotation that gives a project and no work item also
removes the work item of earlier annotations, which belongs to the earlier project. When the event has no project, the
work item of an annotation does not apply: the event stays unattributed, and the report warns and names the annotation.
An interval annotation applies to the events whose `timestamp` is inside its interval. Where annotations overlap, they
apply in the order of their `timestamp` with these rules, and equal instants resolve by event key. Where manual entries
in mode `overlapping` overlap each other, the one with the latest `timestamp` applies, and equal instants resolve by
event key. Events whose project cannot be resolved, also because of a configuration error
([configuration.md](configuration.md) › Matching), go to the unattributed bucket; an event with a project and no work
item stays in the part of its project that has no work item. Blocked time takes the attribution of its decision request.
Reports show the share of the human time and of the agent time of each project and work item that rests on an inferred
repository identity (ADR 0018).

The split rule gives each instant of measured human time to one human signal (ADR 0021). Each interval of human time
belongs to the human signal that ends it: a signal gap to its later signal, a response interval and a minimum attention
interval to their own signal. An instant that more than one interval contains belongs to the interval that ends first,
and intervals that end at the same instant resolve by the event key of their signal. The instant takes the project and
the work item of that human signal, so projects and work items need no separate split.

The agent time of a turn whose events resolve to more than one project or work item divides at its events: each part
between two consecutive events, without blocked time and waits for subagents, takes the attribution of the event
that ends it.

Attributed parts and the unattributed bucket always add up to the human time of the period: the per-project totals of
a timesheet equal the daily total.

## Days and weeks

Data stays in UTC; days and weeks exist only in reports (ADR 0022). The time zone of a person at an instant comes from
the time-zone history of the person: a dated list of IANA time zones, each valid from an instant, in the person
configuration (see [configuration.md](configuration.md)). At setup the history holds the time zone of the operating
system; the person adds an entry for a journey or a move, and every report recomputes. The time zone belongs to the
person, not to the machine that runs an agent, an ingestion, or a report.

The local time of an instant comes from the time zone that is valid at that instant, and the instant belongs to the
local day of the latest date whose day start hour, valid on that date, is not after that local time. The day start hour
comes from a dated list in the person configuration, each hour valid from a local date; the first run writes 00:00. A
later hour, such as 04:00, keeps work after midnight on the day before. The day start hour is a fact of the person, not
a report parameter, so timesheet entries and every report use the same local days; a change starts on a date and leaves
earlier days as they were. Because each instant has exactly one local time, a day at a change of daylight saving has 23
or 25 hours, the day before a change of the day start hour is longer or shorter by the difference, and a journey changes
the length of the day in which it starts; a journey to the west across the start of a day can give that day two parts.
None of these needs another rule, and an interval of human time or agent time that crosses the start of a day divides
there. A local time that a command reads, such as the instant of a manual entry, is its first occurrence when a change
of daylight saving repeats it, and the first instant after the change when the change skips it.

Weeks come with the weekly reports of Phase 2. A week starts on the first day of the week, a report parameter that is
Monday by default, as in ISO 8601. A week is identified by the date of its first day; when the first day is Monday,
reports also show the ISO 8601 week number. The rule applies to the whole report, so the weeks of all persons in one
report are the same.

## Cost

Cost is computed from Phase 2. List-price cost uses the token usage, the request counts, and the price factors of each
agent output with the price table valid on its date, keyed by provider and model identifier (ADR 0007, ADR 0024). A
token category, a request type, or a value of a price factor without a price makes the cost unknown, never zero and
never a guess. Actual cost of a `subscription` cost source divides the fee of each billing period over the usage of that
period that the ledger knows (ADR 0013): the imported total when an imported cost source gives one, otherwise the sum of
measured and declared usage. With an imported total, the share that no measured or declared usage explains is
unattributed; without one, the report states that the unmeasured share is unknown and that the allocated cost of each
project is an upper bound.

## Reproducibility

Every report records the report parameters, the rules, and the dated facts it used (idle gap, stale limit, minimum
attention time, headless prompts, timesheet granularity, language, and, from Phase 2, the first day of the week;
identity rules, category rules; time-zone history, day start hours, price tables), the version of the ledger and of
the time-zone database, and the state of the store it read ([architecture.md](architecture.md) › Report record). A
person freezes a report when they
give it to someone: the report keeps exactly the document that the person gives, and later reports of that period show
their differences against it, instead of replacing it; the rule of the frozen reports is in
[command-line.md](command-line.md) › Frozen reports.

## Uncertainty

Every command that shows the human time of a day — `report timesheet`, `report day`, and `timesheet <day>`
([command-line.md](command-line.md) › Reports) — also shows it, for a measured day, at idle gaps of 5, 10, and 15
minutes and at the idle gap in use, so that the reader sees how much the figure depends on the parameter.

## To be confirmed

- Whether reports show an upper bound of human time next to the measured lower bound, and how it is defined (for example
  signal gaps up to a longer idle gap, or the presence span with long breaks removed): measured human time covers a
  median of about 20 % of the presence span. To specify at the start of Phase 2, with the declared days of Phase 1 as
  evidence.
- Whether human time extends after the last agent output of a session when no human signal follows, to cover the reading
  of that output, and by how much. To specify at the start of Phase 2, with the declared days of Phase 1 as evidence.
- Unit of calendar time: elapsed days, days with activity, or working days; and how a single late event affects it. To
  specify at the start of Phase 2.
- Releases and milestones: how events are attributed to a release (date window, git tag, release line, explicit
  mapping), the bucket of unreleased work, and the rule for milestones. To specify at the start of Phase 2.
- Work items and estimates: work-item type, size class (from size counters, ADR 0012, and from repositories), the rule
  for AI mode, the reference class of the estimator, completion, how an estimate is recorded with the instant of its
  recording, and the check that an estimate precedes the first event of its work item. To specify at the start of
  Phase 5.
- Cost details: the basis that divides a subscription (tokens or list-price cost), how the ledger knows which cost
  source paid each agent output (subscription or metered account), billing periods that differ from report periods,
  provider resolution from the provider hint, token categories of other providers, the prices of request types and price
  factors, and how costs in different currencies combine (for example a dated table of exchange rates). To specify at
  the start of Phase 2.
- Team export: format, granularity, version of schema and parameters, stable export identity, person identity, shared
  identity rules, and which fields are removed. To specify at the start of Phase 4.
