# Architecture

The parts of the ledger, how data goes through them, the files that they keep, and how they are tested. Terms follow
[GLOSSARY.md](../../GLOSSARY.md); the reasons are in ADR 0002, ADR 0005, ADR 0010, ADR 0017, ADR 0022, and ADR 0023.

## Runtime

The ledger is one Python package, `ai-effort-ledger`, with the import name `ai_effort_ledger` and one command,
`ai-effort-ledger` ([command-line.md](command-line.md)). A person installs a release, a tag `v<version>` of its git
repository, with `uv tool install git+<repository URL>@v<version>` or `pipx`; it needs Python 3.11 or later, and
publication on the package index is a later decision. It uses only the standard library and the time-zone database
`tzdata` (ADR 0005). It reads time zones only from `tzdata` (`zoneinfo.reset_tzpath` with an empty path), on every
operating system, so that all machines of a person compute the same local days, and every report records the version of
`tzdata` (ADR 0022).

The build tool is `flit_core` (`requires = ["flit_core >=4.2,<5"]`, `build-backend = "flit_core.buildapi"`): a
pure-Python package without dependencies, maintained by the PyPA, that installers download only to build the package
([build-tool-2026-11.md](../research/build-tool-2026-11.md)). `pyproject.toml` holds the metadata only in its standard
`[project]` table, with a static version.

The ledger never uses the network. It never runs a program inside a folder taken from a source (ADR 0004); the only
programs it runs are the schedulers of the operating system in `setup` and `schedule` and, on macOS, `ioreg` for the
installation identifier.

The version of the package is the writer version of every event that the package writes (ADR 0015). A release version
is whole numbers separated by dots, such as `1.3.0`, and every release has a higher version than the earlier releases.
Between two releases, `pyproject.toml` holds the next version with a development mark, `.dev` and a whole number, such
as `1.3.0.dev0`; a version with the mark comes before the same version without it, as in the version order of PEP 440.
A version with a development mark writes to a store only when the environment variable `AI_EFFORT_LEDGER_DEVELOPMENT`
is `1`; otherwise every command that writes stops with exit code 1. The tests set the variable.

## Modules

| Module | Responsibility | Depends on |
|---|---|---|
| `events` | the event schema: fields, encoding, validation, event keys, the merge rule of two copies, reading of newer schema versions | — |
| `platform` | folders of the operating system, installation identifier, file lock, scheduler entries | — |
| `repository` | repository identity from the files of a repository, without git | — |
| `language` | the English and Italian texts of titles, states, warnings, and errors, by code | — |
| `configuration` | reading the machine configuration and the person configuration, appending entries, dated facts and rules as values | `platform` |
| `store` | segments: append, read, purge, broken lines, store metadata, frozen reports | `events`, `platform` |
| `adapters` | one subpackage for each adapter; `claude_code` turns native logs into complete events; each adapter declares the folders of native logs and the retention setting of its agent tools | `events` |
| `index` | the local index of a store | `store` |
| `days` | local days from the time-zone history and the day start hours | `configuration` |
| `ingestion` | the ingestion of all adapters into the store | `adapters`, `repository`, `store`, `index`, `configuration` |
| `selection` | the events of a report: its period with whole sessions, without the events that a purge blocks or that a retraction cancels | `index`, `days` |
| `metrics` | turns, measured human time, manual entries and their union with measured human time, agent time, blocked time, activity classes of the person | `events` |
| `attribution` | matching of identity rules and category rules, annotations, names of projects and work items, the split rule, unattributed time, activity classes of projects and work items | `metrics`, `configuration`, `days` |
| `declared` | timesheet proposals, timesheet confirmations, declared days | `attribution`, `days` |
| `setup` | the setup steps and the scheduled ingestion | `configuration`, `platform`, `ingestion` |
| `reports` | reports, their record, frozen reports and differences, text and JSON output | `declared`, `selection`, `language` |
| `cli` | commands, options, exit codes; the only module that writes to the terminal, in the language of the output | all |

Build order: `events`, `platform`, `repository`, `language` → `configuration`, `store`, `adapters` → `index`, `days` →
`ingestion`, `selection`, `metrics` → `attribution` → `declared`, `setup` → `reports` → `cli`. A module never imports a
module that depends on it. Every module other than `cli` returns its warnings and configuration errors as values, each
with a code and the values that it names, and `cli` writes them with the texts of `language` in the language of the
output ([command-line.md](command-line.md) › JSON documents). The `cli` module also runs the modules of a report in the
order of the data flow, and passes the result of each to the next, so `reports` imports neither `metrics` nor
`attribution`.

## Data flow

An ingestion runs these steps:

