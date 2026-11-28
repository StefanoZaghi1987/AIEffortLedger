"""The record of the sources that one machine has already read into one store, kept in
`sources.json` of the machine-local data folder: the instant of the last ingestion of each
folder of native logs, the size and the time of change of each file of native logs already
read, the sessions with events held back, and the purges already applied (architecture.md ›
Files of a machine). The selection of the sessions to read and the warning for lost events
read the record; the ingestion writes it (ingestion.md › Frequency, architecture.md › Data
flow, steps 4 and 9)."""

import json
import os
from collections.abc import Sequence
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from ..adapters import Retention, SessionFiles
from ..events import format_instant, parse_instant
from ..platform import LockUnavailable, replace_file, store_identifier

SOURCES_FILE = "sources.json"
"""The name of the file of the record, below `stores/<store>` of the machine-local data
folder."""

STORES_FOLDER = "stores"
"""The folder of the machine-local data folder that holds the files of each store that the
machine keeps beside the store itself: the record of the sources and the lock."""


class SourcesState:
    """What one machine remembers of the sources of one store. `folders` maps each folder of
    native logs to the instant of its last ingestion; `files` maps each file of native logs
    already read to its size and its time of change; `held_back` maps each agent tool to the
    identifiers of its sessions whose events the machine holds back; `applied_purges` holds
    the identifier of each purge that the machine has applied (ingestion.md › Store)."""

    def __init__(
        self,
        folders: dict[str, str] | None = None,
        files: dict[str, tuple[int, int]] | None = None,
        held_back: dict[str, list[str]] | None = None,
        applied_purges: list[str] | None = None,
    ) -> None:
        self.folders = folders if folders is not None else {}
        self.files = files if files is not None else {}
        self.held_back = held_back if held_back is not None else {}
        self.applied_purges = applied_purges if applied_purges is not None else []

    @classmethod
    def load(cls, path: Path) -> "SourcesState":
        """Read the record from the file. A missing or unreadable file, and a section that is
        not of its shape, gives an empty state in its place, so that the first ingestion and a
        write that stopped both start from nothing."""
        try:
            document: Any = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            document = {}
        if not isinstance(document, dict):
            document = {}
        return cls(
            _folders(document.get("folders")),
            _files(document.get("files")),
            _held_back(document.get("held_back")),
            _purges(document.get("applied_purges")),
        )

    def save(self, path: Path, limit_seconds: float = 600.0) -> None:
        """Write the record to the file, creating the folders above it when they are missing.

        The document goes into a file beside the record first, and one replace puts it in the
        place of the record, so a write that stops leaves the record whole, never half of a
        document (architecture.md › Concurrency). A replace that the operating system refuses
        while another process holds the file open is tried again every half second until the
        limit; then the new file is removed again and the save stops with `LockUnavailable`,
        leaving the record as it was."""
        document = {
            "applied_purges": self.applied_purges,
            "files": {key: list(value) for key, value in self.files.items()},
            "folders": self.folders,
            "held_back": self.held_back,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        new_path = path.with_name(path.name + ".new")
        with open(new_path, "w", encoding="utf-8") as record_file:
            record_file.write(
                json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
            record_file.flush()
            os.fsync(record_file.fileno())
        replace_file(new_path, path, limit_seconds)


def sources_path(machine_folder: Path, store_folder: Path, system: str) -> Path:
    """The file of the record of the sources of one store: below `stores` and the identifier
    of the store folder, in the machine-local data folder (architecture.md › Files of a
    machine)."""
    return machine_folder / STORES_FOLDER / store_identifier(store_folder, system) / SOURCES_FILE


def file_stamp(path: Path) -> tuple[int, int] | None:
    """The size and the time of change of a file of native logs, the pair that the record
    holds for each file already read, or None when the file is gone."""
    try:
        status = path.stat()
    except OSError:
        return None
    return status.st_size, status.st_mtime_ns


def sessions_to_read(
    state: SourcesState,
    found: Sequence[SessionFiles],
    purged: Sequence[tuple[str, str]],
) -> list[SessionFiles]:
    """The sessions that this ingestion reads, in the order in which the adapter found them
    (architecture.md › Data flow, step 4): each session with a file that changed since the
    last ingestion, or with events held back, or named by a purge whose corrected version the
    machine applies. `purged` holds each such session as its agent tool and its session
    identifier; the ingestion passes what `PurgeSet.sessions_to_read` gives for its own
    version and its applied purges (ingestion.md › Store)."""
    named = set(purged)
    for tool, sessions in state.held_back.items():
        named.update((tool, session_id) for session_id in sessions)
    return [session for session in found
            if (session.tool, session.session_id) in named or _changed(state, session)]


def lost_events(
    state: SourcesState,
    folder: str,
    retention: Retention,
    now: datetime,
) -> dict | None:
    """The warning `lost_events` for a folder of native logs, or None (ingestion.md ›
    Frequency): when the time since the previous ingestion of the folder is longer than the
    retention period of its agent tool, that tool can have deleted files that changed after
    that ingestion before any ingestion read them. The first ingestion of a folder, and an
    agent tool whose retention sets no age limit, give no warning; a gap of exactly the
    retention period gives none. The `now` is an aware instant, as the instants of the record
    are."""
    if retention.days is None:
        return None
    previous = state.folders.get(folder)
    if previous is None:
        return None
    if now - parse_instant(previous) <= timedelta(days=retention.days):
        return None
    return {
        "code": "lost_events",
        "values": {"folder": folder, "from": previous, "to": format_instant(now)},
    }


def held_back_sessions(
    machine_folder: Path,
    store_folder: Path,
    system: str,
) -> set[tuple[str, str]]:
    """The sessions with events held back for one store, each as its agent tool and its
    session identifier, from the record of the sources of the store: what `cli` passes to the
    selection for its `held_back_events` warning (architecture.md › Data flow)."""
    state = SourcesState.load(sources_path(machine_folder, store_folder, system))
    return {(tool, session_id)
            for tool, sessions in state.held_back.items()
            for session_id in sessions}


def _changed(state: SourcesState, session: SessionFiles) -> bool:
    """Whether the session has a file that is gone, that the record never saw, or that
    differs from the file on the disk in its size or its time of change."""
    for path in [session.main, *session.subagents.values()]:
        if path is None:
            continue
        stamp = file_stamp(path)
        if stamp is None or state.files.get(str(path)) != stamp:
            return True
    return False


def _folders(value: Any) -> dict[str, str]:
    """The folders of a section of the record, or an empty dict when the section is not of
    its shape."""
    if not isinstance(value, dict):
        return {}
    return {str(key): str(item) for key, item in value.items()}


def _files(value: Any) -> dict[str, tuple[int, int]]:
    """The files of a section of the record: each pair of size and time of change back as a
    tuple of two integers; a pair of another shape stays out."""
    if not isinstance(value, dict):
        return {}
    files = {}
    for key, item in value.items():
        if (isinstance(item, list) and len(item) == 2
                and isinstance(item[0], int) and isinstance(item[1], int)):
            files[str(key)] = (item[0], item[1])
    return files


def _held_back(value: Any) -> dict[str, list[str]]:
    """The held-back sessions of a section of the record, or an empty dict when the section
    is not of its shape."""
    if not isinstance(value, dict):
        return {}
    held = {}
    for key, item in value.items():
        if isinstance(item, list):
            held[str(key)] = [str(session_id) for session_id in item]
    return held


def _purges(value: Any) -> list[str]:
    """The applied purges of a section of the record, or an empty list when the section is
    not of its shape."""
    if not isinstance(value, list):
        return []
    return [str(purge) for purge in value]
