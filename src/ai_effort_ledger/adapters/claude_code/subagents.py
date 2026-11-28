"""The subagents of a session: the copy of one record that gives its event when the source
wrote the record in the files of several agents, and the link of each subagent to the call
that started it, which names its parent agent and its mode
(claude-code-adapter.md › Session fields; event-schema.md › Keys and invariants)."""

from collections.abc import Sequence
from typing import Any

from ...events import Event
from .mapping import SessionRecord, _parts


def deduplicate(
    records: Sequence[SessionRecord],
) -> tuple[list[SessionRecord], list[dict]]:
    """The records of a session with one row per record: when the same record is in the files
    of several agents, the copy in the file of the agent that its `agentId` names, or of the
    main agent when it names none, gives the event, and the copies that differ in another
    field warn, naming the fields and never their content (event-schema.md › Keys and
    invariants). A row whose record holds no `uuid` stays, because nothing names it as the
    copy of another row."""
    copies: dict[str, list[int]] = {}
    for position, row in enumerate(records):
        identity = _identity_of(row.record)
        if identity is not None:
            copies.setdefault(identity, []).append(position)
    keep: set[int] = set()
    warnings: list[dict] = []
    for positions in copies.values():
        rows = [records[position] for position in positions]
        keep.add(positions[rows.index(_named_copy(rows))])
        if len(rows) > 1:
            fields = _differing_fields(rows)
            if fields:
                warnings.append(
                    {"code": "record_copies_differ", "values": {"fields": fields}})
    kept = [row for position, row in enumerate(records)
            if position in keep or not _identity_of(row.record)]
    return kept, warnings


def link_subagents(events: list[Event], records: Sequence[SessionRecord]) -> None:
    """Set `parent_agent_id` and `subagent_mode` on the events of every subagent that the
    result of a tool names with its `toolUseResult.agentId`: the parent is the agent of the
    call that the result answers, and the mode is `background` when the result holds `isAsync`
    true or the input of the call holds `run_in_background` true, and `foreground` otherwise
    (claude-code-adapter.md › Session fields)."""
    callers: dict[str, str | None] = {}
    for event in events:
        if event["kind"] == "tool_call" and isinstance(event.get("call_id"), str):
            callers[event["call_id"]] = event.get("agent_id")
    inputs = _tool_inputs(records)
    links: dict[str, tuple[str | None, str]] = {}
    for row in records:
        result = row.record.get("toolUseResult")
        if not isinstance(result, dict):
            continue
        agent = result.get("agentId")
        if not (isinstance(agent, str) and agent):
            continue
        parent: str | None = None
        background = result.get("isAsync") is True
        for part in _parts(row.record.get("message")):
            if part.get("type") != "tool_result":
                continue
            call_id = part.get("tool_use_id")
            if not isinstance(call_id, str):
                continue
            if parent is None:
                parent = callers.get(call_id)
            tool_input = inputs.get(call_id)
            if isinstance(tool_input, dict) and tool_input.get("run_in_background") is True:
                background = True
        links[agent] = (parent, "background" if background else "foreground")
    for event in events:
        link = links.get(event.get("agent_id"))
        if link is None:
            continue
        parent, mode = link
        if parent is not None:
            event["parent_agent_id"] = parent
        event["subagent_mode"] = mode


def _named_copy(rows: list[SessionRecord]) -> SessionRecord:
    """The copy that gives the event: the one in the file of the agent that the record names
    with its `agentId`, or in the file of the main agent when it names none; the first copy in
    the order of the files stays when no copy sits in the named file."""
    named = ""
    for row in rows:
        agent = row.record.get("agentId")
        if isinstance(agent, str) and agent:
            named = agent
            break
    for row in rows:
        if row.agent == named:
            return row
    return rows[0]


def _differing_fields(rows: list[SessionRecord]) -> list[str]:
    """The fields of the record that the copies do not hold with the same value, in name
    order; a field that one copy holds and another does not differs too."""
    fields: set[str] = set()
    first = rows[0].record
    for other in rows[1:]:
        for key in set(first) | set(other.record):
            if key not in first or key not in other.record or first[key] != other.record[key]:
                fields.add(key)
    return sorted(fields)


def _identity_of(record: dict[str, Any]) -> str | None:
    """The name that two copies of one record share: its `uuid` when it is a non-empty
    string, else None."""
    identity = record.get("uuid")
    return identity if isinstance(identity, str) and identity else None


def _tool_inputs(records: Sequence[SessionRecord]) -> dict[str, dict[str, Any]]:
    """The input of each use of a tool that the records of the session ask for, by the
    identifier of the use."""
    inputs: dict[str, dict[str, Any]] = {}
    for row in records:
        for part in _parts(row.record.get("message")):
            if part.get("type") != "tool_use":
                continue
            call_id = part.get("id")
            if isinstance(call_id, str) and call_id:
                tool_input = part.get("input")
                inputs[call_id] = tool_input if isinstance(tool_input, dict) else {}
    return inputs
