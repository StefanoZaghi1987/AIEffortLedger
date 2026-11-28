"""What the readers of the frozen reports may meet in a file (command-line.md › Frozen
reports, › JSON documents): a file of a frozen report that the ledger cannot read as one
stops the reader with `frozen_report_unreadable`, which names the file, and no consumer of
a frozen report ends in a traceback on the content of a file.

Every document comes from a real command: the fixture stores of `support` hold invented
events, and `report timesheet --freeze` and `report day --freeze` write the frozen reports;
no document built by hand serves as the model of a frozen report. A changed envelope is
written as the file of its frozen report through the writer of the store, in a store folder
of the test, and read back through the reader; the property test, which changes thousands of
envelopes, writes the file once and serves its changed text from memory to the same two
readers. Four things are proved:

- the named damages, the shapes that a reader trips on, are each refused, the file named,
  and, through the real commands, each damage of `_DAMAGED_FILES` stops every reader of the
  frozen reports;
- the proposed value of an entry and the context of a day, which no report command writes
  and which the text shows when a frozen document holds them, are read in their kinds;
- the property: every leaf of every real envelope — the containers too — is taken away,
  replaced by a value of each other kind of JSON or, for a number, by NaN, and, for a key of
  an object, given an invented name; each key that a consumer reads when it is held is
  added where the document does not hold it, and each empty list gains one element; for
  every envelope so changed the reader stops or every consumer completes: the rows of
  `frozen list`, the latest frozen report of each day, the days of the document, its
  differences against the real report of now of the same command, and the text and the
  JSON of the documents that hold a frozen report, in both languages;
- the completeness: each key that the two report commands always write, taken away from a
  real document, makes the reader stop.
"""

import contextlib
import json
import math
import unittest
from collections.abc import Callable, Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, NamedTuple, NoReturn
from unittest import mock

import support
from ai_effort_ledger import reports, store
from ai_effort_ledger.language import label
from ai_effort_ledger.store import FrozenReportUnreadable

_Step = str | int
"""One step of a path into a JSON value: a key of an object, or the position of an element
of a list."""

_ENVELOPE = tuple[str, str, dict]
"""What the reader of the reports gives for one file: the machine, the identifier, and the
envelope."""

_REMOVED = object()
"""The change that takes a node away."""

_INVENTED_KEY = "an invented key"
"""The name that a renamed key takes, which no document holds."""

_REALS = (
    ("the timesheet of the frozen period", "frozen_period", "report timesheet",
     "Sent to the office"),
    ("the timesheet of the declared day", "declared_day", "report timesheet", None),
    ("the day of the annotations", "annotations", "report day", None),
    ("the day of the declared day", "declared_day", "report day", None),
)
"""The real frozen reports of the file, each as the name of its scenario, the fixture store
that the command freezes on, the command, and the note of the freeze when it has one: a
timesheet with a note over the two measured days of the frozen period, a timesheet of a
declared day, a day with two projects and two work items, and a day of a declared day."""

_OTHER_VALUES = {"null": None, "a boolean": True, "a number": 2.5,
                 "a text": "an invented text", "a list": [], "an object": {}}
"""A value of each kind of JSON; the number is not whole, so that a duration meets a number
of another kind too."""

_RECORD_PATHS = (("parameters",), ("identity_rules",), ("category_rules",), ("dated_facts",),
                 ("dated_facts", "time_zones"), ("dated_facts", "day_starts"))
"""The keys of the record that every report command writes, relative to the record."""

_MEASURE_PATHS = tuple((name,) for name in ("human_time", "agent_time", "blocked_time",
                                            "activity_classes"))
"""The keys of the measures, relative to the person, to a project, or to a work item."""

_ALWAYS_WRITTEN = {
    "report timesheet": (
        ("document", "days"),
        ("document", "days", "day"),
        ("document", "days", "state"),
        ("document", "days", "total"),
        ("document", "days", "measured_total"),
        ("document", "days", "unknown_invocation_share"),
        ("document", "days", "entries"),
        ("document", "days", "entries", "project"),
        ("document", "days", "entries", "work_item"),
        ("document", "days", "entries", "measured"),
        ("document", "days", "entries", "with_manual_entries"),
        ("document", "days", "entries", "declared"),
        ("document", "days", "entries", "inferred_human_share"),
        ("document", "days", "entries", "inferred_agent_share"),
        *(("document", "record", *path) for path in _RECORD_PATHS),
    ),
    "report day": (
        ("document", "day"),
        ("document", "state"),
        ("document", "unknown_invocation_share"),
        ("document", "person"),
        *(("document", "person", *path) for path in _MEASURE_PATHS),
        ("document", "projects"),
        ("document", "projects", "project"),
        *(("document", "projects", *path) for path in _MEASURE_PATHS),
        ("document", "projects", "inferred_human_share"),
        ("document", "projects", "inferred_agent_share"),
        ("document", "work_items"),
        ("document", "work_items", "work_item"),
        *(("document", "work_items", *path) for path in _MEASURE_PATHS),
        ("document", "work_items", "inferred_human_share"),
        ("document", "work_items", "inferred_agent_share"),
        *(("document", "record", *path) for path in _RECORD_PATHS),
    ),
}
"""The keys that each report command always writes (command-line.md › JSON documents), as
paths into the envelope of its frozen report: a key that follows a list names every object
of the list. The human time at the idle gaps is absent, because a declared day holds
none."""


