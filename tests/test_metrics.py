"""Tests of the metrics module: the spans, the human signals, the three kinds of interval
of measured human time at the idle gaps and inside the window of a day (metrics.md › Human
time, › Uncertainty, ADR 0021), the turns with their parts of agent time and the blocked
time of the agents (metrics.md › Agent time, › Blocked time), the parts that the manual
entries count against the measured human time (metrics.md › Declared values), and the
activity classes of the person (metrics.md › Activity classes)."""

import json
import unittest
from collections.abc import Sequence
from itertools import count
from typing import Any

import support
from ai_effort_ledger import adapters
from ai_effort_ledger.adapters import claude_code
from ai_effort_ledger.events import (
    SCHEMA_VERSION,
    Event,
    decode_line,
    event_order,
    format_instant,
)
from ai_effort_ledger.metrics import (
    AgentPart,
    BlockedInterval,
    HumanInterval,
    ManualPart,
    Metrics,
    MetricsParameters,
    Span,
    Turn,
    activity_classes,
    agent_parts,
    blocked_intervals,
    compute_metrics,
    human_intervals,
    human_signals,
    human_time_at_idle_gaps,
    instant_ms,
    intersect,
    manual_parts,
    presence_span,
    stored_category,
    stream_of,
    subtract,
    total,
    total_by_key,
    turns,
    union,
    unknown_invocation_share,
)

_ACTOR_BY_KIND = {
    "prompt": "human",
    "queued_message": "human",
    "interruption": "human",
    "decision": "human",
    "decision_request": "agent",
    "agent_output": "agent",
    "notification": "system",
    "tool_call": "agent",
    "tool_result": "system",
    "session_end": "system",
    "session_start": "system",
}
_UIDS = count(1)


def ms(instant: str) -> int:
    """The instant as milliseconds since the epoch, the unit of a span."""
    return round(support.utc(instant).timestamp() * 1000)


def window_of(start: str, end: str) -> Span:
    """One span of the window, from the start instant to the end instant."""
    return (ms(start), ms(end))


DAY = [window_of("2026-11-10T00:00", "2026-11-11T00:00")]
"""The window of one whole day, in which every interval of the tests falls."""

AGENT = ("claude-code", "s-one", "s-one")
"""The identity of the main agent of the fixtures: its tool, its session, the agent."""

SUBAGENT = ("claude-code", "s-one", "agent-1")
"""The identity of the subagent of the fixtures, of the session of the main agent."""

_TIE_SESSION = "aaaaaaaa-aaaa-5aaa-9aaa-aaaaaaaaaaaa"
"""The session of the records of the tie, which the adapter gives to every event."""

_TIE_AGENT = ("claude-code", _TIE_SESSION, _TIE_SESSION)
"""The identity of the main agent of the records of the tie: its tool, session, agent."""


def tie_records() -> list[adapters.SessionRecord]:
    """The records of one session whose middle response is one record that holds its text
    and the `server_tool_use` of its `web_search`, the shape that the adapter documents
    for a tool that the provider runs: prompts of the person at 09:00, 09:10, and 09:20;
    responses at 09:01, 09:11, and 09:21 (claude-code-adapter.md › Records and events)."""
    lines = [
        (1, "2026-11-19T09:00:00.000Z", "user",
         {"role": "user", "content": "Find the rows that miss a project."}),
        (2, "2026-11-19T09:01:00.000Z", "assistant",
         {"id": "msg_a", "model": "Invented-Model", "usage": {},
          "content": [{"type": "text", "text": "The rows sit in the report."}]}),
        (3, "2026-11-19T09:10:00.000Z", "user",
         {"role": "user", "content": "Now search the ledger for them."}),
        (4, "2026-11-19T09:11:00.000Z", "assistant",
         {"id": "msg_b", "model": "Invented-Model", "usage": {},
          "content": [{"type": "text", "text": "The search runs inside the report."},
                      {"type": "server_tool_use", "id": "srvtool_01", "name": "web_search",
                       "input": {"query": "invented"}}]}),
        (5, "2026-11-19T09:20:00.000Z", "user",
         {"role": "user", "content": "And what does the web hold?"}),
        (6, "2026-11-19T09:21:00.000Z", "assistant",
         {"id": "msg_c", "model": "Invented-Model", "usage": {},
          "content": [{"type": "text", "text": "The web holds the same rows."}]}),
    ]
    return [adapters.SessionRecord("", 0, number, {
        "type": kind, "uuid": f"3f1c0000-0000-4000-8000-{number:012x}",
        "timestamp": instant, "sessionId": _TIE_SESSION, "entrypoint": "cli",
        "message": message})
        for number, instant, kind, message in lines]


_CORNER_SESSION = "bbbbbbbb-bbbb-5bbb-9bbb-bbbbbbbbbbbb"
"""The session of the records of the corner, which the adapter gives to every event."""

_CORNER_AGENT = ("claude-code", _CORNER_SESSION, _CORNER_SESSION)
"""The identity of the main agent of the records of the corner: its tool, its session, and
the agent that the session names."""


def corner_records() -> list[adapters.SessionRecord]:
    """The records of a session that the store holds from its middle, so its first record is
    already a response: that response of 09:00 carries the `server_tool_use` of the
    `web_search` that the provider runs inside it, the prompt of the person follows at 09:10,
    and the last response at 09:11 (claude-code-adapter.md › Records and events)."""
    lines = [
        (1, "2026-11-19T09:00:00.000Z", "assistant",
         {"id": "msg_a", "model": "Invented-Model", "usage": {},
          "content": [{"type": "text", "text": "The ledger holds the rows of the report."},
                      {"type": "server_tool_use", "id": "srvtool_01", "name": "web_search",
                       "input": {"query": "invented"}}]}),
        (2, "2026-11-19T09:10:00.000Z", "user",
         {"role": "user", "content": "And which of the rows miss a project?"}),
        (3, "2026-11-19T09:11:00.000Z", "assistant",
         {"id": "msg_b", "model": "Invented-Model", "usage": {},
          "content": [{"type": "text", "text": "The rows that miss it sit at the end."}]}),
    ]
    return [adapters.SessionRecord("", 0, number, {
        "type": kind, "uuid": f"4e2d0000-0000-4000-8000-{number:012x}",
        "timestamp": instant, "sessionId": _CORNER_SESSION, "entrypoint": "cli",
        "message": message})
        for number, instant, kind, message in lines]


def event(kind: str, instant: str, session_id: str = "s-one", **fields: Any) -> Event:
    """An event with the fields that the metrics reads; the other fields are invented."""
    moment = format_instant(support.utc(instant))
    base: Event = {
        "schema_version": SCHEMA_VERSION,
        "source": "test-source",
        "event_uid": f"uid-{next(_UIDS)}",
        "timestamp": moment,
        "ingested_at": moment,
        "writer_version": "0.1.0.dev0",
        "actor": _ACTOR_BY_KIND[kind],
        "kind": kind,
        "machine": "machine-1",
        "tool": "claude-code",
        "session_id": session_id,
        "invocation": "interactive",
    }
    base.update(fields)
    return base


def parameters(idle_gap: int = 600, headless_prompts: bool = False) -> MetricsParameters:
    """The parameters at the defaults of the spec: idle gap 10 minutes, minimum attention
    1 minute, stale limit 4 hours, each in whole seconds."""
    return MetricsParameters(idle_gap=idle_gap, minimum_attention=60, stale_limit=14400,
                             headless_prompts=headless_prompts)


def manual_entry(start: str, end: str, mode: str = "overlapping", **fields: Any) -> Event:
    """A manual entry of the fixtures: the interval that the person declares, with its mode
    and its fields; a command writes it, so it has no session."""
    moment = format_instant(support.utc(start))
    made: Event = {
        "schema_version": SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": f"uid-{next(_UIDS)}",
        "timestamp": moment,
        "ingested_at": moment,
        "writer_version": "0.1.0.dev0",
        "actor": "human",
        "kind": "manual_entry",
        "machine": "machine-1",
        "start": format_instant(support.utc(start)),
        "end": format_instant(support.utc(end)),
        "manual_mode": mode,
        "project": "project-a",
    }
    made.update(fields)
    return made


