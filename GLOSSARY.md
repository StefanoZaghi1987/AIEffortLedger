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
The agent that receives the prompts of a session.
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

**Tool**:
An operation that an agent can call, such as editing a file, running a command, or starting a subagent; not to be
confused with an agent tool.
_Italian_: tool
_Avoid_: function, command (as the generic term)

**Tool category**:
The normalized class of a tool, the same for every agent tool: edit, execute, read, search, web, delegate, decide, or
other.
_Italian_: categoria di tool

**Session**:
One identified exchange between a person and an agent tool; a resumed session continues it, a forked session is a new
session that starts with a copy of its history.
_Italian_: sessione
_Avoid_: chat, conversation, transcript (the transcript is a source, not the session)

**Invocation**:
How the prompts of a session arrive: interactive (a person types them), headless (a script or a command line gives
them), scheduled (a schedule starts the session), or orchestrated (another program or session drives it); a resumed
session can arrive in another way.
_Italian_: modalità di avvio

**Machine**:
The computer on which the work of a session happened.
_Italian_: macchina

## Signals and decisions

**Human signal**:
An event that shows that a person attended to the work: a prompt of a session that is interactive or of unknown
invocation, a queued message, a decision made by the person, or an interruption.
_Italian_: segnale umano

**Notification**:
A non-human input to an agent, such as the end of a background subagent, a message of another agent, a scheduled
trigger, or a prompt of a session that is not interactive.
_Italian_: notifica

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
One unit of agent execution: it starts at an input that reaches an agent with no turn in progress, continues through
the tool results, queued messages, and notifications that arrive while it is in progress, and ends at the last agent
output before the agent waits for a prompt or a notification.
_Italian_: turno
_Avoid_: request, round

**Stale limit**:
The longest time without any event after which a turn in progress ends at its last event.
_Italian_: limite di stallo

**Idle gap**:
The longest silence that still counts as continuous human time, both in a signal gap and in a response interval.
_Italian_: soglia di inattività
_Avoid_: pause threshold, timeout

**Signal gap**:
An interval of human time between two consecutive human signals of a person, from any of the sessions of the person,
that are not more than the idle gap apart.
_Italian_: intervallo fra segnali

**Response interval**:
An interval of human time from the last agent output or decision request of a session to the human signal of the same
session that follows it, when it is not longer than the idle gap.
_Italian_: intervallo di risposta

**Minimum attention time**:
The human time that an isolated human signal counts for.
_Italian_: attenzione minima

**Presence span**:
The interval from the first to the last human signal of a person in one day.
_Italian_: arco di presenza

**Activity class**:
One of five mutually exclusive states of an instant: person only, supervised, unattended, blocked, idle.
_Italian_: classe di attività

**Supervised time**:
Time in which human time and agent time overlap.
_Italian_: tempo supervisionato

**Unattended time**:
Agent time with no overlapping human time, for example a night run or a long run that nobody follows.
_Italian_: tempo non supervisionato
_Avoid_: autonomous hours, background time

**Manual entry**:
An interval of human time that a person declares because no source recorded it; it is either additional to or
overlapping with measured human time.
_Italian_: registrazione manuale
_Avoid_: estimated day, giorno stimato, fixed summary

**Timesheet entry**:
The human time of a person for one day and one project, declared without start and end: the ledger proposes it from
measured values, and the person confirms or changes it.
_Italian_: voce del registro attività
_Avoid_: estimated day, giorno stimato

**Declared usage**:
Agent time, token usage, or cost that a person declares for work that no source recorded, such as a cloud session.
_Italian_: utilizzo dichiarato

**Measured value**:
A value that the ledger derives from a source other than a manual entry, a timesheet entry, or declared usage.
_Italian_: valore misurato

**Declared value**:
A value that comes from a manual entry, a timesheet entry, or declared usage.
_Italian_: valore dichiarato

**Size counter**:
A number that describes the size of an edit without its text: lines added, lines removed, and the file extension.
_Italian_: contatore di dimensione

## Data

**Source**:
A place that records activity: a native log, a hook, a telemetry stream, a manual entry, or an imported file.
_Italian_: sorgente

**Native log**:
The files in which an agent tool records its own sessions, in a format that the agent tool defines.
_Italian_: log nativo

**Retention period**:
The time after which an agent tool deletes its native logs.
_Italian_: periodo di conservazione

**Hook**:
A command that an agent tool runs at a defined point of a session, such as the end of a session, and that receives
data about that point.
_Italian_: hook

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
The private, append-only collection of the events of one person: a folder of segments.
_Italian_: archivio
_Avoid_: database, data file, ledger (the name of the tool)

**Segment**:
A file of the store that one machine writes and no other machine changes.
_Italian_: segmento

**Annotation**:
An event that sets labels on a session or a time interval, such as its work item, and adds no time.
_Italian_: annotazione

**Retraction**:
An event that cancels an earlier event without removing it from the store.
_Italian_: ritiro

**Purge**:
The physical removal of events from the store, the only exception to append-only; a purge event keeps the removed keys,
the reason, and the time, so that ingestion and merge do not bring the events back.
_Italian_: eliminazione definitiva

## Attribution

**Project**:
A body of work to which effort is attributed, such as a product or a contract; identity rules resolve it, and by
default one repository is one project.
_Italian_: progetto

**Repository identity**:
The normalized remote URL of a repository, or the hash of its root commit when it has no remote, read from the
repository files; an observation on events, not a project.
_Italian_: identità del repository

**Identity rule**:
A rule of the configuration that resolves events to a project from their repository identity, folder, branch, and date.
_Italian_: regola di identità

**Unattributed**:
The bucket of events, and of usage known only from imported totals, whose project or work item cannot be resolved,
kept so that attributed parts add up to totals.
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
The rule that divides human time that the sessions of more than one project or work item can claim, so that the parts
add up to the total.
_Italian_: regola di ripartizione

**Period**:
A calendar interval that a report covers: a day, a week, a month, or a custom interval.
_Italian_: periodo

**Frozen period**:
A period whose report was given to someone and is no longer recomputed.
_Italian_: periodo congelato

## Cost

**Token usage**:
The tokens that a model reads and writes, counted per token category, such as input, output, and cache reads.
_Italian_: utilizzo di token

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

**Allocated cost**:
The part of the fee of a subscription that the ledger assigns to a project or a work item in proportion to its usage.
_Italian_: costo ripartito

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
