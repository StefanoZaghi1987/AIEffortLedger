"""The JSON documents of the commands (command-line.md › JSON documents): for each
command, exactly the keys of its row of the table, with the durations in whole seconds,
the days as `YYYY-MM-DD`, and a project or a work item as its identifier with the name
that reports show, or null."""

from collections.abc import Mapping, Sequence
from datetime import date
from typing import NamedTuple

from ..declared import (
    Bucket,
    BucketFigures,
    DayFigures,
    DayTimesheet,
    TimesheetLine,
    _seconds,
    largest_remainder,
)
from ..events import Event

_KEY_FACTS = ("event_uid", "kind", "timestamp")
"""The keys that each entry of `entries` holds first (command-line.md › JSON documents)."""

_NO_FIGURES = BucketFigures(0, 0, 0, 0, {}, 0.0, 0.0)
"""The figures of a bucket that holds no time in the day: their absence is a sound zero."""

_PRESENT = ("person_only", "supervised")
"""The activity classes where the person is present: they divide the human time of every
holder (command-line.md › Reports)."""

_REST = ("unattended", "blocked", "idle")
"""The other classes of the person, which divide the whole seconds that its human time
leaves of the day (command-line.md › Reports)."""

_CLASS_ORDER = (*_PRESENT, *_REST)
"""The activity classes in the order of the table of metrics.md › Activity classes: between
equal remainders, the class that comes first takes the second."""


class Names(NamedTuple):
    """The names that reports show for the project identifiers and for the work items of
    one project (ADR 0019): the values that `attribution` computes for a report."""

    projects: dict[str, str]
    work_items: dict[tuple[str, str], str]


def timesheet_document(days: Sequence[DayFigures], names: Names) -> dict:
    """The document of `report timesheet` (command-line.md › JSON documents): one entry
    for each day of the period, in the order of the days."""
    return {"days": [_timesheet_of(figures, None, names, proposed=False)
                     for figures in days]}


def timesheet_day_document(
    figures: DayFigures,
    proposal: Mapping[Bucket, int] | None,
    names: Names,
) -> dict:
    """The document of `timesheet <day>` (command-line.md › JSON documents): the day of
    `report timesheet`, each entry also with `proposed` — the proposed value in whole
    seconds, or null when the proposal holds none — and the `context` of the day, its
    agent time and its presence span."""
    return _timesheet_of(figures, proposal, names, proposed=True)


def day_document(figures: DayFigures, names: Names) -> dict:
    """The document of `report day` (command-line.md › JSON documents): the person, the
    projects of the day with the unattributed time, and the work items of its buckets,
    each with its measures and its shares."""
    sheet = figures.timesheet
    document = {
        "day": sheet.day.isoformat(),
        "state": sheet.state,
        "unknown_invocation_share": sheet.unknown_invocation_share,
    }
    _idle_gaps_of(sheet, document)
    document["person"] = _measures(figures.person, person=True)
    document["projects"] = [_project_document(project, held, names)
                            for project, held in figures.projects.items()]
    document["work_items"] = [_work_item_document(line.bucket, figures, names)
                              for line in sheet.lines
                              if line.bucket[1] is not None
                              and line.bucket in figures.buckets]
    return document


def sessions_document(day: date, sessions: list[dict]) -> dict:
    """The document of `sessions <day>` (command-line.md › JSON documents): the day and
    the sessions as the command gives them, each session with `session_id`, `tool`,
    `start`, `end`, `cwd`, `branch`, and `parts`, and each part with its `project` and
    `work_item` objects and its durations in whole seconds."""
    return {"day": day.isoformat(), "sessions": sessions}


def entries_document(day: date, events: list[Event]) -> dict:
    """The document of `entries` (command-line.md › JSON documents): the day and, for
    each event, `event_uid`, `kind`, and `timestamp` first, then its other fields by
    name."""
    ordered = []
    for event in events:
        entry = {key: event[key] for key in _KEY_FACTS}
        entry.update((key, event[key]) for key in sorted(event)
                     if key not in _KEY_FACTS)
        ordered.append(entry)
    return {"day": day.isoformat(), "entries": ordered}


def _timesheet_of(
    figures: DayFigures,
    proposal: Mapping[Bucket, int] | None,
    names: Names,
    proposed: bool,
) -> dict:
    """The document of one day of `report timesheet` or of `timesheet <day>`: its state,
    its totals, the idle gaps of a measured day, the share of unknown invocation, and
    its entries (command-line.md › JSON documents)."""
    sheet = figures.timesheet
    document = {
        "day": sheet.day.isoformat(),
        "state": sheet.state,
        "total": sheet.total,
        "measured_total": sheet.measured_total,
        "unknown_invocation_share": sheet.unknown_invocation_share,
        "entries": [_entry_document(line, figures, proposal, names, proposed)
                    for line in sheet.lines],
    }
    _idle_gaps_of(sheet, document)
    if proposed:
        context: dict = {"agent_time": sheet.agent_time}
        ratio = _parallel_ratio(figures.person)
        if ratio is not None:
            context["parallel_ratio"] = ratio
        context["presence_span"] = sheet.presence_span
        document["context"] = context
    return document


