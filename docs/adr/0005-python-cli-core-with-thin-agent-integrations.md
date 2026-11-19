---
status: superseded in part by 0022
date: 2026-11-18
---

# A Python command-line core holds all logic; agent integrations are thin

The ledger is a command-line program in Python whose only dependency is the time-zone database `tzdata`, needed on
Windows where the operating system does not provide one to `zoneinfo`; everything else comes from the standard library
(`sqlite3`, `json`, `tomllib`, `zoneinfo`). It installs with `uv tool install` or `pipx` on Windows, Linux, and macOS. Skills, hooks,
and agent instructions for Claude Code, Codex, or other tools only call the command line and handle the conversation
(asking for undeclared time, labelling work items, explaining a report). The core must run without any agent: from a
terminal, a scheduled task, or a hook.

## Considered Options

- **Logic inside skills or prompts**: fast to start, but results are not repeatable, cannot be tested, and work in one
  agent tool only.
- **TypeScript / Node**: same ecosystem as existing usage tools, but Node must be present and data analysis is less
  natural.
- **Go or Rust single binary**: no interpreter needed, but more costly to develop and change. The command line and its
  JSON output are a stable contract, so a rewrite stays possible if distribution becomes the main problem.

## Consequences

- Python 3.11 or later is required on the machine, because the standard library reads TOML configuration
  (`tomllib`) from that version; `uv` can install it.
