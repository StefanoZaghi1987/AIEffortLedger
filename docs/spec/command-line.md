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
- the value of a timesheet entry is `<project>=<duration>`, or `<project>#<work item identifier>=<duration>`.

## Output

- **Standard output** holds the result: tables for a person, or the JSON document with `--json`.
- **Standard error** holds warnings and errors, one on each line, each starting with `warning:` or `error:`. With
  `--json`, warnings and configuration errors are also in the `warnings` and `configuration_errors` lists of the
  document.
- **Durations** are `H:MM` in tables and whole seconds in JSON.

A command asks a question only in `setup` and `purge`, and only when standard input is a terminal. An option gives
every answer, so a scheduler, a hook, or a script never waits for a person.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | the command completed |
| 1 | the command stopped with an error and wrote nothing, for example: a configuration file that the ledger cannot read, an instant without a local day, or a lock not available within 10 minutes |
| 2 | wrong use: an unknown command or option, or a value in a wrong format |
| 3 | the command completed, but some figures are not complete: a configuration error, a broken line in a segment, or, for the ingestion that finds them, events lost because a native log was deleted before ingestion |

A warning that does not make a figure incomplete, such as an unknown tool name, a declared value lower than the
measured value, or two timesheet confirmations of a day from two machines, keeps the exit code 0.

## Commands

| Command | Use |
|---|---|
| `setup` | prepare the ledger on a machine (see Setup) |
| `schedule show\|create\|remove` | show, create, or remove the scheduled ingestion ([ingestion.md](ingestion.md) › Frequency) |
| `ingest` | run an ingestion; show the number of new events of each source |
| `machine label <text>` | change the label of the machine in its store metadata |
| `config show` | show the value of each parameter and dated fact with the layer that gives it, and every configuration error |
| `config add <entry> <options>` | append an entry to the person configuration (see Configuration entries) |
| `sessions <day>` | list the sessions of a local day: identifier, agent tool, start, end, folder, branch, project, work item, human time, agent time |
| `annotate --session <id> \| --from <instant> --to <instant>` with at least one of `--project`, `--work-item`, and an optional `--note` | write an annotation; `--session` takes the identifier that `sessions` shows |
| `entry add --from <instant> --to <instant> --project <project> --mode overlapping\|additional` with `--work-item`, `--note` | write a manual entry |
| `timesheet <day>` | show the timesheet proposal of a measured day, or the timesheet entries of a declared day, with the measured values next to them |
| `timesheet confirm <day>` with `--total <duration>`, `--set <value of a timesheet entry>` (repeatable), `--note <text>` | write a timesheet confirmation (see Timesheet) |
| `timesheet retract <day>` | retract the latest timesheet confirmation of the day |
| `entries <day>` | list the manual entries, annotations, and timesheet confirmations of a day, with their event keys |
| `retract <key>` | write a retraction of a manual entry, an annotation, or a timesheet confirmation, by the key that `entries` shows |
| `purge` (see Purge) | remove events from the store |
| `report timesheet --from <day> --to <day>` | the daily timesheet of a period (see Reports) |
| `report day <day>` | human time, agent time, blocked time, and activity classes of a day, for the person and each project |
| `freeze --from <day> --to <day>` with `--note` | keep the daily timesheet of the period as a frozen report; show its identifier |
| `frozen list`, `frozen show <id>` | list the frozen reports; show one with its differences against a report of now |
| `index rebuild` | build the local index again from the segments |
| `version` | show the version of the ledger and of `tzdata` |

## Setup

`setup` runs these steps in this order. It can run again at any time: it changes only what its options or answers
change.

1. Machine configuration: create the machine identifier when there is none, or a new one when the installation
   identifier changed ([ingestion.md](ingestion.md) › Store); record the folders of native logs that each agent tool
   uses on the machine, also the one that `CLAUDE_CONFIG_DIR` gives at setup, and the folders of
   `--native-logs <agent tool>=<folder>`.
2. Store folder: the default folder, or the folder of `--store`, which `setup` writes in the machine configuration.
3. Person configuration: when the store folder has none, create it ([configuration.md](configuration.md) › Writes) and
   show its entries.
4. Machine label: the value of `--label`, or the answer of the person; written in the store metadata.
5. Retention: show the retention period of each agent tool and the advice of [ingestion.md](ingestion.md) › Frequency.
6. Scheduled ingestion: show the scheduler entry, a daily ingestion at the time of `--time` (default 12:00), and
   create it only with `--schedule yes` or the consent of the person ([ingestion.md](ingestion.md) › Frequency).
7. First ingestion: run `ingest`.

Every other command stops with exit code 1, and asks for `setup`, when the machine has no machine configuration or
the store folder has no person configuration.

## Configuration entries

`config add` appends one entry with the keys of [configuration.md](configuration.md) › Format as options:

| Entry | Options |
|---|---|
| `time-zone` | `--zone <IANA time zone> --from <instant>` |
| `day-start` | `--hour <HH:MM> --from <day>` |
| `project` | `--id <project identifier> --name <name>` |
| `work-item` | `--project <project identifier> --id <work item identifier> --name <name>` |
| `identity-rule` | `--project <project identifier>` and at least one of `--repository`, `--folder`, `--branch`, `--from`, `--to` |
| `category-rule` | `--tool <pattern> --category <tool category>` |

## Timesheet

`timesheet confirm <day>` without options confirms the timesheet proposal as `timesheet <day>` shows it. `--set` gives
the value of one entry; the other entries keep their proposed values. `--total` gives the total human time of the day,
which divides among the entries that `--set` does not give ([metrics.md](metrics.md) › Declared values). The command
writes one timesheet confirmation with all the entries of the day, shows them, and warns about each entry that is lower
than the measured human time of its project and work item. A new confirmation of the same day replaces the earlier one
as a whole, and names, in `replaces`, the latest confirmation of the day that the machine has. `--set` can name a
project or a work item that the proposal does not hold. `--note` gives its text to every entry. When the values of
`--set` are more than `--total`, the command stops with exit code 1.

## Purge

```text
ai-effort-ledger purge (--key <key>... | --writer-version-below <version> [--source <source>])
                       --reason content|correction|forget [--corrected-version <version>] [--yes]
```

The command shows the keys that it removes and warns about the keys whose source no longer exists
([event-schema.md](event-schema.md) › Keys and invariants). It writes the purge only with `--yes` or the consent of the
person. `--corrected-version` is not accepted with `--reason forget` (ADR 0015).

## Reports

`report timesheet` shows, for each local day of the period, the state of the day (measured or declared) and, for each
project and work item and for the unattributed time, the measured human time with manual entries, the declared value,
and the total human time of the day ([metrics.md](metrics.md) › Declared values). Measured days also show their human
time at idle gaps of 5, 10, and 15 minutes ([metrics.md](metrics.md) › Uncertainty). Warnings and configuration errors
come before the table.

With `--json`, the document holds `report` (the name of the report), `record` (the report record,
[architecture.md](architecture.md) › Report record), `days` (for each day: `day`, `state`, `total`, and `entries` with
`project` and `work_item` each as `id` and `name`, or `null` for the unattributed time and for no work item, `measured`,
and `declared`), `warnings`, and `configuration_errors`.

In Italian, the titles, the states, and the warnings use the Italian terms of [GLOSSARY.md](../../GLOSSARY.md);
project names, work items, and notes stay as the person wrote them.
