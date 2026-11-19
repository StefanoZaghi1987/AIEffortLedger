---
status: superseded in part by 0015, 0017
date: 2026-11-18
---

# The store is a folder of segments with one writer each

A person works on several machines and can keep the store in any folder: the user data folder, a folder synchronized
by a file-sync service, a network share, or a repository with or without `.gitignore` (ADR 0003). File-sync services
and git copy whole files and cannot merge two writers of one file. The store is therefore a folder of segments: each
machine appends its events to its own segments, append-only JSON Lines files per machine and month, and never changes
a segment of another machine. A read is the union of all segments, deduplicated by event key with the merge rule of
the event schema. Each machine keeps a local index derived from all segments; the index is never shared and can be
rebuilt at any time. A lock per machine serializes ingestions that start at the same time, such as a scheduled run and
a hook.

## Considered Options

- **One SQLite file for the store**: a file-sync service creates conflict copies or a damaged file when two machines
  write between two synchronizations, and git cannot merge a binary file.
- **One SQLite file per machine**: free of conflicts, but binary: a person cannot read a segment to check that it
  holds no text (ADR 0003), and a repository cannot show its differences.
- **Central server**: see ADR 0003.

## Consequences

- Reading cost grows with the number of segments; the local index keeps reports fast.
- A purge rewrites only the segments of the machine that runs it; the purge event reaches the other machines through
  the store folder. Every read ignores purged keys at once, and each machine removes them from its own segments at its
  next ingestion (ADR 0008).
- The person pseudonym and the store settings are metadata of the store folder, not fields of each event.
