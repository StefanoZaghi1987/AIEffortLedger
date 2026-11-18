# Data sources of agent tools — research of November 2026

Point-in-time research that supports ADR 0006. Facts change with tool releases; the adapters and their fixtures are
the current truth, this file is not updated.

## Claude Code

Source: official documentation at code.claude.com/docs (sessions, sub-agents, worktrees, hooks, monitoring-usage,
costs, claude-directory).

- Transcripts: `~/.claude/projects/<slug>/<session-id>.jsonl`; the slug is the launch folder with every
  non-alphanumeric character replaced by `-` (truncated with a hash above 200 characters). Subagents:
  `<session-id>/subagents/agent-<id>.jsonl`. A worktree session is filed under the worktree folder.
- Resume appends to the same file; fork (`/branch`, `--fork-session`) creates a new session with copied history.
- Retention: `cleanupPeriodDays`, default 30, minimum 1, cannot be disabled. Desktop and Cowork transcripts are kept
  unless `desktopSessionCleanupPeriodDays` is set.
- The documentation states that the transcript format is internal and changes between versions. Observed record
  types include `user`, `assistant`, `attachment`, `api-request`, `permission-mode`, `ai-title`, `last-prompt`; fields
  include `timestamp`, `sessionId`, `cwd`, `gitBranch`, `entrypoint`, `version`, `requestId`, `permissionDecision`,
  `message.model`, `message.usage`.
- Hooks (33 events) receive `session_id`, `prompt_id`, `transcript_path`, `cwd`, `permission_mode`; subagent hooks
  add `agent_id` and `agent_type`. Relevant events: `SessionStart`, `UserPromptSubmit`, `PermissionRequest`,
  `PermissionDenied`, `Stop`, `SubagentStart`, `SubagentStop`, `CwdChanged`, `WorktreeCreate`, `SessionEnd`.
- OpenTelemetry: metric `claude_code.active_time.total` with attribute `type` = `user` | `cli`; `token.usage`,
  `cost.usage`, `session.count`, `lines_of_code.count`, `commit.count`, `pull_request.count`; events `user_prompt`,
  `api_request` (tokens per cache lifetime, `cost_usd`), `tool_decision`, `tool_result`. Prompt text is redacted by
  default.
- Cloud sessions (claude.ai/code, scheduled cloud routines) have no local transcript.
- Organization data: Claude Code Analytics API (Console organizations, Admin API key, not on the Team plan); spend
  report CSV (Team plan); Enterprise Analytics API (Enterprise plan).

## Codex CLI

- State under `CODEX_HOME` (default `~/.codex`). Rollouts at `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`
  (third-party sources, not official documentation): envelope of timestamp, type, payload; types `session_meta`,
  `turn_context` (model, cwd), `response_item`, `event_msg` with a cumulative `token_count`.
- OpenTelemetry through `[otel]` in `config.toml`, off by default; events `user_prompt`, `api_request`,
  `tool_decision`, `tool_result`, and others. Retention of rollouts is not documented.

## Existing usage tools

- ccusage (MIT): tokens and cost per day, week, month, session, about 20 tools, JSON output.
- tokscale: tokens and cost, about 70 clients, LiteLLM prices, JSON output; licence to be checked.
- agentsview (MIT): 16 agents, tokens, cost, and session duration distributions, JSON output.
- None separates human time from agent time, splits time among projects, or takes manual entries.

## Method references

- METR randomized trial (July 2025): developers expected and afterwards believed a speed-up of about 20 %, but were
  measured 19 % slower; self-reported effort can be wrong in direction.
- Evidence-Based Scheduling (J. Spolsky, 2007): per-person history of estimate-to-actual ratios, Monte Carlo
  forecast of completion dates.
