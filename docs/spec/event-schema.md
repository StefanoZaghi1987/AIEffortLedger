# Event schema

The normalized event is the contract between adapters and the metrics engine (ADR 0002). Adapters write events; the
metrics engine reads only events, never native source formats. Terms follow [GLOSSARY.md](../../GLOSSARY.md).

## Kinds

| Kind | Actor | Meaning |
|---|---|---|
| `session_start`, `session_end` | system | Limits of a session |
| `prompt` | human | A prompt of the person to the main agent of a session that is interactive or of unknown invocation |
| `queued_message` | human | A message typed while an agent works |
| `interruption` | human | The person stops an agent turn |
| `notification` | system | A non-human input to an agent: task notification, coordinator or peer message, scheduled trigger, or a prompt of a session of headless, scheduled, or orchestrated invocation |
| `agent_output` | agent | One response of a model; carries token usage |
| `tool_call` | agent | An agent asks to run a tool; carries the tool name, the tool category, and size counters |
| `tool_result` | system | The result of a tool returns to the agent |
| `decision_request` | agent | A permission request, a question to the person, or a plan approval |
| `decision` | human or system | The answer to a decision request; `human` when the person answered, `system` for a configured rule |
| `manual_entry` | human | An interval of declared human time |
| `timesheet_entry` | human | Declared human time of one day for one project, or for the unattributed time of the day, with an optional work item (ADR 0011, ADR 0014) |
| `declared_usage` | human | Declared agent time, token usage, or cost of work that no source recorded |
| `annotation` | human | Labels on a session or a time interval; adds no time |
| `retraction` | human | Cancels an earlier event by key |
| `purge` | human | The keys that a purge removed, its reason, its time, and an optional corrected version (ADR 0008, ADR 0015) |

Turns, intervals, activity classes, attributions, projects, providers, and costs are not events: the metrics engine
derives them.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Version of this schema used to write the event, a whole number; the first release writes `1` |
| `source` | yes | Stable identifier of the writer: the adapter, for example `claude-code-jsonl`, or `ledger` for events that a command writes; part of the key |
| `source_format` | for events from native sources | Native format version that the adapter recognized, for example the version of the agent tool; not part of the key |
| `native_id` | when the source gives one | Identifier of the event in the source, unique across sessions of that source |
| `session_id` | for events of a session | Session identifier given by the source |
| `event_uid` | yes | Identifier of the event within its session, stable across re-ingestion |
| `timestamp` | yes | UTC instant of the event; for an `agent_output` written on several lines, the instant of the last line |
| `ingested_at` | yes | UTC instant at which the event first entered a segment |
| `writer_version` | yes | Version of the ledger program that wrote the event, compared number by number (`1.10.0` is newer than `1.9.0`); not part of the key (ADR 0015) |
| `actor` | yes | `human`, `agent`, or `system` |
| `kind` | yes | One of the kinds above |
| `invocation` | for events of a session | `interactive`, `headless`, `scheduled`, `orchestrated`, or `unknown`, as the source shows it at the event; a resumed session can change it |
| `parent_session_id` | when known | Session that started this session, such as the session of a coordinator or an orchestrator |
| `agent_id` | for agent events and tool results | Agent that produced or receives the event; equals the session for the main agent |
| `parent_agent_id` | for subagents | Agent that started the subagent |
| `subagent_mode` | for subagents | `foreground` or `background` |
| `call_id` | for tool and decision events | Links `tool_call`, `decision_request`, `decision`, and `tool_result` of one tool use |
| `tool_name` | for `tool_call` | Native name of the tool, as given by the source |
| `tool_category` | for `tool_call` | `edit`, `execute`, `read`, `search`, `web`, `delegate`, `decide`, or `other`, from the table of the adapter; category rules can replace it at report time |
| `lines_added`, `lines_removed`, `file_ext` | for `tool_call` of category `edit` with a successful result, when the source gives them | Size counters (ADR 0012, ADR 0016); a value that the source does not give is absent, never zero |
| `size_basis` | with size counters | `patch` when the counters come from a patch, `input` when they come from the tool input (ADR 0016) |
| `decision_type` | for decision events | `permission`, `question`, or `plan_approval` |
| `input_origin` | for notifications | `task_notification`, `coordinator`, `peer`, `scheduled`, or `scripted` |
| `forked_from` | for forked sessions | Session the history was copied from, and the instant of the fork |
| `machine` | yes | Random identifier of the machine on which the work happened, or, for an event that a command writes, of the machine that wrote it ([ingestion.md](ingestion.md)) |
| `tool` | for events of a session and for declared usage | Agent tool, for example `claude-code`, `claude-desktop`, `codex` |
| `provider_hint` | for `agent_output` when the source shows it | What the source shows about the provider, such as the host of the endpoint; the provider is resolved at report time |
| `model` | for `agent_output`; optional for `declared_usage` | Model identifier as given by the source or by the person |
| `tokens` | for `agent_output`; optional for `declared_usage` | Token counts per category; the category set is open (see below) |
| `cwd` | when known | Folder of the session when the event occurred |
| `repo_hint` | when known | Repository identity observed or inferred at ingestion (ADR 0004, ADR 0009, ADR 0018) |
| `repo_basis` | with `repo_hint` | `observed` when read from the folder of the event, `inferred` when read from its nearest existing parent folder because the folder no longer exists (ADR 0018) |
| `branch` | when known | Git branch at the event |
| `start`, `end` | for manual entries and interval annotations; optional for `declared_usage` | UTC limits of the declared interval |
| `day` | for timesheet entries | Date of the local day of the person to which the entry applies ([metrics.md](metrics.md)) |
| `duration` | for timesheet entries; optional for `declared_usage` | Declared human time, or declared agent time for declared usage |
| `cost`, `currency` | optional for `declared_usage` | Actual cost that the person declares; computed costs are never stored (ADR 0007) |
| `manual_mode` | for manual entries | `additional` or `overlapping` |
| `project`, `work_item` | for manual entries, declared usage, and annotations; optional for timesheet entries | Attribution declared by the person: a project identifier (ADR 0019) and a work item; a timesheet entry without a project declares unattributed time |
| `note` | for manual entries, timesheet entries, and declared usage | Short text written by the person for the person |
| `retracts` | for retractions | Key of the cancelled event |
| `purged_keys`, `purge_reason` | for purges | Keys removed and the reason, a label for the person: `content`, `correction`, or `forget` |
| `corrected_version` | optional for purges, never with reason `forget` | Writer version from which new copies of the purged keys are accepted (ADR 0015) |
| `labels` | no | Attribution hints from the allow-list of label keys in the person configuration |
| `session_title` | no | Title of the session, only when the person configuration allows titles |

