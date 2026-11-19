# Ingestion

How sources reach the store. Terms follow [GLOSSARY.md](../../GLOSSARY.md); the reasons are in ADR 0004, ADR 0006,
ADR 0009, ADR 0010, ADR 0015, ADR 0018, and ADR 0020.

## Adapters

Each source format has one adapter. An adapter reads its source, drops all text of prompts, responses, tool input, and
code, and writes events as defined in [event-schema.md](event-schema.md). An adapter recognizes the native format
versions it supports; a record type or a structure it does not know produces a warning with the record type and the
format version, never an event with a guessed meaning.

An adapter writes an event only when it is complete, that is, when no later record of the source can change it
(ADR 0020). A response of a model is complete when a later record of the same agent exists, and a tool call is complete
when its tool result exists. When the files of a session have not changed for the settle time (default 4 hours, a single
value of the person configuration), every event of the session is complete; a tool result that arrives later finds its
tool call stored without size counters. An event that is not complete stays out of the store, and the next ingestion
reads it again, so the same native log gives the same store at any hour of ingestion (ADR 0002). Three cases depend on
the hour or the order of ingestion: a tool result that arrives after the settle time; a forked session whose copied
events entered the store before the session that holds them as its own ([event-schema.md](event-schema.md) › Keys and
invariants); and the repository identity, which the first ingestion of an event reads from the folder as it is at that
hour (see Repository identity).

An adapter sets the invocation of each session from what the source shows, and writes the prompts of sessions that are
not interactive as notifications. A value that the adapter does not know gives invocation `unknown` and a warning that
names the value. When a later version of the ledger knows the value, a purge that names that version as its corrected
version lets the next ingestion write the events again with their invocation, while the native log exists (ADR 0015).
An adapter sets invocation `orchestrated` only when the source shows a sign of it.

Each adapter maps native tool names to tool categories with its own table. Each ingestion warns once for each tool name
that it finds, that the table does not list, and that no category rule matches ([configuration.md](configuration.md) ›
Matching); a category rule such as `mcp__*` → `other` stops the warnings for all tools of MCP servers.

Each adapter reads the folders of native logs that the machine configuration lists for each of its agent tools: setup
writes there the folders that each agent tool uses on the machine, and the person can add more
([command-line.md](command-line.md) › Setup). The ledger has these adapters:

| Adapter (`source`) | Sources | Specification | Phase |
|---|---|---|---|
| `claude-code-jsonl` | native logs of Claude Code and of Claude Desktop | [claude-code-adapter.md](claude-code-adapter.md) | 1 |

## Store

The store is a folder of segments (ADR 0010). Ingestion on a machine appends events only to the segments of that machine
and never changes a segment of another machine. A lock per machine serializes ingestions that start at the same time,
such as a scheduled run and a hook. Each machine keeps a local index derived from all segments; the index is never
shared and can be rebuilt ([architecture.md](architecture.md) › Local index). Every read ignores the copies that a purge
blocks, in any segment (see [event-schema.md](event-schema.md)). Before it appends an event, ingestion checks the purges
of all segments, and it removes blocked copies from the segments of its own machine. A purge with a corrected version
names the sessions that hold its keys. When a machine finds such a purge and its own version is that corrected version
or newer, its next ingestion reads again those sessions whose native logs still exist, and the machine records the purge
as applied; a machine with an older version leaves the purge to a later version.

A segment has one writer, so two machines must never share an identifier, while a new identifier is always safe: the old
segments only stop growing. At setup on a machine, the ledger creates a random machine identifier and keeps it in the
machine configuration, in the machine-local data folder of the operating system ([architecture.md](architecture.md) ›
Files of a machine), never in the store and never in a folder that a roaming profile copies. Next to it, the ledger
keeps a salted hash of the installation identifier; when that hash changes, because a user profile was copied to another
computer or a virtual machine was cloned, the ledger creates a new machine identifier; every command that writes checks
the hash first. Where the operating system gives no identifier, this check does not apply. The person gives each machine
a machine label, which the machine writes in its own file of store metadata and reports show; the label can change at
any time.

The store folder has this layout, and every file has one writer (ADR 0010):

| Path | Content | Writer |
|---|---|---|
| `segments/<machine>/<YYYY-MM>.jsonl` | the events that the machine wrote in that month of `ingested_at` (UTC) | that machine |
| `machines/<machine>.toml` | the store metadata of the machine: its label | that machine |
| `configuration.toml` | the person configuration ([configuration.md](configuration.md)) | the person |
| `frozen/<machine>/<id>.json` | a frozen report, as given ([command-line.md](command-line.md) › Frozen reports) | the machine that froze it, which alone removes it |

A machine appends only to the segment of the current month, so an older segment changes only through a purge, which
writes the new segment in a new file and then puts it in the place of the old one.

A reader ignores a last line of a segment that has no line break, without a warning, because a machine or a file-sync
service is still writing it. A line that is not a valid event in another position is a broken line: it stays out of
every report, and the report warns with the segment and the line number, and completes with the exit code for incomplete
figures ([command-line.md](command-line.md) › Exit codes). An event of a newer schema version is not a broken line
([event-schema.md](event-schema.md) › Encoding). The order of the names of segments, which settles two copies of an
event with the same `ingested_at` (see [event-schema.md](event-schema.md)), is the order of these paths as text. The
lock and the record of the last ingestion of each folder of native logs are facts of one machine and one store: they
stay in the machine-local data folder, next to the machine configuration, outside the store, with one copy for each
store that the machine uses ([architecture.md](architecture.md) › Files of a machine).

## Frequency

Native logs disappear after the retention period of their agent tool (30 days by default for Claude Code). Ingestion
therefore runs:

