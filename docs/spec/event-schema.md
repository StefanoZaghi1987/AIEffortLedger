# Event schema

The normalized event is the contract between adapters and the metrics engine (ADR 0002). Adapters write events; the
metrics engine reads only events, never native source formats. Terms follow [GLOSSARY.md](../../GLOSSARY.md); the
reasons for event identity and for new schema versions are in ADR 0023.

## Kinds

| Kind | Actor | Meaning |
|---|---|---|
| `session_start`, `session_end` | system | Limits of a session |
| `prompt` | human | A prompt of the person to the main agent of a session that is interactive or of unknown invocation |
| `queued_message` | human | A message typed while an agent works |
| `interruption` | human | The person stops an agent turn |
| `notification` | system | A non-human input to an agent: task notification, coordinator or peer message, the input that a subagent gets from the agent that started it, scheduled trigger, or a prompt of a session of headless, scheduled, or orchestrated invocation |
| `agent_output` | agent | One response of a model; carries token usage, request counts, and price factors |
| `tool_call` | agent | An agent asks to run a tool; carries the tool name, the tool category, and size counters |
| `tool_result` | system | The result of a tool call, returned to the agent that asked for it |
| `decision_request` | agent | A permission request, a question to the person, or a plan approval |
| `decision` | human or system | The answer to a decision request; `human` when the person answered, `system` for a configured rule |
| `manual_entry` | human | An interval of declared human time |
| `timesheet_confirmation` | human | The timesheet entries of one day that the person confirms together, each with the declared human time of a project or of the unattributed time, and an optional work item (ADR 0011, ADR 0014) |
| `declared_usage` | human | Declared agent time, token usage, or cost of work that no source recorded (Phase 2) |
| `annotation` | human | Project, work item, or labels of a session or a time interval; adds no time |
| `retraction` | human | Cancels an earlier event by event key |
| `purge` | human | The keys that a purge removed, its reason, its time, and an optional corrected version (ADR 0008, ADR 0015) |

Turns, intervals, activity classes, attributions, projects, providers, and costs are not events: the metrics engine
derives them.

## Fields

