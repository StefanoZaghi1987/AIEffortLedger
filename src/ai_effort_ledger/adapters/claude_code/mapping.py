"""The mapping of the records of a session to events: the rows of the table of records, the
token counts, the request counts, and the price factors of a response, the category of each
tool name, the size counters of a call of a tool of the edit category, and the event
identifier of a record without a native identifier
(claude-code-adapter.md › Records and events, › Tokens, › Requests and price factors,
› Tool categories, › Size counters; event-schema.md › Keys and invariants)."""

from collections.abc import Iterator, Sequence
from typing import Any, NamedTuple

from ...events import SCHEMA_VERSION, Event, format_instant, parse_instant
from .size import size_counters
from .tables import SOURCE, TOOL_CATEGORIES, invocation_of

DECISION_TOOLS: dict[str, str] = {
    "AskUserQuestion": "question",
    "ExitPlanMode": "plan_approval",
}
"""The decision type that each tool whose use also asks for a decision gives."""

ORIGIN_KINDS: dict[str, str] = {
    "task-notification": "task_notification",
    "coordinator": "coordinator",
    "peer": "peer",
}
"""The input origin that each kind of the origin of a record of the person gives."""

INSTANT_RECORD_TYPES: tuple[str, ...] = ("assistant", "user", "queue-operation")
"""The record types that give events; only a record of these types needs an instant."""

NOTIFICATION_TAG = "<task-notification"
NO_ORIGIN_TAGS: tuple[str, ...] = (
    "<task-notification", "<local-command-stdout", "<local-command-caveat", "<system-reminder",
)
"""The tags with which the text of a record without `origin` is no prompt of the person: a text
that starts with the tag of a task notification is a notification, the other tags give no event."""

INTERRUPTION = "[Request interrupted by user"
"""The text with which a record of the person begins when the person stops the agent turn."""

TOKEN_KEYS: tuple[tuple[str, str], ...] = (
    ("input", "input_tokens"),
    ("output", "output_tokens"),
    ("cache_read", "cache_read_input_tokens"),
)
"""The token category that each key of the usage of a response gives."""

REQUEST_KEYS: tuple[tuple[str, str], ...] = (
    ("web_search", "web_search_requests"),
    ("web_fetch", "web_fetch_requests"),
)
"""The request type that each key of the server tool usage of a response gives."""

PRICE_KEYS: tuple[str, ...] = ("speed", "service_tier", "inference_geo")
"""The price factors that the usage of a response names."""


class SessionRecord(NamedTuple):
    """One record of the files of a session: the agent whose file holds it, empty for the main
    agent, the order of that file in the session, the number of the line in the file, and the
    record (claude-code-adapter.md › Session fields)."""

    agent: str
    file_order: int
    line: int
    record: dict[str, Any]


class _Call(NamedTuple):
    """A use of a tool that the mapping has seen: the record of the agent that asked for it,
    the invocation of that record, the decision that the tool asks for, when one, the event of
    the call, and the input that the call gives to the tool."""

    row: SessionRecord
    invocation: str
    decision_type: str | None
    event: Event
    tool_input: dict[str, Any]


class _Input(NamedTuple):
    """The input event that a record of the person without a result of a tool gives: the kind
    of the event, its input origin for a notification, its native identifier when the record
    names one, and the warning when the origin or the structure of the record is not known."""

    kind: str | None
    origin: str | None
    native_id: str | None
    warning: dict | None


