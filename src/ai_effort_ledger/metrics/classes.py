"""The manual entries of the person and the activity classes of their day (metrics.md ›
Declared values, › Activity classes).

A manual entry is an interval that the person declares, with a mode that decides how it
combines with the measured human time: in mode `overlapping` it keeps its whole interval, so
that the union with the measured time merges the two, and in mode `additional` it counts only
where the measured time does not cover it, with a warning for the overlap that the ledger
removes. The activity classes divide the instants of a window — a local day can have two
spans — into five classes that come from three unions: the measured human time with the
manual entries, the agent time, and the blocked time. The figures are milliseconds since the
epoch (decision D12).
"""

from collections.abc import Sequence
from typing import NamedTuple

from ..events import Event
from .agent import AgentPart, BlockedInterval, agent_parts, blocked_intervals
from .human import HumanInterval, MetricsParameters, _ms_of_text, _stream_order, human_intervals
from .spans import Span, intersect, subtract, total, union


class ManualPart(NamedTuple):
    """One interval that a manual entry counts: the whole declared interval of an entry in
    mode `overlapping`, or the part of it that no measured human time covers for an entry in
    mode `additional`, with the entry that declares it (metrics.md › Declared values)."""

    start: int
    end: int
    entry: Event


class Metrics(NamedTuple):
    """The figures of one report: the intervals of the measured human time, the parts that
    the manual entries count, the parts of agent time, the blocked time, and the warnings
    that the manual entries give (metrics.md › Quantities). Every list of parts comes
    sorted by start, as `compute_metrics` sorts them; the bounds that the attribution
    reads them through rest on that order."""

    human: list[HumanInterval]
    manual: list[ManualPart]
    agent: list[AgentPart]
    blocked: list[BlockedInterval]
    warnings: list[dict]


def manual_parts(
    entries: Sequence[Event],
    human: list[Span],
) -> tuple[list[ManualPart], list[dict]]:
    """The parts that the manual entries count against the measured human time, with the
    warnings of the overlaps that they give up (metrics.md › Declared values): an entry in
    mode `overlapping` keeps its whole interval, so that the union with the measured time
    merges the two, and an entry in mode `additional` keeps only what the measured time does
    not cover, in as many parts as the measured time cuts out of its interval, with one
    `manual_entry_overlap` warning for the overlap that it loses."""
    measured = union(human)
    parts: list[ManualPart] = []
    warnings: list[dict] = []
    for entry in sorted(entries, key=_stream_order):
        start, end = _entry_span(entry)
        if start >= end:
            continue
        if entry.get("manual_mode") == "additional":
            remaining = subtract([(start, end)], measured)
            for begin, finish in remaining:
                parts.append(ManualPart(begin, finish, entry))
            if intersect([(start, end)], measured):
                warnings.append({"code": "manual_entry_overlap",
                                 "values": {"event_uid": entry["event_uid"]}})
        else:
            parts.append(ManualPart(start, end, entry))
    parts.sort(key=lambda part: (part.start, part.end, _stream_order(part.entry)))
    return parts, warnings


def activity_classes(
    human: list[Span],
    agent: list[Span],
    blocked: list[Span],
    window: Sequence[Span],
) -> dict[str, int]:
    """The milliseconds of the window that each activity class holds (metrics.md › Activity
    classes): the person only where the human time covers and no agent works, supervised
    where the human time covers and an agent works, unattended where an agent works alone,
    blocked where the blocked time alone covers, and idle where nothing covers. The human
    time is the measured human time with the manual entries; the values add up to the
    window."""
    inside = union(window)
    present = intersect(union(human), inside)
    working = intersect(union(agent), inside)
    held = intersect(union(blocked), inside)
    supervised = total(intersect(present, working))
    working_union = union(present + working)
    return {
        "person_only": total(present) - supervised,
        "supervised": supervised,
        "unattended": total(working) - supervised,
        "blocked": total(held) - total(intersect(held, working_union)),
        "idle": total(inside) - total(union(present + working + held)),
    }


def compute_metrics(
    session_events: Sequence[Event],
    manual_entries: Sequence[Event],
    parameters: MetricsParameters,
) -> Metrics:
    """The figures of the events of the sessions and of the manual entries of one report
    (metrics.md › Quantities): the measured human time of the one stream of the person, the
    parts that the manual entries count against it, the parts of agent time and the blocked
    time of every agent of every session, and the warnings that the manual entries give."""
    human = human_intervals(session_events, parameters)
    agent = agent_parts(session_events, parameters)
    blocked = blocked_intervals(session_events)
    manual, warnings = manual_parts(
        manual_entries, [(interval.start, interval.end) for interval in human])
    return Metrics(human, manual, agent, blocked, warnings)


def _entry_span(entry: Event) -> Span:
    """The interval that a manual entry declares, in milliseconds: the `start` included, the
    `end` excluded (metrics.md › Declared values)."""
    return (_ms_of_text(entry["start"]), _ms_of_text(entry["end"]))
