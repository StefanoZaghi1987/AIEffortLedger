"""The buckets of the events: the identity that an event takes from the previous event
of its session, the project that the identity rules give it, and the overrides of the
annotations of a session or of an interval (metrics.md › Attribution, ADR 0019).

A bucket is the project identifier and the work item identifier of an event; `(None,
None)` is the unattributed time. An event without its own folder, branch, or repository
identity takes those of the previous event of its session; events with the same
timestamp take them in the order of their event keys. The annotations override the
derived attribution in the order of their timestamp, equal instants by event key: a work
item of an annotation applies only to an event that has a project, and the project of an
annotation also removes the work item of the earlier annotations. The list that the
buckets come with holds the warnings and the configuration errors as values, each with
its code and the values that it names; `reports` adds the texts.
"""

from collections.abc import Sequence

from ..configuration import PersonConfiguration
from ..days import LocalDays
from ..events import Event, EventKey, event_key, event_order, parse_instant
from .names import declared_project_unknown
from .rules import project_of

Bucket = tuple[str | None, str | None]
"""The project identifier and the work item identifier of an event; `(None, None)` is
the unattributed time (metrics.md › Attribution)."""


def event_buckets(
    session_events: Sequence[Event],
    annotations: Sequence[Event],
    person: PersonConfiguration,
    days: LocalDays,
) -> tuple[dict[EventKey, Bucket], list[dict]]:
    """The bucket of each event of the sessions, and the warnings and configuration
    errors (metrics.md › Attribution).

    The identity rules resolve the project of each event from the repository identity,
    the folder, and the branch that it holds or takes from the previous event of its
    session, on its local day. The annotations apply in the order of their timestamp,
    equal instants by event key. Two identity rules of which neither is more specific
    give one `identity_rule_conflict` error that one event of theirs completes; a work
    item that an annotation gives to an event without a project warns
    `work_item_without_project`; and the project of an annotation that no identity rule,
    no entry of the person configuration, and no repository identity of the events gives
    warns `declared_project_unknown`.
    """
    buckets, notices, _ = _event_buckets(session_events, annotations, person, days)
    return buckets, notices


def _event_buckets(
    session_events: Sequence[Event],
    annotations: Sequence[Event],
    person: PersonConfiguration,
    days: LocalDays,
) -> tuple[dict[EventKey, Bucket], list[dict], frozenset[EventKey]]:
    """The buckets and the notices of `event_buckets`, with the event keys of the events
    whose repository identity, their own or the one they take from the previous event of
    their session, rests on an inferred basis (metrics.md › Attribution, ADR 0018), for
    `attribute`, which counts their shares."""
    ordered = sorted(session_events,
                     key=lambda event: (event["timestamp"], event_order(event)))
    carried = _carried(ordered)
    buckets: dict[EventKey, Bucket] = {}
    notices: list[dict] = []
    conflicts: dict[tuple[str, str], dict] = {}
    inferred: set[EventKey] = set()
    for event, identity in zip(ordered, carried):
        repository, folder, branch, basis = identity
        if basis == "inferred":
            inferred.add(event_key(event))
        day = days.local_day(parse_instant(event["timestamp"]))
        project, error = project_of(repository, folder, branch, day, person.identity_rules)
        buckets[event_key(event)] = (project, None)
        if error is None:
            continue
        pair = (error["values"]["first"], error["values"]["second"])
        if pair not in conflicts:
            error["values"]["event"] = event_key(event).to_json()
            conflicts[pair] = error
    notices.extend(conflicts.values())
    _apply_annotations(buckets, ordered, annotations, notices)
    hints = {identity[0] for identity in carried if identity[0] is not None}
    notices.extend(declared_project_unknown(
        (note["project"] for note in annotations if note.get("project") is not None),
        person, hints))
    return buckets, notices, frozenset(inferred)


def _apply_annotations(
    buckets: dict[EventKey, Bucket],
    ordered: Sequence[Event],
    annotations: Sequence[Event],
    notices: list[dict],
) -> None:
    """Override the buckets with the annotations, in the order of their timestamp, equal
    instants by event key (metrics.md › Attribution).

    A work item that an annotation gives to an event without a project does not apply:
    the event stays unattributed, and one warning per annotation names the annotation,
    by its `event_uid`, and its work item.
    """
    warned: set[EventKey] = set()
    for note in sorted(annotations,
                       key=lambda event: (event["timestamp"], event_order(event))):
        covered = _covered(note, ordered)
        for event in covered:
            key = event_key(event)
            project, work_item = buckets[key]
            given = note.get("project")
            if given is not None:
                project, work_item = given, None
            item = note.get("work_item")
            if item is not None:
                if project is None:
                    if event_key(note) not in warned:
                        warned.add(event_key(note))
                        notices.append({"code": "work_item_without_project",
                                        "values": {"work_item": item,
                                                   "event_uid": note["event_uid"]}})
                    continue
                work_item = item
            buckets[key] = (project, work_item)


def _covered(note: Event, ordered: Sequence[Event]) -> list[Event]:
    """The events that the annotation applies to: the events of the session that it
    names, or the events whose timestamp its interval contains, with the start included
    and the end excluded (metrics.md › Attribution)."""
    named = note.get("annotates")
    if named is not None:
        return [event for event in ordered
                if event.get("tool") == named.get("tool")
                and event.get("session_id") == named.get("session_id")]
    start = parse_instant(note["start"])
    end = parse_instant(note["end"])
    return [event for event in ordered
            if start <= parse_instant(event["timestamp"]) < end]


_Carried = tuple[str | None, str | None, str | None, str | None]
"""The repository identity, the folder, the branch, and the basis of the repository
identity that an event holds or takes from the previous event of its session."""


def _carried(ordered: Sequence[Event]) -> list[_Carried]:
    """The repository identity, the folder, and the branch of each event, each its own
    value or the value of the previous event of its session, and the basis of the
    repository identity, which goes with it (metrics.md › Attribution, ADR 0018)."""
    previous: dict[tuple[str | None, str | None], _Carried] = {}
    carried: list[_Carried] = []
    for event in ordered:
        session = (event.get("tool"), event.get("session_id"))
        before = previous.get(session, (None, None, None, None))
        hint = event.get("repo_hint")
        identity = (
            _own(hint, before[0]),
            _own(event.get("cwd"), before[1]),
            _own(event.get("branch"), before[2]),
            event.get("repo_basis") if hint is not None else before[3],
        )
        carried.append(identity)
        previous[session] = identity
    return carried


def _own(value: str | None, before: str | None) -> str | None:
    """The value that the event holds, or the one it takes from the previous event."""
    return value if value is not None else before
