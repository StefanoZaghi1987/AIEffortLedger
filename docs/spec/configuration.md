# Configuration

How the ledger gets the values that no source gives. Terms follow [GLOSSARY.md](../../GLOSSARY.md); the reasons are
in ADR 0003, ADR 0004, ADR 0005, ADR 0009, and ADR 0017.

## Layers

Each fact lives with its owner.

| Layer | Owner | Location | Content |
|---|---|---|---|
| Defaults of the ledger | the ledger | the program | price tables, the table of tool categories of each adapter, the table that converts Windows time-zone names to IANA time zones, default values of parameters |
| Machine configuration | the machine | the machine-local data folder (see [ingestion.md](ingestion.md) › Store) | machine identifier, salted hash of the installation identifier, location of the store |
| Person configuration | the person | `configuration.toml` in the store folder (ADR 0017) | pseudonym, time-zone history, day start hours, names of projects, identity rules, category rules, names of preferred remotes, allow-list of label keys, consent for session titles, defaults of report parameters, hourly rates, cost sources |
| Project configuration | the project | `.ai-effort-ledger.toml` at the root of its repository | identity rules on its own repository identity |

The location of the store is the local user data folder of the operating system unless the machine configuration gives
another folder (ADR 0003): `%LOCALAPPDATA%\ai-effort-ledger\store` on Windows, `$XDG_DATA_HOME/ai-effort-ledger` on Linux
(`~/.local/share/ai-effort-ledger` when the variable is not set), and `~/Library/Application
Support/ai-effort-ledger/store` on macOS. A roaming profile does not copy this folder, so the data of the person leaves
the machine only when the person chooses a synchronized folder (ADR 0010); an option of a command can give another
folder for that command only. The store metadata is one file for each machine, which holds its label (see
[ingestion.md](ingestion.md) › Store); it is not part of any configuration.

## Order

A parameter takes its value from the first layer that gives one: an option of the command, then the person
configuration, then the defaults of the ledger. Every report records the values it used (see
[metrics.md](metrics.md) › Reproducibility).

Rules of all layers apply together, and the most specific matching rule wins (ADR 0009; see Matching). Category rules
replace the category that the table of the adapter gave (see [event-schema.md](event-schema.md)).

## Format

Every configuration file is TOML, which the standard library reads (ADR 0005). Each dated fact and each rule is one
entry of an array of tables:

| Entry | Content |
|---|---|
| `[[time_zone]]` | an IANA time zone and the instant from which it is valid |
| `[[day_start]]` | a day start hour and the local date from which it is valid |
| `[[project]]` | a project identifier and the name that reports show for it (ADR 0019) |
| `[[identity_rule]]` | the repository identity, folder, branch, and dates it matches, and the project identifier it gives |
| `[[category_rule]]` | the pattern of tool names it matches and the tool category it gives |
| `[[label_key]]` | one key that the `labels` field of an event can hold |
| `[[hourly_rate]]` | an amount, a currency, and the date from which it is valid |
| `[[cost_source]]` | a cost source and its type |

Single values, such as the consent for session titles, the names of preferred remotes (`["origin"]` by default, see
[ingestion.md](ingestion.md) › Repository identity), and the defaults of report parameters, are keys outside these
entries. For example, a journey adds this entry to the time-zone history:

```toml
[[time_zone]]
zone = "Asia/Tokyo"
from = 2026-12-01T00:00:00Z
```

A dated fact never changes: a new value is a new entry with a later start, so the earlier value stays valid for the
earlier instants, and a report of any period recomputes with the values that applied then. Each entry is valid from its
start to the start of the next entry of the same list, never before its own start. An instant before the earliest entry
of the time-zone history or of the day start hours has no local day: a report that needs it stops with an error that
names the instant.

## Matching

A rule matches an event when all its conditions match. A branch or a tool name in a rule is a pattern in which `*`
stands for any text. A folder in a rule matches that folder and every folder inside it; `/` and `\` are the same
separator, and Windows paths match without regard to case. A range of dates is a range of local days of the person,
with both ends included (see [metrics.md](metrics.md) › Days and weeks).

Rule X is more specific than rule Y when X has every condition of Y with the same or a narrower value, and at least
one more condition or one narrower value. A value is narrower when it matches a part of what the other value matches:
a folder inside the other folder, an exact name that the other pattern matches, a range of dates inside the other
range. When one of the matching rules is more specific than every other matching rule, it wins; otherwise the report
shows a configuration error, never a silent choice (ADR 0009). Category rules follow the same rule.

## Writes

The command line changes the person configuration only by appending entries at the end of the file. After each append,
it reads the whole file again; when the read fails, it restores the earlier content and reports the error. It never
writes the file again as a whole, so the comments and the layout of the person stay. The person changes single values,
and corrects or removes entries, with a text editor; the next report reads the file as it is (ADR 0002).

At its first run with a store folder that has no person configuration, the ledger creates the file with one
`[[time_zone]]` entry that holds the time zone of the operating system and one `[[day_start]]` entry with 00:00, both
valid from the start of 1970 (`1970-01-01T00:00:00Z` and `1970-01-01`), so that native logs older than the first run
have local days. It shows the entries and the file in which the person changes them.

Linux and macOS give an IANA time zone. Windows gives a Windows time-zone name, which the ledger converts with a
table made from the CLDR `windowsZones` list and held in the program as data. When the table has no conversion for
the name, the ledger writes no `[[time_zone]]` entry, and every report stops with an error that asks for the time
zone; the ledger never guesses a time zone.

The ledger writes the machine configuration as a whole: at its first run, when it creates a new machine identifier,
and when the person sets another location of the store. Its keys and the types of their values are fixed, so writing
it needs no general TOML writer.

A configuration file that the ledger cannot read stops every command that needs it, with the line of the error; the
ledger never uses part of a file.

## Project configuration

A project configuration applies only to events whose repository identity is the repository identity of its own
repository. A rule in it that matches another repository identity, or a folder, is a configuration error that the
report shows, so that a repository taken from a source cannot change the attribution of other work. Rules on local
folders stay in the person configuration (ADR 0009). The ledger only reads the file and never runs git to get it
(ADR 0004); reading TOML runs no code.

## To be confirmed

- Which copy of a project configuration applies: the folder from which the ledger reads it, when it reads it (ingestion
  or report), how a change of the file over time applies, and how a report records it. To specify at the start of
  Phase 4.
- Whether a rule of the person configuration overrides a rule of a project configuration of equal specificity, or the
  two are a configuration error as within one layer (ADR 0009). To specify at the start of Phase 4.
- Which other shared content a project configuration holds, such as milestones, releases, and price tables, which
  ADR 0003 allows in a project repository. To specify with the phase that introduces each content.