class SpanTests(unittest.TestCase):
    """The union, the intersection, the difference, and the total of spans."""

    def test_span_operations(self) -> None:
        """Overlapping and touching spans merge, empty spans disappear, the results are
        sorted and disjoint, and an instant counts once in the total."""
        self.assertEqual(union([(400, 500), (100, 200), (150, 300)]),
                         [(100, 300), (400, 500)])
        self.assertEqual(union([(0, 100), (100, 200)]), [(0, 200)])
        self.assertEqual(union([(50, 50)]), [])
        self.assertEqual(union([]), [])
        self.assertEqual(intersect([(0, 100), (200, 300)], [(50, 150), (250, 350)]),
                         [(50, 100), (250, 300)])
        self.assertEqual(intersect([(0, 100), (200, 300)], [(50, 250)]),
                         [(50, 100), (200, 250)])
        self.assertEqual(intersect([(0, 100)], [(100, 200)]), [])
        self.assertEqual(subtract([(0, 100), (200, 300)], [(50, 150), (250, 350)]),
                         [(0, 50), (200, 250)])
        self.assertEqual(subtract([(0, 100)], [(100, 200)]), [(0, 100)])
        self.assertEqual(subtract([(0, 100)], [(0, 100)]), [])
        self.assertEqual(total([(200, 300), (0, 100)]), 200)
        self.assertEqual(total([(0, 100), (50, 150)]), 150)
        self.assertEqual(total([]), 0)
        self.assertEqual(intersect([], [(0, 100)]), [])
        self.assertEqual(subtract([(0, 100)], []), [(0, 100)])

    def test_total_by_key(self) -> None:
        """The sum over the keys of the total of the spans of each key: nothing gives 0;
        the spans of one key give their total, 100 + 50 = 150; the spans of two keys that
        overlap give the sum of their totals, 100 + 100 = 200, and not the total of their
        union, 150; the parts of one key that touch or overlap count once, 200 and 150;
        and a part that a window cuts in two, 0-40 and 60-100, gives the length of its two
        pieces, 80 (metrics.md › Agent time)."""
        self.assertEqual(total_by_key([]), 0)
        self.assertEqual(total_by_key([((0, 100), "one"), ((150, 200), "one")]), 150)
        self.assertEqual(total_by_key([((0, 100), "one"), ((50, 150), "two")]), 200)
        self.assertEqual(total_by_key([((0, 100), "one"), ((100, 200), "one")]), 200)
        self.assertEqual(total_by_key([((0, 100), "one"), ((50, 150), "one")]), 150)
        self.assertEqual(total_by_key([((0, 40), "one"), ((60, 100), "one")]), 80)


