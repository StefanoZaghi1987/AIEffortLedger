"""The split rule and the figures of the buckets: every instant of the measured human
time to the human signal whose interval ends first, the manual entries over it, and the
agent time and the blocked time by their events (metrics.md › Attribution, › Declared
values, ADR 0021).

The split rule gives each instant of measured human time to one human signal, so the
projects and the work items need no separate split: the instant takes the attribution of
that signal. An entry of mode `overlapping` applies to its whole interval over the
measured time, an entry of mode `additional` counts only where the measured time does
not cover it, and two entries that overlap each other resolve by their timestamp, equal
instants by event key. The agent time divides at its events, and a holder counts it as
the sum over the agents of the union of the parts of each agent (metrics.md › Agent
time); the blocked time takes the attribution of its decision request. The attributed
parts and the unattributed bucket add up to the human time of the period (acceptance
criterion 4).
"""

from bisect import bisect_left, bisect_right, insort
from collections.abc import Iterable, Iterator, Sequence
from itertools import accumulate, groupby
from typing import Any, NamedTuple

from ..configuration import PersonConfiguration
from ..days import LocalDays
from ..events import Event, EventKey, event_key, event_order
from ..language import CONFIGURATION_ERROR_CODES
from ..metrics import (
    Agent,
    HumanInterval,
    ManualPart,
    Metrics,
    Span,
    activity_classes,
    instant_ms,
    intersect,
    stored_category,
    total,
    total_by_key,
    union,
)
from .annotations import Bucket, _event_buckets
from .names import declared_project_unknown, project_names
from .rules import category_of

Piece = Span | tuple[Span, Agent]
"""A piece of a dimension that a bucket holds: a span, or, for the agent time, a span with
the agent that works it, so that the figures sum the agent time over the agents."""


class BucketFigures(NamedTuple):
    """The figures of one bucket or project inside the window of a report, in
    milliseconds since the epoch (decision D12): the measured human time after the
    split rule, the measured human time with the manual entries, the agent time, and
    the blocked time of the bucket, its activity classes — on its human time with manual
    entries — and the shares that rest on an inferred repository identity (metrics.md ›
    Attribution, › Activity classes, › Declared values, ADR 0018)."""

    human_time: int
    with_manual: int
    agent_time: int
    blocked_time: int
    activity_classes: dict[str, int]
    inferred_human_share: float
    inferred_agent_share: float


def split_human(intervals: Sequence[HumanInterval]) -> list[tuple[Span, Event]]:
    """The measured human time divided by the split rule (metrics.md › Attribution,
    ADR 0021): the disjoint parts of the union of the intervals, each with the human
    signal whose interval ends first at its instants; intervals that end at the same
    instant resolve by the event key of their signal, the larger key, as every rule
    that applies over another.

    The claimed instants are kept as sorted, disjoint spans, and a new interval touches
    only the window of them that can reach it: the claim order ends every claimed piece
    at or before the end of the interval that claims next, so only a piece that starts
    before that end can share an instant with it, and each interval enters at most one
    piece, which keeps the walk close to linear in the number of the intervals."""
    claimed: list[Span] = []
    parts: list[tuple[Span, Event]] = []
    for interval in _claim_order(intervals):
        start, end = interval.start, interval.end
        if start >= end:
            continue
        first = bisect_right(claimed, start, key=lambda piece: piece[1])
        last = bisect_left(claimed, end, key=lambda piece: piece[0])
        window = claimed[first:last]
        cursor = start
        for piece_start, piece_end in window:
            if piece_start > cursor:
                parts.append(((cursor, piece_start), interval.signal))
            cursor = max(cursor, piece_end)
        if cursor < end:
            parts.append(((cursor, end), interval.signal))
        claimed[first:last] = [(
            min(start, window[0][0]) if window else start,
            max(end, window[-1][1]) if window else end)]
    parts.sort(key=lambda part: part[0])
    return parts


def _claim_order(intervals: Sequence[HumanInterval]) -> Iterator[HumanInterval]:
    """The intervals in the order in which they claim their instants: the interval that
    ends first claims first, and at the same end the larger event key claims first, so
    that it takes the shared instants (metrics.md › Attribution)."""
    ordered = sorted(intervals, key=lambda held: (held.end, event_order(held.signal)))
    for _, group in groupby(ordered, key=lambda held: held.end):
        yield from reversed(list(group))


