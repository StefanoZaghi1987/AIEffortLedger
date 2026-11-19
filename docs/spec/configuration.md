# Configuration

How the ledger gets the values that no source gives. Terms follow [GLOSSARY.md](../../GLOSSARY.md); the reasons are in
ADR 0003, ADR 0004, ADR 0005, ADR 0009, ADR 0017, and ADR 0022.

## Layers

Each fact lives with its owner.

| Layer | Owner | Location | Content |
|---|---|---|---|
| Defaults of the ledger | the ledger | the program | price tables, the table of tool categories of each adapter, the table that converts Windows time-zone names to IANA time zones, default values of parameters |
| Machine configuration | the machine | the machine-local data folder (see [ingestion.md](ingestion.md) › Store) | machine identifier, salted hash of the installation identifier, location of the store, folders of native logs for each agent tool |
| Person configuration | the person | `configuration.toml` in the store folder (ADR 0017) | pseudonym, time-zone history, day start hours, names of projects, identity rules, category rules, names of preferred remotes, settle time, allow-list of label keys, consent for session titles, defaults of report parameters, hourly rates, cost sources |
| Project configuration | the project | `.ai-effort-ledger.toml` at the root of its repository | identity rules on its own repository identity (Phase 4) |

The location of the store is the local user data folder of the operating system unless the machine configuration gives
another folder (ADR 0003); the default store folder of each operating system is in [architecture.md](architecture.md) ›
Files of a machine. A roaming profile does not copy this folder, so the data of the person leaves the machine only when
the person chooses a synchronized folder (ADR 0010); an option of a command can give another folder for that command
only. The store metadata is one file for each machine, which holds its label (see [ingestion.md](ingestion.md) › Store);
it is not part of any configuration.

## Order

A parameter takes its value from the first layer that gives one: an option of the command, then the person
configuration, then the defaults of the ledger. Every report records the values it used (see [metrics.md](metrics.md) ›
Reproducibility).

Rules of all layers apply together, and the most specific matching rule wins (ADR 0009; see Matching). Category rules
replace the category that the table of the adapter gave (see [event-schema.md](event-schema.md)).

## Format

Every configuration file is TOML, which the standard library reads (ADR 0005). Each dated fact and each rule is one
entry of an array of tables:

| Entry | Keys | Content |
|---|---|---|
| `[[time_zone]]` | `zone`, `from` | an IANA time zone and the UTC instant from which it is valid |
| `[[day_start]]` | `hour`, `from` | a day start hour (a TOML local time) and the local date from which it is valid |
| `[[project]]` | `id`, `name` | a project identifier and the name that reports show for it (ADR 0019) |
| `[[work_item]]` | `project`, `id`, `name` | a work item identifier of a project and the name that reports show for it (ADR 0019) |
| `[[identity_rule]]` | `repository`, `folder`, `branch`, `from`, `to`, `project` | the conditions it matches, at least one: a repository identity, an absolute folder, a pattern of branch names, and the first and last local day; and the project identifier it gives |
| `[[category_rule]]` | `tool`, `category` | the pattern of tool names it matches and the tool category it gives |
| `[[label_key]]` | `key` | one key that the `labels` field of an event can hold (Phase 2) |
| `[[hourly_rate]]` | `amount`, `currency`, `from` | an amount, a currency, and the date from which it is valid (Phase 2) |
| `[[cost_source]]` | `name`, `type` | a cost source and its type (Phase 2) |

Single values are keys outside these entries:

| Key | Default | Content |
|---|---|---|
| `preferred_remotes` | `["origin"]` | names of preferred remotes ([ingestion.md](ingestion.md) › Repository identity) |
| `settle_time` | `"4h"` | the settle time ([ingestion.md](ingestion.md) › Adapters) |
| `session_titles` | `false` | the consent for session titles (Phase 2) |
| `pseudonym` | none | the pseudonym of the person (Phase 4) |
| `[report]` table | defaults of the ledger | defaults of report parameters, one key for each: `idle_gap`, `minimum_attention`, `stale_limit`, `headless_prompts`, `first_day_of_week`, `timesheet_granularity`, `language` |

Keys and entries of a later phase are valid in any version of the ledger and have no effect before their phase. A
duration is a text of whole numbers with the units `h`, `min`, and `s`, such as `"4h"`, `"10min"`, or `"1h30min"`. For
example, a journey adds this entry to the time-zone history:

```toml
[[time_zone]]
zone = "Asia/Tokyo"
from = 2026-12-01T00:00:00Z
```

A dated fact is not overwritten: a new value is a new entry with a later start, so the earlier value stays valid for the
earlier instants, and a report of any period recomputes with the values that applied then. Each entry is valid from its
start to the next start in the same list, never before its own start; two entries of one list with the same start are a
configuration error; in the time-zone history and the day start hours they leave instants without a local day, so every
command that needs local days stops with an error that names the two entries. An instant before the earliest entry of
the time-zone history or of the day start hours has no local day: a report that needs it stops with an error that names
the instant.

