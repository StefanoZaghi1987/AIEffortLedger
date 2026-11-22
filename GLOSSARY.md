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

**Cowork**:
The part of the Claude Desktop application for long autonomous work; its sessions run in a virtual machine, and their
working folders are paths inside that machine.
_Italian_: Cowork

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

**Category rule**:
A rule of the person configuration that gives a tool category to the tool names it matches, at report time, in place
of the category that the adapter stored.
_Italian_: regola di categoria

**Session**:
One identified exchange between a person and an agent tool; a resumed session continues it, a forked session is a new
session that starts with a copy of its history.
_Italian_: sessione
_Avoid_: chat, conversation, transcript (the transcript is a source, not the session)

**Fork instant**:
The timestamp of the last record that a forked session shares with its original.
_Italian_: istante del fork

**Session title**:
The title that an agent tool gives to a session; it enters the store only when the person configuration allows titles
(Phase 2).
_Italian_: titolo della sessione

**Invocation**:
How the prompts of a session arrive: interactive (a person types them), headless (a script or a command line gives
them), scheduled (a schedule starts the session), or orchestrated (another program or session drives it); a resumed
session can arrive in another way.
_Italian_: modalità di avvio

**Machine**:
The computer on which the work of a session happened; the ledger identifies it with a random identifier kept on the
computer and shows its machine label.
_Italian_: macchina

**Machine label**:
The name that the person gives to a machine and that reports show; the machine writes it in its store metadata, and the
person can change it at any time.
_Italian_: etichetta della macchina

**Installation identifier**:
The identifier that the operating system gives to its installation; the ledger keeps only a salted hash of it, to see
when a user profile or a virtual machine was copied to another computer.
_Italian_: identificativo dell'installazione

## Signals and decisions

**Human signal**:
An event that shows that a person attended to the work: a prompt of a session that is interactive or of unknown
invocation, a queued message, a decision made by the person, or an interruption; a headless prompt only when the
report counts headless prompts.
_Italian_: segnale umano

**Notification**:
A non-human input to an agent, such as the end of a background subagent, a message of another agent, a scheduled
trigger, or a prompt of a session of headless, scheduled, or orchestrated invocation.
_Italian_: notifica

**Input origin**:
Where a notification comes from: a task notification, a coordinator, a peer, the agent that started a subagent, a
schedule, or a script.
_Italian_: origine dell'input

**Headless prompt**:
A prompt of a session of headless invocation, which the ledger stores as a notification; a report parameter decides
whether reports count it as a human signal, because no source shows whether a person or a script typed it.
_Italian_: prompt headless

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
signals. The event schema holds it as the `actor` of a `decision` event.
_Italian_: origine della decisione

## Time

**Human time**:
Time in which a person attends to the work, with or without an agent.
_Italian_: tempo persona
_Avoid_: effective hours, ore effettive, active hours, man-hours

**Agent time**:
Time in which an agent executes turns, without its blocked time and without waiting for its own subagents;
the agent time of agents that run in parallel adds up.
_Italian_: tempo agente
_Avoid_: AI hours, machine time

**Blocked time**:
Time in which an agent waits for the answer to a decision request, whether or not the person is present.
_Italian_: tempo bloccato
_Avoid_: waiting time, idle agent time

**Calendar time**:
Elapsed time from the first to the last event of work of a work item; annotations, retractions, and purges are not
work.
_Italian_: tempo di calendario
_Avoid_: lead time

**Turn**:
One unit of agent execution: it starts at an input that reaches an agent with no turn in progress, continues through
the tool results, queued messages, and notifications that arrive while it is in progress, and ends at the last agent
output before the agent waits, with no tool call pending, for a prompt or a notification, at an interruption, at the
end of the session, or at its last event when no event follows within the stale limit.
_Italian_: turno
_Avoid_: request, round

**Agent output**:
One response of a model to an agent, with its token usage, request counts, and price factors.
_Italian_: output dell'agente

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
An interval of human time from the last agent output or decision request of the main agent or of a foreground subagent
of a session to the human signal of the same session that follows it, when it is not longer than the idle gap.
_Italian_: intervallo di risposta

