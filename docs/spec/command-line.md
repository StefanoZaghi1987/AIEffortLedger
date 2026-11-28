# Command line

The commands with which a person, a scheduler, or a hook uses the ledger. Terms follow
[GLOSSARY.md](../../GLOSSARY.md); the command line and its JSON output are a stable contract (ADR 0005).

## Form

```text
ai-effort-ledger <command> [<subcommand>] [options]
```

Options of every command:

| Option | Meaning |
|---|---|
| `--store <folder>` | use another store folder for this command only ([configuration.md](configuration.md) › Layers); `setup --store` also makes it the store of the machine |
| `--json` | write the result as one JSON document |
| `--language en\|it` | language of the output: the report parameter `language`, `en` by default |

The language of the output takes its value as every report parameter does ([configuration.md](configuration.md) ›
Order): `--language`, then `[report] language` of the person configuration, then `en`. The help and the faults of the
command line — those of the parse and those of a value, which are found after the parse — take the language of the
command line alone, because no store is read for them. When the ledger gives no person configuration to read, because
none exists or because its file cannot be read, the output keeps the language of the command line, and a command that
needs the person configuration stops with its own error in it; `setup` creates the person configuration when none exists
and completes, and stops with its own error when its file cannot be read. `version` reads no configuration and always
takes the language of the command line.

Report parameters are options of the commands that compute figures: `--idle-gap`, `--minimum-attention`,
`--stale-limit`, `--headless-prompts yes|no`, and `--timesheet-granularity`; `--first-day-of-week` joins them in
Phase 2; an option overrides the person configuration for one command ([configuration.md](configuration.md) › Order).

Values in options:

- a duration uses the format of [configuration.md](configuration.md) › Format (`"1h30min"`), or `H:MM`;
- a day is `YYYY-MM-DD`, `today`, or `yesterday`, a local day of the person;
- an instant is `YYYY-MM-DDTHH:MM`, a local time of the person, or an RFC 3339 instant with an offset or `Z`; the
  `--from` of a time-zone entry is always an RFC 3339 instant;
- a project is its project identifier, or, when no identifier matches, its name; `-` is the unattributed time, which
  has no work item;
- the value of a timesheet entry is `<project>=<duration>`, or `<project>#<work item identifier>=<duration>`;
- the first day of the week (Phase 2) is the name of a day in English or in Italian, without regard to case
  (`monday`, `lunedì`); in JSON it is the ISO 8601 number of the day, 1 (Monday) to 7 (Sunday);
- a period and every range of days in an option includes both end days.

The standard output and the standard error of every command are UTF-8, strict on the output and with `backslashreplace`
on the error, so a redirected run never dies of an output character.

## Output

- **Standard output** holds the result: tables for a person, or the JSON document with `--json`.
- **Standard error** holds warnings and errors, one on each line, and the questions that `setup` and `purge` ask in
  the language of the output, whose answers the command reads from standard input, where an end of the input is no
  answer: warnings start with `warning:`; configuration errors and stop errors start with `error:`. With `--json`,
  warnings and configuration errors are also in the `warnings` and `configuration_errors` lists of the document, and
  a command that stops writes one envelope with `command`, `warnings`, `configuration_errors`, and `error` (`code`,
  `values`, `message`) instead of the document of the command, with no partial line before it (see JSON documents).
- **Durations** are `H:MM` in tables and whole seconds in JSON; a table shows whole minutes and leaves the seconds out,
  so it never shows more than the value; hours longer than a day keep their full count, such as `25:30`. The parts
  of a total therefore add up to the total in the JSON document; in a table they can add up to less, by less than
  one minute for each part.

A command asks a question only in `setup` and `purge`, and only when standard input is a terminal. An option gives
every answer, so a scheduler, a hook, or a script never waits for a person.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | the command completed |
| 1 | the command stopped with an error and wrote no partial line; events that it appended before the error stay, complete. For example: a configuration file that the ledger cannot read, an instant without a local day, a lock not available within 10 minutes, or a development version that may not write to the store ([architecture.md](architecture.md) › Runtime) |
| 2 | wrong use: no command, an argument missing, an argument not known, arguments that do not go together, a value in a wrong format, or an event of a kind that the command cannot act on |
| 3 | the command completed, but some figures are not complete: a configuration error, a broken line in a segment, events of a newer schema version that the ledger leaves out ([event-schema.md](event-schema.md) › Encoding), held-back events of a day that its figures cover, or events lost because a native log was deleted before ingestion or between the selection and the read, which sets exit code 3 for the command whose ingestion finds it, also the first ingestion of `setup` |

