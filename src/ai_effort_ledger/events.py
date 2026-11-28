"""The event schema: the kinds and fields, the instant and version texts, the line encoding, and
the keys, the key order, the merge of two copies of one key, and the events that a command writes.

The constants and the encoding follow `event-schema.md` › Kinds, › Fields, › Encoding. A line
decodes to an event of this schema version, is left out when it is of a newer schema version and
holds a kind or a value that this schema does not know, or is broken when it is not a valid event
of any schema version (ADR 0023). The keys of the open sets — token categories, request types, and
price factors — pass through as they are.
"""

import importlib.metadata
import json
import re
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, NamedTuple

SCHEMA_VERSION = 1
"""The schema version that this ledger writes."""

Event = dict[str, Any]
"""An event in memory: a JSON-shaped object of the field names and their values."""

KINDS: frozenset[str] = frozenset({
    "session_start", "session_end", "prompt", "queued_message", "interruption", "notification",
    "agent_output", "tool_call", "tool_result", "decision_request", "decision", "manual_entry",
    "timesheet_confirmation", "declared_usage", "annotation", "retraction", "purge",
})
"""Every kind of event of the schema."""

FIELDS: frozenset[str] = frozenset({
    "schema_version", "source", "source_format", "native_id", "session_id", "event_uid",
    "timestamp", "ingested_at", "writer_version", "actor", "kind", "invocation",
    "parent_session_id", "agent_id", "parent_agent_id", "subagent_mode", "call_id", "tool_name",
    "tool_category", "lines_added", "lines_removed", "file_ext", "size_basis", "decision_type",
    "input_origin", "forked_from", "machine", "tool", "provider_hint", "model", "tokens",
    "requests", "price_factors", "cwd", "repo_hint", "repo_basis", "branch", "start", "end",
    "day", "duration", "cost", "currency", "manual_mode", "project", "work_item", "note",
    "entries", "replaces", "annotates", "retracts", "purged_keys", "purge_reason",
    "purged_sessions", "corrected_version", "labels",
})
"""Every field of the schema."""

REQUIRED_FIELDS: frozenset[str] = frozenset({
    "schema_version", "source", "event_uid", "timestamp", "ingested_at", "writer_version",
    "actor", "kind", "machine",
})
"""The fields that an event of every schema version holds."""

FIXED_VALUES: dict[str, frozenset[str]] = {
    "kind": KINDS,
    "actor": frozenset({"human", "agent", "system"}),
    "invocation": frozenset(
        {"interactive", "headless", "scheduled", "orchestrated", "unknown"}),
    "subagent_mode": frozenset({"foreground", "background"}),
    "tool_category": frozenset(
        {"edit", "execute", "read", "search", "web", "delegate", "decide", "other"}),
    "input_origin": frozenset(
        {"task_notification", "coordinator", "peer", "parent", "scheduled", "scripted"}),
    "decision_type": frozenset({"permission", "question", "plan_approval"}),
    "manual_mode": frozenset({"additional", "overlapping"}),
    "size_basis": frozenset({"patch", "input"}),
    "repo_basis": frozenset({"observed", "inferred"}),
    "purge_reason": frozenset({"content", "correction", "forget"}),
}
"""The fields with a fixed set of values, and the values that this schema version knows."""

VERSION_TEXT = re.compile(r"[0-9]+(?:\.[0-9]+)*(?:\.dev[0-9]+)?")
"""A writer version: whole numbers separated by dots, with an optional development mark."""

INSTANT_TEXT = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])"
    r"T(?:[01][0-9]|2[0-3]):[0-5][0-9]:[0-5][0-9]\.[0-9]{3}Z")
"""An instant of the schema: RFC 3339 in UTC, with `Z` and milliseconds
(`event-schema.md` › Encoding)."""

DAY_TEXT = re.compile(
    r"[0-9]{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12][0-9]|3[01])")
"""A local day of the schema: a date `YYYY-MM-DD` (`event-schema.md` › Encoding)."""

DECIMAL_TEXT = re.compile(r"[0-9]+(?:\.[0-9]+)?")
"""A decimal of the schema, as the text that `cost` holds (`event-schema.md` › Encoding)."""

