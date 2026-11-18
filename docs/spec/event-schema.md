# Event schema

The normalized event is the contract between adapters and the metrics engine (ADR 0002). Adapters write events; the
metrics engine reads only events, never native source formats. Terms follow [GLOSSARY.md](../../GLOSSARY.md).

## Kinds

| Kind | Actor | Meaning |
|---|---|---|
| `session_start`, `session_end` | system | Limits of a session |
| `prompt` | human | A prompt of the person to the main agent of an interactive session |
| `queued_message` | human | A message typed while an agent works |
| `interruption` | human | The person stops an agent turn |
| `notification` | system | A non-human input to an agent: task notification, coordinator or peer message, scheduled trigger, or a prompt of a session that is not interactive |
| `agent_output` | agent | One response of a model; carries token usage |
| `tool_call` | agent | An agent asks to run a tool; carries the tool name, the tool category, and size counters |
| `tool_result` | system | The result of a tool returns to the agent |
| `decision_request` | agent | A permission request, a question to the person, or a plan approval |
| `decision` | human or system | The answer to a decision request; `human` when the person answered, `system` for a configured rule |
| `manual_entry` | human | An interval of declared human time |
| `timesheet_entry` | human | Declared human time of one day and one project (ADR 0011) |
| `declared_usage` | human | Declared agent time, token usage, or cost of work that no source recorded |
| `annotation` | human | Labels on a session or a time interval; adds no time |
| `retraction` | human | Cancels an earlier event by key |
| `purge` | human | The keys that a purge removed, its reason, and its time (ADR 0008) |

Turns, intervals, activity classes, attributions, projects, providers, and costs are not events: the metrics engine
derives them.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Version of this schema used to write the event |
| `source` | yes | Stable adapter identifier, for example `claude-code-jsonl`; part of the key |
| `source_format` | for events from native sources | Native format version that the adapter recognized, for example the version of the agent tool; not part of the key |
| `native_id` | when the source gives one | Identifier of the event in the source, unique across sessions of that source |
| `session_id` | for events of a session | Session identifier given by the source |
| `event_uid` | yes | Identifier of the event within its session, stable across re-ingestion |
| `timestamp` | yes | UTC instant of the event; for an `agent_output` written on several lines, the instant of the last line |
| `ingested_at` | yes | UTC instant at which the event first entered a segment |
| `actor` | yes | `human`, `agent`, or `system` |
| `kind` | yes | One of the kinds above |
| `invocation` | for events of a session | `interactive`, `headless`, `scheduled`, `orchestrated`, or `unknown`, as the source shows it at the event; a resumed session can change it |
| `parent_session_id` | when known | Session that started this session, such as the session of a coordinator or an orchestrator |
| `agent_id` | for agent events and tool results | Agent that produced or receives the event; equals the session for the main agent |
| `parent_agent_id` | for subagents | Agent that started the subagent |
| `subagent_mode` | for subagents | `foreground` or `background` |
| `call_id` | for tool and decision events | Links `tool_call`, `decision_request`, `decision`, and `tool_result` of one tool use |
| `tool_name` | for `tool_call` | Native name of the tool, as given by the source |
| `tool_category` | for `tool_call` | `edit`, `execute`, `read`, `search`, `web`, `delegate`, `decide`, or `other` |
| `lines_added`, `lines_removed`, `file_ext` | for `tool_call` of category `edit`, when the input gives them | Size counters (ADR 0012) |
| `decision_type` | for decision events | `permission`, `question`, or `plan_approval` |
| `input_origin` | for notifications | `task_notification`, `coordinator`, `peer`, `scheduled`, or `scripted` |
| `forked_from` | for forked sessions | Session the history was copied from, and the instant of the fork |
| `machine` | yes | Machine on which the work happened |
| `tool` | yes | Agent tool, for example `claude-code`, `claude-desktop`, `codex` |
| `provider_hint` | for `agent_output` when the source shows it | What the source shows about the provider, such as the host of the endpoint; the provider is resolved at report time |
| `model` | for `agent_output`; optional for `declared_usage` | Model identifier as given by the source or by the person |
| `tokens` | for `agent_output`; optional for `declared_usage` | Token counts per category; the category set is open (see below) |
| `cwd` | when known | Folder of the session when the event occurred |
| `repo_hint` | when known | Repository identity observed at ingestion (ADR 0004, ADR 0009) |
| `branch` | when known | Git branch at the event |
| `start`, `end` | for manual entries and interval annotations; optional for `declared_usage` | UTC limits of the declared interval |
| `day` | for timesheet entries | Local calendar date of the person to which the entry applies |
| `duration` | for timesheet entries; optional for `declared_usage` | Declared human time, or declared agent time for declared usage |
| `cost`, `currency` | optional for `declared_usage` | Actual cost that the person declares; computed costs are never stored (ADR 0007) |
| `manual_mode` | for manual entries | `additional` or `overlapping` |
| `project`, `work_item` | for manual entries, timesheet entries, declared usage, and annotations | Attribution declared by the person |
| `note` | for manual entries, timesheet entries, and declared usage | Short text written by the person for the person |
| `retracts` | for retractions | Key of the cancelled event |
| `purged_keys`, `purge_reason` | for purges | Keys removed and the reason: `content` or `forget` |
| `labels` | no | Attribution hints from an allow-list of keys defined in the configuration |
| `session_title` | no | Title of the session, only when the configuration allows titles |