A warning that does not make a figure incomplete, such as an unknown tool name, a declared value lower than the
measured value, or two timesheet confirmations of a day from two machines, keeps the exit code 0. `timesheet confirm`
also keeps it when it warns about held-back events of the day, because its entries are the declaration of the person.
`config show`, which computes no figures, completes with exit code 0 also when it shows configuration errors.

A stop error has a code, values, and one line of text in the output language; with `--json` the envelope carries
them in `error` (see Output). A value that holds a list, such as `arguments`, is a list in the JSON document and its
items joined by `, ` in the line. The stop errors of the ledger:

| Code | Values | Exit code |
|---|---|---|
| `lock_unavailable` | `path` | 1 |
| `scheduler_failed` | `program`, `exit_code` | 1 |
| `configuration_unreadable` | `path`, `line` | 1 |
| `setup_required` | — | 1 |
| `no_local_day` | `instant` | 1 |
| `dated_fact_conflict` | `first`, `second` | 1 |
| `time_zone_missing` | — | 1 |
| `development_version` | — | 1 |
| `index_busy` | — | 1 |
| `target_not_found` | `target` | 1 |
| `frozen_other_machine` | `id`, `machine`, `machine_label` (when the store holds one) | 1 |
| `frozen_report_unreadable` | `path` | 1 |
| `frozen_command_unknown` | `id`, `command` | 1 |
| `ambiguous_session` | `session_id`, `tools` | 1 |
| `ambiguous_name` | `option`, `name`, `identifiers` | 1 |
| `day_after_today` | `day` | 1 |
| `set_above_total` | — | 1 |
| `no_command` | — | 2 |
| `missing_argument` | `command`, `arguments` | 2 |
| `unknown_argument` | `command`, `arguments` | 2 |
| `conflicting_arguments` | `command`, `arguments` | 2 |
| `wrong_value` | `key`, `value` | 2 |
| `wrong_kind` | `command`, `event_uid`, `kind` | 2 |

`scheduler_failed` is the stop form in `schedule create` and `schedule remove`; in `setup` the same event is the
warning `scheduler_failed` (see JSON documents).

## Commands

