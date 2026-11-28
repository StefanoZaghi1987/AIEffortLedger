"""Measured human time: the human signals of a person and the three kinds of interval that
their union counts (metrics.md › Human time, ADR 0021).

The human signals of all sessions, agent tools, and machines of the person form one stream:
a prompt, a queued message, an interruption, and a decision that the person made; a headless
prompt is one only when the report parameter `headless prompts` says so. Measured human time
is the union of the signal gaps, the response intervals, and the minimum attention intervals.
The module reads the event schema and nothing else of the core (architecture.md › Modules);
its figures are milliseconds since the epoch (decision D12), and its parameter durations are
whole seconds.
"""

from bisect import bisect_left
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import NamedTuple

from ..events import Event, event_order, parse_instant
from .spans import Span, intersect, total, union

IDLE_GAPS_OF_UNCERTAINTY = (300, 600, 900)
"""The idle gaps in seconds at which every command that shows the human time of a day also
shows it (metrics.md › Uncertainty)."""


def instant_ms(event: Event) -> int:
    """The instant of an event as milliseconds since the epoch, the unit of a span."""
    return _ms_of_text(event["timestamp"])


@lru_cache(maxsize=None)
def _ms_of_text(text: str) -> int:
    """The milliseconds since the epoch of an instant of the schema, the unit of a span.
    The conversion of a text is remembered, as `parse_instant` remembers its parse: a
    report reads the instant of one event many times, and one text always gives the same
    instant. The memory has no bound: it holds the text and one whole number for each
    distinct text, for the life of the process, which a command ends."""
    return round(parse_instant(text).timestamp() * 1000)


def stored_category(event: Event) -> str:
    """The tool category that the store holds for a tool call, before the category rules
    replace it at report time (`event-schema.md` › Fields); an event that holds none falls
    in `other`."""
    return event.get("tool_category", "other")


@dataclass(frozen=True)
class MetricsParameters:
    """The report parameters that the human time and the turns use, their durations in whole
    seconds: the idle gap, the minimum attention time, and the stale limit, whether the
    report counts headless prompts, and the category that gives the tool category of a tool
    call after the category rules (`metrics.md` › Human time, › Agent time).

    The default `category` reads the stored category; `cli` builds the parameters from
    `ReportParameters` and the effective category, because `configuration` and `attribution`
    are not below `metrics` (architecture.md › Modules).
    """

    idle_gap: int
    minimum_attention: int
    stale_limit: int
    headless_prompts: bool
    category: Callable[[Event], str] = stored_category


class HumanInterval(NamedTuple):
    """One interval of measured human time: its limits in milliseconds, the human signal
    that ends it, and its kind: `"signal_gap"` between two consecutive signals, `"response"`
    from the last agent output or decision request to the signal, `"minimum_attention"`
    before a signal that ends no other interval. A signal gap belongs to its later signal; a
    response interval and a minimum attention interval belong to their own signal (ADR 0021,
    metrics.md › Attribution)."""

    start: int
    end: int
    signal: Event
    kind: str


def human_signals(events: Sequence[Event], headless_prompts: bool) -> list[Event]:
    """The human signals of the events, in the order of the one stream of the person: by
    instant, then by event key (`metrics.md` › Human time)."""
    ordered = sorted(events, key=_stream_order)
    return [event for event in ordered if _is_signal(event, headless_prompts)]


def human_intervals(
    events: Sequence[Event],
    parameters: MetricsParameters,
) -> list[HumanInterval]:
    """The intervals of measured human time of the events (metrics.md › Human time, ADR
    0021): the signal gaps between consecutive signals of the person that are not more than
    the idle gap apart, from any session; the response intervals from the last agent output
    or decision request of the main agent or of a foreground subagent of a session to each
    signal of the same session that follows while it stays the last; and one minimum
    attention interval for each signal that ends no other interval."""
    idle_ms = parameters.idle_gap * 1000
    attention_ms = parameters.minimum_attention * 1000
    ordered = sorted(events, key=_stream_order)
    signals = [event for event in ordered if _is_signal(event, parameters.headless_prompts)]
    intervals: list[HumanInterval] = []
    ended: set[int] = set()
    for position, (earlier, later) in enumerate(zip(signals, signals[1:])):
        if instant_ms(later) - instant_ms(earlier) <= idle_ms:
            intervals.append(
                HumanInterval(instant_ms(earlier), instant_ms(later), later, "signal_gap"))
            ended.add(position + 1)
    starters: dict[tuple[str | None, str | None], tuple[int, Event]] = {}
    position = 0
    for event in ordered:
        if _is_starter(event):
            starters[(event.get("tool"), event.get("session_id"))] = (instant_ms(event), event)
        elif position < len(signals) and event is signals[position]:
            moment = instant_ms(event)
            starter = starters.get((event.get("tool"), event.get("session_id")))
            if starter is not None and moment - starter[0] <= idle_ms:
                intervals.append(HumanInterval(starter[0], moment, event, "response"))
                ended.add(position)
            position += 1
    for position, signal in enumerate(signals):
        if position in ended:
            continue
        moment = instant_ms(signal)
        intervals.append(
            HumanInterval(moment - attention_ms, moment, signal, "minimum_attention"))
    intervals.sort(key=lambda interval: (interval.start, interval.end))
    return intervals