def _adding(key: str, value: Any) -> Callable[[dict], dict]:
    """The change that gives an object one more key, with the value."""
    return lambda held: {**held, key: value}


_PERIOD = "the timesheet of the frozen period"
_DAY = "the day of the annotations"
_DAY_TEXT = support.FIXTURE_DAY_ONE.isoformat()
_OTHER_ID = "10000000-0000-4000-8000-000000000099"
"""An identifier that names no file of the tests."""

_DAMAGES = (
    # no day
    (_PERIOD, "no day: `days` empty", ("document", "days"), []),
    (_DAY, "no day: no `day`", ("document", "day"), _REMOVED),
    (_PERIOD, "`days` that is not a list", ("document", "days"), "abc"),
    (_PERIOD, "a day that is not an object", ("document", "days", 0), 2.5),
    (_PERIOD, "a day without `day`", ("document", "days", 0, "day"), _REMOVED),
    (_PERIOD, "a `day` that is no day text", ("document", "days", 0, "day"), "2026-11-99"),
    (_DAY, "a `day` that is no day text", ("document", "day"), "yesterday"),
    # a required key absent, one per group
    (_PERIOD, "no key of the document: `days`", ("document", "days"), _REMOVED),
    (_DAY, "no key of the document: `person`", ("document", "person"), _REMOVED),
    (_PERIOD, "no key of a day: `total`", ("document", "days", "total"), _REMOVED),
    (_DAY, "no key of the day: `state`", ("document", "state"), _REMOVED),
    (_PERIOD, "no key of an entry: `measured`", ("document", "days", "entries", "measured"),
     _REMOVED),
    (_DAY, "no key of the person: `activity_classes`",
     ("document", "person", "activity_classes"), _REMOVED),
    (_DAY, "no key of a project: `human_time`", ("document", "projects", "human_time"),
     _REMOVED),
    (_DAY, "no key of a work item: `inferred_agent_share`",
     ("document", "work_items", "inferred_agent_share"), _REMOVED),
    (_PERIOD, "no key of the record: `dated_facts`",
     ("document", "record", "dated_facts"), _REMOVED),
    (_DAY, "no key of the record: `parameters`", ("document", "record", "parameters"),
     _REMOVED),
    (_PERIOD, "no key of the dated facts: `day_starts`",
     ("document", "record", "dated_facts", "day_starts"), _REMOVED),
    # a figure in another kind
    (_PERIOD, "a duration in another kind", ("document", "days", "total"), "60"),
    (_DAY, "a duration that is not whole", ("document", "person", "human_time"), 2.5),
    (_DAY, "a duration that is null", ("document", "person", "human_time"), None),
    (_PERIOD, "a duration that is a boolean", ("document", "days", "total"), True),
    (_PERIOD, "a share in another kind", ("document", "days", "unknown_invocation_share"),
     "0"),
    (_DAY, "a share that is a boolean", ("document", "unknown_invocation_share"), True),
    (_PERIOD, "the gaps in another kind",
     ("document", "days", "human_time_at_idle_gaps"), 60),
    (_DAY, "a class in another kind",
     ("document", "person", "activity_classes", "person_only"), "60"),
    (_DAY, "the classes in another kind", ("document", "person", "activity_classes"), [60]),
    (_PERIOD, "an entry list in another kind", ("document", "days", "entries"), {}),
    (_PERIOD, "a project in another kind", ("document", "days", "entries", "project"),
     "alpha"),
    (_DAY, "a work item without a name", ("document", "work_items", "work_item"),
     {"id": "story-1"}),
    (_PERIOD, "the text of a gap that is no number",
     ("document", "days", "human_time_at_idle_gaps"), {"300": 60, _INVENTED_KEY: 60}),
    # a part of the record in another kind
    (_PERIOD, "a part of the record in another kind: the parameters",
     ("document", "record", "parameters"), []),
    (_PERIOD, "a part of the record in another kind: a parameter",
     ("document", "record", "parameters", "idle_gap"), "600"),
    (_PERIOD, "a part of the record in another kind: the identity rules",
     ("document", "record", "identity_rules"), {}),
    (_PERIOD, "a part of the record in another kind: the dated facts",
     ("document", "record", "dated_facts"), []),
    (_PERIOD, "a part of the record in another kind: the time zones",
     ("document", "record", "dated_facts", "time_zones"), {}),
    # a state that is no day state
    (_PERIOD, "a state that is no day state", ("document", "days", "state"), "closed"),
    (_DAY, "a state that is no day state", ("document", "state"), "closed"),
    # a key that no freeze writes
    (_PERIOD, "`differences` held", ("document",), _adding("differences", "abc")),
    (_DAY, "`differences` held, empty", ("document",), _adding("differences", [])),
    (_DAY, "`changed` held", ("document",), _adding("changed", 5)),
    (_PERIOD, "`changed` held, empty", ("document",), _adding("changed", [])),
    (_DAY, "`frozen` held", ("document",), _adding("frozen", "x")),
    (_PERIOD, "`frozen` held, an object", ("document",), _adding("frozen", {})),
    (_DAY, "a `report day` document that holds `days`", ("document",),
     _adding("days", [{"day": _DAY_TEXT}])),
    (_PERIOD, "a `report timesheet` document that holds `day`", ("document",),
     _adding("day", _DAY_TEXT)),
    # a key that a consumer reads when it is held, in another kind
    (_PERIOD, "an entry's `proposed` in another kind",
     ("document", "days", 0, "entries", 0), _adding("proposed", "x")),
    (_PERIOD, "an entry's `proposed` that is not whole",
     ("document", "days", 0, "entries", 0), _adding("proposed", 2.5)),
    (_PERIOD, "a day's `context` in another kind", ("document", "days", 0),
     _adding("context", "x")),
    (_PERIOD, "a day's `context` that is null", ("document", "days", 0),
     _adding("context", None)),
    (_PERIOD, "a day's `context` without its keys", ("document", "days", 0),
     _adding("context", {})),
    (_PERIOD, "a day's `context` without `presence_span`", ("document", "days", 0),
     _adding("context", {"agent_time": 60})),
    (_PERIOD, "a context's `agent_time` in another kind", ("document", "days", 0),
     _adding("context", {"agent_time": "60", "presence_span": None})),
    (_PERIOD, "a context's `presence_span` in another kind", ("document", "days", 0),
     _adding("context", {"agent_time": 60, "presence_span": "60"})),
    (_DAY, "the day's `context` in another kind", ("document",), _adding("context", [])),
    (_PERIOD, "a day's person in another kind", ("document", "days", 0),
     _adding("person", "x")),
    (_PERIOD, "a day's projects in another kind", ("document", "days", 0),
     _adding("projects", [3])),
    (_DAY, "the entries of the day in another kind", ("document",),
     _adding("entries", [{"project": "alpha"}])),
    (_DAY, "a total of the day in another kind", ("document",), _adding("total", "60")),
    # the parallel ratio in another kind
    (_DAY, "a parallel ratio that is a text", ("document", "person", "parallel_ratio"),
     "1.5"),
    (_DAY, "a parallel ratio that is a boolean",
     ("document", "person", "parallel_ratio"), False),
    (_DAY, "a parallel ratio that is null", ("document", "person", "parallel_ratio"),
     None),
    (_DAY, "a parallel ratio of a project in another kind",
     ("document", "projects", 0, "parallel_ratio"), "1.5"),
    (_DAY, "a parallel ratio of a work item in another kind",
     ("document", "work_items", 0, "parallel_ratio"), False),
    (_PERIOD, "a context's `parallel_ratio` in another kind", ("document", "days", 0),
     _adding("context", {"agent_time": 60, "parallel_ratio": "1.5",
                         "presence_span": None})),
    # the numbers and the envelope
    (_PERIOD, "a share that is NaN", ("document", "days", 0, "unknown_invocation_share"),
     math.nan),
    (_DAY, "a share that is infinite", ("document", "projects", 0, "inferred_human_share"),
     -math.inf),
    (_PERIOD, "a note that is no text", ("note",), {"text": "Sent to the office"}),
    (_DAY, "a note that is null", (), _adding("note", None)),
    (_PERIOD, "a `frozen_id` other than the identifier of the file name",
     ("document", "frozen_id"), _OTHER_ID),
)
"""The named damages: the scenario of the real frozen report, the damage, the path of the
node in its envelope, and the change — a value, a function that gives the changed node, or
`_REMOVED`."""

