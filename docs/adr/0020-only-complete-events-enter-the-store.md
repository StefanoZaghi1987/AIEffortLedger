---
status: accepted
date: 2026-11-19
---

# Only complete events enter the store

A native log grows while its session runs: Claude Code writes one response of a model on several lines, and writes a
tool result after its tool call, sometimes hours later. A stored event never changes (ADR 0002, ADR 0008), and the size
counters of a tool call come from its tool result (ADR 0016). An ingestion that stores what it sees at its hour
therefore stores events that later records change, and the same native log gives different stores at different hours of
ingestion. Therefore an adapter writes an event only when it is complete, that is, when no later record of its source
can change it. A response of a model is complete when a later record of the same agent exists, a tool call is complete
when its tool result exists, and the events of a subagent are complete when the tool result that links the subagent
exists. When the files of a session have not changed for the settle time (4 hours by
default, a single value of the person configuration), every event of the session is complete. An event that is not
complete stays out of the store, and the next ingestion reads its session again.

## Considered Options

- **Store every event at once and correct it with a later event**: the store mixes observations and corrections, every
  reader must apply the corrections, and two machines can store two versions of one response.
- **Store every event at once and change it in place**: the store is no longer append-only, and a file-sync service can
  copy a segment while it changes (ADR 0010).
- **Wait for the end of the session**: the native log has no record for the end of a session, so a session that stays
  open for days holds back all its events.

## Consequences

- The last response of a session that is still active enters the store only after a later record or after the settle
  time. A report of today can miss that response, and the timesheet of today warns about the events that the machine
  holds back.
- A tool result that arrives after the settle time finds its tool call stored without size counters; a forked session
  whose copies entered the store before its original keeps them in the session of the first ingestion; and the
  repository identity that an event records is the one that its first ingestion observed. These three are the only
  cases where the hour or the order of ingestion changes the store.
- Each machine keeps the sessions with events held back in its machine-local data folder, and reads them again at each
  ingestion.
