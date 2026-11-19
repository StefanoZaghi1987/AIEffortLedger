# AI Effort Ledger

Measure the effort of software work that you do fully or partly with AI agents — after the work is done — and keep
the data for estimating new work.

The ledger separates **human time** (your attention) from **agent time** (agents executing work, which adds up when
agents run in parallel) and from **calendar time**. It attributes effort to projects, work items, releases, and
milestones, accepts manual entries, timesheet entries, and declared usage for work that no tool records, and computes
list-price and actual cost at report time. It is independent of the agent tool, the model provider, and the operating
system, and it works for one person or a team.

## Status

Phase 0 (specification, prototype, validation, review) is complete. Phase 1 is in specification; there is no
installable tool yet. The content of each phase is in [docs/spec/product.md](docs/spec/product.md).

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

Each specification ends with a `To be confirmed` section: its open points, each with the phase that specifies it.

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