| Field | Required | Meaning |
|---|---|---|
| `schema_version` | yes | Version of this schema used to write the event, a whole number; the first release writes `1` |
| `source` | yes | Stable identifier of the writer: the adapter, for example `claude-code-jsonl`, or `ledger` for events that a command writes; part of the key |
| `source_format` | for events from native sources | Native format version that the adapter recognized, for example the version of the agent tool; not part of the key |
| `native_id` | when the source gives one | Identifier of the event in the source, unique across sessions of that source; the copies of a record that a forked session makes are one event (see Keys and invariants) |
| `session_id` | for events of a session | Session identifier given by the source |
| `event_uid` | yes | Identifier of the event within its session, stable across re-ingestion; the native identifier when the source gives one |
| `timestamp` | yes | UTC instant of the event; for an `agent_output` written on several lines, the instant of the last line; for an event that a command writes, the instant at which the command writes it |
| `ingested_at` | yes | UTC instant at which the event first entered a segment |
| `writer_version` | yes | Version of the ledger program that wrote the event, compared number by number (`1.10.0` is newer than `1.9.0`), and a version with a development mark before the same version without it (`1.3.0.dev0` is older than `1.3.0`); not part of the key (ADR 0015) |
| `actor` | yes | `human`, `agent`, or `system` |
| `kind` | yes | One of the kinds above |
| `invocation` | for events of a session | `interactive`, `headless`, `scheduled`, `orchestrated`, or `unknown`, as the source shows it at the event; a resumed session can change it |
| `parent_session_id` | when known | Session that started this session, such as the session of a coordinator or an orchestrator |
| `agent_id` | for events of a session | Agent that the event belongs to: the agent that produced it, or, for an input, the agent that the input reaches; equals the session for the main agent |
| `parent_agent_id` | for subagents | Agent that started the subagent |
| `subagent_mode` | for subagents | `foreground` or `background` |
| `call_id` | for tool and decision events | Links `tool_call`, `decision_request`, `decision`, and `tool_result` of one tool use |
| `tool_name` | for `tool_call` | Native name of the tool, as given by the source |
| `tool_category` | for `tool_call` | `edit`, `execute`, `read`, `search`, `web`, `delegate`, `decide`, or `other`, from the table of the adapter; category rules can replace it at report time |
| `lines_added`, `lines_removed`, `file_ext` | for `tool_call` of category `edit` with a successful result, when the source gives them | Size counters (ADR 0012, ADR 0016); a value that the source does not give is absent, never zero |
| `size_basis` | with size counters | `patch` when the counters come from a patch, `input` when they come from the tool input (ADR 0016) |
| `decision_type` | for decision events | `permission`, `question`, or `plan_approval` |
| `input_origin` | for notifications | `task_notification`, `coordinator`, `peer`, `parent` (the agent that started the subagent), `scheduled`, or `scripted` |
| `forked_from` | for forked sessions | Session the history was copied from, and the instant of the fork |
| `machine` | yes | Random identifier of the machine on which the work happened, or, for an event that a command writes, of the machine that wrote it ([ingestion.md](ingestion.md)) |
| `tool` | for events of a session and for declared usage | Agent tool, for example `claude-code`, `claude-desktop`, `codex` |
| `provider_hint` | for `agent_output` when the source shows it | What the source shows about the provider, such as the host of the endpoint; the provider is resolved at report time |
| `model` | for `agent_output`; optional for `declared_usage` | Model identifier as given by the source or by the person |
| `tokens` | for `agent_output`; optional for `declared_usage` | Token counts per category; the category set is open (see below) |
| `requests` | for `agent_output` when the source gives them | Request counts per request type, such as `web_search`; the set of types is open, and a count of zero is not written (ADR 0024) |
| `price_factors` | for `agent_output` when the source gives them | Price factors by name, such as `speed`, `service_tier`, or `inference_geo`, each with the value that the source gives; the set of names is open (ADR 0024) |
| `cwd` | when known | Folder of the session when the event occurred |
| `repo_hint` | when known | Repository identity observed or inferred at ingestion (ADR 0004, ADR 0009, ADR 0018) |
| `repo_basis` | with `repo_hint` | `observed` when read from the folder of the event, `inferred` when read from its nearest existing parent folder because the folder no longer exists (ADR 0018) |
| `branch` | when known | Git branch at the event |
| `start`, `end` | for manual entries and interval annotations; optional for `declared_usage` | UTC limits of the declared interval, which includes its start instant and excludes its end instant |
| `day` | for timesheet confirmations | Date of the local day of the person to which the confirmation applies ([metrics.md](metrics.md)) |
| `duration` | optional for `declared_usage` | Declared agent time (Phase 2) |
| `cost`, `currency` | optional for `declared_usage` | Actual cost that the person declares (Phase 2); computed costs are never stored (ADR 0007) |
| `manual_mode` | for manual entries | `additional` or `overlapping` |
| `project`, `work_item` | `project` for declared usage; for manual entries optional, absent for the unattributed time; otherwise optional | Attribution declared by the person: a project identifier and a work item identifier (ADR 0019); an annotation has at least one of them or `labels` |
| `note` | optional for manual entries, annotations, and declared usage | Short text written by the person for the person |
| `entries` | for timesheet confirmations | The timesheet entries of the day, at most one for each project and work item, possibly none: each with `project` (absent for the unattributed time), `work_item` (optional, only with `project`), `duration`, and `note` (optional) |
| `replaces` | optional for timesheet confirmations | Event key of the latest confirmation of the same day that the writing machine had when it wrote this one ([metrics.md](metrics.md) › Declared values) |
| `annotates` | for annotations of a session | The session that the annotation applies to: `tool` and `session_id` |
| `retracts` | for retractions | Event key of the cancelled event |
| `purged_keys`, `purge_reason` | for purges | Keys removed and the reason, a label for the person: `content`, `correction`, or `forget` |
| `purged_sessions` | for purges with a corrected version | The sessions that hold the purged keys, each as `tool` and `session_id`, so that every machine knows which sessions to read again (ADR 0015) |
| `corrected_version` | optional for purges, never with reason `forget` | Writer version from which new copies of the purged keys are accepted (ADR 0015) |
| `labels` | no | Attribution hints from the allow-list of label keys in the person configuration (Phase 2) |
| `session_title` | no | Title of the session, only when the person configuration allows titles (Phase 2) |