class HumanSignalTests(unittest.TestCase):
    """The events that show that a person attended to the work."""

    def test_rule_decision_is_no_signal(self) -> None:
        """A decision that a configured rule made is no human signal, and the decision
        request before the only prompt starts the response interval that the prompt ends."""
        request = event("decision_request", "2026-11-10T10:00")
        ruled = event("decision", "2026-11-10T10:02", actor="system")
        prompt = event("prompt", "2026-11-10T10:05")
        self.assertEqual(human_signals([request, ruled, prompt], False), [prompt])
        self.assertEqual(human_intervals([request, ruled, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T10:00"), ms("2026-11-10T10:05"), prompt, "response"),
        ])

    def test_headless_prompts_parameter(self) -> None:
        """With headless prompts, the notifications of scripted input in sessions of headless
        invocation are signals; by default they are none, and a task notification is no
        signal at any setting."""
        typed = [
            event("notification", "2026-11-10T09:00", input_origin="scripted",
                  invocation="headless"),
            event("notification", "2026-11-10T09:05", input_origin="scripted",
                  invocation="headless"),
            event("notification", "2026-11-10T09:10", input_origin="task_notification"),
        ]
        counting = parameters(headless_prompts=True)
        self.assertEqual(human_signals(typed, True), [typed[0], typed[1]])
        self.assertEqual(human_intervals(typed, counting), [
            HumanInterval(ms("2026-11-10T08:59"), ms("2026-11-10T09:00"), typed[0],
                          "minimum_attention"),
            HumanInterval(ms("2026-11-10T09:00"), ms("2026-11-10T09:05"), typed[1],
                          "signal_gap"),
        ])
        self.assertEqual(human_signals(typed, False), [])
        self.assertEqual(human_intervals(typed, parameters()), [])

    def test_headless_prompt_holds_both_marks(self) -> None:
        """A headless prompt is the notification with `input_origin` `scripted` of a
        session of headless invocation, and the two marks hold together
        (`event-schema.md` › Keys and invariants): with headless prompts counted, the
        scripted notification of a session of interactive invocation and the notification
        of `input_origin` `parent` of a session of headless invocation are no human
        signal — the notification that holds both marks is the only one."""
        typed = event("notification", "2026-11-10T09:00", input_origin="scripted",
                      invocation="interactive")
        from_parent = event("notification", "2026-11-10T09:05", input_origin="parent",
                            invocation="headless")
        headless = event("notification", "2026-11-10T09:10", input_origin="scripted",
                         invocation="headless")
        self.assertEqual(human_signals([typed, from_parent, headless], True), [headless])
        self.assertEqual(
            human_intervals([typed, from_parent, headless], parameters(headless_prompts=True)),
            [HumanInterval(ms("2026-11-10T09:09"), ms("2026-11-10T09:10"), headless,
                           "minimum_attention")])


class HumanIntervalTests(unittest.TestCase):
    """The three kinds of interval of measured human time."""

    def test_signal_gap(self) -> None:
        """Prompts at 09:00 and 09:05 give a signal gap of 5 minutes that belongs to the
        later prompt and a minimum attention of 1 minute to the first prompt, which ends no
        interval: 6 minutes of human time at every idle gap."""
        first = event("prompt", "2026-11-10T09:00")
        second = event("prompt", "2026-11-10T09:05")
        intervals = human_intervals([second, first], parameters())
        self.assertEqual(intervals, [
            HumanInterval(ms("2026-11-10T08:59"), ms("2026-11-10T09:00"), first,
                          "minimum_attention"),
            HumanInterval(ms("2026-11-10T09:00"), ms("2026-11-10T09:05"), second,
                          "signal_gap"),
        ])
        self.assertEqual(human_time_at_idle_gaps(stream_of([first, second]), parameters(), DAY),
                         {300: 360000, 600: 360000, 900: 360000})

    def test_gap_longer_than_idle_gap(self) -> None:
        """Prompts 11 minutes apart give no signal gap at the idle gap of 10 minutes: two
        minimum attentions of 1 minute each. At the idle gap of 15 minutes the prompts hold
        a signal gap, and the union counts 12 minutes."""
        first = event("prompt", "2026-11-10T09:00")
        second = event("prompt", "2026-11-10T09:11")
        self.assertEqual(human_intervals([first, second], parameters()), [
            HumanInterval(ms("2026-11-10T08:59"), ms("2026-11-10T09:00"), first,
                          "minimum_attention"),
            HumanInterval(ms("2026-11-10T09:10"), ms("2026-11-10T09:11"), second,
                          "minimum_attention"),
        ])
        self.assertEqual(human_time_at_idle_gaps(stream_of([first, second]), parameters(), DAY),
                         {300: 120000, 600: 120000, 900: 720000})

    def test_response_interval(self) -> None:
        """An output of the main agent at 10:30 and the prompt at 10:34 of the same session
        give a response interval of 4 minutes, and the output is no signal."""
        output = event("agent_output", "2026-11-10T10:30")
        prompt = event("prompt", "2026-11-10T10:34")
        self.assertEqual(human_signals([output, prompt], False), [prompt])
        self.assertEqual(human_intervals([output, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T10:30"), ms("2026-11-10T10:34"), prompt, "response"),
        ])
        self.assertEqual(human_time_at_idle_gaps(stream_of([output, prompt]), parameters(), DAY),
                         {300: 240000, 600: 240000, 900: 240000})

    def test_background_output_starts_no_response(self) -> None:
        """An output of a background subagent starts no response interval: the prompt that
        follows it counts only its minimum attention."""
        output = event("agent_output", "2026-11-10T10:30", subagent_mode="background")
        prompt = event("prompt", "2026-11-10T10:34")
        self.assertEqual(human_intervals([output, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T10:33"), ms("2026-11-10T10:34"), prompt,
                          "minimum_attention"),
        ])

    def test_absent_mode_starts_response(self) -> None:
        """A subagent whose `subagent_mode` is absent counts as a foreground subagent: its
        output starts the response interval that the following prompt ends."""
        output = event("agent_output", "2026-11-10T10:30", agent_id="agent-1")
        prompt = event("prompt", "2026-11-10T10:34")
        self.assertEqual(human_intervals([output, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T10:30"), ms("2026-11-10T10:34"), prompt, "response"),
        ])

    def test_decision_request_starts_response(self) -> None:
        """A decision request starts a response interval like an output does."""
        request = event("decision_request", "2026-11-10T10:30")
        prompt = event("prompt", "2026-11-10T10:34")
        self.assertEqual(human_intervals([request, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T10:30"), ms("2026-11-10T10:34"), prompt, "response"),
        ])

    def test_response_interval_longer_than_idle_gap(self) -> None:
        """A signal that follows the output of its session after more than the idle gap
        starts no response interval: the prompt of 09:11 holds only its minimum attention."""
        output = event("agent_output", "2026-11-10T09:00")
        prompt = event("prompt", "2026-11-10T09:11")
        self.assertEqual(human_intervals([output, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T09:10"), ms("2026-11-10T09:11"), prompt,
                          "minimum_attention"),
        ])

    def test_response_interval_at_the_idle_gap(self) -> None:
        """A signal that follows the output of its session at exactly the idle gap holds
        its response interval, for the gap is not longer than the idle gap (metrics.md ›
        Human time): the 10 minutes from the output of 10:00 to the prompt of 10:10 are
        human time at the idle gap of 10 minutes and at 15 minutes, while at the idle gap
        of 5 minutes the gap is longer than it and the prompt holds only its minimum
        attention."""
        output = event("agent_output", "2026-11-10T10:00")
        prompt = event("prompt", "2026-11-10T10:10")
        self.assertEqual(human_intervals([output, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T10:00"), ms("2026-11-10T10:10"), prompt, "response"),
        ])
        self.assertEqual(human_time_at_idle_gaps(stream_of([output, prompt]), parameters(), DAY),
                         {300: 60000, 600: 600000, 900: 600000})

    def test_response_interval_for_each_signal(self) -> None:
        """Two signals of the same session that follow one output each hold their own
        response interval, and both run from the same output."""
        output = event("agent_output", "2026-11-10T09:00")
        first = event("prompt", "2026-11-10T09:02")
        second = event("prompt", "2026-11-10T09:04")
        self.assertEqual(human_intervals([second, output, first], parameters()), [
            HumanInterval(ms("2026-11-10T09:00"), ms("2026-11-10T09:02"), first, "response"),
            HumanInterval(ms("2026-11-10T09:00"), ms("2026-11-10T09:04"), second, "response"),
            HumanInterval(ms("2026-11-10T09:02"), ms("2026-11-10T09:04"), second,
                          "signal_gap"),
        ])

    def test_response_pairing_keys_on_tool_and_session(self) -> None:
        """The output of one agent tool starts no response interval for the signal of
        another agent tool that gives the same session identifier: two sources record the
        same session when they give the same tool and the same session identifier
        (`event-schema.md` › Keys and invariants)."""
        output = event("agent_output", "2026-11-10T09:00", tool="claude-code")
        prompt = event("prompt", "2026-11-10T09:02", tool="claude-desktop")
        self.assertEqual(human_intervals([output, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T09:01"), ms("2026-11-10T09:02"), prompt,
                          "minimum_attention"),
        ])

    def test_queued_message_and_interruption_are_signals(self) -> None:
        """A queued message and an interruption are human signals, and they hold a signal
        gap between them."""
        queued = event("queued_message", "2026-11-10T09:00")
        stopped = event("interruption", "2026-11-10T09:05")
        self.assertEqual(human_signals([queued, stopped], False), [queued, stopped])
        self.assertEqual(human_intervals([queued, stopped], parameters()), [
            HumanInterval(ms("2026-11-10T08:59"), ms("2026-11-10T09:00"), queued,
                          "minimum_attention"),
            HumanInterval(ms("2026-11-10T09:00"), ms("2026-11-10T09:05"), stopped,
                          "signal_gap"),
        ])

    def test_human_decision_is_a_signal(self) -> None:
        """A decision that the person made is a human signal."""
        answered = event("decision", "2026-11-10T09:00")
        prompt = event("prompt", "2026-11-10T09:05")
        self.assertEqual(human_signals([answered, prompt], False), [answered, prompt])
        self.assertEqual(human_intervals([answered, prompt], parameters()), [
            HumanInterval(ms("2026-11-10T08:59"), ms("2026-11-10T09:00"), answered,
                          "minimum_attention"),
            HumanInterval(ms("2026-11-10T09:00"), ms("2026-11-10T09:05"), prompt,
                          "signal_gap"),
        ])

    def test_one_stream_across_sessions(self) -> None:
        """The signals of two sessions form one stream, so the four prompts of two parallel
        sessions count 7 minutes, and not the 10 minutes of the two sessions added up."""
        first = event("prompt", "2026-11-10T09:00", session_id="s-one")
        second = event("prompt", "2026-11-10T09:02", session_id="s-two")
        third = event("prompt", "2026-11-10T09:04", session_id="s-one")
        fourth = event("prompt", "2026-11-10T09:06", session_id="s-two")
        events: Sequence[Event] = [fourth, third, second, first]
        self.assertEqual(human_signals(events, False), [first, second, third, fourth])
        self.assertEqual(human_intervals(events, parameters()), [
            HumanInterval(ms("2026-11-10T08:59"), ms("2026-11-10T09:00"), first,
                          "minimum_attention"),
            HumanInterval(ms("2026-11-10T09:00"), ms("2026-11-10T09:02"), second,
                          "signal_gap"),
            HumanInterval(ms("2026-11-10T09:02"), ms("2026-11-10T09:04"), third,
                          "signal_gap"),
            HumanInterval(ms("2026-11-10T09:04"), ms("2026-11-10T09:06"), fourth,
                          "signal_gap"),
        ])
        self.assertEqual(human_time_at_idle_gaps(stream_of(events), parameters(), DAY),
                         {300: 420000, 600: 420000, 900: 420000})


class InstantMsTests(unittest.TestCase):
    """The milliseconds of an instant text, the unit of every span of the human time."""

    def test_instant_ms_keeps_the_milliseconds(self) -> None:
        """The instant of an event at the half second is the half second, and two prompts
        500 ms apart hold a signal gap of 500 ms between them: a figure of the human time
        depends on the milliseconds of the instant text (metrics.md › Human time)."""
        moment = ms("2026-11-10T09:00:00.000Z")
        early = event("prompt", "2026-11-10T09:00:00.000Z")
        late = event("prompt", "2026-11-10T09:00:00.500Z")
        self.assertEqual(instant_ms(late), moment + 500)
        gaps = [held for held in human_intervals([early, late], parameters())
                if held.kind == "signal_gap"]
        self.assertEqual([(held.start, held.end) for held in gaps], [(moment, moment + 500)])


class AgentTimeTests(unittest.TestCase):
    """The turns, their parts of agent time, and the blocked time of the agents."""

    def test_turn_from_input_to_last_output(self) -> None:
        """A turn runs from the prompt that reaches an agent with no turn in progress to
        the output before which the agent waits for the next prompt with no tool call
        pending (metrics.md › Agent time): the prompt of 09:10 starts no new turn that
        holds time."""
        prompt = event("prompt", "2026-11-10T09:00")
        output = event("agent_output", "2026-11-10T09:05")
        again = event("prompt", "2026-11-10T09:10")
        self.assertEqual(turns([again, output, prompt], 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:05")),
        ])

    def test_tool_execution_is_part_of_turn(self) -> None:
        """The tool result that arrives while a turn is in progress continues it, so the
        execution of the tool of 09:02 to 09:03 is part of the turn that the prompt of
        09:00 started, and every interval between two consecutive events is a part
        (metrics.md › Agent time, › Attribution)."""
        prompt = event("prompt", "2026-11-10T09:00")
        output = event("agent_output", "2026-11-10T09:01")
        call = event("tool_call", "2026-11-10T09:02", tool_category="execute", call_id="c-1")
        result = event("tool_result", "2026-11-10T09:03", call_id="c-1")
        done = event("agent_output", "2026-11-10T09:04")
        again = event("prompt", "2026-11-10T09:10")
        events = [done, again, call, prompt, output, result]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:04")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:01"), AGENT, output),
            AgentPart(ms("2026-11-10T09:01"), ms("2026-11-10T09:02"), AGENT, call),
            AgentPart(ms("2026-11-10T09:02"), ms("2026-11-10T09:03"), AGENT, result),
            AgentPart(ms("2026-11-10T09:03"), ms("2026-11-10T09:04"), AGENT, done),
        ])

    def test_interruption_ends_turn(self) -> None:
        """A turn ends at an interruption, at the instant of the interruption and not at
        the last output before it, and the part that the interruption ends is agent time
        (metrics.md › Agent time)."""
        prompt = event("prompt", "2026-11-10T09:00")
        output = event("agent_output", "2026-11-10T09:01")
        call = event("tool_call", "2026-11-10T09:02", tool_category="execute", call_id="c-1")
        stopped = event("interruption", "2026-11-10T09:03")
        again = event("prompt", "2026-11-10T09:10")
        events = [again, stopped, call, output, prompt]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:03")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:01"), AGENT, output),
            AgentPart(ms("2026-11-10T09:01"), ms("2026-11-10T09:02"), AGENT, call),
            AgentPart(ms("2026-11-10T09:02"), ms("2026-11-10T09:03"), AGENT, stopped),
        ])

    def test_stale_turn_ends_at_last_event(self) -> None:
        """A turn with no event for longer than the stale limit of 4 hours ends at its last
        event: the prompt of 08:00 and the call of 08:01 hold one turn, the result of 13:00
        starts another, which the output of 13:01 ends — two turns of 1 minute."""
        prompt = event("prompt", "2026-11-10T08:00")
        call = event("tool_call", "2026-11-10T08:01", tool_category="execute", call_id="c-1")
        result = event("tool_result", "2026-11-10T13:00", call_id="c-1")
        done = event("agent_output", "2026-11-10T13:01")
        events = [prompt, call, result, done]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T08:00"), ms("2026-11-10T08:01")),
            Turn(AGENT, ms("2026-11-10T13:00"), ms("2026-11-10T13:01")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T08:00"), ms("2026-11-10T08:01"), AGENT, call),
            AgentPart(ms("2026-11-10T13:00"), ms("2026-11-10T13:01"), AGENT, done),
        ])

    def test_turn_at_exactly_the_stale_limit(self) -> None:
        """A turn with no event for exactly the stale limit of 4 hours is not a turn with
        no event for longer than it: the result of 12:01 arrives exactly 4 hours after the
        call of 08:01, the last event of the turn, so the turn runs from the prompt of
        08:00 to the output of 12:02, and the execution of the tool is part of it
        (metrics.md › Agent time)."""
        prompt = event("prompt", "2026-11-10T08:00")
        call = event("tool_call", "2026-11-10T08:01", tool_category="execute", call_id="c-1")
        result = event("tool_result", "2026-11-10T12:01", call_id="c-1")
        done = event("agent_output", "2026-11-10T12:02")
        events = [prompt, call, result, done]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T08:00"), ms("2026-11-10T12:02")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T08:00"), ms("2026-11-10T08:01"), AGENT, call),
            AgentPart(ms("2026-11-10T08:01"), ms("2026-11-10T12:01"), AGENT, result),
            AgentPart(ms("2026-11-10T12:01"), ms("2026-11-10T12:02"), AGENT, done),
        ])

    def test_notification_waits_for_every_pending_call(self) -> None:
        """Two calls of one response wait each for their own result: the notification of
        09:04 arrives after the result of the call `c-1` and before the result of the call
        `c-2`, so it closes no turn, and the turn runs from the prompt of 09:00 to the
        output of 09:06, 6 minutes of agent time (metrics.md › Agent time)."""
        prompt = event("prompt", "2026-11-10T09:00")
        first = event("tool_call", "2026-11-10T09:01", tool_category="execute", call_id="c-1")
        second = event("tool_call", "2026-11-10T09:02", tool_category="execute", call_id="c-2")
        one = event("tool_result", "2026-11-10T09:03", call_id="c-1")
        note = event("notification", "2026-11-10T09:04", input_origin="task_notification")
        two = event("tool_result", "2026-11-10T09:05", call_id="c-2")
        done = event("agent_output", "2026-11-10T09:06")
        events = [prompt, first, second, one, note, two, done]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:06")),
        ])

    def test_result_without_pending_call_removes_nothing(self) -> None:
        """A tool result whose `call_id` names no pending call removes none: the call
        `c-1` still waits at the notification of 09:03, which closes no turn."""
        prompt = event("prompt", "2026-11-10T09:00")
        call = event("tool_call", "2026-11-10T09:01", tool_category="execute", call_id="c-1")
        stray = event("tool_result", "2026-11-10T09:02", call_id="c-9")
        note = event("notification", "2026-11-10T09:03", input_origin="task_notification")
        done = event("agent_output", "2026-11-10T09:04")
        self.assertEqual(turns([prompt, call, stray, note, done], 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:04")),
        ])

    def test_call_without_call_id_waits_for_the_output(self) -> None:
        """A tool call with no `call_id` waits until the next agent output, since no result
        can name it: the result of 09:02 removes nothing of it, so the notification of
        09:03 closes no turn."""
        prompt = event("prompt", "2026-11-10T09:00")
        call = event("tool_call", "2026-11-10T09:01", tool_category="execute")
        result = event("tool_result", "2026-11-10T09:02", call_id="c-1")
        note = event("notification", "2026-11-10T09:03", input_origin="task_notification")
        done = event("agent_output", "2026-11-10T09:04")
        self.assertEqual(turns([prompt, call, result, note, done], 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:04")),
        ])

    def test_result_with_a_call_id_that_is_no_text_removes_nothing(self) -> None:
        """A store line can carry a `call_id` that is no text, since the reading of a line
        does not check the type of the field: the result of 09:02 with such a `call_id`
        removes nothing, the call that gets no result still waits at the notification of
        09:03, and the turns and the parts of the session are computed (metrics.md ›
        Agent time)."""
        line = json.dumps({
            "schema_version": 1, "source": "store", "event_uid": "uid-store-1",
            "timestamp": "2026-11-10T09:02:00.000Z",
            "ingested_at": "2026-11-10T09:02:00.000Z", "writer_version": "0.1.0.dev0",
            "actor": "system", "kind": "tool_result", "machine": "machine-1",
            "tool": "claude-code", "session_id": "s-one", "call_id": ["c-1"],
        })
        stray = decode_line(line.encode("utf-8")).event
        prompt = event("prompt", "2026-11-10T09:00")
        call = event("tool_call", "2026-11-10T09:01", tool_category="execute", call_id="c-1")
        note = event("notification", "2026-11-10T09:03", input_origin="task_notification")
        done = event("agent_output", "2026-11-10T09:04")
        events = [prompt, call, stray, note, done]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:04")),
        ])
        parts = agent_parts(events, parameters())
        self.assertEqual(sum(part.end - part.start for part in parts), 240_000)

    def test_blocked_time_is_subtracted(self) -> None:
        """Blocked time runs from the decision request of 10:02 to its decision of 10:07,
        so the part between them is no agent time: the turn of 8 minutes holds 5 minutes of
        blocked time and 3 minutes of agent time (metrics.md › Blocked time)."""
        prompt = event("prompt", "2026-11-10T10:00")
        output = event("agent_output", "2026-11-10T10:01")
        asked = event("decision_request", "2026-11-10T10:02", decision_type="permission",
                      call_id="d-1")
        gave = event("decision", "2026-11-10T10:07", call_id="d-1")
        done = event("agent_output", "2026-11-10T10:08")
        again = event("prompt", "2026-11-10T10:30")
        events = [again, gave, output, asked, prompt, done]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T10:00"), ms("2026-11-10T10:08")),
        ])
        self.assertEqual(blocked_intervals(events), [
            BlockedInterval(ms("2026-11-10T10:02"), ms("2026-11-10T10:07"), asked),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T10:00"), ms("2026-11-10T10:01"), AGENT, output),
            AgentPart(ms("2026-11-10T10:01"), ms("2026-11-10T10:02"), AGENT, asked),
            AgentPart(ms("2026-11-10T10:07"), ms("2026-11-10T10:08"), AGENT, done),
        ])

    def test_foreground_wait_is_subtracted(self) -> None:
        """The wait for the own subagent of the agent runs from the call of category
        `delegate` of 11:05 to its result of 11:15, so the part between them is no agent
        time of the agent: the subagents count it as their own (metrics.md › Agent time)."""
        prompt = event("prompt", "2026-11-10T11:00")
        output = event("agent_output", "2026-11-10T11:01")
        call = event("tool_call", "2026-11-10T11:05", tool_category="delegate", call_id="c-1")
        result = event("tool_result", "2026-11-10T11:15", call_id="c-1")
        done = event("agent_output", "2026-11-10T11:16")
        again = event("prompt", "2026-11-10T11:30")
        events = [again, result, call, prompt, output, done]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T11:00"), ms("2026-11-10T11:16")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T11:00"), ms("2026-11-10T11:01"), AGENT, output),
            AgentPart(ms("2026-11-10T11:01"), ms("2026-11-10T11:05"), AGENT, call),
            AgentPart(ms("2026-11-10T11:15"), ms("2026-11-10T11:16"), AGENT, done),
        ])

    def test_background_wait_is_near_zero(self) -> None:
        """A background subagent returns its tool result at once, so its wait is near zero:
        the 2 seconds from the call of 12:01:00 to its result of 12:01:02 are subtracted,
        and the mode of the subagent is not read (metrics.md › Agent time)."""
        prompt = event("prompt", "2026-11-10T12:00")
        output = event("agent_output", "2026-11-10T12:00:30")
        call = event("tool_call", "2026-11-10T12:01:00", tool_category="delegate",
                     call_id="c-1", subagent_mode="background")
        result = event("tool_result", "2026-11-10T12:01:02", call_id="c-1")
        done = event("agent_output", "2026-11-10T12:01:03")
        again = event("prompt", "2026-11-10T12:05")
        events = [again, result, call, prompt, output, done]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T12:00"), ms("2026-11-10T12:01:03")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T12:00"), ms("2026-11-10T12:00:30"), AGENT, output),
            AgentPart(ms("2026-11-10T12:00:30"), ms("2026-11-10T12:01:00"), AGENT, call),
            AgentPart(ms("2026-11-10T12:01:02"), ms("2026-11-10T12:01:03"), AGENT, done),
        ])

    def test_call_without_result_waits_to_next_event(self) -> None:
        """A call of category `delegate` that gets no tool result waits until the next
        event of its agent: the wait from the call of 09:02 to the output of 09:20 takes
        the part between them out of the agent time (metrics.md › Agent time)."""
        prompt = event("prompt", "2026-11-10T09:00")
        output = event("agent_output", "2026-11-10T09:01")
        call = event("tool_call", "2026-11-10T09:02", tool_category="delegate", call_id="c-1")
        done = event("agent_output", "2026-11-10T09:20")
        limit = event("session_end", "2026-11-10T09:21")
        events = [prompt, output, call, done, limit]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:21")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:01"), AGENT, output),
            AgentPart(ms("2026-11-10T09:01"), ms("2026-11-10T09:02"), AGENT, call),
            AgentPart(ms("2026-11-10T09:20"), ms("2026-11-10T09:21"), AGENT, limit),
        ])

    def test_call_without_result_in_its_response_ends_at_the_output(self) -> None:
        """A call that the provider runs inside the response gets no tool result
        (claude-code-adapter.md › Records and events), and the output that follows it ends
        the turn, so the later prompts start their own turns and the idle gaps between
        the turns stay idle. Three turns of 60 s: the call of 09:00:20 gets its result at
        09:00:40, the call of 09:10:30 gets none; the parts are 20 + 20 + 20 s, 30 + 30 s,
        and 60 s, 180 s in all (metrics.md › Agent time)."""
        first = event("prompt", "2026-11-10T09:00")
        call = event("tool_call", "2026-11-10T09:00:20", tool_category="execute",
                     call_id="c-1")
        result = event("tool_result", "2026-11-10T09:00:40", call_id="c-1")
        done = event("agent_output", "2026-11-10T09:01")
        second = event("prompt", "2026-11-10T09:10")
        search = event("tool_call", "2026-11-10T09:10:30", tool_name="web_search",
                       tool_category="other", call_id="srvtool-1")
        found = event("agent_output", "2026-11-10T09:11")
        third = event("prompt", "2026-11-10T09:20")
        last = event("agent_output", "2026-11-10T09:21")
        events = [first, call, result, done, second, search, found, third, last]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:01")),
            Turn(AGENT, ms("2026-11-10T09:10"), ms("2026-11-10T09:11")),
            Turn(AGENT, ms("2026-11-10T09:20"), ms("2026-11-10T09:21")),
        ])
        parts = agent_parts(events, parameters())
        self.assertEqual(parts, [
            AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:00:20"), AGENT, call),
            AgentPart(ms("2026-11-10T09:00:20"), ms("2026-11-10T09:00:40"), AGENT, result),
            AgentPart(ms("2026-11-10T09:00:40"), ms("2026-11-10T09:01"), AGENT, done),
            AgentPart(ms("2026-11-10T09:10"), ms("2026-11-10T09:10:30"), AGENT, search),
            AgentPart(ms("2026-11-10T09:10:30"), ms("2026-11-10T09:11"), AGENT, found),
            AgentPart(ms("2026-11-10T09:20"), ms("2026-11-10T09:21"), AGENT, last),
        ])
        self.assertEqual(sum(part.end - part.start for part in parts), 180_000)

    def test_output_at_the_call_instant_completes_the_provider_run_call(self) -> None:
        """A tool call that the provider runs inside the response gets no tool result and
        is complete with its response (claude-code-adapter.md › Records and events): on a
        response of one record the output takes the instant of that record, the instant
        of its last line, so it sits at the call's own instant, and the order of the
        event keys places it before the call, since `msg_…` sorts before `tool_call:…`.
        The output of 09:11 has already completed the call, so the idle gap to the prompt
        of 09:20 stays idle: three turns of 60 s, 180 s (metrics.md › Agent time)."""
        events, warnings = claude_code.map_session(tie_records(), "claude-code",
                                                   "machine-one")
        self.assertEqual(warnings, [
            {"code": "unknown_tool_name", "values": {"tool": "web_search"}}])
        ordered = sorted(events, key=lambda item: (instant_ms(item), event_order(item)))
        self.assertEqual([item["event_uid"] for item in ordered[3:5]],
                         ["msg_b", "tool_call:srvtool_01"])
        self.assertEqual(turns(events, 14400), [
            Turn(_TIE_AGENT, ms("2026-11-19T09:00"), ms("2026-11-19T09:01")),
            Turn(_TIE_AGENT, ms("2026-11-19T09:10"), ms("2026-11-19T09:11")),
            Turn(_TIE_AGENT, ms("2026-11-19T09:20"), ms("2026-11-19T09:21")),
        ])
        outputs = [item for item in events if item["kind"] == "agent_output"]
        parts = agent_parts(events, parameters())
        self.assertEqual(parts, [
            AgentPart(ms("2026-11-19T09:00"), ms("2026-11-19T09:01"), _TIE_AGENT,
                      outputs[0]),
            AgentPart(ms("2026-11-19T09:10"), ms("2026-11-19T09:11"), _TIE_AGENT,
                      outputs[1]),
            AgentPart(ms("2026-11-19T09:20"), ms("2026-11-19T09:21"), _TIE_AGENT,
                      outputs[2]),
        ])
        self.assertEqual(sum(part.end - part.start for part in parts), 180_000)

    def test_output_with_no_turn_open_completes_the_call_at_its_instant(self) -> None:
        """A session that the store holds from its middle begins with a response, so the
        output of 09:00 arrives with no turn open, and the `web_search` that the provider
        runs inside that response gets no tool result and is complete with its response
        (claude-code-adapter.md › Records and events): the output sorts before the call of
        its own instant, the idle gap of 600 s to the prompt of 09:10 stays idle, and the
        turn of that prompt runs to the output of 09:11, 60 s (metrics.md › Agent time)."""
        events, _ = claude_code.map_session(corner_records(), "claude-code", "machine-one")
        ordered = sorted(events, key=lambda item: (instant_ms(item), event_order(item)))
        self.assertEqual([item["event_uid"] for item in ordered[:2]],
                         ["msg_a", "tool_call:srvtool_01"])
        self.assertEqual(turns(events, 14400), [
            Turn(_CORNER_AGENT, ms("2026-11-19T09:10"), ms("2026-11-19T09:11")),
        ])
        outputs = [item for item in events if item["kind"] == "agent_output"]
        parts = agent_parts(events, parameters())
        self.assertEqual(parts, [
            AgentPart(ms("2026-11-19T09:10"), ms("2026-11-19T09:11"), _CORNER_AGENT,
                      outputs[1]),
        ])
        self.assertEqual(sum(part.end - part.start for part in parts), 60_000)

    def test_calls_at_the_output_instant_wait_for_their_own_results(self) -> None:
        """Two calls of one response on one record sit at the instant of its output, and
        the output sorts before them, so each call joins the pending set after it and
        waits for its own result: the notification of 09:03, which arrives after the
        result of `c-2` and before the result of `c-1`, closes no turn, and the turn runs
        from the prompt of 09:00 to the output of 09:07, 420 s (metrics.md › Agent
        time)."""
        prompt = event("prompt", "2026-11-10T09:00")
        done = event("agent_output", "2026-11-10T09:01")
        first = event("tool_call", "2026-11-10T09:01", tool_category="execute",
                      call_id="c-1")
        second = event("tool_call", "2026-11-10T09:01", tool_category="search",
                       call_id="c-2")
        two = event("tool_result", "2026-11-10T09:02", call_id="c-2")
        note = event("notification", "2026-11-10T09:03", input_origin="task_notification")
        one = event("tool_result", "2026-11-10T09:06", call_id="c-1")
        last = event("agent_output", "2026-11-10T09:07")
        events = [prompt, done, first, second, two, note, one, last]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:07")),
        ])
        parts = agent_parts(events, parameters())
        self.assertEqual(parts, [
            AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:01"), AGENT, done),
            AgentPart(ms("2026-11-10T09:01"), ms("2026-11-10T09:02"), AGENT, two),
            AgentPart(ms("2026-11-10T09:02"), ms("2026-11-10T09:03"), AGENT, note),
            AgentPart(ms("2026-11-10T09:03"), ms("2026-11-10T09:06"), AGENT, one),
            AgentPart(ms("2026-11-10T09:06"), ms("2026-11-10T09:07"), AGENT, last),
        ])
        self.assertEqual(sum(part.end - part.start for part in parts), 420_000)

    def test_ordinary_call_survives_an_output_before_its_result(self) -> None:
        """A response on two lines: the call `c-1` of the first line at 09:01:00, the call
        `c-2` and the output at 09:01:30, the output first by its key. The output
        completes the calls that the provider runs, not a call that its own later result
        completes, so `c-1` still waits at the notification of 09:03 and the turn runs
        from the prompt of 09:00 to the output of 09:07, 420 s (metrics.md › Agent
        time)."""
        prompt = event("prompt", "2026-11-10T09:00")
        first = event("tool_call", "2026-11-10T09:01:00", tool_category="execute",
                      call_id="c-1")
        done = event("agent_output", "2026-11-10T09:01:30")
        second = event("tool_call", "2026-11-10T09:01:30", tool_category="search",
                       call_id="c-2")
        two = event("tool_result", "2026-11-10T09:02", call_id="c-2")
        note = event("notification", "2026-11-10T09:03", input_origin="task_notification")
        one = event("tool_result", "2026-11-10T09:06", call_id="c-1")
        last = event("agent_output", "2026-11-10T09:07")
        events = [prompt, first, done, second, two, note, one, last]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:07")),
        ])
        parts = agent_parts(events, parameters())
        self.assertEqual(parts, [
            AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:01:00"), AGENT, first),
            AgentPart(ms("2026-11-10T09:01:00"), ms("2026-11-10T09:01:30"), AGENT, done),
            AgentPart(ms("2026-11-10T09:01:30"), ms("2026-11-10T09:02"), AGENT, two),
            AgentPart(ms("2026-11-10T09:02"), ms("2026-11-10T09:03"), AGENT, note),
            AgentPart(ms("2026-11-10T09:03"), ms("2026-11-10T09:06"), AGENT, one),
            AgentPart(ms("2026-11-10T09:06"), ms("2026-11-10T09:07"), AGENT, last),
        ])
        self.assertEqual(sum(part.end - part.start for part in parts), 420_000)

    def test_parts_end_at_the_end_of_the_turn(self) -> None:
        """The parts of a turn end where the turn ends: the output of 09:03 ends the turn
        of 09:00, so the queued message of 09:05 that follows it ends no part, and the
        parts of 60 + 60 + 60 s sum to the 180 s of the turn (metrics.md › Agent time, ›
        Attribution)."""
        prompt = event("prompt", "2026-11-10T09:00")
        call = event("tool_call", "2026-11-10T09:01", tool_category="execute", call_id="c-1")
        result = event("tool_result", "2026-11-10T09:02", call_id="c-1")
        output = event("agent_output", "2026-11-10T09:03")
        queued = event("queued_message", "2026-11-10T09:05")
        again = event("prompt", "2026-11-10T09:10")
        events = [prompt, call, result, output, queued, again]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:03")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:01"), AGENT, call),
            AgentPart(ms("2026-11-10T09:01"), ms("2026-11-10T09:02"), AGENT, result),
            AgentPart(ms("2026-11-10T09:02"), ms("2026-11-10T09:03"), AGENT, output),
        ])

    def test_delegate_category_wait_without_tool_names(self) -> None:
        """The wait is found by the category that `parameters.category` gives, never by a
        tool name: the category rule that makes Spawn a delegate call takes the wait from
        the call of 12:01 to its result of 12:09 out of the agent time, and the stored
        category of `other` leaves it in."""
        prompt = event("prompt", "2026-11-10T12:00")
        call = event("tool_call", "2026-11-10T12:01", tool_name="Spawn",
                     tool_category="other", call_id="c-1")
        result = event("tool_result", "2026-11-10T12:09", call_id="c-1")
        done = event("agent_output", "2026-11-10T12:10")
        again = event("prompt", "2026-11-10T12:30")
        events = [prompt, call, result, done, again]

        def spawn_is_delegate(item: Event) -> str:
            """The category rule of the report: a use of Spawn delegates work."""
            return "delegate" if item.get("tool_name") == "Spawn" else stored_category(item)

        ruled = MetricsParameters(idle_gap=600, minimum_attention=60, stale_limit=14400,
                                  headless_prompts=False, category=spawn_is_delegate)
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T12:00"), ms("2026-11-10T12:01"), AGENT, call),
            AgentPart(ms("2026-11-10T12:01"), ms("2026-11-10T12:09"), AGENT, result),
            AgentPart(ms("2026-11-10T12:09"), ms("2026-11-10T12:10"), AGENT, done),
        ])
        self.assertEqual(agent_parts(events, ruled), [
            AgentPart(ms("2026-11-10T12:00"), ms("2026-11-10T12:01"), AGENT, call),
            AgentPart(ms("2026-11-10T12:09"), ms("2026-11-10T12:10"), AGENT, done),
        ])

    def test_decision_without_decision_ends_at_next_event(self) -> None:
        """A decision request that gets no decision ends its blocked time at the next event
        of its agent, at an interruption, or at the last event of the session: the request
        of s-one waits for the output of 10:20, the request of s-two waits for the last
        event of its session, the output of the subagent of 14:10, and the request of
        s-three waits for the interruption of 15:05 (metrics.md › Blocked time)."""
        asked_a = event("decision_request", "2026-11-10T10:02", decision_type="question",
                        call_id="d-a", session_id="s-a")
        done_a = event("agent_output", "2026-11-10T10:20", session_id="s-a")
        limit_a = event("session_end", "2026-11-10T10:21", session_id="s-a")
        asked_b = event("decision_request", "2026-11-10T14:02", decision_type="question",
                        call_id="d-b", session_id="s-b")
        sub_out = event("agent_output", "2026-11-10T14:10", session_id="s-b",
                        agent_id="agent-1")
        asked_c = event("decision_request", "2026-11-10T15:00", decision_type="question",
                        call_id="d-c", session_id="s-c")
        stopped = event("interruption", "2026-11-10T15:05", session_id="s-c")
        prompt_a = event("prompt", "2026-11-10T10:00", session_id="s-a")
        output_a = event("agent_output", "2026-11-10T10:01", session_id="s-a")
        prompt_b = event("prompt", "2026-11-10T14:00", session_id="s-b")
        output_b = event("agent_output", "2026-11-10T14:01", session_id="s-b")
        events = [asked_a, done_a, limit_a, asked_b, sub_out, asked_c, stopped,
                  prompt_a, output_a, prompt_b, output_b]
        self.assertEqual(blocked_intervals(events), [
            BlockedInterval(ms("2026-11-10T10:02"), ms("2026-11-10T10:20"), asked_a),
            BlockedInterval(ms("2026-11-10T14:02"), ms("2026-11-10T14:10"), asked_b),
            BlockedInterval(ms("2026-11-10T15:00"), ms("2026-11-10T15:05"), asked_c),
        ])

    def test_subagent_has_own_turns(self) -> None:
        """A subagent has its own turns, from its own events: the notification that the
        agent that started it writes reaches the subagent at 09:03 and its output of 09:10
        ends its turn, while the agent that called it holds the turn of 09:00 to 09:13
        without the wait for the subagent (metrics.md › Agent time)."""
        prompt = event("prompt", "2026-11-10T09:00")
        output = event("agent_output", "2026-11-10T09:01")
        call = event("tool_call", "2026-11-10T09:02", tool_category="delegate", call_id="c-1")
        sub_in = event("notification", "2026-11-10T09:03", input_origin="parent",
                       agent_id="agent-1")
        sub_out = event("agent_output", "2026-11-10T09:10", agent_id="agent-1")
        result = event("tool_result", "2026-11-10T09:12", call_id="c-1")
        done = event("agent_output", "2026-11-10T09:13")
        again = event("prompt", "2026-11-10T09:30")
        events = [prompt, output, call, sub_in, sub_out, result, done, again]
        self.assertEqual(turns(events, 14400), [
            Turn(AGENT, ms("2026-11-10T09:00"), ms("2026-11-10T09:13")),
            Turn(SUBAGENT, ms("2026-11-10T09:03"), ms("2026-11-10T09:10")),
        ])
        self.assertEqual(agent_parts(events, parameters()), [
            AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:01"), AGENT, output),
            AgentPart(ms("2026-11-10T09:01"), ms("2026-11-10T09:02"), AGENT, call),
            AgentPart(ms("2026-11-10T09:03"), ms("2026-11-10T09:10"), SUBAGENT, sub_out),
            AgentPart(ms("2026-11-10T09:12"), ms("2026-11-10T09:13"), AGENT, done),
        ])

    def test_records_out_of_order_give_same_agent_time(self) -> None:
        """The records of one file arrive out of time order, and the metrics sort by
        `timestamp`, never by line: the turns, the blocked time, and the parts of agent
        time of the scrambled records are the records in time order give."""
        prompt = event("prompt", "2026-11-10T09:00")
        output = event("agent_output", "2026-11-10T09:01")
        call = event("tool_call", "2026-11-10T09:02", tool_category="execute", call_id="c-1")
        asked = event("decision_request", "2026-11-10T09:03", decision_type="permission",
                      call_id="d-1")
        gave = event("decision", "2026-11-10T09:04", call_id="d-1")
        result = event("tool_result", "2026-11-10T09:05", call_id="c-1")
        done = event("agent_output", "2026-11-10T09:06")
        again = event("prompt", "2026-11-10T09:30")
        events = [prompt, output, call, asked, gave, result, done, again]
        scrambled = [events[6], events[2], events[0], events[5], events[3], events[1],
                     events[7], events[4]]
        self.assertEqual(turns(scrambled, 14400), turns(events, 14400))
        self.assertEqual(blocked_intervals(scrambled), blocked_intervals(events))
        self.assertEqual(agent_parts(scrambled, parameters()),
                         agent_parts(events, parameters()))


