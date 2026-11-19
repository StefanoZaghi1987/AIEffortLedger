---
status: accepted
date: 2026-11-19
---

# A missing folder resolves through its nearest existing parent, and the event says so

Ingestion records the repository identity of each event as an observation of its folder (ADR 0004). An agent tool can
remove a folder when a session ends, for example a worktree inside its repository, before any ingestion reads it; the
events of that folder then have no repository identity and are unattributed, although the repository that held the
folder still exists. Therefore, when the folder of an event no longer exists, ingestion starts the usual search for
`.git` at the nearest existing parent folder. A repository identity found this way is inferred, not observed: the event
records it in `repo_hint` and records `repo_basis` = `inferred`, while an identity read from the folder itself has
`repo_basis` = `observed`. The search never reaches the home folder of the person or the root of a drive, so a
repository there, such as one that keeps the settings files of the person, is never inferred. When the search finds no
repository, the event has no repository identity. This supersedes ADR 0004 where the hint is always an observation of
the folder of the event.

## Considered Options

- **No inference**: always safe, but the most common case, a removed worktree inside its repository, stays
  unattributed until the person writes an identity rule.
- **Inference only for the folder layout of one agent tool**, such as `.claude/worktrees/`: correct for that layout,
  but it depends on a folder name, does not cover a removed subfolder of a repository, and does not apply to other
  agent tools.

## Consequences

- A separate repository that was inside another repository and no longer exists, such as a removed clone in a
  `vendor` folder, resolves to the outer repository; the event says that the identity is inferred, reports show the
  inferred share, and an identity rule corrects it at report time (ADR 0009).
- An inferred identity is a hint like an observed one: the first ingestion of an event sets it for good (ADR 0004),
  and attribution still happens at report time (ADR 0002).
- An event whose folder exists never has an inferred identity.