The pseudonym of the person is in the person configuration ([configuration.md](configuration.md)), not a field of each
event; a team export adds it.

No field holds the text of prompts, responses, tool input, or code, or the paths of files in tool input (ADR 0003,
ADR 0012). Adapters drop that text while they read.

Token categories start with `input`, `output`, `cache_write_5m`, `cache_write_1h`, and `cache_read`. An adapter adds a
category, such as reasoning output, when a provider reports it separately; a price table that has no price for a
category makes the report show that cost as unknown, never as zero. Cumulative counters of a source become per-event
counts in the adapter.

## Keys and invariants

- The key of an event is (`source`, `native_id`) when the source gives a native identifier, otherwise (`source`,
  `session_id`, `event_uid`). Events that a command writes have the source `ledger` and no session: their key is
  (`ledger`, `event_uid`), with a random `event_uid` made at creation. Ingesting an event twice leaves one event, also
  after an adapter starts to recognize a new `source_format`.
- The identity of an event comes only from facts that the source gives about identity, never from the place of a record
  in a file or from its content. An event takes the identifier of the record it comes from; when one record gives more
  than one event, the kind of the event goes before the identifier, for example `decision:` and the identifier of the
  tool use. An event from a record without an identifier gets as `event_uid` its kind, its timestamp, and its position
  among the records of its session with the same kind and timestamp.
- When a source writes one record more than once, for example in the file of a session and in the file of one of its
  subagents, the adapter writes one event, from the copy in the file of the agent that the record names, and warns
  when the copies differ in another field. The adapter therefore reads all the files of a session together.
- When two copies of an event with the same key differ in a field other than the key, the copy with the earliest
  `ingested_at` wins, and equal instants resolve by the order of the names of the segments that hold the copies.
  Segments of several machines therefore merge to the same result in any order.
- A stored event does not change. A correction of an adapter reaches events already stored only through a purge that
  names the corrected version and a new ingestion (ADR 0015).
- Two sources record the same session when they give the same `tool` and the same `session_id`. Such sources, such as
  a native log and a hook, never add up: for each session and each kind, reports read one source.
- An adapter writes a prompt as `prompt` with actor `human` only when the session is interactive or of unknown
  invocation and the source shows a human origin; otherwise it writes a `notification` with `input_origin` `scripted`.
- A forked session starts with copies of records of its original, with the same native identifiers, so a copy and
  its original are one event. A session cannot have records of its own from before it existed: the original is the
  session that holds records of its own, without a copy in the other session, inside the time range of the shared
  records, and the shared events belong to it. The fork instant is the timestamp of the last shared record, and the
  events of the fork carry `forked_from`. When both sessions or neither hold records of their own in that range, the
  session whose identifier sorts first is the original, and the adapter warns. An event already in the store keeps its
  session.
- One response that the source writes on several lines becomes one `agent_output` with the largest token counts.
- Size counters are computed before the text is dropped (ADR 0016). When the source gives a patch of the change, in the
  tool result or in the tool input, they are the added and removed lines of the patch, with `size_basis` `patch`.
  Otherwise they are the lines of the new text and of the replaced text in the tool input, with `size_basis` `input`; a
  whole-file write that the source reports as a new file has no removed lines, and one that the source does not report
  as new has lines removed absent. A tool call without a result, or whose result the source marks as an error, gets no
  size counters. The lines of a text are its line breaks, plus one when the text does not end with a line break; the
  file extension is the part of the file name after its last dot, in lower case.
- The tool category comes from a table of the adapter; an unknown tool name gets `other`, and ingestion warns about it
  (ADR 0012, [ingestion.md](ingestion.md)). Category rules ([configuration.md](configuration.md)), matched on the tool
  name, replace the stored category at report time, so a tool that the adapter cannot know, such as a tool of an MCP
  server, can count as `edit` or `search`.
- Events are append-only. A wrong event is cancelled by a retraction; attribution changes by annotation; only a purge
  removes events (ADR 0008). Ingestion and merge never add a copy of a key that a purge lists, unless the purge names a
  corrected version and the writer version of the copy is that version or a newer one (ADR 0015). Before a purge, the
  ledger warns about the purged keys whose source no longer exists, because no new ingestion can bring them back.

## To be confirmed

- Whether a fork made with `/branch` has the structure of a fork made with `--fork-session`
  ([fork-2026-11.md](../research/fork-2026-11.md)); the changelog says that `/branch` writes a pointer, and no
  `/branch` session is tested yet.
- Which source has precedence for each kind when two sources record the same session (for example hooks for human
  signals, native logs for token usage). To specify with the first source other than native logs (Phase 3).
