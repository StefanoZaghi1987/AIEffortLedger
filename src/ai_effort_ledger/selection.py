"""The selection of a report: the events of its period with the whole sessions that hold one
of them, the timesheet confirmations by day, the declared intervals, and the bookkeeping
events of any instant (`architecture.md` › Data flow).

The selection brings the local index up to date first and takes no lock: it reads the
segments through the index, and a report of an index that is empty gives the same figures.
Every read leaves out the copies that a purge blocks, through the `PurgeSet` of the purge
events of the store; the selection leaves out, besides, the events that a retraction cancels
— a retraction that an active retraction names cancels nothing — and the broken lines never enter
the index as events. The margin around the period is the longer of the stale limit and the
idle gap, so that a decision request, a wait for a subagent, or the folder of an earlier
event of a session counts the same in a report of one day and in one of a longer period.
"""

from collections.abc import Sequence
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from .configuration import ReportParameters
from .days import LocalDays
from .events import Event, EventKey, event_key, event_order
from .index import BrokenLine, LocalIndex, SegmentState
from .store import PurgeSet


class Selection(NamedTuple):
    """The events of one report and the state of the store that it read.

    `session_events` holds the events of the whole sessions that have an event in the period
    with its margin, without the ones a purge blocks or a retraction cancels. `confirmations`
    holds every timesheet confirmation of the days of the period, retracted or not, for the
    chain of `replaces`. `manual_entries` and `annotations` hold the manual entries and the
    annotations of an interval that intersect the period and the annotations of a session, at
    any instant, without the cancelled ones. `retractions` holds every retraction of the
    store, also a retracted one, and `cancelled` the keys that the retractions cancel.
    `segments`, `broken`, and `newer` are the state of the store that the report record
    shows; `warnings` holds the code and the values of every warning.
    """

    first: date
    last: date
    session_events: list[Event]
    confirmations: list[Event]
    manual_entries: list[Event]
    annotations: list[Event]
    retractions: list[Event]
    cancelled: set[EventKey]
    segments: list[SegmentState]
    broken: list[BrokenLine]
    newer: bool
    warnings: list[dict]


def select(
    index: LocalIndex,
    store_folder: Path,
    days: LocalDays,
    first: date,
    last: date,
    parameters: ReportParameters,
    held_back: set[tuple[str, str]],
) -> Selection:
    """The events of the report of the local days from `first` to `last` of the person.

    The sessions are every session that has an event in the period with the margin of the
    longer of the stale limit and the idle gap around it; the confirmations are the ones of
    the days of the period; the manual entries and the interval annotations are the ones
    whose interval intersects the period; the retractions, the purges, and the annotations
    of a session are the ones of any instant. Every session among the ones selected that
    `held_back` names warns that its events are not complete yet.
    """
    index.update(store_folder)
    purges = PurgeSet.from_events(index.purge_events())
    start, end = _period(days, first, last)
    margin = timedelta(seconds=max(parameters.stale_limit, parameters.idle_gap))
    _sessions, given = index.sessions_and_events(start - margin, end + margin, purges=purges)
    bookkeeping = index.bookkeeping(purges=purges)
    retractions = [event for event in bookkeeping if event["kind"] == "retraction"]
    cancelled_keys = cancelled(retractions)
    session_events = [event for event in given
                      if event_key(event) not in cancelled_keys]
    intervals = index.intervals_between(start, end, purges=purges)
    manual_entries = [event for event in intervals
                      if event["kind"] == "manual_entry"
                      and event_key(event) not in cancelled_keys]
    annotations = [event for event in intervals
                   if event["kind"] == "annotation" and event_key(event) not in cancelled_keys]
    annotations.extend(event for event in bookkeeping
                       if event["kind"] == "annotation"
                       and event_key(event) not in cancelled_keys)
    annotations.sort(key=lambda event: (event["timestamp"], event_order(event)))
    broken = index.broken_lines()
    newer = index.has_newer()
    return Selection(
        first,
        last,
        session_events,
        index.confirmations_of(_day_names(first, last), purges=purges),
        manual_entries,
        annotations,
        retractions,
        cancelled_keys,
        index.segment_states(),
        broken,
        newer,
        _warnings(broken, newer, session_events, held_back),
    )