class Stream(NamedTuple):
    """The events of the sessions of a report in the order of the one stream of the
    person: by instant, then by event key (metrics.md › Human time), each at the
    position of its instant, so that a window reads by two searches the events near it
    and never the whole stream."""

    events: list[Event]
    instants: list[int]


def stream_of(events: Sequence[Event]) -> Stream:
    """The stream of the events, whatever their order; a report builds it once, and the
    figures of each of its days read it."""
    ordered = sorted(events, key=_stream_order)
    return Stream(ordered, [instant_ms(event) for event in ordered])


def human_time_at_idle_gaps(
    stream: Stream,
    parameters: MetricsParameters,
    window: Sequence[Span],
) -> dict[int, int]:
    """The human time of the stream at the idle gaps of 5, 10, and 15 minutes and at the
    idle gap in use (metrics.md › Uncertainty): for each idle gap in seconds, the
    milliseconds of the union of the intervals inside the window, so that the reader sees
    how much the figure depends on the parameter. A window is a sequence of spans, because a
    local day can have two parts."""
    gaps = sorted({*IDLE_GAPS_OF_UNCERTAINTY, parameters.idle_gap})
    near = _near(stream, window, max(gaps[-1], parameters.minimum_attention) * 1000)
    return {
        idle_gap: _inside(
            human_intervals(near, replace(parameters, idle_gap=idle_gap)), window)
        for idle_gap in gaps
    }


def unknown_invocation_share(
    stream: Stream,
    parameters: MetricsParameters,
    window: Sequence[Span],
) -> float:
    """The share of the human signals inside the window that come from sessions of unknown
    invocation (`metrics.md` › Human time); 0.0 when the window holds no signal."""
    moments = _signal_moments(stream, parameters, window)
    if not moments:
        return 0.0
    unknown = sum(1 for event, _ in moments if event.get("invocation") == "unknown")
    return unknown / len(moments)


def presence_span(
    stream: Stream,
    parameters: MetricsParameters,
    window: Sequence[Span],
) -> int | None:
    """The presence span of the person inside the window: the milliseconds from the first to
    the last human signal of the window; None when the window holds no signal."""
    moments = _signal_moments(stream, parameters, window)
    if not moments:
        return None
    return moments[-1][1] - moments[0][1]


def _signal_moments(
    stream: Stream,
    parameters: MetricsParameters,
    window: Sequence[Span],
) -> list[tuple[Event, int]]:
    """The human signals of the window with their instants, in the order of the stream."""
    inside = union(window)
    moments = [(event, instant_ms(event))
               for event in human_signals(_near(stream, window, 0),
                                          parameters.headless_prompts)]
    return [(event, moment) for event, moment in moments
            if any(start <= moment < end for start, end in inside)]


def _near(
    stream: Stream,
    window: Sequence[Span],
    margin_ms: int,
) -> list[Event]:
    """The events of the stream whose instant lies within `margin_ms` of the window: the
    only ones that an interval of human time that the window covers can hold, since an
    interval pairs two signals of the stream at most one idle gap apart, or a signal with
    the last start of its session at most one idle gap before it, and reaches at most one
    minimum attention before its own signal (metrics.md › Human time). The figures of the
    window that this module computes from them are the figures that all the events give.
    The instants of the stream never decrease, so two searches find the first event of
    the window and the first event after it."""
    first = min(start for start, _ in window) - margin_ms
    last = max(end for _, end in window) + margin_ms
    return stream.events[bisect_left(stream.instants, first):
                         bisect_left(stream.instants, last)]


def _inside(intervals: list[HumanInterval], window: Sequence[Span]) -> int:
    """The milliseconds of the union of the intervals that the window covers."""
    measured = union([(interval.start, interval.end) for interval in intervals])
    return total(intersect(measured, union(window)))


def _stream_order(event: Event) -> tuple:
    """The order of the stream: by instant, then by event key (`event-schema.md` › Keys and
    invariants)."""
    return (instant_ms(event), event_order(event))


def _is_signal(event: Event, headless_prompts: bool) -> bool:
    """Whether one event shows that a person attended to the work (GLOSSARY › Human signal):
    a prompt, a queued message, an interruption, a decision that the person made, and a
    headless prompt only when the report counts headless prompts."""
    kind = event["kind"]
    if kind == "decision":
        return event.get("actor") == "human"
    if kind in ("prompt", "queued_message", "interruption"):
        return True
    return kind == "notification" and headless_prompts and _is_headless_prompt(event)


def _is_headless_prompt(event: Event) -> bool:
    """Whether a notification is a prompt of a session of headless invocation: of input
    origin `scripted` (`event-schema.md` › Keys and invariants)."""
    return event.get("input_origin") == "scripted" and event.get("invocation") == "headless"


def _is_starter(event: Event) -> bool:
    """Whether an event starts a response interval: an agent output or a decision request of
    the main agent or of a foreground subagent. An output of a background subagent starts
    none, because the person does not watch it while it runs, and a subagent whose
    `subagent_mode` is absent counts as a foreground subagent (ruled 2026-11-20)."""
    if event["kind"] not in ("agent_output", "decision_request"):
        return False
    return event.get("subagent_mode") != "background"
