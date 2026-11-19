---
status: accepted
date: 2026-11-18
---

# A purge names the writer version from which purged keys can come back

ADR 0008 makes a purge block its keys, so that a merge with an older copy of the store does not bring the events back. A
stored event never changes, so the only way to correct the events that a faulty adapter wrote is a purge followed by a
new ingestion; with keys blocked for good, the corrected events can never come back. A purge must therefore block the
bad copies of a key, not always the key. Every event records its writer version: the version of the ledger program that
wrote it, compared number by number. A purge can name a corrected version: copies of its keys with an older writer
version stay blocked in every segment, and copies from the corrected version or a newer one are accepted. A purge
without a corrected version blocks its keys for good. The reason of a purge (`content`, `correction`, `forget`) is a
label for the person and does not change the behaviour; a purge with reason `forget` never names a corrected version.
Before a purge, the ledger warns about the keys whose source no longer exists, because no new ingestion can bring them
back. This supersedes ADR 0008 where it blocks the keys of every purge for good, and ADR 0010 where every read ignores
purged keys.

## Considered Options

- **Every purge blocks its keys for good** (ADR 0008 as written): an adapter correction can never reach stored events.
- **A purge removes the copies ingested before its time and accepts later copies**: a machine that runs an older
  version of the ledger, or that receives the purge late through a file-sync service, brings a bad copy back.
- **The reason decides the behaviour**: a name then carries a rule, and a new reason needs a new rule; a person who
  wrote text in a note by mistake needs a purge that blocks for good, whatever its name.

## Consequences

- Every event has `writer_version`, and a purge has an optional `corrected_version`; the event schema has these fields
  from its first version.
- After an adapter error, the events that the faulty versions wrote can be selected by writer version, without a scan
  of the sources.
- Writer versions must be comparable: every build of the ledger that writes to a store has a higher version than every
  earlier build.