def cancelled(retractions: Sequence[Event]) -> set[EventKey]:
    """The keys that the active retractions cancel (`architecture.md` › Data flow,
    `command-line.md` › Commands).

    A retraction is active when no active retraction names it, at every depth of a chain:
    a retraction of a retraction brings the event back, a third retraction cancels it
    again, and so on. A retraction without the key that it cancels cancels nothing. A
    retraction names an earlier event, so a chain has no loop; still, a retraction that
    names itself, or whose chain of named keys leads back to it, is no active retraction
    and cancels nothing. The order of the list does not count.
    """
    targets: dict[EventKey, EventKey] = {}
    for retraction in retractions:
        if "retracts" in retraction:
            targets[event_key(retraction)] = EventKey.from_json(retraction["retracts"])
    naming: dict[EventKey, list[EventKey]] = {}
    for key, target in targets.items():
        naming.setdefault(target, []).append(key)
    active = {key: False for key in _in_loops(targets)}
    for key in targets:
        pending = [key]
        while pending:  # the ones that name a retraction are settled before it
            top = pending[-1]
            if top in active:
                pending.pop()
                continue
            unsettled = [one for one in naming.get(top, []) if one not in active]
            if unsettled:
                pending.extend(unsettled)
                continue
            active[top] = not any(active[one] for one in naming.get(top, []))
            pending.pop()
    return {target for key, target in targets.items() if active[key]}


def _in_loops(targets: dict[EventKey, EventKey]) -> set[EventKey]:
    """The retractions that a walk along the keys that the retractions name comes back to:
    a retraction that names itself, and every retraction of a loop."""
    looping: set[EventKey] = set()
    walked: set[EventKey] = set()
    for start in targets:
        path: list[EventKey] = []
        place: dict[EventKey, int] = {}
        key = start
        while key in targets and key not in walked:
            walked.add(key)
            place[key] = len(path)
            path.append(key)
            key = targets[key]
        if key in place:
            looping.update(path[place[key]:])
    return looping


def _period(days: LocalDays, first: date, last: date) -> tuple[datetime, datetime]:
    """The bounds of the period as UTC instants: the start of its first part and the end of
    its last part, the start included and the end excluded (`metrics.md` › Days and weeks).

    Every local day of the period has to have parts: a day before the first entry of the
    time-zone history or of the day start hours stops the selection with `NoLocalDay`.
    """
    one_day = timedelta(days=1)
    parts = days.day_parts(first)
    start = parts[0][0]
    end = parts[-1][1]
    day = first
    while day < last:
        day += one_day
        parts = days.day_parts(day)
        end = parts[-1][1]
    return start, end


def _day_names(first: date, last: date) -> list[str]:
    """The dates of the period as the ISO text that the `day` field of a confirmation
    holds."""
    names = []
    day = first
    one_day = timedelta(days=1)
    while day <= last:
        names.append(day.isoformat())
        day += one_day
    return names


def _warnings(
    broken: Sequence[BrokenLine],
    newer: bool,
    session_events: Sequence[Event],
    held_back: set[tuple[str, str]],
) -> list[dict]:
    """The warnings of the selection: every broken line of the index, a newer schema
    version, and each held-back session among the ones selected, once."""
    given = [{"code": "broken_line", "values": {"segment": line.segment, "line": line.number}}
             for line in broken]
    if newer:
        given.append({"code": "newer_schema_version", "values": {}})
    warned: set[tuple[str, str]] = set()
    for event in session_events:
        held = (event.get("tool"), event.get("session_id"))
        if None in held or held not in held_back or held in warned:
            continue
        warned.add(held)
        given.append({"code": "held_back_events", "values": {"session_id": held[1]}})
    return given