CURRENCY_TEXT = re.compile(r"[A-Z]{3}")
"""An ISO 4217 currency code, as the text that `currency` holds
(`event-schema.md` › Encoding)."""


def _whole_number(value: Any) -> bool:
    """Whether the value is a whole number; `True` of JSON is not one of them."""
    return isinstance(value, int) and not isinstance(value, bool)


def _is_instant(value: Any) -> bool:
    """Whether the value is the text of an instant of the schema."""
    return isinstance(value, str) and INSTANT_TEXT.fullmatch(value) is not None


def _is_version(value: Any) -> bool:
    """Whether the value is the text of a writer version."""
    return isinstance(value, str) and VERSION_TEXT.fullmatch(value) is not None


def _tokens_of(value: Any) -> bool:
    """Whether the value is an object of token category and whole number."""
    return isinstance(value, dict) and all(_whole_number(one) for one in value.values())


def _requests_of(value: Any) -> bool:
    """Whether the value is an object of request type and whole number above zero."""
    return isinstance(value, dict) and all(
        _whole_number(one) and one > 0 for one in value.values())


def _texts_of(value: Any) -> bool:
    """Whether the value is an object whose every value is text: the price factors and the
    labels of the schema (`event-schema.md` › Encoding)."""
    return isinstance(value, dict) and all(isinstance(one, str) for one in value.values())


def _forked_from_of(value: Any) -> bool:
    """Whether the value is the object of a forked session: the session it was copied
    from, and the instant of the fork (`event-schema.md` › Encoding)."""
    return (isinstance(value, dict)
            and isinstance(value.get("session_id"), str)
            and _is_instant(value.get("instant")))


def _event_key_of(value: Any) -> bool:
    """Whether the value is one event key as the schema stores it: `source` with its
    native identifier or its event identifier, every part text
    (`event-schema.md` › Encoding)."""
    if not isinstance(value, dict) or not isinstance(value.get("source"), str):
        return False
    parts = [held for name, held in value.items() if name != "source"]
    return (bool(parts)
            and all(isinstance(one, str) for one in parts)
            and ("native_id" in value or "event_uid" in value))


def _event_keys_of(value: Any) -> bool:
    """Whether the value is an array of event keys."""
    return isinstance(value, list) and all(_event_key_of(one) for one in value)


def _entries_of(value: Any) -> bool:
    """Whether the value is an array of the objects of a timesheet, the `duration` of each
    in whole seconds when it holds one (`event-schema.md` › Encoding)."""
    return isinstance(value, list) and all(
        isinstance(one, dict) and ("duration" not in one or _whole_number(one["duration"]))
        for one in value)


def _sessions_of(value: Any) -> bool:
    """Whether the value is an array of the objects of sessions."""
    return isinstance(value, list) and all(isinstance(one, dict) for one in value)


ENCODINGS: dict[str, Callable[[Any], bool]] = {
    "timestamp": _is_instant,
    "ingested_at": _is_instant,
    "start": _is_instant,
    "end": _is_instant,
    "day": lambda value: isinstance(value, str) and DAY_TEXT.fullmatch(value) is not None,
    "duration": _whole_number,
    "tokens": _tokens_of,
    "requests": _requests_of,
    "price_factors": _texts_of,
    "cost": lambda value: (isinstance(value, str)
                           and DECIMAL_TEXT.fullmatch(value) is not None),
    "currency": lambda value: (isinstance(value, str)
                               and CURRENCY_TEXT.fullmatch(value) is not None),
    "forked_from": _forked_from_of,
    "retracts": _event_key_of,
    "replaces": _event_key_of,
    "purged_keys": _event_keys_of,
    "entries": _entries_of,
    "purged_sessions": _sessions_of,
    "annotates": lambda value: isinstance(value, dict),
    "machine": lambda value: isinstance(value, str),
    "repo_hint": lambda value: isinstance(value, str),
    "writer_version": _is_version,
    "corrected_version": _is_version,
    "labels": _texts_of,
}
"""The check of the value of each field whose encoding the table of the schema owns
(`event-schema.md` › Encoding). A line whose field fails its check is broken, whatever its
schema version, because a new schema version never changes the encoding of a field."""