## Matching

A rule matches an event when all its conditions match. A repository in a rule is a repository identity and matches only
that repository identity; `config add` turns a remote URL into a repository identity with the steps of
[ingestion.md](ingestion.md) › Repository identity. A branch or a tool name in a rule is a pattern in which `*` stands
for any text, and it matches with regard to case. A folder in a rule is an absolute folder and matches that folder and
every folder inside it; `/` and `\` are the same separator, and Windows paths match without regard to case. A range of
dates is a range of local days of the person, with both ends included (see [metrics.md](metrics.md) › Days and weeks).

Rule X is more specific than rule Y when X has every condition of Y with the same or a narrower value, and at least one
more condition or one narrower value. A value is narrower when it matches a part of what the other value matches: a
folder inside the other folder, a pattern whose every match the other pattern also matches (an exact name is a pattern
without `*`), a range of dates inside the other range. Pattern P matches a part of what pattern Q matches when Q matches
the text of P in which each `*` is a character that only a `*` of Q matches. When one of the matching rules is more
specific than every other matching rule, it wins. Otherwise the ledger applies none of them, never a silent choice
(ADR 0009): an event that two identity rules claim goes to the unattributed bucket, a tool that two category rules claim
keeps the category that the adapter stored, and the report shows the configuration error with the rules and one event
that they match. The default identity rule, one repository identity as one project, applies only to events that no
identity rule of a configuration matches, so it never makes a configuration error.

## Writes

The command line changes the person configuration only by appending entries at the end of the file. Each appended value
is written as a TOML basic string: the ledger writes the value between double quotes and escapes double quotes,
backslashes, and control characters, so a value can never add, change, or remove an entry. The re-read after each append
applies to every command that appends. Before it appends, it checks each value: a time zone that `tzdata` holds, an hour
as `HH:MM`, a tool category of the event schema, a duration in the format above, and an instant or a day in the format
of [command-line.md](command-line.md) › Form; a wrong value stops the command with the exit code for wrong use. After
each append, it reads the whole file again; when the read fails, it restores the earlier content and reports the error.
It never writes the file again as a whole, so the comments and the layout of the person stay. The person changes single
values, and corrects or removes entries, with a text editor; the next report reads the file as it is (ADR 0002). When
two machines change the file before a file-sync service copies it, the service keeps a conflict copy; the ledger reads
only `configuration.toml`, and the person merges the copy by hand (ADR 0017). The command line takes the lock of the
machine and the store ([architecture.md](architecture.md) › Concurrency) while it appends.

When setup finds a store folder that has no person configuration, it creates the file with one `[[time_zone]]` entry
that holds the time zone of the operating system and one `[[day_start]]` entry with 00:00, both valid from the start of
1970 (`1970-01-01T00:00:00Z` and `1970-01-01`), so that native logs older than the first run have local days. It shows
the entries and the file in which the person changes them.

Linux and macOS give an IANA time zone. Windows gives a Windows time-zone name, the value `TimeZoneKeyName` of the
registry, which the ledger reads with `winreg` and converts with a table made from the CLDR `windowsZones` list and held
in the program as data. When the table has no conversion for the name, the ledger writes no `[[time_zone]]` entry, and
every report stops with an error that asks for the time zone; the ledger never guesses a time zone.

Setup writes the machine configuration as a whole, also when it creates a new machine identifier, sets another location
of the store, or records folders of native logs. Its keys and the types of their values are fixed
([architecture.md](architecture.md) › Files of a machine), so writing it needs no general TOML writer.

A configuration file that the ledger cannot read stops every command that needs it, with the line of the error; the
ledger never uses part of a file.

## Project configuration

A project configuration applies only to events whose repository identity is the repository identity of its own
repository. A rule in it that matches another repository identity, or a folder, is a configuration error: the ledger
ignores the rule and the report shows the error, so that a repository taken from a source cannot change the attribution
of other work. Rules on local folders stay in the person configuration (ADR 0009). The ledger only reads the file and
never runs git to get it (ADR 0004); reading TOML runs no code.

## To be confirmed

- Which copy of a project configuration applies: the folder from which the ledger reads it, when it reads it (ingestion
  or report), how a change of the file over time applies, and how a report records it. To specify at the start of
  Phase 4.
- Whether a rule of the person configuration overrides a rule of a project configuration of equal specificity, or the
  two are a configuration error as within one layer (ADR 0009). To specify at the start of Phase 4.
- Which other shared content a project configuration holds, such as milestones, releases, and price tables, which
  ADR 0003 allows in a project repository. To specify with the phase that introduces each content.
- Which release of the CLDR `windowsZones` list the table of Windows time-zone names is built from, and how an update of
  the table reaches a release. To specify before the end of Phase 1.