The pseudonym of the person is metadata of the store, not a field of each event (ADR 0010); a team export adds it.

No field holds the text of prompts, responses, tool input, or code, or the paths of files in tool input (ADR 0003,
ADR 0012). Adapters drop that text while they read.

Token categories start with `input`, `output`, `cache_write_5m`, `cache_write_1h`, and `cache_read`. An adapter adds a
category, such as reasoning output, when a provider reports it separately; a price table that has no price for a
category makes the report show that cost as unknown, never as zero. Cumulative counters of a source become per-event
counts in the adapter.

## Keys and invariants

- The key of an event is (`source`, `native_id`) when the source gives a native identifier, otherwise (`source`,
  `session_id`, `event_uid`). Events that a person creates get a random `event_uid` at creation. Ingesting an event
  twice leaves one event, also after an adapter starts to recognize a new `source_format`.
- When two copies of an event with the same key differ in a field other than the key, the copy with the earliest
  `ingested_at` wins, and equal instants resolve by the order of the names of the segments that hold the copies.
  Segments of several machines therefore merge to the same result in any order.
- A stored event does not change. A correction of an adapter reaches events already stored only through a purge and a
  new ingestion.
- Two sources that record the same session, such as a native log and a hook, never add up: for each session and each
  kind, reports read one source.
- An adapter writes a prompt as `prompt` with actor `human` only when the session is interactive or of unknown
  invocation and the source shows a human origin; otherwise it writes a `notification` with `input_origin` `scripted`.
- In a forked session, events up to the fork instant of `forked_from` are copies: their native identifiers match the
  original, they keep the `session_id` of the original, and events without a native identifier are ignored up to that
  instant.
- One response that the source writes on several lines becomes one `agent_output` with the largest token counts.
- Size counters are computed from the tool input before its text is dropped: lines of the new text and lines of the
  replaced text. They measure size, not a diff.
- Events are append-only. A wrong event is cancelled by a retraction; attribution changes by annotation; only a purge
  removes events (ADR 0008). Ingestion and merge never add an event whose key a purge lists.

## To be confirmed

- How each adapter derives `event_uid` for events without a native identifier.
- How the Claude Code adapter recognizes a forked session and its fork instant; no fork exists yet in the measured
  data, and a fixture with a real fork is needed.
- How the `machine` identifier is derived so that it is stable and reveals no personal data.
- Whether a purge with reason `content` lets a corrected adapter ingest the same keys again without the removed text,
  while a purge with reason `forget` blocks them for good.
- The mapping of native tool names to tool categories for each adapter, and how size counters are derived for each
  edit tool (whole-file write, multiple edits, notebook edit, patch formats of other agent tools).
- Which source has precedence for each kind when two sources record the same session (for example hooks for human
  signals, native logs for token usage), and how the ledger recognizes that two sources record the same session.
- Which line of a response gives the timestamp of an `agent_output`: this schema says the last line, the prototype uses
  the first; the first adapter confirms which instant matches the end of the response.
