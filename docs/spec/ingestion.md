# Ingestion

How sources reach the store. Terms follow [GLOSSARY.md](../../GLOSSARY.md); the reasons are in ADR 0004 and ADR 0006.

## Adapters

Each source format has one adapter. An adapter reads its source, drops all text of prompts, responses, tool input, and
code, and writes events as defined in [event-schema.md](event-schema.md). An adapter recognizes the native format
versions it supports; a record type or a structure it does not know produces a warning with the record type and the
format version, never an event with a guessed meaning.

The Claude Code adapter also reads Claude Desktop sessions, which use the same format: local Cowork sessions under
`Claude/local-agent-mode-sessions/…/.claude/projects/` in the application data folder of the operating system.

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

The ledger resolves the repository of a folder by reading files, never by running git inside a folder taken from a
source (ADR 0004): it finds `.git` (a folder, or a file that points to a worktree folder), follows `commondir` to the
common git directory, and reads the remote URL from its `config`, or the root commit from the object store when no
remote exists. Folders without git, folders inside virtual machines (such as Cowork sessions), and folders that no
longer exist resolve through identity rules in the configuration; otherwise their events are unattributed.

## To be confirmed

- How the root commit is found without git when the object store is packed.
- How a hook of an agent tool triggers ingestion without delaying the end of the session.
