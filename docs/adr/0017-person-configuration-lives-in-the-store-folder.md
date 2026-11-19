---
status: accepted
date: 2026-11-18
---

# The person configuration lives in the store folder

The ledger needs values that no source gives: the time-zone history, identity rules, category rules, the allow-list
of label keys, the consent for session titles, the defaults of report parameters, and later hourly rates and cost
sources. The person owns these facts, and the same facts apply on every machine of the person. The data of the person
already travels in the store folder, and the store settings are metadata of that folder (ADR 0010). Therefore the
person configuration is one file in the store folder: every machine that uses the store reads the same file, and a
report depends only on the store folder, the version of the ledger, and the report parameters. Only the facts of one
machine, its machine identifier and the location of the store, stay in the machine configuration, which the ledger
must read before it can find the store.

## Considered Options

- **One file in the user configuration folder of each machine**: no conflict between machines, but each machine needs
  its own copy, a change made on one machine does not reach the others, and one store can give two different reports
  on two machines.
- **Configuration changes as events in the store**: the segments of each machine remove every conflict and keep the
  history of each change, but the person cannot edit the configuration by hand or write comments in it, every change
  needs a command, and settings mix with the observations that the store keeps (ADR 0002).

## Consequences

- With one machine and the store in its default folder, the person configuration is one file next to the data, as a
  file per machine would be.
- When two machines change the file before a file-sync service synchronizes them, the service keeps a conflict copy;
  the ledger reads only the file with the defined name, and the person merges the copy by hand.
- When the store is in a repository (ADR 0003), the person configuration is in that repository too.
- A move of the store moves the person configuration with it.