class Attribution:
    """The attribution of one report: the bucket of every event of its sessions, the
    names of the projects and of the work items, and the warnings and configuration
    errors of the report; `figures` measures the buckets inside a window,
    `project_figures` measures every project from the spans of its buckets, and
    `person_figures` measures the person over every bucket: in each, the human time and
    the blocked time are unions and the agent time is the sum over the agents of the
    union of the parts of each. `session_parts` divides the human time and the agent
    time by session and bucket (metrics.md › Attribution, › Agent time)."""

    def __init__(
        self,
        metrics: Metrics,
        buckets: dict[EventKey, Bucket],
        parts: list[tuple[Span, Event]],
        names: dict[str, str],
        work_item_names: dict[tuple[str, str], str],
        configuration_errors: list[dict],
        warnings: list[dict],
        person: PersonConfiguration,
        hints: set[str],
        inferred: frozenset[EventKey],
    ) -> None:
        self._metrics = metrics
        self._buckets = buckets
        self._parts = parts
        self._human = _bounds(parts, [span for span, _ in parts])
        self._manual = _bounds(metrics.manual,
                               [(part.start, part.end) for part in metrics.manual])
        self._agent = _bounds(metrics.agent,
                             [(part.start, part.end) for part in metrics.agent])
        self._blocked = _bounds(metrics.blocked,
                                [(held.start, held.end) for held in metrics.blocked])
        self.names = names
        self.work_item_names = work_item_names
        self.configuration_errors = configuration_errors
        self.warnings = warnings
        self._person = person
        self._hints = hints
        self._inferred = inferred
        """The event keys of the events whose repository identity, their own or the one
        they take from the previous event of their session, rests on an inferred basis."""
        self._buckets_of_window: dict[tuple[Span, ...],
                                      dict[Bucket, dict[str, list[Piece]]]] = {}
        """The buckets of the windows already asked for: `figures` and `project_figures`
        measure the same window of a day, and the spans of the parts never change."""

    def person_figures(self, window: Sequence[Span]) -> BucketFigures:
        """The figures of the person inside the window: the unions over the buckets of
        the measured human time with the manual entries and of the blocked time, the agent
        time as the sum over the agents of the union of the parts of each, the activity
        classes of the person, the class idle included, and the shares that rest on an
        inferred repository identity (metrics.md › Attribution, › Agent time, › Activity
        classes)."""
        inside = union(window)
        human: list[Span] = []
        inferred_human: list[Span] = []
        for span, signal in self._human.within(inside):
            for piece in intersect([span], inside):
                human.append(piece)
                if self._rests_on_inferred(signal):
                    inferred_human.append(piece)
        manual = [piece for part in self._manual.within(inside)
                  for piece in intersect([(part.start, part.end)], inside)]
        agent: list[tuple[Span, Agent]] = []
        inferred_agent: list[tuple[Span, Agent]] = []
        for part in self._agent.within(inside):
            for piece in intersect([(part.start, part.end)], inside):
                agent.append((piece, part.agent))
                if self._rests_on_inferred(part.event):
                    inferred_agent.append((piece, part.agent))
        blocked = [piece for interval in self._blocked.within(inside)
                   for piece in intersect([(interval.start, interval.end)], inside)]
        present = union(human + manual)
        measured, working = total(union(human)), total_by_key(agent)
        return BucketFigures(
            measured, total(present), working, total(union(blocked)),
            activity_classes(present, [span for span, _ in agent], blocked, inside),
            _share(total(union(inferred_human)), measured),
            _share(total_by_key(inferred_agent), working))

    def unknown_projects(self, identifiers: Iterable[str]) -> list[dict]:
        """One `declared_project_unknown` warning for each of the given project
        identifiers that no identity rule, no entry of the person configuration, and no
        repository identity of this attribution gives (metrics.md › Attribution, ADR
        0019); `declared` calls it for the projects of the latest confirmation."""
        return declared_project_unknown(identifiers, self._person, self._hints)

    @property
    def repository_hints(self) -> frozenset[str]:
        """The repository identities that the events of the sessions of this attribution
        name in `repo_hint`, which give the default names of the projects (metrics.md ›
        Attribution, ADR 0019)."""
        return frozenset(self._hints)

    def work_item_name(self, project: str, work_item: str) -> str:
        """The name of the work item `work_item` of the project `project`: the name that
        the person configuration gives it, else its identifier (metrics.md ›
        Attribution)."""
        return _work_item_name(self._person, project, work_item)

    def figures(self, window: Sequence[Span]) -> dict[Bucket, BucketFigures]:
        """The figures of every bucket that holds time inside the window, which a local
        day holds as one or two spans (metrics.md › Days and weeks): the human time by
        the split rule, the figure with the manual entries by the paint over it, the
        agent time by the event that ends each part, summed over the agents, the blocked
        time by its decision request, and the activity classes of the bucket, which rest
        on that figure with the manual entries and hold no class idle (metrics.md ›
        Attribution, › Agent time, › Activity classes)."""
        inside = union(window)
        return {bucket: self._figures_of(held, inside)
                for bucket, held in self._by_bucket(inside).items()}

    def project_figures(self, window: Sequence[Span]) -> dict[str | None, BucketFigures]:
        """The figures of every project that holds time inside the window, the
        unattributed time included as `None`, each from the spans of its buckets: the
        human time and the blocked time from their unions, so that the blocked time and
        the activity classes of a project are never sums of the figures of its work
        items, and the agent time as the sum over the agents of the union of the parts
        of each (metrics.md › Attribution, › Agent time, › Activity classes)."""
        inside = union(window)
        by_bucket = self._by_bucket(inside)
        figures: dict[str | None, BucketFigures] = {}
        for project in sorted({bucket[0] for bucket in by_bucket},
                              key=lambda name: (name is None, name or "")):
            merged: dict[str, list[Piece]] = {}
            for bucket, held in by_bucket.items():
                if bucket[0] != project:
                    continue
                for key, spans in held.items():
                    merged.setdefault(key, []).extend(spans)
            figures[project] = self._figures_of(merged, inside)
        return figures

    def session_parts(
        self, window: Sequence[Span],
    ) -> dict[tuple[str, str], dict[Bucket, tuple[int, int]]]:
        """The human time and the agent time of each bucket of each session inside the
        window, which `sessions <day>` shows (command-line.md › Commands): the human
        time that the split rule gives to the signals of the session, and the agent
        time of its agents by the event that ends each part, the sum over the agents of
        the session (metrics.md › Attribution, › Agent time)."""
        inside = union(window)
        held: dict[tuple[str, str], dict[Bucket, list[int]]] = {}
        for span, signal in self._parts:
            _count(held, (signal["tool"], signal["session_id"]),
                   self._buckets[event_key(signal)], total(intersect([span], inside)),
                   0)
        agent_pieces: dict[tuple[str, str], dict[Bucket, list[tuple[Span, Agent]]]] = {}
        for part in self._metrics.agent:
            pieces = intersect([(part.start, part.end)], inside)
            if not pieces:
                continue
            buckets = agent_pieces.setdefault((part.agent[0], part.agent[1]), {})
            buckets.setdefault(self._buckets[event_key(part.event)], []).extend(
                (piece, part.agent) for piece in pieces)
        for session, buckets in agent_pieces.items():
            for bucket, pieces in buckets.items():
                _count(held, session, bucket, total_by_key(pieces), 1)
        return {session: {bucket: (times[0], times[1])
                          for bucket, times in parts.items()}
                for session, parts in held.items()}

    def _by_bucket(self, inside: list[Span]) -> dict[Bucket, dict[str, list[Piece]]]:
        """The pieces of every dimension inside the window, by bucket: the human time of
        the split rule with the spans whose signal rests on an inferred repository
        identity, the paint of the manual entries, the agent time with the parts whose
        event rests on one, each piece with the agent that works it, and the blocked time
        (metrics.md › Attribution, ADR 0018). Only a bucket that holds an instant of the
        window enters. The buckets of one window are computed once: `figures` and
        `project_figures` measure the same window of one day, and the spans of the parts
        never change after the construction."""
        key = tuple(inside)
        held = self._buckets_of_window.get(key)
        if held is None:
            held = self._buckets_inside(inside)
            self._buckets_of_window[key] = held
        return held

    def _buckets_inside(self, inside: list[Span]) -> dict[Bucket, dict[str, list[Piece]]]:
        """The pieces of every dimension inside the window, by bucket, computed from the
        parts that can hold an instant of the window."""
        held: dict[Bucket, dict[str, list[Piece]]] = {}
        human = self._human.within(inside)
        for span, signal in human:
            spans = intersect([span], inside)
            key = event_key(signal)
            bucket = self._buckets[key]
            _extend(held, bucket, "human", spans)
            if key in self._inferred:
                _extend(held, bucket, "inferred_human", spans)
        for bucket, spans in _painted(self._manual.within(inside), self._buckets, human,
                                      inside).items():
            _extend(held, bucket, "manual", spans)
        for part in self._agent.within(inside):
            key = event_key(part.event)
            bucket = self._buckets[key]
            spans = intersect([(part.start, part.end)], inside)
            if spans:
                pieces = [(span, part.agent) for span in spans]
                _extend(held, bucket, "agent", pieces)
                if key in self._inferred:
                    _extend(held, bucket, "inferred_agent", pieces)
        for interval in self._blocked.within(inside):
            _extend(held, self._buckets[event_key(interval.request)], "blocked",
                    intersect([(interval.start, interval.end)], inside))
        return held

    def _rests_on_inferred(self, event: Event) -> bool:
        """Whether the repository identity of the event, its own or the one it takes from
        the previous event of its session, rests on an inferred basis (ADR 0018)."""
        return bool(self._inferred) and event_key(event) in self._inferred

    @staticmethod
    def _figures_of(held: dict[str, list[Piece]], inside: list[Span]) -> BucketFigures:
        """The figures of one bucket or project from its pieces: the totals of the human
        time, of the manual entries, and of the blocked time, the agent time as the sum
        over the agents of the union of the parts of each, the activity classes of its
        human time with manual entries, of its agent time, and of its blocked time,
        without the class idle, and the shares of the human time and the agent time that
        rest on an inferred repository identity (metrics.md › Attribution, › Agent time,
        › Activity classes, ADR 0018)."""
        classes = activity_classes(held["manual"], [span for span, _ in held["agent"]],
                                   held["blocked"], inside)
        human, agent = total(held["human"]), total_by_key(held["agent"])
        return BucketFigures(
            human, total(held["manual"]), agent, total(held["blocked"]),
            {name: value for name, value in classes.items() if name != "idle"},
            _share(total(held["inferred_human"]), human),
            _share(total_by_key(held["inferred_agent"]), agent))