- on a schedule much shorter than the shortest retention period of the sources in use (default: daily);
- at the end of a session, through a hook of the agent tool where one exists (Phase 3);
- before a worktree is removed, where the agent tool reports the removal, so that its repository identity is observed
  while the folder exists (Phase 3).

Setup shows the scheduled task and creates it only when the person agrees, and only in a scheduler that keeps each task
as its own entry: the Task Scheduler on Windows, a launchd agent on macOS, or a systemd user timer on Linux. The task is
an entry of the ledger, so the ledger changes nothing that another program owns, and a command removes it. Where only
cron exists, whose table of a user is one shared file, setup shows the line to add. When the person does not agree, or
the run cannot ask, such as a first run from a hook, setup only shows the task.

The entry of the scheduled ingestion has the name `ai-effort-ledger-ingest`, by which `schedule show` and
`schedule remove` find it. It runs the absolute path of the installed command `ai-effort-ledger` with
`ingest --store <store folder>`, once a day at the time of `--time` of `setup` or `schedule create` (default 12:00),
without a visible window where the scheduler allows it. It runs a missed start as soon as possible: the Task Scheduler
with its setting to start a missed task when it can, a systemd timer with `Persistent=true`, and launchd when the
computer wakes.

For each folder of native logs, every ingestion records its own instant. When the time since the previous ingestion of a
folder is longer than the retention period of its agent tool, the agent tool can have deleted files that changed after
that ingestion before any ingestion read them: the ingestion warns that events may be lost, names the folder and the
interval, and completes with the exit code for incomplete figures.

Each adapter declares the retention setting of its agent tool (for Claude Code, `cleanupPeriodDays` in any settings
file). Setup shows the retention period that the agent tool applies and what it means: events of a native log that a
longer gap in ingestion lets the agent tool delete are lost, and a purge that names a corrected version brings back
only events whose native log still exists (ADR 0015). Setup advises a longer retention period, shows the setting to
change, and states its cost: the native log keeps the text of prompts, responses, and code on the disk for longer. The
person decides; the ledger never changes the settings of an agent tool.

## Repository identity

Repository identity is an observation on events; identity rules turn it into a project at report time (ADR 0009). The
ledger resolves the repository of a folder by reading files, never by running git inside a folder taken from a source
(ADR 0004): it finds `.git` (a folder, or a file that points to a worktree folder), follows `commondir` to the common
git directory, and reads the remote URL from its `config`, or the root commit from the object store when no remote
exists.

The remote is the first one in the list of preferred remote names of the person configuration (`["origin"]` by default)
that the repository has, otherwise the first remote in the order of the names. Its URL becomes a repository identity in
these steps: for a URL with a scheme (such as `https://` or `ssh://`), remove the scheme, the user information with any
password or token, and the port; for an address without a scheme (`user@host:path`), remove the user and write
`host:path` as `host/path`; remove a final `.git` and a final `/`; write all in lower case. No credential reaches the
store. When the SSH URL and the HTTPS URL of a repository differ only in these parts, the two clones have one repository
identity. When a host writes them with different paths, an identity rule joins the two identities. The ledger reads only
the `config` file of the common git directory, without its `include` files and without `insteadOf` rewrites. A remote
that is a local folder or a `file://` URL is not used, because its path names folders of the machine; the ledger takes
the next remote, or the root commit.

The root commit is the commit that the ledger reaches from `HEAD`, resolved through the reference files and
`packed-refs`, by following the first parent of each commit until a commit has no parent. The ledger reads each commit
as a loose object or from a pack file, with its deltas, using only the standard library (`zlib`), and keeps the root
commit of each repository, so it reads the history of a repository once. It reads the remotes from `config` at every
ingestion, so a remote that is added or changed applies to the events that later ingestions write. A repository that
gets its first remote changes from a root-commit identity to a remote identity; an identity rule joins the two. The
repository identity of a root commit is `root-commit:` followed by its hash. A shallow clone, whose history stops before
its root, has no root-commit identity, and the ledger warns.

When the folder of an event no longer exists, ingestion starts the search for `.git` at the nearest existing parent
folder; the repository identity it finds is inferred, and the event records `repo_basis` `inferred` (ADR 0018). The
search for `.git` never reaches the home folder of the person or the root of a drive, so a repository there, such as one
that keeps the settings files of the person, gives no identity to the folders inside it. A `cwd` that is not an absolute
path of the operating system of the machine, such as a path inside a virtual machine, is not resolved. Folders without
git, folders inside virtual machines (such as Cowork sessions), and folders whose search finds no repository resolve
through identity rules ([configuration.md](configuration.md)); otherwise their events are unattributed.

## To be confirmed

- How a hook of an agent tool triggers ingestion without delaying the end of the session. Facts for Claude Code
  ([hooks](https://code.claude.com/docs/en/hooks)): `SessionEnd` hooks share a budget of 1.5 seconds, which a per-hook
  `timeout` raises up to 60 seconds; a command hook with `"async": true` runs in the background, and Claude Code does
  not enforce its `timeout`; `WorktreeRemove` fires only for a worktree that a `WorktreeCreate` hook created, so the
  nearest existing parent folder (ADR 0018) still covers other worktrees. To specify at the start of Phase 3.
- How an adapter recognizes sessions that an orchestrator drives, and the session that started them: the native log
  of Claude Code shows no known sign. To specify with a real sample.
- Whether one adapter reads events that other programs (agent tools, orchestrators, converters written by a member of a
  team) write directly in the form of [event-schema.md](event-schema.md), and how it rejects fields outside the schema,
  so that a new agent tool needs no adapter inside the ledger. To specify at the start of Phase 3.
