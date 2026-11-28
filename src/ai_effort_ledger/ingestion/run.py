"""The ingestion of all adapters into the store: the eleven steps of the data flow
(architecture.md › Data flow) — the lock of the machine and the store, the sessions that the
adapters read, the repository identity of the folders of the events, the append to the
segment of the machine, the record of the sources and of the sessions held back, the warning
for the lost events, and the copies that a purge blocks (ingestion.md › Store, › Frequency,
› Repository identity)."""

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from ..adapters import Adapter, ReadContext, Retention, SessionFiles
from ..configuration import MachineConfiguration, PersonConfiguration, pattern_matches
from ..events import (
    Event,
    decode_line,
    event_key,
    format_instant,
    version_key,
    writer_version,
)
from ..index import LocalIndex
from ..platform import StoreLock, store_identifier
from ..repository import RepositoryIdentity, RootCommits, resolve_folder
from ..store import (
    PurgeSet,
    SegmentLine,
    append_events,
    read_lines,
    rewrite_segment,
    segment_names,
)
from .state import (
    STORES_FOLDER,
    SourcesState,
    file_stamp,
    lost_events,
    sessions_to_read,
    sources_path,
)

DEVELOPMENT_VARIABLE = "AI_EFFORT_LEDGER_DEVELOPMENT"
"""The environment variable that lets a version with a development mark write to the store
(architecture.md › Runtime)."""

INDEX_FILE = "index.sqlite"
"""The name of the file of the local index of one store, below `stores/<store>` of the
machine-local data folder (architecture.md › Files of a machine)."""

LOCK_FILE = "lock"
"""The name of the file of the lock of the machine and one store, below `stores/<store>` of
the machine-local data folder (architecture.md › Files of a machine)."""

REPOSITORIES_FILE = "repositories.json"
"""The name of the file that keeps the root commit of each repository already read, in the
machine-local data folder (architecture.md › Files of a machine)."""


class DevelopmentVersion(Exception):
    """The stop error of a version with a development mark that the environment does not let
    write to the store (architecture.md › Runtime).

    A stop error carries a code, values, and an exit code; the output language holds the text.
    """

    def __init__(self) -> None:
        self.code = "development_version"
        self.values: dict[str, object] = {}
        self.exit_code = 1
        super().__init__("development_version")


class SourceResult(NamedTuple):
    """What one folder of native logs gave in one ingestion: the source that read it, the
    folder as the machine configuration names it, the number of new events it gave, and the
    number of its sessions whose events stay held back (command-line.md › Ingest)."""

    source: str
    folder: str
    new_events: int
    sessions_held_back: int


class IngestionResult(NamedTuple):
    """What one ingestion gives: one result per folder of native logs, in the order of the
    machine configuration, once however many agent tools of one adapter record the folder,
    and the warnings of the reading, of the tool names that no table lists, of a folder of
    native logs that the machine configuration records more than once for one adapter, of
    the repository identity, and of the lost events."""

    sources: list[SourceResult]
    warnings: list[dict]


def run_ingestion(
    machine: MachineConfiguration,
    machine_folder: Path,
    store_folder: Path,
    person: PersonConfiguration,
    adapters: Sequence[Adapter],
    now: datetime,
    home: Path,
    system: str,
    environ: Mapping[str, str],
    version: str | None = None,
) -> IngestionResult:
    """Run one ingestion of every adapter into the store, in the order of the eleven steps of
    the data flow (architecture.md › Data flow), under the lock of the machine and the store,
    and give one result per folder of native logs with the warnings.

    The `version`, or the version of the ledger when None, is the writer version of every new
    event, the version that decides which purges with a corrected version the machine applies,
    and the version of the development check: a version with a development mark writes only
    when `environ` gives `AI_EFFORT_LEDGER_DEVELOPMENT` as `1`, which stops before the lock.
    The `version` must be a valid writer version: any other text is no stop error of the
    ledger and raises `ValueError` at the version order of the purges.
    """
    writer = writer_version() if version is None else version
    if is_development(writer) and environ.get(DEVELOPMENT_VARIABLE) != "1":
        raise DevelopmentVersion()
    inside = machine_folder / STORES_FOLDER / store_identifier(store_folder, system)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        index = LocalIndex(inside / INDEX_FILE)
        try:
            return _ingest(machine, machine_folder, store_folder, person, adapters,
                           now, home, system, environ, writer, index)
        finally:
            index.close()


def is_development(version: str) -> bool:
    """Whether the version carries a development mark, `.dev` and a whole number, at its end
    (architecture.md › Runtime): the rule of the development check of the ingestion, of the
    guard of every command that writes, and of the scheduled ingestion of the setup."""
    _, mark, number = version.rpartition(".dev")
    return bool(mark) and number.isdigit()


