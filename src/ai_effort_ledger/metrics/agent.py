"""The turns of the agents, their parts of agent time, and the blocked time of their
decision requests (metrics.md › Agent time, › Blocked time).

An agent is an agent tool with a session and the agent that the session names, and a
subagent has its own turns, from its own events. The agent time of a turn is its duration
without its blocked time and without the time in which it waits for its own subagents: a
wait for a subagent is the interval from a tool call of the category `delegate` that
`parameters.category` gives to its tool result, found by the category and the `call_id`,
never by a tool name, and never by `subagent_mode` (ruled 2026-11-20). A call that gets no
tool result and a request that gets no decision wait until the next event of their agent,
an interruption, or the last event of the session. The figures are milliseconds since the
epoch (decision D12), and the stale limit and the durations of the parameters are whole
seconds.
"""

from bisect import bisect_right
from collections.abc import Callable, Sequence
from typing import NamedTuple

from ..events import Event
from .human import MetricsParameters, _stream_order, instant_ms
from .spans import Span, union

Agent = tuple[str, str, str]
"""An agent of a session: its agent tool, its session, and the agent that the session
names (`event-schema.md` › Fields)."""

INPUTS = frozenset({"prompt", "queued_message", "tool_result", "notification"})
"""The kinds of event that reach an agent as an input (metrics.md › Agent time)."""

CLOSERS = frozenset({"interruption", "session_end"})
"""The kinds of event that end a turn in progress: an interruption and the end of the
session (metrics.md › Agent time)."""


class Turn(NamedTuple):
    """One turn of one agent: the agent as the triple of its tool, its session, and the
    agent that the session names, and the limits of the turn in milliseconds, from the
    input that started it to its last agent output before the agent waits for a prompt or
    a notification, to an interruption, to the end of the session, or to its last event at
    the stale limit (GLOSSARY › Turn)."""

    agent: Agent
    start: int
    end: int


class AgentPart(NamedTuple):
    """One part of the agent time of a turn: the interval between two consecutive events
    of the turn, without the parts that the blocked time of the agent or a wait for its
    own subagents covers, with the event that ends it (metrics.md › Attribution)."""

    start: int
    end: int
    agent: Agent
    event: Event


class BlockedInterval(NamedTuple):
    """One interval of blocked time: from a decision request to the decision that answers
    it, or to the instant at which the request waits without an answer (metrics.md ›
    Blocked time). The attribution of the interval is that of its request."""

    start: int
    end: int
    request: Event


def turns(events: Sequence[Event], stale_limit: int) -> list[Turn]:
    """The turns of the events, of every agent of every session, each with its limits in
    milliseconds; the stale limit is in whole seconds (metrics.md › Agent time). A turn
    with no event for longer than the stale limit ends at its last event, and a turn open
    at the last event of the stream ends there."""
    ordered = sorted(events, key=_stream_order)
    found = [Turn(agent, start, end)
             for agent, stream in _streams(ordered).items()
             for start, end, _ in _turns_of(stream, stale_limit * 1000)]
    found.sort(key=lambda turn: (turn.start, turn.end, turn.agent))
    return found


def agent_parts(events: Sequence[Event], parameters: MetricsParameters) -> list[AgentPart]:
    """The parts of agent time of the turns of the events (metrics.md › Attribution): for
    each turn, the interval between two consecutive events of the turn, without the parts
    that the blocked time of the agent or a wait for its own subagents covers. A wait never
    splits a part: a delegate wait begins and ends at events of the same turn, so any
    overlap with a turn covers whole parts, and a session-fallback wait lies after the end
    of the turn. The waits of each stream are unioned once, and each part asks only the
    first of them that can reach it, found by a search over their ends."""
    ordered = sorted(events, key=_stream_order)
    lasts = _last_of_sessions(ordered)
    parts: list[AgentPart] = []
    for agent, stream in _streams(ordered).items():
        end_of_session = _last_of_session(stream, lasts)
        waits = union(
            _delegate_waits(stream, parameters.category, end_of_session)
            + [(blocked.start, blocked.end)
               for blocked in _blocked_of_stream(stream, end_of_session)])
        wait_ends = [end for _, end in waits]
        for _, _, held in _turns_of(stream, parameters.stale_limit * 1000):
            for earlier, later in zip(held, held[1:]):
                begin, finish = instant_ms(earlier), instant_ms(later)
                if finish <= begin or _in_waits(waits, wait_ends, begin, finish):
                    continue
                parts.append(AgentPart(begin, finish, agent, later))
    parts.sort(key=lambda part: (part.start, part.end, part.agent))
    return parts