**Minimum attention time**:
The human time that a human signal counts for when it ends no signal gap and no response interval.
_Italian_: attenzione minima

**Local day**:
The instants whose local time, in the time zone of the person at each instant, is at or after the day start hour of a
date and before the day start hour of the next date; the day of a timesheet and of a daily report.
_Italian_: giorno locale

**Day start hour**:
The local hour at which a local day starts: a dated fact of the person, each hour valid from a local date, 00:00 at
setup; not a report parameter.
_Italian_: ora di inizio giornata

**First day of the week**:
The day on which each week of a report starts, Monday by default; a report parameter of Phase 2.
_Italian_: primo giorno della settimana

**Dated fact**:
A value of the person configuration that is valid from an instant or a local date until the start of the next value of
the same list, such as a time zone or a day start hour; a change adds a value and keeps the earlier ones.
_Italian_: dato datato

**Time-zone history**:
The dated list of the time zones of a person, each valid from an instant, in the person configuration.
_Italian_: storico dei fusi orari

**Presence span**:
The interval from the first to the last human signal of a person in one local day.
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
The human time of a person for one day and one project, with an optional work item, or for the unattributed time of
that day, which has no work item, declared without start and end: the ledger proposes it from measured values, and the
person confirms or changes it.
_Italian_: voce del registro attività
_Avoid_: estimated day, giorno stimato

**Timesheet proposal**:
The timesheet entries that the ledger computes for one day from measured values, before the person confirms them; it
never enters the store.
_Italian_: proposta del registro attività

**Timesheet confirmation**:
The event that holds the timesheet entries of one day that a person confirms together; the latest confirmation of a day
that is not retracted gives all the timesheet entries of that day.
_Italian_: conferma del registro attività

**Measured day**:
A day with no timesheet confirmation that is not retracted: its human time is the union of measured human time and
manual entries.
_Italian_: giorno misurato

**Declared day**:
A day with a timesheet confirmation that is not retracted: the sum of the timesheet entries of its latest confirmation
is all the human time of the person in that day, and its measured values are evidence.
_Italian_: giorno dichiarato
_Avoid_: closed day, giorno chiuso

**Timesheet granularity**:
The unit to which the ledger rounds the timesheet entries that it proposes, for example 15 minutes.
_Italian_: granularità del registro attività

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
The values that describe the size of an edit without its text: lines added, lines removed, and the file extension;
their size basis tells whether they come from a patch or from the tool input.
_Italian_: contatore di dimensione

**Size basis**:
The origin of the size counters of a tool call: `patch` when they come from the patch of the change, `input` when they
come from the tool input.
_Italian_: base della dimensione

## Data

**Source**:
A place or a writer that records activity: a native log, a hook, a telemetry stream, an imported file, or the ledger
itself for the events that its commands write.
_Italian_: sorgente

**Native log**:
The files in which an agent tool records its own sessions, in a format that the agent tool defines.
_Italian_: log nativo

**Retention period**:
The time after which an agent tool deletes its native logs.
_Italian_: periodo di conservazione

**Settle time**:
The time without a change to the files of a session after which ingestion takes every event of the session as
complete; 4 hours by default.
_Italian_: tempo di assestamento

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
_Avoid_: record (for an event), log line, block

**Native identifier**:
The identifier that a source gives to one of its records, unique across the sessions of that source; a forked session
starts with copies of the records of its original, a copy keeps the native identifier of its record, and the copies
are one event.
_Italian_: identificativo nativo

**Event identifier**:
The identifier of an event within its session: the native identifier when the source gives one, otherwise the
identifier that the adapter makes from the kind, the timestamp, and the position of the record.
_Italian_: identificatore dell'evento

**Complete event**:
An event that no later record of its source can change; only complete events enter the store.
_Italian_: evento completo

**Held-back events**:
The events of a session that a machine has not stored because they are not complete.
_Italian_: eventi trattenuti

