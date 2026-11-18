---
status: superseded in part by 0009
date: 2026-11-18
---

# A project is identified by its repository, not by the launch folder

Agent tools file their logs by the folder from which they were started, so one repository appears under several
names: a subfolder, a second clone, or a worktree each get their own log folder (for example, a launch from `D:\GammaBot` and one
from `D:\GammaBot\GammaBot` produce two log folders). The ledger identifies a project by the normalized URL of its remote, or by
the hash of its root commit when no remote exists, and resolves worktrees to their repository through the common git
directory. Folders without git map to projects through explicit rules in the configuration. The branch is a hint for
the work item, not its definition.

## Consequences

- An adapter records the folder and the branch of each event; resolution to a project happens at report time and can
  use rules added later.
- A folder that no longer exists on disk keeps the identity that was resolved while it existed; the store records the
  repository identity at ingestion as a hint for this case. The hint is an observation of the folder at that moment,
  not an attribution: attribution still happens at report time (ADR 0002), and the first ingestion of an event sets the
  hint for good.
- The ledger reads the repository files (`.git`, `commondir`, `config`) directly and never runs git inside a folder
  taken from a source, because the configuration of an unknown repository can make git execute code.
