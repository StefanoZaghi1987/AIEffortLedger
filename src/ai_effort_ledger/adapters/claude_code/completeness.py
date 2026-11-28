"""The completeness of the events of a session: an event enters the store only when no later
record of the source can change it, and every event of a session whose files have not changed
for the settle time is complete
(claude-code-adapter.md › Complete events; ingestion.md › Adapters; ADR 0020)."""

from collections.abc import Sequence
from typing import NamedTuple

from ...events import Event
from .mapping import SessionRecord, _parts, _response_key, event_identifiers

PROVIDER_BLOCKS = ("server_tool_use", "mcp_tool_use")
"""The kinds of content block whose use of a tool the provider runs inside the response."""

Place = tuple[int, int]
"""The place of a record in the reading of a session: the order of its file, then its line."""

ResponseKey = tuple[str, ...]
"""The name that the lines of one response share: its native identifier, or its row."""


class _Facts(NamedTuple):
    """What the records of a session show about the completeness of its events: the last line
    of each file, the place of the last line of each response, the response that each use of a
    tool of the provider belongs to, the uses whose result exists, the subagents that a result
    links, the subagents of the files, and the place of the record of each event identifier
    that no native identifier names."""

    last_lines: dict[int, int]
    responses: dict[ResponseKey, Place]
    provider: dict[str, ResponseKey]
    results: set[str]
    linked: set[str]
    subagents: set[str]
    derived: dict[str, Place]


def complete_events(
    events: list[Event], records: Sequence[SessionRecord], settled: bool
) -> tuple[list[Event], bool]:
    """The complete events of a session and whether an event stays held back.

    A response of the model is complete when a later record of its file exists that is not a
    line of the same response; the events of a subagent are complete when the result that
    links the subagent exists; a use of a tool of the agent, and the request of a permission,
    are complete when their result exists; a use of a tool that the provider runs inside the
    response is complete with its response; every other event is complete when its record
    exists (claude-code-adapter.md › Complete events). A settled session holds no event back,
    because every event of it is complete.
    """
    if settled:
        return list(events), False
    facts = _facts_of(records)
    complete = [event for event in events if _is_complete(event, facts)]
    return complete, len(complete) < len(events)


def _is_complete(event: Event, facts: _Facts) -> bool:
    """Whether no later record of the session can change the event: every event of a subagent
    waits for its link, the events of the main agent wait by their kind."""
    agent = event.get("agent_id")
    if agent in facts.subagents:
        return agent in facts.linked
    kind = event["kind"]
    if kind == "agent_output":
        return _response_is_complete(event, facts)
    if kind == "tool_call":
        return _call_is_complete(event, facts)
    if kind == "decision_request" and event.get("decision_type") == "permission":
        return event.get("call_id") in facts.results
    return True


def _response_is_complete(event: Event, facts: _Facts) -> bool:
    """Whether a later record of the file of the response exists that is not a line of the same
    response: the response ends at its last line, which its native identifier names, or the
    record of the event names when the source gives none."""
    native = event.get("native_id")
    if native is not None:
        return _has_later(facts.responses.get(("id", native)), facts)
    return _has_later(facts.derived.get(event.get("event_uid")), facts)


def _call_is_complete(event: Event, facts: _Facts) -> bool:
    """Whether the use of a tool is complete: a use that the provider runs inside the response
    is complete with its response, any other use waits for its result."""
    response = facts.provider.get(event.get("call_id"))
    if response is None:
        return event.get("call_id") in facts.results
    return _has_later(facts.responses.get(response), facts)


def _has_later(place: Place | None, facts: _Facts) -> bool:
    """Whether the file of the place holds a record at a later line."""
    return place is not None and facts.last_lines.get(place[0], 0) > place[1]


def _facts_of(records: Sequence[SessionRecord]) -> _Facts:
    """What the records of the session show, in one reading of the rows."""
    last_lines: dict[int, int] = {}
    responses: dict[ResponseKey, Place] = {}
    provider: dict[str, ResponseKey] = {}
    results: set[str] = set()
    linked: set[str] = set()
    for row in records:
        if row.line > last_lines.get(row.file_order, 0):
            last_lines[row.file_order] = row.line
        record = row.record
        result = record.get("toolUseResult")
        if isinstance(result, dict):
            agent = result.get("agentId")
            if isinstance(agent, str) and agent:
                linked.add(agent)
        response = _response_of(row)
        for part in _parts(record.get("message")):
            kind = part.get("type")
            if response is not None and kind in PROVIDER_BLOCKS:
                call_id = part.get("id")
                if isinstance(call_id, str):
                    provider[call_id] = response
            elif kind == "tool_result":
                tool_use_id = part.get("tool_use_id")
                if isinstance(tool_use_id, str):
                    results.add(tool_use_id)
        if response is not None:
            place = (row.file_order, row.line)
            known = responses.get(response)
            if known is None or place > known:
                responses[response] = place
    subagents = {row.agent for row in records if row.agent}
    derived = {name: place for place, name in event_identifiers(records).items()}
    return _Facts(last_lines, responses, provider, results, linked, subagents, derived)


def _response_of(row: SessionRecord) -> ResponseKey | None:
    """The name that the lines of one response share, by the rule of the mapping that pairs
    them (mapping.py › `_response_key`); a record that is not a response of the model names
    none."""
    if row.record.get("type") != "assistant":
        return None
    return _response_key(row)
