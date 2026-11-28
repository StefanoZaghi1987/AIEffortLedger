"""The purges of the store: the copies that they block, the sessions that a machine reads
again, and the rewrite of a segment that removes the blocked copies.

A purge blocks every copy of a key that it lists, unless it names a corrected version and the
`writer_version` of the copy is that version or a newer one (ADR 0015); a purge without a
corrected version blocks for good (ADR 0008). The rewrite writes the kept lines into a new file
in the folder of the segment and puts it in the place of the segment (`ingestion.md` › Store),
so a reader sees the segment before or after the purge, never in between.
"""

import os
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path
from typing import NamedTuple

from ..events import Event, EventKey, event_key, version_key
from ..platform import LockUnavailable, replace_file
from .segments import SegmentLine, read_lines


class _Purge(NamedTuple):
    """One purge event: its identifier, its corrected version as an order key, the sessions
    that hold its keys, and the keys that it lists."""

    event_uid: str
    corrected: tuple | None
    sessions: tuple[tuple[str, str], ...]
    keys: tuple[EventKey, ...]


class PurgeSet:
    """The purges of a store: which copies they block, and which sessions a machine reads again
    once its own writer version reaches the corrected version of a purge."""

    def __init__(self, purges: Sequence[_Purge]) -> None:
        self._purges = tuple(purges)
        self._by_key: dict[EventKey, list[_Purge]] = {}
        for purge in self._purges:
            for key in purge.keys:
                self._by_key.setdefault(key, []).append(purge)

    @classmethod
    def from_events(cls, purges: Iterable[Event]) -> "PurgeSet":
        """The purges from the purge events of the store, in the order of the events."""
        entries = []
        for event in purges:
            corrected = event.get("corrected_version")
            entries.append(_Purge(
                event["event_uid"],
                None if corrected is None else version_key(corrected),
                tuple((session["tool"], session["session_id"])
                      for session in event.get("purged_sessions", ())),
                tuple(EventKey.from_json(key) for key in event.get("purged_keys", ()))))
        return cls(entries)

    def blocks(self, event: Event) -> bool:
        """Whether a purge blocks this copy: a purge that lists the key of the copy blocks it,
        unless it names a corrected version that the `writer_version` of the copy reaches or
        passes (`event-schema.md` › Keys and invariants)."""
        listed = self._by_key.get(event_key(event))
        if not listed:
            return False
        writer = version_key(event["writer_version"])
        return any(purge.corrected is None or writer < purge.corrected for purge in listed)

    def holds_keys(self) -> bool:
        """Whether the purges list any key at all: a purge set that lists none blocks no
        copy, so the segments need no walk over their lines."""
        return bool(self._by_key)

    def sessions_to_read(self, own_version: str, applied: set[str]) -> list[tuple[str, str]]:
        """The sessions of the purges that name a corrected version that the own writer version
        reaches or passes and that the machine has not recorded as applied, each as `tool` and
        `session_id` (`ingestion.md` › Store)."""
        own = version_key(own_version)
        return [
            session
            for purge in self._purges
            if purge.corrected is not None and purge.corrected <= own
            and purge.event_uid not in applied
            for session in purge.sessions
        ]


def rewrite_segment(
    store_folder: Path,
    segment: str,
    keep: Callable[[SegmentLine], bool],
    limit_seconds: float = 600.0,
) -> int:
    """Rewrite the segment without the lines that `keep` refuses, and give the number of lines
    removed.

    The kept lines go into a new file in the folder of the segment, and one `os.replace` puts
    the new file in the place of the segment. A last line without a line break stays out, as in
    every read; a segment that does not exist gives 0 and stays missing. When the operating
    system refuses the replace while another process holds the segment open, the rewrite tries
    again every half second until the limit, and then removes the new file again and stops with
    `LockUnavailable`, leaving the segment as it was.
    """
    path = store_folder / segment
    if not path.is_file():
        return 0
    lines = list(read_lines(store_folder, segment))
    new_path = path.with_name(path.name + ".new")
    kept = 0
    with open(new_path, "wb") as new_file:
        for line in lines:
            if keep(line):
                new_file.write(line.data)
                kept += 1
        new_file.flush()
        os.fsync(new_file.fileno())
    replace_file(new_path, path, limit_seconds)
    return len(lines) - kept
