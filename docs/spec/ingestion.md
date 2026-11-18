# Ingestion

How sources reach the store. Terms follow [GLOSSARY.md](../../GLOSSARY.md); the reasons are in ADR 0004, ADR 0006,
ADR 0009, and ADR 0010.

## Adapters

Each source format has one adapter. An adapter reads its source, drops all text of prompts, responses, tool input, and
code, and writes events as defined in [event-schema.md](event-schema.md). An adapter recognizes the native format
versions it supports; a record type or a structure it does not know produces a warning with the record type and the
format version, never an event with a guessed meaning.

An adapter sets the invocation of each session from what the source shows, and writes the prompts of sessions that are
not interactive as notifications. For Claude Code, the entry points `cli` and `local-agent` are interactive and the
entry point `sdk-cli` is headless.

The Claude Code adapter also reads Claude Desktop sessions, which use the same format: local Cowork sessions under
`Claude/local-agent-mode-sessions/…/.claude/projects/` in the application data folder of the operating system.

## Store

The store is a folder of segments (ADR 0010). Ingestion on a machine appends events only to the segments of that
machine and never changes a segment of another machine. A lock per machine serializes ingestions that start at the
same time, such as a scheduled run and a hook. Each machine keeps a local index derived from all segments; the index
is never shared and can be rebuilt. Every read ignores the events whose key a purge lists, in any segment. Before it
appends an event, ingestion checks the purges of all segments, and it removes purged events from the segments of its
own machine.

## Frequency

Native logs disappear after the retention period of their agent tool (30 days by default for Claude Code). Ingestion
therefore runs:

- on a schedule much shorter than the shortest retention period of the sources in use (default: daily);
- at the end of a session, through a hook of the agent tool where one exists;
- before a worktree is removed, where the agent tool reports the removal, so that its repository identity is observed
  while the folder exists.

Every ingestion records the newest event it found per source. When the oldest event still present in a source is newer
than the newest event already in the store, the ledger warns that some events were lost.

## Repository identity

Repository identity is an observation on events; identity rules turn it into a project at report time (ADR 0009). The
ledger resolves the repository of a folder by reading files, never by running git inside a folder taken from a source
(ADR 0004): it finds `.git` (a folder, or a file that points to a worktree folder), follows `commondir` to the common
git directory, and reads the remote URL from its `config`, or the root commit from the object store when no remote
exists. Folders without git, folders inside virtual machines (such as Cowork sessions), and folders that no longer
exist resolve through identity rules in the configuration; otherwise their events are unattributed.

## To be confirmed

- How the root commit is found without git when the object store is packed.
- How a hook of an agent tool triggers ingestion without delaying the end of the session.
- The invocation of the other Claude Code entry points (editor extensions, other SDK entry points), and how an adapter
  recognizes sessions that an orchestrator drives and the session that started them.
- Whether a headless prompt that a person types in a terminal (for example a single `claude -p` command) counts as a
  human signal, and how the adapter can tell it from a script.
- Whether one adapter reads events that other programs (agent tools, orchestrators, converters written by a member of
  a team) write directly in the form of [event-schema.md](event-schema.md), and how it rejects fields outside the
  schema, so that a new agent tool needs no adapter inside the ledger.
- Whether a folder that no longer exists resolves through its nearest existing parent folder (for example a worktree
  inside its repository), with the result marked as inferred.
- Whether setup advises a longer retention period where an agent tool allows it (for Claude Code,
  `cleanupPeriodDays`), after a check of the official documentation.
