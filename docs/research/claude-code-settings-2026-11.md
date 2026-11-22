# Claude Code settings — files, precedence, and the cleanup keys (2026-11)

Point-in-time note. It records the facts that [claude-code-adapter.md](../spec/claude-code-adapter.md) › Retention and
plan Task 24 rely on. Sources, read 2026-11-20; managed-settings.md again on 2026-11-22 for the system
directories and the drop-in files:

- https://code.claude.com/docs/en/settings.md
- https://code.claude.com/docs/en/settings-reference.md
- https://code.claude.com/docs/en/managed-settings.md
- https://code.claude.com/docs/en/claude-directory.md (› Cleaned up automatically)

## The settings files

Four files, and managed delivery beside them: the user `settings.json` under the home directory of Claude Code; the
shared project `.claude/settings.json`; the project local `.claude/settings.local.json`; the managed
`managed-settings.json` in a system directory of the operating system: `C:\Program Files\ClaudeCode\`
on Windows (the legacy `C:\ProgramData\ClaudeCode\` path is not read), `/Library/Application
Support/ClaudeCode/` on macOS, `/etc/claude-code/` on Linux and WSL. Precedence, highest first: managed, project
local, shared project, user. A `--settings` value given on the command line of one session ranks between managed and
project local.

## The cleanup keys

- `cleanupPeriodDays`: any file; a whole number, minimum 1 (`0` fails validation); default 30.
- `desktopSessionCleanupPeriodDays`: the user or managed file; a whole number, minimum 0; default 0, which sets no
  age limit. The key exists since Claude Code 2.1.248; earlier versions delete the transcripts below after
  `cleanupPeriodDays`.

A transcript of a session started or most recently continued in Claude Desktop or Cowork is deleted only when it is
older than both keys; the documentation's example: with `cleanupPeriodDays` at its default of 30, a
`desktopSessionCleanupPeriodDays` of 7 still keeps them 30 days. Which `cleanupPeriodDays` pairs with the desktop key
is not named by file: the value in effect under the precedence above. A managed `cleanupPeriodDays` does not pair:
managed settings (and the HIPAA configuration) make `cleanupPeriodDays` delete these transcripts alone, and the
desktop key is ignored.

## Managed sources this project does not read

The ledger reads only the `managed-settings.json` file of the three system directories. The documentation names these
further managed sources, which the ledger does not read: server-managed settings fetched from the claude.ai console
or a gateway; a macOS configuration profile (the `com.anthropic.claudecode` managed preferences domain); the Windows
registry (the `Settings` value under `HKLM\SOFTWARE\Policies\ClaudeCode`, and its user-writable `HKCU` counterpart);
the `managed-settings.d/` drop-in files beside the managed file, which the documentation merges with it (for
a single value, the later file's value replaces the earlier); the output of a `policyHelper` program that
managed settings name; parent settings that an embedding host passes. A
machine that deploys policy only through one of them holds no managed file, so the ledger reports no managed layer,
and its configuration shows the person configuration alone. The `--settings` value of a single session is likewise
not visible to the ledger.
