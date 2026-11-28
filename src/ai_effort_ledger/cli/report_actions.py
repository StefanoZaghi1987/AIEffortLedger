"""The actions of the report commands (command-line.md › Reports, › Frozen reports, ›
Timesheet, › Output, › JSON documents): `report timesheet`, `report day`, `timesheet
<day>`, and `sessions <day>` compute their figures through the one pipeline of `figures`
and build their document with the report record; the two reports also hold their
differences against the latest frozen reports of their days. A report takes no lock
(architecture.md › Concurrency), but one with `--freeze` writes a frozen report into the
store folder and takes it, as `frozen remove` does; `frozen list` and `frozen show` only
read. In text mode a report writes its warning and configuration-error lines to the
standard error before its text, so that the person reads them before the table
(command-line.md › Reports)."""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path

from .. import days, reports
from ..configuration import (
    PersonConfiguration,
    ReportParameters,
    WrongValue,
    resolve_parameters,
)
from ..declared import Bucket, _seconds, _window, bucket_order
from ..events import Event, event_order, parse_instant
from ..ingestion.run import LOCK_FILE
from ..language import label
from ..platform import StoreLock
from ..store import TargetNotFound
from . import Context, inside_folder, machine_configuration
from .figures import (
    Figures,
    figures_of_days,
    proposed_values,
    report_names,
    report_options,
    report_warnings,
)
from .output import Outcome, json_document, write_lines


class FrozenActionUnknown(Exception):
    """The stop error of a frozen report whose document names a command that this version
    of the ledger does not know, for which `frozen show` cannot compute a report of now
    (command-line.md › Exit codes).

    A stop error carries a code, values, and an exit code; the output language holds the
    text.
    """

    def __init__(self, frozen_id: str, action_name: str) -> None:
        self.code = "frozen_command_unknown"
        self.values = {"id": frozen_id, "command": action_name}
        self.exit_code = 1
        super().__init__(f"{frozen_id}: {action_name}")


