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

Report parameters are options of the commands that compute figures: `--idle-gap`, `--minimum-attention`,
`--stale-limit`, `--headless-prompts yes|no`, `--first-day-of-week`, and `--timesheet-granularity`; an option overrides
the person configuration for one command ([configuration.md](configuration.md) › Order).

Values in options:

- a duration uses the format of [configuration.md](configuration.md) › Format (`"1h30min"`), or `H:MM`;
- a day is `YYYY-MM-DD`, `today`, or `yesterday`, a local day of the person;
- an instant is `YYYY-MM-DDTHH:MM`, a local time of the person, or an RFC 3339 instant with an offset or `Z`; the
  `--from` of a time-zone entry is always an RFC 3339 instant;
- a project is its project identifier, or, when no identifier matches, its name; `-` is the unattributed time, which
  has no work item;
- the value of a timesheet entry is `<project>=<duration>`, or `<project>#<work item identifier>=<duration>`;
- the first day of the week is the name of a day in English or in Italian, without regard to case (`monday`,
  `lunedì`); in JSON it is the ISO 8601 number of the day, 1 (Monday) to 7 (Sunday);
- a period and every range of days in an option includes both end days.

## Output

- **Standard output** holds the result: tables for a person, or the JSON document with `--json`.
- **Standard error** holds warnings and errors, one on each line, each starting with `warning:` or `error:`. With
  `--json`, warnings and configuration errors are also in the `warnings` and `configuration_errors` lists of the
  document (see JSON documents).
- **Durations** are `H:MM` in tables and whole seconds in JSON; hours longer than a day keep their full count, such as
  `25:30`.

A command asks a question only in `setup` and `purge`, and only when standard input is a terminal. An option gives
every answer, so a scheduler, a hook, or a script never waits for a person.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | the command completed |
| 1 | the command stopped with an error and wrote no partial line; events that it appended before the error stay, complete. For example: a configuration file that the ledger cannot read, an instant without a local day, a lock not available within 10 minutes, or a development version that may not write to the store ([architecture.md](architecture.md) › Runtime) |
| 2 | wrong use: an unknown command or option, or a value in a wrong format |
| 3 | the command completed, but some figures are not complete: a configuration error, a broken line in a segment, events of a newer schema version that the ledger leaves out ([event-schema.md](event-schema.md) › Encoding), or, for the ingestion that finds them, events lost because a native log was deleted before ingestion |

A warning that does not make a figure incomplete, such as an unknown tool name, a declared value lower than the
measured value, or two timesheet confirmations of a day from two machines, keeps the exit code 0.

## Commands

| Command | Use |
|---|---|
| `setup` | prepare the ledger on a machine (see Setup) |
| `schedule show\|create\|remove` | show, create (with `--time <HH:MM>`, default 12:00), or remove the scheduled ingestion ([ingestion.md](ingestion.md) › Frequency); `schedule create` replaces an entry of the ledger that already exists, and `schedule remove` without an entry completes with the warning `no_schedule_entry` |
| `ingest` | run an ingestion; show the number of new events of each source |
| `machine label <text>` | change the label of the machine in its store metadata |
| `config show` | show the value of each parameter and dated fact with the layer that gives it, and every configuration error |
| `config add <entry> <options>` | append an entry to the person configuration (see Configuration entries) |
| `sessions <day>` | list the sessions of a local day: identifier, agent tool, start and end (its first and last event in the day), folder, branch, and, on one line for each project and work item of the session, the human time that the split rule gives to its human signals and its agent time |
| `annotate [--tool <agent tool>] --session <id> \| --from <instant> --to <instant>` with at least one of `--project` and `--work-item`, and an optional `--note` | write an annotation; `--session` takes the identifier that `sessions` shows, and `--tool` names the agent tool when two of them hold the same identifier; a work item without `--project` belongs to the project that attribution gives to the event ([metrics.md](metrics.md) › Attribution) |
| `entry add --from <instant> --to <instant> [--project <project>] --mode overlapping\|additional` with `--work-item`, `--note`; without `--project`, or with `--project -`, the entry declares the unattributed time | write a manual entry |
| `timesheet <day>` | show the timesheet proposal of a measured day, or the timesheet entries of a declared day, with the measured values next to them |
| `timesheet confirm <day>` with `--total <duration>`, `--set <value of a timesheet entry>` (repeatable), `--note <text>` | write a timesheet confirmation (see Timesheet) |
| `timesheet retract <day>` | retract the latest timesheet confirmation of the day |
| `entries <day>` | list the manual entries, annotations, and retractions whose `timestamp` is in that local day, and the timesheet confirmations whose `day` is that day, with their `event_uid` |
| `retract <event_uid>` | write a retraction of a manual entry, an annotation, a timesheet confirmation, or a retraction, by the `event_uid` that `entries` shows; a retraction of a retraction brings the event back |
| `purge` (see Purge) | remove events from the store |
| `report timesheet --from <day> --to <day>` with `--freeze` and `--note` | the daily timesheet of a period (see Reports); with `--freeze`, also keep it as a frozen report (see Frozen reports) |
| `report day <day>` with `--freeze` and `--note` | human time, agent time, blocked time, and activity classes of a day, for the person, each project, and each work item; with `--freeze`, also keep it as a frozen report |
| `frozen list`, `frozen show <id>`, `frozen remove <id>` | list the frozen reports; show one with its differences against a report of now; remove one (see Frozen reports) |
| `index rebuild` | build the local index again from the segments |
| `version` | show the version of the ledger and of `tzdata` |
| `--help`, `<command> --help` | show the commands, or the options of one command |