class ManualEntryTests(unittest.TestCase):
    """The parts that the manual entries count and their warnings (metrics.md › Declared
    values)."""

    def test_overlapping_entry_merges_by_union(self) -> None:
        """An entry in mode `overlapping` keeps its whole interval where measured human time
        covers part of it, so that the union with the measured time merges the two, and it
        gives no warning here: the warning about measured time of another project needs the
        attribution."""
        made = manual_entry("2026-11-10T09:05", "2026-11-10T09:20")
        measured = [window_of("2026-11-10T09:00", "2026-11-10T09:10")]
        parts, warnings = manual_parts([made], measured)
        self.assertEqual(
            parts, [ManualPart(ms("2026-11-10T09:05"), ms("2026-11-10T09:20"), made)])
        self.assertEqual(warnings, [])

    def test_additional_entry_counts_outside_measured_time(self) -> None:
        """An entry in mode `additional` counts only where no measured human time covers it,
        in as many parts as the measured time cuts out of its interval, and one warning of
        code `manual_entry_overlap` says that the overlap is removed, once however many
        pieces the measured time cuts out; an entry that the measured time covers whole
        counts nothing and still warns."""
        made = manual_entry("2026-11-10T09:00", "2026-11-10T09:20", "additional")
        measured = [window_of("2026-11-10T09:05", "2026-11-10T09:10"),
                    window_of("2026-11-10T09:12", "2026-11-10T09:15")]
        parts, warnings = manual_parts([made], measured)
        self.assertEqual(parts, [
            ManualPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:05"), made),
            ManualPart(ms("2026-11-10T09:10"), ms("2026-11-10T09:12"), made),
            ManualPart(ms("2026-11-10T09:15"), ms("2026-11-10T09:20"), made),
        ])
        self.assertEqual(warnings, [
            {"code": "manual_entry_overlap", "values": {"event_uid": made["event_uid"]}},
        ])
        inside = manual_entry("2026-11-10T09:06", "2026-11-10T09:08", "additional")
        parts, warnings = manual_parts([inside], measured)
        self.assertEqual(parts, [])
        self.assertEqual(warnings, [
            {"code": "manual_entry_overlap", "values": {"event_uid": inside["event_uid"]}},
        ])


