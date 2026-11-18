---
status: accepted
date: 2026-11-18
---

# Purge is the only operation that removes events from the store

The store is append-only (ADR 0002): a correction is a new event. An annotation sets labels on a session or a time
interval, for example the work item a session belongs to, and adds no time; a retraction is an event that cancels an
earlier event by key. Neither removes data. Purge is the single exception: it deletes events physically, for content
that must not be kept (text ingested by mistake against ADR 0003) or on request of the person who owns the store. A
purge writes a purge record with the keys removed, the reason, and the time, so that a merge with an older copy of the
store from another machine does not bring the events back.

## Considered Options

- **Retraction only**: rejected; a retracted event keeps its data, which is not acceptable for text that must not be
  stored.
- **Editable events**: rejected; edits make re-ingestion and merge non-deterministic and remove the history that
  reproducible reports need.

## Consequences

- A report frozen before a purge can no longer be recomputed for the purged events; the frozen report stays valid as
  a record of what was reported.
