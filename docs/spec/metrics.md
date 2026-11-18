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
session that a script, a schedule, or an orchestrator started (see [event-schema.md](event-schema.md)). Measured human
time of a person is the union of three kinds of interval:

- **signal gap**: two consecutive human signals of the person, from any of the sessions of the person, not more than
  the idle gap apart;
- **response interval**: from the last agent output or decision request of a session to the human signal of the same
  session that follows it, when not longer than the idle gap;
- **minimum attention**: an interval of the minimum attention time that ends at a human signal that belongs to no
  other interval.

The default idle gap is 10 minutes. The human signals of all sessions, agent tools, and machines of the person form
one stream, so a person who moves between parallel sessions stays present, and an instant counts once. Signal gaps
between sessions of different projects, and overlaps of their intervals, go to projects through the split rule.
Reports show the share of human signals that come from sessions of unknown invocation.

### Declared values

A manual entry is an interval with a start, an end, a project, an optional work item, and a note. It is not a human
signal. Its mode decides how it combines with measured human time:

- `overlapping`: the entry merges with measured human time by union;
- `additional`: the entry counts only where it does not overlap measured human time, and the report warns about every
  overlap it removed.

A timesheet entry declares the human time of one day and one project, with a duration, an optional work item, and a
note, and no start or end (ADR 0011). The ledger proposes the timesheet entries of a day from measured values; the
person confirms or changes them, and only confirmed entries enter the store. A day, a project, and a work item have at
most one timesheet entry; a change retracts the old entry and adds a new one. The entries of the work items of a
project add up to the declared value of the project. A timesheet entry takes no part in activity classes, in the split
rule, or in the union with manual entries.

Declared usage gives agent time, token usage, or actual cost of work that no source recorded, such as a cloud session.
Its values appear in their own quantities as declared values; declared token usage with a model gets a list-price
cost like measured usage.

Reports show measured and declared values in separate columns. Total human time of a day and a project is the
timesheet entries when they exist, otherwise the union of measured human time and manual entries. The report warns
when a timesheet entry is lower than the measured human time of the same day and project. Measured human time is a
lower bound: no source sees thinking, discussion, or reading away from the tools.

## Agent time

An input to an agent is a prompt, a queued message, a tool result, or a notification. A turn starts at an input that
reaches an agent with no turn in progress. Tool results, queued messages, and notifications that arrive while a turn is
in progress continue it, so the execution of a tool is part of the turn. A turn ends at the last agent output before
the agent waits, with no tool call pending, for a prompt or a notification, at an interruption, or at the end of the
session. A turn with no event for longer than the stale limit (default 4 hours) ends at its last event. A subagent has its own turns, from
its own events.

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

## Calendar time

Calendar time of a work item runs from its first to its last event of work, from any source: human signals, agent
events, tool events, decisions, manual entries by their interval, timesheet entries and declared usage by their day.
Annotations, retractions, and purges record bookkeeping, not work, and do not count.

## Attribution

Each event is attributed to independent dimensions: person, machine, tool, provider, model, project, work item,
release, milestone, and cost centre. A report is a grouping over a period. Identity rules resolve the project of each
event at report time from its repository identity, folder, branch, and date; by default one repository is one project
(ADR 0009). An event without its own folder, branch, or repository identity takes those of the previous event of its
session. Annotations override the derived attribution of a session or an interval; where annotations overlap, the
most recent one applies. Events whose project or work item cannot be resolved go to the unattributed bucket.

When human time can belong to sessions of more than one project or work item, the split rule divides it among them.
Attributed parts and the unattributed bucket always add up to the human time of the period: the per-project totals of
a timesheet equal the daily total.

Data stays in UTC; a session across midnight belongs to two days only in reports.

## Cost

List-price cost uses the price table valid on the date of each agent output, keyed by provider and model identifier
(ADR 0007). A token category without a price makes the cost unknown, never zero. Actual cost of a `subscription` cost
source divides the fee of each billing period over the usage of that period that the ledger knows (ADR 0013): the
imported total when an imported cost source gives one, otherwise the sum of measured and declared usage. With an
imported total, the share that no measured or declared usage explains is unattributed; without one, the report states
that the unmeasured share is unknown and that the allocated cost of each project is an upper bound.

## Reproducibility

Every report records the parameters it used (idle gap, stale limit, minimum attention time, split rule, identity
rules, price tables) and the state of the store it read. A person can freeze a period after giving its report to
someone: the frozen report is kept as given, and later reports show any difference against it instead of replacing
it.

## Uncertainty

Reports that show human time also show it at idle gaps of 5, 10, and 15 minutes, so that the reader sees how much the
figure depends on the parameter.

## To be confirmed

- Minimum attention time of an isolated human signal (the prototype uses 1 minute; from 30 to 120 seconds human time
  changes by −2 % to +3 %, see [validation-2026-11.md](../research/validation-2026-11.md)).
- Whether reports show an upper bound of human time next to the measured lower bound, and how it is defined (for
  example signal gaps up to a longer idle gap, or the presence span with long breaks removed): measured human time
  covers a median of about 20 % of the presence span.
- Split rule, needed for the first timesheet: proportional to the human signals of each session in the contested
  interval, or equal parts; how a signal gap between sessions of two projects is divided; how the split nests when
  projects and work items are both split; whether activity classes have a meaning per project when the person works
  on one project while an agent runs on another. In the prototype data the overlap between projects is about 3 % of
  human time, and signal gaps across sessions add about 6 % (see [review-2026-11.md](../research/review-2026-11.md)).
- Timesheet entries, needed for the first timesheet: which measured values the proposal uses (for example measured
  human time, agent time, and presence span per project); the granularity and the rounding that keep the per-project
  values equal to the day total; how unattributed measured human time of a day combines with the timesheet entries of
  that day; how a declared project value divides among work items when its entries name no work item.
- Attribution of a turn whose events resolve to two projects, for example after a change of folder inside the turn.
- Whether human time extends after the last agent output of a session when no human signal follows, to cover the
  reading of that output, and by how much.
- Unit of calendar time: elapsed days, days with activity, or working days; and how a single late event affects it.
- Releases and milestones: how events are attributed to a release (date window, git tag, release line, explicit
  mapping), the bucket of unreleased work, and the rule for milestones. To specify at the start of the release
  reporting phase.
- Work items and estimates: work-item type, size class (from size counters, ADR 0012, and from repositories), the
  rule for AI mode, completion, and the check that an estimate precedes the first event of its work item. To specify
  at the start of the estimation phase.
- Cost details: the basis that divides a subscription (tokens or list-price cost), how the ledger knows which cost
  source paid each agent output (subscription or metered account), billing periods that differ from report periods, provider resolution from the provider hint, token categories of other providers, and how costs in
  different currencies combine (for example a dated table of exchange rates). To specify at the start of the cost
  phase.
- Time zones: a dated time-zone history of the person for travel and moves, the day of a timesheet entry, ISO weeks,
  and days of 23 or 25 hours at daylight-saving changes. To specify with the first timesheet.
- Team export: format, granularity, version of schema and parameters, stable export identity, person identity, shared
  identity rules, and which fields are removed. To specify at the start of the team phase.
- Private configuration: where hourly rates, cost sources, time-zone history, identity rules, label allow-list, and
  estimates live. To specify with the first command-line release.