def report_timesheet(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `report timesheet` (command-line.md › Reports, › JSON documents):
    the daily timesheet of the local days from `--from` to `--to`, both included. A period
    whose first day comes after its last day holds no day, so the command stops with a
    wrong value that names `--to`: after the machine and the person
    configuration are read, because the day words name local days of the person, and
    before any figure is computed. Where frozen reports hold days of the period, the
    document also holds `differences` and `changed`; with `--freeze` it also holds
    `frozen_id` (command-line.md › Frozen reports)."""
    _, person, store = context.require_setup(options.store)
    local = days.LocalDays(person.time_zones, person.day_starts)
    first = _day(local, getattr(options, "from"), context.now)
    last = _day(local, options.to, context.now)
    if first > last:
        raise WrongValue("--to", options.to)
    return _report(context, options, person, store, first, last, _timesheet_document)


def report_day(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `report day` (command-line.md › Reports, › JSON documents): the
    human time, the agent time, the blocked time, and the activity classes of the person,
    of each project, and of each work item of the local day; where a frozen report holds
    the day, the document also holds `differences` and `changed`; with `--freeze` it also
    holds `frozen_id` (command-line.md › Frozen reports)."""
    _, person, store = context.require_setup(options.store)
    local = days.LocalDays(person.time_zones, person.day_starts)
    day = _day(local, options.day, context.now)
    return _report(context, options, person, store, day, day, _day_document)


def timesheet(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `timesheet <day>` (command-line.md › Commands, › Timesheet, › JSON
    documents): the timesheet proposal of a measured day, or the timesheet entries of a
    declared day, each with the measured values next to it, the agent time and the
    presence span of the day as its context, and the report record. The command shows no
    difference against any frozen report (command-line.md › Reports)."""
    _, person, store = context.require_setup(options.store)
    local = days.LocalDays(person.time_zones, person.day_starts)
    day = _day(local, options.day, context.now)
    figures, parameters = _figures(context, options, person, store, day, day)
    shown = figures.days[0]
    document = {
        **reports.timesheet_day_document(
            shown, proposed_values(shown, parameters.timesheet_granularity),
            report_names(figures)),
        "record": _record(context, parameters, person, figures),
    }
    return _outcome(document, figures, options)


def sessions(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `sessions <day>` (command-line.md › Commands, › JSON documents): the
    sessions of the local day with the parts that the split rule gives to each project
    and work item of a session, with the report record. The command is a report: it
    takes the report parameters of its options over the person configuration, and its
    warnings and configuration errors go to the standard error before the table."""
    _, person, store = context.require_setup(options.store)
    local = days.LocalDays(person.time_zones, person.day_starts)
    day = _day(local, options.day, context.now)
    figures, parameters = _figures(context, options, person, store, day, day)
    document = {
        **reports.sessions_document(day, _sessions_of(figures, local, day)),
        "record": _record(context, parameters, person, figures),
    }
    return _outcome(document, figures, options)


def frozen_list(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `frozen list` (command-line.md › Frozen reports, › JSON documents):
    one row for each frozen report of the store, with the warnings of the machine labels.
    No figure is computed and no lock is taken; a file that the ledger cannot read stops
    the command."""
    _, _, store = context.require_setup(options.store)
    rows, warnings = reports.frozen_list(store)
    document = {"frozen": rows}
    if not options.json:
        print(reports.render(document, options.language))
    return Outcome(document, warnings, [], False)


def frozen_show(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `frozen show <id>` (command-line.md › Frozen reports, › JSON
    documents): the frozen report as its document kept at the freeze, with the record of
    that moment, and its differences against the report of now — the same action over
    the days of the frozen document, with the report parameters, the rules, and the dated
    facts of now, which `frozen show` has no option to change. One pair: the document of
    now is compared with the one frozen report, whatever other frozen reports hold its
    days. As a report, the warnings and the configuration errors of the figures of now go
    to the standard error before the text. The document comes from the reader of the
    frozen reports, which gives a document of a command of `reports.FROZEN_ACTIONS` only
    when it holds at least one day, so `frozen show` keeps no guard of its own. An
    identifier that the store does not hold stops with the target named; a frozen report
    of a command that this version does not know stops with it named. No lock is taken."""
    _, person, store = context.require_setup(options.store)
    frozen = _frozen_document(store, options.id)
    action = frozen["command"]
    if action not in reports.FROZEN_ACTIONS:
        raise FrozenActionUnknown(options.id, action)
    held = reports.report_days(frozen)
    figures, parameters = _figures(context, options, person, store, min(held), max(held))
    document_of = _timesheet_document if action == "report timesheet" else _day_document
    now = {**document_of(figures), "record": _record(context, parameters, person, figures)}
    figure_rows, changed = reports.differences(frozen, now)
    document = {"frozen": frozen, "differences": figure_rows, "changed": changed}
    return _outcome(document, figures, options)


def frozen_remove(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `frozen remove <id>` (command-line.md › Frozen reports): the file of
    one frozen report, removed under the lock of the machine and the store after the
    guards of every action that writes. The file is found by its name and read never, so
    a file that the ledger cannot read as a frozen report is removed too. Only the
    machine that wrote the file removes it; an identifier that the store does not hold
    stops with the target named."""
    _, _, store = context.require_setup(options.store)
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        reports.remove_frozen_report(store, options.id, machine.machine)
    document = {"id": options.id}
    if not options.json:
        print(f"{label('id', options.language)}: {document['id']}")
    return Outcome(document, [], [], False)


def _day(local: days.LocalDays, value: str, now: datetime) -> date:
    """The local day of a day value of the command line, as the person typed it
    (command-line.md › Form): a date `YYYY-MM-DD`, or `today` and `yesterday`, the local
    days of the person at `now`, through the time-zone history and the day start hours
    (metrics.md › Days and weeks)."""
    return local.parse_day(value, now)


def _figures(
    context: Context,
    options: argparse.Namespace,
    person: PersonConfiguration,
    store: Path,
    first: date,
    last: date,
) -> tuple[Figures, ReportParameters]:
    """The figures of the local days from `first` to `last` and the report parameters
    they used: the options of the command line over the person configuration
    (configuration.md › Order), through the one pipeline of the figures."""
    parameters, _layers = resolve_parameters(report_options(options), person)
    return figures_of_days(context, store, person, parameters, first, last), parameters


def _report(
    context: Context,
    options: argparse.Namespace,
    person: PersonConfiguration,
    store: Path,
    first: date,
    last: date,
    document_of: Callable[[Figures], dict],
) -> Outcome:
    """The outcome of `report timesheet` and of `report day`: the document that
    `document_of` builds from the figures of the days, with the report record; then the
    differences against the frozen reports that the store holds (command-line.md › JSON
    documents, › Frozen reports); with `--freeze`, the JSON document of the report is
    kept as a frozen report first — so its differences are never against the file it is
    writing — and the document gains the identifier of the freeze."""
    figures, parameters = _figures(context, options, person, store, first, last)
    document = {**document_of(figures), "record": _record(context, parameters, person,
                                                          figures)}
    differences = _frozen_differences(
        store, options.action, [one.timesheet.day for one in figures.days], document)
    if getattr(options, "freeze", False):
        kept = Outcome(document, report_warnings(figures),
                       figures.attribution.configuration_errors, False)
        document["frozen_id"] = _freeze(context, options, store, kept)
    return _outcome({**document, **differences}, figures, options)


def _freeze(context: Context, options: argparse.Namespace, store: Path,
            kept: Outcome) -> str:
    """Keep the JSON document of the report as a frozen report of the machine
    (command-line.md › Frozen reports) and give the identifier of the freeze. The guards
    of every action that writes come first, then the lock of the machine and the store
    around the write of the file, and the machine identifier is read again after the
    guard; nothing reaches a stream before the file is written, so a stop of the guard
    leaves no line."""
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        return reports.freeze(store, machine.machine,
                              json_document(kept, options.action, options.language),
                              getattr(options, "note", None), context.now,
                              context.new_uid)


def _record(
    context: Context,
    parameters: ReportParameters,
    person: PersonConfiguration,
    figures: Figures,
) -> dict:
    """The report record of the figures of a report (architecture.md › Report record)."""
    return reports.report_record(parameters, person, figures.selection,
                                 figures.attribution.configuration_errors,
                                 context.version, days.tzdata_version())


def _timesheet_document(figures: Figures) -> dict:
    """The document of `report timesheet`, from the figures of the days of the period."""
    return reports.timesheet_document(figures.days, report_names(figures))


def _day_document(figures: Figures) -> dict:
    """The document of `report day`, from the figures of its day."""
    return reports.day_document(figures.days[0], report_names(figures))


def _frozen_document(store: Path, frozen_id: str) -> dict:
    """The document of the frozen report with the identifier, as the reader of the frozen
    reports gives it (command-line.md › Frozen reports); an identifier that no file names
    stops with the target that is not found."""
    for _, held_id, envelope in reports.read_frozen(store):
        if held_id == frozen_id:
            return envelope["document"]
    raise TargetNotFound(frozen_id)


def _frozen_differences(
    store: Path,
    action: str,
    days_of_report: Sequence[date],
    document: dict,
) -> dict:
    """The `differences` and `changed` of a report of now against the frozen reports of
    the store (command-line.md › Frozen reports, › JSON documents), or no key when no
    frozen report holds a day of the report.

    Each day compares with the latest frozen report that holds it. Because `differences`
    works on one pair of documents, a frozen report that is the latest for at least one
    day gives the figure rows of exactly those days — the document of now is narrowed to
    the days the pair wins — and the `changed` rows between its record and the record of
    now. A frozen report whose `command` is not `action`, the action of now, keeps only
    the figure rows that hold both values: a figure that one document alone holds is the
    shape of its command and no difference, while `changed` compares always, because the
    record has one shape. The pairs follow the order of the first day of the report that
    each one wins; the rows of `changed` merge in the order of their first appearance, an
    identical row once.
    """
    latest = reports.latest_frozen_by_day(
        [envelope for _, _, envelope in reports.read_frozen(store)])
    pairs: dict[int, tuple[dict, set[str]]] = {}
    for day in days_of_report:
        frozen = latest.get(day.isoformat())
        if frozen is not None:
            pairs.setdefault(id(frozen), (frozen, set()))[1].add(day.isoformat())
    if not pairs:
        return {}
    figure_rows: list[dict] = []
    changed: list[dict] = []
    for frozen, won in pairs.values():
        rows, changes = reports.differences(frozen, _only_days(document, won))
        if frozen.get("command") != action:
            rows = [row for row in rows if "frozen" in row and "now" in row]
        figure_rows.extend(rows)
        changed.extend(row for row in changes if row not in changed)
    return {"differences": figure_rows, "changed": changed}


def _only_days(document: dict, days: set[str]) -> dict:
    """The document of a period with only the days that one frozen report wins; the
    document of one day already holds one day."""
    if "days" not in document:
        return document
    return {**document, "days": [day for day in document["days"] if day["day"] in days]}


def _sessions_of(figures: Figures, local: days.LocalDays, day: date) -> list[dict]:
    """The sessions of the local day (command-line.md › Commands, › JSON documents): the
    ones with at least one event in a part of the day, in the order of the start of
    their first event in the day, then of the agent tool and of the identifier as text.
    Each session starts at its first event of the day and ends at its last, two events
    at the same instant in the order of their event keys, and takes the folder and the
    branch of that last event — a field that the event does not hold is not written. Its
    parts are those that the split rule and the agent time give it inside the day, in the
    order in which the timesheet of the day shows its entries; a session with an event in
    the day and no part holds none."""
    parts = local.day_parts(day)
    grouped: dict[tuple[str, str], list[Event]] = {}
    for event in figures.selection.session_events:
        if any(start <= parse_instant(event["timestamp"]) < end for start, end in parts):
            grouped.setdefault((event["tool"], event["session_id"]), []).append(event)
    times = figures.attribution.session_parts(_window(parts))
    names = report_names(figures)
    sessions = []
    for (tool, session_id), events in grouped.items():
        events.sort(key=lambda event: (event["timestamp"], event_order(event)))
        held: dict = {"session_id": session_id, "tool": tool,
                      "start": events[0]["timestamp"], "end": events[-1]["timestamp"]}
        for key in ("cwd", "branch"):
            if key in events[-1]:
                held[key] = events[-1][key]
        held["parts"] = _parts_of(times.get((tool, session_id), {}), names)
        sessions.append(held)
    sessions.sort(key=lambda held: (held["start"], held["tool"], held["session_id"]))
    return sessions


def _parts_of(held: dict[Bucket, tuple[int, int]], names: reports.Names) -> list[dict]:
    """The parts of one session (command-line.md › JSON documents): one for each project
    and work item that holds human time or agent time of the session in the day, with
    the objects that the reports show for them — null for the unattributed time and for
    no work item — and the two durations in whole seconds, in the order of the entries
    of the timesheet of the day."""
    measured = {bucket: milliseconds[0] for bucket, milliseconds in held.items()}
    parts = []
    for bucket in sorted(held, key=lambda one: bucket_order(one, measured)):
        project, work_item = bucket
        parts.append({
            "project": None if project is None else {
                "id": project, "name": names.projects[project]},
            "work_item": None if work_item is None else {
                "id": work_item, "name": names.work_items[(project, work_item)]},
            "human_time": _seconds(held[bucket][0]),
            "agent_time": _seconds(held[bucket][1]),
        })
    return parts


def _outcome(document: dict, figures: Figures, options: argparse.Namespace) -> Outcome:
    """The outcome of a report command. In text mode the action writes its warning and
    configuration-error lines to the standard error itself, before its text, through the
    one function of the output module, and the outcome says that it wrote them, so `emit`
    writes none of them again; the lists stay in the outcome. In JSON mode `emit` writes
    the lines and the envelope carries them (command-line.md › Output).
    """
    warnings = report_warnings(figures)
    errors = figures.attribution.configuration_errors
    if not options.json:
        write_lines(warnings, errors, options.language, sys.stderr)
        print(reports.render(document, options.language))
    return Outcome(document, warnings, errors, False, not options.json)