A command that names a target that the store does not hold — `annotate --session`, `retract`, and `frozen remove` —
stops with exit code 1 and names the target; `annotate --session` without `--tool` does the same when two agent tools
hold the identifier.

## Setup

`setup` runs these steps in this order. It can run again at any time: it changes only what its options or answers
change.

1. Machine configuration: create the machine identifier when there is none, or a new one when the installation
   identifier changed ([ingestion.md](ingestion.md) › Store); add the folders of native logs that each agent tool
   uses on the machine ([claude-code-adapter.md](claude-code-adapter.md) › Native logs), also the one that
   `CLAUDE_CONFIG_DIR` gives at setup, and the folders of `--native-logs <agent tool>=<folder>`; a folder already
   recorded stays, also one that the person added.
2. Store folder: the default folder, or the folder of `--store`, which `setup` writes in the machine configuration.
3. Person configuration: when the store folder has none, create it ([configuration.md](configuration.md) › Writes) and
   show its entries.
4. Machine label: the value of `--label`, or the answer of the person; written in the store metadata. When standard
   input is not a terminal and `--label` is absent, setup writes no label; the command `machine label` sets it later.
5. Retention: show the retention period of each agent tool and the advice of [ingestion.md](ingestion.md) › Frequency.
6. Scheduled ingestion: show the scheduler entry, a daily ingestion at the time of `--time` (default 12:00), and
   create it only with `--schedule yes` or the consent of the person ([ingestion.md](ingestion.md) › Frequency).
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

## Timesheet

`timesheet confirm <day>` without options confirms the timesheet proposal of a measured day, or the timesheet entries of
a declared day, as `timesheet <day>` shows them. `--set` gives the value of one entry; the other entries keep their
values, and an entry of zero is left out of the confirmation. `--total` gives the total human time of the day, which
divides among the entries that `--set` does not give ([metrics.md](metrics.md) › Declared values). The command writes
one timesheet confirmation with all the entries of the day, shows them, and warns about each project whose declared
value is lower than its measured human time ([metrics.md](metrics.md) › Declared values). A new confirmation of the same
day replaces the earlier one as a whole, and names, in `replaces`, the latest confirmation of the day that the machine
has. `--set` can name a project or a work item that the proposal does not hold. `--note` gives its text to every entry.
When the values of `--set` are more than `--total`, or the day is after today, the command stops with exit code 1. For
today, the command warns when the machine holds back events of the day that are not complete yet. The command warns when
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
the consent of the person. `--corrected-version` is not accepted with `--reason forget` (ADR 0015).

## Reports

`report timesheet` shows, for each local day of the period, the state of the day (measured or declared), the total human
time of the day, and, for each project and work item and for the unattributed time, three values: the measured human
time, the measured human time with manual entries, and the declared value of a declared day
([metrics.md](metrics.md) › Declared values). Every command that shows the human time of a day — `report timesheet`,
`report day`, `timesheet <day>` — also shows, for a measured day, the human time at idle gaps of 5, 10, and 15 minutes
and at the idle gap in use ([metrics.md](metrics.md) › Uncertainty), and the share of human signals from sessions of
unknown invocation; each project and work item shows the share of its human time and of its agent time that rests on an
inferred repository identity. Warnings and configuration errors come before the table.

A report of a period that a frozen report holds also shows, for each day, project, and work item, the difference
against the frozen figures, and the report parameters, rules, and dated facts that changed (see Frozen reports).

In Italian, the titles, the states, and the warnings use the Italian terms of [GLOSSARY.md](../../GLOSSARY.md);
project names, work items, and notes stay as the person wrote them.

## Frozen reports