def attribute(
    session_events: Sequence[Event],
    annotations: Sequence[Event],
    manual_entries: Sequence[Event],
    metrics: Metrics,
    person: PersonConfiguration,
    days: LocalDays,
    confirmations: Sequence[Event] = (),
) -> Attribution:
    """The attribution of a report (metrics.md › Attribution): the buckets of the
    events of the sessions, the bucket of each manual entry by the project and the work
    item that the person declared, the names of every project and work item that the
    events, the manual entries, or the timesheet confirmations name, and the warnings
    and configuration errors of the report.

    The `metrics` argument must have been computed from the same `session_events`: the
    bucket lookup indexes the events of the split parts, and a `Metrics` that other events
    built stops at this call when a manual entry of mode `overlapping` overlaps one of its
    parts, and otherwise on the first window that reads one of its parts, and on
    `session_parts`. The projects and the work items of the confirmations get names too, so
    that a project that only a timesheet confirmation names has one (metrics.md › Declared
    values); the declared values themselves are the work of the `declared` module.
    """
    buckets, notices, inferred = _event_buckets(session_events, annotations, person, days)
    parts = split_human(metrics.human)
    hints = _repository_hints(session_events)
    names, name_errors = project_names(
        sorted(_project_identifiers(buckets, manual_entries, confirmations)), hints, person)
    work_item_names = {pair: _work_item_name(person, *pair) for pair in sorted(
        _work_item_pairs(buckets, manual_entries, confirmations))}
    errors = [notice for notice in notices if notice["code"] in CONFIGURATION_ERROR_CODES]
    errors.extend(name_errors)
    errors.extend(_category_conflicts(session_events, person))
    warnings = [notice for notice in notices
                if notice["code"] not in CONFIGURATION_ERROR_CODES]
    warnings.extend(metrics.warnings)
    known = {notice["values"]["project"] for notice in warnings
             if notice["code"] == "declared_project_unknown"}
    warnings.extend(notice for notice in declared_project_unknown(
        (entry["project"] for entry in manual_entries
         if entry.get("project") is not None),
        person, hints)
        if notice["values"]["project"] not in known)
    warnings.extend(_entry_overlap_changes(metrics, buckets, parts))
    return Attribution(metrics, buckets, parts, names, work_item_names, errors, warnings,
                       person, hints, inferred)