def map_session(
    records: Sequence[SessionRecord], tool: str, machine: str
) -> tuple[list[Event], list[dict]]:
    """The events that the records of one session give, and their warnings: every event carries
    the agent tool and the machine of the session, and the invocation of the entrypoint of its
    own record, because a resumed session can change it (event-schema.md › Fields).

    The records come in the order of the files of the session and of the lines in each file; a
    response that the source writes on several lines becomes one `agent_output` with the largest
    token counts and request counts and the price factors of the last line that gives each.

    A record of the agent whose `message` is not an object gives no event and one `invalid_record`
    warning, which names the order of the file of the session instead of the file, because the
    mapping does not know the file; the reading names the file. A record of a type that gives
    events (`assistant`, `user`, `queue-operation`) whose `timestamp` is absent or is not an
    instant with an offset gives no event and the same warning; a record of another type needs
    no instant.

    A record of the person gives the events of the rows of its kind: the result of each use of a
    tool that it holds, the decision of the person that the result of a question or of a plan
    approval gives, the request of a decision and the decision that a permission gives, the
    notification of a machine origin, and, without a result of a tool and without a machine
    origin, its prompt, its notification, or its interruption; a message that the person typed
    while the agent worked gives a queued message. An origin kind or a permission source that no
    row names gives one warning that names the value, once per value.
    """
    identifiers = event_identifiers(records)
    warnings: list[dict] = []
    seen_entrypoints: set[str] = set()
    seen_tools: set[str] = set()
    seen_origins: set[str] = set()
    seen_sources: set[str] = set()
    calls: dict[Any, _Call] = {}
    events: list[Event] = []
    responses: dict[tuple, Event] = {}
    fallbacks: dict[tuple, int] = {}
    for row in sorted(records, key=lambda item: (item.file_order, item.line)):
        record = row.record
        if record.get("isMeta"):
            continue
        if _instant_of(record) is None:
            if record.get("type") in INSTANT_RECORD_TYPES:
                warnings.append({"code": "invalid_record",
                                 "values": {"file": row.file_order, "line": row.line}})
            continue
        invocation = _invocation_of(record, seen_entrypoints, warnings)
        kind = record.get("type")
        if kind == "assistant":
            _map_response(
                row, tool, machine, invocation, identifiers, responses, events,
                seen_tools, calls, warnings, fallbacks)
        elif kind == "user":
            _map_person(row, tool, machine, invocation, identifiers, calls, seen_origins,
                        seen_sources, events, warnings)
        elif kind == "queue-operation":
            _map_queued(row, tool, machine, invocation, identifiers, events)
    for key, count in fallbacks.items():
        tokens = responses[key]["tokens"]
        _keep_largest(tokens, "cache_write_5m", count - tokens.get("cache_write_1h", 0))
    for event in events:
        for field in ("tokens", "requests", "price_factors"):
            if event.get(field) == {}:
                del event[field]
    return events, warnings


def event_identifiers(records: Sequence[SessionRecord]) -> dict[tuple[int, int], str]:
    """The event identifier of every record that gives an event without a native identifier, by
    the file order and line of its record: the kind of the event, the instant as the event
    stores it, and the position of the record among those with the same kind and instant, in the
    order of the files of the session and of the lines in each file (event-schema.md › Keys and
    invariants)."""
    identifiers: dict[tuple[int, int], str] = {}
    counted: dict[tuple[str, str], int] = {}
    for row in sorted(records, key=lambda item: (item.file_order, item.line)):
        record = row.record
        instant = _instant_of(record)
        if record.get("isMeta") or instant is None:
            continue
        for kind, native_id in _events_of(row):
            if native_id is not None:
                continue
            position = counted.get((kind, instant), 0)
            counted[(kind, instant)] = position + 1
            identifiers[(row.file_order, row.line)] = f"{kind}:{instant}:{position}"
    return identifiers


def _message_of(record: dict[str, Any]) -> dict[str, Any] | None:
    """The message of a record when it is an object that the mapping reads, else None."""
    message = record.get("message")
    return message if isinstance(message, dict) else None


def _model_of(message: dict[str, Any]) -> str | None:
    """The model of a response when the mapping maps it: a non-empty string that does not start
    with `<`; every other value of the model gives no event (claude-code-adapter.md › Records
    and events)."""
    model = message.get("model")
    if not (isinstance(model, str) and model) or model.startswith("<"):
        return None
    return model


