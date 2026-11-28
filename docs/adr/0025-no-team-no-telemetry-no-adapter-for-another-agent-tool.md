---
status: accepted
date: 2026-11-25
---

# The roadmap serves one person who works with Claude Code: no team, no telemetry, no adapter for another agent tool

A roadmap is an order: each phase is specified and built after the one before it. The roadmap of the ledger held, after
the reports, a team, the optional sources with telemetry among them, and adapters for other agent tools beside the one
of Claude Code (ADR 0006). The person works with Claude Code and Claude Desktop only; wants to see their own effort
when they work in a team, and little of the effort of the other persons; and measures, outside the ledger, the work
that no agent records. Therefore the roadmap holds what serves that effort: the core, the reports, the integration
with Claude Code as a plugin with hooks and skills, which stays while it improves the architecture, the functioning,
the installation, or the use of the ledger, and the estimation from the reference class of a work item; no phase
builds for a team, reads telemetry, or holds an adapter for another agent tool.

## Considered Options

- **A team phase**: its content — a team export, the merge of stores, team reports, a project configuration that a team
  shares, cost centres, and a pseudonym — serves only the effort of the other persons. Phase 1 shows a person their own
  effort in a team in full, because every store and every report is personal (ADR 0003).
- **Telemetry as an optional source**: optional by its own definition, and a source that records nothing before its
  installation; the cost of Phase 2 has its own sources, an imported cost source and declared usage.
- **Adapters for other agent tools**: the person works with Claude Code and Claude Desktop only, so an adapter for
  another agent tool serves no work the person does; each one is a permanent cost of maintenance against an
  undocumented format (ADR 0006).

## Consequences

- No phase reads telemetry: the ledger opens no connection in any phase, and a value that lives on the network, such
  as the usage that a provider shows, arrives as a file that the person exported. This supersedes ADR 0006 where it
  accepts telemetry as an optional source.
- The architecture of the adapters stays: `adapters` holds one subpackage for each adapter and `tool` is an open set,
  so an adapter for another agent tool, if one is needed, is a new subpackage.
- A need of a team starts a specification then; what a team needs reads personal stores and frozen reports, so
  nothing built until then is wasted.
- ADR 0003, ADR 0005, ADR 0009 and ADR 0010 name a team, a pseudonym, or other agent tools as permissions or as
  examples: they stay as they are.