1. Take the lock of the machine and the store (see Concurrency).
2. Read the machine configuration and the person configuration.
3. Bring the local index up to date with the segments.
4. For each adapter, find the sessions to read: each session with a file that changed since the last ingestion,
   with events held back because they were not complete, or named by a purge with a corrected version that the
   machine has not applied yet and whose corrected version is not newer than the version of the ledger. Read all the
   files of each of these sessions.
5. The adapter writes the complete events of those sessions ([ingestion.md](ingestion.md) › Adapters).
6. Resolve the repository identity of each new folder ([ingestion.md](ingestion.md) › Repository identity).
7. Keep only the events that no purge blocks and of which the store holds no copy that a purge leaves.
8. Append them to the segment of the machine for the current month.
9. Add them to the local index, record the instant of this ingestion for each folder of native logs and the
   sessions with events held back, and warn about lost events.
10. Remove the copies that a purge blocks from the segments of the machine.
11. Release the lock.

A report brings the local index up to date and selects: all the events of every session that has an event in its period,
with a margin of the longer of the stale limit and the idle gap before its start and after its end, so that a decision
request, a wait for a subagent, or the folder of an earlier event of the session counts the same in a report of one day
and in a report of a longer period; the timesheet confirmations by their `day`; manual entries and annotations of an
interval by their interval; and retractions, purges, and annotations of a session at any instant. It leaves out the
events that a purge blocks, that a retraction cancels, and that broken lines hold, and then computes in the order of the
modules: `selection`, `metrics`, `attribution`, `declared`, and `reports`.

## Files of a machine

The ledger uses these folders, where `$XDG_STATE_HOME` is `~/.local/state` and `$XDG_DATA_HOME` is `~/.local/share` when
the variable is not set:

| Operating system | Machine-local data folder | Default store folder |
|---|---|---|
| Windows | `%LOCALAPPDATA%\ai-effort-ledger\machine` | `%LOCALAPPDATA%\ai-effort-ledger\store` |
| Linux | `$XDG_STATE_HOME/ai-effort-ledger/machine` | `$XDG_DATA_HOME/ai-effort-ledger/store` |
| macOS | `~/Library/Application Support/ai-effort-ledger/machine` | `~/Library/Application Support/ai-effort-ledger/store` |

The machine-local data folder ([ingestion.md](ingestion.md) › Store) holds:

| Path | Content |
|---|---|
| `machine.toml` | the machine configuration: `machine` (the machine identifier), `installation` and `salt` (the salted hash of the installation identifier), `store` (the store folder, when it is not the default), and a `[native_logs]` table with a list of folders for each agent tool, which its adapter reads or searches ([claude-code-adapter.md](claude-code-adapter.md) › Native logs) |
| `repositories.json` | the root commit of each repository already read, by the path of its common git directory; the remotes are read again at every ingestion |
| `stores/<store>/lock` | the lock of the machine and that store |
| `stores/<store>/sources.json` | the instant of the last ingestion of each folder of native logs, the size and the time of change of each file of native logs already read, the sessions with events held back, and the purges already applied |
| `stores/<store>/index.sqlite` | the local index of that store |

`<store>` is the first 16 hexadecimal characters, in lower case, of the SHA-256 hash of the absolute path of the store
folder, with links resolved; on Windows the ledger reads the path itself in lower case before the hash, so that two
ways to write the same folder give one `<store>`. A move of the store folder therefore gives a new
`<store>`, a new local index, and an ingestion that reads every native log again; the store keeps one copy of each event
key. The installation identifier is `MachineGuid` of the Windows registry, `/etc/machine-id` on Linux, and
`IOPlatformUUID` of `ioreg` on macOS.

The store metadata of a machine, `machines/<machine>.toml` in the store folder, holds one key, `label`.

## Local index

The local index is an SQLite database (`sqlite3` of the standard library) that holds every event of every segment with
its segment and line, and for each segment the number of bytes that it indexed, the SHA-256 hash of its last indexed
line, and the chained hash of its indexed lines: the SHA-256 hash of the chained hash of the lines before it and the
bytes of the line, starting from the hash of no bytes. To bring it up to date, the ledger reads only the new bytes of a
segment whose last indexed line is still at the same place, reads again a segment where it is not, such as after a
purge, and removes the events of a segment that no longer exists. When the index was written by a version of the ledger
with another index format, the ledger builds it again. It adds the lines of a segment in one transaction, keyed by
segment and byte offset, so a report and an ingestion that bring it up to date at the same time add each line once. The
database runs in WAL mode, every connection sets a busy timeout of 30 seconds, and a command that cannot write within
the timeout stops with exit code 1. No result depends on the index: a report with an empty index gives the same
figures.

## Concurrency

The lock is a lock of the operating system on the file `stores/<store>/lock`. Every command that writes to the store,
or appends to the person configuration, takes it; the operating system releases it when the process ends, so a lock
never stays after a crash. A command that cannot take the lock within 10 minutes stops with an error. Reports take no
lock — they read the lines that the segments hold, and ignore a last line without a line break — except a report with
`--freeze`, which writes a frozen report into the store folder and takes the lock.

