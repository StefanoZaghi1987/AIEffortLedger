# Architecture

The parts of the ledger, how data goes through them, the files that they keep, and how they are tested. Terms follow
[GLOSSARY.md](../../GLOSSARY.md); the reasons are in ADR 0002, ADR 0005, ADR 0010, and ADR 0017.

## Runtime

The ledger is one Python package, `ai-effort-ledger`, with the import name `ai_effort_ledger` and one command,
`ai-effort-ledger` ([command-line.md](command-line.md)). A person installs a release, a tag `v<version>` of its git
repository, with `uv tool install git+<repository URL>@v<version>` or `pipx`; it needs Python 3.11 or later, and
publication on the package index is a later decision. It uses only the standard library and the time-zone database
`tzdata` (ADR 0005). It reads time zones only from `tzdata` (`zoneinfo.reset_tzpath` with an empty path), on every
operating system, so that all machines of a person compute the same local days, and every report records the version of
`tzdata`.

The ledger never uses the network. It never runs a program inside a folder taken from a source (ADR 0004); the only
programs it runs are the schedulers of the operating system in `setup` and `schedule` and, on macOS, `ioreg` for the
installation identifier.

The version of the package is whole numbers separated by dots, and it is the writer version of every event that the
package writes. Every release has a higher version than the earlier releases, and a build from a commit without a
release tag writes only to the stores of tests (ADR 0015).

## Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `events` | the event schema: fields, encoding, validation, event keys, the merge rule of two copies | — |
| `platform` | folders of the operating system, installation identifier, file lock, scheduler entries | — |
| `repository` | repository identity from the files of a repository, without git | — |
| `configuration` | reading the machine configuration and the person configuration, appending entries, matching rules, dated facts | `platform` |
| `store` | segments: append, read, purge, broken lines, store metadata, frozen reports | `events`, `platform` |
| `index` | the local index of a store | `store` |
| `adapters` | one subpackage for each adapter; `claude_code` turns native logs into complete events | `events` |
| `ingestion` | the ingestion of all adapters into the store | `adapters`, `repository`, `store`, `index`, `configuration` |
| `days` | local days from the time-zone history and the day start hours | `configuration` |
| `metrics` | turns, human time, agent time, blocked time, activity classes of the person | `events` |
| `attribution` | identity rules, annotations, names of projects and work items, the split rule, unattributed time, activity classes of projects and work items | `metrics`, `configuration`, `days` |
| `declared` | manual entries, timesheet proposals, timesheet confirmations, retractions | `metrics`, `attribution`, `days` |
| `reports` | reports, their record, frozen periods, text and JSON output, English and Italian | `declared`, `index` |
| `setup` | the setup steps and the scheduled ingestion | `configuration`, `platform` |
| `cli` | commands, options, exit codes | all |

Build order: `events`, `platform`, `repository` → `configuration`, `store` → `index`, `adapters` → `ingestion` →
`days`, `metrics` → `attribution` → `declared` → `reports`, `setup` → `cli`. A module never imports a module that
depends on it, and only `cli` writes to the terminal.

## Data flow

An ingestion runs these steps:

1. Take the lock of the machine and the store (see Concurrency).
2. Read the machine configuration and the person configuration.
3. Bring the local index up to date with the segments.
4. For each adapter, find the sessions to read: each session with a file that changed since the last ingestion,
   with events held back because they were not complete, or with a key of a purge with a corrected version that
   the machine has not applied yet. Read all the files of each of these sessions.
5. The adapter writes the complete events of those sessions ([ingestion.md](ingestion.md) › Adapters).
6. Resolve the repository identity of each new folder ([ingestion.md](ingestion.md) › Repository identity).
7. Keep only the events that no purge blocks and of which the store holds no copy that a purge leaves.
8. Append them to the segment of the machine for the current month.
9. Add them to the local index, record the newest event of each folder of native logs and the sessions with events
   held back, and warn about lost events.
10. Remove the copies that a purge blocks from the segments of the machine.
11. Release the lock.

A report brings the local index up to date and selects: the events of its period, with a margin of the longer of the
stale limit and the idle gap before its start and after its end; the timesheet confirmations by their `day`; manual
entries and annotations of an interval by their interval; and retractions, purges, and annotations of a session at any
instant. It leaves out the events that a purge blocks, that a retraction cancels, and that broken lines hold, and then
applies attribution, metrics, and declared values in that order.

## Files of a machine

The machine-local data folder ([ingestion.md](ingestion.md) › Store) holds:

