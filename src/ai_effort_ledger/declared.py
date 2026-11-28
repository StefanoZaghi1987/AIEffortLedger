"""The declared values of a day: the latest timesheet confirmation with its chain of
`replaces`, the timesheet of the day with its lines, the timesheet proposal that the
person confirms or changes, the largest-remainder method that divides a total among its
parts, and the figures that `reports` reads, so that `reports` takes the buckets and
their figures from this module and never imports `attribution` (metrics.md › Declared
values, ADR 0011, ADR 0014).

A day with a timesheet confirmation that is not retracted is a declared day: the sum of
the timesheet entries of its latest confirmation is all the human time of the person in
that day, and its measured values are evidence. The latest confirmation is the one with
the latest `timestamp`, equal instants by event key; a retraction brings back the one
before it, and a retracted confirmation still carries the chain of `replaces`. The
figures are milliseconds since the epoch where they come from the attribution, and
whole seconds where the day shows them.
"""

from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime
from typing import Any, NamedTuple

from .attribution import Attribution, Bucket, BucketFigures
from .days import LocalDays
from .events import Event, EventKey, event_key, event_order
from .metrics import (
    MetricsParameters,
    Span,
    Stream,
    human_time_at_idle_gaps,
    instant_ms,
    presence_span,
    unknown_invocation_share,
)

__all__ = [
    "Attribution",
    "Bucket",
    "BucketFigures",
    "DayFigures",
    "DayTimesheet",
    "Declaration",
    "SetAboveTotal",
    "TimesheetLine",
    "UNATTRIBUTED",
    "bucket_order",
    "day_figures",
    "largest_remainder",
    "latest_confirmation",
    "proposal",
    "whole_seconds",
]

MEASURED_DAY = "measured_day"
DECLARED_DAY = "declared_day"
"""The state of a day, the keys that the texts of `language` name (GLOSSARY › Measured
day, › Declared day)."""

UNATTRIBUTED: Bucket = (None, None)
"""The bucket of the unattributed time of a day, which has no project and no work item
(GLOSSARY › Unattributed)."""


class Declaration(NamedTuple):
    """The latest timesheet confirmation of one day that is not retracted, with the
    warnings of the confirmations of the day (metrics.md › Declared values, ADR 0014)."""

    latest: Event | None
    warnings: list[dict]


class TimesheetLine(NamedTuple):
    """One line of the timesheet of a day, in whole seconds: the bucket, the measured
    human time after the split rule, the measured human time with the manual entries,
    and the declared value, which a measured day holds as None (metrics.md › Declared
    values)."""

    bucket: Bucket
    measured: int
    with_manual: int
    declared: int | None


class DayTimesheet(NamedTuple):
    """The timesheet of one day: its state, its total and its measured total in whole
    seconds, a line for each bucket, the human time at the idle gaps of a measured day,
    and the agent time and the presence span as context (command-line.md › JSON
    documents)."""

    day: date
    state: str
    total: int
    measured_total: int
    lines: list[TimesheetLine]
    human_time_at_idle_gaps: dict[int, int] | None
    unknown_invocation_share: float
    agent_time: int
    presence_span: int | None
    warnings: list[dict]


class DayFigures(NamedTuple):
    """The figures of one day that `reports` reads: the timesheet of the day, the
    figures of the person, and the figures of every project and of every bucket that
    holds time inside the day (metrics.md › Declared values, › Attribution)."""

    timesheet: DayTimesheet
    person: BucketFigures
    projects: dict[str | None, BucketFigures]
    buckets: dict[Bucket, BucketFigures]