**Event key**:
The identity of an event: its source and its native identifier, or, when the source gives none, its source, its
session, and an identifier that the adapter makes; two copies with the same key are one event.
_Italian_: chiave dell'evento

**Store**:
The private, append-only collection of the events of one person: a folder of segments.
_Italian_: archivio
_Avoid_: database, data file, ledger (the name of the tool)

**Store folder**:
The folder that holds the store: its segments, the store metadata, the person configuration, and the frozen reports.
_Italian_: cartella dell'archivio

**Default store folder**:
The folder of the store in the local user data folder of the operating system, used when the machine configuration
gives no other folder.
_Italian_: cartella predefinita dell'archivio

**Segment**:
A file of the store that one machine writes and no other machine changes.
_Italian_: segmento

**Broken line**:
A line of a segment that is not a valid event; every report leaves it out and names it.
_Italian_: riga non valida

**Local index**:
A file of one machine that holds the events of all segments of a store in a form that reports read fast; it is never
shared, and the ledger can build it again from the segments at any time.
_Italian_: indice locale

**Chained hash**:
The SHA-256 value that covers one line of a segment and the chained hash of all the lines of the segment before it,
which tells the local index where its copy of a segment ends.
_Italian_: hash a catena

**Store metadata**:
The file of the store folder in which one machine describes itself, such as its machine label; only that machine
writes it.
_Italian_: metadati dell'archivio

**File-sync service**:
A program that copies a folder between the machines of a person, so that two machines see the same files after a
delay.
_Italian_: servizio di sincronizzazione

**Conflict copy**:
The extra copy of a file that a file-sync service keeps when two machines changed the file before it copied it; the
person merges it by hand.
_Italian_: copia di conflitto

**Pseudonym**:
The name that stands for a person in a team export, kept in the person configuration.
_Italian_: pseudonimo

**Person configuration**:
The settings and rules that a person owns, such as the time-zone history, identity rules, and hourly rates: one file
in the store folder, so that every machine of the person reads the same values.
_Italian_: configurazione personale
_Avoid_: settings file, preferences, profile

**Machine configuration**:
The settings that belong to one machine: its machine identifier, the check of its installation, the location of the
store, and the folders of native logs, in the machine-local data folder of the operating system.
_Italian_: configurazione della macchina

**Machine-local data folder**:
The folder of one machine, outside every store, that holds its machine configuration, its locks, and what it
remembers of its ingestions.
_Italian_: cartella dati della macchina

**Project configuration**:
The rules that a project shares in its repository, such as identity rules on that repository; they apply only to
events of the repository identity of that repository.
_Italian_: configurazione di progetto

**Scheduled ingestion**:
An ingestion that a scheduler of the operating system starts every day, from an entry that setup or the command
`schedule create` creates with the consent of the person.
_Italian_: acquisizione pianificata

**Setup**:
The steps with which the ledger starts on a machine: the machine configuration, the person configuration when the store
folder has none, and the scheduled ingestion with the consent of the person.
_Italian_: configurazione iniziale

**Declared event**:
An event that a person writes through a command and that declares an attribution or a value: a manual entry, a
timesheet confirmation, declared usage, or an annotation; it stores project identifiers and work item identifiers,
never names.
_Italian_: evento dichiarato

**Label key**:
A key that the `labels` of an event can hold, from the allow-list of the person configuration (Phase 2).
_Italian_: chiave di etichetta

**Annotation**:
An event that sets the project, the work item, or labels of a session or a time interval, and adds no time.
_Italian_: annotazione

**Retraction**:
An event that cancels an earlier event without removing it from the store.
_Italian_: ritiro

**Purge**:
The physical removal of events from the store, the only exception to append-only; a purge event keeps the removed keys,
the reason, the time, and an optional corrected version, so that ingestion and merge bring back only copies that the
corrected version or a newer one wrote, and none when no corrected version is given.
_Italian_: eliminazione definitiva

**Writer version**:
The version of the ledger program that wrote an event; a version between two releases has a development mark,
`.dev` and a number, and comes before the release of the same number.
_Italian_: versione di scrittura