| Path | Content |
|---|---|
| `machine.toml` | the machine configuration: `machine` (the machine identifier), `installation` and `salt` (the salted hash of the installation identifier), `store` (the store folder, when it is not the default), and a `[native_logs]` table with a list of folders for each agent tool |
| `repositories.json` | the repository identity of each repository already read, by the path of its common git directory |
| `stores/<store>/lock` | the lock of the machine and that store |
| `stores/<store>/sources.json` | the newest event of each folder of native logs, the size and the time of change of each file of native logs already read, the sessions with events held back, and the purges already applied |
| `stores/<store>/index.sqlite` | the local index of that store |

`<store>` is the first 16 hexadecimal characters of the SHA-256 hash of the absolute path of the store folder, with
links resolved, and on Windows with all its characters in lower case. The installation identifier is `MachineGuid` of
the Windows registry, `/etc/machine-id` on Linux, and `IOPlatformUUID` of `ioreg` on macOS.

The store metadata of a machine, `machines/<machine>.toml` in the store folder, holds one key, `label`.

## Local index

The local index is an SQLite database (`sqlite3` of the standard library) that holds every event of every segment with
its segment and line, and for each segment the number of bytes that it indexed and the SHA-256 hash of its last indexed
line. To bring it up to date, the ledger reads only the new bytes of a segment whose last indexed line is still at the
same place, reads again a segment where it is not, such as after a purge, and removes the events of a segment that no
longer exists. When the index was written by a version of the ledger with another index format, the ledger builds it
again. It adds the lines of a segment in one transaction, keyed by segment and byte offset, so a report and an ingestion
that bring it up to date at the same time add each line once. No result depends on the index: a report with an empty
index gives the same figures.

## Concurrency

The lock is a lock of the operating system on the file `stores/<store>/lock`. Every command that writes to the store,
or appends to the person configuration, takes it; the operating system releases it when the process ends, so a lock
never stays after a crash. A command that cannot take the lock within 10 minutes stops with an error. Reports take no
lock: they read the lines that the segments hold, and ignore a last line without a line break.

A machine writes each event as one complete line and flushes it. A purge writes the new segment to a new file and then
replaces the old one in one operation of the file system; when another process holds the segment open, the purge tries
again until the time limit of the lock. Two machines never write the same file; the person configuration is the only
file that more than one machine can change, and ADR 0017 gives its conflicts to the person.

## Report record

Every report records: the version of the ledger and of `tzdata`; the report parameters and the dated facts that it
used; its configuration errors; and the state of the store that it read: for each segment, its path, the number of
bytes read, and the SHA-256 hash of those bytes, and the broken lines that it skipped. A frozen report is this record
with the figures of the report, as JSON in `frozen/<machine>/<id>.json` of the store folder, with a random UUID as
`<id>`. A later report of a frozen period shows the differences against it for each day, project, and work item.

## Tests

Tests use `unittest` of the standard library: `python -I -m unittest discover -s tests`, in a virtual environment with
the package installed in editable mode (`uv pip install -e .`).

- **Unit tests** for each module.
- **Scenario tests**: the scenarios of the prototype ([validation-2026-11.md](../research/validation-2026-11.md)), with
  values computed by hand, run on the core; every rule of [metrics.md](metrics.md) has at least one scenario.
- **Adapter fixtures**: small native logs written by hand, with the record types and keys of
  [claude-code-adapter.md](claude-code-adapter.md) and invented text; one fixture for each row of its table of records.
  No fixture holds text copied from a native log (CLAUDE.md › Privacy).
- **Store tests**: store folders that act as two machines and a file-sync service with a delay: half-written last
  lines, broken lines, purges with and without a corrected version, timesheet confirmations of the same day from two
  machines.
- **Order tests**: the same native logs in any order of files, and the same segments in any order, give the same store
  and the same reports.
- **Report tests**: the text and JSON output of fixture stores, in English and Italian, against expected files.
- **Privacy test**: a store built from all fixtures holds only fields of the schema, and no text of the prompts,
  responses, tool input, or code of the fixtures.

The tests run on Windows, Linux, and macOS, with Python 3.11 and the newest Python release. The validation on real
native logs is not a test: it runs by hand on a copy of the native logs, writes only to a folder that git ignores, and
its ratios go to `docs/research/`.

## Project structure

| Path | Content |
|---|---|
| `src/ai_effort_ledger/` | the package, one module or subpackage for each row of Modules |
| `tests/` | the tests of the package; fixtures in `tests/fixtures/` |
| `pyproject.toml` | the package, its version, its dependency on `tzdata`, and the command |
| `prototype/` | the throw-away prototype; not part of the package |
| `docs/` | specifications, ADRs, research |
