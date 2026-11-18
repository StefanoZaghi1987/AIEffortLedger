# AI Effort Ledger

The measurement of effort in software work that a person does fully or partly with AI agents, after the work is done.
The same data later supports estimates for new work. Each term gives the Italian equivalent that reports and skills
use in Italian.

## Actors and tools

**Person**:
A human who does, supervises, or reviews the work and whose time is measured.
_Italian_: persona
_Avoid_: user, developer, operator

**Agent tool**:
A program through which a person works with agents, such as Claude Code, Claude Desktop, or Codex.
_Italian_: strumento agentico
_Avoid_: client, assistant, IDE

**Provider**:
The company that serves a model and bills its usage, which can differ from the company that trained the model.
_Italian_: fornitore

**Agent**:
One running instance of a model that executes work: the main agent of a session or a subagent.
_Italian_: agente
_Avoid_: AI, bot, assistant, the name of a product or model

**Main agent**:
The agent that receives the prompts of the person in a session.
_Italian_: agente principale

**Subagent**:
An agent that another agent starts to execute a delegated part of the work.
_Italian_: subagent
_Avoid_: child agent, sidechain

**Foreground subagent**:
A subagent whose starting agent waits for its result before it continues.
_Italian_: subagent in primo piano

**Background subagent**:
A subagent whose starting agent continues without waiting and receives a notification at the end.
_Italian_: subagent in background

**Session**:
One identified exchange between a person and an agent tool; a resumed session continues it, a forked session is a new
session that starts with a copy of its history.
_Italian_: sessione
_Avoid_: chat, conversation, transcript (the transcript is a source, not the session)

**Machine**:
The computer on which the work of a session happened.
_Italian_: macchina

## Signals and decisions

**Human signal**:
An event that shows that a person attended to the work: a prompt, a queued message, a decision made by the person, or
an interruption.
_Italian_: segnale umano

**Queued message**:
A message that a person types while an agent works, delivered to the agent when it can receive it.
_Italian_: messaggio in coda

**Interruption**:
A stop of an agent turn by the person.
_Italian_: interruzione

**Decision request**:
A point at which an agent cannot continue without a decision of a person: a permission request, a question to the
person, or a plan approval.
_Italian_: richiesta di decisione

**Decision source**:
Whether a decision request was answered by the person or by a configured rule; only answers of the person are human
signals.
_Italian_: origine della decisione

## Time

**Human time**:
Time in which a person attends to the work, with or without an agent.
_Italian_: tempo persona
_Avoid_: effective hours, ore effettive, active hours, man-hours

**Agent time**:
Time in which an agent executes turns, without its blocked time and without waiting for its own foreground subagents;
the agent time of agents that run in parallel adds up.
_Italian_: tempo agente
_Avoid_: AI hours, machine time

**Blocked time**:
Time in which an agent waits for the answer to a decision request, whether or not the person is present.
_Italian_: tempo bloccato
_Avoid_: waiting time, idle agent time

**Calendar time**:
Elapsed time from the first to the last event of a work item.
_Italian_: tempo di calendario
_Avoid_: lead time

**Turn**:
One unit of agent execution, from an input to the last agent output before the next input of any kind.
_Italian_: turno
_Avoid_: request, round

**Idle gap**:
The longest silence that still counts as continuous human time, both between two human signals and between an agent
output and the human signal that reacts to it.
_Italian_: soglia di inattività
_Avoid_: pause threshold, timeout

**Signal gap**:
An interval of human time between two human signals of one session that are closer than the idle gap.
_Italian_: intervallo fra segnali

**Response interval**:
An interval of human time from an agent output to the human signal that reacts to it, when it is shorter than the idle
gap.
_Italian_: intervallo di risposta

**Minimum attention time**:
The human time that an isolated human signal counts for.
_Italian_: attenzione minima

**Activity class**:
One of five mutually exclusive states of an instant: person only, supervised, unattended, blocked, idle.
_Italian_: classe di attività

**Supervised time**:
Time in which human time and agent time overlap.
_Italian_: tempo supervisionato

**Unattended time**:
Agent time with no overlapping human time, for example a night run or a long-running task.
_Italian_: tempo non supervisionato
_Avoid_: autonomous hours, background time

**Manual entry**:
An interval of human time that a person declares because no source recorded it; it is either additional to or
overlapping with measured human time.
_Italian_: registrazione manuale
_Avoid_: estimated day, giorno stimato, fixed summary