def _native_id_of(message: dict[str, Any]) -> str | None:
    """The native identifier of a response: its `message.id` when it is a non-empty string,
    else None, so that an empty or absent identifier falls to the identifier of its record at
    every site that derives it (event-schema.md › Keys and invariants)."""
    message_id = message.get("id")
    return message_id if isinstance(message_id, str) and message_id else None


def _response_key(row: SessionRecord) -> tuple[str, ...] | None:
    """The name that the lines of one response share: the native identifier of the message of
    the model, or the place of the row when the record gives none; a record that gives no
    response of a model names none. The completeness of the reading pairs the lines of one
    response with the same name (claude-code-adapter.md › Complete events)."""
    message = _message_of(row.record)
    if message is None or _model_of(message) is None:
        return None
    native_id = _native_id_of(message)
    if native_id is not None:
        return ("id", native_id)
    return ("row", row.file_order, row.line)


def _events_of(row: SessionRecord) -> Iterator[tuple[str, str | None]]:
    """The kind and the native identifier of every event that a record gives, for the rows that
    the mapping knows; an event whose native identifier is None takes the identifier of its
    record instead."""
    record = row.record
    kind = record.get("type")
    if kind == "assistant":
        message = _message_of(record)
        if message is None or _model_of(message) is None:
            return
        yield "agent_output", _native_id_of(message)
        for part in _parts(message):
            part_type = part.get("type")
            if part_type == "tool_use":
                call_id = part.get("id")
                yield "tool_call", f"tool_call:{call_id}"
                decision = DECISION_TOOLS.get(part.get("name"))
                if decision is not None:
                    yield "decision_request", f"decision_request:{decision}:{call_id}"
            elif part_type in ("server_tool_use", "mcp_tool_use"):
                yield "tool_call", f"tool_call:{part.get('id')}"
    elif kind == "user":
        results = _tool_results_of(record)
        for part in results:
            yield "tool_result", f"tool_result:{part.get('tool_use_id')}"
        mapped, warning = _machine_origin_of(record)
        if mapped is not None:
            yield "notification", _uuid_of(record)
        elif warning is None and not results:
            found = _input_of(record, row.agent, invocation_of(record)[0])
            if found.kind is not None:
                yield found.kind, found.native_id
    elif kind == "queue-operation":
        if _queued_of(record):
            yield "queued_message", None


def _map_response(
    row: SessionRecord,
    tool: str,
    machine: str,
    invocation: str,
    identifiers: dict[tuple[int, int], str],
    responses: dict[tuple, Event],
    events: list[Event],
    seen_tools: set[str],
    calls: dict[Any, _Call],
    warnings: list[dict],
    fallbacks: dict[tuple, int],
) -> None:
    """Map one record of the agent: its response, and one event for each use of a tool that its
    content holds, whose call the mapping remembers for the rows of its result. A `message`
    that is not an object gives no event and one `invalid_record` warning."""
    message = _message_of(row.record)
    if message is None:
        warnings.append({"code": "invalid_record",
                         "values": {"file": row.file_order, "line": row.line}})
        return
    model = _model_of(message)
    if model is None:
        return
    native_id = _native_id_of(message)
    key = _response_key(row)
    output = responses.get(key)
    if output is None:
        output = _skeleton(row, "agent_output", "agent", tool, machine, invocation,
                           identifiers, native_id)
        output["model"] = model
        responses[key] = output
        events.append(output)
    output["timestamp"] = _instant_of(row.record)
    output["invocation"] = invocation
    usage = message.get("usage")
    if isinstance(usage, dict):
        _keep_fallback(fallbacks, key, _merge_tokens(output, usage))
        _merge_requests(output, usage)
        _merge_price_factors(output, usage)
    for part in _parts(message):
        part_type = part.get("type")
        if part_type == "tool_use":
            decision = DECISION_TOOLS.get(part.get("name"))
            call = _tool_call(row, part, tool, machine, invocation,
                              identifiers, seen_tools, warnings)
            events.append(call)
            tool_input = part.get("input")
            calls[part.get("id")] = _Call(row, invocation, decision, call,
                                          tool_input if isinstance(tool_input, dict) else {})
            if decision is not None:
                call_id = part.get("id")
                event = _skeleton(row, "decision_request", "agent", tool, machine,
                                  invocation, identifiers,
                                  f"decision_request:{decision}:{call_id}")
                event["decision_type"] = decision
                event["call_id"] = call_id
                events.append(event)
        elif part_type in ("server_tool_use", "mcp_tool_use"):
            events.append(_tool_call(row, part, tool, machine, invocation,
                                     identifiers, seen_tools, warnings))