The pseudonym of the person is in the person configuration ([configuration.md](configuration.md)), not a field of each
event; a team export adds it.

No field holds the text of prompts, responses, tool input, or code, or the paths of files in tool input (ADR 0003,
ADR 0012). Adapters drop that text while they read.

Token categories start with `input`, `output`, `cache_write_5m`, `cache_write_1h`, and `cache_read`. An adapter adds a
category, such as reasoning output, when a provider reports it separately; a price table that has no price for a
category makes the report show that cost as unknown, never as zero. Cumulative counters of a source become per-event
counts in the adapter.

## Encoding

A segment holds one event on each line: a JSON object in UTF-8, ended by a line break (`\n`). A writer writes only the
fields of its schema version. An absent field is not written, never written as `null`.

A new schema version only adds fields, kinds, or values of a field; it never changes the meaning of an existing field,
kind, or value (ADR 0023). A reader therefore reads an event of a newer schema version with the fields that it knows and
ignores the other fields. It leaves out an event of a kind that it does not know, or with a value that it does not know
in a field that it knows; such a line is not a broken line. The values that this rule checks are those of the fields
with a fixed set of values — `kind`, `actor`, `invocation`, `subagent_mode`, `tool_category`, `input_origin`,
`decision_type`, `manual_mode`, `size_basis`, `repo_basis`, and `purge_reason`; the keys of the open sets — token
categories, request types, and price factors — pass through as they are. The report warns that events of a newer
version of the ledger exist, asks to update the ledger, and completes with the exit code for incomplete figures
([command-line.md](command-line.md) › Exit codes).

| Value | Encoding |
|---|---|
| Instants: `timestamp`, `ingested_at`, `start`, `end` | RFC 3339 text in UTC with `Z` and milliseconds, such as `2026-11-19T08:30:00.125Z` |
| `day` | local date, `YYYY-MM-DD` |
| `duration`, also in `entries` | whole seconds |
| `tokens` | object: token category → whole number |
| `requests` | object: request type → whole number above zero |
| `price_factors` | object: name → text |
| `cost`, `currency` | decimal text, such as `"12.50"`; ISO 4217 currency code |
| `forked_from` | object with `session_id` and `instant` |
| An event key, in `retracts`, `replaces`, and each item of `purged_keys` | object with `source` and `native_id`; with `source`, `session_id`, and `event_uid`; or, for an event that a command writes, with `source` and `event_uid` |
| `entries`, `purged_sessions`, `annotates` | array of objects; array of objects; object |
| `machine`, `event_uid` of an event that a command writes | random UUID (version 4) text |
| `repo_hint` | `host/path` for an identity from a remote; `root-commit:` and the hash for an identity from a root commit |
| `writer_version`, `corrected_version` | whole numbers separated by dots, optionally followed by a development mark, `.dev` and a whole number ([architecture.md](architecture.md) › Runtime) |
| `labels` | object: label key → text |

## Keys and invariants

- The key of an event is (`source`, `native_id`) when the source gives a native identifier, otherwise (`source`,
  `session_id`, `event_uid`). Events that a command writes have the source `ledger` and no session: their key is
  (`ledger`, `event_uid`), with a random `event_uid` made at creation. Ingesting an event twice leaves one event, also
  after an adapter starts to recognize a new `source_format`. Event keys have an order, which tie-breaks use: by
  `source`, then `session_id`, then `event_uid`, each compared as text, and an absent part comes before every text.
- The identity of an event comes only from facts that the source gives about identity, never from facts that can
  change while the record stays the same: not from the number of the line of the record in its file, and not from a
  hash of its text (ADR 0023). An event takes the identifier of the record it comes from; when one
  record gives more than one event, the kind of the event goes before the identifier, for example `decision:` and the
  identifier of the tool use. An event from a record without an identifier gets as `event_uid` its kind, its timestamp,
  and its position among the records of its session with the same kind and timestamp, in the order of the files of the
  session (the file of the main agent, then the files of its subagents by name) and of the lines in each file.