def _ingest(
    machine: MachineConfiguration,
    machine_folder: Path,
    store_folder: Path,
    person: PersonConfiguration,
    adapters: Sequence[Adapter],
    now: datetime,
    home: Path,
    system: str,
    environ: Mapping[str, str],
    writer: str,
    index: LocalIndex,
) -> IngestionResult:
    """The ingestion under the lock, from the update of the index (step 3) to the copies that
    a purge blocks (step 10); the caller releases the lock (step 11)."""
    state = SourcesState.load(sources_path(machine_folder, store_folder, system))
    index.update(store_folder)                                              # step 3
    purge_events = index.purge_events()
    purges = PurgeSet.from_events(purge_events)
    applied = set(state.applied_purges)
    purged_sessions = purges.sessions_to_read(writer, applied)              # step 4
    state.applied_purges.extend(_applies_now(purge_events, writer, applied))
    root_commits = RootCommits()
    root_commits.load(machine_folder / REPOSITORIES_FILE)
    warnings: list[dict] = []
    read: list[Event] = []
    held: set[tuple[str, str]] = set()
    unknown: set[str] = set()
    read_of_folder: dict[str, set[tuple[str, str]]] = {}
    sessions_read: list[SessionFiles] = []
    scanned: list[tuple[str, str, str]] = []
    for adapter in adapters:                                                # steps 4 and 5
        found: list[SessionFiles] = []
        folder_of: dict[tuple[str, str], str] = {}
        scanner: dict[str, str] = {}
        for tool in adapter.tools:
            for folder in machine.native_logs.get(tool, []):
                if folder in scanner:
                    warnings.append(_recorded_again(folder, scanner[folder], tool))
                    continue
                scanner[folder] = tool
                scanned.append((adapter.source, tool, folder))
                for session in adapter.sessions(tool, Path(folder)):
                    found.append(session)
                    folder_of[(session.tool, session.session_id)] = folder
        selected = sessions_to_read(state, found, purged_sessions)
        result = adapter.read_sessions(
            selected,
            ReadContext(machine.machine, now, person.settle_time,
                        lambda session, native: index.native_id_owner(
                            adapter.source, native, purges=purges)))
        read.extend(result.events)
        held |= result.held_back
        unknown |= result.unknown_tools
        warnings.extend(warning for warning in result.warnings
                        if warning["code"] != "unknown_tool_name")
        for session in selected:
            key = (session.tool, session.session_id)
            read_of_folder.setdefault(folder_of[key], set()).add(key)
        sessions_read.extend(selected)
    warnings.extend(_unknown_tools(unknown, person))
    resolved, named = _resolve_folders(read, home, system, person, root_commits)  # step 6
    if resolved:
        root_commits.save(machine_folder / REPOSITORIES_FILE)
    warnings.extend(named)
    for event in read:
        identity = resolved.get(event.get("cwd"))
        if identity is not None:
            event["repo_hint"] = identity.hint
            event["repo_basis"] = identity.basis
        event["writer_version"] = writer
    kept = [event for event in read                                          # step 7
            if not purges.blocks(event) and not index.has_key(event_key(event), purges)]
    if kept:
        append_events(store_folder, machine.machine, kept, now)              # step 8
    new_by_session = _new_by_session(kept)
    sources = [
        SourceResult(source, folder,
                     sum(new_by_session.get(key, 0) for key in read_of_folder.get(folder, ())),
                     sum(1 for key in read_of_folder.get(folder, ()) if key in held))
        for source, _, folder in scanned
    ]
    index.update(store_folder)                                               # step 9
    project_folders = _project_folders(read, sessions_read)
    retentions = {tool: adapter.retention(tool, environ, home, system, machine.native_logs,
                                          project_folders)
                  for adapter in adapters for tool in adapter.tools}
    for _, tool, folder in scanned:
        warning = lost_events(state, folder, retentions[tool], now)
        if warning is not None:
            warnings.append(warning)
        state.folders[folder] = format_instant(now)
    for session in sessions_read:
        for path in [session.main, *session.subagents.values()]:
            stamp = file_stamp(path)
            if stamp is not None:
                state.files[str(path)] = stamp
    state.held_back = _held_back_by_tool(held)
    state.save(sources_path(machine_folder, store_folder, system))
    remove_blocked_copies(store_folder, machine.machine, purges)             # step 10
    return IngestionResult(sources, warnings)


def _applies_now(purge_events: Sequence[Event], writer: str, applied: set[str]) -> list[str]:
    """The identifier of each purge that this ingestion applies: it names a corrected version
    that the writer version reaches or passes and that the machine has not recorded as applied
    yet (ingestion.md › Store)."""
    own = version_key(writer)
    names = []
    for purge in purge_events:
        corrected = purge.get("corrected_version")
        if not isinstance(corrected, str) or purge["event_uid"] in applied:
            continue
        if version_key(corrected) <= own:
            names.append(purge["event_uid"])
    return names


