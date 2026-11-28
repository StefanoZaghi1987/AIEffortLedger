"""The forked sessions of a reading: the events that two sessions hold as copies of one
record are one event, and they belong to the original of the pair, while the events that
stay in a forked session name the session that its history was copied from and the instant
of the fork (claude-code-adapter.md › Forks; event-schema.md › Keys and invariants; ADR
0023)."""

from collections.abc import Callable

from ...events import Event

IdOwner = Callable[[str, str], tuple[str, str] | None]
"""The lookup that names the session that holds a native identifier already in the store: it
takes the identifier of the session that the reading reads and the native identifier of an
event, and names the session of the store that holds the identifier."""

Pair = tuple[tuple[str, str], tuple[str, str]]
"""The two sessions that hold copies of one event, each as the agent tool and the session
identifier that the reading names."""


def assign_forks(
    sessions: dict[tuple[str, str], list[Event]], native_id_owner: IdOwner
) -> list[dict]:
    """Give the events that two sessions of the reading share to the original of their pair,
    and write `forked_from` on the events that stay in the forked session: the original is
    the session that holds an event of its own, without a copy in the other session, inside
    the time range of the shared events; when both sessions or neither hold one, the session
    whose identifier sorts first is the original and one `fork_original_unknown` warning
    names the pair. The instant of the fork is the timestamp of the last shared event. The
    copy of the fork leaves when the original holds its own copy of the same event, so one
    event key stays once in the reading; when the original holds no copy, the copy of the
    fork moves to it and takes the identifier of the original as its session. An event that
    stays in the fork names the original and the instant of the fork from its timestamp on;
    an event of an earlier timestamp names nothing. The events of a session whose native
    identifiers the store already holds under another session leave the session, because
    that copy is the same event and keeps its session (ADR 0023), and the events that stay
    name the session of the store from the instant of the fork on."""
    warnings: list[dict] = []
    for pair, shared in _pairs_of(sessions).items():
        original, fork, known = _original_of(pair, sessions, shared)
        if not known:
            warnings.append({"code": "fork_original_unknown", "values": {}})
        instant = max(event["timestamp"] for event in shared.values())
        kept: list[Event] = []
        moved: list[Event] = []
        for event in sessions[fork]:
            uid = _uid_of(event)
            if uid is None or uid not in shared:
                kept.append(event)
            elif _holds_uid(sessions[original], uid):
                continue
            else:
                event["session_id"] = original[1]
                moved.append(event)
        sessions[fork][:] = kept
        sessions[original].extend(moved)
        for event in kept:
            if event["timestamp"] >= instant:
                event["forked_from"] = {"session_id": original[1], "instant": instant}
    for key, events in sessions.items():
        _drop_stored_copies(key, events, native_id_owner)
    return warnings


def _pairs_of(
    sessions: dict[tuple[str, str], list[Event]],
) -> dict[Pair, dict[str, Event]]:
    """The events that two sessions of the reading hold as copies of one event, by the pair
    that holds them: the copies of one event are the events that share a native identifier
    of the same agent tool, and one of the copies stands for the event, because copies of
    one record give it the same timestamp; an event that no native identifier names pairs
    with nothing (claude-code-adapter.md › Forks)."""
    copies: dict[tuple[str, str], list[tuple[tuple[str, str], Event]]] = {}
    for key, events in sessions.items():
        for event in events:
            uid = _uid_of(event)
            if uid is not None:
                copies.setdefault((key[0], uid), []).append((key, event))
    pairs: dict[Pair, dict[str, Event]] = {}
    for (tool, uid), held in copies.items():
        keys: list[tuple[str, str]] = []
        for key, _ in held:
            if key not in keys:
                keys.append(key)
        for index, first in enumerate(keys):
            for second in keys[index + 1:]:
                pair = (first, second) if first < second else (second, first)
                pairs.setdefault(pair, {})[uid] = held[0][1]
    return pairs


def _original_of(
    pair: Pair,
    sessions: dict[tuple[str, str], list[Event]],
    shared: dict[str, Event],
) -> tuple[tuple[str, str], tuple[str, str], bool]:
    """The original of a pair of sessions that share events, the session of the pair that is
    the fork, and whether the events of the pair could decide it: the original is the session
    that holds an event of its own inside the time range of the shared events, and, when both
    sessions or neither hold one, the session whose identifier sorts first
    (event-schema.md › Keys and invariants)."""
    first, second = pair
    instants = [event["timestamp"] for event in shared.values()]
    start, end = min(instants), max(instants)
    first_holds = _holds_own_in_range(sessions[first], shared, start, end)
    second_holds = _holds_own_in_range(sessions[second], shared, start, end)
    if first_holds != second_holds:
        original, fork = (first, second) if first_holds else (second, first)
        return original, fork, True
    original = min(first, second, key=lambda key: key[1])
    fork = second if original == first else first
    return original, fork, False


def _holds_own_in_range(
    events: list[Event], shared: dict[str, Event], start: str, end: str
) -> bool:
    """Whether the events of one session hold an event of its own, without a copy in the
    other session of the pair, whose timestamp is inside the time range of the shared
    events."""
    return any(
        _uid_of(event) not in shared and start <= event["timestamp"] <= end
        for event in events)


def _holds_uid(events: list[Event], uid: str) -> bool:
    """Whether the events of one session hold an event of one `event_uid` already."""
    return any(_uid_of(event) == uid for event in events)


def _drop_stored_copies(key: tuple[str, str], events: list[Event], owner_of: IdOwner) -> None:
    """Drop the events of one session whose native identifier the store already holds under
    another session, and write `forked_from` on the events that stay: the copy that the
    store holds is the same event and keeps its session (ADR 0023), so the forked session
    keeps only the events of its own, and the instant of the fork is the timestamp of the
    last event that another session of the store holds. An event that stays names the
    session of the store from that instant on; an event of an earlier timestamp names
    nothing."""
    kept: list[Event] = []
    claimed: dict[tuple[str, str], list[Event]] = {}
    for event in events:
        owner = _stored_owner(key, event, owner_of)
        if owner is None:
            kept.append(event)
        else:
            claimed.setdefault(owner, []).append(event)
    events[:] = kept
    for owner, copies in claimed.items():
        instant = max(event["timestamp"] for event in copies)
        for event in kept:
            if event["timestamp"] >= instant:
                event["forked_from"] = {"session_id": owner[1], "instant": instant}


def _stored_owner(
    key: tuple[str, str], event: Event, owner_of: IdOwner
) -> tuple[str, str] | None:
    """The session of the store that holds the native identifier of one event, when it is
    another session than the one read; an event without a native identifier is in the index
    of no other session."""
    native = event.get("native_id")
    if not (isinstance(native, str) and native):
        return None
    owner = owner_of(key[1], native)
    return owner if owner is not None and owner != key else None


def _uid_of(event: Event) -> str | None:
    """The name that two copies of one event share: the native identifier of the event when
    it is a non-empty string, else None — a fork copy is a copy of one record, and copies
    share their native identifier, so an event that no native identifier names is the event
    of its own session alone (claude-code-adapter.md › Forks)."""
    uid = event.get("native_id")
    return uid if isinstance(uid, str) and uid else None
