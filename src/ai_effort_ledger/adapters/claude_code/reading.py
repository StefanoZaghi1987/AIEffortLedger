"""The reading of the files of a session: each line of a file is one JSON record with its line
number, a last line without a line break waits for the settle time, and the lines of a file
that give no record warn, the first 10 by name and one warning with the count of all of them;
the records of a session become the complete events that their rows give
(claude-code-adapter.md › Native logs, › Records and events, › Complete events;
ingestion.md › Adapters)."""

import json
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple

from ...events import Event
from .completeness import complete_events
from .discovery import SessionFiles
from .forks import assign_forks
from .mapping import SessionRecord, map_session
from .subagents import deduplicate, link_subagents
from .tables import RECORD_TYPES

_NAMED_INVALID_RECORDS = 10
"""The lines of one file that give no record and name their line; the lines after them stay in
one warning that counts all the lines of the file that give no record."""


class ReadContext(NamedTuple):
    """What the reading of the sessions needs from the ingestion: the machine that reads, the
    instant of the reading, the settle time of the person, and the lookup that names the
    session that holds a native identifier already in the store."""

    machine: str
    now: datetime
    settle_time: int
    native_id_owner: Callable[[str, str], tuple[str, str] | None]


class ReadResult(NamedTuple):
    """What the reading of the sessions gives: the complete events, the pairs of agent tool
    and session whose events stay held back, the warnings, and the tool names that no category
    of the adapter lists."""

    events: list[Event]
    held_back: set[tuple[str, str]]
    warnings: list[dict]
    unknown_tools: set[str]


def read_file(
    path: Path, settled: bool
) -> tuple[list[tuple[int, dict]], bool, list[dict]]:
    """Read the lines of one file of a native log: the records with their line number, whether
    a last line without a line break stayed unread, and the warnings.

    The bytes are read line by line and each line is decoded on its own, so a line whose bytes
    are not valid UTF-8 is a record that is not valid JSON, with the same warning and no event.
    The first 10 lines of the file that give no record name their line; one summary warning
    names the count of all the lines of the file that give no record.
    A last line without a line break is not read while the file is not settled, because the
    agent tool is still writing it, and is read like any other line when it is settled.
    A file that is gone at the reading is a file the agent tool deleted after the selection
    named the session: it gives no record, no unread line, and one warning that names it.
    """
    try:
        data = path.read_bytes()
    except OSError:
        return [], False, [{"code": "native_log_gone", "values": {"file": str(path)}}]
    records: list[tuple[int, dict]] = []
    warnings: list[dict] = []
    unread = False
    if not data:
        return records, unread, warnings
    *complete, last = data.split(b"\n")
    if last:
        if settled:
            complete.append(last)
        else:
            unread = True
    seen: set[tuple[str, str]] = set()
    invalid = 0
    for number, raw in enumerate(complete, start=1):
        try:
            record: Any = json.loads(raw.decode("utf-8"))
        except ValueError:
            record = None
        if not isinstance(record, dict):
            invalid += 1
            if invalid <= _NAMED_INVALID_RECORDS:
                warnings.append(
                    {"code": "invalid_record", "values": {"file": str(path), "line": number}})
            continue
        records.append((number, record))
        _warn_unknown_type(record, seen, warnings)
    if invalid > _NAMED_INVALID_RECORDS:
        warnings.append({"code": "invalid_records_summary",
                         "values": {"file": str(path), "count": invalid}})
    return records, unread, warnings


