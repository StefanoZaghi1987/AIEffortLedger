---
status: accepted
date: 2026-11-18
---

# The store keeps normalized events; every derived value is computed at report time

The store keeps only atomic, normalized events with a stable key, and never derived values such as work blocks,
intervals, attributions, or costs. Idle gap, split rule, attribution rules, and price tables are report parameters,
so any of them can change and the whole history recomputes without loss. Ingesting the same source twice produces the
same store, and stores from several machines merge by key without duplicates.

## Considered Options

- **Store derived work blocks keyed by start time** (the approach of the package this project replaces): a change
  of idle gap or time zone changes the keys and duplicates the blocks; the history cannot be recomputed after the
  native logs are deleted.
- **Store raw native log files**: complete, but tied to undocumented formats, large, and full of prompt content
  (see ADR 0003).

## Consequences

- Reports cost more computation; at the expected volume (thousands of events per day) this is not a concern.
- The event schema is the contract between adapters and the metrics engine and changes only with a schema version.