def latest_confirmation(
    confirmations: Sequence[Event],
    cancelled: set[EventKey],
) -> Declaration:
    """The latest timesheet confirmation of one day that is not retracted, with the
    warnings of the day (metrics.md › Declared values, ADR 0014).

    The `confirmations` are the ones of one day, retracted or not, as a `Selection`
    holds them; `cancelled` holds the keys that the retractions cancel. The latest is
    the one with the latest `timestamp`, equal instants by event key. An earlier
    confirmation that is not retracted and that the latest does not name, directly or
    through the confirmations between them, warns `confirmation_not_seen`; a
    confirmation whose `timestamp` is earlier than the confirmation that it replaces
    warns `confirmation_before_replaced`.
    """
    by_key = {event_key(item): item for item in confirmations}
    active = [item for item in confirmations if event_key(item) not in cancelled]
    ordered = sorted(active, key=lambda item: (instant_ms(item), event_order(item)))
    latest = ordered[-1] if ordered else None
    named = _named_by_chain(latest, by_key)
    warnings: list[dict] = []
    for confirmation in confirmations:
        replaced = confirmation.get("replaces")
        if replaced is not None:
            other = by_key.get(EventKey.from_json(replaced))
            if other is not None and instant_ms(confirmation) < instant_ms(other):
                warnings.append({"code": "confirmation_before_replaced",
                                 "values": {"event_uid": confirmation["event_uid"]}})
        if (confirmation is not latest and event_key(confirmation) not in cancelled
                and event_key(confirmation) not in named):
            warnings.append({"code": "confirmation_not_seen",
                             "values": {"event_uid": confirmation["event_uid"]}})
    return Declaration(latest, warnings)


def bucket_order(bucket: Bucket, measured: Mapping[Bucket, int]) -> tuple:
    """The order of the entries of a day (metrics.md › Declared values): the unattributed
    time last, whatever its measured time, and the other entries by the larger measured
    human time first, then the project and work item identifiers as text."""
    project, work_item = bucket
    return (project is None, -measured.get(bucket, 0), project or "",
            work_item is None, work_item or "")


def whole_seconds(
    parts: Mapping[Bucket, int],
    measured: Mapping[Bucket, int],
) -> dict[Bucket, int]:
    """The whole seconds of the parts of a day: the whole seconds of the
    total divided among the parts with the largest-remainder method, ties by
    `bucket_order` of the `measured` times, so that the parts add up to the total in the
    JSON document; the part of the total below one whole second stays out (metrics.md ›
    Declared values). The `parts` are in milliseconds, the result in whole seconds."""
    return _divided_whole(parts, lambda bucket: bucket_order(bucket, measured))


def largest_remainder(
    total: int,
    shares: Mapping[Any, int],
    order: Callable[[Any], Any],
    unit: int = 1,
) -> dict[Any, int]:
    """The `total` divided among the `shares` with the largest-remainder method, in units
    of `unit`: each share gets the whole part of its share of the units of
    the total, the units that remain go one by one to the shares with the largest
    remainders, between equal remainders in the order that `order` gives, and the part of
    the total below one unit goes to the share with the largest remainder (metrics.md ›
    Declared values). Shares that all hold zero divide nothing: each holds zero, whatever
    the total."""
    weight = sum(shares.values())
    if not weight:
        return dict.fromkeys(shares, 0)
    units, rest = divmod(total, unit)
    quotients = {key: divmod(units * value, weight) for key, value in shares.items()}
    result = {key: whole for key, (whole, _) in quotients.items()}
    ordered = sorted(shares, key=lambda key: (-quotients[key][1], order(key)))
    for key in ordered[:units - sum(result.values())]:
        result[key] += 1
    result = {key: whole * unit for key, whole in result.items()}
    result[ordered[0]] += rest
    return result


