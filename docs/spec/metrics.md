# Metrics

How the ledger turns events into effort. Terms follow [GLOSSARY.md](../../GLOSSARY.md); events follow
[event-schema.md](event-schema.md); the reasons behind the main choices are in [docs/adr](../adr).

## Quantities

| Quantity | Unit | Across parallel sessions of a person | Across persons | Source |
|---|---|---|---|---|
| Human time | person-hours | union | sum | human signals, agent outputs, manual entries, timesheet entries |
| Agent time | agent-hours | sum over agents | sum | turns, declared usage |
| Blocked time | hours | union | sum | decision requests and their decisions |
| Calendar time | days | first to last event | first to last event | all events of a work item |
| Token usage | tokens per category and model | sum | sum | agent outputs, declared usage |
| List-price cost | currency | sum | sum | token usage × price table |
| Actual cost | currency | sum | sum | cost sources, declared usage |
| Person cost | currency | sum | sum | human time × hourly rate |

The quantities are never added together or converted into each other (ADR 0001). Agent-hours of parallel agents add
up, so agent time can be longer than the clock time in which it happens; activity classes are clock time of one
person.

## Human time

Human signals are prompts, queued messages, interruptions, and decisions whose source is the person, from any agent of
any session of the person. A decision made by a configured rule is not a human signal, and neither is a prompt of a
session that a script, a schedule, or an orchestrator started (see [event-schema.md](event-schema.md)). A headless
prompt is the exception: no source shows whether a person or a script typed it, so the report parameter *headless
prompts* decides whether it is a human signal; the default is no. Measured human time of a person is the union of three
kinds of interval:

- **signal gap**: two consecutive human signals of the person, from any of the sessions of the person, not more than
  the idle gap apart;
- **response interval**: from the last agent output or decision request of a session to the human signal of the same
  session that follows it, when not longer than the idle gap;
- **minimum attention**: an interval of the minimum attention time that ends at a human signal that belongs to no
  other interval.

The default idle gap is 10 minutes, and the default minimum attention time is 1 minute. The human signals of all
sessions, agent tools, and machines of the person form one stream, so a person who moves between parallel sessions stays
present, and an instant counts once. Signal gaps between sessions of different projects, and overlaps of their
intervals, go to projects through the split rule. Reports show the share of human signals that come from sessions of
unknown invocation.

### Declared values

A manual entry is an interval with a start, an end, a project, an optional work item, and a note. It is not a human
signal. Its mode decides how it combines with measured human time:

- `overlapping`: the entry merges with measured human time by union, and its attribution applies to the whole
  interval; where it overlaps measured human time of another project or work item, the report warns about the change;
- `additional`: the entry counts only where it does not overlap measured human time, and the report warns about every
  overlap it removed.

A timesheet entry declares the human time of one day for one project, or for the unattributed time of the day, with a
duration, an optional work item, and a note, and no start or end (ADR 0011). A day, a project, and a work item have at
most one timesheet entry; a change retracts the old entry and adds a new one. The declared value of a project is the
sum of its entries; an entry without a work item stays in the part of the project that has no work item, and the
ledger does not divide it among work items. A timesheet entry takes no part in activity classes, in the split rule,
or in the union with manual entries.

The ledger proposes the timesheet entries of a day; the person confirms or changes them, and only confirmed entries
enter the store. The proposal has one entry for each project and work item with measured human time in the day, and
one for the unattributed time. Each proposed value is the measured human time with manual entries, after the split
rule, rounded up to the timesheet granularity (default 15 minutes): measured human time is a lower bound, so a
proposal is never lower than it. When the person gives the total human time of the day, the proposal divides that
total by the shares of measured human time, in units of the timesheet granularity, with the largest-remainder method,
so that the entries add up to the total. Agent time and the presence span appear next to the proposal as context,
never as proposed values.

A day with at least one confirmed timesheet entry is a declared day (ADR 0014): the sum of its timesheet entries is
all the human time of the person in that day, and its measured human time and manual entries are evidence. A day
whose entries are all retracted is a measured day again.

Declared usage gives agent time, token usage, or actual cost of work that no source recorded, such as a cloud session.
Its values appear in their own quantities as declared values; declared token usage with a model gets a list-price
cost like measured usage.

Reports show measured and declared values in separate columns, and the state of each day: measured or declared.
Total human time of a declared day is the sum of its timesheet entries; total human time of a measured day is the
union of measured human time and manual entries. The report warns when the declared value of a project in a declared
day is lower than its measured human time, also when the project has no entry. Measured human time is a lower bound:
no source sees thinking, discussion, or reading away from the tools.

## Agent time

An input to an agent is a prompt, a queued message, a tool result, or a notification. A turn starts at an input that
reaches an agent with no turn in progress. Tool results, queued messages, and notifications that arrive while a turn is
in progress continue it, so the execution of a tool is part of the turn. A turn ends at the last agent output before the
agent waits, with no tool call pending, for a prompt or a notification, at an interruption, or at the end of the
session. A turn with no event for longer than the stale limit (default 4 hours) ends at its last event. A subagent has
its own turns, from its own events.

The agent time of an agent is the duration of its turns without two kinds of wait:

- its blocked time;
- the time in which it waits for its own foreground subagents, which the subagents count as their own agent time.

The agent time of a set of agents is the sum over the agents. The ratio of this sum to the union of the same intervals
shows how much agents work in parallel.

## Blocked time

Blocked time runs from a decision request to its decision: a permission request, a question to the person, or a plan
approval. It is a state of the agent and counts whether or not the person is present. A decision request that gets no
decision ends at the next event of its session, at an interruption, or at the last event of the session. A decision
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

Calendar time of a work item runs from its first to its last event of work, from any source: human signals, agent
events, tool events, decisions, manual entries by their interval, timesheet entries and declared usage by their day.
Annotations, retractions, and purges record bookkeeping, not work, and do not count.

## Attribution

Each event is attributed to independent dimensions: person, machine, tool, provider, model, project, work item, release,
milestone, and cost centre. A report is a grouping over a period. Identity rules resolve the project of each event at
report time from its repository identity, folder, branch, and date; by default one repository is one project (ADR 0009).
A project is a project identifier with a name (ADR 0019): by default the identifier is the repository identity, and the
name is the last part of its path, or the first 12 characters of a root-commit hash; an entry of the person
configuration gives another name. Reports group by project identifier and show the name. An event without its own
folder, branch, or repository identity takes those of the previous event of its session. Annotations override the
derived attribution of a session or an interval; where annotations overlap, the most recent one applies. Events whose
project or work item cannot be resolved go to the unattributed bucket. Reports show the share of the human time and
agent time of each project that rests on an inferred repository identity (ADR 0018).

The split rule gives each instant of measured human time to one human signal. Each interval of human time belongs to
the human signal that ends it: a signal gap to its later signal, a response interval and a minimum attention interval
to their own signal. An instant that more than one interval contains belongs to the interval that ends first. The
instant takes the project and the work item of that human signal, so projects and work items need no separate split.

The agent time of a turn whose events resolve to more than one project or work item divides at its events: each part
between two consecutive events, without blocked time and waits for foreground subagents, takes the attribution of the
event that ends it.

Attributed parts and the unattributed bucket always add up to the human time of the period: the per-project totals of
a timesheet equal the daily total.

## Days and weeks

Data stays in UTC; days and weeks exist only in reports. The time zone of a person at an instant comes from the
time-zone history of the person: a dated list of IANA time zones, each valid from an instant, in the person
configuration (see [configuration.md](configuration.md)). At setup the history holds the time zone of the operating
system; the person adds an entry for a journey or a move, and every report recomputes. The time zone belongs to the
person, not to the machine that runs an agent, an ingestion, or a report.

The local day of a date starts at the day start hour that is valid on that date, and ends where the local day of the
next date starts. The day start hour comes from a dated list in the person configuration, each hour valid from a local
date; the first run writes 00:00. A later hour, such as 04:00, keeps work after midnight on the day before. The day
start hour is a fact of the person, not a report parameter, so timesheet entries and every report use the same local
days; a change starts on a date and leaves earlier days as they were. Because each instant has exactly one local time, a
day at a change of daylight saving has 23 or 25 hours, and the day before a change of the day start hour is longer or
shorter by the difference; neither needs another rule, and an interval of human time or agent time that crosses the
start of a day divides there.

A week starts on the first day of the week, a report parameter that is Monday by default, as in ISO 8601. A week is
identified by the date of its first day; when the first day is Monday, reports also show the ISO 8601 week number.
The rule applies to the whole report, so the weeks of all persons in one report are the same.

## Cost

List-price cost uses the price table valid on the date of each agent output, keyed by provider and model identifier
(ADR 0007). A token category without a price makes the cost unknown, never zero. Actual cost of a `subscription` cost
source divides the fee of each billing period over the usage of that period that the ledger knows (ADR 0013): the
imported total when an imported cost source gives one, otherwise the sum of measured and declared usage. With an
imported total, the share that no measured or declared usage explains is unattributed; without one, the report states
that the unmeasured share is unknown and that the allocated cost of each project is an upper bound.

## Reproducibility

Every report records the parameters and the dated facts it used (idle gap, stale limit, minimum attention time, headless
prompts, split rule, identity rules, category rules, time-zone history, day start hours, first day of the week,
timesheet granularity, price tables) and the state of the store it read. A person can freeze a period after giving its
report to someone: the frozen report is kept as given, and later reports show any difference against it instead of
replacing it.

## Uncertainty

Reports that show human time also show it at idle gaps of 5, 10, and 15 minutes, so that the reader sees how much the
figure depends on the parameter.

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
  for AI mode, completion, how an estimate is recorded with the instant of its recording, and the check that an estimate
  precedes the first event of its work item. To specify at the start of Phase 5.
- Cost details: the basis that divides a subscription (tokens or list-price cost), how the ledger knows which cost
  source paid each agent output (subscription or metered account), billing periods that differ from report periods,
  provider resolution from the provider hint, token categories of other providers, and how costs in different currencies
  combine (for example a dated table of exchange rates). To specify at the start of Phase 2.
- Team export: format, granularity, version of schema and parameters, stable export identity, person identity, shared
  identity rules, and which fields are removed. To specify at the start of Phase 4.