- When a source writes one record more than once, for example in the file of a session and in the file of one of its
  subagents, the adapter writes one event, from the copy in the file of the agent that the record names, and warns
  when the copies differ in another field. The adapter therefore reads all the files of a session together.
- When two copies of an event with the same key differ in a field other than the key, the copy with the earliest
  `ingested_at` wins, and equal instants resolve by the order of the names of the segments that hold the copies.
  Segments of several machines therefore merge to the same result in any order.
- A folder of native logs is read by the machine on which it exists. When two machines read the same folder anyway, for
  example through a copied profile, the merge rule keeps the copy with the earliest `ingested_at` and its `machine`
  field, so the machine that such an event names depends on which machine ingested it first.
- A stored event does not change, so ingestion writes only complete events ([ingestion.md](ingestion.md)). A correction
  of an adapter reaches events already stored only through a purge that names the corrected version and a new ingestion
  (ADR 0015).
- Two sources record the same session when they give the same `tool` and the same `session_id`. Such sources, such as
  a native log and a hook, never add up: for each session and each kind, reports read one source.
- An adapter writes a prompt as `prompt` with actor `human` only when the session is interactive or of unknown
  invocation and the source shows a human origin; otherwise it writes a `notification` with `input_origin` `scheduled`
  in a session of scheduled invocation, and `scripted` in any other. A headless prompt is such a notification with
  `input_origin` `scripted` in a session of headless invocation.
- A forked session starts with copies of records of its original, with the same native identifiers, so a copy and
  its original are one event. A session cannot have records of its own from before it existed: the original is the
  session that holds records of its own, without a copy in the other session, inside the time range of the shared
  records, and the shared events belong to it. The fork instant is the timestamp of the last shared record, and the
  events of the fork carry `forked_from`. When both sessions or neither hold records of their own in that range, the
  session whose identifier sorts first is the original, and the adapter warns. An event already in the store keeps its
  session (ADR 0023).
- One response that the source writes on several lines becomes one `agent_output` with the largest token counts and
  request counts, and, for each price factor, the value of the last line of the response that gives it.
- Size counters are computed before the text is dropped (ADR 0016). When the source gives a patch of the change, in the
  tool result or in the tool input, they are the added and removed lines of the patch, with `size_basis` `patch`.
  Otherwise they are the lines of the new text and of the replaced text in the tool input, with `size_basis` `input`; a
  whole-file write that the source reports as a new file has zero lines removed, and one that the source does not report
  as new has lines removed absent. A tool call without a result, or whose result the source marks as an error, gets no
  size counters. An empty text has no lines; the lines of another text are its line breaks, plus one when the text does
  not end with a line break. The file extension is the part of the file name after its last dot, in lower case; a name
  without a dot, or whose only dot is its first character, has no file extension.
- The tool category comes from a table of the adapter; an unknown tool name gets `other`, and ingestion warns about it
  (ADR 0012, [ingestion.md](ingestion.md)). Category rules ([configuration.md](configuration.md)), matched on the tool
  name, replace the stored category at report time, so a tool that the adapter cannot know, such as a tool of an MCP
  server, can count as `edit` or `search`.
- Events are append-only. A wrong event is cancelled by a retraction; attribution changes by annotation; only a purge
  removes events (ADR 0008). Ingestion and merge never add a copy of a key that a purge lists, unless the purge names a
  corrected version and the writer version of the copy is that version or a newer one (ADR 0015). Before a purge, the
  ledger warns about the purged keys whose source no longer exists: for a source of native logs, a source of which no
  folder of native logs remains in the machine configuration; the source `ledger` always exists. No new ingestion can
  bring such keys back.

## To be confirmed

- Whether a fork made with `/branch` has the structure of a fork made with `--fork-session`
  ([fork-2026-11.md](../research/fork-2026-11.md)); the changelog says that `/branch` writes a pointer, and no `/branch`
  session is tested yet. To specify with a real sample.
- Which source has precedence for each kind when two sources record the same session (for example hooks for human
  signals, native logs for token usage). To specify with the first source other than native logs (Phase 3).
