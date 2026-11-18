---
status: accepted
date: 2026-11-18
---

# Native logs are the baseline source, hooks the preferred future source, telemetry optional; adapters are our own

Three kinds of source exist with different guarantees. Native logs (for example Claude Code and Codex JSONL
transcripts) cover the past within their retention, but their format is undocumented and changes between versions.
Hooks give documented, precise human signals, but only from installation onwards. OpenTelemetry is documented and
rich, but needs a running collector and records nothing retroactively. The ledger reads native logs for history and
as a baseline, prefers hooks for new data, and accepts telemetry as an optional source. Each format has its own
adapter with test fixtures; an unknown format produces a warning, never silently wrong data.

## Considered Options

- **Consume the JSON output of existing usage tools** (ccusage, tokscale, agentsview): rejected as the main source;
  their output is aggregated per day or per session and has lost the per-event timestamps that human time and agent
  time need. They remain useful as a cross-check of token totals and as a fallback for tools without an adapter.
- **Telemetry only**: rejected as the main source; no history, an always-on collector, and centralized data.

## Consequences

- Adapter maintenance is a permanent cost: each tool release can change a native format.
- Sessions that leave no local data (cloud sessions, web chat) need a provider import or a manual entry.