A report command with `--freeze` writes its result and keeps exactly that document as a frozen report: its JSON
document, report record included, also when the output is text. It writes the file `frozen/<machine>/<id>.json` of the
store folder ([ingestion.md](ingestion.md) › Store), with `--note` as its note and a random UUID as `<id>`, and shows
the identifier. A later report of the same period computes with the current report parameters, rules, and dated facts,
and shows the differences against the frozen figures and the report parameters, rules, and dated facts that differ
between the two report records; where frozen reports overlap, it compares each day with the latest frozen report that
holds that day. `frozen remove <id>` deletes the file of a frozen report. Only the machine
that wrote the file removes it, because each file of the store has one writer; on another machine the command stops
with exit code 1 and names the machine that wrote it.

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
| `unknown_origin_kind` | an `origin.kind` value is not known; its record gives no event |
| `unknown_permission_source` | a `permissionDecision.source` value is not known; its record gives no decision |
| `multi_tool_result_permission` | a `permissionDecision` sits on a record with more than one `tool_result` |
| `record_copies_differ` | two copies of one record differ in a field other than identity |
| `fork_original_unknown` | both sessions of a fork, or neither, hold records of their own; the order of the identifiers decides |
| `shallow_clone` | a repository has no root commit that the ledger can reach |
| `held_back_events` | a report of a day shows a session of which this machine holds events back because they are not complete yet |
| `manual_entry_overlap` | a manual entry overlaps measured human time or another manual entry |
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

A code marked "(configuration error)" appears in `configuration_errors`; the others appear in `warnings`. The commands
that compute figures — `report timesheet`, `report day`, `timesheet <day>`, `sessions <day>` — add `record`, the report
record ([architecture.md](architecture.md) › Report record); `frozen show` shows the record kept at freeze time.
Durations are whole seconds, instants are RFC 3339 text in UTC as
in [event-schema.md](event-schema.md) › Encoding, days are `YYYY-MM-DD`, a share is a number from 0 to 1, and a project
or a work item is an object with `id` and `name`, or `null` for the unattributed time and for no work item.

| Command | Other keys |
|---|---|
| `setup` | `machine`, `store`, `configuration_created` (true or false), `schedule` (as in `schedule show`), and `ingest` (as in `ingest`) |
| `schedule show\|create\|remove` | `schedule`: `name`, `command`, and `time`, or `null` when there is no entry |
| `ingest` | `sources`: for each folder of native logs, `source`, `folder`, `new_events`, and `sessions_held_back` |
| `machine label` | `machine` and `label` |
| `config show` | `parameters`, each with `name`, `value`, and `layer`; `entries`, each with `entry` (such as `time_zone`), its keys, and `layer` |
| `config add` | `entry` and its keys as appended |
| `sessions` | `day` and `sessions`, each with `session_id`, `tool`, `start`, `end`, `cwd`, `branch`, and `parts`, each with `project`, `work_item`, `human_time`, and `agent_time` |
| `annotate`, `entry add`, `timesheet confirm`, `timesheet retract`, `retract` | `event_uid` of the event that the command wrote; `timesheet confirm` also `entries` as in `timesheet` |
| `timesheet` | `day`, `state`, `total`, `human_time_at_idle_gaps` (measured days only), `unknown_invocation_share`, `entries` as in `report timesheet`, and `context` with `agent_time` and `presence_span` |
| `entries` | `day` and `entries`, each with `event_uid`, `kind`, `timestamp`, and the other fields of the event ([event-schema.md](event-schema.md) › Fields) |
| `purge` | `keys`, `keys_without_source`, and `written` (true when the command wrote the purge) |
| `report timesheet` | `days`, each with `day`, `state`, `total`, `human_time_at_idle_gaps` (an object from the idle gap in seconds, as text, to the human time; measured days only), `unknown_invocation_share`, and `entries`, each with `project`, `work_item`, `measured`, `with_manual_entries`, `declared` (`null` on a measured day), `inferred_human_share`, and `inferred_agent_share` |
| `report day` | `day`, `state`, `human_time_at_idle_gaps` (measured days only), `unknown_invocation_share`, `person`, `projects`, and `work_items`; `person`, each project of `projects`, and each work item of `work_items` with `human_time`, `agent_time`, `blocked_time`, and `activity_classes` (an object from the activity class to its duration); each project also with `project`, each work item also with `work_item`, and each project and work item also with `inferred_human_share` and `inferred_agent_share` |
| `report timesheet --freeze`, `report day --freeze` | also `frozen_id`, the identifier of the frozen report |
| `frozen list` | `frozen`, each with `id`, `report`, `from`, `to`, `note`, and `machine` |
| `frozen show` | `frozen`, the frozen report; `differences`, for each day, project, and work item whose figures differ: the frozen value and the value of now; and `changed`, the report parameters, rules, and dated facts that differ between the two report records, each with its frozen value and its value of now |
| `frozen remove` | `id` of the removed frozen report |
| `index rebuild` | `segments` and `events`, the numbers that the local index holds |
| `version` | `ledger` and `tzdata` |

A report of a period that a frozen report holds also has `differences` and `changed`, as in `frozen show`.