| Command | Use |
|---|---|
| `setup` | prepare the ledger on a machine (see Setup) |
| `schedule show\|create\|remove` | show, create (with `--time <HH:MM>` in the local time of the operating system, default 12:00), or remove the scheduled ingestion ([ingestion.md](ingestion.md) › Frequency); `schedule create` replaces an entry of the ledger that already exists, and `schedule remove` without an entry completes with the warning `no_schedule_entry`; a store folder with a word that the scheduler of the operating system cannot carry makes `schedule create` stop with the code of a wrong value; when the scheduler of the operating system ends with an error, `schedule create` and `schedule remove` stop with exit code 1 and name the scheduler program and its exit code |
| `ingest` | run an ingestion; show the number of new events of each folder of native logs |
| `machine label <text>` | change the label of the machine in its store metadata; a blank `<text>` stops the command with the exit code for wrong use |
| `config show` | show the value of each parameter and dated fact with the layer that gives it, and every configuration error that the person configuration gives alone; a rule conflict needs an event that the two rules match, so the reports show it |
| `config add <entry> <options>` | append an entry to the person configuration (see Configuration entries) |
| `sessions <day>` | list the sessions of a local day: identifier, agent tool, start and end (its first and last event in the day), folder, branch (of its last event in the day), and, on one line for each project and work item of the session, the human time that the split rule gives to its human signals and its agent time |
| `annotate [--tool <agent tool>] --session <id> \| --from <instant> --to <instant>` with at least one of `--project` and `--work-item`, and an optional `--note` | write an annotation; `--session` takes the identifier that `sessions` shows, and `--tool` names the agent tool when two of them hold the same identifier; a work item without `--project` belongs to the project that attribution gives to the event ([metrics.md](metrics.md) › Attribution) |
| `entry add --from <instant> --to <instant> [--project <project>] --mode overlapping\|additional` with `--work-item`, `--note`; without `--project`, or with `--project -`, the entry declares the unattributed time | write a manual entry |
| `timesheet <day>` | show the timesheet proposal of a measured day, or the timesheet entries of a declared day, with the measured values next to them |
| `timesheet confirm <day>` with `--total <duration>`, `--set <value of a timesheet entry>` (repeatable), `--note <text>` | write a timesheet confirmation (see Timesheet) |
| `timesheet retract <day>` | retract the latest timesheet confirmation of the day |
| `entries <day>` | list the manual entries, annotations, and retractions whose `timestamp` is in that local day, and the timesheet confirmations whose `day` is that day, with their `event_uid` |
| `retract <event_uid>` | write a retraction of a manual entry, an annotation, a timesheet confirmation, or a retraction, by the `event_uid` that `entries` shows; a retraction of a retraction brings the event back; an `event_uid` of another kind, such as a purge, stops the command with the exit code for wrong use |
| `purge` (see Purge) | remove events from the store |
| `report timesheet --from <day> --to <day>` with `--freeze` and `--note` | the daily timesheet of a period (see Reports); with `--freeze`, also keep it as a frozen report (see Frozen reports) |
| `report day <day>` with `--freeze` and `--note` | human time, agent time and its parallel ratio, blocked time, and activity classes of a day, for the person, each project, and each work item; with `--freeze`, also keep it as a frozen report |
| `frozen list`, `frozen show <id>`, `frozen remove <id>` | list the frozen reports; show one with its differences against a report of now; remove one (see Frozen reports) |
| `index rebuild` | build the local index again from the segments |
| `version` | show the version of the ledger and of `tzdata` |
| `--help`, `<command> --help` | show the commands, or the options of one command |

`schedule show` and step 6 of `setup` ask the Task Scheduler on Windows for the entry, and on macOS and Linux read the
files that `setup` or `schedule create` wrote: the plist of the launchd agent, and the timer and the service of the
systemd user timer. A file that is absent, that cannot be read, or that holds no complete entry of the ledger is no
entry; where only cron exists, the ledger holds no entry.

A command that names a target that the store does not hold — `annotate --session`, `retract`, `timesheet retract`,
`frozen show`, and `frozen remove` — stops with exit code 1 and names the target; `annotate --session` without
`--tool` does the same when two agent tools hold the identifier.

An interval whose start does not come before its end stops `annotate` and `entry add` with a wrong value that names
`--to`.

The help is 96 columns wide, whatever the terminal. The usage of a command starts with the name of the program
and the words of the command; when it does not fit on one line, the next lines start under the first part, and a
line breaks between two parts, never inside one. A part is an option, with its value when it takes one, an
argument, or one of the options that the usage joins with `|`; the options come before the arguments. The usage
of `--help` is the form above.

## Setup

`setup` runs these steps in this order. It can run again at any time: it changes only what its options or answers
change.

1. Machine configuration: create the machine identifier when there is none, or a new one when the installation
   identifier changed ([ingestion.md](ingestion.md) › Store); add the folders of native logs that each agent tool
   uses on the machine ([claude-code-adapter.md](claude-code-adapter.md) › Native logs), also the one that
   `CLAUDE_CONFIG_DIR` gives at setup, and the folders of `--native-logs <agent tool>=<folder>`; a folder already
   recorded stays, also one that the person added.
2. Store folder: the default folder, or the folder of `--store`, which `setup` writes in the machine configuration as an
   absolute path, resolved when the word of the command line is not one.
3. Person configuration: when the store folder has none, create it ([configuration.md](configuration.md) › Writes) and
   show its entries and the file in which the person changes them.
4. Machine label: the value of `--label`, or the answer of the person; written in the store metadata. When standard
   input is not a terminal and `--label` is absent or blank, setup writes no label; the command `machine label` sets it
   later.