def format_instant(instant: datetime) -> str:
    """Write an instant as the schema stores it: RFC 3339 in UTC, with `Z` and milliseconds."""
    if instant.tzinfo is None:
        raise ValueError(f"the instant {instant!r} is naive: it needs a time zone")
    moment = instant.astimezone(timezone.utc)
    return f"{moment:%Y-%m-%dT%H:%M:%S}.{moment.microsecond // 1000:03d}Z"


@lru_cache(maxsize=None)
def parse_instant(text: str) -> datetime:
    """Read an instant with an offset or `Z`; the result is aware UTC, to the millisecond.

    The parse of a text is remembered: a report reads the instant of one event many
    times, and one text always gives the same instant."""
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"the instant {text!r} has no offset and no Z")
    microsecond = moment.microsecond - moment.microsecond % 1000
    return moment.astimezone(timezone.utc).replace(microsecond=microsecond)


def version_key(text: str) -> tuple:
    """Read a writer version as its order key: number by number, with a development mark first.

    `1.10.0` is newer than `1.9.0`, and `1.3.0.dev0` is older than `1.3.0` and than `1.3.0.dev1`,
    as the version order of PEP 440 gives it. Text that is not whole numbers separated by dots,
    with an optional `.dev` mark and a whole number, raises `ValueError`.
    """
    if not VERSION_TEXT.fullmatch(text):
        raise ValueError(f"not a writer version: {text!r}")
    release, _, development = text.partition(".dev")
    numbers = [int(part) for part in release.split(".")]
    while len(numbers) > 1 and numbers[-1] == 0:
        numbers.pop()
    mark = (-1, int(development)) if development else (1,)
    return (*numbers, *mark)


def writer_version() -> str:
    """The version of the ledger program that writes: the version of this package (ADR 0015)."""
    return importlib.metadata.version("ai-effort-ledger")


