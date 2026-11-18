---
status: accepted
date: 2026-11-18
---

# A project is an attribution dimension that identity rules resolve; the repository is an observation

ADR 0004 identified a project by its repository. Real work does not follow repositories: one contract spans a frontend
and a backend repository, one monorepo holds two products, one repository serves one contract in March and another in
May, and most session folders measured in the prototype are Cowork paths or folders without git. The ledger therefore
records the repository identity, the folder, and the branch of each event as observations, and resolves the project at
report time through identity rules that match on date interval, branch pattern, folder prefix, and repository identity.
The default rule makes one repository identity one project, so the simple case needs no configuration. Events that no
rule resolves are unattributed. The way ADR 0004 reads repository identity stays: from the repository files, never by
running git inside a folder taken from a source.

## Considered Options

- **Project equal to repository, exceptions by annotation** (ADR 0004): every session of a monorepo or of a
  multi-repository contract needs an annotation, and a change of contract on the same repository cannot be expressed
  once for all its sessions.
- **Project declared by the person for each session**: needs an action of the person for every session, and
  unattended sessions started by a schedule or an orchestrator have nobody to ask.

## Consequences

- The daily timesheet per project needs identity rules, so they belong to the first phase that produces a timesheet.
- A change of identity rules recomputes the whole history (ADR 0002).
- The most specific matching rule wins; two matching rules of equal specificity are a configuration error that the
  report shows, never a silent choice.
- Identity rules on repository identity, branch, and date hold no personal data and can live in a project repository
  and be shared by a team (ADR 0003); rules on local folders stay in the private configuration of the person.
