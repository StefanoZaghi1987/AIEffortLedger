"""Shared support for the tests: the environment, temporary folders, instants, git objects,
the world of a test — one machine set up below a temporary folder, and the file-sync service
that copies the segments of its store to another —, the fixture stores of the report tests,
and the marks that make one expected file of a report test fit every run and every operating
system.

The git objects, reference files, and pack files are built by hand with invented content: the
object names follow from the contents through SHA-1, and no test runs git (ADR 0004).
"""

import contextlib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import zlib
from collections.abc import Callable, Iterable, Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from platform import system as running_system
from typing import Any, NamedTuple

from ai_effort_ledger import adapters, days
from ai_effort_ledger.adapters.claude_code import ClaudeCodeAdapter
from ai_effort_ledger.cli import Context, inside_folder, main
from ai_effort_ledger.cli.figures import Figures, figures_of_days
from ai_effort_ledger.configuration import (
    MachineConfiguration,
    DayStartEntry,
    TimeZoneEntry,
    append_entry,
    create_person_configuration,
    read_person_configuration,
    resolve_parameters,
    write_machine_configuration,
)
from ai_effort_ledger.configuration.person import PERSON_FILE
from ai_effort_ledger.events import Event, decode_line
from ai_effort_ledger.ingestion.run import DEVELOPMENT_VARIABLE, LOCK_FILE
from ai_effort_ledger.metrics import Metrics, MetricsParameters, compute_metrics
from ai_effort_ledger.platform import machine_folder, new_salt, salted_hash
from ai_effort_ledger.store import read_lines, segment_names, write_label

os.environ["AI_EFFORT_LEDGER_DEVELOPMENT"] = "1"

# No test reads the time zones of the machine: only the `tzdata` package serves them
# (ADR 0022).
days.use_tzdata_only()


def utc(text: str) -> datetime:
    """Read an instant as UTC: `YYYY-MM-DDTHH:MM`, with optional seconds and milliseconds."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


TEMPORARY_PREFIX = "ai_effort_ledger_"
"""The start of the name of every temporary folder that `TemporaryFolder` makes."""


class TemporaryFolder:
    """A temporary folder that is removed at the end; it yields its path, resolved, so
    that every path a test derives from it is the same one whatever form the system names
    the folder in."""

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix=TEMPORARY_PREFIX)).resolve()
        return self.path

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        shutil.rmtree(self.path, ignore_errors=True)


PERSON = "Example Person <person@example.org>"
INSTANT = "1700000000 +0100"
TREE = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
PACK_TYPES = {"commit": 1, "tree": 2, "blob": 3, "tag": 4}


def commit_object(tree: str, parents: list[str], message: str) -> bytes:
    """The content of a commit object with the invented person, instant, and message."""
    lines = [f"tree {tree}"]
    lines.extend(f"parent {parent}" for parent in parents)
    lines.append(f"author {PERSON} {INSTANT}")
    lines.append(f"committer {PERSON} {INSTANT}")
    return ("\n".join(lines) + f"\n\n{message}\n").encode("utf-8")


def object_name(type_name: str, content: bytes) -> str:
    """The SHA-1 name of an object: the hash of its header and its content."""
    header = f"{type_name} {len(content)}".encode("utf-8") + b"\0"
    return hashlib.sha1(header + content).hexdigest()


def write_loose_object(git_folder: Path, type_name: str, content: bytes) -> str:
    """Write one loose object under `objects/` and return its name."""
    name = object_name(type_name, content)
    data = f"{type_name} {len(content)}".encode("utf-8") + b"\0" + content
    folder = git_folder / "objects" / name[:2]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name[2:]).write_bytes(zlib.compress(data))
    return name


def write_head(git_folder: Path, target: str) -> None:
    """Write `HEAD` as a symbolic reference to the named branch."""
    _write_file(git_folder, "HEAD", f"ref: {target}\n")


def write_loose_ref(git_folder: Path, name: str, commit: str) -> None:
    """Write one loose reference file, such as `refs/heads/main`, with the commit it holds."""
    _write_file(git_folder, name, commit + "\n")


def write_packed_refs(git_folder: Path, refs: list[tuple[str, str]]) -> None:
    """Write `packed-refs`: the header line, then each pair of reference name and commit."""
    lines = ["# pack-refs with: peeled fully-peeled sorted"]
    lines.extend(f"{commit} {name}" for name, commit in refs)
    _write_file(git_folder, "packed-refs", "\n".join(lines) + "\n")


class Whole(NamedTuple):
    """One object of a pack stored whole: its type and its content."""

    type_name: str
    content: bytes


class OfsDelta(NamedTuple):
    """One object of a pack stored as a delta against an earlier object of the same pack.

    `base` is the position of the base object in the list of entries; `type_name` and
    `content` are the type and the content that applying the delta rebuilds, from which the
    name of the object follows.
    """

    base: int
    delta: bytes
    type_name: str
    content: bytes


class RefDelta(NamedTuple):
    """One object of a pack stored as a delta against the object of a named base.

    `base` is the SHA-1 name of the base object; `type_name` and `content` are the type and
    the content that applying the delta rebuilds, from which the name of the object follows.
    """

    base: str
    delta: bytes
    type_name: str
    content: bytes


def delta_from(base: bytes, target: bytes) -> bytes:
    """The delta that rebuilds the target from the base: a copy of the shared start, the
    difference inserted, and a copy of the shared end."""
    start = 0
    while start < len(base) and start < len(target) and base[start] == target[start]:
        start += 1
    end = 0
    while (end < len(base) - start and end < len(target) - start
           and base[-1 - end] == target[-1 - end]):
        end += 1
    middle = target[start:len(target) - end]
    parts = [_delta_size(len(base)), _delta_size(len(target))]
    if start:
        parts.append(_copy_instruction(0, start))
    for at in range(0, len(middle), 127):
        piece = middle[at:at + 127]
        parts.append(bytes([len(piece)]) + piece)
    if end:
        parts.append(_copy_instruction(len(base) - end, end))
    return b"".join(parts)


def write_pack(git_folder: Path, entries: list[Whole | OfsDelta | RefDelta]) -> list[str]:
    """Write a pack and its index, both of format number 2, with the entries, and return the
    object names in the order of the entries."""
    blobs: list[bytes] = []
    names: list[str] = []
    offsets: list[int] = []
    position = 12
    for entry in entries:
        header = f"{entry.type_name} {len(entry.content)}".encode("utf-8") + b"\0"
        names.append(hashlib.sha1(header + entry.content).hexdigest())
        if isinstance(entry, Whole):
            blob = (_pack_header(PACK_TYPES[entry.type_name], len(entry.content))
                    + zlib.compress(entry.content))
        elif isinstance(entry, OfsDelta):
            distance = position - offsets[entry.base]
            blob = (_pack_header(6, len(entry.delta)) + _negative_offset(distance)
                    + zlib.compress(entry.delta))
        else:
            blob = (_pack_header(7, len(entry.delta)) + bytes.fromhex(entry.base)
                    + zlib.compress(entry.delta))
        blobs.append(blob)
        offsets.append(position)
        position += len(blob)
    pack = b"PACK" + (2).to_bytes(4, "big") + len(entries).to_bytes(4, "big") + b"".join(blobs)
    checksum = hashlib.sha1(pack).digest()
    pack += checksum
    ordered = sorted(zip(names, offsets, blobs))
    fanout = [0] * 256
    for held, _, _ in ordered:
        fanout[int(held[:2], 16)] += 1
    total = 0
    for entry in range(256):
        total += fanout[entry]
        fanout[entry] = total
    index_bytes = bytearray(b"\xfftOc" + (2).to_bytes(4, "big"))
    index_bytes += b"".join(value.to_bytes(4, "big") for value in fanout)
    index_bytes += b"".join(bytes.fromhex(held) for held, _, _ in ordered)
    index_bytes += b"".join(zlib.crc32(blob).to_bytes(4, "big") for _, _, blob in ordered)
    index_bytes += b"".join(offset.to_bytes(4, "big") for _, offset, _ in ordered)
    index_bytes += checksum
    index_bytes += hashlib.sha1(bytes(index_bytes)).digest()
    folder = git_folder / "objects" / "pack"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"pack-{checksum.hex()}.pack").write_bytes(pack)
    (folder / f"pack-{checksum.hex()}.idx").write_bytes(bytes(index_bytes))
    return names


def _write_file(git_folder: Path, relative: str, text: str) -> None:
    """Write the text to the path in the git folder, creating the parent folders."""
    path = git_folder / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _delta_size(number: int) -> bytes:
    """The 7-bit little-endian groups of a size at the start of a delta."""
    out = bytearray()
    while True:
        byte = number & 0x7F
        number >>= 7
        if number:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _copy_instruction(offset: int, size: int) -> bytes:
    """One copy instruction: the head bits say which offset and size bytes are present."""
    if size == 0x10000:
        size = 0
    head = 0x80
    body = bytearray()
    for bit, shift in enumerate((0, 8, 16, 24)):
        byte = (offset >> shift) & 0xFF
        if byte:
            head |= 1 << bit
            body.append(byte)
    for bit, shift in enumerate((0, 8, 16)):
        byte = (size >> shift) & 0xFF
        if byte:
            head |= 0x10 << bit
            body.append(byte)
    return bytes([head, *body])


def _pack_header(type_number: int, size: int) -> bytes:
    """The type and uncompressed size of one object, as a pack holds them."""
    out = bytearray()
    head = (type_number << 4) | (size & 0x0F)
    size >>= 4
    while size:
        out.append(head | 0x80)
        head = size & 0x7F
        size >>= 7
    out.append(head)
    return bytes(out)


def _negative_offset(distance: int) -> bytes:
    """The offset bytes of an `OFS_DELTA`: the distance back to its base object."""
    out = [distance & 0x7F]
    distance >>= 7
    while distance:
        distance -= 1
        out.insert(0, 0x80 | (distance & 0x7F))
        distance >>= 7
    return bytes(out)


VERSION = "2.1.0"
"""The invented format version that the builders of records write in every record."""

_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "claude_code"


def prompt_record(text: str, instant: str, uuid_value: str) -> dict[str, Any]:
    """A `user` record that holds a prompt of the person; the text is invented."""
    return {
        "type": "user",
        "uuid": uuid_value,
        "timestamp": instant,
        "version": VERSION,
        "origin": {"kind": "human"},
        "message": {"role": "user", "content": text},
    }


def output_record(text: str, instant: str, uuid_value: str, message_id: str) -> dict[str, Any]:
    """A record of the agent that holds a response of the model; the text is invented."""
    return {
        "type": "assistant",
        "uuid": uuid_value,
        "timestamp": instant,
        "version": VERSION,
        "message": {
            "id": message_id,
            "model": "Invented-Model",
            "usage": {},
            "content": [{"type": "text", "text": text}],
        },
    }


def tool_use(
    tool_name: str,
    call_id: str,
    tool_input: dict[str, Any],
    instant: str,
    uuid_value: str,
    message_id: str,
) -> dict[str, Any]:
    """A record of the agent whose content holds one use of a tool by the agent."""
    return {
        "type": "assistant",
        "uuid": uuid_value,
        "timestamp": instant,
        "version": VERSION,
        "message": {
            "id": message_id,
            "model": "Invented-Model",
            "usage": {},
            "content": [{"type": "tool_use", "id": call_id, "name": tool_name,
                         "input": tool_input}],
        },
    }


def tool_result_record(
    call_id: str,
    instant: str,
    uuid_value: str,
    result: Any = None,
) -> dict[str, Any]:
    """A `user` record whose content holds the result of one use of a tool; the result becomes
    the `toolUseResult` of the record when it is given."""
    record: dict[str, Any] = {
        "type": "user",
        "uuid": uuid_value,
        "timestamp": instant,
        "version": VERSION,
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": call_id,
                         "content": "Invented result text."}],
        },
    }
    if result is not None:
        record["toolUseResult"] = result
    return record


def queue_record(text: str, instant: str) -> dict[str, Any]:
    """A `queue-operation` record that holds a message typed while the agent worked; the text
    is invented and the record gives no native identifier."""
    return {
        "type": "queue-operation",
        "operation": "enqueue",
        "content": text,
        "timestamp": instant,
        "version": VERSION,
    }


def write_session(
    folder: Path,
    session_id: str,
    records: Sequence[dict[str, Any]],
    subagents: Mapping[str, Sequence[dict[str, Any]]],
    cwd: Path,
) -> None:
    """Write the files of one session into a folder of native logs: the file of the main
    agent, and the file of each subagent below `<session>/subagents/`. Every record is
    stamped with the session and the cwd; a session with no records gets no main file."""
    if records:
        _write_log(folder / f"{session_id}.jsonl", session_id, records, cwd)
    for name, agent_records in subagents.items():
        _write_log(folder / session_id / "subagents" / f"agent-{name}.jsonl",
                   session_id, agent_records, cwd)


def _write_log(
    path: Path,
    session_id: str,
    records: Sequence[dict[str, Any]],
    cwd: Path,
) -> None:
    """Write the records as lines of JSON, each stamped with the session and the cwd."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for record in records:
        stamped = dict(record)
        stamped["sessionId"] = session_id
        stamped["cwd"] = str(cwd)
        lines.append(json.dumps(stamped, separators=(",", ":"), ensure_ascii=False))
    path.write_text("".join(line + "\n" for line in lines), encoding="utf-8")


