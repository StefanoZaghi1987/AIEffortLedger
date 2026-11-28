"""The actions of the declared events: `annotate`, `entry add`, `entries`, `retract`,
`timesheet confirm`, and `timesheet retract`, and the action of `purge`, which removes
events from the store (command-line.md › Commands, › JSON documents, › Timesheet, ›
Purge). Every action that writes calls `before_write` first and holds the lock of the
machine and the store while it reads its target and appends the event; `entries` reads
the index alone and takes no lock, and `purge` asks the person before it takes it."""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .. import days
from ..configuration import (
    MachineConfiguration,
    PersonConfiguration,
    WrongValue,
    parse_duration,
    resolve_parameters,
)
from ..declared import (
    UNATTRIBUTED,
    Bucket,
    DayFigures,
    bucket_order,
    latest_confirmation,
    proposal,
)
from ..events import Event, EventKey, event_key, event_order, format_instant, ledger_event
from ..index import LocalIndex
from ..ingestion.run import INDEX_FILE, LOCK_FILE, remove_blocked_copies
from ..language import label
from ..platform import StoreLock
from ..reports import entries_document, render, timesheet_day_document
from ..selection import cancelled
from ..setup import YES_ANSWERS
from ..store import PurgeSet, TargetNotFound, append_events, machine_labels
from . import Context, ask_by_key, inside_folder, machine_configuration
from .arguments import ConflictingArguments, MissingArgument
from .figures import (
    figures_after_confirmation,
    figures_of_days,
    proposed_values,
    report_names,
    report_options,
    report_warnings,
)
from .output import Outcome, write_lines

RETRACTABLE_KINDS = frozenset(
    {"manual_entry", "annotation", "timesheet_confirmation", "retraction"})
"""The kinds of the events that `retract` acts on (command-line.md › Commands); the
`event_uid` of an event of another kind stops the command with `wrong_kind`."""

LISTED_KINDS = frozenset({"manual_entry", "annotation", "retraction"})
"""The kinds that `entries` lists among the events whose timestamp is in the day; a purge
is not listed (command-line.md › Commands)."""


class AmbiguousSession(Exception):
    """The stop error of a session identifier that two agent tools hold, which `annotate
    --session` names with `--tool` to write (command-line.md › Commands).

    A stop error carries a code, values, and an exit code; the output language holds the
    text.
    """

    def __init__(self, session_id: str, tools: list[str]) -> None:
        self.code = "ambiguous_session"
        self.values = {"session_id": session_id, "tools": tools}
        self.exit_code = 1
        super().__init__(f"{session_id}: {', '.join(tools)}")


class AmbiguousName(Exception):
    """The stop error of a name of a project or of a work item that two entries of the
    person configuration give, which the person names by one of its identifiers instead
    (command-line.md › Exit codes): the option that gave the name, the name, and the
    identifiers, sorted.

    A stop error carries a code, values, and an exit code; the output language holds the
    text.
    """

    def __init__(self, option: str, name: str, identifiers: list[str]) -> None:
        self.code = "ambiguous_name"
        self.values = {"option": option, "name": name, "identifiers": identifiers}
        self.exit_code = 1
        super().__init__(f"{option} {name}: {', '.join(identifiers)}")


class WrongKind(Exception):
    """The stop error of an event of a kind that the command cannot act on
    (command-line.md › Exit codes): an `event_uid` of `retract` whose event is of a kind
    that it does not retract, and a `--key` of `purge` whose event is a purge.

    A stop error carries a code, values, and an exit code; the output language holds the
    text.
    """

    def __init__(self, action_name: str, event_uid: str, kind: str) -> None:
        self.code = "wrong_kind"
        self.values = {"command": action_name, "event_uid": event_uid, "kind": kind}
        self.exit_code = 2
        super().__init__(f"{action_name}: {event_uid}: {kind}")