class ActivityClassTests(unittest.TestCase):
    """The activity classes of the instants of a window (metrics.md › Activity classes)."""

    def test_classes_table(self) -> None:
        """One minute of each row of the table falls in the class of that row: blocked time
        changes nothing where the person is present or an agent works, and it is a class of
        its own only where nobody is present and no agent works."""
        minute = 60_000
        window = [window_of("2026-11-10T10:00", "2026-11-10T10:05")]
        human = [window_of("2026-11-10T10:00", "2026-11-10T10:02")]
        agent = [window_of("2026-11-10T10:01", "2026-11-10T10:03")]
        blocked = [window_of("2026-11-10T10:00", "2026-11-10T10:04")]
        self.assertEqual(activity_classes(human, agent, blocked, window), {
            "person_only": minute,
            "supervised": minute,
            "unattended": minute,
            "blocked": minute,
            "idle": minute,
        })

    def test_present_person_and_blocked_agent_is_person_only(self) -> None:
        """Blocked time of an agent while the person is present and no agent works is person
        only: the person is the one who must act, so the blocked class holds none of it."""
        human = [window_of("2026-11-10T10:00", "2026-11-10T10:10")]
        blocked = [window_of("2026-11-10T10:00", "2026-11-10T10:10")]
        self.assertEqual(activity_classes(human, [], blocked, DAY), {
            "person_only": 600_000,
            "supervised": 0,
            "unattended": 0,
            "blocked": 0,
            "idle": total(DAY) - 600_000,
        })

    def test_blocked_of_one_project_is_person_only_of_the_other_and_of_the_person(self) -> None:
        """An instant of blocked time of one project where the person is present on another
        is blocked for the first project and person only for the second and for the person
        (metrics.md › Activity classes): the person is present on Beta through the five
        minutes of blocked time of Alpha, which the human time of Alpha does not cover, and
        on Alpha later in the day, and no agent works."""
        alpha = [window_of("2026-11-10T10:20", "2026-11-10T10:30")]
        beta = [window_of("2026-11-10T10:00", "2026-11-10T10:05")]
        blocked = [window_of("2026-11-10T10:00", "2026-11-10T10:05")]
        with self.subTest(holder="Alpha"):
            self.assertEqual(activity_classes(alpha, [], blocked, DAY), {
                "person_only": 600_000,
                "supervised": 0,
                "unattended": 0,
                "blocked": 300_000,
                "idle": total(DAY) - 900_000,
            })
        with self.subTest(holder="Beta"):
            self.assertEqual(activity_classes(beta, [], [], DAY), {
                "person_only": 300_000,
                "supervised": 0,
                "unattended": 0,
                "blocked": 0,
                "idle": total(DAY) - 300_000,
            })
        with self.subTest(holder="person"):
            self.assertEqual(activity_classes(alpha + beta, [], blocked, DAY), {
                "person_only": 900_000,
                "supervised": 0,
                "unattended": 0,
                "blocked": 0,
                "idle": total(DAY) - 900_000,
            })

    def test_classes_add_up_to_window(self) -> None:
        """Overlapping human time, agent time, and blocked time divide the whole window into
        the five classes: 40 minutes of human time give 25 minutes of person only and 15 of
        supervised, an agent that works alone for 10 minutes is unattended, the blocked time
        inside them is no class of its own, and the rest of the day is idle."""
        human = [window_of("2026-11-10T09:00", "2026-11-10T09:30"),
                 window_of("2026-11-10T09:20", "2026-11-10T09:40")]
        agent = [window_of("2026-11-10T09:25", "2026-11-10T09:50")]
        blocked = [window_of("2026-11-10T09:10", "2026-11-10T09:35")]
        classes = activity_classes(human, agent, blocked, DAY)
        self.assertEqual(classes, {
            "person_only": 1_500_000,
            "supervised": 900_000,
            "unattended": 600_000,
            "blocked": 0,
            "idle": 83_400_000,
        })
        self.assertEqual(sum(classes.values()), total(DAY))

    def test_day_of_two_parts(self) -> None:
        """A window of two spans counts only what its parts cover: the agent time between
        the parts, and the blocked time between them, count nothing, and the values add up
        to the ten minutes of the two parts."""
        window = [window_of("2026-11-10T10:00", "2026-11-10T10:05"),
                  window_of("2026-11-10T12:00", "2026-11-10T12:05")]
        human = [window_of("2026-11-10T09:58", "2026-11-10T10:02"),
                 window_of("2026-11-10T12:03", "2026-11-10T12:08")]
        agent = [window_of("2026-11-10T10:04", "2026-11-10T12:01")]
        blocked = [window_of("2026-11-10T11:00", "2026-11-10T11:30")]
        classes = activity_classes(human, agent, blocked, window)
        self.assertEqual(classes, {
            "person_only": 240_000,
            "supervised": 0,
            "unattended": 120_000,
            "blocked": 0,
            "idle": 240_000,
        })

    def test_compute_metrics(self) -> None:
        """The figures of one report hold the human intervals, the parts that a manual entry
        counts against the measured human time, the parts of agent time without the interval
        that the blocked time covers, the blocked time, and the warning of the entry."""
        first = event("prompt", "2026-11-10T09:00")
        call = event("tool_call", "2026-11-10T09:01", tool_category="execute", call_id="c-1")
        asked = event("decision_request", "2026-11-10T09:02", decision_type="permission",
                      call_id="d-1")
        gave = event("decision", "2026-11-10T09:07", call_id="d-1")
        result = event("tool_result", "2026-11-10T09:08", call_id="c-1")
        done = event("agent_output", "2026-11-10T09:09")
        made = manual_entry("2026-11-10T09:03", "2026-11-10T09:30", "additional")
        metrics = compute_metrics([first, call, asked, gave, result, done], [made],
                                  parameters())
        self.assertEqual(metrics, Metrics(
            human=[
                HumanInterval(ms("2026-11-10T08:59"), ms("2026-11-10T09:00"), first,
                              "minimum_attention"),
                HumanInterval(ms("2026-11-10T09:00"), ms("2026-11-10T09:07"), gave,
                              "signal_gap"),
                HumanInterval(ms("2026-11-10T09:02"), ms("2026-11-10T09:07"), gave,
                              "response"),
            ],
            manual=[ManualPart(ms("2026-11-10T09:07"), ms("2026-11-10T09:30"), made)],
            agent=[
                AgentPart(ms("2026-11-10T09:00"), ms("2026-11-10T09:01"), AGENT, call),
                AgentPart(ms("2026-11-10T09:01"), ms("2026-11-10T09:02"), AGENT, asked),
                AgentPart(ms("2026-11-10T09:07"), ms("2026-11-10T09:08"), AGENT, result),
                AgentPart(ms("2026-11-10T09:08"), ms("2026-11-10T09:09"), AGENT, done),
            ],
            blocked=[BlockedInterval(ms("2026-11-10T09:02"), ms("2026-11-10T09:07"), asked)],
            warnings=[{"code": "manual_entry_overlap",
                       "values": {"event_uid": made["event_uid"]}}],
        ))