def _map_person(
    row: SessionRecord,
    tool: str,
    machine: str,
    invocation: str,
    identifiers: dict[tuple[int, int], str],
    calls: dict[Any, _Call],
    seen_origins: set[str],
    seen_sources: set[str],
    events: list[Event],
    warnings: list[dict],
) -> None:
    """Map a record of the person: the event of each result of a tool that it holds, the size
    counters that each result gives to the event of its call, the decisions that its results
    and its permission give, the notification of a machine origin, which every record of the
    person takes, and, without a result of a tool and without a machine origin, the prompt,
    notification, or interruption of its input."""
    record = row.record
    results = _tool_results_of(record)
    use_result = record.get("toolUseResult")
    if not isinstance(use_result, dict):
        use_result = {}
    for part in results:
        tool_use_id = part.get("tool_use_id")
        event = _skeleton(row, "tool_result", "system", tool, machine, invocation,
                          identifiers, f"tool_result:{tool_use_id}")
        event["call_id"] = tool_use_id
        events.append(event)
        held = calls.get(tool_use_id)
        if held is not None:
            held.event.update(size_counters(
                held.event.get("tool_name", ""), held.tool_input, use_result,
                part.get("is_error") is True))
    _map_decisions(row, results, tool, machine, invocation, calls, identifiers, events)
    _map_permission(row, results, tool, machine, invocation, calls, identifiers,
                    seen_sources, events, warnings)
    mapped, warning = _machine_origin_of(record)
    if warning is not None and warning["values"]["kind"] not in seen_origins:
        seen_origins.add(warning["values"]["kind"])
        warnings.append(warning)
    if mapped is not None:
        event = _skeleton(row, "notification", "system", tool, machine, invocation,
                          identifiers, _uuid_of(record))
        event["input_origin"] = mapped
        events.append(event)
    if not results and mapped is None and warning is None:
        found = _input_of(record, row.agent, invocation)
        if found.warning is not None:
            warnings.append(found.warning)
        if found.kind is not None:
            actor = "system" if found.kind == "notification" else "human"
            event = _skeleton(row, found.kind, actor, tool, machine, invocation,
                              identifiers, found.native_id)
            if found.origin is not None:
                event["input_origin"] = found.origin
            events.append(event)


def _map_decisions(
    row: SessionRecord,
    results: list[dict[str, Any]],
    tool: str,
    machine: str,
    invocation: str,
    calls: dict[Any, _Call],
    identifiers: dict[tuple[int, int], str],
    events: list[Event],
) -> None:
    """The decision of the person that the result of a question or of a plan approval gives,
    when the call that asked for it is among the records of the session."""
    for part in results:
        call_id = part.get("tool_use_id")
        held = calls.get(call_id)
        if held is None or held.decision_type is None:
            continue
        event = _skeleton(row, "decision", "human", tool, machine, invocation, identifiers,
                          f"decision:{held.decision_type}:{call_id}")
        event["decision_type"] = held.decision_type
        event["call_id"] = call_id
        events.append(event)