5. Retention: show the retention period of each agent tool and the advice of [ingestion.md](ingestion.md) › Frequency.
6. Scheduled ingestion: show the scheduler entry, a daily ingestion at the time of `--time` (default 12:00), and
   create it only with `--schedule yes` or the consent of the person ([ingestion.md](ingestion.md) › Frequency). A
   store folder with a word that the scheduler of the operating system cannot carry stops setup with the code of a
   wrong value, which names the folder and the machine configuration file to fix, before the entry is created. A
   version with a development mark shows the entry and never creates it, because the scheduler does not pass the
   variable that lets such a version write; `schedule create` stops with exit code 1 for such a version. When the
   scheduler ends with an error, setup warns (`scheduler_failed`) and goes on with step 7.
7. First ingestion: run `ingest`.

Every other command except `version` and `--help` stops with exit code 1, and asks for `setup`, when the machine has no
machine configuration or the store folder has no person configuration.

## Configuration entries

`config add` appends one entry with the keys of [configuration.md](configuration.md) › Format as options. The name of an
entry on the command line is the name of its table with each underscore as a hyphen: `time-zone` is `[[time_zone]]`.

| Entry | Options |
|---|---|
| `time-zone` | `--zone <IANA time zone> --from <instant>` |
| `day-start` | `--hour <HH:MM> --from <day>` |
| `project` | `--id <project identifier> --name <name>` |
| `work-item` | `--project <project identifier> --id <work item identifier> --name <name>` |
| `identity-rule` | `--project <project identifier>` and at least one of `--repository`, `--folder`, `--branch`, `--from`, `--to` |
| `category-rule` | `--tool <pattern> --category <tool category>` |
| `price` (Phase 2) | `--provider <provider> --model <model identifier> --currency <currency> --from <day>` and at least one price, as an option with the name of its key |
| `model-provider` (Phase 2) | `--model <model identifier> --provider <provider> --from <day>` |

## Timesheet

`timesheet confirm <day>` without options confirms the timesheet proposal of a measured day, or the timesheet entries of
a declared day, as `timesheet <day>` shows them. `--set` gives the value of one entry; the other entries keep their
values, and an entry of zero is left out of the confirmation. `--total` gives the total human time of the day, which
divides among the entries that `--set` does not give ([metrics.md](metrics.md) › Declared values). The command writes
one timesheet confirmation with all the entries of the day, shows them, and warns about each project whose declared
value is lower than its measured human time ([metrics.md](metrics.md) › Declared values). A new confirmation of the same
day replaces the earlier one as a whole, and names, in `replaces`, the latest confirmation of the day that the machine
has. `--set` can name a project or a work item that the proposal does not hold. `--note` gives its text to every entry.
When the values of `--set` are more than `--total`, or the day is after today, the command stops with exit code 1. The
command warns when the machine holds back events of the day that are not complete yet. The command warns when
the confirmation that it replaces has a later `timestamp` than the instant of the machine, because the clocks of two
machines differ and the latest confirmation is the one with the latest `timestamp`.

## Purge

```text
ai-effort-ledger purge (--key <key>... | --writer-version-below <version> [--source <source>])
                       --reason content|correction|forget [--corrected-version <version>] [--yes]
```

A `--key` is the event key as its JSON object, such as `{"source":"ledger","event_uid":"…"}`, or, for a key of the
source `ledger`, its `event_uid` alone. The command shows the keys that it removes and warns about the keys whose source
no longer exists ([event-schema.md](event-schema.md) › Keys and invariants). It writes the purge only with `--yes` or
the consent of the person. `--corrected-version` is not accepted with `--reason forget` (ADR 0015). A `--key` whose event is a purge stops the command with the exit code for wrong use: a purge cannot be undone, because
the copies that it removed do not come back. A selection by writer version holds no purge event. A selection by writer
version that holds no key writes nothing and asks nothing: the command completes with the warning `no_key_selected`.

After it writes the purge, the command removes the copies that the purge blocks from the segments of its own machine,
as step 10 of an ingestion does ([architecture.md](architecture.md) › Data flow); every other machine removes its own
copies at its next ingestion.

## Reports

`report timesheet` shows, for each local day of the period, the state of the day (measured or declared), the total human
time of the day, and, for each project and work item and for the unattributed time, three values: the measured human
time, the measured human time with manual entries, and the declared value of a declared day
([metrics.md](metrics.md) › Declared values). Every command that shows the human time of a day — `report timesheet`,
`report day`, `timesheet <day>` — also shows the share of human signals from sessions of unknown invocation and, for a
measured day, the human time at idle gaps of 5, 10, and 15 minutes and at the idle gap in use
([metrics.md](metrics.md) › Uncertainty); each project and work item shows the share of its human time and of its agent
time that rests on an inferred repository identity. The command writes its warnings and configuration errors
before it writes the table.

