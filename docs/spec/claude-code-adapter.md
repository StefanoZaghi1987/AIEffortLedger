# Claude Code adapter

How the adapter `claude-code-jsonl` turns the native logs of Claude Code and Claude Desktop into events. Terms follow
[GLOSSARY.md](../../GLOSSARY.md); the rules that apply to every adapter are in [ingestion.md](ingestion.md) ›
Adapters, and the events in [event-schema.md](event-schema.md). The record types and keys below are the ones observed
in Claude Code 2.1 ([sources-2026-11.md](../research/sources-2026-11.md),
[prototype-findings-2026-11.md](../research/prototype-findings-2026-11.md)); the fixtures of the adapter test each of
them.

## Native logs

| Agent tool (`tool`) | Folder of native logs |
|---|---|
| `claude-code` | `projects/` in the configuration folder of Claude Code: the folder that the environment variable `CLAUDE_CONFIG_DIR` gives, otherwise `.claude` in the home folder of the person |
| `claude-desktop` | every `.claude/projects/` folder under `Claude/local-agent-mode-sessions/` in the application data folder of the operating system (`%APPDATA%` on Windows, `~/Library/Application Support` on macOS) |

Setup records in the machine configuration the `projects/` folder of Claude Code and the folder
`Claude/local-agent-mode-sessions/` of Claude Desktop when they exist on the machine, and the person can add more
([command-line.md](command-line.md) › Setup); a scheduled ingestion therefore does not depend on the environment
variables of the scheduler. For `claude-desktop`, every ingestion reads each `.claude/projects/` folder below the
recorded folder, so a session that starts after setup needs no new setup. Inside a folder of native logs,
`<folder>/<session>.jsonl` holds the records of the main agent of a session, and
`<folder>/<session>/subagents/agent-<agent>.jsonl` the records of one subagent. The name of `<folder>` comes from the
launch folder of the session and plays no part in identity; the `cwd` of the records does. The adapter reads all the
files of a session together ([event-schema.md](event-schema.md) › Keys and invariants).

Each line of a file is one JSON record with a `type`. A record that is not valid JSON produces a warning with the file
and the line number, and no event.

## Retention

The adapter declares the retention setting of each of its agent tools, which setup shows with its advice
([ingestion.md](ingestion.md) › Frequency):

| Agent tool | Setting | Default |
|---|---|---|
| `claude-code` | `cleanupPeriodDays` | 30 days |
| `claude-desktop` | `desktopSessionCleanupPeriodDays` | no age limit |

Both settings live in the settings files of Claude Code: `cleanupPeriodDays` in the user, project, local, and managed
settings file, `desktopSessionCleanupPeriodDays` in the user and managed settings file. `cleanupPeriodDays` has a
minimum of 1 day and cannot be off: the value `0` fails validation. The native logs of `claude-desktop` are kept past
`cleanupPeriodDays`; a transcript of Claude Desktop or Cowork is deleted only when it is older than both limits, and
when managed settings set `cleanupPeriodDays`, that period applies to those transcripts as well.

## Session fields

| Record key | Event field |
|---|---|
| `sessionId` | `session_id` |
| `version` | `source_format` |
| `cwd` | `cwd`, and `repo_hint` with `repo_basis` at ingestion ([ingestion.md](ingestion.md) › Repository identity) |
| `gitBranch` | `branch` |
| `entrypoint` | `invocation`: `cli` and `local-agent` are `interactive`, `sdk-cli`, `sdk-ts`, and `sdk-py` are `headless`; any other value is `unknown`, with a warning that names it; a record with no `entrypoint` gives `unknown`, without a warning |
| `agentId` | `agent_id`: present in the records of a subagent; a record without it belongs to the main agent |

The main agent has the session identifier as `agent_id`. A subagent has the `<agent>` part of the name of its file as
`agent_id`, the same value as the `agentId` of its records, and its records belong to its session. When the same record
is in the file of the main agent and in the file of a subagent, the copy in the file of the agent that its `agentId`
names, or of the main agent when it has none, gives the event.

The tool result of an `Agent` or `Task` call links the subagent to the call: its `toolUseResult.agentId` is the
`agent_id` of the subagent, whose `parent_agent_id` is the agent of the tool call. `subagent_mode` is `background` when
`toolUseResult.isAsync` is true or the tool input has `run_in_background` true, and `foreground` otherwise.

## Records and events