def _map_permission(
    row: SessionRecord,
    results: list[dict[str, Any]],
    tool: str,
    machine: str,
    invocation: str,
    calls: dict[Any, _Call],
    identifiers: dict[tuple[int, int], str],
    seen_sources: set[str],
    events: list[Event],
    warnings: list[dict],
) -> None:
    """The request of a decision and the decision that the permission of the record gives: a
    rule of the configuration gives neither, a source that no row names gives one warning per
    value, and a permission on a record with more than one result names no use of a tool."""
    decision = row.record.get("permissionDecision")
    if not isinstance(decision, dict):
        return
    source = decision.get("source")
    if len(results) > 1:
        warnings.append({"code": "multi_tool_result_permission", "values": {}})
        return
    if not results:
        return
    if source == "config":
        return
    if not (isinstance(source, str) and source.startswith("user")):
        if isinstance(source, str) and source not in seen_sources:
            seen_sources.add(source)
            warnings.append(
                {"code": "unknown_permission_source", "values": {"source": source}})
        return
    tool_use_id = results[0].get("tool_use_id")
    event = _skeleton(row, "decision", "human", tool, machine, invocation, identifiers,
                      f"decision:permission:{tool_use_id}")
    event["decision_type"] = "permission"
    event["call_id"] = tool_use_id
    events.append(event)
    held = calls.get(tool_use_id)
    if held is None:
        return
    request = _skeleton(held.row, "decision_request", "agent", tool, machine,
                        held.invocation, identifiers,
                        f"decision_request:permission:{tool_use_id}")
    request["decision_type"] = "permission"
    request["call_id"] = tool_use_id
    events.append(request)


def _map_queued(
    row: SessionRecord,
    tool: str,
    machine: str,
    invocation: str,
    identifiers: dict[tuple[int, int], str],
    events: list[Event],
) -> None:
    """Map the message that a person typed while the agent worked, which the record holds."""
    if _queued_of(row.record):
        events.append(_skeleton(row, "queued_message", "human", tool, machine, invocation,
                                identifiers, None))


def _tool_call(
    row: SessionRecord,
    part: dict[str, Any],
    tool: str,
    machine: str,
    invocation: str,
    identifiers: dict[tuple[int, int], str],
    seen_tools: set[str],
    warnings: list[dict],
) -> Event:
    """The event of one use of a tool, with its category and, for a name that no category of the
    table lists, a warning that names it."""
    call_id = part.get("id")
    event = _skeleton(row, "tool_call", "agent", tool, machine, invocation, identifiers,
                      f"tool_call:{call_id}")
    event["call_id"] = call_id
    name = part.get("name")
    if isinstance(name, str):
        event["tool_name"] = name
        category = TOOL_CATEGORIES.get(name)
        if category is None:
            category = "other"
            if name not in seen_tools:
                seen_tools.add(name)
                warnings.append({"code": "unknown_tool_name", "values": {"tool": name}})
        event["tool_category"] = category
    return event


def _skeleton(
    row: SessionRecord,
    kind: str,
    actor: str,
    tool: str,
    machine: str,
    invocation: str,
    identifiers: dict[tuple[int, int], str],
    native_id: str | None,
) -> Event:
    """The fields that every event of the adapter holds, from its own record; a field that the
    record does not give stays absent, never null."""
    record = row.record
    event: Event = {
        "schema_version": SCHEMA_VERSION,
        "source": SOURCE,
        "kind": kind,
        "actor": actor,
        "timestamp": _instant_of(record),
        "invocation": invocation,
        "agent_id": _agent_id(row, record),
        "machine": machine,
        "tool": tool,
    }
    if native_id is not None:
        event["native_id"] = native_id
        event["event_uid"] = native_id
    else:
        event["event_uid"] = identifiers[(row.file_order, row.line)]
    version = record.get("version")
    if isinstance(version, str) and version:
        event["source_format"] = version
    session_id = record.get("sessionId")
    if isinstance(session_id, str) and session_id:
        event["session_id"] = session_id
    cwd = record.get("cwd")
    if isinstance(cwd, str) and cwd:
        event["cwd"] = cwd
    branch = record.get("gitBranch")
    if isinstance(branch, str) and branch:
        event["branch"] = branch
    return event