`report day` shows, for the person, for each project, and for each work item, the measured human time with
manual entries, on a measured day and on a declared day alike: on a measured day it is the human time of the
day, and on a declared day the evidence behind its timesheet entries
([metrics.md](metrics.md) › Declared values). The activity classes of the person, of each project, and of each
work item come from that human time, so the classes of the projects do not always add up to those of the person,
which the text of `report day` says ([metrics.md](metrics.md) › Activity classes). In the JSON document, the
classes person only and supervised of the person, of each project, and of each work item add up to its `human_time`,
and the five classes of the person add up to the length of its day. When the milliseconds do not divide into whole
seconds, the report divides the whole seconds of the human time between supervised and person only, and for the person
the whole seconds that remain of the day among unattended, blocked, and idle, with the largest-remainder method
([metrics.md](metrics.md) › Declared values), between equal remainders to the class that comes first in the table
of the activity classes; the unattended and the blocked of a project or work item are rounded each alone.

Beside the agent time of the person, of each project, and of each work item, `report day` shows its parallel ratio
([metrics.md](metrics.md) › Agent time), and `timesheet <day>` shows the parallel ratio of the day beside its
agent time; the text shows it with two decimals, and no value where the holder has no agent time.

A report of a period that a frozen report holds also shows, for each day, project, and work item, the difference
against the frozen figures, and the report parameters, rules, and dated facts that changed (see Frozen reports).
Only `report timesheet` and `report day` show the differences; `timesheet <day>` shows the proposal and the entries
of the day and no differences.

In Italian, the titles, the states, and the warnings use the Italian terms of [GLOSSARY.md](../../GLOSSARY.md);
project names, work items, and notes stay as the person wrote them.

## Frozen reports