def _divided_whole(
    parts: Mapping[Any, int],
    order: Callable[[Any], tuple],
) -> dict[Any, int]:
    """The whole seconds of the parts, divided by the largest-remainder method with ties
    in the order that `order` gives: the keys of
    the `parts` are buckets, or the project identifiers that the comparison of the
    declared values divides."""
    return largest_remainder(sum(parts.values()) // 1000, parts, order)


class SetAboveTotal(Exception):
    """The stop error of entries whose given values are more than the total of the day
    (command-line.md › Timesheet).

    A stop error carries a code, values, and an exit code; the output language holds the
    text. The text of this code names no value, so the values are empty.
    """

    def __init__(self) -> None:
        self.code = "set_above_total"
        self.values: dict[str, object] = {}
        self.exit_code = 1
        super().__init__(self.code)


def proposal(
    with_manual: Mapping[Bucket, int],
    granularity: int,
    total: int | None = None,
    given: Mapping[Bucket, int] | None = None,
) -> dict[Bucket, int]:
    """The timesheet proposal of a day, in whole seconds (metrics.md › Declared values,
    command-line.md › Timesheet): one entry for each bucket whose measured human time
    with manual entries is not zero, where `with_manual` holds those values in the whole
    seconds that the report shows. Without a `total`, each entry is its
    value rounded up to the `granularity`. With a `total`, the entries that `given`
    does not name divide the rest of the total by their shares, in units of the
    granularity, with the largest-remainder method, ties by `bucket_order`, and the
    entries of `given` hold the values that the person gave; the values of `given` are
    used only with a `total`, and values that are more than the `total` raise
    `SetAboveTotal`."""
    entries = {bucket: value for bucket, value in with_manual.items() if value}
    if total is None:
        return {bucket: (value + granularity - 1) // granularity * granularity
                for bucket, value in entries.items()}
    given = dict(given) if given is not None else {}
    if sum(given.values()) > total:
        raise SetAboveTotal()
    shares = {bucket: value for bucket, value in entries.items() if bucket not in given}
    divided = _divided_total(shares, granularity, total - sum(given.values()))
    for bucket, value in given.items():
        divided[bucket] = divided.get(bucket, 0) + value
    return divided


def _divided_total(
    shares: Mapping[Bucket, int],
    granularity: int,
    remaining_total: int,
) -> dict[Bucket, int]:
    """The rest of the total of a day divided among the entries that it divides, in
    whole seconds (metrics.md › Declared values): the shares of measured human time
    with manual entries, in units of the `granularity`, with the largest-remainder
    method, so that the entries add up to the rest; a part of the total smaller than
    one unit goes to the entry with the largest remainder, ties by `bucket_order` of
    the shares. When no entry holds measured time, the rest is the entry of the
    unattributed time; a rest of zero proposes no entry, also not the one of the
    unattributed time, whose value is zero (metrics.md › Declared values)."""
    if not sum(shares.values()):
        if remaining_total == 0:
            return {}
        return {UNATTRIBUTED: remaining_total}
    return largest_remainder(remaining_total, shares,
                             lambda bucket: bucket_order(bucket, shares), granularity)


def day_figures(
    day: date,
    attribution: Attribution,
    stream: Stream,
    confirmations: Sequence[Event],
    cancelled: set[EventKey],
    days: LocalDays,
    parameters: MetricsParameters,
) -> DayFigures:
    """The figures of one local day that `reports` reads (metrics.md › Declared values,
    ADR 0014): the timesheet of the day with a line for each bucket that holds time in
    it or an entry of the latest confirmation, the figures of the person over every
    bucket, and the figures of every project and bucket of the day.

    The `confirmations` are the ones of the period, as a `Selection` holds them; the
    ones whose `day` is the day given give the state of the day and its declared
    values. The `stream` is the one of the events of the sessions of the period; it
    gives the human time at the idle gaps, the presence span, and the share of the
    human signals of unknown invocation. The projects of the latest confirmation warn
    `declared_project_unknown` once per identifier, and only when the attribution
    warned about no other declared event of the same identifier.
    """
    window = _day_window(days, day)
    buckets = attribution.figures(window)
    projects = attribution.project_figures(window)
    person = attribution.person_figures(window)
    declaration = latest_confirmation(
        [item for item in confirmations if item.get("day") == day.isoformat()],
        cancelled)
    declared = _declared_of(declaration.latest)
    by_manual = {bucket: held.with_manual for bucket, held in buckets.items()}
    measured = whole_seconds({bucket: held.human_time for bucket, held in buckets.items()},
                             by_manual)
    with_manual = whole_seconds(by_manual, by_manual)
    lines = [TimesheetLine(bucket, measured.get(bucket, 0), with_manual.get(bucket, 0),
                           None if declaration.latest is None else declared.get(bucket, 0))
             for bucket in sorted(set(buckets) | set(declared),
                                  key=lambda held: bucket_order(held, with_manual))]
    warnings = list(declaration.warnings)
    if declaration.latest is not None:
        warnings.extend(_below_measured(projects, declared))
    warnings.extend(_unknown_of(declaration.latest, attribution))
    return DayFigures(DayTimesheet(
        day,
        DECLARED_DAY if declaration.latest is not None else MEASURED_DAY,
        sum(declared.values()) if declaration.latest is not None
        else sum(with_manual.values()),
        sum(measured.values()),
        lines,
        None if declaration.latest is not None else _idle_gaps(stream, parameters,
                                                               window),
        unknown_invocation_share(stream, parameters, window),
        _seconds(person.agent_time),
        _presence(stream, parameters, window),
        warnings,
    ), person, projects, buckets)


def _window(parts: Sequence[tuple[datetime, datetime]]) -> list[Span]:
    """The parts of a day as spans of milliseconds since the epoch, the unit of the
    figures (metrics.md › Days and weeks)."""
    return [(round(start.timestamp() * 1000), round(end.timestamp() * 1000))
            for start, end in parts]


def _day_window(days: LocalDays, day: date) -> list[Span]:
    """The parts of the local day as spans of milliseconds since the epoch, the unit of
    the figures (metrics.md › Days and weeks): a journey to the west can give the day
    two parts."""
    return _window(days.day_parts(day))


def _named_by_chain(latest: Event | None, by_key: dict[EventKey, Event]) -> set[EventKey]:
    """The keys that the latest confirmation names, directly or through the
    confirmations between them, retracted or not (metrics.md › Declared values): the
    chain of `replaces`, which a retracted confirmation still carries."""
    named: set[EventKey] = set()
    confirmation = latest
    while confirmation is not None:
        replaced = confirmation.get("replaces")
        if replaced is None:
            break
        key = EventKey.from_json(replaced)
        if key in named or key not in by_key:
            break
        named.add(key)
        confirmation = by_key[key]
    return named


def _declared_of(latest: Event | None) -> dict[Bucket, int]:
    """The declared value of each bucket that the entries of the latest confirmation
    declare, in whole seconds: the sum of its entries, an entry without a work item
    staying in the part of the project that has no work item, and an entry without a
    project declaring the unattributed time (metrics.md › Declared values, ADR 0014)."""
    declared: dict[Bucket, int] = {}
    for entry in (latest.get("entries", []) if latest is not None else []):
        bucket = (entry.get("project"), entry.get("work_item"))
        declared[bucket] = declared.get(bucket, 0) + entry["duration"]
    return declared


def _below_measured(
    projects: dict[str | None, BucketFigures],
    declared: Mapping[Bucket, int],
) -> list[dict]:
    """One `declared_value_below_measured` warning for each project of the day whose
    declared value is lower than its measured human time in the whole seconds that the
    report shows, also when the project has no entry; the comparison is for each
    project, never for each work item, and the unattributed time is no project
    (metrics.md › Declared values, ADR 0014)."""
    measured = _divided_whole(
        {project: held.human_time for project, held in projects.items()},
        lambda project: (project is None, project or ""))
    declared_of: dict[str, int] = {}
    for bucket, value in declared.items():
        if bucket[0] is not None:
            declared_of[bucket[0]] = declared_of.get(bucket[0], 0) + value
    return [{"code": "declared_value_below_measured", "values": {"project": project}}
            for project, held in projects.items()
            if project is not None
            and declared_of.get(project, 0) < measured.get(project, 0)]


def _unknown_of(
    latest: Event | None,
    attribution: Attribution,
) -> list[dict]:
    """The `declared_project_unknown` warnings of the projects of the entries of the
    latest confirmation (metrics.md › Attribution, ADR 0019): once per identifier, in
    the order of the entries, and only for an identifier that no other declared event
    of the report warned about already."""
    if latest is None:
        return []
    warned = {notice["values"]["project"] for notice in attribution.warnings
              if notice["code"] == "declared_project_unknown"}
    identifiers: list[str] = []
    for entry in latest.get("entries", []):
        project = entry.get("project")
        if project is not None and project not in identifiers:
            identifiers.append(project)
    return [notice for notice in attribution.unknown_projects(identifiers)
            if notice["values"]["project"] not in warned]


def _idle_gaps(
    stream: Stream,
    parameters: MetricsParameters,
    window: Sequence[Span],
) -> dict[int, int]:
    """The human time of the day at the idle gaps, in whole seconds (metrics.md ›
    Uncertainty)."""
    return {gap: _seconds(milliseconds) for gap, milliseconds
            in human_time_at_idle_gaps(stream, parameters, window).items()}


def _presence(
    stream: Stream,
    parameters: MetricsParameters,
    window: Sequence[Span],
) -> int | None:
    """The presence span of the person inside the day, in whole seconds (metrics.md ›
    Human time)."""
    held = presence_span(stream, parameters, window)
    return None if held is None else _seconds(held)


def _seconds(milliseconds: int) -> int:
    """A duration in whole seconds, rounded to the nearest one: a figure that sums with
    no other one (command-line.md › JSON documents)."""
    return (milliseconds + 500) // 1000