def _entry_document(
    line: TimesheetLine,
    figures: DayFigures,
    proposal: Mapping[Bucket, int] | None,
    names: Names,
    proposed: bool,
) -> dict:
    """The document of one entry of a day (command-line.md › JSON documents): its
    project and work item objects, its three values in whole seconds, and the shares of
    the inferred repository identity of its bucket — which holds no figure when the day
    is declared only, and then zero."""
    held = figures.buckets.get(line.bucket)
    if held is None:
        held = _NO_FIGURES
    document = {
        "project": _project_of(line.bucket, names),
        "work_item": _work_item_of(line.bucket, names),
        "measured": line.measured,
        "with_manual_entries": line.with_manual,
        "declared": line.declared,
        "inferred_human_share": held.inferred_human_share,
        "inferred_agent_share": held.inferred_agent_share,
    }
    if proposed:
        document["proposed"] = None if proposal is None else proposal.get(line.bucket)
    return document


def _project_document(project: str | None, held: BucketFigures, names: Names) -> dict:
    """The document of one project of a day (command-line.md › JSON documents): its
    project object, or null for the unattributed time, its measures, and its shares."""
    document = {"project": None if project is None
                else {"id": project, "name": names.projects[project]}}
    document.update(_measures(held))
    document["inferred_human_share"] = held.inferred_human_share
    document["inferred_agent_share"] = held.inferred_agent_share
    return document


def _work_item_document(bucket: Bucket, figures: DayFigures, names: Names) -> dict:
    """The document of the work item of one bucket of a day (command-line.md › JSON
    documents): its work item object, its measures, and its shares."""
    held = figures.buckets[bucket]
    document = {"work_item": _work_item_of(bucket, names)}
    document.update(_measures(held))
    document["inferred_human_share"] = held.inferred_human_share
    document["inferred_agent_share"] = held.inferred_agent_share
    return document


def _measures(held: BucketFigures, *, person: bool = False) -> dict:
    """The measures of one project or work item, or of the person, in whole seconds
    (command-line.md › JSON documents, › Reports). `human_time` is the measured human time
    with the manual entries, on a measured day and on a declared day alike: the human time
    of a measured day is their union, so a manual entry counts for the human time of the person
    and of its project (GLOSSARY.md › Measured day; metrics.md › Declared values). The
    activity classes of every holder come from that human time (metrics.md › Activity
    classes), so their whole seconds are divided with the largest-remainder method: the
    human time between the classes person only and supervised, by their milliseconds, and
    for the person the whole seconds that remain of its day — the five classes cover it —
    among unattended, blocked, and idle. Every other class is rounded to the nearest
    second alone, as the agent time and the blocked time are. The parallel ratio divides
    the exact figures in milliseconds, before any of them is rounded, and stays away when
    the holder has no agent time (metrics.md › Agent time)."""
    classes = held.activity_classes
    human = _seconds(held.with_manual)
    seconds = {name: _seconds(value) for name, value in classes.items()}
    seconds.update(largest_remainder(
        human, {name: classes[name] for name in _PRESENT if name in classes},
        _CLASS_ORDER.index))
    if person:
        seconds.update(largest_remainder(
            _seconds(sum(classes.values())) - human,
            {name: classes[name] for name in _REST if name in classes},
            _CLASS_ORDER.index))
    measures = {"human_time": human, "agent_time": _seconds(held.agent_time)}
    ratio = _parallel_ratio(held)
    if ratio is not None:
        measures["parallel_ratio"] = ratio
    measures["blocked_time"] = _seconds(held.blocked_time)
    measures["activity_classes"] = seconds
    return measures


def _parallel_ratio(held: BucketFigures) -> float | None:
    """The parallel ratio of a holder from its exact figures, in milliseconds (metrics.md
    › Agent time): its agent time divided by its Supervised time plus its Unattended
    time. The two classes are the union of the agent spans of the holder, so their sum is
    zero exactly when the holder has no agent time, and then the ratio is no number."""
    union = (held.activity_classes.get("supervised", 0)
             + held.activity_classes.get("unattended", 0))
    if union == 0:
        return None
    return held.agent_time / union


def _idle_gaps_of(sheet: DayTimesheet, document: dict) -> None:
    """Add the human time at the idle gaps of a measured day to the document, from the
    idle gap in seconds to the human time; a declared day holds no such key."""
    held = sheet.human_time_at_idle_gaps
    if held is not None:
        document["human_time_at_idle_gaps"] = {
            str(gap): seconds for gap, seconds in sorted(held.items())}


def _project_of(bucket: Bucket, names: Names) -> dict | None:
    """The project object of a bucket, or null for the unattributed time."""
    project = bucket[0]
    return None if project is None else {"id": project, "name": names.projects[project]}


def _work_item_of(bucket: Bucket, names: Names) -> dict | None:
    """The work item object of a bucket, or null when the bucket holds no work item."""
    work_item = bucket[1]
    return None if work_item is None else {
        "id": work_item, "name": names.work_items[(bucket[0], work_item)]}