def _reject_none(value: Any, where: str) -> None:
    """Refuse a `None` value at any depth of an event: an absent field is not written."""
    if value is None:
        raise ValueError(f"{where} is None: an absent field is not written, never written as null")
    if isinstance(value, dict):
        for key, entry in value.items():
            _reject_none(entry, f"{where}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, entry in enumerate(value):
            _reject_none(entry, f"{where}[{index}]")


def encode_event(event: Event) -> bytes:
    """Write one event as one line: JSON with sorted members, no white space, UTF-8, and a break.

    One event always gives the same bytes (`event-schema.md` › Encoding): the members are sorted
    by name in the order of Unicode code points, a letter outside ASCII is written as UTF-8 and
    never as a `\\u` escape, and the line ends with one line break.
    """
    for key, value in event.items():
        _reject_none(value, key)
    line = json.dumps(event, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return line.encode("utf-8") + b"\n"


class Decoded(NamedTuple):
    """The reading of one line: its state, the event when there is one, and whether it is newer.

    The state is `"event"` for an event this schema reads, `"left_out"` for an event of a newer
    schema version that holds a kind or a value this schema does not know, and `"broken"` for a
    line that is not a valid event of any schema version.
    """

    state: str
    event: Event | None
    newer: bool


def decode_line(data: bytes) -> Decoded:
    """Read one line of a segment as the schema gives the reading (`event-schema.md` › Encoding).

    A line that is not a JSON object, that misses a required field, or that at this schema version
    holds an unknown kind or an unknown value of a field with a fixed set of values is broken. So
    is a line whose field the table of the encoding gives in another shape — a version that is not
    a text of whole numbers separated by dots, an instant that is not an RFC 3339 text with `Z`
    and milliseconds, a count that is not a whole number — because a new schema version never
    changes the encoding of a field, so no schema version reads such a line. An event of a newer
    schema version keeps the fields this schema knows and drops the others; an unknown kind or
    fixed value leaves it out, and the line marks itself newer (ADR 0023).
    """
    try:
        parsed = json.loads(data)
    except ValueError:
        return Decoded("broken", None, False)
    if not isinstance(parsed, dict):
        return Decoded("broken", None, False)
    version = parsed.get("schema_version")
    whole = isinstance(version, int) and not isinstance(version, bool)
    if not whole or version < 1:
        return Decoded("broken", None, False)
    newer = version > SCHEMA_VERSION
    if not REQUIRED_FIELDS <= parsed.keys():
        return Decoded("broken", None, False)
    state = "event"
    for field, values in FIXED_VALUES.items():
        if field not in parsed:
            continue
        value = parsed[field]
        if not isinstance(value, str) or value not in values:
            state = "left_out" if newer else "broken"
    if state != "event":
        return Decoded(state, None, newer)
    for field, check in ENCODINGS.items():
        if field in parsed and not check(parsed[field]):
            return Decoded("broken", None, newer)
    known = {key: value for key, value in parsed.items() if key in FIELDS}
    return Decoded(state, known, newer)


@dataclass(frozen=True)
class EventKey:
    """The identity of an event: its source with its native identifier, or, when the source gives
    none, with its session and its event identifier (`event-schema.md` › Keys and invariants).

    A part that the event does not hold stays `None`; an event that a command writes has the source
    `ledger` and no session.
    """

    source: str
    native_id: str | None = None
    session_id: str | None = None
    event_uid: str | None = None

    def to_json(self) -> dict[str, str]:
        """Write the key as the schema stores it in `retracts`, `replaces`, and `purged_keys`."""
        parts = {
            "source": self.source,
            "native_id": self.native_id,
            "session_id": self.session_id,
            "event_uid": self.event_uid,
        }
        return {name: value for name, value in parts.items() if value is not None}

    @classmethod
    def from_json(cls, value: Mapping[str, str]) -> "EventKey":
        """Read a key that `to_json` wrote; the parts the value does not name stay `None`."""
        return cls(
            source=value["source"],
            native_id=value.get("native_id"),
            session_id=value.get("session_id"),
            event_uid=value.get("event_uid"),
        )


def random_uid() -> str:
    """A random identifier (version 4) as text, for an event that a command writes."""
    return str(uuid.uuid4())


def event_key(event: Event) -> EventKey:
    """The key of an event: (`source`, `native_id`) when the source gives a native identifier,
    else (`source`, `session_id`, `event_uid`); the key of an event that a command writes is
    (`ledger`, `event_uid`) (`event-schema.md` › Keys and invariants). A session identifier
    that the event does not hold stays absent in its key, as the key order reads an absent
    part.
    """
    source = event["source"]
    native_id = event.get("native_id")
    if native_id is not None:
        return EventKey(source, native_id=native_id)
    if source == "ledger":
        return EventKey(source, event_uid=event["event_uid"])
    return EventKey(
        source, session_id=event.get("session_id"), event_uid=event["event_uid"])


def _order_part(text: str | None) -> tuple:
    """One part of an event for the key order: an absent part comes before every text."""
    return (0,) if text is None else (1, text)


def event_order(event: Event) -> tuple:
    """The order of an event, which tie-breaks use: by source, then session, then event
    identifier, each compared as text (`event-schema.md` › Keys and invariants).
    """
    return (
        (1, event["source"]),
        _order_part(event.get("session_id")),
        _order_part(event.get("event_uid")),
    )


def winning_copy(a: tuple[Event, str], b: tuple[Event, str]) -> tuple[Event, str]:
    """The copy of one event key that the merge keeps: the earliest `ingested_at`, and, at equal
    instants, the copy in the segment whose name sorts first as text, so segments of several
    machines merge to the same result in any order (`event-schema.md` › Keys and invariants).
    """
    left, right = parse_instant(a[0]["ingested_at"]), parse_instant(b[0]["ingested_at"])
    if left != right:
        return a if left < right else b
    return a if a[1] <= b[1] else b


def ledger_event(
    kind: str,
    actor: str,
    machine: str,
    timestamp: datetime,
    fields: Mapping[str, Any],
    new_uid: Callable[[], str] = random_uid,
    version: str | None = None,
) -> Event:
    """An event that a command writes: the source `ledger`, a new random event identifier, and no
    `ingested_at` — the store sets it when it writes the event into a segment (`event-schema.md`
    › Keys and invariants).

    The `timestamp` is the instant at which the command writes the event; `fields` holds the fields
    of the kind, such as the entries of a timesheet confirmation or the key of a retraction.
    """
    event: Event = {
        "schema_version": SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": new_uid(),
        "timestamp": format_instant(timestamp),
        "writer_version": writer_version() if version is None else version,
        "actor": actor,
        "kind": kind,
        "machine": machine,
    }
    event.update(fields)
    return event
