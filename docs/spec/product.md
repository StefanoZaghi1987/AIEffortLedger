# Product

What the ledger is for, for whom, what it does not do, and what each phase delivers. Terms follow
[GLOSSARY.md](../../GLOSSARY.md).

## Objective

The ledger measures the effort of software work that a person does fully or partly with agents, after the work is done,
and keeps the data to estimate new work. It separates human time from agent time and from calendar time (ADR 0001),
attributes them to projects and work items, proposes a daily timesheet from measured values that the person confirms,
and computes cost at report time.

Usage tools that exist count tokens and cost; none of them separates human time from agent time, divides time among
projects, or takes declared values ([sources-2026-11.md](../research/sources-2026-11.md)). A timesheet written from
memory is not reliable: in a controlled trial, persons who wrote code believed that agents made them faster when the
measurement showed that they were slower (same note).

## Persons

- **A person** who works with agent tools, on one or more machines, and wants a timesheet and an estimate basis from
  what the tools record. The person is the only reader of their store (ADR 0003).
- **A team** (Phase 4), whose members combine team exports that each person reviews before sharing.

## Non-goals

- No monitoring of a person by another person: data leaves the store only in a team export that the person reviews.
- No recording of the screen, the keyboard, or the applications of a person; a human-activity tracker is at most an
  optional source (Phase 6).
- No text of prompts, responses, tool input, or code in the store (ADR 0003).
- No network access, no server, no telemetry.
- No conversion of agent time into human time, and no single "hours" figure (ADR 0001).
- No score or ranking of persons, and no invoicing.
- No change to what another program owns: the ledger shows and advises, the person changes settings of agent tools.

## Phases

| Phase | Content |
|---|---|
| 0 | Glossary, specifications, ADRs, measurement prototype, validation, review |
| 1 | Core: the daily timesheet of one person, from Claude Code and Claude Desktop (see Phase 1) |
| 2 | Attribution and reports: releases and milestones, weekly, monthly, and custom periods, declared usage, list-price cost, actual cost and subscription division, hourly rates and person cost, labels and session titles |
| 3 | Coverage: Claude Code plugin with skills and hooks; integration for other agent tools (open: an MCP server over the command line, ingestion of events that other programs write in the normalized form); an adapter for another agent tool, such as Codex, only with real samples from a person who uses that tool |
| 4 | Team: team export, merge, team reports, project configuration, pseudonym |
| 5 | Estimation: work-item types and size classes, estimates, estimate-versus-actuals dataset, estimator |
| 6 | Optional: OpenTelemetry ingestion, ingestion of provider analytics, human-activity tracker as a source |

Each phase starts with the specification of the points that the `To be confirmed` sections of the specifications list
for it, and with an implementation plan. A sentence of a specification without a phase applies from Phase 1; a
sentence for a later phase names it.

## Phase 1

**Scope.** All commands of [command-line.md](command-line.md):

- setup, the scheduled ingestion, and the machine label;
- ingestion of the native logs of Claude Code and Claude Desktop ([claude-code-adapter.md](claude-code-adapter.md)),
  with complete events only, repository identity, and the warning about lost events;
- the store, the local index, purges with a corrected version, and retractions;
- the person configuration: time-zone history, day start hours, project names, identity rules, category rules,
  preferred remotes, settle time, and defaults of report parameters;
- human time, agent time, blocked time, activity classes, the split rule, annotations with projects and work items,
  manual entries, timesheet proposals, and timesheet confirmations;
- the daily timesheet and the report of a day, as text and JSON, in English and Italian, with frozen periods.

The adapter writes every field of [event-schema.md](event-schema.md) that the native log gives, except session titles,
which need consent (Phase 2), also the fields that only later phases use, such as token usage, model, and size counters:
native logs disappear after their retention period, and a field that ingestion does not write is lost.

**Acceptance criteria.**

1. After `setup`, the store holds the events of every native log of the machine within its retention period; a second
   `ingest` without new records adds no event.
2. The same native logs give the same store at any hour of ingestion and in any order of files, except in the two
   cases of [ingestion.md](ingestion.md) › Adapters, and segments of two machines give the same reports in any order.
3. The scenarios of the prototype give, in the core, the human time, agent time, blocked time, and activity classes
   computed by hand.
4. In every daily timesheet, the measured values of the projects, work items, and unattributed time add up to the
   measured human time of the day, and on a declared day the declared values add up to its total.
5. A day confirmed on two machines before the file-sync service copies the segments shows the latest confirmation and
   a warning.
6. A purge with a corrected version, followed by an ingestion with that version, gives the corrected events; a purge
   without one keeps its keys out for good.
7. A store built from the fixtures holds no text of the prompts, responses, tool input, or code of the fixtures.
8. The tests pass on Windows, Linux, and macOS with Python 3.11 and the newest Python release.
9. On a laptop, the first ingestion of 30 days of native logs takes less than 1 minute, and a daily timesheet of one
   month less than 5 seconds.

**End of the phase.** Phase 2 starts its specification when the person has at least 20 declared days, the evidence
that the open points of [metrics.md](metrics.md) on the upper bound of human time need.