class WindowTests(unittest.TestCase):
    """The figures of a window: the idle gaps, the unknown invocation, the presence span."""

    def test_idle_gaps_5_10_15(self) -> None:
        """The human time of prompts 7 minutes apart is 2 minutes at the idle gap of 5
        minutes and 8 minutes at the idle gaps of 10 and 15 minutes."""
        first = event("prompt", "2026-11-10T09:00")
        second = event("prompt", "2026-11-10T09:07")
        at_gaps = human_time_at_idle_gaps(stream_of([second, first]), parameters(), DAY)
        self.assertEqual(at_gaps, {300: 120000, 600: 480000, 900: 480000})

    def test_human_time_inside_a_window_of_two_parts(self) -> None:
        """A window of two spans counts only what its parts cover: the signal gap of 6
        minutes gives 4 minutes inside the two parts, and at the idle gap of 5 minutes only
        the second minimum attention falls inside, 1 minute."""
        first = event("prompt", "2026-11-10T09:00")
        second = event("prompt", "2026-11-10T09:06")
        window: Sequence[Span] = [window_of("2026-11-10T09:00", "2026-11-10T09:02"),
                                  window_of("2026-11-10T09:04", "2026-11-10T09:06")]
        self.assertEqual(human_time_at_idle_gaps(stream_of([first, second]), parameters(), window),
                         {300: 60000, 600: 240000, 900: 240000})

    def test_window_inside_a_signal_gap(self) -> None:
        """A window that starts inside a signal gap counts the part of the gap inside it,
        because the signal before its start lies within the idle gap of the window: prompts
        at 08:55 and 09:05 and the window from 09:00 give 5 minutes at the idle gaps of 10
        and 15 minutes, and at the idle gap of 5 minutes only the minute of the minimum
        attention of the second prompt (metrics.md › Human time, › Uncertainty)."""
        first = event("prompt", "2026-11-10T08:55")
        second = event("prompt", "2026-11-10T09:05")
        window = [window_of("2026-11-10T09:00", "2026-11-10T10:00")]
        self.assertEqual(human_time_at_idle_gaps(stream_of([first, second]), parameters(), window),
                         {300: 60000, 600: 300000, 900: 300000})

    def test_stream_orders_the_events_whatever_their_order(self) -> None:
        """The stream puts the events in the order of their instants, whatever the order
        given: of six prompts given out of order, two lie inside the window 09:00-09:20
        and the other four lie beyond its idle gaps; the window holds the two, 10 minutes
        apart, so it holds their signal gap and the minute of minimum attention of the
        first at the idle gaps of 10 and 15 minutes, and two minutes of minimum attention
        at 5 minutes (metrics.md › Human time, › Uncertainty)."""
        events = [
            event("prompt", "2026-11-10T09:40"),
            event("prompt", "2026-11-10T08:00"),
            event("prompt", "2026-11-10T09:05"),
            event("prompt", "2026-11-10T10:00"),
            event("prompt", "2026-11-10T08:30"),
            event("prompt", "2026-11-10T09:15"),
        ]
        window = [window_of("2026-11-10T09:00", "2026-11-10T09:20")]
        self.assertEqual(human_time_at_idle_gaps(stream_of(events), parameters(), window),
                         {300: 120000, 600: 660000, 900: 660000})

    def test_stream_orders_two_events_of_one_instant_by_their_key(self) -> None:
        """Two events of one instant are ordered by their event key, and the instant of the
        stream at each position is the instant of its event: of two prompts of two sessions
        at 09:00, given with the session that sorts second first, the stream holds the
        session that sorts first first, and its instants name the instant of each of their
        events (metrics.md › Human time; `event-schema.md` › Keys and invariants)."""
        early = event("prompt", "2026-11-10T09:00", session_id="s-early")
        late = event("prompt", "2026-11-10T09:00", session_id="s-late")
        stream = stream_of([late, early])
        self.assertEqual([held["session_id"] for held in stream.events], ["s-early", "s-late"])
        self.assertEqual(stream.instants, [instant_ms(held) for held in stream.events])

    def test_signal_at_the_start_of_the_window_counts(self) -> None:
        """A human signal exactly at the start instant of the window is inside it, and one
        exactly at its end instant is outside it: the prompts at 09:00, of a session of
        unknown invocation, and at 09:20 give the window from 09:00 to 09:21 a share of
        unknown invocation of 0.5 and a presence span of 20 minutes, and the window from
        09:00 to 09:20, which ends at the second prompt, a share of 1.0 and a span of 0
        (metrics.md › Human time)."""
        first = event("prompt", "2026-11-10T09:00", session_id="s-two", invocation="unknown")
        second = event("prompt", "2026-11-10T09:20", session_id="s-one")
        stream = stream_of([second, first])
        window = [window_of("2026-11-10T09:00", "2026-11-10T09:21")]
        self.assertEqual(unknown_invocation_share(stream, parameters(), window), 0.5)
        self.assertEqual(presence_span(stream, parameters(), window), 1200000)
        ended = [window_of("2026-11-10T09:00", "2026-11-10T09:20")]
        self.assertEqual(unknown_invocation_share(stream, parameters(), ended), 1.0)
        self.assertEqual(presence_span(stream, parameters(), ended), 0)

    def test_signal_at_the_end_of_the_first_part_is_outside(self) -> None:
        """A human signal exactly at the end instant of the first part of a window of two
        parts is outside it, as the end instant of every span is, also when it is not the
        last instant of the window: the window of the parts 09:00-09:20 and 10:00-11:00
        holds the prompt of 09:10 alone, and the prompt of 09:20, of a session of unknown
        invocation, never — the share of unknown invocation stays 0.0 and the presence
        span stays 0 (metrics.md › Human time)."""
        inside = event("prompt", "2026-11-10T09:10", session_id="s-one")
        at_end = event("prompt", "2026-11-10T09:20", session_id="s-two", invocation="unknown")
        stream = stream_of([at_end, inside])
        window = [window_of("2026-11-10T09:00", "2026-11-10T09:20"),
                  window_of("2026-11-10T10:00", "2026-11-10T11:00")]
        self.assertEqual(unknown_invocation_share(stream, parameters(), window), 0.0)
        self.assertEqual(presence_span(stream, parameters(), window), 0)

    def test_unknown_invocation_share(self) -> None:
        """One of the four signals of the window comes from a session of unknown invocation:
        a share of 0.25; a window that holds no signal gives 0.0, and its end instant is
        outside it."""
        events = [
            event("prompt", "2026-11-10T09:00", session_id="s-one"),
            event("prompt", "2026-11-10T09:01", session_id="s-one"),
            event("prompt", "2026-11-10T09:02", session_id="s-two", invocation="unknown"),
            event("prompt", "2026-11-10T09:03", session_id="s-one"),
        ]
        self.assertEqual(unknown_invocation_share(stream_of(events), parameters(), DAY), 0.25)
        self.assertEqual(
            unknown_invocation_share(stream_of(events), parameters(),
                                     [window_of("2026-11-10T09:00", "2026-11-10T09:02")]),
            0.0)
        self.assertEqual(unknown_invocation_share(stream_of(events), parameters(),
                                                  [window_of("2026-11-10T11:00",
                                                             "2026-11-10T12:00")]),
                         0.0)

    def test_presence_span(self) -> None:
        """The presence span runs from the first to the last human signal inside the window,
        is None without a signal, and is 0 with one signal inside."""
        first = event("prompt", "2026-11-10T09:00")
        second = event("prompt", "2026-11-10T09:20")
        self.assertEqual(presence_span(stream_of([first, second]), parameters(), DAY), 1200000)
        self.assertEqual(presence_span(stream_of([first, second]), parameters(),
                                       [window_of("2026-11-10T09:10", "2026-11-10T10:00")]), 0)
        self.assertIsNone(presence_span(stream_of([]), parameters(), DAY))


class ParametersTests(unittest.TestCase):
    """The stored tool category and the default category of the parameters."""

    def test_stored_category(self) -> None:
        """The stored category of a tool call is its `tool_category`, the parameters use it
        by default, and an event without one falls in `other`."""
        call = event("tool_call", "2026-11-10T09:00", tool_category="edit")
        prompt = event("prompt", "2026-11-10T09:01")
        self.assertEqual(stored_category(call), "edit")
        self.assertEqual(stored_category(prompt), "other")
        made = parameters()
        self.assertIs(made.category, stored_category)
        self.assertEqual(made.category(call), "edit")


if __name__ == "__main__":
    unittest.main()