def _repository_hints(session_events: Sequence[Event]) -> set[str]:
    """The repository identities that the events of the sessions name in `repo_hint`."""
    return {event["repo_hint"] for event in session_events
            if event.get("repo_hint") is not None}


def _work_item_name(person: PersonConfiguration, project: str, work_item: str) -> str:
    """The name of a work item: the name that the person configuration gives the pair of
    its project and its identifier, else its identifier (metrics.md › Attribution)."""
    given = {(item.project, item.id): item.name for item in person.work_items}
    return given.get((project, work_item), work_item)


def _project_identifiers(
    buckets: dict[EventKey, Bucket],
    manual_entries: Sequence[Event],
    confirmations: Sequence[Event],
) -> set[str]:
    """Every project identifier that the report names: the projects of the buckets, of
    the manual entries, and of the entries of the timesheet confirmations, the
    unattributed time excepted (metrics.md › Attribution)."""
    projects = {project for project, _ in buckets.values() if project is not None}
    projects.update(entry["project"] for entry in manual_entries
                    if entry.get("project") is not None)
    for confirmation in confirmations:
        projects.update(entry["project"] for entry in confirmation.get("entries", [])
                        if entry.get("project") is not None)
    return projects


def _work_item_pairs(
    buckets: dict[EventKey, Bucket],
    manual_entries: Sequence[Event],
    confirmations: Sequence[Event],
) -> set[tuple[str, str]]:
    """Every project and work item that the report names: the buckets that hold a work
    item, the manual entries that hold both, and the entries of the confirmations that
    hold both (metrics.md › Attribution)."""
    pairs = {pair for pair in buckets.values()
             if pair[0] is not None and pair[1] is not None}
    pairs.update((entry["project"], entry["work_item"]) for entry in manual_entries
                 if entry.get("project") is not None
                 and entry.get("work_item") is not None)
    for confirmation in confirmations:
        pairs.update((entry["project"], entry["work_item"])
                     for entry in confirmation.get("entries", [])
                     if entry.get("project") is not None
                     and entry.get("work_item") is not None)
    return pairs