**Measured value**:
A value that the ledger derives from a source other than a manual entry.
_Italian_: valore misurato

**Declared value**:
A value that comes from a manual entry.
_Italian_: valore dichiarato

## Data

**Source**:
A place that records activity: a native log, a hook, a telemetry stream, a manual entry, or an imported file.
_Italian_: sorgente

**Adapter**:
The part of the ledger that reads one source format and produces events.
_Italian_: adattatore
_Avoid_: parser, collector, importer

**Ingestion**:
The reading of a source by an adapter and the addition of the resulting events to the store.
_Italian_: acquisizione
_Avoid_: import, sync (as the name of the operation)

**Event**:
One atomic, timestamped fact that comes from a source.
_Italian_: evento
_Avoid_: record, log line, block

**Store**:
The private, append-only collection of the events of one person.
_Italian_: archivio
_Avoid_: database, data file, ledger (the name of the tool)

**Annotation**:
An event that sets labels on a session or a time interval, such as its work item, and adds no time.
_Italian_: annotazione

**Retraction**:
An event that cancels an earlier event without removing it from the store.
_Italian_: ritiro

**Purge**:
The physical removal of events from the store, the only exception to append-only.
_Italian_: eliminazione definitiva

## Attribution

**Project**:
A body of work identified by its repository, not by the folder from which a tool was started.
_Italian_: progetto

**Unattributed**:
The bucket of events whose project or work item cannot be resolved, kept so that attributed parts add up to totals.
_Italian_: non attribuito

**Work item**:
One unit of planned work, such as a task, an issue, or an evolution, that collects effort and can carry an estimate.
_Italian_: unità di lavoro
_Avoid_: activity, job, task (as the generic term)

**Release**:
A published version of the deliverable of a project.
_Italian_: rilascio
_Avoid_: version, stable point, punto stabile

**Milestone**:
A planned point in the schedule of a project, independent of releases.
_Italian_: milestone

**Attribution**:
The assignment of an event to a project, a work item, a release, a milestone, and other dimensions.
_Italian_: attribuzione

**Split rule**:
The rule that divides overlapping human time among the projects or work items of sessions that run at the same time,
so that the parts add up to the total.
_Italian_: regola di ripartizione

**Period**:
A calendar interval that a report covers: a day, a week, a month, or a custom interval.
_Italian_: periodo

**Frozen period**:
A period whose report was given to someone and is no longer recomputed.
_Italian_: periodo congelato

## Cost

**Price table**:
A dated list of prices per provider, model, and token category.
_Italian_: listino
_Avoid_: rate card, tariff

**List-price cost**:
The token usage multiplied by the price table that applies on the date of use.
_Italian_: costo a listino
_Avoid_: consumption cost, API cost, pay-as-you-go cost

**Actual cost**:
The money that is really paid for model usage, as given by a cost source.
_Italian_: costo effettivo

**Cost source**:
An account through which a person or a team pays for model usage; its type is subscription, metered, or imported.
_Italian_: fonte di costo
_Avoid_: plan, billing

**Billing period**:
The interval that one charge of a cost source covers, such as one month of a subscription.
_Italian_: periodo di fatturazione

**Hourly rate**:
The cost of one hour of human time of a person, valid from a date.
_Italian_: tariffa oraria

**Person cost**:
Human time multiplied by the hourly rate of the person.
_Italian_: costo persona

**Cost centre**:
An organizational unit to which effort and cost are charged, independent of projects.
_Italian_: centro di costo

## Reporting and estimation

**Effort**:
The human time, agent time, blocked time, calendar time, token usage, and cost of a work item, reported as separate
quantities.
_Italian_: effort
_Avoid_: hours (as a single total), impegno

**Timesheet**:
The record of the human time of a person per day and per project.
_Italian_: registro attività
_Avoid_: report, log

**Team export**:
An aggregate of the effort of one person, without content, that the person reviews before sharing it.
_Italian_: export di team

**Estimate**:
A forecast of the human time, agent time, and cost of a work item, recorded before the work starts.
_Italian_: stima

**Actuals**:
The measured and declared effort of a completed work item.
_Italian_: consuntivo

**AI mode**:
The share of a work item that agents do: full, partial, or none.
_Italian_: modalità AI (completa, parziale, assente)

**Reference class**:
The set of completed work items with the same type, size class, and AI mode.
_Italian_: classe di riferimento