def _in_waits(waits: Sequence[Span], ends: Sequence[int], begin: int, finish: int) -> bool:
    """Whether one of the sorted, disjoint waits of a stream shares an instant with the
    interval: the first wait that ends after the begin of the interval is the only one that
    can reach it, and it does when it starts before the interval ends. The waits come from
    `union`, so they are sorted and disjoint and their ends rise with them; `ends` holds
    those ends, parallel to `waits`."""
    at = bisect_right(ends, begin)
    return at < len(waits) and waits[at][0] < finish


def blocked_intervals(events: Sequence[Event]) -> list[BlockedInterval]:
    """The blocked time of the events, of every agent of every session (metrics.md ›
    Blocked time): from each decision request to the first decision of the same `call_id`
    that follows it, or to the instant at which the request waits without an answer."""
    ordered = sorted(events, key=_stream_order)
    lasts = _last_of_sessions(ordered)
    found = [blocked
             for stream in _streams(ordered).values()
             for blocked in _blocked_of_stream(stream, _last_of_session(stream, lasts))]
    found.sort(key=lambda blocked: (blocked.start, blocked.end, _stream_order(blocked.request)))
    return found


def _agent_of(event: Event) -> Agent:
    """The agent that an event of a session belongs to: its agent tool, its session, and
    the agent that the session names; an absent `agent_id` falls back to the session,
    which is the agent of the main agent (`event-schema.md` › Fields)."""
    session = event.get("session_id")
    agent_id = event.get("agent_id")
    return (event.get("tool"), session, session if agent_id is None else agent_id)


def _streams(ordered: Sequence[Event]) -> dict[Agent, list[Event]]:
    """The events of a session, grouped by the agent each belongs to, in the order of the
    stream; the events of no session — manual entries, timesheet confirmations, the
    bookkeeping of the ledger — hold no turn and no blocked time (metrics.md › Agent
    time)."""
    streams: dict[Agent, list[Event]] = {}
    for event in ordered:
        if event.get("session_id") is None:
            continue
        streams.setdefault(_agent_of(event), []).append(event)
    return streams


def _last_of_sessions(ordered: Sequence[Event]) -> dict[tuple[str | None, str | None], int]:
    """The instant, in milliseconds, of the last event of each session: a call or a
    request that gets no answer waits until the last event of its session (metrics.md ›
    Agent time, › Blocked time)."""
    last: dict[tuple[str | None, str | None], int] = {}
    for event in ordered:
        if event.get("session_id") is not None:
            last[(event.get("tool"), event.get("session_id"))] = instant_ms(event)
    return last


def _last_of_session(
    stream: Sequence[Event],
    lasts: dict[tuple[str | None, str | None], int],
) -> int:
    """The instant of the last event of the session of the stream."""
    return lasts[(stream[0].get("tool"), stream[0].get("session_id"))]


def _wait_end(stream: Sequence[Event], position: int, end_of_session: int) -> int:
    """The instant at which a call or a request that gets no answer stops waiting: the
    next event of its agent, or, when no event of the agent follows, the last event of its
    session (metrics.md › Agent time, › Blocked time)."""
    if position + 1 < len(stream):
        return instant_ms(stream[position + 1])
    return end_of_session


def _answers(stream: Sequence[Event], kind: str) -> dict[str, list[tuple[int, int]]]:
    """The positions and instants, in the order of the stream, of the events of the kind
    that a `call_id` links to a call or a request of the same agent."""
    linked: dict[str, list[tuple[int, int]]] = {}
    for position, event in enumerate(stream):
        if event["kind"] != kind:
            continue
        call_id = event.get("call_id")
        if isinstance(call_id, str):
            linked.setdefault(call_id, []).append((position, instant_ms(event)))
    return linked


def _first_answer(
    linked: dict[str, list[tuple[int, int]]],
    call_id: str | None,
    position: int,
) -> int | None:
    """The instant of the first linked event of the `call_id` that follows the position in
    the stream, or None when none follows it."""
    if not isinstance(call_id, str):
        return None
    return next((moment for at, moment in linked.get(call_id, []) if at > position), None)