def _merge_tokens(event: Event, usage: dict[str, Any]) -> int | None:
    """Take the largest value of each token category among the lines read so far, and return the
    count that a line without `cache_creation` gives for its cache write, or None. The caller
    keeps the largest such count and, when the response is complete, derives the count of the
    cache write of five minutes as that count without the largest write of one hour that any
    line of the response gives, whatever the order of the lines (claude-code-adapter.md ›
    Tokens)."""
    tokens = event.setdefault("tokens", {})
    for category, key in TOKEN_KEYS:
        _keep_largest(tokens, category, usage.get(key))
    creation = usage.get("cache_creation")
    creation = creation if isinstance(creation, dict) else None
    write_1h = creation.get("ephemeral_1h_input_tokens") if creation else None
    write_5m = creation.get("ephemeral_5m_input_tokens") if creation else None
    _keep_largest(tokens, "cache_write_1h", write_1h)
    _keep_largest(tokens, "cache_write_5m", write_5m)
    if write_5m is None and creation is None:
        total = usage.get("cache_creation_input_tokens")
        if isinstance(total, int) and not isinstance(total, bool):
            return total
    return None


def _keep_fallback(fallbacks: dict[tuple, int], key: tuple, count: int | None) -> None:
    """Keep the largest count of a cache write that a line without `cache_creation` gives."""
    if count is not None and (key not in fallbacks or count > fallbacks[key]):
        fallbacks[key] = count


def _keep_largest(tokens: dict[str, int], category: str, value: Any) -> None:
    """Keep the largest whole number seen for the category; a key that no line gives leaves the
    category absent."""
    if isinstance(value, int) and not isinstance(value, bool):
        if category not in tokens or value > tokens[category]:
            tokens[category] = value


def _merge_requests(event: Event, usage: dict[str, Any]) -> None:
    """Take the largest count of each request type among the lines read so far; a count of zero
    is not written (event-schema.md › Fields)."""
    server = usage.get("server_tool_use")
    if not isinstance(server, dict):
        return
    requests = event.setdefault("requests", {})
    for name, key in REQUEST_KEYS:
        value = server.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            if name not in requests or value > requests[name]:
                requests[name] = value


def _merge_price_factors(event: Event, usage: dict[str, Any]) -> None:
    """Take the value of the last line read that gives each price factor, as text."""
    factors = event.setdefault("price_factors", {})
    for name in PRICE_KEYS:
        value = usage.get(name)
        if value is not None:
            factors[name] = str(value)


def _parts(message: Any) -> list[dict[str, Any]]:
    """The parts of the content of a message, as far as they are objects."""
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [part for part in content if isinstance(part, dict)]


def _tool_results_of(record: dict[str, Any]) -> list[dict[str, Any]]:
    """The blocks with the result of a tool that a record of the person holds."""
    return [part for part in _parts(record.get("message"))
            if part.get("type") == "tool_result"]


def _text_of(record: dict[str, Any]) -> str | None:
    """The text of a record of the person: the text of the content of its message — one
    string, or the joined texts of the `text` blocks of a list of blocks."""
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return _content_text(content)


