"""The frozen reports and their differences (command-line.md › Frozen reports, › JSON
documents): the JSON document of a report kept as given in the store folder, the one reader
of the frozen reports for every command that reads them, the rows that `frozen list` shows,
the latest frozen report of each day, and what differs between a frozen report and a report
of now."""

from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any, Optional, Union

from ..declared import DECLARED_DAY, MEASURED_DAY
from ..events import format_instant, parse_instant
from ..store.files import (
    FrozenReportUnreadable,
    TargetNotFound,
    frozen_name,
    frozen_names,
    list_frozen,
    machine_labels,
    remove_frozen,
    write_frozen,
)

_ABSENT = object()
"""The marker of a value that one side of a comparison does not hold: an absent value is
left out of a row, never null."""

_DAY_FIGURES = ("total", "measured_total", "unknown_invocation_share",
                "human_time_at_idle_gaps")
"""The figures that the day of a document holds beside its entries, its person, its
projects, and its work items (command-line.md › JSON documents); the state of the day is
no figure."""

_ENTRY_FIGURES = ("measured", "with_manual_entries", "declared", "inferred_human_share",
                  "inferred_agent_share")
"""The figures of one entry of the timesheet of a day (command-line.md › JSON documents)."""

_MEASURES = ("human_time", "agent_time", "parallel_ratio", "blocked_time",
              "activity_classes")
"""The measures of the person, of a project, and of a work item of a day."""

_MEASURE_FIGURES = (*_MEASURES, "inferred_human_share", "inferred_agent_share")
"""The measures of a project and of a work item of a day, with the shares of the inferred
repository identity; the person holds no shares."""

_RULE_PARTS = ("identity_rules", "category_rules")
"""The parts of the report record whose lists of rules `changed` compares."""

_DATED_PARTS = ("time_zones", "day_starts")
"""The lists of dated facts of the report record that `changed` compares."""

FROZEN_ACTIONS = ("report timesheet", "report day")
"""The commands whose report a frozen report can be the document of (command-line.md ›
Frozen reports): `frozen show` computes the report of now with the command that the frozen
document names."""

_Kind = Callable[[Any], bool]
"""Whether a value has the kind that a key of a document names."""

_Shape = Union[_Kind, list["_Shape"], dict[str, "_Shape"],
               tuple[tuple[str, ...], dict[str, "_Shape"]]]
"""The shape of a value of a document: a kind; a list with the shape of each of its
elements; an object, as the shape of each of its keys that it may hold; or the same object
behind the keys that it must hold."""

_Keys = dict[str, Optional["_Keys"]]
"""The keys that an object always holds, each with the keys that its own value always
holds, or None where any value stands."""


def _text(value: Any) -> bool:
    """The kind of a text."""
    return isinstance(value, str)


def _duration(value: Any) -> bool:
    """The kind of a duration: a whole number, a boolean being no number."""
    return isinstance(value, int) and not isinstance(value, bool)