def _resolve_folders(
    read: Sequence[Event],
    home: Path,
    system: str,
    person: PersonConfiguration,
    root_commits: RootCommits,
) -> tuple[dict[str, RepositoryIdentity | None], list[dict]]:
    """The repository identity of each folder that the events name, resolved once per folder
    in one ingestion (architecture.md › Data flow, step 6), with the warnings of the
    resolutions."""
    resolved: dict[str, RepositoryIdentity | None] = {}
    warnings: list[dict] = []
    for event in read:
        folder = event.get("cwd")
        if not isinstance(folder, str) or folder in resolved:
            continue
        identity, named = resolve_folder(
            folder, system, home, person.preferred_remotes, root_commits)
        resolved[folder] = identity
        warnings.extend(named)
    return resolved, warnings


def _unknown_tools(unknown: Iterable[str], person: PersonConfiguration) -> list[dict]:
    """One warning for each tool name that no table of its adapter lists and that no category
    rule of the person matches (ingestion.md › Adapters)."""
    return [{"code": "unknown_tool_name", "values": {"tool": tool}}
            for tool in sorted(unknown)
            if not any(pattern_matches(rule.tool, tool) for rule in person.category_rules)]


def _recorded_again(folder: str, first: str, second: str) -> dict:
    """The warning for a folder of native logs that the machine configuration records for a
    second agent tool of the adapter that scans it already: the folder is scanned once, for
    the first of the two tools, and that tool carries the row of the sources of the
    folder (ingestion.md › Adapters)."""
    return {"code": "ambiguous_folder",
            "values": {"folder": folder, "tools": [first, second]}}


def _new_by_session(kept: Sequence[Event]) -> dict[tuple[str, str], int]:
    """The number of new events of each session of the reading, as its agent tool and its
    session identifier; an event that names neither counts for no folder of native logs."""
    counts: dict[tuple[str, str], int] = {}
    for event in kept:
        held = (event.get("tool"), event.get("session_id"))
        if None not in held:
            counts[held] = counts.get(held, 0) + 1
    return counts


def _project_folders(
    read: Sequence[Event],
    sessions: Sequence[SessionFiles],
) -> set[str]:
    """The folders that the retention reads the project settings files of: the `cwd` of every
    session this ingestion read, also of one it holds back (claude-code-adapter.md ›
    Retention). The events give the `cwd` of their sessions; a session that gave no event with
    a `cwd` gives the one its first record holds, so that a session whose events all stay held
    back counts too."""
    folders = {event["cwd"] for event in read
               if isinstance(event.get("cwd"), str) and event["cwd"]}
    gave = {(event.get("tool"), event.get("session_id")) for event in read if "cwd" in event}
    for session in sessions:
        if (session.tool, session.session_id) in gave:
            continue
        folders.update(_recorded_folders(session))
    return folders


def _recorded_folders(session: SessionFiles) -> Iterable[str]:
    """The `cwd` that the first record with one holds, of each file of the session."""
    for path in [session.main, *session.subagents.values()]:
        if path is None:
            continue
        try:
            with open(path, "rb") as log:
                for line in log:
                    try:
                        record: object = json.loads(line)
                    except ValueError:
                        continue
                    folder = record.get("cwd") if isinstance(record, dict) else None
                    if isinstance(folder, str) and folder:
                        yield folder
                        break
        except OSError:
            continue
    return


def _held_back_by_tool(held: Iterable[tuple[str, str]]) -> dict[str, list[str]]:
    """The sessions whose events stay held back, by their agent tool, as the record keeps
    them: this reading decides, so a session read complete and a session whose files are gone
    leave the record."""
    held_back: dict[str, list[str]] = {}
    for tool, session_id in sorted(held):
        held_back.setdefault(tool, []).append(session_id)
    return held_back


def remove_blocked_copies(store_folder: Path, machine: str, purges: PurgeSet) -> None:
    """Remove the copies that a purge blocks from the segments of the machine, one rewrite of
    each segment that holds one (architecture.md › Data flow, step 10). The segments of the
    other machines keep their copies: a machine never changes a segment of another machine
    (ingestion.md › Store). The purge set that lists no key blocks no copy, so no segment is
    decoded at all — the store without purges, the common one."""
    if not purges.holds_keys():
        return
    own = f"segments/{machine}/"
    for name in segment_names(store_folder):
        if not name.startswith(own):
            continue
        if any(not _keeps(line, purges) for line in read_lines(store_folder, name)):
            rewrite_segment(store_folder, name, lambda line: _keeps(line, purges))


def _keeps(line: SegmentLine, purges: PurgeSet) -> bool:
    """Whether the rewrite of a segment keeps a line: a line that is no event of this schema
    stays, and an event stays when no purge blocks its copy (event-schema.md › Keys and
    invariants)."""
    decoded = decode_line(line.data)
    return decoded.event is None or not purges.blocks(decoded.event)