_ENTRY = {"project": None, "work_item": None, "measured": 60, "with_manual_entries": 60,
          "declared": None, "inferred_human_share": 0.0, "inferred_agent_share": 0.0}
"""An entry of the timesheet of a measured day for the unattributed time, as the command
writes one."""

_DAMAGED_FILES = (
    ("report timesheet", "an entry's `proposed` that is a text",
     ("document", "days", 0, "entries", 0), _adding("proposed", "x")),
    ("report timesheet", "a day's `context` that is a text", ("document", "days", 0),
     _adding("context", "x")),
    ("report timesheet", "a day's `context` that holds no key", ("document", "days", 0),
     _adding("context", {})),
    ("report day", "`differences` that is a text", ("document",),
     _adding("differences", "abc")),
    ("report day", "`changed` that is a number", ("document",), _adding("changed", 5)),
    ("report day", "`frozen` that is a text", ("document",), _adding("frozen", "x")),
    ("report day", "a `report day` document that holds `days`", ("document",),
     _adding("days", [{"day": _DAY_TEXT}])),
    ("report day", "a share that is NaN", ("document", "unknown_invocation_share"),
     math.nan),
    ("report timesheet", "a note that is no text", (), _adding("note", {"a": 1})),
    ("report day", "a `frozen_id` other than the identifier of the file name",
     ("document", "frozen_id"), _OTHER_ID),
)
"""The damaged files that the test of the readers writes on a real frozen report, each on
the report of one command: the keys that the text of `frozen show` alone reads when a
frozen document holds them — the proposed value of an entry, the context of a day, and the
keys that no freeze writes: `differences`, `changed`, `frozen`, and `days` in a `report
day` document —, a number that is not finite, a note that is no text, and a `frozen_id`
that names another file."""

_NESTING = 200_000
"""The depth of the lists that the test of the readers nests in a file: far beyond what the
parser of JSON reads."""

_ADDED_KEYS = {
    "the envelope": ("note",),
    "the document": ("frozen", "differences", "changed", "days", "day", "context",
                     "human_time_at_idle_gaps", "total", "measured_total", "person",
                     "entries", "projects", "work_items"),
    "a day": ("context", "human_time_at_idle_gaps", "total", "measured_total", "person",
              "entries", "projects", "work_items"),
    "the person": ("parallel_ratio",),
    "a project": ("parallel_ratio",),
    "a work item": ("parallel_ratio",),
    "an entry": ("proposed",),
}
"""The keys that a consumer reads by name when a part of a frozen report holds them — or
that no freeze writes —, which the property adds to each part that does not hold them: the
note of the envelope; the keys of the documents that hold frozen reports, the key of the
shape of the other command, and the keys of a day at the top of the document; the keys of a
day in each day of `days`; the parallel ratio of each holder of measures of a `report day`
document, which the real documents hold only where the holder has agent time; and the
proposed value of each entry."""

