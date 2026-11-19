---
status: accepted
date: 2026-11-19
---

# A project has a stable identifier and a separate name

Measured events never store a project: identity rules resolve it at report time (ADR 0009). Manual entries, timesheet
entries, declared usage, and annotations are different: the person declares their project, and the store keeps it.
The stored value must match the project that the identity rules give to measured events, and it must stay valid when
the person changes how the project is called. Therefore each project has a project identifier, which never changes,
and a name, which reports show and which can change. By default the project identifier is the repository identity,
and the name comes from it; an identity rule can give another project identifier, and an entry of the person
configuration can give any project identifier a name. Declared events store the project identifier.

## Considered Options

- **The project is its name**: simple, but a change of name leaves every declared event with the old name without a
  project, and a correction needs a retraction for each of them.
- **Declared events store a repository identity**: the default case needs nothing more, but a project without git and
  a project over two repositories cannot be declared.

## Consequences

- Work items follow the same rule: declared events store a work item identifier, and an entry of the person
  configuration gives it a name; without an entry, the name is the identifier.
- A change of name changes only the configuration; stored events stay as they are, and all history shows the new name.
- A rule that gives a new project identifier to work that had another one leaves the declared events of the old
  identifier where they are; the report warns about declared events whose project identifier no rule, no entry of
  the person configuration, and no repository identity gives.
- Reports group by project identifier and show the name; a name that the person configuration gives to two project
  identifiers is a configuration error that the report shows. Two default names that are the same show more parts of
  their path, so a configuration without names never has this error.
