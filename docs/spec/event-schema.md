# Event schema

The normalized event is the contract between adapters and the metrics engine (ADR 0002). Adapters write events; the
metrics engine reads only events, never native source formats. Terms follow [GLOSSARY.md](../../GLOSSARY.md).

## Kinds

| Kind | Actor | Meaning |
|---|---|---|
| `session_start`, `session_end` | system | Limits of a session |
| `prompt` | human | A prompt of the person to the main agent |
| `queued_message` | human | A message typed while an agent works |
| `interruption` | human | The person stops an agent turn |
| `notification` | system | A non-human input to an agent: task notification, coordinator or peer message, scheduled trigger |
| `agent_output` | agent | One response of a model; the only kind that carries token usage |
| `tool_call` | agent | An agent asks to run a tool |
| `tool_result` | system | The result of a tool returns to the agent |
| `decision_request` | agent | A permission request, a question to the person, or a plan approval |
| `decision` | human or system | The answer to a decision request; `human` when the person answered, `system` for a configured rule |
| `manual_entry` | human | An interval of declared human time |
| `annotation` | human | Labels on a session or a time interval; adds no time |
| `retraction` | human | Cancels an earlier event by key |

Turns, intervals, activity classes, attributions, and costs are not events: the metrics engine derives them.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Version of this schema used to write the event |
| `source` | yes | Adapter identifier and native format version, for example `claude-code-jsonl` |
| `native_id` | when the source gives one | Identifier of the event in the source, unique across sessions of that source |
| `session_id` | yes, except manual entries, annotations, retractions | Session identifier given by the source |
| `event_uid` | yes | Identifier of the event within its session, stable across re-ingestion |
| `timestamp` | yes | UTC instant of the event; for an `agent_output` written on several lines, the instant of the last line |
| `actor` | yes | `human`, `agent`, or `system` |
| `kind` | yes | One of the kinds above |
| `agent_id` | for agent events and tool results | Agent that produced or receives the event; equals the session for the main agent |
| `parent_agent_id` | for subagents | Agent that started the subagent |
| `subagent_mode` | for subagents | `foreground` or `background` |
| `call_id` | for tool and decision events | Links `tool_call`, `decision_request`, `decision`, and `tool_result` of one tool use |
| `decision_type` | for decision events | `permission`, `question`, or `plan_approval` |
| `input_origin` | for notifications | `task_notification`, `coordinator`, `peer`, or `scheduled` |
| `forked_from` | for forked sessions | Session the history was copied from, and the instant of the fork |
| `person` | yes | Pseudonym of the person, from the configuration |
| `machine` | yes | Machine on which the work happened |
| `tool` | yes | Agent tool, for example `claude-code`, `claude-desktop`, `codex` |
| `provider` | for `agent_output` | Provider that served the model, resolved at ingestion |
| `model` | for `agent_output` | Model identifier as given by the source |
| `tokens` | for `agent_output` | Token counts per category; the category set is open (see below) |
| `cwd` | when known | Folder of the session when the event occurred |
| `repo_hint` | when known | Repository identity observed at the first ingestion (ADR 0004) |
| `branch` | when known | Git branch at the event |
| `start`, `end` | for manual entries and interval annotations | UTC limits of the declared interval |
| `manual_mode` | for manual entries | `additional` or `overlapping` |
| `project`, `work_item` | for manual entries and annotations | Attribution declared by the person |
| `note` | for manual entries | Short text written by the person for the person |
| `retracts` | for retractions | Key of the cancelled event |
| `labels` | no | Attribution hints from an allow-list of keys defined in the configuration |
| `session_title` | no | Title of the session, only when the configuration allows titles |

No field holds the text of prompts, responses, tool input, or code (ADR 0003). Adapters drop that text while they read.

Token categories start with `input`, `output`, `cache_write_5m`, `cache_write_1h`, and `cache_read`. An adapter adds a
category, such as reasoning output, when a provider reports it separately; a price table that has no price for a
category makes the report show that cost as unknown, never as zero. Cumulative counters of a source become per-event
counts in the adapter.

## Keys and invariants

- The key of an event is (`source`, `native_id`) when the source gives a native identifier, otherwise (`source`,
  `session_id`, `event_uid`). Ingesting an event twice leaves one event.
- In a forked session, events up to the fork instant of `forked_from` are copies: their native identifiers match the
  original, and events without a native identifier are ignored up to that instant.
- One response that the source writes on several lines becomes one `agent_output` with the largest token counts.
- Events are append-only. A wrong event is cancelled by a retraction; attribution changes by annotation; only a purge
  removes events (ADR 0008).
- The first ingestion of an event sets `cwd`, `repo_hint`, and `machine`; later ingestions of the same key do not
  change them. Stores from several machines therefore merge by key to the same result in any order.

## To be confirmed

- How each adapter derives `event_uid` for events without a native identifier.
- How the Claude Code adapter recognizes a forked session and its fork instant; no fork exists yet in the measured
  data, and a fixture with a real fork is needed.
- How the `machine` identifier is derived so that it is stable and reveals no personal data.