A machine writes each event as one complete line and flushes it. A purge writes the new segment to a new file and then
replaces the old one in one operation of the file system; when another process holds the segment open, the purge tries
again until the time limit of the lock. Two machines never write the same file; the person configuration is the only
file that more than one machine can change, and ADR 0017 gives its conflicts to the person.

## Report record

Every report records: the version of the ledger and of `tzdata`; the report parameters, the identity rules and category
rules, and the dated facts that it used; its configuration errors; and the state of the store that it read: for each
segment, its path, the number of bytes read, and the chained hash of those lines from the local index, and the broken
lines that it skipped. A frozen report is kept as given in `frozen/<machine>/<id>.json` of the store folder, and only
the machine that wrote it removes it; the rule of the frozen reports, and what a later report of the same period shows
against them, is in [command-line.md](command-line.md) › Frozen reports.

## Tests

Tests use `unittest` of the standard library: `python -I -m unittest discover -s tests`, in a virtual environment with
the package installed in editable mode (`uv pip install -e .`).

- **Unit tests** for each module.
- **Scenario tests**: the scenarios of the prototype ([validation-2026-11.md](../research/validation-2026-11.md)), with
  values computed by hand, run on the core; every rule of [metrics.md](metrics.md) has at least one scenario, among them
  the two modes of manual entries, the timesheet proposal and the division of a given total, a change of the day start
  hour, a day with a change of daylight saving, a journey to another time zone, overlapping annotations, and work that
  crosses the start or the end of a report period.
- **Adapter fixtures**: small native logs written by hand, with the record types and keys of
  [claude-code-adapter.md](claude-code-adapter.md) and invented text; one fixture for each row of its table of records.
  No fixture holds text copied from a native log (CLAUDE.md › Privacy).
- **Store tests**: store folders that act as two machines and a file-sync service with a delay: half-written last
  lines, broken lines, purges with and without a corrected version, timesheet confirmations of the same day from two
  machines.
- **Order tests**: the same native logs in any order of files, and the same segments in any order, give the same store
  and the same reports; two stores are the same when they hold the same event keys, and each key with the same fields
  except `ingested_at`. The report of a day gives the same figures for that day as a report of a longer period that
  holds it.
- **Report tests**: the text and JSON output of fixture stores, in English and Italian, against expected files.
- **Privacy test**: a store built from all fixtures holds only fields of the schema version that the ledger writes, and
  no text of the prompts, responses, tool input, or code of the fixtures.

A GitHub Actions workflow, `.github/workflows/tests.yml`, runs the tests after each push and each pull request on
Windows, Linux, and macOS, with Python 3.11 and the newest Python release, and then runs the static check
`python -I tests/style.py`: it parses every file of the package and of the tests, names identifiers that hold a whole
word that the glossary marks _Avoid_ (it reads them from [GLOSSARY.md](../../GLOSSARY.md)), public functions without
type hints, and lines longer than 99 columns ([lint-tool-2026-11.md](../research/lint-tool-2026-11.md)). The workflow
uses only actions that GitHub publishes, `actions/checkout` and `actions/setup-python`, each fixed to a commit hash.

The validation on real native logs is not a test: it runs by hand on a copy of the native logs, writes only to a folder
that git ignores, and its ratios go to `docs/research/`.

The benchmark is not a test either. `tests/benchmark.py`, whose name does not match the `test*.py` pattern of
`unittest`, writes invented native logs with the record types of the adapter fixtures: 30 days × 10 sessions a day ×
1,000 lines a session, 300,000 lines, by default; the size is an option of the script. It times the first ingestion of
these native logs and a daily timesheet of one month. A person runs it by hand on a laptop before each release, and
writes the seconds and the processor of the laptop in a dated note in `docs/research/`.

## Release

A release is a tag `v<version>` of the repository (see Runtime). The steps, in this order:

1. Run the tests.
2. Run the benchmark on a laptop and write the dated note in `docs/research/` (see Tests).
3. Set the release version in `pyproject.toml`, without the development mark, and commit.
4. Tag the commit `v<version>` and push the tag.

## Project structure

| Path | Content |
|---|---|
| `src/ai_effort_ledger/` | the package, one module or subpackage for each row of Modules |
| `tests/` | the tests of the package; fixtures in `tests/fixtures/`; the benchmark in `tests/benchmark.py`; the static check in `tests/style.py` |
| `pyproject.toml` | the build tool, the package, its version, its dependency on `tzdata`, and the command |
| `.github/workflows/` | the workflow that runs the tests on three operating systems (see Tests) |
| `prototype/` | the throw-away prototype; not part of the package |
| `docs/` | specifications, ADRs, research |
