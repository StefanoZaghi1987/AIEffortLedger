---
status: accepted
date: 2026-11-19
---

# Event keys come from facts of the source, and the event schema only grows

The events of one person come from several machines, several versions of the ledger, and several ingestions of the same
native logs, and they merge in any order (ADR 0010). A key that depends on the line number of a record, on its content,
or on the hour of ingestion gives two keys to one event. A field whose meaning changes between versions gives two
meanings to one stored value. And a machine with an older version of the ledger reads the segments of a machine with a
newer one. Therefore the key of an event comes only from facts that the source gives about identity: the source and the
native identifier, or the source, the session, and an event identifier that the adapter makes from the kind, the
timestamp, and the position among the records with the same kind and timestamp. A forked session starts with copies of
records of its original; the copies are events of the original, which is the session that holds records of its own
inside the time range of the shared records. A new version of the event schema only adds fields, kinds of event, or
values, and never changes the meaning of an existing one. A reader ignores a field that it does not know, and leaves out
an event of a kind, or with a value, that it does not know, with a warning that asks to update the ledger.

## Considered Options

- **Key from a hash of the record**: a change of a field that the adapter writes gives a new key to the same event.
- **Key from the position of the record in its file**: a fork, or a file that the agent tool writes again, moves every
  position.
- **A reader that leaves out every event of a newer schema version**: two machines with different versions show
  different figures for the same old fields.
- **A reader that stops until it is updated**: one machine without the update shows no report.

## Consequences

- Ingesting the same native log twice, on any machine and in any order, gives one copy of each event; two copies of a
  key merge by the rule of the event schema.
- A change of the meaning of a field needs a new field and a new schema version, never a new reading of the old field.
- An older ledger completes its reports with the exit code for incomplete figures while events of a newer version exist,
  so the person sees that an update is needed.