def _category_conflicts(
    session_events: Sequence[Event],
    person: PersonConfiguration,
) -> list[dict]:
    """One `category_rule_conflict` error for each pair of matching category rules of
    which neither is narrower, however many tool calls the pair both matches, with one
    event that they match as its event key: the first such tool call in the order of
    the timestamp, equal instants by event key (configuration.md › Matching)."""
    conflicts: dict[tuple[str, str], tuple[tuple, dict]] = {}
    for event in session_events:
        if event["kind"] != "tool_call":
            continue
        _, error = category_of(event.get("tool_name", ""), stored_category(event),
                               person.category_rules)
        if error is None:
            continue
        pair = (error["values"]["first"], error["values"]["second"])
        order = (event["timestamp"], event_order(event))
        if pair not in conflicts or order < conflicts[pair][0]:
            error["values"]["event"] = event_key(event).to_json()
            conflicts[pair] = (order, error)
    return [error for _, error in conflicts.values()]


def _entry_overlap_changes(
    metrics: Metrics,
    buckets: dict[EventKey, Bucket],
    parts: list[tuple[Span, Event]],
) -> list[dict]:
    """One `manual_entry_overlap` warning for each manual entry of mode `overlapping`
    that overlaps measured human time of another project or work item, the change that
    its attribution on the whole interval makes (metrics.md › Declared values). The
    `parts` are the split of the metrics that `attribute` computed once."""
    changes: list[dict] = []
    warned: set[EventKey] = set()
    for part in metrics.manual:
        if part.entry.get("manual_mode") != "overlapping":
            continue
        key = event_key(part.entry)
        bucket = (part.entry.get("project"), part.entry.get("work_item"))
        moved = any(buckets[event_key(signal)] != bucket
                    for span, signal in parts
                    if span[0] < part.end and part.start < span[1])
        if moved and key not in warned:
            warned.add(key)
            changes.append({"code": "manual_entry_overlap",
                            "values": {"event_uid": part.entry["event_uid"]}})
    return changes


class _Bounds(NamedTuple):
    """The parts of one dimension of a report with what lets a window read only the
    parts that can hold an instant of it. The parts come sorted by start, as
    `split_human`, `manual_parts`, `agent_parts`, and `blocked_intervals` sort them,
    and `reach` holds, for each position, the latest end among the parts up to it,
    which never decreases. The parts that can hold an instant of a window lie between
    the first whose latest end is after the start of the window and the last that
    starts before its end: a part before that slice ends at or before the start of the
    window, and a part after it starts at or after its end. A window of two parts, as
    a journey gives a day, takes the slice from the start of its first part to the end
    of its last, and `intersect` cuts the gap out (metrics.md › Days and weeks)."""

    parts: Sequence[Any]
    starts: list[int]
    reach: list[int]

    def within(self, window: Sequence[Span]) -> Sequence[Any]:
        """The parts that can hold an instant of the window; an empty window gives no
        part, and a window whose spans hold no instant can give parts, which `intersect`
        then empties."""
        if not window:
            return []
        return self.parts[
            bisect_right(self.reach, min(start for start, _ in window)):
            bisect_left(self.starts, max(end for _, end in window))]