def _content_text(content: Any) -> str | None:
    """The text of the content of a record of the person or of a message in the queue: the
    content itself when it is one string, or, when it is a list of blocks, the texts of its
    `text` blocks joined; a block of another type gives no text, so a list without a `text`
    block has no text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    texts = [part["text"] for part in content
             if isinstance(part, dict) and part.get("type") == "text"
             and isinstance(part.get("text"), str)]
    return "".join(texts) if texts else None


def _uuid_of(record: dict[str, Any]) -> str | None:
    """The native identifier of a record of the person: its `uuid` when it is a non-empty
    string, else None, so that a record without one falls to the identifier of its record
    (event-schema.md › Keys and invariants)."""
    uuid_value = record.get("uuid")
    return uuid_value if isinstance(uuid_value, str) and uuid_value else None


def _interrupted(record: dict[str, Any]) -> bool:
    """Whether the text of a record of the person begins with the text of an interruption."""
    text = _text_of(record)
    return text is not None and text.lstrip().startswith(INTERRUPTION)


def _machine_origin_of(record: dict[str, Any]) -> tuple[str | None, dict | None]:
    """The input origin that the kind of the origin of a record of the person gives, and the
    warning when no row names the kind: every record of the person takes this row, whether or
    not it holds results of tools (claude-code-adapter.md › Records and events)."""
    origin = record.get("origin")
    if isinstance(origin, dict):
        kind = origin.get("kind")
        if isinstance(kind, str):
            mapped = ORIGIN_KINDS.get(kind)
            if mapped is not None:
                return mapped, None
            if kind != "human":
                return None, {"code": "unknown_origin_kind", "values": {"kind": kind}}
    return None, None


def _input_of(record: dict[str, Any], agent: str, invocation: str) -> _Input:
    """The input event that a record of the person without a result of a tool and without a
    machine origin gives: a prompt of an interactive or unknown session, the notification of a
    scripted input or of the input that the starting agent gives to a subagent, or the
    interruption of the person, which replaces the prompt. The caller has taken the machine
    origins and the warning for a kind that no row names; an origin that gives no kind is a
    structure of a known type that is not known (claude-code-adapter.md › Records and events)."""
    native = _uuid_of(record)
    origin = record.get("origin")
    if "origin" in record and not (
            isinstance(origin, dict) and isinstance(origin.get("kind"), str)):
        return _Input(None, None, native,
                      {"code": "unknown_record_type",
                       "values": {"type": str(record.get("type", "")),
                                  "version": str(record.get("version", ""))}})
    interrupted = _interrupted(record)
    if "origin" not in record:
        text = _text_of(record)
        stripped = text.lstrip() if text is not None else ""
        if stripped.startswith(NOTIFICATION_TAG):
            return _Input("notification", "task_notification", native, None)
        if stripped.startswith(NO_ORIGIN_TAGS):
            return _Input(None, None, native, None)
    if agent:
        return _Input("notification", "parent", native, None)
    if interrupted:
        return _Input("interruption", None, native, None)
    return _prompt_of(invocation, native)


def _prompt_of(invocation: str, native: str | None) -> _Input:
    """The prompt of the person, or the notification of a scripted input in a session that is
    neither interactive nor of unknown invocation (event-schema.md › Keys and invariants)."""
    if invocation in ("interactive", "unknown"):
        return _Input("prompt", None, native, None)
    return _Input("notification", "scripted", native, None)


def _queued_of(record: dict[str, Any]) -> bool:
    """Whether a queue-operation record gives a message in the queue: an enqueue whose content
    is a text — one string, or the joined texts of its `text` blocks — that, after leading
    spaces, does not start with `<` (claude-code-adapter.md › Records and events)."""
    if record.get("operation") != "enqueue":
        return False
    text = _content_text(record.get("content"))
    return text is not None and not text.lstrip().startswith("<")


def _invocation_of(
    record: dict[str, Any], seen: set[str], warnings: list[dict]
) -> str:
    """The invocation of a record, with one warning per entrypoint value that no invocation
    gives (claude-code-adapter.md › Session fields)."""
    invocation, warning = invocation_of(record)
    if warning is not None and warning["values"]["value"] not in seen:
        seen.add(warning["values"]["value"])
        warnings.append(warning)
    return invocation


def _agent_id(row: SessionRecord, record: dict[str, Any]) -> str | None:
    """The agent that the event belongs to: the agent that the record names, or the agent of the
    file that holds it, or the session for the main agent."""
    agent_id = record.get("agentId")
    if isinstance(agent_id, str) and agent_id:
        return agent_id
    if row.agent:
        return row.agent
    session_id = record.get("sessionId")
    return session_id if isinstance(session_id, str) and session_id else None


def _instant_of(record: dict[str, Any]) -> str | None:
    """The instant of a record as the event stores it, or None when the record gives none or
    gives a text that is not an instant with an offset."""
    instant = record.get("timestamp")
    if not isinstance(instant, str) or not instant:
        return None
    try:
        return format_instant(parse_instant(instant))
    except (ValueError, OverflowError):
        return None