def read_sessions(sessions: Sequence[SessionFiles], context: ReadContext) -> ReadResult:
    """Read every file of the given sessions and map their records to the events that no later
    record of the session can change.

    The files of a session are read together, the file of the main agent first and then the
    files of the subagents by name, because a record that two files hold gives one event, from
    the copy in the file of the agent that its `agentId` names. A session is settled when none
    of its files changed for the settle time; only a settled session reads its last line
    without a line break, and every event of a settled session is complete. A session that
    holds an event back, or whose last line stayed unread, names itself in the held-back
    sessions of the result, so that the next ingestion reads it again although its files did
    not change. One warning names each record type and format version that the adapter does
    not know, in any file of any session of the reading; an entrypoint value or a tool
    name that the adapter does not know warns when a record that carries it reaches the
    mapping — a record without a valid instant, or a meta record, skips first. A
    record whose message is not an object, or a record of a type that gives events whose
    `timestamp` is absent or is not an instant with an offset, warns like a line that is not
    valid JSON, with the file that the reading names. A file of a session that is gone at
    the reading — the agent tool deleted it after the selection named the session — gives
    no event, no unread line, and one warning that names the file. Two sessions of the
    reading that name the same agent tool and the same session identifier, one per recorded
    folder, give the events of the folder that the list of the sessions names first alone:
    the reading of the later session is skipped, with one warning that names both folders
    and the session, and the later session names itself in no held-back sessions. The
    events that two sessions of the reading share move to the original of their pair, and
    the events that stay in a forked session name the session and the instant that its
    history was copied from.
    """
    events: list[Event] = []
    warnings: list[dict] = []
    unknown_tools: set[str] = set()
    held_back: set[tuple[str, str]] = set()
    seen: set[tuple[str, str]] = set()
    read: dict[tuple[str, str], list[Event]] = {}
    first_of: dict[tuple[str, str], SessionFiles] = {}
    for session in sessions:
        key = (session.tool, session.session_id)
        first = first_of.get(key)
        if first is not None:
            warnings.append({
                "code": "ambiguous_session_folder",
                "values": {"session_id": session.session_id,
                           "first": str(first.folder), "second": str(session.folder)}})
            continue
        first_of[key] = session
        settled = _is_settled(session, context)
        files = _files_of(session)
        rows: list[SessionRecord] = []
        unread = False
        for order, (agent, path) in enumerate(files):
            records, line_unread, file_warnings = read_file(path, settled)
            unread = unread or line_unread
            rows.extend(
                SessionRecord(agent, order, number, record) for number, record in records)
            for warning in file_warnings:
                _add_warning(warning, seen, warnings)
        rows, copy_warnings = deduplicate(rows)
        session_events, session_warnings = map_session(rows, session.tool, context.machine)
        link_subagents(session_events, rows)
        session_events, held = complete_events(session_events, rows, settled)
        read[key] = session_events
        if held or unread:
            held_back.add(key)
        for warning in copy_warnings:
            _add_warning(warning, seen, warnings)
        for warning in session_warnings:
            if warning["code"] == "invalid_record":
                _name_file(warning, files)
            _add_warning(warning, seen, warnings)
            if warning["code"] == "unknown_tool_name":
                unknown_tools.add(warning["values"]["tool"])
    for warning in assign_forks(read, context.native_id_owner):
        _add_warning(warning, seen, warnings)
    for session_events in read.values():
        events.extend(session_events)
    return ReadResult(events, held_back, warnings, unknown_tools)


def _name_file(warning: dict, files: Sequence[tuple[str, Path]]) -> None:
    """Name the file in an `invalid_record` warning of the mapping: the mapping knows only the
    order of the file among the files of the session, the reading knows its path."""
    file = warning["values"].get("file")
    if isinstance(file, int) and 0 <= file < len(files):
        _, path = files[file]
        warning["values"]["file"] = str(path)


def _add_warning(warning: dict, seen: set[tuple[str, str]], warnings: list[dict]) -> None:
    """Append the warning unless a warning of the same value came before it."""
    key = _warning_key(warning)
    if key is not None:
        if key in seen:
            return
        seen.add(key)
    warnings.append(warning)


def _warn_unknown_type(
    record: dict, seen: set[tuple[str, str]], warnings: list[dict]
) -> None:
    """One warning for each record type and format version that the adapter does not know."""
    kind = record.get("type", "")
    version = record.get("version", "")
    key = (str(kind), str(version))
    if (isinstance(kind, str) and kind in RECORD_TYPES) or key in seen:
        return
    seen.add(key)
    warnings.append({
        "code": "unknown_record_type",
        "values": {"type": str(kind), "version": str(version)},
    })


def _warning_key(warning: dict) -> tuple[str, str] | None:
    """The value that one warning of the adapter names, when warnings of the same value stay to
    one: the record type and format version, the entrypoint value, or the tool name. A warning
    with no value, such as one about a permission on several results, stays to none."""
    code = warning["code"]
    values = warning.get("values", {})
    if code == "unknown_record_type":
        return code, f"{values['type']}|{values['version']}"
    if code == "unknown_entrypoint":
        return code, str(values["value"])
    if code == "unknown_tool_name":
        return code, str(values["tool"])
    return None


def _files_of(session: SessionFiles) -> list[tuple[str, Path]]:
    """The files of a session with the agent whose file each is: the file of the main agent,
    then the files of the subagents by name."""
    files = [("", session.main)] if session.main else []
    files.extend((name, session.subagents[name]) for name in sorted(session.subagents))
    return files


def _is_settled(session: SessionFiles, context: ReadContext) -> bool:
    """Whether no file of the session changed for the settle time: the newest time of change
    of its files is at least that far in the past. A file that is gone has no time of change
    and stays out, so a session whose files are all gone is settled."""
    moments = []
    for _, path in _files_of(session):
        try:
            changed = path.stat().st_mtime
        except OSError:
            continue
        moments.append(datetime.fromtimestamp(changed, timezone.utc))
    if not moments:
        return True
    return (context.now - max(moments)).total_seconds() >= context.settle_time
