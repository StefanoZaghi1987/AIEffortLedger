# AI Effort Ledger

Measure the effort of software work that you do fully or partly with AI agents — after the work is done — and keep
the data for estimating new work.

The ledger separates **human time** (your attention) from **agent time** (agents executing work, which adds up when
agents run in parallel) and from **calendar time**. It attributes effort to projects, work items, releases, and
milestones, accepts manual entries for work that no tool records, and computes list-price and actual cost at report
time. It is independent of the agent tool, the model provider, and the operating system, and it works for one person
or a team.

## Status

Phase 0: specification and prototype. There is no installable tool yet.

## Documents

| Document | Content |
|---|---|
| [GLOSSARY.md](GLOSSARY.md) | Terms, with the Italian equivalent used in reports and skills |
| [docs/spec/metrics.md](docs/spec/metrics.md) | How events become effort |
| [docs/spec/event-schema.md](docs/spec/event-schema.md) | The normalized event |
| [docs/spec/ingestion.md](docs/spec/ingestion.md) | How sources reach the store |
| [docs/adr](docs/adr) | Architecture decisions, one per file |
| [docs/research](docs/research) | Point-in-time research |
| [prototype](prototype) | Throw-away measurements on real logs |

## Principles

- Human time, agent time, and calendar time are never summed or converted (ADR 0001).
- The store keeps events; every figure is computed at report time and can be recomputed (ADR 0002).
- Your data is private, outside project repositories by default, and holds no prompt or code text (ADR 0003).
- All logic is in a Python command line; agent skills and hooks only call it (ADR 0005).

## Languages

Code, identifiers, and documentation are in English. Reports and skills are available in English and Italian, with the
terms fixed by [GLOSSARY.md](GLOSSARY.md).