def _turns_of(stream: Sequence[Event], stale_ms: int) -> list[tuple[int, int, list[Event]]]:
    """The turns of the stream of one agent, each with its limits in milliseconds and its
    events in the order of the stream: the events from the input that started the turn to
    the event that ends it (metrics.md › Agent time). The stream is whole when the turns
    are computed, so the stream itself tells which calls still wait: one pass collects
    the positions of the `tool_result` events by their `call_id`, and a tool call
    compares its own position with them. A call whose `call_id` names a result later in
    the stream is ordinary: it joins the pending set, only its own result removes it, and
    an output leaves it, since it still waits. A call whose `call_id` names no result
    later in the stream is one that the provider runs inside the response, which gets no
    tool result and is complete with its response (claude-code-adapter.md › Records and
    events): it waits only until the next agent output, and an output at its own instant
    has already completed it, also when no turn is open at that output — the order of the
    event keys places that output before the call, since the identifier of the response
    sorts before `tool_call:…`. An output that arrives while no turn is open — a stream
    that begins in the middle of a session, or a closer that lands between the output and
    the call — is remembered too, and only a later output replaces it (ruled 2026-11-27):
    the call of its own instant is complete, while a turn still ends at its own last
    output, never at one from before it. A call whose `call_id` is absent or is no text
    waits until the next output in the same way, since no result can name it. A tool
    result whose `call_id` is absent or is no text removes nothing, and one that names no
    pending call removes nothing. A prompt or a notification closes the turn only when no
    call of either kind waits."""
    turns: list[tuple[int, int, list[Event]]] = []
    start: int | None = None
    last: int | None = None
    output: int | None = None
    last_output: int | None = None
    results = _answers(stream, "tool_result")
    pending: set[str] = set()
    unanswered: set[int] = set()
    held: list[Event] = []
    for position, event in enumerate(stream):
        moment = instant_ms(event)
        if start is not None and moment - last > stale_ms:
            _close(turns, start, last, held)
            start, output, pending, unanswered, held = None, None, set(), set(), []
        kind = event["kind"]
        if start is not None and kind in CLOSERS:
            held.append(event)
            _close(turns, start, moment, held)
            start, output, pending, unanswered, held = None, None, set(), set(), []
        elif kind in INPUTS:
            if kind == "tool_result":
                call_id = event.get("call_id")
                if isinstance(call_id, str):
                    pending.discard(call_id)
            if start is None:
                start, held = moment, [event]
            elif kind in ("prompt", "notification") and not pending and not unanswered:
                _close(turns, start, output if output is not None else last, held)
                start, output, held = moment, None, [event]
            else:
                held.append(event)
        elif kind == "tool_call":
            call_id = event.get("call_id")
            answered = _first_answer(results, call_id, position)
            if isinstance(call_id, str) and answered is not None:
                pending.add(call_id)
            elif last_output != moment:
                unanswered.add(position)
            if start is None:
                start, held = moment, [event]
            else:
                held.append(event)
        elif kind == "agent_output":
            unanswered.clear()
            last_output = moment
            if start is not None:
                output = moment
                held.append(event)
        elif start is not None:
            held.append(event)
        last = moment
    _close(turns, start, last, held)
    return turns


def _close(
    turns: list[tuple[int, int, list[Event]]],
    start: int | None,
    end: int | None,
    held: list[Event],
) -> None:
    """Record the turn that ends at the given instant, when it holds time, with its events
    up to that instant: an event after the output that ends the turn ends no part of it,
    and a turn with no duration holds no agent time and no part."""
    if start is not None and end is not None and start < end:
        turns.append((start, end, [event for event in held if instant_ms(event) <= end]))


def _delegate_waits(
    stream: Sequence[Event],
    category: Callable[[Event], str],
    end_of_session: int,
) -> list[Span]:
    """The waits for the own subagents of the stream (metrics.md › Agent time): from each
    tool call of the category that `category` gives to the first result of the same
    `call_id` that follows it, or, when no result follows, to the instant that a call
    without a result reaches."""
    results = _answers(stream, "tool_result")
    waits: list[Span] = []
    for position, event in enumerate(stream):
        if event["kind"] != "tool_call" or category(event) != "delegate":
            continue
        answered = _first_answer(results, event.get("call_id"), position)
        end = answered if answered is not None else _wait_end(stream, position, end_of_session)
        waits.append((instant_ms(event), end))
    return waits


def _blocked_of_stream(stream: Sequence[Event], end_of_session: int) -> list[BlockedInterval]:
    """The blocked time of the stream of one agent (metrics.md › Blocked time): from each
    decision request to the first decision of the same `call_id` that follows it, or, when
    no decision follows, to the instant that a request without a decision reaches."""
    made = _answers(stream, "decision")
    blocked: list[BlockedInterval] = []
    for position, event in enumerate(stream):
        if event["kind"] != "decision_request":
            continue
        answered = _first_answer(made, event.get("call_id"), position)
        end = answered if answered is not None else _wait_end(stream, position, end_of_session)
        blocked.append(BlockedInterval(instant_ms(event), end, event))
    return blocked