_ADDED_VALUES = {
    "context": ({}, {"agent_time": 60}, {"agent_time": "60", "presence_span": None},
                {"agent_time": 60, "presence_span": "60"},
                {"agent_time": 60, "parallel_ratio": "1.5", "presence_span": None},
                {"agent_time": 60, "parallel_ratio": 1.5, "presence_span": None},
                {"agent_time": 60, "presence_span": None},
                {"agent_time": 60, "presence_span": 60}),
    "proposed": (60,),
    "total": (60,),
    "measured_total": (60,),
    "human_time_at_idle_gaps": ({"300": 60},),
    "entries": ([_ENTRY],),
    "days": ([{"day": _DAY_TEXT}],),
    "day": (_DAY_TEXT,),
}
"""The values that a key of `_ADDED_KEYS` is added with beyond one of each kind of JSON:
the context of a day with its agent time, its presence span, and its parallel ratio, each
in a kind that the reader refuses and in a kind that it reads; the other keys of a day in
a kind that it reads; and the days and the day of the other command."""


class _Real(NamedTuple):
    """A frozen report that a real command wrote: the name of its scenario, the machine and
    the identifier of its file, its envelope as the file holds it, and the document of the
    report of now of the same command over the same days."""

    name: str
    machine: str
    frozen_id: str
    envelope: dict
    now: dict


def _real_documents(base: Path) -> dict[str, _Real]:
    """The real frozen reports, each frozen by its command over the period of its fixture
    store, in a home of its own below the base. The freeze runs an hour after the instant of
    the fixtures, so that, where the store holds a frozen report, the new one is the latest
    of its days; the report of now runs at the same instant."""
    reals: dict[str, _Real] = {}
    for name, fixture, action, note in _REALS:
        home = base / fixture / action.replace(" ", "-")
        context = support.fixture_store(fixture, home)
        first, last = support.FIXTURE_PERIODS[fixture]
        report = (["report", "timesheet", "--from", first.isoformat(), "--to",
                   last.isoformat()] if action == "report timesheet"
                  else ["report", "day", first.isoformat()])
        later = context._replace(now=support.FIXTURE_NOW + timedelta(hours=1))
        words = [*report, "--freeze", *(["--note", note] if note is not None else []),
                 "--json"]
        code, shown, error = support.run_main(later, *words)
        if code != 0:
            raise AssertionError(f"the freeze of {name} stopped: exit {code}, standard"
                                 f" error: {error}")
        frozen_id = json.loads(shown)["frozen_id"]
        folder = support.fixture_store_folder(home) / "frozen" / support.FIXTURE_MACHINE
        envelope = json.loads((folder / f"{frozen_id}.json").read_text(encoding="utf-8"))
        code, shown, error = support.run_main(later, *report, "--json")
        if code != 0:
            raise AssertionError(f"the report of now of {name} stopped: exit {code},"
                                 f" standard error: {error}")
        reals[name] = _Real(name, support.FIXTURE_MACHINE, frozen_id, envelope,
                            json.loads(shown))
    return reals


def _nodes(held: Any, path: tuple = ()) -> Iterator[tuple[tuple, Any]]:
    """Every node of a JSON value with the path that names it, the value itself first: the
    nodes under the keys of its objects and under the positions of its lists, the containers
    with their content."""
    yield path, held
    if isinstance(held, dict):
        for key, value in held.items():
            yield from _nodes(value, (*path, key))
    elif isinstance(held, list):
        for position, value in enumerate(held):
            yield from _nodes(value, (*path, position))


def _changed(held: Any, path: tuple[_Step, ...], change: Any) -> Any:
    """A copy of the JSON value with the node at the end of each path that `path` names
    changed: a callable receives the node and gives the node in its place, and `_REMOVED`
    takes it away. A key of the path names a key of an object and of every object of a
    list; a position names the element of a list at that position. A path that the value
    does not hold changes nothing, so that a test that named a wrong path fails on a
    document that is still read."""
    if not path:
        return change(held) if callable(change) else change
    if isinstance(held, list):
        copied = list(held)
        if isinstance(path[0], int):
            if len(path) == 1 and change is _REMOVED:
                del copied[path[0]]
            else:
                copied[path[0]] = _changed(held[path[0]], path[1:], change)
            return copied
        return [_changed(one, path, change) if isinstance(one, dict) else one
                for one in held]
    if not isinstance(held, dict) or path[0] not in held:
        return held
    copied = dict(held)
    if len(path) == 1 and change is _REMOVED:
        del copied[path[0]]
    else:
        copied[path[0]] = _changed(held[path[0]], path[1:], change)
    return copied


def _renaming(key: str) -> Callable[[dict], dict]:
    """The change that gives a key of an object its invented name; the value stays."""
    return lambda held: {_INVENTED_KEY if held_key == key else held_key: value
                         for held_key, value in held.items()}