def copy_fixture(name: str, folder: Path, cwd: Path) -> Path:
    """Copy the fixture `name` into `folder` as a native log, with the given cwd in every
    record, and return the path of the copy. A line that is not a JSON record stays as it is,
    so that a fixture can hold a line that warns."""
    lines = []
    source = (_FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8")
    for line in source.splitlines():
        try:
            record: Any = json.loads(line)
        except ValueError:
            lines.append(line)
            continue
        record["cwd"] = str(cwd)
        lines.append(json.dumps(record, separators=(",", ":"), ensure_ascii=False))
    target = folder / f"{name}.jsonl"
    target.write_text("".join(line + "\n" for line in lines), encoding="utf-8")
    return target


def adapters_for_tests(home: Path) -> ClaudeCodeAdapter:
    """The adapter of Claude Code whose managed settings file is in the temporary home: every
    test that ingests or builds a context passes the home of its temporary folder, so that no
    test reads the managed settings file of the machine that runs the tests."""
    return ClaudeCodeAdapter(managed_file=home / "managed-settings.json")


SCENARIO_PARAMETERS = MetricsParameters(
    idle_gap=600, minimum_attention=60, stale_limit=14400, headless_prompts=False)
"""The report parameters of a scenario, at the defaults of the ledger (metrics.md › Human
time, › Agent time). Public: a test that computes metrics of its own takes these, never a
restated literal."""

_SCENARIO_WRITING = utc("2026-01-01T00:00")
"""The instant at which a scenario writes its files, so that the reading of the same day at
noon sees every session settled."""

_SCENARIO_READING = utc("2026-01-01T12:00")
"""The instant at which a scenario reads the files it wrote, half a day later."""

SETTLE_TIME = 14400
"""The settle time of the person configuration that setup creates — the default of the
ledger (GLOSSARY › Settle time) — in whole seconds: the reading of a scenario and `settle`
take it; a test that builds a person configuration of its own takes this, never a restated
literal."""


def scenario_days(
    time_zones: Sequence[TimeZoneEntry] | None = None,
    day_starts: Sequence[DayStartEntry] | None = None,
) -> days.LocalDays:
    """The local days of a scenario: the dated facts given, or one time zone valid from 1970
    and the day start 00:00 when absent, so that a scenario can change the day start, cross
    a change of daylight saving, or make a journey (metrics.md › Days and weeks)."""
    return days.LocalDays(
        list(time_zones) if time_zones is not None
        else [TimeZoneEntry("Etc/UTC", utc("1970-01-01T00:00"), 2)],
        list(day_starts) if day_starts is not None
        else [DayStartEntry(time(0, 0), date(1970, 1, 1), 3)],
    )


def scenario(
    sessions: Sequence[Sequence[dict[str, Any]]],
    annotations: Sequence[Event] = (),
    manual_entries: Sequence[Event] = (),
    subagents: Mapping[int, Mapping[str, Sequence[dict[str, Any]]]] | None = None,
    time_zones: Sequence[TimeZoneEntry] | None = None,
    day_starts: Sequence[DayStartEntry] | None = None,
) -> tuple[list[Event], Metrics, days.LocalDays]:
    """The events, the metrics, and the local days of one scenario: the builder writes the
    native logs, reads the logs with the adapter as the settled sessions of one person,
    and computes the metrics, so that a test asserts hand-computed values and which events
    the scenario writes (architecture.md › Tests, validation-2026-11.md).

    `sessions` is a sequence of the record lists of one or more sessions; each session has
    its own working folder, whose repository the builder writes by hand, and every of its
    records is stamped with the session identifier `session-<its position>` and that folder.
    `subagents` names, for the position of a session, the records of each file of a
    subagent; the subagent links through the `agentId` that the `toolUseResult` of the
    result of the call that started it holds. `annotations` and `manual_entries` are events
    that a command writes; the manual entries take part in the metrics, and all of them
    come back among the events, though the builder writes none of them to a store. The
    time-zone history and the day-start hours are the dated facts of the person
    (`scenario_days`); the reading uses the settle time of the ledger, and the metrics its
    default parameters.
    """
    person = scenario_days(time_zones, day_starts)
    linked = subagents or {}
    with TemporaryFolder() as root:
        logs = root / "logs"
        for position, records in enumerate(sessions):
            cwd = _own_repository(root, position)
            write_session(logs, f"session-{position}", records, linked.get(position, {}), cwd)
        for path in sorted(logs.rglob("*.jsonl")):
            os.utime(path, (_SCENARIO_WRITING.timestamp(), _SCENARIO_WRITING.timestamp()))
        adapter = adapters_for_tests(root / "home")
        context = adapters.ReadContext(
            "machine-one", _SCENARIO_READING, SETTLE_TIME, _without_owner)
        read = adapter.read_sessions(adapter.sessions("claude-code", logs), context)
        metrics = compute_metrics(read.events, list(manual_entries), SCENARIO_PARAMETERS)
    return [*read.events, *annotations, *manual_entries], metrics, person


def _own_repository(root: Path, position: int) -> Path:
    """The working folder of one session of a scenario, with its own repository: a `.git`
    folder that holds one root commit, to which `HEAD` points through `refs/heads/main`."""
    cwd = root / f"work-{position}"
    git_folder = cwd / ".git"
    git_folder.mkdir(parents=True)
    (git_folder / "config").write_text(
        "[core]\n    repositoryformatversion = 0\n", encoding="utf-8")
    content = commit_object(TREE, [], "Invented root commit of the scenario.")
    name = write_loose_object(git_folder, "commit", content)
    write_loose_ref(git_folder, "refs/heads/main", name)
    write_head(git_folder, "refs/heads/main")
    return cwd


def _without_owner(session_id: str, native_id: str) -> tuple[str, str] | None:
    """The lookup of a reading that has no store behind it: no native identifier names a
    session that holds it already."""
    return None


_ROOT_MARK = "<root>"
"""What `normalize` writes in the place of a path below a root, whose part below the
root stays, with its separators as `/`, so one expected file fits every operating system."""

_BYTES_MARK = '"size": <bytes>'
"""What `normalize` writes in the place of the bytes that a report read of one segment."""

_HASH_MARK = '"chained_hash": <hash>'
"""What `normalize` writes in the place of the chained hash of the lines of one segment."""

_TZDATA_JSON_MARK = '"tzdata": <tzdata>'
"""What `normalize` writes in the place of a tzdata version in a JSON document: the key
`tzdata` holds one only in the report record and in the document of `version`."""

_TZDATA_TEXT_MARK = "tzdata: <tzdata>"
"""What `normalize` writes in the place of a tzdata version in a text output, which the
line `tzdata: <version>` holds."""

_PATH_RUN = r"(?:[\\/][^\s\"]*)?"
"""The part of one path that follows its root, up to a space or a quote: the text of the
path below the root, in which each separator is one slash or backslash of the form the
output wrote."""


def normalize(text: str, roots: Sequence[Path]) -> str:
    """The text of an output as one committed expected file holds it: the line ends are
    folded, every absolute path below one of the roots — as a table prints it and as JSON
    escapes it — becomes `<root>` with the part of the path below its root, whose
    separators become `/`, the bytes read and the chained hash of each segment of the
    report record become `<bytes>` and `<hash>`, and every tzdata version becomes
    `<tzdata>` (Global Constraints). Running it over its own output changes nothing, so
    the comparison runs both sides of a report test through it."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for root in sorted({str(Path(one)) for one in roots}, key=len, reverse=True):
        text = _mask_below_root(text, root)
    text = re.sub(r'"size":\s*\d+', _BYTES_MARK, text)
    text = re.sub(r'"chained_hash":\s*"[0-9a-f]*"', _HASH_MARK, text)
    text = re.sub(r'"tzdata":\s*"[^"]*"', _TZDATA_JSON_MARK, text)
    text = re.sub(r"(?m)^tzdata:.*$", _TZDATA_TEXT_MARK, text)
    return text


def _mask_below_root(text: str, root: str) -> str:
    """Replace every path that begins with the root, in the form that JSON escapes and in
    the form that a table prints, with the mark and the part of the path below the root."""
    for form in dict.fromkeys((json.dumps(root)[1:-1], root)):
        text = re.sub(re.escape(form) + _PATH_RUN,
                      lambda found: _marked_path(found.group(0), len(form)), text)
    return text


def _marked_path(path: str, length: int) -> str:
    """The mark of the root and the part of the path below it, with each separator as one
    `/`, whatever form the output wrote the separators in."""
    return _ROOT_MARK + path[length:].replace("\\\\", "/").replace("\\", "/")


def cells(text: str) -> list[list[str]]:
    """The cells of each line of a text: the parts that two or more spaces separate, without
    the spaces at the ends of the line; a line without cells gives an empty list. The column
    of a table that holds an absolute path is as wide as the path of the machine, and
    `normalize` masks the path only after the layout is made, so the report test of such a
    table compares its text cell by cell after `normalize`."""
    return [[part.strip() for part in re.split(r" {2,}", line) if part.strip()]
            for line in text.split("\n")]


class FormText(NamedTuple):
    """One text of the shared table of the forms, with the verdict of each form: whether
    the text is a day `YYYY-MM-DD`, a local instant `YYYY-MM-DDTHH:MM`, an RFC 3339
    instant with an offset or `Z`, or an hour `HH:MM` (command-line.md › Form)."""

    text: str
    day: bool
    local_instant: bool
    offset_instant: bool
    hour: bool


FORM_TEXTS: tuple[FormText, ...] = (
    FormText("2026-11-10", True, False, False, False),
    FormText("today", False, False, False, False),
    FormText("yesterday", False, False, False, False),
    FormText("2026-11-10T09:30", False, True, False, False),
    FormText("2026-11-10T09:30:00Z", False, False, True, False),
    FormText("2026-11-10T09:30:00.125+01:00", False, False, True, False),
    FormText("04:00", False, False, False, True),
    FormText("20261110", False, False, False, False),
    FormText("2026-W46-1", False, False, False, False),
    FormText("2026-11-10 09:30", False, False, False, False),
    FormText("2026-11-10T09:30:00", False, False, False, False),
    FormText("2026-11-10T09:30Z", False, False, False, False),
    FormText("04:00:00", False, False, False, False),
    FormText("2026-02-30", False, False, False, False),
)
"""The one table of texts of the forms of the dated values, shared by the tests of every
reader: a reader of a person's text takes the forms of its kind alone, so every text that
no column holds is a wrong value for every reader. `today` and `yesterday` are words of
the day of the run, which a day reader of the command line takes besides the form and the
configuration file never takes; `2026-11-10T09:30:00` is a local instant with seconds and
`2026-11-10T09:30Z` an offset without the second, and `2026-11-10 09:30` a space for `T`."""


FIXTURE_NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
"""The instant of the context of every fixture store and of the commands of its tests, and
the instant of every world that gives none."""

FIXTURE_VERSION = "0.1.0"
"""The release version of the ledger that the context of every fixture store gives, and the
version of every world that gives none."""

FIXTURE_ZONE = "Etc/UTC"
"""The one time zone of the person of every store that a fixture store or a world creates,
valid from the start of 1970, so that every instant is both the UTC instant and the local
time, and no day holds a change of daylight saving; the context gives it as the time zone
of the operating system."""

FIXTURE_MACHINE = "machine-one"
"""The fixed machine identifier of every fixture store, which `before_write()` keeps,
because the machine configuration records the salted hash of the installation."""

FIXTURE_LABEL = "Invented office laptop"
"""The machine label that the store metadata of `FIXTURE_MACHINE` holds in the fixture
stores of `FIXTURE_LABELLED`."""

FIXTURE_LABELLED = frozenset({"annotations", "frozen_period"})
"""The fixture stores whose machine has a machine label: the stores of the expected files
of `frozen list` and of one pair of `entries`, which show the label; `declared_day`, whose
pair of `entries` shows the identifier, and every other store hold none."""

FIXTURE_INSTALLATION = "Installation-Fixture-2026"
"""The installation identifier of the context of every fixture store and of every world
that gives none, whose salted hash the machine configuration holds, so that a command of a
test never makes the machine identifier again."""

FIXTURE_EXECUTABLE = Path("D:/Work/Product/ai-effort-ledger")
"""The absolute path of the installed command that the context of every fixture store and
of every world gives, invented, a path of no machine that runs the tests."""

FIXTURE_FIRST_UID = "00000000-0000-4000-8000-000000000001"
"""The first identifier that the context of a fixture store gives to a command of a
test; the identifiers that the build of the store wrote itself count in another
namespace, `build_uid`, so that the two never meet."""

FIXTURE_NAMES = ("measured_day", "declared_day", "manual_entries", "annotations",
                 "retraction", "frozen_period", "frozen_day", "parallel_agents")
"""The names of the fixture stores, each the scenario of one or more report tests."""

FIXTURE_DAY_ONE = date(2026, 11, 20)
"""The first day of the fixtures, a day of work of the stores of one day."""

FIXTURE_DAY_TWO = date(2026, 11, 21)
"""The second day of the fixtures, the later day of the period of `frozen_period`."""

FIXTURE_DAY_THREE = date(2026, 11, 23)
"""The third day of the fixtures, the declared day."""

FIXTURE_PERIODS: dict[str, tuple[date, date]] = {
    "measured_day": (FIXTURE_DAY_ONE, FIXTURE_DAY_ONE),
    "declared_day": (FIXTURE_DAY_THREE, FIXTURE_DAY_THREE),
    "manual_entries": (FIXTURE_DAY_ONE, FIXTURE_DAY_ONE),
    "annotations": (FIXTURE_DAY_ONE, FIXTURE_DAY_ONE),
    "retraction": (FIXTURE_DAY_ONE, FIXTURE_DAY_ONE),
    "frozen_period": (FIXTURE_DAY_ONE, FIXTURE_DAY_TWO),
    "frozen_day": (FIXTURE_DAY_ONE, FIXTURE_DAY_ONE),
    "parallel_agents": (FIXTURE_DAY_ONE, FIXTURE_DAY_ONE),
}
"""The period of each fixture store, both ends included, that a report of the store
covers and that the tests read the figures of."""

FIXTURE_PROJECTS: dict[str, str] = {"alpha": "Alpha", "beta": "Beta"}
"""The two projects of the fixtures, each identifier with the name that reports show."""

FIXTURE_IDENTITIES: dict[str, str] = {"alpha": "example.com/acme/alpha",
                                      "beta": "example.com/acme/beta"}
"""The repository identity of the repository of each project; the remote URL of the
repository is `https://<identity>.git`, and one identity rule per repository resolves
its events to the project, so no figure of a store rests on an inferred repository
identity."""

FIXTURE_WORK_ITEMS: dict[tuple[str, str], str] = {
    ("alpha", "story-1"): "Story One",
    ("beta", "story-2"): "Story Two",
}
"""The work items of the fixtures, each with its project, its identifier, and the name
that reports show; only the `annotations` store declares them."""

FIXTURE_SESSIONS: dict[str, tuple[str, ...]] = {
    "measured_day": ("session-alpha",),
    "declared_day": ("session-alpha",),
    "manual_entries": ("session-alpha",),
    "annotations": ("session-alpha", "session-beta"),
    "retraction": ("session-alpha",),
    "frozen_period": ("session-alpha", "session-beta"),
    "frozen_day": ("session-alpha", "session-beta"),
    "parallel_agents": ("session-alpha", "session-beta"),
}
"""The sessions of the native logs of each fixture store; a session works in the
repository of its project, `session-alpha` in `alpha` and `session-beta` in `beta`."""

FIXTURE_NOTES: dict[str, str] = {
    "overlapping": "Invented note of the overlapping entry.",
    "additional": "Invented note of the additional entry.",
    "session": "Invented note of the session annotation.",
    "interval": "Invented note of the interval annotation.",
    "retracted": "Invented note of the retracted entry.",
    "frozen": "Invented note of the frozen report.",
}
"""The notes that the declared events and the frozen report of the fixtures carry, as
the commands wrote them."""

FIXTURE_STORE_FOLDER = "store"
"""The name of the store folder of a fixture store, and of a world that gives none, below
the home."""

FIXTURE_LOGS_FOLDER = "logs"
"""The name of the folder of native logs of a fixture store, and of a world that gives
none, below the home."""

FIXTURE_WORK_FOLDER = "work"
"""The name of the folder that holds the working folder of each project of a fixture,
below the temporary home."""

FIXTURE_FOLDERS: dict[str, str] = {"alpha": "work/alpha", "beta": "work/beta"}
"""The working folder of each project of a fixture, below the temporary home with `/` as
the separator; every `cwd` of a fixture is below the temporary home (Global Constraints)."""

_FIXTURE_ENTRYPOINT = "cli"
"""The entrypoint of every record of a fixture session, so that its prompts are of the
interactive invocation and the share of unknown invocation is 0.0 on every fixture day."""


class World(NamedTuple):
    """One machine of a test, as `world` makes it: the home of its person, its machine-local
    data folder, its machine identifier, its store folder, its folders of native logs in the
    order that the machine configuration lists them, the environment of its commands, and the
    context of its commands."""

    home: Path
    machine_folder: Path
    machine: str
    store: Path
    logs: Sequence[Path]
    environ: dict[str, str]
    context: Context


def world_environ(home: Path) -> dict[str, str]:
    """The environment of the commands of a world: `AI_EFFORT_LEDGER_DEVELOPMENT` set to
    `1`, the variable that lets a version with a development mark write to the store
    (architecture.md › Runtime), and the machine-local data folders of every operating
    system below `home`, so that a command writes nothing outside the folder of its world.
    A release version writes whatever the variable holds."""
    return {
        DEVELOPMENT_VARIABLE: "1",
        "LOCALAPPDATA": str(home / "app-data"),
        "XDG_STATE_HOME": str(home / "state"),
        "XDG_DATA_HOME": str(home / "share"),
    }


def world(
    home: Path,
    machine: str,
    store: Path | None = None,
    logs: Sequence[Path] | None = None,
    *,
    now: datetime = FIXTURE_NOW,
    version: str = FIXTURE_VERSION,
    new_uid: Callable[[], str] | None = None,
    installation: str | None = FIXTURE_INSTALLATION,
    uid: int | None = 501,
) -> World:
    """One machine of a test, set up below the folder `home` of its person as `setup`
    leaves a machine (command-line.md › Setup, steps 1 to 3), so that every command that
    needs a set-up ledger runs on it.

    The store folder is the one given, else `FIXTURE_STORE_FOLDER` below the home; the
    folders of native logs are the ones given, else `FIXTURE_LOGS_FOLDER` below the home,
    which the machine configuration lists for the agent tool `claude-code`. The machine
    configuration of the machine-local data folder holds the identifier `machine`, the
    store folder, the folders of native logs, and the salted hash of the installation
    identifier with its salt — neither of the two when the installation gives no identifier —
    so that `before_write()` keeps the identifier. The person configuration of the store
    folder is created when the folder holds none: the time zone `FIXTURE_ZONE` and the day
    start 00:00, valid from the start of 1970, the settle time and the report parameters
    at their defaults, no project and no rule. The context of the commands of the world
    gives the running system, the environment of `world_environ`, the home, the instant
    `now`, `new_uid`, `no_scheduler`, `FIXTURE_EXECUTABLE`, the installation identifier,
    no question, the adapters of the home, `FIXTURE_ZONE` as the time zone, `version`, and
    the user identifier `uid`.

    Without `new_uid`, the world counts its own identifiers from `FIXTURE_FIRST_UID`: two
    worlds whose events meet, in one store or through copies of segments, take one maker
    for both, because two events with one identifier are one event key.

    Two worlds that share one store folder are two machines on one store. Two worlds with
    a store each, and `copy_segments` between the stores, show the delay of a file-sync
    service.
    """
    store = home / FIXTURE_STORE_FOLDER if store is None else store
    folders = [home / FIXTURE_LOGS_FOLDER] if logs is None else list(logs)
    environ = world_environ(home)
    system = running_system()
    folder = Path(machine_folder(system, environ, home))
    salt = None
    hashed = None
    if installation is not None:
        salt = new_salt()
        hashed = salted_hash(installation, salt)
    home.mkdir(parents=True, exist_ok=True)
    store.mkdir(parents=True, exist_ok=True)
    folder.mkdir(parents=True, exist_ok=True)
    for held in folders:
        held.mkdir(parents=True, exist_ok=True)
    write_machine_configuration(folder, MachineConfiguration(
        machine=machine, installation=hashed, salt=salt, store=str(store),
        native_logs={"claude-code": [str(held) for held in folders]}))
    if not (store / PERSON_FILE).exists():
        create_person_configuration(store, FIXTURE_ZONE)
    context = Context(
        system=system,
        environ=environ,
        home=home,
        now=now,
        new_uid=fixture_uids() if new_uid is None else new_uid,
        run=no_scheduler,
        executable=FIXTURE_EXECUTABLE,
        installation=installation,
        ask=None,
        adapters=[adapters_for_tests(home)],
        time_zone=lambda: FIXTURE_ZONE,
        version=version,
        uid=uid,
    )
    return World(home, folder, machine, store, folders, environ, context)


def no_scheduler(words: list[str]) -> subprocess.CompletedProcess:
    """The call of a scheduler program that no test reaches: the worlds of the tests are
    set up by `world` and the fixture stores by their builders, and no command of a test
    runs one."""
    raise AssertionError(f"no test runs a scheduler program: {words}")


def settle(paths: Iterable[Path], now: datetime = FIXTURE_NOW) -> None:
    """Give the files of native logs a time of change two settle times before the instant
    `now`, so that a reading at `now` takes every session as settled (GLOSSARY › Settle
    time). Each path is a file of native logs, or a folder that holds them at any depth."""
    moment = now.timestamp() - 2 * SETTLE_TIME
    for path in paths:
        for held in (path.rglob("*.jsonl") if path.is_dir() else (path,)):
            os.utime(held, (moment, moment))


def remote_repository(work: Path, url: str) -> Path:
    """The working folder `work`, with a repository whose remote `origin` names the URL, so
    that the ingestion resolves the repository identity of the sessions that work there.
    The `.git` folder and its `config` are written by hand, the only git file that the
    identity reads (ADR 0004: no test runs git); a folder that holds the repository already
    gets the URL in the place of the earlier one."""
    (work / ".git").mkdir(parents=True, exist_ok=True)
    (work / ".git" / "config").write_text(
        f'[remote "origin"]\n    url = {url}\n', encoding="utf-8")
    return work


def stored_events(store_folder: Path) -> list[tuple[Event, str]]:
    """Every event that the segments of the store hold, each copy of each event key on its
    own, as the event and the name of the segment that holds it — the shape that
    `events.winning_copy` compares — in the order of the segments and of their lines, read
    through the readers of the store. A last line without a line break gives nothing, and a
    broken line no event."""
    found: list[tuple[Event, str]] = []
    for name in segment_names(store_folder):
        for line in read_lines(store_folder, name):
            decoded = decode_line(line.data)
            if decoded.event is not None:
                found.append((decoded.event, name))
    return found


def copy_segments(source: World, target: World, cut_last_line: bool) -> None:
    """The file-sync service between two machines, as a test drives it: one call is one
    moment at which the service delivered what the machine of `source` wrote.

    The service delivers the segments of the source machine alone, the files
    `segments/<machine of the source>/*.jsonl` of the source store: they are created or
    replaced in the target store, as after a purge rewrote a segment in the source; every
    other file of the target stays, its own segments and those of any third machine, which
    the service never writes, since two machines never write the same file. A source store
    and a target store that are one folder leave the service nothing to deliver, and the
    call raises `AssertionError`.

    The service copies segments and nothing else: no store metadata, no person
    configuration, no frozen report. A test that needs those shared gives its two worlds
    one store folder.

    With `cut_last_line` true, every file it writes stops before the last line break of the
    file of the source: the target holds the complete lines before it and a last line
    without a line break, the line that the service is still carrying. A later call without
    the cut completes it.

    It changes nothing in the source store.
    """
    assert source.store != target.store, "one store folder: nothing to deliver"
    prefix = f"segments/{source.machine}/"
    for name in segment_names(source.store):
        if not name.startswith(prefix):
            continue
        data = (source.store / name).read_bytes()
        if cut_last_line and b"\n" in data:
            data = data[:data.rfind(b"\n")]
        target_file = target.store / name
        target_file.parent.mkdir(parents=True, exist_ok=True)
        target_file.write_bytes(data)


def fixture_uids() -> Callable[[], str]:
    """A maker of the identifiers that the context of a fixture store or of a world gives
    to the events that the commands of a test write and to its frozen reports: it counts
    `FIXTURE_FIRST_UID`, `…2`, and so on, fresh at every call, so the first command of a
    test that writes always receives `FIXTURE_FIRST_UID`, whatever the build of the store
    wrote before."""
    counter = [0]

    def new_uid() -> str:
        counter[0] += 1
        return f"00000000-0000-4000-8000-{counter[0]:012d}"

    return new_uid


def build_uid(position: int) -> str:
    """The identifier that the build of a fixture store gave to the event of its scenario
    at the position given, first, second, and so on, in the namespace of the build, which
    no identifier of a command of a test ever reaches."""
    return f"10000000-0000-4000-8000-{position:012d}"


def _build_uids() -> Callable[[], str]:
    """A maker of the identifiers of the build of a fixture store, which counts from the
    first of its own namespace."""
    counter = [0]

    def new_uid() -> str:
        counter[0] += 1
        return build_uid(counter[0])

    return new_uid


def fixture_store_folder(home: Path) -> Path:
    """The store folder that `fixture_store` wrote below the temporary home."""
    return home / FIXTURE_STORE_FOLDER


def fixture_logs_folder(home: Path) -> Path:
    """The folder of native logs that `fixture_store` wrote below the temporary home."""
    return home / FIXTURE_LOGS_FOLDER


def store_figures(context: Context, store: Path, first: date, last: date) -> Figures:
    """The figures of the days of the store folder from the day `first` to the day `last`,
    both ends included, through the one pipeline that every report command shares
    (`figures_of_days`), with the person configuration of the store folder and the
    defaults of the report parameters (architecture.md › Tests)."""
    person = read_person_configuration(store)
    parameters, _layers = resolve_parameters({}, person)
    return figures_of_days(context, store, person, parameters, first, last)


def fixture_store(name: str, home: Path) -> Context:
    """The store of the report fixture `name` in the temporary home, and the context of
    the tests that read it (architecture.md › Tests › Report tests).

    The store is built afresh at every call, into the temporary home that the test made:
    it stands in the world that `world` makes there with the machine `FIXTURE_MACHINE`,
    the native logs are written by hand with invented text and read by the real
    ingestion, the configurations are written with the functions of `configuration`, and
    every declared event and every frozen report is written by the real command through
    `main`.

    The person of every store keeps one time zone, `Etc/UTC`, valid from the start of
    1970, and one day start hour, 00:00, so every instant below is both the UTC instant
    and the local time. The report parameters are the defaults of the ledger: idle gap 10
    minutes, minimum attention 1 minute, stale limit 4 hours, headless prompts no,
    timesheet granularity 15 minutes. The two projects are `FIXTURE_PROJECTS`; each
    works in its repository of `FIXTURE_FOLDERS`, whose remote URL names the repository
    identity of `FIXTURE_IDENTITIES`, and one identity rule per repository resolves its
    events to the project, so no share of an inferred repository identity is above 0.0.
    Every record of a session carries the entrypoint `cli` (`_FIXTURE_ENTRYPOINT`), so
    the share of human signals of unknown invocation is 0.0 on every fixture day. The
    context of the tests carries `FIXTURE_NOW`, `FIXTURE_VERSION`, the running system,
    the adapters of the temporary home, the fixed time zone, and a maker of identifiers
    that counts from `FIXTURE_FIRST_UID`; the machine configuration holds
    `FIXTURE_MACHINE` and the salted hash of the installation of the context, so that
    `before_write()` keeps the machine identifier and no command of a test spends an
    identifier on it. The store metadata of the machine holds the machine label
    `FIXTURE_LABEL` in the stores of `FIXTURE_LABELLED`, `annotations` and `frozen_period`,
    written before the build, and no label in the other stores. Every fact that defines a
    figure of a store is stated here, so a person computes each value of an expected file
    by hand.

    measured_day: the day `FIXTURE_DAY_ONE`. One session, `session-alpha`, in `alpha`:
    one prompt of the person at 09:00 and one output of the model at 09:05. The one human
    signal counts the minimum attention, which ends at the signal, so the measured human
    time of `alpha` is the 60 seconds from 08:59 to 09:00; the turn from the prompt to
    the output gives `alpha` 300 seconds of agent time. No manual entry, no confirmation:
    the day is measured, its total is 60 seconds, and its proposal is one entry for
    `alpha` of 900 seconds, rounded up to the granularity.

    declared_day: the day `FIXTURE_DAY_THREE`. One session, `session-alpha`, in `alpha`:
    one prompt at 10:00 and one output at 10:20, so 60 seconds of measured human time
    (from 09:59 to 10:00) and 1200 seconds of agent time. The builder runs `timesheet
    confirm` for the day one hour before `FIXTURE_NOW`, at 2026-11-24T11:00:00.000Z, which
    confirms the proposal: one entry for `alpha` of 900 seconds, the event of
    `build_uid(1)`, with that instant as its timestamp and its `ingested_at`, so a
    confirmation that a test writes at `FIXTURE_NOW` comes after it, as a person confirms
    a day again. The day is declared; its total is 900 seconds and its measured total 60.

    manual_entries: the day `FIXTURE_DAY_ONE`. One session, `session-alpha`, in `alpha`:
    one prompt at 09:00 and one output at 09:05, so 60 seconds of measured human time of
    `alpha`, from 08:59 to 09:00, and 300 seconds of agent time. The builder writes two
    manual entries of `beta` through `entry add`: one of mode `overlapping` from 08:50
    to 09:10, which covers the measured human time of `alpha` and makes the report warn
    `manual_entry_overlap`, and one of mode `additional` from 09:30 to 09:50, which meets
    no measured human time and warns nothing. With the manual entries, `beta` holds 1200
    + 1200 = 2400 seconds and `alpha` none, so the total of the day is 2400 seconds, its
    measured total 60, and its proposal one entry for `beta` of 2700 seconds.

    annotations: the day `FIXTURE_DAY_ONE`. `session-alpha` in `alpha`, with one prompt
    at 09:00 and one output at 09:20; `session-beta` in `beta`, with one prompt at 11:00.
    The builder annotates: the session annotation gives `session-alpha` to `alpha` with
    the work item `story-1`, and the interval annotation from 11:00 to 12:00 gives `beta`
    the work item `story-2`. The buckets of the day are (`alpha`, `story-1`) with 60
    seconds of human time (08:59 to 09:00) and 1200 of agent time, and (`beta`,
    `story-2`) with 60 seconds of human time (10:59 to 11:00) and no agent time. The two
    signals are further apart than the idle gap, so the presence span is 7200 seconds and
    each signal counts its own minimum attention. The day is measured.

    retraction: the day `FIXTURE_DAY_ONE`. One session, `session-alpha`, in `alpha`, with
    one prompt at 09:00 and one output at 09:10, so 60 seconds of measured human time and
    600 seconds of agent time. The builder writes one manual entry of `beta` in mode
    `additional` from 12:00 to 13:00 — the event of `build_uid(1)` — and retracts it
    through `retract`: the entry counts nothing, so the day holds `alpha` alone, and the
    store holds the manual entry and its retraction, the event of `build_uid(2)`.

    frozen_period: the days `FIXTURE_DAY_ONE` and `FIXTURE_DAY_TWO`. `session-alpha` in
    `alpha` on the first day, one prompt at 09:00 and one output at 09:40, so 60 seconds
    of measured human time and 2400 of agent time; `session-beta` in `beta` on the second
    day, one prompt at 10:00 and one output at 10:15, so 60 seconds and 900 seconds. The
    person configuration holds no identity rule for `beta` at the freeze, so the events
    of the second day resolve to the repository identity `example.com/acme/beta` itself,
    shown by its default name `beta`. The builder runs `report timesheet --freeze` over
    the period, with the note of `FIXTURE_NOTES`: the frozen report is the event of
    `build_uid(1)`, kept at the instant `FIXTURE_NOW`. Then it adds the identity rule of
    `beta` through `config add`: a report of now resolves the second day to `beta`, shown
    as `Beta`, and shows its differences against the frozen report.

    frozen_day: the day `FIXTURE_DAY_ONE`, with the events and the two annotations of the
    `annotations` store. The builder runs `report day --freeze` with a minimum attention
    of two minutes — the frozen report is the event of `build_uid(3)`, at the instant
    `FIXTURE_NOW`; each prompt then counts 120 seconds of human time — and then writes one
    additional manual entry of an hour on the work item `story-1`, from 14:00 to 15:00,
    the event of `build_uid(4)`. A report of now, at the minimum attention of one minute
    and with the manual entry, shows its differences against the frozen report: every
    figure of the person, of each project, and of each work item that differs.

    parallel_agents: the day `FIXTURE_DAY_ONE`. `session-alpha` in `alpha`, with one
    prompt at 09:00 and one output at 09:20; `session-beta` in `beta`, with one prompt at
    09:10 and one output at 09:20. The two agents work in parallel from 09:10 to 09:20,
    so the agent time of the person is the sum over its agents, 1200 + 600 = 1800
    seconds, over a union of 1200 seconds: its parallel ratio is 1.5, the ratio of each
    project 1.0, and the agent time of the person is longer than the clock time in which
    its agents work. The prompts are 600 seconds apart, not more than the idle gap, so
    the signal gap between them, from 09:00 to 09:10, belongs to the later signal, the
    prompt of `session-beta`, and the prompt of `session-alpha` counts its minimum
    attention: the human time of the person is 660 seconds, Beta 600 and Alpha 60. The
    person is present from 08:59 to 09:10 and its agents work from 09:00 to 09:20, so it
    is supervised 600 seconds, person only 60, unattended 600, blocked 0, and idle the
    rest of the day. The presence span is 600 seconds, the total of the day 660, and the
    human time at the idle gaps 120 seconds at 5 minutes and 660 at 10 and at 15.
    """
    if name not in FIXTURE_NAMES:
        raise ValueError(f"unknown fixture store: {name}")
    built = world(home, FIXTURE_MACHINE, new_uid=_build_uids())
    inside = inside_folder(built.context, built.store)
    inside.mkdir(parents=True, exist_ok=True)
    for entry, values in _person_entries(name):
        append_entry(built.store, inside / LOCK_FILE, entry, values)
    if name in FIXTURE_LABELLED:
        write_label(built.store, FIXTURE_MACHINE, FIXTURE_LABEL)
    _BUILDERS[name](built)
    return built.context._replace(new_uid=fixture_uids())


def _person_entries(name: str) -> list[tuple[str, dict[str, str]]]:
    """The entries of the person configuration of one fixture store, after the time zone
    and the day start hour that the creation writes: the two projects, one identity rule
    per repository — no rule for `beta` in the frozen period, which gets it after the
    freeze — and, in the annotations stores, the two work items."""
    entries: list[tuple[str, dict[str, str]]] = [
        ("project", {"id": "alpha", "name": FIXTURE_PROJECTS["alpha"]}),
        ("project", {"id": "beta", "name": FIXTURE_PROJECTS["beta"]}),
        ("identity_rule", {"project": "alpha",
                           "repository": FIXTURE_IDENTITIES["alpha"]}),
    ]
    if name != "frozen_period":
        entries.append(("identity_rule", {"project": "beta",
                                          "repository": FIXTURE_IDENTITIES["beta"]}))
    if name in ("annotations", "frozen_day"):
        for (project, identifier), shown in FIXTURE_WORK_ITEMS.items():
            entries.append(("work_item", {"project": project, "id": identifier,
                                          "name": shown}))
    return entries


_RECORDS_IDS = "7f1c0000-0000-4000-8000-{0:012x}"
"""The form of the native identifier of each record of a fixture session, fresh at every
build, so every build writes the same records."""


def _fixture_ids() -> Callable[[], str]:
    """A maker of the native identifiers of the records of one fixture build, fresh at
    every call."""
    counter = [0]

    def native_id() -> str:
        counter[0] += 1
        return _RECORDS_IDS.format(counter[0])

    return native_id


def _prompt(instant: str, native_id: str, text: str) -> dict[str, Any]:
    """A prompt of the person of a fixture session, typed in the interactive invocation."""
    return {**prompt_record(text, instant, native_id), "entrypoint": _FIXTURE_ENTRYPOINT}


def _answer(instant: str, native_id: str, response_id: str, text: str) -> dict[str, Any]:
    """One output of the model that answers the prompt of a fixture session."""
    return output_record(text, instant, native_id, response_id)


def _session_records(
    start: str,
    end: str,
    native_ids: Callable[[], str],
    prompt_text: str,
    answer_text: str,
) -> list[dict[str, Any]]:
    """The records of a fixture session that holds one prompt of the person and one
    output of the model that answers it."""
    return [_prompt(start, native_ids(), prompt_text),
            _answer(end, native_ids(), f"response-{start[:16]}", answer_text)]


def _project_repository(fixture: World, project: str) -> Path:
    """The working folder of one project of a fixture, in the world of the fixture: its
    repository names the identity of the project, which the identity rule of the person
    matches."""
    return remote_repository(fixture.home / FIXTURE_FOLDERS[project],
                             f"https://{FIXTURE_IDENTITIES[project]}.git")


def run_main(context: Context, *words: str) -> tuple[int, str, str]:
    """One command through `main` with the context given, as a test of the output of a
    command runs it: its exit code, its standard output, and its standard error. `_run`
    builds a fixture store on it and stops at any line of the standard error."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(words), context)
    return code, stdout.getvalue(), stderr.getvalue()


def _run(context: Context, *words: str) -> None:
    """One command of a fixture build through `main` with the context of the build; a
    command that stops, or that writes a line of warning or error, stops the build, so a
    fixture never rests on a step that its scenario did not mean."""
    code, _, stderr = run_main(context, *words)
    if code != 0 or stderr:
        raise AssertionError(f"the build of the fixture store stopped at {words}: "
                             f"exit {code}, standard error: {stderr}")


def _build_measured_day(fixture: World) -> None:
    """The measured day: one session with one prompt and one output, no declared event."""
    native_ids = _fixture_ids()
    cwd = _project_repository(fixture, "alpha")
    write_session(fixture.logs[0], "session-alpha",
                  _session_records("2026-11-20T09:00:00.000Z", "2026-11-20T09:05:00.000Z",
                                   native_ids, "Invented prompt of the measured day.",
                                   "Invented answer of the measured day."), {}, cwd)
    settle(fixture.logs)
    _run(fixture.context, "ingest")


def _build_declared_day(fixture: World) -> None:
    """The declared day: one session, then the confirmation of the proposal through
    `timesheet confirm`, one hour before `FIXTURE_NOW`."""
    native_ids = _fixture_ids()
    cwd = _project_repository(fixture, "alpha")
    write_session(fixture.logs[0], "session-alpha",
                  _session_records("2026-11-23T10:00:00.000Z", "2026-11-23T10:20:00.000Z",
                                   native_ids, "Invented prompt of the declared day.",
                                   "Invented answer of the declared day."), {}, cwd)
    settle(fixture.logs)
    _run(fixture.context, "ingest")
    _run(fixture.context._replace(now=FIXTURE_NOW - timedelta(hours=1)),
         "timesheet", "confirm", FIXTURE_DAY_THREE.isoformat())


def _build_manual_entries(fixture: World) -> None:
    """The manual entries: one session, then one entry of each mode through `entry add`,
    the overlapping one over the measured human time of `alpha`, which the minimum
    attention puts before the prompt, the additional one beside it."""
    native_ids = _fixture_ids()
    cwd = _project_repository(fixture, "alpha")
    write_session(fixture.logs[0], "session-alpha",
                  _session_records("2026-11-20T09:00:00.000Z", "2026-11-20T09:05:00.000Z",
                                   native_ids, "Invented prompt of the manual entries.",
                                   "Invented answer of the manual entries."), {}, cwd)
    settle(fixture.logs)
    _run(fixture.context, "ingest")
    _run(fixture.context, "entry", "add", "--from", "2026-11-20T08:50", "--to",
         "2026-11-20T09:10", "--project", "beta", "--mode", "overlapping",
         "--note", FIXTURE_NOTES["overlapping"])
    _run(fixture.context, "entry", "add", "--from", "2026-11-20T09:30", "--to",
         "2026-11-20T09:50", "--project", "beta", "--mode", "additional",
         "--note", FIXTURE_NOTES["additional"])


def _build_annotations(fixture: World) -> None:
    """The annotations: two sessions, then one annotation of the first session and one
    annotation of an interval through `annotate`."""
    native_ids = _fixture_ids()
    alpha = _project_repository(fixture, "alpha")
    beta = _project_repository(fixture, "beta")
    write_session(fixture.logs[0], "session-alpha",
                  _session_records("2026-11-20T09:00:00.000Z", "2026-11-20T09:20:00.000Z",
                                   native_ids, "Invented prompt of the annotated session.",
                                   "Invented answer of the annotated session."), {}, alpha)
    write_session(fixture.logs[0], "session-beta",
                  [_prompt("2026-11-20T11:00:00.000Z", native_ids(),
                           "Invented prompt of the second session.")], {}, beta)
    settle(fixture.logs)
    _run(fixture.context, "ingest")
    _run(fixture.context, "annotate", "--session", "session-alpha", "--project", "alpha",
         "--work-item", "story-1", "--note", FIXTURE_NOTES["session"])
    _run(fixture.context, "annotate", "--from", "2026-11-20T11:00", "--to",
         "2026-11-20T12:00", "--project", "beta", "--work-item", "story-2",
         "--note", FIXTURE_NOTES["interval"])


def _build_retraction(fixture: World) -> None:
    """The retraction: one session, then one manual entry through `entry add` and the
    retraction of it through `retract`, so the entry counts nothing any more."""
    native_ids = _fixture_ids()
    cwd = _project_repository(fixture, "alpha")
    write_session(fixture.logs[0], "session-alpha",
                  _session_records("2026-11-20T09:00:00.000Z", "2026-11-20T09:10:00.000Z",
                                   native_ids, "Invented prompt of the retraction.",
                                   "Invented answer of the retraction."), {}, cwd)
    settle(fixture.logs)
    _run(fixture.context, "ingest")
    _run(fixture.context, "entry", "add", "--from", "2026-11-20T12:00", "--to",
         "2026-11-20T13:00", "--project", "beta", "--mode", "additional",
         "--note", FIXTURE_NOTES["retracted"])
    _run(fixture.context, "retract", build_uid(1))


def _build_frozen_period(fixture: World) -> None:
    """The frozen period: one session on each of its two days, then `report timesheet`
    over the period with `--freeze`, which keeps its document as the frozen report, and,
    after the freeze, the identity rule of `beta` through `config add`."""
    native_ids = _fixture_ids()
    alpha = _project_repository(fixture, "alpha")
    beta = _project_repository(fixture, "beta")
    write_session(fixture.logs[0], "session-alpha",
                  _session_records("2026-11-20T09:00:00.000Z", "2026-11-20T09:40:00.000Z",
                                   native_ids, "Invented prompt of the first frozen day.",
                                   "Invented answer of the first frozen day."), {}, alpha)
    write_session(fixture.logs[0], "session-beta",
                  _session_records("2026-11-21T10:00:00.000Z", "2026-11-21T10:15:00.000Z",
                                   native_ids, "Invented prompt of the second frozen day.",
                                   "Invented answer of the second frozen day."), {}, beta)
    settle(fixture.logs)
    _run(fixture.context, "ingest")
    _run(fixture.context, "report", "timesheet", "--from", FIXTURE_DAY_ONE.isoformat(),
         "--to", FIXTURE_DAY_TWO.isoformat(), "--freeze", "--note", FIXTURE_NOTES["frozen"])
    _run(fixture.context, "config", "add", "identity-rule", "--project", "beta",
         "--repository", f"https://{FIXTURE_IDENTITIES['beta']}.git")


def _build_frozen_day(fixture: World) -> None:
    """The frozen day: the annotations of the `annotations` store, then `report day` of the
    day with `--freeze` at a minimum attention of two minutes, then one additional manual
    entry of an hour on the work item `story-1` through `entry add`."""
    _build_annotations(fixture)
    _run(fixture.context, "report", "day", FIXTURE_DAY_ONE.isoformat(), "--freeze",
         "--minimum-attention", "2min")
    _run(fixture.context, "entry", "add", "--from", "2026-11-20T14:00", "--to",
         "2026-11-20T15:00", "--project", "alpha", "--work-item", "story-1",
         "--mode", "additional")


def _build_parallel_agents(fixture: World) -> None:
    """The agents in parallel: two sessions of one machine whose turns overlap, one in
    each project, so the agent time of the person is the sum over its two agents over a
    union shorter than it (metrics.md › Agent time)."""
    native_ids = _fixture_ids()
    alpha = _project_repository(fixture, "alpha")
    beta = _project_repository(fixture, "beta")
    write_session(fixture.logs[0], "session-alpha",
                  _session_records("2026-11-20T09:00:00.000Z", "2026-11-20T09:20:00.000Z",
                                   native_ids, "Invented prompt of the first of two agents.",
                                   "Invented answer of the first of two agents."), {}, alpha)
    write_session(fixture.logs[0], "session-beta",
                  _session_records("2026-11-20T09:10:00.000Z", "2026-11-20T09:20:00.000Z",
                                   native_ids, "Invented prompt of the second of two agents.",
                                   "Invented answer of the second of two agents."), {}, beta)
    settle(fixture.logs)
    _run(fixture.context, "ingest")


_BUILDERS = {
    "measured_day": _build_measured_day,
    "declared_day": _build_declared_day,
    "manual_entries": _build_manual_entries,
    "annotations": _build_annotations,
    "retraction": _build_retraction,
    "frozen_period": _build_frozen_period,
    "frozen_day": _build_frozen_day,
    "parallel_agents": _build_parallel_agents,
}
"""The builder of each fixture store, which runs after the configurations are written."""


class FixtureStores(unittest.TestCase):
    """A test case whose class holds one build of every store of `STORES`, each in its
    own home below one temporary folder, from `setUpClass` to `tearDownClass`: the tests
    of a class only read the stores, so one build of each serves them all; a test that
    changes a store builds its own (architecture.md › Tests › Report tests)."""

    STORES: tuple[str, ...] = FIXTURE_NAMES
    """The fixture stores that the class builds, each by its name."""

    @classmethod
    def setUpClass(cls) -> None:
        """Build every store of the class once, each in its own home below one temporary
        folder."""
        cls._folder = TemporaryFolder()
        cls._base = cls._folder.__enter__()
        cls._homes: dict[str, Path] = {name: cls._base / name for name in cls.STORES}
        cls._contexts = {name: fixture_store(name, home)
                         for name, home in cls._homes.items()}

    @classmethod
    def tearDownClass(cls) -> None:
        cls._folder.__exit__(None, None, None)
