# AI Effort Ledger

Measure the effort of software work that you do fully or partly with AI agents — after the work is done — and keep
the data for estimating new work.

The ledger separates **human time** (your attention) from **agent time** (agents executing work, which adds up when
agents run in parallel) and from **calendar time**. It attributes effort to projects and work items, accepts manual
entries for work that no source recorded, and proposes a daily timesheet from measured values that you confirm. From
Phase 2 it also accepts declared usage, computes cost at report time (the list-price cost of a model, the actual
cost that a cost source gives, and the allocated cost of a subscription), and reads the labels that annotations set.
It is independent of the agent tool, the model provider, and the operating system, and it
works for one person.

## Status

Phase 0 (specification, prototype, validation, review) is complete. Phase 1 — the core: the daily timesheet of one
person, from Claude Code and Claude Desktop — is implemented. Phase 2 adds weekly, monthly, and custom period
reports with calendar time, token usage, and list-price cost, then declared usage, actual cost and subscription
division, and labels; then the maintenance of the price table, the dated price rows and the provider rows. Phase 3
adds a Claude Code plugin with hooks and skills. Phase 4 adds estimation, from
estimates recorded before the work starts and the actuals of completed work items. The first release is `v0.1.0`;
publication on a package index is a later decision. The content of each phase is in
[docs/spec/product.md](docs/spec/product.md).

## Install

The package needs Python 3.11 or later ([pyproject.toml](pyproject.toml)). Install the first release, `v0.1.0`, from
this repository:

```text
uv tool install git+https://github.com/StefanoZaghi1987/AIEffortLedger.git@v0.1.0
```

or, with pipx:

```text
pipx install git+https://github.com/StefanoZaghi1987/AIEffortLedger.git@v0.1.0
```

## Use

Prepare the ledger on a machine: `setup` records the folders of the native logs of the agent tools present on the
machine, sets the store folder (`--store`, or the default store folder), writes the person configuration when the
store has none, and runs the first ingestion; with `--schedule yes` it also creates the scheduled ingestion, a daily
ingestion at the time of `--time` (12:00 by default).

```text
ai-effort-ledger setup --store D:\Work\Store --schedule yes
```

The daily timesheet: `timesheet <day>` shows the timesheet proposal of a measured day — the human time per project,
work item, and unattributed time — and `timesheet confirm <day>` writes the timesheet confirmation.

```text
ai-effort-ledger timesheet today
ai-effort-ledger timesheet confirm today
```

The report of a period shows, for each day, the state of the day (measured or declared), its total human time, and
the human time of each project, work item, and the unattributed time:

```text
ai-effort-ledger report timesheet --from 2026-11-01 --to 2026-11-30
```

Every command takes `--language en|it`, the language of the output. The scheduled ingestion is removed with:

```text
ai-effort-ledger schedule remove
```

Every command, option, output, and exit code is in [docs/spec/command-line.md](docs/spec/command-line.md).

## Remove

Run `ai-effort-ledger schedule remove` first: removing the package removes neither the entry of the scheduled
ingestion nor the folders of the machine. Then uninstall the package:

```text
uv tool uninstall ai-effort-ledger
```

or, with pipx:

```text
pipx uninstall ai-effort-ledger
```

The store folder — `%LOCALAPPDATA%\ai-effort-ledger\store` on Windows, `$XDG_DATA_HOME/ai-effort-ledger/store` on
Linux, `~/Library/Application Support/ai-effort-ledger/store` on macOS, or the folder that `setup --store` gave —
and the machine-local data folder — `%LOCALAPPDATA%\ai-effort-ledger\machine` on Windows,
`$XDG_STATE_HOME/ai-effort-ledger/machine` on Linux, `~/Library/Application Support/ai-effort-ledger/machine` on
macOS — stay; delete them by hand.

## Documents

Read them in this order:

| Document | Content |
|---|---|
| [docs/spec/product.md](docs/spec/product.md) | Objective, persons, non-goals, phases, scope and acceptance criteria of Phase 1 |
| [GLOSSARY.md](GLOSSARY.md) | Terms, with the Italian equivalent used in reports and skills |
| [docs/spec/metrics.md](docs/spec/metrics.md) | How events become effort |
| [docs/spec/event-schema.md](docs/spec/event-schema.md) | The normalized event and its encoding |
| [docs/spec/ingestion.md](docs/spec/ingestion.md) | How sources reach the store, and the store |
| [docs/spec/claude-code-adapter.md](docs/spec/claude-code-adapter.md) | How native logs of Claude Code and Claude Desktop become events |
| [docs/spec/configuration.md](docs/spec/configuration.md) | Where settings and rules live, their format, and how they are written |
| [docs/spec/command-line.md](docs/spec/command-line.md) | Commands, options, output, exit codes, reports |
| [docs/spec/architecture.md](docs/spec/architecture.md) | Modules, data flow, files of a machine, local index, concurrency, tests |
| [docs/adr](docs/adr) | Architecture decisions, one per file; the status line of each tells which later ADR changes it |
| [docs/research](docs/research) | Point-in-time research; not updated after its date |
| [prototype](prototype) | Throw-away measurements on real logs, scenario tests (`python -I -m unittest discover -s prototype/tests`), and validation |

A specification with open points ends with a `To be confirmed` section: each open point names the phase that specifies
it, or the event that lets the ledger specify it, such as a real sample of a native log.

## Principles

- Human time, agent time, and calendar time are never summed or converted (ADR 0001).
- The store keeps events; every figure is computed at report time and can be recomputed (ADR 0002).
- Your data is private, outside project repositories by default, and holds no prompt or code text (ADR 0003).
- The store is a folder of segments with one writer per machine, so it can live in any folder, synchronized or not
  (ADR 0010).
- A project comes from identity rules at report time; by default one repository is one project (ADR 0009).
- A timesheet is proposed from measured values and confirmed by the person (ADR 0011).
- All logic is in a Python command line; agent skills and hooks only call it (ADR 0005).

## Languages

Code, identifiers, and documentation are in English. Reports and skills are available in English and Italian, with the
terms fixed by [GLOSSARY.md](GLOSSARY.md).