class DayAfterToday(Exception):
    """The stop error of a day that is after the day of the run, which `timesheet
    confirm` refuses (command-line.md › Timesheet).

    A stop error carries a code, values, and an exit code; the output language holds the
    text.
    """

    def __init__(self, day: str) -> None:
        self.code = "day_after_today"
        self.values = {"day": day}
        self.exit_code = 1
        super().__init__(day)


def annotate(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `annotate`: one annotation of a session or of an interval, with at
    least one of `--project` and `--work-item` (command-line.md › Commands). A work item
    without `--project` keeps the project that attribution gives to the event
    (metrics.md › Attribution), so the annotation holds no project then."""
    _, person, store = context.require_setup(options.store)
    project = _project(getattr(options, "project", None), "--project", person)
    work_item = _work_item(getattr(options, "work_item", None), project, "--work-item",
                           person)
    if project is None and work_item is None:  # an annotation that gives neither
        raise MissingArgument(options.action, ["--project | --work-item"])
    _check_shape(options)
    if getattr(options, "session", None) is None:  # the interval form of the command
        _check_interval(days.LocalDays(person.time_zones, person.day_starts), options)
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        fields = _annotation_fields(person, store, inside, options, project, work_item)
        event = ledger_event("annotation", "human", machine.machine, context.now, fields,
                             new_uid=context.new_uid, version=context.version)
        append_events(store, machine.machine, [event], context.now)
        _update_index(inside, store)
    return _outcome(event, options)


def entry_add(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `entry add`: one manual entry between two instants, in the mode that
    `--mode` names; without `--project`, or with `--project -`, the entry declares the
    unattributed time, which has no work item (command-line.md › Commands)."""
    _, person, store = context.require_setup(options.store)
    project = _project(getattr(options, "project", None), "--project", person)
    work_item = _work_item(getattr(options, "work_item", None), project, "--work-item",
                           person)
    if work_item is not None and project is None:  # the unattributed time has none
        raise MissingArgument(options.action, ["--project"])
    local = days.LocalDays(person.time_zones, person.day_starts)
    _check_interval(local, options)
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    fields = {
        "start": format_instant(_instant(local, getattr(options, "from"))),
        "end": format_instant(_instant(local, options.to)),
        "manual_mode": options.mode,
    }
    if project is not None:
        fields["project"] = project
    if work_item is not None:
        fields["work_item"] = work_item
    if getattr(options, "note", None) is not None:
        fields["note"] = options.note
    with StoreLock(inside / LOCK_FILE):
        event = ledger_event("manual_entry", "human", machine.machine, context.now,
                             fields, new_uid=context.new_uid, version=context.version)
        append_events(store, machine.machine, [event], context.now)
        _update_index(inside, store)
    return _outcome(event, options)


def entries(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `entries`: the manual entries, annotations, and retractions whose
    timestamp is in the local day, and the timesheet confirmations whose day is the day,
    with their `event_uid` (command-line.md › Commands). A purge is not listed. The text
    shows the machine of an event by the machine label that the store holds for it, and by
    its identifier when it holds none; the document keeps the identifier. The labels are
    read in both modes, so the text and the document carry the same warnings."""
    _, person, store = context.require_setup(options.store)
    local = days.LocalDays(person.time_zones, person.day_starts)
    day = local.parse_day(options.day, context.now)
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    index = LocalIndex(inside / INDEX_FILE)
    try:
        index.update(store)
        purges = PurgeSet.from_events(index.purge_events())
        held = [event for event
                in index.ledger_events_between(local.day_parts(day), purges=purges)
                if event["kind"] in LISTED_KINDS]
        held.extend(index.confirmations_of([day.isoformat()], purges=purges))
    finally:
        index.close()
    held.sort(key=lambda event: (event["timestamp"], event_order(event)))
    document = entries_document(day, held)
    labels, warnings = machine_labels(store, [event["machine"] for event in held])
    if not options.json:
        print(render(document, options.language, machine_labels=labels))
    return Outcome(document, warnings, [], False)


def retract(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `retract`: one retraction of a manual entry, an annotation, a
    timesheet confirmation, or a retraction, by the `event_uid` that `entries` shows; a
    retraction of a retraction brings the event back (command-line.md › Commands). An
    `event_uid` that the store does not hold names the target and stops; one of another
    kind, such as a purge, stops with `wrong_kind`."""
    _, _, store = context.require_setup(options.store)
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        index = LocalIndex(inside / INDEX_FILE)
        try:
            index.update(store)
            purges = PurgeSet.from_events(index.purge_events())
            target = index.ledger_event_by_uid(options.event_uid, purges=purges)
            if target is None:
                raise TargetNotFound(options.event_uid)
            kind = target["kind"]
            if kind not in RETRACTABLE_KINDS:
                raise WrongKind(options.action, options.event_uid, kind)
            event = ledger_event("retraction", "human", machine.machine, context.now,
                                 {"retracts": event_key(target).to_json()},
                                 new_uid=context.new_uid, version=context.version)
            append_events(store, machine.machine, [event], context.now)
            index.update(store)
        finally:
            index.close()
    return _outcome(event, options)


def timesheet_confirm(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `timesheet confirm`: one timesheet confirmation of the day, with
    all the entries of the day, which confirms the proposal that `timesheet <day>`
    shows, or the entries of a declared day (command-line.md › Timesheet). Without
    `--total` and `--set`, the command confirms those values as they are; `--set` gives
    the value of one entry, and `--total` gives the total human time of the day, which
    divides among the entries that `--set` does not give. A day after the day of the
    run, and values of `--set` that are more than `--total`, stop the command. The
    command names, in `replaces`, the latest confirmation of the day that the machine
    has, and holds the lock of the machine and the store while it reads the day through
    the figures and appends the event; the held-back events of the day keep no figure
    incomplete, because its entries are the declaration of the person. It shows the
    identifier of the confirmation and the entries of the day as `timesheet <day>` shows
    them once the confirmation is written, through the same document and the same
    proposed values, and writes its warning lines before them (command-line.md › JSON
    documents, › Reports)."""
    _, person, store = context.require_setup(options.store)
    options.held_back_is_incomplete = False
    local = days.LocalDays(person.time_zones, person.day_starts)
    day = local.parse_day(options.day, context.now)
    if day > local.local_day(context.now):
        raise DayAfterToday(day.isoformat())
    given = _given(options, person)
    parameters, _layers = resolve_parameters(report_options(options), person)
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        figures = figures_of_days(context, store, person, parameters, day, day)
        total = getattr(options, "total", None)
        if total is not None:  # the reader of the parser has checked the format
            total = parse_duration(total, clock=True)
        confirmed = _confirmed(figures.days[0], total, given,
                               parameters.timesheet_granularity)
        replaced = latest_confirmation(
            [one for one in figures.selection.confirmations
             if one.get("day") == day.isoformat()], set()).latest
        fields: dict = {"day": day.isoformat(),
                        "entries": _event_entries(confirmed, options)}
        if replaced is not None:
            fields["replaces"] = event_key(replaced).to_json()
        event = ledger_event("timesheet_confirmation", "human", machine.machine,
                             context.now, fields, new_uid=context.new_uid,
                             version=context.version)
        append_events(store, machine.machine, [event], context.now)
        _update_index(inside, store)
    after = figures_after_confirmation(figures, day, event, person, parameters)
    shown = timesheet_day_document(
        after, proposed_values(after, parameters.timesheet_granularity),
        report_names(figures, person, [event]))
    document = {"event_uid": event["event_uid"], "entries": shown["entries"]}
    warnings = report_warnings(figures, [after])
    errors = figures.attribution.configuration_errors
    if not options.json:  # the lines before the table, as `timesheet <day>` writes them
        write_lines(warnings, errors, options.language, sys.stderr)
        print(render(document, options.language))
    return Outcome(document, warnings, errors, False, not options.json)


def timesheet_retract(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `timesheet retract`: one retraction of the latest timesheet
    confirmation of the day, which brings back the one before it (command-line.md ›
    Commands, › Timesheet). A day whose confirmations the store does not hold, also
    because its latest confirmation is retracted already, names the day and stops. The
    command holds the lock of the machine and the store while it reads the
    confirmations of the day and appends the retraction."""
    _, person, store = context.require_setup(options.store)
    local = days.LocalDays(person.time_zones, person.day_starts)
    day = local.parse_day(options.day, context.now)
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        index = LocalIndex(inside / INDEX_FILE)
        try:
            index.update(store)
            purges = PurgeSet.from_events(index.purge_events())
            confirmations = index.confirmations_of([day.isoformat()], purges=purges)
            retractions = [one for one in index.bookkeeping(purges=purges)
                           if one["kind"] == "retraction"]
            latest = latest_confirmation(confirmations, cancelled(retractions)).latest
            if latest is None:
                raise TargetNotFound(day.isoformat())
            event = ledger_event("retraction", "human", machine.machine, context.now,
                                 {"retracts": event_key(latest).to_json()},
                                 new_uid=context.new_uid, version=context.version)
            append_events(store, machine.machine, [event], context.now)
            index.update(store)
        finally:
            index.close()
    return _outcome(event, options)


def purge(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `purge`: the removal of the events of the keys that the `--key`
    values name, or of the keys of every kind but `purge` whose winning copy a writer
    version under `--writer-version-below` wrote, with its reason (command-line.md ›
    Purge). `--source` narrows a selection by writer version alone, so beside `--key` it
    stops the command with a wrong use. A selection by writer version that holds no key
    writes nothing and asks nobody: the command completes with the warning
    `no_key_selected`. The command refuses a selected key whose event is a purge, warns
    about the keys whose source no longer exists, and writes the purge only with `--yes`
    or the consent of the person: at a terminal the keys and the warnings reach the
    streams before the question, which is asked before the lock so that a scheduled
    ingestion takes the lock while the person answers; a corrected version names the
    sessions that hold the keys (ADR 0015), and after the write the copies that the
    purge blocks leave the segments of the machine, as step 10 of an ingestion does
    (ADR 0008)."""
    _, _, store = context.require_setup(options.store)
    corrected = getattr(options, "corrected_version", None)
    if corrected is not None and options.reason == "forget":  # ADR 0015
        raise ConflictingArguments(options.action, ["--reason forget", "--corrected-version"])
    by_key = _typed_keys(options)
    if by_key is not None and getattr(options, "source", None) is not None:
        raise ConflictingArguments(options.action, ["--key", "--source"])
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    index = LocalIndex(inside / INDEX_FILE)
    try:
        index.update(store)
        held_purges = index.purge_events()
        purges = PurgeSet.from_events(held_purges)
        keys = by_key if by_key is not None else index.keys_written_below(
            options.writer_version_below, getattr(options, "source", None),
            purges=purges)
        _refuse_purge_of_purge(options.action, keys, index, purges)
        if not keys:
            if not options.json:
                print(_purge_text(keys, False, options.language))
            return Outcome({"keys": [], "keys_without_source": [], "written": False},
                           [{"code": "no_key_selected", "values": {}}], [], False)
        without_source = _keys_without_source(keys, _held_sources(context, machine))
        sessions: set[tuple[str, str]] = set()
        if corrected is not None:
            sessions = index.sessions_of_keys(keys, purges=purges)
    finally:
        index.close()
    warnings = _source_gone_warnings(without_source)
    asking = not getattr(options, "yes", False) and context.ask is not None
    if asking:  # the person answers on what they see, before the question
        if not options.json:
            print(_keys_text(keys, options.language))
        write_lines(warnings, [], options.language, sys.stderr)
    written = _consents(context, options)
    if written:
        with StoreLock(inside / LOCK_FILE):
            fields: dict = {"purged_keys": [key.to_json() for key in keys],
                            "purge_reason": options.reason}
            if corrected is not None:
                fields["corrected_version"] = corrected
                fields["purged_sessions"] = [{"tool": tool, "session_id": session}
                                             for tool, session in sorted(sessions)]
            event = ledger_event("purge", "human", machine.machine, context.now, fields,
                                 new_uid=context.new_uid, version=context.version)
            append_events(store, machine.machine, [event], context.now)
            remove_blocked_copies(store, machine.machine,
                                  PurgeSet.from_events([*held_purges, event]))
            _update_index(inside, store)
    document = {"keys": [key.to_json() for key in keys],
                "keys_without_source": [key.to_json() for key in without_source],
                "written": written}
    if not options.json:
        if asking:  # the keys are on the terminal already
            print(_written_line(written, options.language))
        else:
            print(_purge_text(keys, written, options.language))
    return Outcome(document, warnings, [], False, asking)


def _outcome(event: Event, options: argparse.Namespace) -> Outcome:
    """The outcome of a command that wrote one event: its document holds the `event_uid`
    of the event that the command wrote (command-line.md › JSON documents)."""
    document = {"event_uid": event["event_uid"]}
    if not options.json:
        print(f"{label('event_uid', options.language)}: {document['event_uid']}")
    return Outcome(document, [], [], False)


def _check_shape(options: argparse.Namespace) -> None:
    """The about of `annotate`: a session alone, with `--tool` when two agent tools hold
    it, or an interval with both its ends (command-line.md › Commands). A session with an
    interval end, and an interval with `--tool`, stop with `ConflictingArguments`, and an
    interval without its end with `MissingArgument`; the parser stops a line without
    `--session` and without `--from`."""
    ends = [flag for flag, dest in (("--from", "from"), ("--to", "to"))
            if getattr(options, dest, None) is not None]
    if getattr(options, "session", None) is not None:
        if ends:
            raise ConflictingArguments(options.action, ["--session", *ends])
        return
    if getattr(options, "tool", None) is not None:
        raise ConflictingArguments(options.action, ["--tool", "--from"])
    if getattr(options, "to", None) is None:
        raise MissingArgument(options.action, ["--to"])


def _check_interval(local: days.LocalDays, options: argparse.Namespace) -> None:
    """The ends of an interval of `annotate` or of `entry add`: an interval whose start
    does not come before its end holds no time, so the command stops with a wrong value
    that names `--to` and the value, instead of writing an interval that the metrics
    would silently drop (command-line.md › Commands)."""
    if _instant(local, getattr(options, "from")) >= _instant(local, options.to):
        raise WrongValue("--to", options.to)


def _given(options: argparse.Namespace, person: PersonConfiguration) -> dict[Bucket, int]:
    """The entries that `--set` gives, each value read as `<project>=<duration>` or as
    `<project>#<work item identifier>=<duration>` (command-line.md › Form, › Timesheet):
    the parser holds the values as text, so the action checks their shape, and a value
    of another shape stops with a wrong value that names `--set` and the value. A project
    is its identifier, or its name when no identifier matches, and `-` is the unattributed
    time."""
    given: dict[Bucket, int] = {}
    for text in getattr(options, "set", None) or []:
        target, mark, seconds_text = text.rpartition("=")
        if not mark or not target:
            raise WrongValue("--set", text)
        try:
            seconds = parse_duration(seconds_text, clock=True)
        except ValueError:
            raise WrongValue("--set", text) from None
        given[_bucket(target, text, person)] = seconds
    return given


def _bucket(target: str, text: str, person: PersonConfiguration) -> Bucket:
    """The bucket of one target of `--set`: the project before `#`, and the work item
    after it when one is given (command-line.md › Form). The unattributed time takes no
    work item, and a work item without a project is a value of no shape; a name that two
    entries give stops with `AmbiguousName`, which names `--set`."""
    project_text, mark, work_item_text = target.partition("#")
    if project_text == "-":
        if mark:  # the unattributed time has no work item
            raise WrongValue("--set", text)
        return UNATTRIBUTED
    if mark and not project_text:
        raise WrongValue("--set", text)  # a work item without a project
    project = _project(project_text, "--set", person)
    work_item = _work_item(work_item_text, project, "--set", person) if mark else None
    return project, work_item


def _confirmed(
    figures: DayFigures,
    total: int | None,
    given: dict[Bucket, int],
    granularity: int,
) -> dict[Bucket, int]:
    """The entries that the command confirms, in whole seconds (command-line.md ›
    Timesheet): the values that the day shows — the proposal of a measured day, or the
    entries of a declared day — with the values of `--set` in the place of theirs; when
    `total` gives the total human time of the day, the rest of the total divides among
    the entries that `--set` does not give, by the shares of the measured human time
    with manual entries (metrics.md › Declared values). An entry of zero is left out of
    the confirmation."""
    if total is None:
        values = proposed_values(figures, granularity)
        values.update(given)
        return {bucket: value for bucket, value in values.items() if value}
    with_manual = {line.bucket: line.with_manual for line in figures.timesheet.lines}
    divided = proposal(with_manual, granularity, total, given)
    return {bucket: value for bucket, value in divided.items() if value}


def _event_entries(confirmed: dict[Bucket, int], options: argparse.Namespace) -> list[dict]:
    """The `entries` of the event, in the order of the entries of a day (event-schema.md
    › Fields): at most one for each project and work item, with `project` absent for the
    unattributed time, `work_item` only with a project, the `duration` in whole seconds,
    and the `note` that `--note` gives to every entry."""
    entries = []
    for bucket in sorted(confirmed, key=lambda held: bucket_order(held, confirmed)):
        entry: dict = {}
        if bucket[0] is not None:
            entry["project"] = bucket[0]
            if bucket[1] is not None:
                entry["work_item"] = bucket[1]
        entry["duration"] = confirmed[bucket]
        if getattr(options, "note", None) is not None:
            entry["note"] = options.note
        entries.append(entry)
    return entries


def _annotation_fields(
    person: PersonConfiguration,
    store: Path,
    inside: Path,
    options: argparse.Namespace,
    project: str | None,
    work_item: str | None,
) -> dict:
    """The fields of the annotation: `annotates` with the agent tool and the session
    that the store holds, or the `start` and the `end` of the interval; then the project
    and the work item, and the note (event-schema.md › Fields). A session that no agent
    tool holds stops with `target_not_found`; one that two agent tools hold stops with
    `ambiguous_session` unless `--tool` names one of them."""
    fields: dict = {}
    session = getattr(options, "session", None)
    if session is not None:
        index = LocalIndex(inside / INDEX_FILE)
        try:
            index.update(store)
            tools = index.tools_of_session(session,
                                           purges=PurgeSet.from_events(
                                               index.purge_events()))
        finally:
            index.close()
        if not tools:
            raise TargetNotFound(session)
        tool = getattr(options, "tool", None)
        if tool is not None:
            if tool not in tools:
                raise TargetNotFound(f"{tool} {session}")
        elif len(tools) > 1:
            raise AmbiguousSession(session, sorted(tools))
        else:
            tool = sorted(tools)[0]
        fields["annotates"] = {"tool": tool, "session_id": session}
    else:
        local = days.LocalDays(person.time_zones, person.day_starts)
        fields["start"] = format_instant(_instant(local, getattr(options, "from")))
        fields["end"] = format_instant(_instant(local, options.to))
    if project is not None:
        fields["project"] = project
    if work_item is not None:
        fields["work_item"] = work_item
    if getattr(options, "note", None) is not None:
        fields["note"] = options.note
    return fields


def _instant(local: days.LocalDays, value: str) -> datetime:
    """The instant of a `--from` or `--to` value of the command line (command-line.md ›
    Form): an instant with an offset or `Z` stays as it is, in UTC; a local time is the
    first instant whose local time reaches it in the zone that is valid there."""
    return local.local_instant(value)


def _project(
    value: str | None, option: str, person: PersonConfiguration,
) -> str | None:
    """The project identifier of a `--project` value (command-line.md › Form): `-` is the
    unattributed time and no identifier; an identifier of the person configuration stays
    as it is; when no identifier matches, the name of one entry gives its identifier; the
    name that two entries give stops with `AmbiguousName`, which names the option that
    gave the value, and a value that no entry holds stays as it is, for the reports to
    warn about."""
    if value is None or value == "-":
        return None
    if any(entry.id == value for entry in person.projects):
        return value
    named = sorted({entry.id for entry in person.projects if entry.name == value})
    if len(named) > 1:
        raise AmbiguousName(option, value, named)
    return named[0] if named else value


def _work_item(
    value: str | None, project: str | None, option: str, person: PersonConfiguration,
) -> str | None:
    """The work item identifier of a `--work-item` value (command-line.md › Form), among
    the work items of the project when one is given: an identifier stays as it is, the
    name of one entry gives its identifier, the name that two entries give stops with
    `AmbiguousName`, which names the option that gave the value, and a value that no
    entry holds stays as it is."""
    if value is None:
        return None
    held = [entry for entry in person.work_items
            if project is None or entry.project == project]
    if any(entry.id == value for entry in held):
        return value
    named = sorted({entry.id for entry in held if entry.name == value})
    if len(named) > 1:
        raise AmbiguousName(option, value, named)
    return named[0] if named else value


def _update_index(inside: Path, store: Path) -> None:
    """Bring the local index up to date with the store, as the ingestion does after it
    appends, so that the next command reads the event this one wrote."""
    index = LocalIndex(inside / INDEX_FILE)
    try:
        index.update(store)
    finally:
        index.close()


def _typed_keys(options: argparse.Namespace) -> list[EventKey] | None:
    """The keys that the `--key` values of the command line name, or None when the
    command selects by writer version (command-line.md › Purge)."""
    typed = getattr(options, "key", None)
    if typed is None:
        return None
    return [_key_of_value(value) for value in typed]


def _key_of_value(value: str) -> EventKey:
    """The key that one `--key` value names (command-line.md › Purge): the event key as
    its JSON object, or, for a key of the source `ledger`, its `event_uid` alone. Text
    that is not valid JSON where JSON is required, a JSON value that is no key object, a
    missing `source`, or an empty value stops with a wrong value that names the whole
    text the person typed."""
    text = value.strip()
    if not text:
        raise WrongValue("--key", value)
    try:
        parsed: object = json.loads(text)
    except ValueError:
        if text.startswith("{"):  # the object that the text began did not close
            raise WrongValue("--key", value) from None
        return EventKey("ledger", event_uid=text)
    if not isinstance(parsed, dict):
        raise WrongValue("--key", value)
    return _key_of_object(parsed, value)


def _key_of_object(parsed: dict, value: str) -> EventKey:
    """The key of one JSON object of `--key`, in one of the three shapes of the schema
    (event-schema.md › Keys and invariants): `source` with `native_id`; `source`,
    `session_id`, and `event_uid`; or, for the source `ledger`, `source` with
    `event_uid`. Every part that the object names is text, and an object of another
    shape stops with a wrong value; `EventKey.from_json` is never given an object
    without `source`."""
    unknown = set(parsed) - {"source", "native_id", "session_id", "event_uid"}
    source = parsed.get("source")
    native_id = parsed.get("native_id")
    session_id = parsed.get("session_id")
    event_uid = parsed.get("event_uid")
    if unknown or not _is_name(source):
        raise WrongValue("--key", value)
    if native_id is not None:
        if session_id is not None or event_uid is not None or not _is_name(native_id):
            raise WrongValue("--key", value)
        return EventKey(source, native_id=native_id)
    if not _is_name(event_uid):
        raise WrongValue("--key", value)
    if session_id is not None:
        if not _is_name(session_id):
            raise WrongValue("--key", value)
        return EventKey(source, session_id=session_id, event_uid=event_uid)
    if source == "ledger":
        return EventKey(source, event_uid=event_uid)
    raise WrongValue("--key", value)


def _is_name(value: object) -> bool:
    """Whether a value is the text of a part of an event key: a text that is not empty."""
    return isinstance(value, str) and bool(value)


def _refuse_purge_of_purge(
    action_name: str,
    keys: list[EventKey],
    index: LocalIndex,
    purges: PurgeSet,
) -> None:
    """The stop when a selected key names a purge, on every selection: a purge cannot be
    undone, because the copies that it removed do not come back, so no purge removes one
    (command-line.md › Purge)."""
    for key in keys:
        if key.source != "ledger" or key.event_uid is None:
            continue
        event = index.ledger_event_by_uid(key.event_uid, purges=purges)
        if event is not None and event["kind"] == "purge":
            raise WrongKind(action_name, key.event_uid, event["kind"])


def _keys_without_source(keys: list[EventKey], held: set[str]) -> list[EventKey]:
    """The keys whose source no longer exists (command-line.md › Purge)."""
    return [key for key in keys if key.source not in held]


def _held_sources(context: Context, machine: MachineConfiguration) -> set[str]:
    """The sources that exist: the source `ledger`, and the source of each adapter whose
    agent tools the machine configuration gives a folder of native logs for (event-
    schema.md › Keys and invariants)."""
    held = {"ledger"}
    for adapter in context.adapters:
        if any(machine.native_logs.get(tool) for tool in adapter.tools):
            held.add(adapter.source)
    return held


def _source_gone_warnings(without_source: list[EventKey]) -> list[dict]:
    """One warning for each source that a selected key names and that no folder of native
    logs feeds any more (command-line.md › JSON documents)."""
    return [{"code": "purged_key_source_gone", "values": {"source": source}}
            for source in sorted({key.source for key in without_source})]


def _consents(context: Context, options: argparse.Namespace) -> bool:
    """Whether the purge is written: with `--yes` it is; without a terminal on the
    standard input nobody is asked and it is not; otherwise the person decides, whose
    answer counts as consent in the two languages of the output; an empty answer, which an
    end of the input gives, is no consent (command-line.md › Output, › Purge)."""
    if getattr(options, "yes", False):
        return True
    ask = ask_by_key(context.ask, options.language)
    if ask is None:
        return False
    return ask("purge_consent").strip().lower() in YES_ANSWERS


def _keys_text(keys: list[EventKey], language: str) -> str:
    """The keys that the command removes, one on each line, each as its JSON object
    (command-line.md › Output)."""
    lines = [label("keys", language)]
    lines.extend(json.dumps(key.to_json(), ensure_ascii=False, sort_keys=True)
                 for key in keys)
    return "\n".join(lines)


def _written_line(written: bool, language: str) -> str:
    """The line that says whether the command wrote the purge (command-line.md ›
    Output)."""
    return f"{label('written', language)}: " \
           f"{label('yes' if written else 'no', language)}"


def _purge_text(keys: list[EventKey], written: bool, language: str) -> str:
    """The text of `purge` when nothing was written to the terminal yet: the keys that
    the command removes and whether the command wrote the purge (command-line.md ›
    Output)."""
    return "\n".join([_keys_text(keys, language), _written_line(written, language)])