def _number(value: Any) -> bool:
    """The kind of a number from a division — a share or a ratio: an integer or a
    float, a boolean being no number."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _list(value: Any) -> bool:
    """The kind of a list of rules or of dated facts."""
    return isinstance(value, list)


def _day_text(value: Any) -> bool:
    """The kind of a day: a text that `report_days` reads as a local day."""
    if not _text(value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _day_state(value: Any) -> bool:
    """The kind of the state of a day: one of the two day states of `declared`."""
    return value in (MEASURED_DAY, DECLARED_DAY)


def _named(value: Any) -> bool:
    """The kind of a project or of a work item: an object that holds `id` and `name` as
    texts, or null for the unattributed time and for no work item."""
    return value is None or (isinstance(value, dict) and _text(value.get("id"))
                             and _text(value.get("name")))


def _counted(value: Any) -> bool:
    """The kind of the activity classes: an object from a text to a whole number."""
    return isinstance(value, dict) and all(_duration(held) for held in value.values())


def _gaps(value: Any) -> bool:
    """The kind of the human time at the idle gaps: an object from the text of an idle gap,
    one that `int` reads as the text of the table does, to a whole number."""
    if not _counted(value):
        return False
    for gap in value:
        try:
            int(gap)
        except ValueError:
            return False
    return True


def _or_none(kind: _Kind) -> _Kind:
    """The kind of a key that the document writes as null where it holds no value."""
    return lambda value: value is None or kind(value)


_ENTRY_KINDS: _Shape = {
    "project": _named, "work_item": _named, "measured": _duration,
    "with_manual_entries": _duration, "declared": _or_none(_duration),
    "inferred_human_share": _number, "inferred_agent_share": _number,
    "proposed": _or_none(_duration),
}
"""The shape of an entry of the timesheet of a day: its project and its work item, its
three durations — `declared` is null on a measured day —, its two shares, and the proposed
value that the text shows when the entry holds it, null where the proposal holds none."""

_MEASURE_KINDS: _Shape = {"human_time": _duration, "agent_time": _duration,
                          "parallel_ratio": _number, "blocked_time": _duration,
                          "activity_classes": _counted}
"""The shape of the measures of the person, of a project, and of a work item of a day:
the parallel ratio a key that no document must hold, so a frozen report written before
it is read."""

_PROJECT_KINDS: _Shape = {"project": _named, **_MEASURE_KINDS,
                          "inferred_human_share": _number,
                          "inferred_agent_share": _number}
"""The shape of a project of a day, the unattributed time holding a null project."""

_WORK_ITEM_KINDS: _Shape = {"work_item": _named, **_MEASURE_KINDS,
                            "inferred_human_share": _number,
                            "inferred_agent_share": _number}
"""The shape of a work item of a day."""

_CONTEXT_KINDS: _Shape = (("agent_time", "presence_span"),
                          {"agent_time": _duration, "parallel_ratio": _number,
                           "presence_span": _or_none(_duration)})
"""The shape of the context of a day, which the text shows when the day holds it: its agent
time, its parallel ratio when it holds one, and its presence span, null on a day without
one."""

_DAY_KINDS: _Shape = {
    "day": _day_text, "state": _day_state, "total": _duration, "measured_total": _duration,
    "unknown_invocation_share": _number, "human_time_at_idle_gaps": _gaps,
    "person": _MEASURE_KINDS, "entries": [_ENTRY_KINDS], "projects": [_PROJECT_KINDS],
    "work_items": [_WORK_ITEM_KINDS], "context": _CONTEXT_KINDS,
}
"""The shape of the keys of a day that a document may hold: its day, its state, its
figures, its entries, its person, its projects, its work items, and its context."""

_RECORD_KINDS: _Shape = {
    "parameters": {"idle_gap": _duration, "minimum_attention": _duration,
                   "stale_limit": _duration, "timesheet_granularity": _duration},
    "identity_rules": _list, "category_rules": _list,
    "dated_facts": {"time_zones": _list, "day_starts": _list},
}
"""The shape of the parts of the report record that `changed` compares."""

_DOCUMENT_KINDS: _Shape = {**_DAY_KINDS, "days": [(("day",), _DAY_KINDS)],
                           "record": _RECORD_KINDS}
"""The shape of the document of any command: the keys of a day, because a document that
holds `day` is itself a day object; `days`, a list of day objects, each holding its day;
and the record."""

_ENTRY_KEYS: _Keys = {"project": None, "work_item": None, **dict.fromkeys(_ENTRY_FIGURES)}
"""The keys that an entry of the timesheet of a day always holds."""

_MEASURE_KEYS: _Keys = {"human_time": None, "agent_time": None, "blocked_time": None,
                        "activity_classes": None}
"""The keys that the person, a project, and a work item of a day always hold: the
parallel ratio stays away, because a holder with no agent time writes none and a frozen
report written before the ratio is read like any other."""

_RECORD_KEYS: _Keys = {"parameters": None, "identity_rules": None, "category_rules": None,
                       "dated_facts": {"time_zones": None, "day_starts": None}}
"""The keys that the report record of a report command always holds."""

_ALWAYS_WRITTEN: dict[str, _Keys] = {
    "report timesheet": {
        "days": {"day": None, "state": None, "total": None, "measured_total": None,
                 "unknown_invocation_share": None, "entries": _ENTRY_KEYS},
        "record": _RECORD_KEYS,
    },
    "report day": {
        "day": None, "state": None, "unknown_invocation_share": None, "person": _MEASURE_KEYS,
        "projects": {"project": None, **_MEASURE_KEYS, "inferred_human_share": None,
                     "inferred_agent_share": None},
        "work_items": {"work_item": None, **_MEASURE_KEYS, "inferred_human_share": None,
                       "inferred_agent_share": None},
        "record": _RECORD_KEYS,
    },
}
"""The keys that each command of `FROZEN_ACTIONS` always writes (command-line.md › JSON
documents), which its text reads and `differences` compares; the human time at the idle gaps
is absent, because a declared day holds none."""


_NEVER_KEPT = ("frozen", "differences", "changed")
"""The keys that a frozen document never holds, whatever its command: `frozen`, which the
documents of `frozen list` and of `frozen show` hold, and `differences` and `changed`, which
a freeze leaves out of the document it keeps. The text would read a document that holds one
of them as one of those documents."""

_NEVER_WRITTEN: dict[str, tuple[str, ...]] = {"report timesheet": ("day",),
                                              "report day": ("days",)}
"""For each command of `FROZEN_ACTIONS`, the key of the shape of its other command, which
its document never holds: `_days_of` and the text read `days` before `day`, so the command
of the document alone must fix its shape."""


def freeze(
    store_folder: Path,
    machine: str,
    document: dict,
    note: str | None,
    now: datetime,
    new_uid: Callable[[], str],
) -> str:
    """Keep the JSON document of a report as a frozen report of the machine
    (command-line.md › Frozen reports): the file `frozen/<machine>/<id>.json` of the store
    folder holds that document unchanged, with the identifier of the freeze added, as
    `document`, the note as `note` when the report has one, and the instant of the freeze
    as `frozen_at`; returns the identifier, a UUID 4 in the command. The document is the
    one that the command writes with `--json` without its differences against other frozen
    reports, which every later report computes again."""
    frozen_id = new_uid()
    envelope: dict[str, Any] = {"document": {**document, "frozen_id": frozen_id}}
    if note is not None:
        envelope["note"] = note
    envelope["frozen_at"] = format_instant(now)
    write_frozen(store_folder, machine, frozen_id, envelope)
    return frozen_id


def read_frozen(store_folder: Path) -> list[tuple[str, str, dict]]:
    """The frozen reports of the store, read for every command that reads them: what
    `store.list_frozen` gives — the machine, the identifier, and the envelope of each file,
    in the order of the paths as text, the envelope read by the reader of the file — after
    the document of each envelope passed `_is_frozen_document`. A file that either reader
    refuses stops with `FrozenReportUnreadable`, which names the file as the store holds it
    (command-line.md › Frozen reports)."""
    frozen = []
    for machine, frozen_id, envelope in list_frozen(store_folder):
        if not _is_frozen_document(envelope["document"]):
            raise FrozenReportUnreadable(frozen_name(machine, frozen_id))
        frozen.append((machine, frozen_id, envelope))
    return frozen


def frozen_list(store_folder: Path) -> tuple[list[dict], list[dict]]:
    """The rows of `frozen list` (command-line.md › JSON documents), in the order of the
    files of the store: the identifier, the command and the period of the document, the
    note when the report has one, the machine that wrote the file with its machine label
    when the store holds one, and the instant of the freeze; and the warnings of the
    machine labels, each store metadata read once for all the rows of its machine. The
    files are read through `read_frozen`, so a file that the ledger cannot read stops the
    listing."""
    frozen = read_frozen(store_folder)
    labels, warnings = machine_labels(store_folder, [machine for machine, _, _ in frozen])
    rows = []
    for machine, frozen_id, envelope in frozen:
        held = _days_of(envelope["document"])
        row: dict[str, Any] = {"id": frozen_id,
                               "report": envelope["document"]["command"]}
        if held:
            row["from"] = min(held)
            row["to"] = max(held)
        if "note" in envelope:
            row["note"] = envelope["note"]
        row["machine"] = machine
        if machine in labels:
            row["machine_label"] = labels[machine]
        row["frozen_at"] = envelope["frozen_at"]
        rows.append(row)
    return rows, warnings


def latest_frozen_by_day(frozen: Sequence[dict]) -> dict[str, dict]:
    """The document of the latest frozen report that holds each day (command-line.md ›
    Frozen reports), from the envelopes of the store: the one with the latest `frozen_at`,
    and, at the same `frozen_at`, the one with the latest identifier as text."""
    latest: dict[str, tuple[tuple[Any, str], dict]] = {}
    for envelope in frozen:
        document = envelope["document"]
        order = (parse_instant(envelope["frozen_at"]),
                 document.get("frozen_id", ""))
        for day in _days_of(document):
            if day not in latest or order > latest[day][0]:
                latest[day] = (order, document)
    return {day: document for day, (_, document) in latest.items()}


def differences(frozen: dict, current: dict) -> tuple[list[dict], list[dict]]:
    """What differs between a frozen report and a report of now (command-line.md › Frozen
    reports, › JSON documents), from their documents: `differences`, one row for each
    figure of each day, project, and work item whose value differs, with the frozen value
    and the value of now; and `changed`, one row for each report parameter, rule, and
    dated fact that differs between the two report records."""
    frozen_days = _days_of(frozen)
    current_days = _days_of(current)
    figure_rows: list[dict] = []
    for day in sorted(set(frozen_days) & set(current_days)):
        figure_rows.extend(_day_differences(day, frozen_days[day], current_days[day]))
    return figure_rows, _record_changes(frozen["record"], current["record"])


def remove_frozen_report(store_folder: Path, frozen_id: str, own_machine: str) -> None:
    """Remove the frozen report with the identifier (command-line.md › Frozen reports):
    only the machine that wrote the file removes it; an identifier that the store does not
    hold stops with the target that is not found. The file is found by its name and read
    never, so a file that the ledger cannot read as a frozen report is removed too."""
    for machine, held_id in frozen_names(store_folder):
        if held_id == frozen_id:
            remove_frozen(store_folder, machine, frozen_id, own_machine)
            return
    raise TargetNotFound(frozen_id)


def report_days(document: dict) -> list[date]:
    """The local days that a report document covers, in the order of the document: the
    days of `report timesheet`, or the one day of `report day`; a document of another
    shape covers none."""
    return [date.fromisoformat(day) for day in _days_of(document)]


def _days_of(document: dict) -> dict[str, dict]:
    """The days that a report document holds, from the day as text to the document of the
    day: the days of `report timesheet`, or the one day of `report day`."""
    if "days" in document:
        return {day["day"]: day for day in document["days"]}
    if "day" in document:
        return {document["day"]: document}
    return {}


def _day_differences(day: str, frozen_day: dict, current_day: dict) -> list[dict]:
    """The rows of `differences` of one day that both documents hold: the figures of the
    day, of its entries, and of its person, projects, and work items, in the order of the
    frozen document first, then the figures that only the document of now holds."""
    frozen_figures = _figures_of(frozen_day)
    current_figures = _figures_of(current_day)
    rows = []
    for key, (locator, frozen_value) in frozen_figures.items():
        if key in current_figures:
            _, current_value = current_figures.pop(key)
            if current_value != frozen_value:
                rows.append(_figure_row(day, locator, key[-1], frozen_value, current_value))
        else:
            rows.append(_figure_row(day, locator, key[-1], frozen_value, _ABSENT))
    for key, (locator, current_value) in current_figures.items():
        rows.append(_figure_row(day, locator, key[-1], _ABSENT, current_value))
    return rows


def _figures_of(day: dict) -> dict[tuple, tuple[dict, Any]]:
    """The figures of one day of a document: a map from the key of each figure — the
    section of the day and the project and work item that hold it, and the name of the
    figure — to the keys that name its row and its value; a value of None is no value."""
    held: dict[tuple, tuple[dict, Any]] = {}

    def hold(key: tuple, locator: dict, value: Any) -> None:
        if value is not None:
            held[key] = (locator, value)

    for name in _DAY_FIGURES:
        hold(("day", name), {}, day.get(name))
    person = day.get("person")
    if person is not None:
        for name in _MEASURES:
            hold(("person", name), {}, person.get(name))
    for entry in day.get("entries", []):
        locator = {"project": entry.get("project"), "work_item": entry.get("work_item")}
        for name in _ENTRY_FIGURES:
            hold(("entry", _id_of(entry.get("project")), _id_of(entry.get("work_item")),
                  name), locator, entry.get(name))
    for project in day.get("projects", []):
        locator = {"project": project.get("project")}
        for name in _MEASURE_FIGURES:
            hold(("project", _id_of(project.get("project")), name), locator,
                 project.get(name))
    for work_item in day.get("work_items", []):
        locator = {"work_item": work_item.get("work_item")}
        for name in _MEASURE_FIGURES:
            hold(("work_item", _id_of(work_item.get("work_item")), name), locator,
                 work_item.get(name))
    return held


def _figure_row(day: str, locator: dict, figure: str,
                frozen_value: Any, now_value: Any) -> dict:
    """One row of `differences`: the day, the project and work item that hold the figure
    when one does, the name of the figure, and the values that differ."""
    row = {"day": day, **locator, "figure": figure}
    if frozen_value is not _ABSENT:
        row["frozen"] = frozen_value
    if now_value is not _ABSENT:
        row["now"] = now_value
    return row


def _record_changes(frozen_record: dict, current_record: dict) -> list[dict]:
    """The rows of `changed` between two report records: the parameters, the rules, and
    the dated facts that differ (command-line.md › JSON documents); the versions, the
    configuration errors, and the state of the store are no fact of a rule."""
    rows = []
    frozen_parameters = frozen_record.get("parameters", {})
    current_parameters = current_record.get("parameters", {})
    keys = [*frozen_parameters,
            *(key for key in current_parameters if key not in frozen_parameters)]
    for key in keys:
        rows.extend(_value_changes(f"parameters.{key}",
                                   frozen_parameters.get(key, _ABSENT),
                                   current_parameters.get(key, _ABSENT)))
    for part in _RULE_PARTS:
        rows.extend(_list_changes(frozen_record.get(part, []),
                                  current_record.get(part, []), part))
    frozen_facts = frozen_record.get("dated_facts", {})
    current_facts = current_record.get("dated_facts", {})
    for part in _DATED_PARTS:
        rows.extend(_list_changes(frozen_facts.get(part, []), current_facts.get(part, []),
                                  f"dated_facts.{part}"))
    return rows


def _list_changes(frozen_items: list, current_items: list, path: str) -> list[dict]:
    """The rows of `changed` of two lists of rules or dated facts, position by position:
    the rule that changed holds its frozen value and its value of now, and a rule that one
    record alone holds holds that one value."""
    rows = []
    for position in range(max(len(frozen_items), len(current_items))):
        rows.extend(_value_changes(f"{path}[{position}]",
                                   frozen_items[position] if position < len(frozen_items)
                                   else _ABSENT,
                                   current_items[position] if position < len(current_items)
                                   else _ABSENT))
    return rows


def _value_changes(path: str, frozen_value: Any, now_value: Any) -> list[dict]:
    """The row of `changed` of one fact when its values differ: its path in the record and
    the values that differ."""
    if frozen_value == now_value:
        return []
    row = {"path": path}
    if frozen_value is not _ABSENT:
        row["frozen"] = frozen_value
    if now_value is not _ABSENT:
        row["now"] = now_value
    return [row]


def _id_of(held: dict | None) -> str | None:
    """The identifier that a project or work item object names, or None when it is the
    unattributed time or no work item."""
    return None if held is None else held["id"]


def _is_frozen_document(document: Any) -> bool:
    """Whether the document of a file is one that the consumers of the frozen reports read.
    The consumers are `differences`, `report_days`, `latest_frozen_by_day`, `frozen_list`,
    the actions of `cli` that read a frozen report, and the text of `frozen show`
    (`text.py`); each key that one of them reads only when the document holds it is in the
    shapes below with its kind. The checks are those of the kind of each key, never of its
    range: a duration may be negative, and a share larger than one.

    The document of any command holds none of the keys of `_NEVER_KEPT`, and every key that
    it holds has its kind (`_DOCUMENT_KINDS`): a figure of a day is a whole number, a share
    and the parallel ratio a number — the ratio a key that no command must write, so a
    frozen report written before it is read —, the activity classes and the human time at
    the idle gaps an object from a text to a whole number, a project or a work item an
    object with `id` and `name` as texts or null, the state of a day one of the two day
    states, the proposed value of an entry a whole number or null, the context of a day an
    object whose agent time is a whole number, whose parallel ratio, when it holds one, is
    a number, and whose presence span is a whole number or null; a document that holds
    `day` is itself a day object; `days` is a list of day objects, each holding a `day`
    that is a day text; and the parts of the record that `changed` compares have their
    kinds. Beside `frozen_id`, whose kind the reader of the file checks against the name
    of the file (`store/files.py`), and the two keys of the document that every consumer
    reads, every key that the shapes do not name is free: no consumer reads it by name.

    The document of a command of `FROZEN_ACTIONS` also holds every key that the command
    always writes (`_ALWAYS_WRITTEN`), none of the keys of `_NEVER_WRITTEN`, and at least
    one day, because `frozen show` computes the report of now from the first day of the
    document to the last.
    """
    if not _fits(document, _DOCUMENT_KINDS) or any(key in document for key in _NEVER_KEPT):
        return False
    action = document.get("command")
    if not isinstance(action, str) or action not in _ALWAYS_WRITTEN:
        return True
    if any(key in document for key in _NEVER_WRITTEN.get(action, ())):
        return False
    if "days" in document and not document["days"]:
        return False
    return _holds(document, _ALWAYS_WRITTEN[action])


def _fits(value: Any, shape: _Shape) -> bool:
    """Whether a value has the shape: a kind tests the value; a list is the shape of every
    element of a list; an object holds, with their shapes, the keys that it may hold, its
    other keys being free; and a pair of keys and of an object is the same object, the keys
    being the ones that it must hold."""
    if callable(shape):
        return shape(value)
    if isinstance(shape, list):
        return isinstance(value, list) and all(_fits(one, shape[0]) for one in value)
    required, fields = shape if isinstance(shape, tuple) else ((), shape)
    if not isinstance(value, dict) or any(key not in value for key in required):
        return False
    return all(_fits(value[key], held) for key, held in fields.items() if key in value)


def _holds(value: Any, keys: _Keys) -> bool:
    """Whether an object holds every key of `keys` and, under each key that names the keys
    of its own value, an object that holds them or a list whose every object holds them."""
    if isinstance(value, list):
        return all(_holds(one, keys) for one in value)
    if not isinstance(value, dict) or any(key not in value for key in keys):
        return False
    return all(_holds(value[key], held) for key, held in keys.items() if held is not None)
