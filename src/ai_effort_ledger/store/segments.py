"""The segments of the store: their names, the reading of their lines, and the append of events.

A segment holds one event on each line and one machine writes it (`ingestion.md` › Store). A
reader ignores a last line without a line break, without a warning, because a machine or a
file-sync service is still writing it; before it appends, the machine cuts such a last line from
its own segment (D14). Each appended line takes one `write` and one `flush`, and the batch takes
one `os.fsync` (`architecture.md` › Concurrency). The lock of the machine and the store is the
caller's: `append_events` never takes it.
"""

import os
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from ..events import Event, encode_event, format_instant


class SegmentLine(NamedTuple):
    """One line of a segment: the name of its segment, its number from 1, its byte offset in the
    segment, and its bytes with the line break."""

    segment: str
    number: int
    offset: int
    data: bytes


def _segment_name(machine: str, now: datetime) -> str:
    """The path text of the segment of the machine for the UTC month of the instant."""
    return f"segments/{machine}/{format_instant(now)[:7]}.jsonl"


def segment_names(store_folder: Path) -> list[str]:
    """The names of the segments of the store, in the order of their paths as text."""
    segments = store_folder / "segments"
    if not segments.is_dir():
        return []
    return sorted(path.relative_to(store_folder).as_posix() for path in segments.glob("*/*.jsonl"))


def read_lines(
    store_folder: Path,
    segment: str,
    offset: int = 0,
    first_number: int = 1,
) -> Iterator[SegmentLine]:
    """Read the complete lines of the segment from the byte offset on, numbered from
    `first_number`, so that a read that resumes an earlier read gives the numbers of the segment.

    A last line without a line break is not given, without a warning; a broken line is given and
    keeps its number, so the caller decides its state with `decode_line`.
    """
    path = store_folder / segment
    if not path.is_file():
        return
    with open(path, "rb") as segment_file:
        segment_file.seek(offset)
        position = offset
        number = first_number
        while True:
            data = segment_file.readline()
            if not data.endswith(b"\n"):
                return
            yield SegmentLine(segment, number, position, data)
            position += len(data)
            number += 1


def append_events(
    store_folder: Path,
    machine: str,
    events: Sequence[Event],
    now: datetime,
) -> list[SegmentLine]:
    """Append the events to the segment of the machine for the UTC month of `now`, with
    `ingested_at` set to `now`, and give the lines as written.

    A last line without a line break of the segment is cut before the append (D14): its bytes
    are an append that stopped, never an event. The events of the caller are not changed.
    """
    name = _segment_name(machine, now)
    path = store_folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    written: list[SegmentLine] = []
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT)
    with os.fdopen(descriptor, "r+b") as segment_file:
        size = segment_file.seek(0, os.SEEK_END)
        segment_file.seek(0)
        content = segment_file.read(size)
        end = content.rfind(b"\n") + 1
        if end != size:
            segment_file.truncate(end)
        segment_file.seek(end)
        number = content.count(b"\n", 0, end) + 1
        for event in events:
            data = encode_event({**event, "ingested_at": format_instant(now)})
            offset = segment_file.tell()
            segment_file.write(data)
            segment_file.flush()
            written.append(SegmentLine(name, number, offset, data))
            number += 1
        os.fsync(segment_file.fileno())
    return written