A report command with `--freeze` writes its result and keeps its document as a frozen report: its JSON document, report
record included, also when the output is text, but without the differences against other frozen reports, which every
later report computes again. It writes the file `frozen/<machine>/<id>.json` of the store folder
([ingestion.md](ingestion.md) › Store), with a random UUID as `<id>`, and shows the identifier; the file is a JSON
object that holds that document unchanged as `document`, `--note` as `note`, and the instant of the freeze as
`frozen_at`. A later report of the same period computes with the current report parameters, rules, and dated facts, and
shows the differences against the frozen figures and the report parameters, rules, and dated facts that differ between
the two report records; where frozen reports overlap, it compares each day with the latest frozen report that holds that
day: the one with the latest `frozen_at`, then the identifier as text. When the latest frozen report is of another
command, the report compares only on the figures that both documents hold under the same name, and `changed` always;
between two reports of one command, a figure that only one of them holds is a difference too. `frozen remove <id>`
deletes the file of a frozen report. The identifier of a frozen report is one file name below the frozen folder of a
machine — text that holds no `/` and no `\` and is neither empty nor `.` nor `..` — so a word of another shape stops
`frozen remove` as a wrong value. Only the machine that wrote the file removes it, because each file of the store has
one writer; on another machine the command stops with exit code 1 and names the machine that wrote it. A file of a
frozen report that the ledger cannot read as one stops every command that reads the frozen reports with exit code 1 and
names the file; `frozen remove` reads no file, so it removes such a file too. `frozen show` stops with exit code 1 when
the frozen report is of a command that the version of the ledger does not know.

## JSON documents

With `--json`, every command writes one JSON object with `command` (the command and its subcommand, such as
`report timesheet`), `warnings`, and `configuration_errors`. Each warning and each configuration error is an object
with `code`, a stable name such as `lost_events`; `values`, an object with the values that it names, never translated;
and `message`, its text in the language of the output. Every warning and every configuration error has a code: a stable
name in lower case with underscores, the same in every version and every language; the codes are part of the contract,
the program holds an English and an Italian text for each, and the codes of Phase 1 are:

| Code | Condition |
|---|---|
| `lost_events` | the ingestion finds that native logs were deleted before it read them |
| `broken_line` | a line of a segment is not a valid event |
| `newer_schema_version` | events of a newer schema version exist; kinds and values that the ledger does not know are left out |
| `unknown_tool_name` | a tool name is in no table of its adapter and no category rule matches it |
| `unknown_entrypoint` | an entrypoint value maps to no invocation |
| `unknown_record_type` | a record type of a native log is not known, or a record of a known type has a structure that the adapter does not know; it gives no event |
| `invalid_record` | a line of a native log is not valid JSON; it gives no event |
| `invalid_records_summary` | a file of a native log holds more than 10 lines that are not valid JSON; one warning names the count of all of them |
| `unknown_origin_kind` | an `origin.kind` value is not known; its record gives no event from that key |
| `unknown_permission_source` | a `permissionDecision.source` value is not known; its record gives no decision |
| `multi_tool_result_permission` | a `permissionDecision` sits on a record with more than one `tool_result` |
| `record_copies_differ` | two copies of one record differ in a field other than identity |
| `fork_original_unknown` | both sessions of a fork, or neither, hold records of their own; the order of the identifiers decides |
| `shallow_clone` | a repository has no root commit that the ledger can reach |
| `held_back_events` | a report of a day shows a session of which this machine holds events back because they are not complete yet |
| `manual_entry_overlap` | an entry in mode `overlapping` overlaps measured human time of another project or work item, or an entry in mode `additional` overlaps measured human time |
| `identity_rule_conflict` | two identity rules match an event and neither is more specific (configuration error) |
| `category_rule_conflict` | two category rules match a tool name and neither is more specific (configuration error) |
| `project_name_conflict` | the person configuration gives one name to two project identifiers (configuration error) |
| `declared_value_below_measured` | the declared value of a project in a declared day is lower than its measured human time |
| `confirmation_not_seen` | an earlier confirmation of a day is not named by the latest one, directly or through the confirmations between them |
| `confirmation_before_replaced` | a confirmation has a `timestamp` earlier than the confirmation that it replaces |
| `work_item_without_project` | an annotation gives a work item to events that have no project |
| `declared_project_unknown` | no identity rule, no entry of the person configuration, and no repository identity gives the project identifier of a declared event |
| `purged_key_source_gone` | a key of a purge names a source that no longer exists: for a source of native logs, one of which no folder remains in the machine configuration; the source `ledger` always exists |
| `no_schedule_entry` | `schedule remove` finds no entry of the ledger |
| `no_key_selected` | a selection of `purge` by writer version holds no key |
| `scheduler_failed` | in `setup`, the scheduler of the operating system ends with an error and creates no scheduled ingestion: its program and exit code; `setup` goes on |
| `machine_label_unreadable` | the store metadata of a machine that the command names cannot be read, or its `label` is not text: its path in the store folder; the output shows the machine identifier |
| `native_log_gone` | a file of a session that the agent tool deleted between the selection and the read; it gives no event |
| `ambiguous_folder` | the machine configuration records one folder of native logs for a second agent tool of one adapter, or a second time for the same tool; the ledger reads it once, for the first of the recordings |
| `ambiguous_session_folder` | two folders of native logs that the machine configuration records for one agent tool hold the same session identifier; the ledger reads the session once, in the first of the folders |

A code marked "(configuration error)" appears in `configuration_errors`; the others appear in `warnings`. The commands
that compute figures — `report timesheet`, `report day`, `timesheet <day>`, `sessions <day>` — add `record`, the report
record ([architecture.md](architecture.md) › Report record); `frozen show` shows the record kept at freeze time.
Durations are whole seconds, instants are RFC 3339 text in UTC as
in [event-schema.md](event-schema.md) › Encoding, days are `YYYY-MM-DD`, a share is a number from 0 to 1, the parallel
ratio is a number from 1 up, and a project or a work item is an object with `id` and `name`, or `null` for the
unattributed time and for no work item.

| Command | Other keys |
|---|---|
| `setup` | `machine`, `machine_label` (when the store holds one), `store`, `configuration_created` (true or false), `schedule` (as in `schedule show`), and `ingest` (as in `ingest`) |
| `schedule show\|create\|remove` | `schedule`: `name`, `command`, and `time`, or `null` when there is no entry |
| `ingest` | `sources`: for each folder of native logs, `source`, `folder`, `new_events`, and `sessions_held_back` |
| `machine label` | `machine` and `label` |
| `config show` | `parameters`, each with `name`, `value`, and `layer`; `entries`, each with `entry` (such as `time_zone`), its keys, and `layer` |
| `config add` | `entry` and its keys as appended |
| `sessions` | `day` and `sessions`, each with `session_id`, `tool`, `start`, `end`, `cwd` and `branch` (those of its last event in the day, when that event holds them), and `parts`, each with `project`, `work_item`, `human_time`, and `agent_time` |
| `annotate`, `entry add`, `timesheet confirm`, `timesheet retract`, `retract` | `event_uid` of the event that the command wrote; `timesheet confirm` also `entries` as in `timesheet` |
| `timesheet` | `day`, `state`, `total`, `measured_total` (as in `report timesheet`), `human_time_at_idle_gaps` (measured days only), `unknown_invocation_share`, `entries` as in `report timesheet`, each also with `proposed`, the proposed value in whole seconds, and `context` with `agent_time`, `parallel_ratio` (when the day has agent time), and `presence_span` |
| `entries` | `day` and `entries`, each with `event_uid`, `kind`, `timestamp`, and the other fields of the event ([event-schema.md](event-schema.md) › Fields) |
| `purge` | `keys`, `keys_without_source`, and `written` (true when the command wrote the purge) |
| `report timesheet` | `days`, each with `day`, `state`, `total`, `measured_total` (the measured human time of the day in whole seconds; equals `total` on a day without manual entries), `human_time_at_idle_gaps` (an object from the idle gap in seconds, as text, to the human time; measured days only), `unknown_invocation_share`, and `entries`, each with `project`, `work_item`, `measured`, `with_manual_entries`, `declared` (`null` on a measured day), `inferred_human_share`, and `inferred_agent_share` |
| `report day` | `day`, `state`, `human_time_at_idle_gaps` (measured days only), `unknown_invocation_share`, `person`, `projects`, and `work_items`; `person`, each project of `projects`, and each work item of `work_items` with `human_time`, `agent_time`, `parallel_ratio` (when it has agent time), `blocked_time`, and `activity_classes` (an object from the activity class to its duration); each project also with `project`, each work item also with `work_item`, and each project and work item also with `inferred_human_share` and `inferred_agent_share` |
| `report timesheet --freeze`, `report day --freeze` | also `frozen_id`, the identifier of the frozen report |
| `frozen list` | `frozen`, each with `id`, `report`, `from` and `to` (the first and the last day of the frozen report, when its document holds days), `note` (when the frozen report has one), `machine`, `machine_label` (when the store holds one), and `frozen_at` |
| `frozen show` | `frozen`, the frozen report; `differences`, for each day, project, and work item whose figures differ: the frozen value and the value of now; and `changed`, the report parameters, rules, and dated facts that differ between the two report records, each with its frozen value and its value of now |
| `frozen remove` | `id` of the removed frozen report |
| `index rebuild` | `segments` and `events`, the numbers that the local index holds |
| `version` | `ledger` and `tzdata` |

A report of a period that a frozen report holds also has `differences` and `changed`, as in `frozen show`.

Where the text of a command names a machine, it shows the machine label that the store holds for that machine, and the
machine identifier when the store holds none: the column Machine of `frozen list` and of `entries`, and the message of
`frozen_other_machine`. `setup` and `machine label` show the machine identifier, and the label beside it when the store
holds one. A document keeps the identifier under `machine`. A label that is blank counts as no label. Store metadata
that the ledger cannot read counts as no label too, and the command warns `machine_label_unreadable` once for each such
file; the stop error `frozen_other_machine` names the identifier and carries no warning.

## To be confirmed

- The name of the warning for a session identifier that two folders of one agent tool hold:
  the warning is `ambiguous_session_folder` because the stop error `ambiguous_session` is
  taken (it names two agent tools and tells the person to name one with `--tool`, so one code
  cannot hold both texts), and the alternative — one code with a second text of
  `TEXT_VARIANTS` — is a mechanism that today only a stop error carries. To rule: this name,
  or another; the texts and the row follow the code.
