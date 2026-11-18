# Metrics

How the ledger turns events into effort. Terms follow [GLOSSARY.md](../../GLOSSARY.md); events follow
[event-schema.md](event-schema.md); the reasons behind the main choices are in [docs/adr](../adr).

## Quantities

| Quantity | Unit | Across parallel sessions | Source |
|---|---|---|---|
| Human time | person-hours | union | human signals, agent outputs, manual entries |
| Agent time | agent-hours | sum over agents | turns |
| Blocked time | hours | union | decision requests and their decisions |
| Calendar time | days | first to last event | all events of a work item |
| Token usage | tokens per category and model | sum | agent outputs |
| List-price cost | currency | sum | token usage × price table |
| Actual cost | currency | sum | cost sources |
| Person cost | currency | sum | human time × hourly rate |

The quantities are never added together or converted into each other (ADR 0001).

## Human time

Human signals are prompts, queued messages, interruptions, and decisions whose source is the person, from any agent of
any session. A decision made by a configured rule is not a human signal. Measured human time of a person is the union
of three kinds of interval:

- **signal gap**: two consecutive human signals of the same session closer than the idle gap;
- **response interval**: from an agent output to the human signal of the same session that reacts to it, when shorter
  than the idle gap;
- **minimum attention**: an interval of the minimum attention time that ends at a human signal that belongs to no
  other interval.

The default idle gap is 10 minutes. Intervals of all sessions, tools, and machines of the person merge by union, so an
instant counts once. Time between signals of two different sessions belongs to neither session; overlaps between
sessions go to projects through the split rule.

### Manual entries

A manual entry is an interval with a start, an end, a project, an optional work item, and a note. It is not a human
signal. Its mode decides how it combines with measured human time:

- `overlapping`: the entry merges with measured human time by union;
- `additional`: the entry counts only where it does not overlap measured human time, and the report warns about every
  overlap it removed.

Reports show measured and declared values in separate columns, and their union as total human time. Measured human
time is a lower bound: no source sees thinking, discussion, or reading away from the tools.

## Agent time

An input to an agent is a prompt, a queued message, a tool result, or a notification. A turn starts at an input that
reaches an agent with no turn in progress, and ends at the last agent output before the next input of any kind, or at
the end of the session. A turn with no event for longer than the stale limit (default 4 hours) ends at its last event.
A subagent has its own turns, from its own events.

The agent time of an agent is the duration of its turns without two kinds of wait:

- its blocked time;
- the time in which it waits for its own foreground subagents, which the subagents count as their own agent time.

The agent time of a set of agents is the sum over the agents. The ratio of this sum to the union of the same intervals
shows how much agents work in parallel.

## Blocked time

Blocked time runs from a decision request to its decision: a permission request, a question to the person, or a plan
approval. It is a state of the agent and counts whether or not the person is present. A decision request that a
configured rule answers produces no blocked time worth reporting, because the rule answers at once.

## Activity classes

Each instant of a person's day falls in exactly one activity class. The classes come from three unions: human time,
agent time, and blocked time.

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

Calendar time of a work item runs from its first to its last event, from any source.

## Attribution

Each event is attributed to independent dimensions: person, machine, tool, provider, model, project, work item,
release, milestone, and cost centre. A report is a grouping over a period. Project identity follows ADR 0004;
annotations override the derived attribution of a session or an interval. Events whose project or work item cannot be
resolved go to the unattributed bucket.

When sessions of different projects or work items overlap in human time, the split rule divides the overlap among
them. Attributed parts and the unattributed bucket always add up to the human time of the period: the per-project
totals of a timesheet equal the daily total.

Data stays in UTC; a session across midnight belongs to two days only in reports.

## Cost

List-price cost uses the price table valid on the date of each agent output, keyed by provider and model identifier
(ADR 0007). A token category without a price makes the cost unknown, never zero. Actual cost of a `subscription` cost
source divides the fee of each billing period over all usage of that period; the share that no measured project
explains is reported as unattributed.

## Reproducibility

Every report records the parameters it used (idle gap, stale limit, minimum attention time, split rule, attribution
rules, price tables) and the state of the store it read. A person can freeze a period after giving its report to
someone: the frozen report is kept as given, and later reports show any difference against it instead of replacing
it.

## Uncertainty

Reports that show human time also show it at idle gaps of 5, 10, and 15 minutes, so that the reader sees how much the
figure depends on the parameter.

## To be confirmed

- Minimum attention time of an isolated human signal (the prototype uses 1 minute).
- Split rule for overlapping human time: proportional to the human signals of each session in the overlap, or equal
  parts; how the split nests when projects and work items are both split; whether activity classes have a meaning per
  project when the person works on one project while an agent runs on another. In the prototype data the overlap is
  1 % of human time.
- Whether human time extends after the last agent output of a session when no human signal follows, to cover the
  reading of that output, and by how much.
- Unit of calendar time: elapsed days, days with activity, or working days; and how a single late event affects it.
- Releases and milestones: how events are attributed to a release (date window, git tag, release line, explicit
  mapping), the bucket of unreleased work, and the rule for milestones. To specify at the start of the release
  reporting phase.
- Work items and estimates: work-item type, size class, the rule for AI mode, completion, and the check that an
  estimate precedes the first event of its work item. To specify at the start of the estimation phase.
- Cost details: the basis that divides a subscription (tokens or list-price cost), billing periods that differ from
  report periods, provider resolution when the source does not name it, and token categories of other providers. To
  specify at the start of the cost phase.
- Time zones: a dated time-zone history of the person for travel and moves, ISO weeks, and days of 23 or 25 hours at
  daylight-saving changes. To specify with the first timesheet.
- Team export: format, granularity, version of schema and parameters, stable export identity, person identity, shared
  project identity rules, and which fields are removed. To specify at the start of the team phase.
- Private configuration: where hourly rates, cost sources, time-zone history, identity rules, label allow-list, and
  estimates live. To specify with the first command-line release.