def _kind(value: Any) -> str:
    """The kind of JSON that a value has; a boolean is no number."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a text"
    return "a list" if isinstance(value, list) else "an object"


def _refuse(text: str) -> NoReturn:
    """Refuse `NaN`, `Infinity`, and `-Infinity` in a JSON text: strict JSON holds none of
    them."""
    raise ValueError(f"{text} is no JSON number")


def _row_of(text: str, first_cell: str) -> str:
    """The line of a table of the text of a report whose first cell is the one named."""
    return next(line for line in text.split("\n") if line.startswith(first_cell))


def _role(path: tuple) -> str | None:
    """The part of a frozen report that the node at the path is, as `_ADDED_KEYS` names it,
    or None for any other node."""
    if path == ():
        return "the envelope"
    if path == ("document",):
        return "the document"
    if len(path) == 3 and path[:2] == ("document", "days"):
        return "a day"
    if path == ("document", "person"):
        return "the person"
    if len(path) == 3 and path[:2] == ("document", "projects"):
        return "a project"
    if len(path) == 3 and path[:2] == ("document", "work_items"):
        return "a work item"
    if len(path) >= 2 and path[-2] == "entries" and isinstance(path[-1], int):
        return "an entry"
    return None


def _changes(envelope: dict) -> Iterator[tuple[str, tuple, Any]]:
    """The changes of the property, each as what it does, the path of its node, and the
    change: every node but the envelope taken away; every node replaced by a value of each
    other kind of JSON, and every number by NaN; every key of every object given an invented
    name; each key of `_ADDED_KEYS` that a part of the report does not hold, added with a
    value of each kind of JSON and with the values of `_ADDED_VALUES`; and every empty list
    extended by one element of each kind of JSON."""
    for path, value in _nodes(envelope):
        if path:
            yield "taken away", path, _REMOVED
        for kind, other in _OTHER_VALUES.items():
            if kind != _kind(value):
                yield f"replaced by {kind}", path, other
        if _kind(value) == "a number":
            yield "replaced by NaN", path, math.nan
        if isinstance(value, dict):
            for key in value:
                yield f"the key {key} given an invented name", path, _renaming(key)
            for key in _ADDED_KEYS.get(_role(path) or "", ()):
                if key not in value:
                    for other in (*_OTHER_VALUES.values(), *_ADDED_VALUES.get(key, ())):
                        yield (f"the key {key} added as {json.dumps(other)}", path,
                               _adding(key, other))
        if value == []:
            for kind, other in _OTHER_VALUES.items():
                yield f"extended by {kind}", path, _adding_element(other)


def _adding_element(element: Any) -> Callable[[list], list]:
    """The change that gives a list one more element, last."""
    return lambda held: [*held, element]


class FrozenFileTests(unittest.TestCase):
    """The reader of the reports on real frozen documents: what it refuses, naming the file,
    and what it reads, on which every consumer then completes."""

    reals: dict[str, _Real]
    """The real frozen reports of the class, by the name of their scenario."""

    @classmethod
    def setUpClass(cls) -> None:
        """Freeze the real documents once, each in a fixture store of its own below one
        temporary folder, which a class cleanup closes also when a freeze stops; the tests
        only read them."""
        folder = support.TemporaryFolder()
        base = folder.__enter__()
        cls.addClassCleanup(folder.__exit__, None, None, None)
        cls.reals = _real_documents(base)

    def _read(self, store_folder: Path, real: _Real, envelope: dict) -> list[_ENVELOPE] | None:
        """Write the envelope as the file of the real frozen report, through the writer of
        the store, and read the files of the store folder through the reader of the
        reports: what it gives when it reads the file, or None when it stops with
        `frozen_report_unreadable`, which must name the file as the store holds it. Any
        other outcome fails the test."""
        store.write_frozen(store_folder, real.machine, real.frozen_id, envelope)
        return self._outcome_of_reader(store_folder, real)

    def _outcome_of_reader(self, store_folder: Path, real: _Real) -> list[_ENVELOPE] | None:
        """What the reader of the reports gives for the files of the store folder, or None
        when it stops with `frozen_report_unreadable` naming the file of the real frozen
        report."""
        try:
            return reports.read_frozen(store_folder)
        except FrozenReportUnreadable as stopped:
            self.assertEqual(stopped.code, "frozen_report_unreadable")
            self.assertEqual(stopped.values,
                             {"path": f"frozen/{real.machine}/{real.frozen_id}.json"})
            self.assertEqual(stopped.exit_code, 1)
            return None

    @contextlib.contextmanager
    def _served(self, store_folder: Path, real: _Real) -> Iterator[Callable[[Any], None]]:
        """The file of the real frozen report, written once, whose text the reader then
        receives from memory: the context gives the function that sets the envelope that the
        next reads of that file give. Both readers run as they run on a file — the listing
        of the folder, the parse of the text, every check — and only the write and the read
        of the bytes on the disk are spared, which would make the property test last a
        minute."""
        store.write_frozen(store_folder, real.machine, real.frozen_id, real.envelope)
        path = store_folder / "frozen" / real.machine / f"{real.frozen_id}.json"
        held = [json.dumps(real.envelope)]
        read_text = Path.read_text

        def serving(source: Path, *arguments: Any, **keywords: Any) -> str:
            """The text of the served file from memory, of any other file from the disk."""
            if source == path:
                return held[0]
            return read_text(source, *arguments, **keywords)

        def serve(envelope: Any) -> None:
            held[0] = json.dumps(envelope, indent=2, ensure_ascii=False) + "\n"

        with mock.patch.object(Path, "read_text", serving):
            yield serve

    def _consumers(self, store_folder: Path, real: _Real,
                   frozen: list[_ENVELOPE]) -> None:
        """Run every consumer of the frozen reports on the one file of the store folder,
        whose frozen report is `frozen`: the rows of `frozen list`, the latest frozen
        report of each day, the days of its document, its differences against the real
        report of now of the same command, and the text and the JSON of the documents that
        hold a frozen report — the list, the report of now with its differences, and, for a
        document of the two commands that `frozen show` knows, `frozen show` — in both
        languages."""
        [(machine, frozen_id, envelope)] = frozen
        self.assertEqual((machine, frozen_id), (real.machine, real.frozen_id))
        document = envelope["document"]
        rows, _ = reports.frozen_list(store_folder)
        self.assertEqual([row["id"] for row in rows], [frozen_id])
        latest = reports.latest_frozen_by_day([envelope])
        held = reports.report_days(document)
        self.assertEqual(sorted(latest), sorted(day.isoformat() for day in held))
        figure_rows: list[dict] = []
        changed: list[dict] = []
        if latest:
            figure_rows, changed = reports.differences(document, real.now)
        documents = [{"frozen": rows},
                     {**real.now, "differences": figure_rows, "changed": changed}]
        if document["command"] in reports.FROZEN_ACTIONS:
            self.assertTrue(held)  # `frozen show` reads the first and the last day
            documents.append({"frozen": document, "differences": figure_rows,
                              "changed": changed})
        for language in ("en", "it"):
            for one in documents:
                reports.render(one, language)
                json.dumps(one, ensure_ascii=False)

    def test_the_real_documents_are_read_and_every_consumer_completes(self) -> None:
        """Each real frozen report, as its command wrote it, is read by the reader of the
        reports as the reader of the file gives it, and every consumer completes on it: the
        property and the completeness below rest on documents that the reader reads."""
        with support.TemporaryFolder() as store_folder:
            for real in self.reals.values():
                with self.subTest(report=real.name):
                    frozen = self._read(store_folder, real, real.envelope)
                    self.assertIsNotNone(frozen)
                    self.assertEqual(frozen, [(real.machine, real.frozen_id, real.envelope)])
                    self.assertIn(real.envelope["document"]["command"],
                                  reports.FROZEN_ACTIONS)
                    self._consumers(store_folder, real, frozen)

    def test_the_named_damages_are_refused_and_the_file_is_named(self) -> None:
        """Each named damage — no day, a `days` that is not a list, a day that is not an
        object or that holds no day text, a key that a report command always writes absent,
        a duration, a share, the gaps, a class, an entry list, a project, or a part of the
        record in another kind, the text of a gap that is no number, and a state that is no
        day state — makes the reader of the reports stop with `frozen_report_unreadable`,
        which names the file (command-line.md › Frozen reports)."""
        with support.TemporaryFolder() as store_folder:
            for name, damage, path, change in _DAMAGES:
                with self.subTest(report=name, damage=damage):
                    real = self.reals[name]
                    changed = _changed(real.envelope, path, change)
                    self.assertNotEqual(changed, real.envelope)
                    self.assertIsNone(self._read(store_folder, real, changed))

    def test_each_damage_stops_every_reader_of_the_frozen_reports(self) -> None:
        """Each damage of `_DAMAGED_FILES`, and a file that holds lists nested deeper than
        the parser of JSON reads under a key that no consumer reads, written as the file of
        a real frozen report beside a healthy one, stops `report timesheet`, `report day`,
        `frozen list`, and `frozen show` of that report with the exit code 1 and the one
        `error:` line that names the file, before any output; `frozen show --json` holds the
        stop error and no document, so no number that strict JSON cannot hold either; and
        the healthy reports read again after each damage (command-line.md › Frozen reports,
        › Exit codes)."""
        one = support.FIXTURE_DAY_ONE.isoformat()
        reports_of_now = (("report", "timesheet", "--from", one, "--to", one),
                          ("report", "day", one))
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            folder = support.fixture_store_folder(home) / "frozen" / support.FIXTURE_MACHINE
            frozen: dict[str, tuple[str, dict]] = {}
            for action, words in zip(("report timesheet", "report day"), reports_of_now):
                code, shown, error = support.run_main(context, *words, "--freeze", "--json")
                self.assertEqual(code, 0, error)
                frozen_id = json.loads(shown)["frozen_id"]
                frozen[action] = (frozen_id, json.loads(
                    (folder / f"{frozen_id}.json").read_text(encoding="utf-8")))
            nested = (json.dumps(frozen["report day"][1])[:-1]
                      + f', "invented": {"[" * _NESTING}{"]" * _NESTING}}}')
            damaged = [(action, name, json.dumps(_changed(frozen[action][1], path, change)))
                       for action, name, path, change in _DAMAGED_FILES]
            damaged.append(("report day", "lists nested deeper than the parser reads",
                            nested))
            for action, name, text in damaged:
                frozen_id, envelope = frozen[action]
                named = f"frozen/{support.FIXTURE_MACHINE}/{frozen_id}.json"
                message = (f"The file {named} of a frozen report is not readable; remove it"
                           " with frozen remove.")
                line = f"error: {message}\n"
                (folder / f"{frozen_id}.json").write_text(text, encoding="utf-8")
                for words in (*reports_of_now, ("frozen", "list"),
                              ("frozen", "show", frozen_id)):
                    with self.subTest(damage=name, command=" ".join(words)):
                        code, shown, error = support.run_main(context, *words)
                        self.assertEqual((code, shown, error), (1, "", line))
                with self.subTest(damage=name, command="frozen show --json"):
                    code, shown, error = support.run_main(
                        context, "frozen", "show", frozen_id, "--json")
                    self.assertEqual((code, error), (1, line))
                    self.assertEqual(json.loads(shown, parse_constant=_refuse)["error"], {
                        "code": "frozen_report_unreadable", "values": {"path": named},
                        "message": message})
                store.write_frozen(support.fixture_store_folder(home),
                                   support.FIXTURE_MACHINE, frozen_id, envelope)
            for frozen_id, _ in frozen.values():
                code, shown, error = support.run_main(context, "frozen", "show", frozen_id)
                self.assertEqual(code, 0, error)
            for words in (*reports_of_now, ("frozen", "list")):
                code, shown, error = support.run_main(context, *words)
                self.assertEqual(code, 0, error)

    def test_the_proposed_value_and_the_context_are_read_and_shown(self) -> None:
        """The keys that no report command writes and that the text shows when a frozen
        document holds them, as `timesheet <day>` writes them: a proposed value on an
        entry that is a duration or null, and a context on a day whose agent time is a
        duration and whose presence span is a duration or null. The reader reads the
        document; `frozen show` shows both in its text, in English and in Italian, a null
        value giving an empty cell and a null presence span no line; and its JSON holds
        them (command-line.md › Frozen reports, › Output)."""
        one = support.FIXTURE_DAY_ONE.isoformat()
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            code, shown, error = support.run_main(
                context, "report", "timesheet", "--from", one, "--to", one, "--freeze",
                "--json")
            self.assertEqual(code, 0, error)
            frozen_id = json.loads(shown)["frozen_id"]
            store_folder = support.fixture_store_folder(home)
            envelope = json.loads((store_folder / "frozen" / support.FIXTURE_MACHINE
                                   / f"{frozen_id}.json").read_text(encoding="utf-8"))
            day = envelope["document"]["days"][0]
            self.assertNotIn("proposed", day["entries"][0])
            self.assertNotIn("context", day)
            day["entries"][0]["proposed"] = 900
            day["context"] = {"agent_time": 300, "presence_span": 240}
            store.write_frozen(store_folder, support.FIXTURE_MACHINE, frozen_id, envelope)
            for language in ("en", "it"):
                code, shown, error = support.run_main(
                    context, "frozen", "show", frozen_id, "--language", language)
                self.assertEqual(code, 0, error)
                self.assertIn(f"{label('agent_time', language)}  0:05\n"
                              f"{label('presence_span', language)}  0:04", shown)
                self.assertTrue(_row_of(shown, "Alpha").endswith("  0:15"), shown)
            code, shown, error = support.run_main(
                context, "frozen", "show", frozen_id, "--json")
            self.assertEqual(code, 0, error)
            held = json.loads(shown)["frozen"]["days"][0]
            self.assertEqual(held["context"], {"agent_time": 300, "presence_span": 240})
            self.assertEqual(held["entries"][0]["proposed"], 900)
            day["entries"][0]["proposed"] = None
            day["context"]["presence_span"] = None
            store.write_frozen(store_folder, support.FIXTURE_MACHINE, frozen_id, envelope)
            code, shown, error = support.run_main(context, "frozen", "show", frozen_id)
            self.assertEqual(code, 0, error)
            self.assertIn(f"{label('agent_time', 'en')}  0:05", shown)
            self.assertNotIn(label("presence_span", "en"), shown)
            self.assertIn(f"{label('proposed', 'en')}\n", shown)  # the column stays
            self.assertFalse(_row_of(shown, "Alpha").endswith("0:15"), shown)
            code, shown, error = support.run_main(
                context, "report", "timesheet", "--from", one, "--to", one)
            self.assertEqual(code, 0, error)

    def test_a_frozen_report_without_the_parallel_ratio_is_read(self) -> None:
        """A frozen `report day` written before the parallel ratio: the reader reads its
        document with the key taken away from the person and from Alpha, and `report
        day` of its day completes — exit code 0 — with one row of `differences` per
        holder that the document of now holds the ratio for, each `figure`
        `parallel_ratio` with `now` 1.0 and no `frozen`, the person first and Alpha
        after; the text shows the two rows with an empty Frozen cell and `1.00`, in
        English and in Italian, and `frozen show` completes, the tables of the frozen
        document showing the empty cells of the ratio (command-line.md › Frozen
        reports; metrics.md › Agent time)."""
        one = support.FIXTURE_DAY_ONE.isoformat()
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            code, shown, error = support.run_main(
                context, "report", "day", one, "--freeze", "--json")
            self.assertEqual(code, 0, error)
            frozen_id = json.loads(shown)["frozen_id"]
            store_folder = support.fixture_store_folder(home)
            envelope = json.loads((store_folder / "frozen" / support.FIXTURE_MACHINE
                                   / f"{frozen_id}.json").read_text(encoding="utf-8"))
            document = envelope["document"]
            self.assertEqual(document["person"]["parallel_ratio"], 1.0)
            self.assertEqual(document["projects"][0]["parallel_ratio"], 1.0)
            del document["person"]["parallel_ratio"]
            del document["projects"][0]["parallel_ratio"]
            store.write_frozen(store_folder, support.FIXTURE_MACHINE, frozen_id, envelope)
            self.assertEqual([row[2] for row in reports.read_frozen(store_folder)],
                             [envelope])
            rows = [{"day": one, "figure": "parallel_ratio", "now": 1.0},
                    {"day": one, "project": {"id": "alpha", "name": "Alpha"},
                     "figure": "parallel_ratio", "now": 1.0}]
            shown_rows = {
                "en": {"2026-11-20                      parallel_ratio          1.00",
                       "2026-11-20  Alpha               parallel_ratio          1.00"},
                "it": {"2026-11-20                             parallel_ratio"
                       "               1.00",
                       "2026-11-20  Alpha                      parallel_ratio"
                       "               1.00"},
            }
            for language in ("en", "it"):
                with self.subTest(language=language):
                    code, held, error = support.run_main(
                        context, "report", "day", one, "--language", language, "--json")
                    self.assertEqual(code, 0, error)
                    self.assertEqual(json.loads(held)["differences"], rows)
                    code, text, error = support.run_main(
                        context, "report", "day", one, "--language", language)
                    self.assertEqual(code, 0, error)
                    self.assertEqual({line for line in text.split("\n")
                                      if "parallel_ratio" in line},
                                     shown_rows[language])
                    code, text, error = support.run_main(
                        context, "frozen", "show", frozen_id, "--language", language)
                    self.assertEqual(code, 0, error)
                    gap = 26 if language == "en" else 38
                    self.assertIn("0:05" + " " * gap + "0:00", text)

    def test_the_document_of_another_action_is_read(self) -> None:
        """A frozen report of another command, as a file that a newer version wrote on
        another machine: the reader reads it by the kinds of its figures alone, `frozen
        list` names its command, and `differences` compares it on the figures that both
        documents hold; the same document with a duration in another kind is refused
        (command-line.md › Frozen reports)."""
        real = self.reals["the timesheet of the declared day"]
        week = _changed(real.envelope, ("document", "command"), "report week")
        with support.TemporaryFolder() as store_folder:
            frozen = self._read(store_folder, real, week)
            self.assertIsNotNone(frozen)
            self.assertEqual([row["report"] for row in reports.frozen_list(store_folder)[0]],
                             ["report week"])
            self.assertEqual(reports.differences(week["document"], real.now), ([], []))
            self.assertIsNone(self._read(
                store_folder, real, _changed(week, ("document", "days", "total"), "60")))

    def test_every_change_of_every_leaf_stops_the_reader_or_completes(self) -> None:
        """The property. For every leaf of every real envelope — the containers too — the
        envelope with one change of `_changes`: the leaf taken away; the leaf replaced by a
        value of each other kind of JSON, and a number by NaN; a key of an object given an
        invented name, each key of the object in turn, so that each key of an object from a
        text to a number is named too; a key that a consumer reads when it is held, added to
        the part of the report that does not hold it; an empty list extended by one element.
        Written as the file of its frozen report, each changed envelope either stops the
        reader with `frozen_report_unreadable` or lets every consumer complete; no exception
        of any kind is a pass (command-line.md › Frozen reports). The envelope itself is
        never taken away: a file that holds none is a damage of the reader of the file. The
        text of the file comes from memory (`_served`); both readers and every consumer run
        as they do on the disk. Each real document gives cases that the reader refuses and
        cases that it reads, so the consumers run on changed documents too."""
        for real in self.reals.values():
            refused = read_on = 0
            with support.TemporaryFolder() as store_folder, \
                    self._served(store_folder, real) as serve:
                self.assertIsNotNone(self._outcome_of_reader(store_folder, real), real.name)
                for what, at, change in _changes(real.envelope):
                    changed = _changed(real.envelope, at, change)
                    # the JSON text, because a boolean compares equal to the number it
                    # names in Python — `True == 1.0` — and the reader tells them apart
                    self.assertNotEqual(json.dumps(changed), json.dumps(real.envelope))
                    serve(changed)
                    try:
                        read = self._outcome_of_reader(store_folder, real)
                        if read is not None:
                            self._consumers(store_folder, real, read)
                    except Exception as fault:
                        leaf = ".".join(str(step) for step in at) or "the envelope"
                        self.fail(f"{real.name}: the leaf {leaf}, {what}: a reader or a"
                                  f" consumer failed: {type(fault).__name__}: {fault}")
                    if read is None:
                        refused += 1  # the reader stops: a pass
                    else:
                        read_on += 1
            self.assertTrue(refused and read_on, (real.name, refused, read_on))

    def test_each_key_that_a_report_action_always_writes_is_required(self) -> None:
        """The completeness of the keys: each key that `report timesheet` or `report day`
        always writes, taken away from a real document of that command that holds it — from
        every object of a list where the path names a list — makes the reader stop, the file
        named; and at least one real document of the command holds each key, a day without
        work items holding none to take a key from (command-line.md › JSON documents)."""
        with support.TemporaryFolder() as store_folder:
            for action, written in _ALWAYS_WRITTEN.items():
                reals = [real for real in self.reals.values()
                         if real.envelope["document"]["command"] == action]
                for real in reals:
                    self.assertIsNotNone(self._read(store_folder, real, real.envelope))
                for path in written:
                    without = [(real, _changed(real.envelope, path, _REMOVED))
                               for real in reals]
                    self.assertTrue(any(changed != real.envelope for real, changed in without),
                                    f"no real document of {action} holds {path}")
                    for real, changed in without:
                        if changed != real.envelope:  # this document holds the key
                            with self.subTest(report=real.name, key=".".join(path)):
                                self.assertIsNone(self._read(store_folder, real, changed))