| Record | Event | Event key and fields |
|---|---|---|
| `assistant` whose `message.model` does not start with `<` | `agent_output` | native identifier `message.id`; `model`; `tokens` (see Tokens); `requests` and `price_factors` (see Requests and price factors); the `timestamp` of the last line of the response |
| each `tool_use` block of an `assistant` record | `tool_call` | native identifier `tool_call:` and the `id` of the block; `call_id` is that `id`; `tool_name`; `tool_category` (see Tool categories); size counters (see Size counters) |
| a `tool_use` block of `AskUserQuestion` or `ExitPlanMode` | also `decision_request` | native identifier `decision_request:question:` or `decision_request:plan_approval:` and the `id`; `decision_type` `question` or `plan_approval`; `call_id`; at the instant of the tool call |
| each `tool_result` block of a `user` record | `tool_result` | native identifier `tool_result:` and the `tool_use_id`; `call_id` is the `tool_use_id` |
| a `tool_result` of `AskUserQuestion` or `ExitPlanMode` | also `decision`, actor `human` | native identifier `decision:question:` or `decision:plan_approval:` and the `tool_use_id`; `call_id` |
| a `tool_result` in a `user` record whose `permissionDecision.source` starts with `user` (`user_temporary`, `user_permanent`, `user_reject`) | also `decision_request` at the instant of the tool call, and `decision`, actor `human`, at the instant of the result | native identifiers `decision_request:permission:` and `decision:permission:` with the `tool_use_id`; `decision_type` `permission`; `call_id` |
| in the file of the main agent, a `user` record without `tool_result` whose `origin.kind` is `human` | `prompt`, or `notification` with `input_origin` `scripted` when the session is not interactive and not of unknown invocation | native identifier `uuid` |
| a `user` record whose `origin.kind` is `task-notification`, `coordinator`, or `peer` | `notification` with `input_origin` `task_notification`, `coordinator`, or `peer` | native identifier `uuid` |
| `queue-operation` with `operation` `enqueue` whose `content` is a text that does not start with `<` | `queued_message` | no native identifier: the event identifier of [event-schema.md](event-schema.md) › Keys and invariants |
| in the file of a subagent, a `user` record without `tool_result` and without `origin.kind` `task-notification`, `coordinator`, or `peer` | `notification` with `input_origin` `parent`: the input that the starting agent gives to the subagent | native identifier `uuid` |
| a `user` record whose text, after leading spaces, starts with `[Request interrupted by user` | also `interruption`, actor `human`; the record gives no `prompt` | native identifier `uuid` |
| each `server_tool_use` or `mcp_tool_use` block of an `assistant` record: a tool that the provider runs inside the response | `tool_call` without a tool result, complete with its response | native identifier `tool_call:` and the `id` of the block; `tool_name` is its `name` |

A decision that `permissionDecision.source` `config` gives is a configured rule with no time and no human signal; it
produces no event. A `permissionDecision` on a `user` record with more than one `tool_result` block produces a warning
and no decision request or decision, because it does not name its tool use. An `origin.kind` or a
`permissionDecision.source` that this specification does not name produces a warning that names the value, and no
event from that key. An `assistant` record whose model starts with `<` is a message that Claude Code writes itself,
not a response of a model, and produces no event. Records with `isMeta` produce no event.

A `user` record of a version that has no `origin` is a prompt when its text, after leading spaces, does not start with
one of the tags `<task-notification`, `<local-command-stdout`, `<local-command-caveat`, or `<system-reminder`, or with
`[Request interrupted by user`; a `<task-notification` text is a notification with `input_origin` `task_notification`,
and the other tags produce no event. The adapter reads the text only for these tests and drops it.

The record types `system`, `attachment`, `api-request`, `api-request-shape`, `api-request-blob`, `permission-mode`,
`mode`, `atis-latch`, `file-history-snapshot`, `file-history-delta`, `tools-used`, `cost-state`, `agent-name`,
`session-owner`, `bridge-session`, `pr-link`, `ai-title`, `custom-title`, and `last-prompt` produce no event; `ai-title`
and `custom-title` give `session_title` only when the person configuration allows titles (Phase 2). A record type that
the table and this list do not name produces one warning for each type and format version.

The native log has no record for the start or the end of a session, so the adapter writes no `session_start` or
`session_end`; a turn that the native log leaves open ends by the stale limit ([metrics.md](metrics.md) › Agent time).

## Forks

A record whose `uuid` is in the files of two sessions, or whose `uuid` the local index holds for another session, is a
copy that a fork made; a fork of a session that no longer changes is therefore found when only the fork is read. The
adapter applies the rule of forked sessions of [event-schema.md](event-schema.md) › Keys and invariants, and writes
`forked_from` on the events of the fork.

## Complete events

The rule of [ingestion.md](ingestion.md) › Adapters applies with these conditions:

- an `agent_output` is complete when the file of its agent holds a later record that is not a line of the same
  response;
- a `tool_call`, and the `decision_request` of a permission, are complete when the tool result exists; a `tool_call`
  of a `server_tool_use` or `mcp_tool_use` block is complete when its `agent_output` is complete, because the tool runs
  inside the response;
- every other event is complete when its record exists.

## Tokens

The `message.usage` of a response gives the token counts; each category takes the largest value among the lines of
the response, and a category whose key the response does not give is absent, never zero:

| Token category | Usage key |
|---|---|
| `input` | `input_tokens` |
| `output` | `output_tokens` |
| `cache_read` | `cache_read_input_tokens` |
| `cache_write_1h` | `cache_creation.ephemeral_1h_input_tokens` |
| `cache_write_5m` | `cache_creation.ephemeral_5m_input_tokens`, or, without `cache_creation`, `cache_creation_input_tokens` minus `cache_write_1h`, with an absent `cache_write_1h` as 0 |

## Requests and price factors

The same `message.usage` gives the request counts and the price factors of the response (ADR 0024). Each request count
takes the largest value among the lines of the response, and a count of zero is not written; each price factor takes the
value of the last line of the response that gives it as text:

| Field | Name | Usage key |
|---|---|---|
| `requests` | `web_search` | `server_tool_use.web_search_requests` |
| `requests` | `web_fetch` | `server_tool_use.web_fetch_requests` |
| `price_factors` | `speed` | `speed` |
| `price_factors` | `service_tier` | `service_tier` |
| `price_factors` | `inference_geo` | `inference_geo` |

## Tool categories

Every tool name that the table does not list, such as the name of a tool of an MCP server, is `other`.

| Tool category | Native tool names |
|---|---|
| `edit` | `Edit`, `Write`, `MultiEdit`, `NotebookEdit` |
| `execute` | `Bash`, `PowerShell` |
| `read` | `Read` |
| `search` | `Grep`, `Glob` |
| `web` | `WebFetch`, `WebSearch` |
| `delegate` | `Agent`, `Task`, `SendMessage`, `SubagentHandback`, `ListAgents` |
| `decide` | `AskUserQuestion`, `ExitPlanMode` |
| `other` | `ToolSearch`, `Skill`, `TodoWrite`, `TaskCreate`, `TaskUpdate`, `TaskStop`, `Monitor`, `ListMcpResourcesTool` |

A tool call of `Agent` or `Task` is a wait of the calling agent for its subagent, from the tool call to its tool result:
a background subagent returns its tool result at once, so its wait is near zero ([metrics.md](metrics.md) › Agent time).

## Size counters

The size counters of a tool call of category `edit` come from the `structuredPatch` in the `toolUseResult` of the
`user` record that holds its tool result, with `size_basis` `patch`; the `type` in that `toolUseResult` of a `Write`
(`create` or `update`) tells whether the file was new. A `structuredPatch` without hunks, and a `toolUseResult` that is
a text or null, give no patch. Without a patch the counters come from the input, with `size_basis` `input`:

| Tool | Lines added | Lines removed | File |
|---|---|---|---|
| `Edit` | `new_string` | `old_string` | `file_path` |
| `MultiEdit` | `new_string` of each item of `edits` | `old_string` of each item of `edits` | `file_path` |
| `Write` | `content` | absent, or 0 when the result says `create` | `file_path` |
| `NotebookEdit` | `new_source` | absent | `notebook_path` |

A result with `is_error` gets no size counters, because the edit changed no file. The file extension follows
[event-schema.md](event-schema.md) › Keys and invariants.

## To be confirmed

- Whether every interruption writes a `user` record that starts with `[Request interrupted by user`: the samples show
  it, and a tool result can also carry `toolDenialKind` `interrupted`. To confirm with fixtures from more samples,
  before the end of Phase 1.
- The instant of a permission decision: the native log gives only the tool result, so blocked time of a permission
  includes the run time of the tool after the approval. Hooks give the instant (Phase 3).
- How a subagent links to the tool call that started it when the `toolUseResult` of the call is a text without
  `agentId`, and how nested subagents link. To specify with a real sample, before the end of Phase 1.
- The input keys of `MultiEdit` and `NotebookEdit` (`edits`, `new_source`, `notebook_path`): no sample of Claude
  Code 2.1 holds these tools. To confirm with a real sample, before the end of Phase 1.
- What the native log shows about the provider (`provider_hint`) when Claude Code uses the endpoint of another
  provider. To specify with a real sample, at the start of Phase 2.