**Corrected version**:
The writer version from which a purge accepts new copies of the keys it removed.
_Italian_: versione corretta

## Attribution

**Project**:
A body of work to which effort is attributed, such as a product or a contract; identity rules resolve it, and by
default one repository is one project.
_Italian_: progetto

**Project identifier**:
The value that names a project for good: identity rules give it, declared events store it, and by default it is the
repository identity; the name that reports show is separate and can change.
_Italian_: identificativo di progetto

**Repository identity**:
The normalized remote URL of a repository, or the hash of its root commit when it has no remote, read from the
repository files; an observation on events, not a project. It is inferred, not observed, when the folder of the event
no longer exists and the ledger reads the nearest existing parent folder.
_Italian_: identità del repository

**Worktree**:
A second working folder of one repository, with its own files and one shared history; an agent tool can create and
remove it, so the folder of a session can disappear while its repository stays.
_Italian_: worktree

**Identity rule**:
A rule of the person configuration or of a project configuration that resolves events to a project from their
repository identity, folder, branch, and date.
_Italian_: regola di identità

**Configuration error**:
A rule or an entry of a configuration that the ledger cannot apply without a guess, such as two matching rules of
which neither is more specific; the ledger applies none of them, the figures stay computable, and the report shows the
error.
_Italian_: errore di configurazione

**Unattributed**:
The bucket of events, and of usage known only from imported totals, whose project cannot be resolved, kept so that
attributed parts add up to totals; an event with a project and no work item stays in the part of its project that has
no work item.
_Italian_: non attribuito

**Work item**:
One unit of planned work, such as a task, an issue, or an evolution, that collects effort and can carry an estimate.
_Italian_: unità di lavoro
_Avoid_: activity, job, task (as the generic term)

**Work item identifier**:
The value that names a work item of a project for good: declared events store it, and the name that reports show
is separate, can change, and is the identifier when the person configuration gives none.
_Italian_: identificativo dell'unità di lavoro

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

**Report parameter**:
A value that a report uses to compute or show its figures, such as the idle gap, the timesheet granularity, or the
language; the person configuration gives its default, an option of a command can change it for one report, and every
report records the values it used.
_Italian_: parametro del report

**Frozen period**:
A period whose report was given to someone and is kept as given; later reports show their differences against it.
_Italian_: periodo congelato

**Frozen report**:
The document of a report that the person gave to someone, with its report record and its figures, kept as given in
the store folder until the machine that wrote it removes it.
_Italian_: report congelato

## Cost

**Token usage**:
The tokens that a model reads and writes, counted per token category, such as input, output, and cache reads.
_Italian_: utilizzo di token

**Request count**:
The number of requests of one type that a provider charges one by one, such as web searches, in one agent output.
_Italian_: conteggio delle richieste

**Price factor**:
A fact of an agent output, other than token usage, on which its price depends, such as the speed mode, the service
tier, or the region where the model ran.
_Italian_: fattore di prezzo

**Price table**:
A dated list of prices per provider and model, for each token category, request type, and value of a price factor.
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

**Report**:
The figures that the ledger computes from the store for a period, with the report parameters and the dated facts that
it used; a timesheet is shown by a report.
_Italian_: report

**Report record**:
The part of a report that tells how it was computed: the version of the ledger, the report parameters, the rules
(identity rules, category rules), the dated facts, the configuration errors, and the state of the store that it read; a
frozen report keeps it with the figures.
_Italian_: traccia del report

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

## Development

**Benchmark**:
A run of `tests/benchmark.py` that writes invented native logs and times the first ingestion and a daily timesheet of
one month; a person runs it by hand before each release.
_Italian_: benchmark

**Scenario**:
A short sequence of invented events with its figures computed by hand, which a test of the core compares with the
figures that the core computes; every rule of the metrics has at least one.
_Italian_: scenario

**Fixture**:
A small native log, store, or expected output written by hand with invented text, which a test reads; the tests of an
adapter hold one fixture for each row of its table of records.
_Italian_: fixture
