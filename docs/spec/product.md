# Product

What the ledger is for, for whom, what it does not do, and what each phase delivers. Terms follow
[GLOSSARY.md](../../GLOSSARY.md).

## Objective

The ledger measures the effort of software work that a person does fully or partly with agents, after the work is done,
and keeps the data to estimate new work. It separates human time from agent time and from calendar time (ADR 0001),
attributes them to projects and work items, proposes a daily timesheet from measured values that the person confirms,
and, from Phase 2, computes cost at report time.

Usage tools that exist count tokens and cost; none of them separates human time from agent time, divides time among
projects, or takes manual entries ([sources-2026-11.md](../research/sources-2026-11.md)). A timesheet written from
memory is not reliable: in a controlled trial, persons who wrote code believed that agents made them faster when the
measurement showed that they were slower (same note).

## Persons

A **person** who works with agent tools, on one or more machines, wants a timesheet and an estimate basis from what
the tools record. The person is the only reader of their store (ADR 0003).

## Non-goals

- No monitoring of a person by another person: no command sends data to another person, and data leaves the store
  only when the person gives it.
- No recording of the screen, the keyboard, or the applications of a person.
- No text of prompts, responses, tool input, or code in the store (ADR 0003).
- No network access, no server, no telemetry: the ledger itself opens no connection in any phase; data that lives on
  the network, such as the usage that a provider shows, arrives as a file that the person exported (ADR 0025).
- No conversion of agent time into human time, and no single "hours" figure (ADR 0001).
- No score or ranking of persons, and no invoicing.
- No change to what another program owns: the ledger shows and advises, the person changes settings of agent tools.

## Phases

| Phase | Content |
|---|---|
| 0 | Glossary, specifications, ADRs, measurement prototype, validation, review |
| 1 | Core: the daily timesheet of one person, from Claude Code and Claude Desktop (see Phase 1) |
| 2 | Attribution and reports, in this order: weekly, monthly, and custom period reports with calendar time, token usage, and list-price cost by model; then declared usage, actual cost and subscription division, and labels; then the maintenance of the price table, the dated price rows and the provider rows that `config add price` and `config add model-provider` write over the rows that ship with the program |
| 3 | Integration with Claude Code: a plugin with hooks and skills, among them a skill that reads the price pages of a provider and proposes the rows for `config add price`, which the person confirms; the ledger never fetches and never parses a provider page |
| 4 | Estimation, in this order: the recording of an estimate before the work starts, with work-item types, size classes, and AI mode; then the estimate-versus-actuals dataset and the estimator, which gives an estimate from the reference class of a work item |

Each phase starts with the specification of the points that the `To be confirmed` sections of the specifications list
for it, and with an implementation plan. A sentence of a specification without a phase applies from Phase 1; a
sentence for a later phase names it.

## Phase 1

**Scope.** All commands of [command-line.md](command-line.md):

- setup, the scheduled ingestion, and the machine label;
- ingestion of the native logs of Claude Code and Claude Desktop ([claude-code-adapter.md](claude-code-adapter.md)),
  with complete events only, repository identity, and the warning about lost events;
- the store, the local index, purges with a corrected version, and retractions;
- the person configuration: time-zone history, day start hours, project names and work item names, identity rules,
  category rules, preferred remotes, settle time, and defaults of report parameters;
- human time, agent time, blocked time, activity classes, the split rule, annotations with projects and work items,
  manual entries, timesheet proposals, and timesheet confirmations;
- the daily timesheet and the report of a day, as text and JSON, in English and Italian, with frozen reports and
  their differences.

The adapter writes every field of [event-schema.md](event-schema.md) that the native log gives — also the fields that
only later phases use, such as token usage, request counts, price factors, model, and size counters — except the provider hint, of which no sample of a native log shows the source fact yet
(the open point of [claude-code-adapter.md](claude-code-adapter.md)): native logs disappear after their retention
period, and a field that ingestion does not write is lost.

**Acceptance criteria.**

1. After `setup`, the store holds the complete events of every native log of the machine within its retention period;
   a second `ingest` without new records adds no event.
2. The same native logs give the same store at any hour of ingestion and in any order of files, except in the three
   cases of [ingestion.md](ingestion.md) › Adapters, and segments of two machines give the same reports in any order;
   two stores are the same when they hold the same event keys with the same fields except `ingested_at`.
3. The scenarios of the prototype give, in the core, the human time, agent time, blocked time, and activity classes
   computed by hand.
4. In every daily timesheet, the measured human time of the projects, work items, and unattributed time adds up to
   the measured human time of the day; on a measured day their values with manual entries add up to the total human
   time of the day; and on a declared day their declared values add up to the total of its latest timesheet
   confirmation. The JSON document shows each sum exactly; a table, which leaves out the seconds, can fall short
   by less than one minute for each part ([command-line.md](command-line.md) › Output).
5. A day confirmed on two machines before the file-sync service copies the segments shows the latest confirmation and
   a warning.
6. A purge with a corrected version, followed by an ingestion with that version, gives the corrected events; a purge
   without one keeps its keys out for good.
7. A store built from the fixtures holds no text of the prompts, responses, tool input, or code of the fixtures.
8. The tests pass on Windows, Linux, and macOS with Python 3.11 and the newest Python release, in the workflow of
   [architecture.md](architecture.md) › Tests.
9. Every command of [command-line.md](command-line.md) has report tests of its text and JSON output, in English and
   Italian, from fixture stores, among them manual entries, annotations, retractions, and frozen periods.
10. On a laptop, with the invented native logs of the benchmark (30 days, 300,000 lines;
    [architecture.md](architecture.md) › Tests), the first ingestion takes less than 1 minute, a daily timesheet of
    one month less than 30 seconds, and the timesheet or the report of one day less than 5 seconds.

**End of the phase.** Phase 2 starts its specification when the person has at least 20 declared days, the evidence
that the open points of [metrics.md](metrics.md) on the upper bound of human time need.

## To be confirmed

- An MCP server over the command line, which opens no connection (Non-goals): whether Phase 3 takes it, and under
  which conditions. To specify at the start of Phase 3.