def _bounds(parts: Sequence[Any], spans: Sequence[Span]) -> _Bounds:
    """The bounds of the parts, from their spans in the order of the parts."""
    return _Bounds(parts, [start for start, _ in spans],
                   list(accumulate((end for _, end in spans), max)))


def _painted(
    manual: Sequence[ManualPart],
    buckets: dict[EventKey, Bucket],
    parts: list[tuple[Span, Event]],
    inside: list[Span],
) -> dict[Bucket, list[Span]]:
    """The spans of the window that each bucket holds of the measured human time with
    the manual entries (metrics.md › Declared values, › Attribution): the window
    painted in one pass, where an entry of mode `overlapping` covers the measured time
    of its whole interval, an entry of mode `additional` counts only where the measured
    time does not cover it, two entries that overlap each other resolve by their
    timestamp, equal instants by event key, and the measured time holds where no entry
    covers. The `manual` and the `parts` are the manual entries and the split of the
    human time that `attribute` computed once, kept to those that can hold an instant
    of the window. The spans of a bucket are disjoint, and no two buckets hold one
    instant, so the project figures can take their union.

    The limits of the layers divide the window into elementary spans. A sweep from one
    to the next holds the layers that cover the span — those that began at or before
    its start and end after it — and gives the span to the best of them; the layers
    stay in the order of the list, so an equal rank and an equal order go to the first."""
    layers: list[tuple[int, tuple, int, int, Bucket]] = []
    for part in manual:
        rank = 0 if part.entry.get("manual_mode") == "overlapping" else 1
        order = (instant_ms(part.entry), event_order(part.entry))
        bucket = (part.entry.get("project"), part.entry.get("work_item"))
        for start, end in intersect([(part.start, part.end)], inside):
            layers.append((rank, order, start, end, bucket))
    for span, signal in parts:
        for start, end in intersect([span], inside):
            layers.append((2, (0, ()), start, end, buckets[event_key(signal)]))
    moments = sorted({moment for layer in layers for moment in layer[2:4]})
    beginning: dict[int, list[int]] = {}
    for position, layer in enumerate(layers):
        beginning.setdefault(layer[2], []).append(position)
    spans: dict[Bucket, list[Span]] = {}
    active: list[int] = []
    for start, end in zip(moments, moments[1:]):
        active = [held for held in active if layers[held][3] > start]
        for held in beginning.get(start, ()):
            insort(active, held)
        winner: tuple[int, tuple, Bucket] | None = None
        for held in active:
            rank, order, _, _, bucket = layers[held]
            if winner is None or rank < winner[0] or (rank == winner[0]
                                                      and order > winner[1]):
                winner = (rank, order, bucket)
        if winner is not None:
            spans.setdefault(winner[2], []).append((start, end))
    return spans


_DIMENSIONS = ("human", "inferred_human", "manual", "agent", "inferred_agent", "blocked")
"""The keys of the pieces that the figures of a bucket and of a project read."""


def _extend(
    held: dict[Bucket, dict[str, list[Piece]]],
    bucket: Bucket,
    key: str,
    pieces: list[Piece],
) -> None:
    """Add the pieces of one dimension to the bucket, as a key that the figures read;
    a bucket whose pieces are all empty enters no row of the figures."""
    if not pieces:
        return
    dimensions = held.setdefault(bucket, {name: [] for name in _DIMENSIONS})
    dimensions[key].extend(pieces)


def _count(
    held: dict[tuple[str, str], dict[Bucket, list[int]]],
    session: tuple[str, str],
    bucket: Bucket,
    length: int,
    position: int,
) -> None:
    """Add the milliseconds to the human or the agent time of the bucket of a session:
    the human time at position 0, the agent time at position 1."""
    if length:
        times = held.setdefault(session, {}).setdefault(bucket, [0, 0])
        times[position] += length


def _share(inferred: int, whole: int) -> float:
    """The share of the whole that the part of an inferred repository identity holds,
    0.0 for a whole that holds no time (metrics.md › Attribution, ADR 0018)."""
    return inferred / whole if whole else 0.0
