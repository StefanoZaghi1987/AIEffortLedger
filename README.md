# AI Effort Ledger

Measure the effort of software work that you do fully or partly with AI agents — after the work is done — and keep
the data for estimating new work.

The ledger separates **human time** (your attention) from **agent time** (agents executing work, which adds up when
agents run in parallel) and from **calendar time**. It attributes effort to projects, work items, releases, and
milestones, accepts manual entries, timesheet entries, and declared usage for work that no tool records, and computes
list-price and actual cost at report time. It is independent of the agent tool, the model provider, and the operating
system, and it works for one person or a team.

## Status

Phase 0 (specification, prototype, validation, review) is complete. There is no installable tool yet.

## Roadmap

| Phase | Content |
|---|---|
| 0 | Glossary, specifications, ADRs, measurement prototype, validation, review — done |
| 1 | Core: store, Claude Code adapter (also Claude Desktop), manual entries, timesheet entries, identity rules, split rule, scheduled ingestion, daily timesheet per project |
| 2 | Attribution and reports: work items, releases and milestones, periods, declared usage, list-price cost, subscription division |
| 3 | Coverage: Claude Code plugin with skills and hooks; integration for other agent tools (open: an MCP server over the command line, ingestion of events that other programs write in the normalized form); an adapter for another agent tool, such as Codex, only with real samples from a person who uses that tool |
| 4 | Team: team export, merge, team reports, project configuration |
| 5 | Estimation: estimate-versus-actuals dataset and estimator |
| 6 | Optional: OpenTelemetry ingestion, ingestion of provider analytics, human-activity tracker as a source |

Each phase starts with the specification of the points that the `To be confirmed` sections of the specifications list
for it, and with an implementation plan.

## Documents

| Document | Content |
|---|---|
| [GLOSSARY.md](GLOSSARY.md) | Terms, with the Italian equivalent used in reports and skills |
| [docs/spec/metrics.md](docs/spec/metrics.md) | How events become effort |
| [docs/spec/event-schema.md](docs/spec/event-schema.md) | The normalized event |
| [docs/spec/ingestion.md](docs/spec/ingestion.md) | How sources reach the store |
| [docs/spec/configuration.md](docs/spec/configuration.md) | Where settings and rules live, and how they are written |
| [docs/adr](docs/adr) | Architecture decisions, one per file |
| [docs/research](docs/research) | Point-in-time research |
| [prototype](prototype) | Throw-away measurements on real logs, scenario tests (`python -I -m unittest discover -s prototype/tests`), and validation |

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
