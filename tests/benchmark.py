"""The speed probe of the ledger: invented native logs with the record types of the adapter
fixtures, and four times, printed with the processor of the machine: the first ingestion of
the logs, the daily timesheet of one month of the store, and the timesheet and the report of
one day of it, the day being the last of the month. Every time is one command through the
command line, `cli.main` with a `Context` that the probe builds, never the one of the
running process (architecture.md › Tests; product.md › Phase 1, acceptance criterion 10);
the printed output says, for every time, what the timed span covers and what lies outside
it. The working folders of the sessions hold an invented repository each, so that the
figures hold the projects of the repositories and not only unattributed time.

No test of the suite runs it: a person runs it by hand with
`python -I tests/benchmark.py` before each release and writes the four times and the
processor in a dated note in `docs/research/`. The probe touches only the temporary folder
that it makes, or the one that `--folder` names.
"""

import argparse
import contextlib
import hashlib
import io
import json
import os
import platform
import sys
import tempfile
import uuid
import zlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from time import perf_counter
from typing import Any

from ai_effort_ledger import cli, days
from ai_effort_ledger.adapters import ClaudeCodeAdapter
from ai_effort_ledger.cli.arguments import PROGRAM
from ai_effort_ledger.configuration import (
    MachineConfiguration,
    create_person_configuration,
    write_machine_configuration,
)
from ai_effort_ledger.configuration.person import DEFAULT_SETTLE_TIME
from ai_effort_ledger.events import format_instant, writer_version
from ai_effort_ledger.ingestion.run import DEVELOPMENT_VARIABLE
from ai_effort_ledger.platform import machine_folder

SETTLE_TIME = DEFAULT_SETTLE_TIME
"""The settle time of the probe, two of which separate the time of change of every file of
a session from the instant of the run: the default of the reader of the person
configuration, so that the sessions of the probe are complete for the first ingestion
exactly as they are for a person who names no settle time."""

ZONE = "Etc/UTC"
"""The invented time zone of the person configuration of the probe, valid from the epoch,
so that the local days of the probe are the days of UTC; the day start hour follows it."""

MACHINE = "5d3f1a2b-4c6e-4a8d-9b0c-7e1f2a3b4c5d"
"""The invented machine identifier of the machine configuration of the probe."""

FORMAT_VERSION = "2.1.0"
"""The invented format version of the source that every record names, as in the fixtures."""

BRANCH = "main"
"""The invented branch that the session records of the probe name, as the records of the
fixtures do; a record of the queue names none, as in the fixtures."""

PERSON = "Example Person <person@example.org>"
"""The invented author of the root commit of each working folder of the probe."""

INSTANT = "1700000000 +0100"
"""The invented instant of the author line of the root commit."""

TREE = "0f1e2d3c4b5a69788796a5b4c3d2e1f00f1e2d3c"
"""The invented tree name that the root commit of each working folder names."""

CYCLE = 10
"""The records of one cycle of a session: a prompt, a response on two lines, an edit of a
file of the working folder with its result, a response, a message for the queue, a read of a
file with its result, and a response."""

LINE_STEP = 8
"""The seconds between two consecutive records of a session."""

PHASE_STEP = 137
"""The milliseconds that each session adds to the instants of its records, in the order of
the sessions of the probe: 137 shares no factor with 1000, so the phases repeat only after
1000 sessions, and while the probe writes at most 1000 sessions in total (`days` times
`sessions`) no two of them hold a record at the same instant. Beyond that bound two sessions
can share a phase, their records can land on the same instant, and the pair looks like a
forked session, which gives the events of one of them to the other; the defaults of the
probe stay far below the bound."""

MONTH = 30
"""The calendar days of the period that the timesheet half figures, whatever the span of
the logs: the daily timesheet of one month of the benchmark."""

PROJECTS = ("bramblewick", "fennwick", "hollowbrook")
"""The invented working folders that the sessions of the probe name as their cwd."""

PROMPTS = (
    "Invented prompt about the bramblewick module.",
    "Invented prompt that asks for the fennwick counts.",
    "Invented prompt on the hollowbrook imports.",
)
"""The texts of the prompts of the person; each is invented."""

OUTPUTS = (
    "Invented answer that names three parts of the bramblewick module.",
    "Invented answer that sums the fennwick counts by hand.",
    "Invented answer that lists the hollowbrook imports in order.",
)
"""The texts of the lines of the responses of the model; each is invented."""

QUEUED = (
    "Invented message typed while the agent worked on bramblewick.",
    "Invented message typed while the agent waited for the fennwick run.",
)
"""The texts of the messages that a person types while an agent works; each is invented."""

USAGE = (
    {"input_tokens": 10, "output_tokens": 5},
    {"input_tokens": 20, "output_tokens": 8, "cache_read_input_tokens": 4},
    {"input_tokens": 12, "output_tokens": 6,
     "cache_creation": {"ephemeral_5m_input_tokens": 3}},
)
"""The invented token counts that a line of a response holds."""


def write_native_logs(folder: Path, days: int, sessions: int, lines: int) -> int:
    """Write the invented native logs of the probe into `folder`: `sessions` files of `lines`
    records for each of `days` days, of the record types of the adapter fixtures, each record
    stamped with the working folder of its session below the home folder that `folder` sits
    in, and with the instants of its day. Every file takes a time of change two settle times
    in the past, so that the first ingestion reads every event of every session as complete.
    Returns the number of lines written."""
    folder.mkdir(parents=True, exist_ok=True)
    written = 0
    moment = datetime.now(timezone.utc).replace(microsecond=0)
    for day in range(days):
        start = moment - timedelta(days=day + 1)
        for number in range(sessions):
            order = day * sessions + number
            project = PROJECTS[order % len(PROJECTS)]
            _write_session(folder, str(uuid.uuid4()), project,
                           start + timedelta(hours=number), PHASE_STEP * order % 1000, lines)
            written += lines
    return written


def main(argv: list[str] | None = None) -> int:
    """Run the speed probe: write the invented native logs of the size that the options name,
    time the first ingestion of them, the daily timesheet of one month of the store, and the
    timesheet and the report of the last day of that month, all through `cli.main`, and
    print the lines, the new events, the four times with what each timed span covers, and
    the processor of this machine. Time zones come only from `tzdata`; the probe reads and
    writes only the temporary folder that it makes, or the one that `--folder` names, which a
    second run must not reuse, because the ingestion would no longer be the first one."""
    days.use_tzdata_only()
    options = _options(argv)
    if options.folder is None:
        with tempfile.TemporaryDirectory(prefix="ai_effort_ledger_benchmark_") as name:
            return _probe(Path(name), options.days, options.sessions, options.lines)
    return _probe(options.folder, options.days, options.sessions, options.lines)


def _options(argv: list[str] | None) -> argparse.Namespace:
    """The options of the probe: the size of the invented native logs and, when given, the
    folder of the probe, left in place after the run."""
    named = argparse.ArgumentParser(
        description="Time the first ingestion of invented native logs, the daily timesheet "
                    "of one month of them, and the timesheet and the report of one day "
                    "(architecture.md › Tests).")
    named.add_argument("--days", type=int, default=30, help="days of native logs (30)")
    named.add_argument("--sessions", type=int, default=10, help="sessions a day (10)")
    named.add_argument("--lines", type=int, default=1000, help="lines a session (1000)")
    named.add_argument("--folder", type=Path, default=None,
                       help="the folder of the probe, left in place (default: a temporary "
                            "folder that the run removes)")
    return named.parse_args(argv)


def _commands(month: list[date]) -> list[tuple[str, list[str]]]:
    """The four commands of the probe, in the order they run, each with the words that name
    it in the printed result: the first ingestion, the daily timesheet of the `month`, and
    the timesheet and the report of its last day."""
    day = month[-1].isoformat()
    return [
        ("the first ingestion", ["ingest"]),
        ("the daily timesheet of one month",
         ["report", "timesheet", "--from", month[0].isoformat(), "--to", month[-1].isoformat()]),
        ("the timesheet of one day", ["timesheet", day]),
        ("the report of one day", ["report", "day", day]),
    ]


def _probe(root: Path, day_count: int, session_count: int, line_count: int) -> int:
    """The probe in its folder: the home, the machine-local data folder, and the store folder
    of one machine of invented logs, with the two configurations that a set-up ledger holds;
    four commands through `cli.main` — the first ingestion of the logs, the daily timesheet
    of one month of the store, and the timesheet and the report of the last day of that
    month — each timed from its call to its end, the printed result saying, for every time,
    what the timed span covers and what lies outside it. A command that stops ends the probe
    with its exit code, after what the command wrote reaches the terminal."""
    home = root / "home"
    logs = home / ".claude" / "projects"
    total = write_native_logs(logs, day_count, session_count, line_count)
    context = _context(root)
    data_folder = Path(machine_folder(context.system, context.environ, home))
    data_folder.mkdir(parents=True, exist_ok=True)
    store = root / "store"
    store.mkdir(parents=True, exist_ok=True)
    write_machine_configuration(data_folder, MachineConfiguration(
        machine=MACHINE, installation=None, salt=None, store=str(store),
        native_logs={"claude-code": [str(logs)]}))
    create_person_configuration(store, ZONE)
    taken: list[tuple[str, list[str], float]] = []
    new_events = 0
    entries = 0
    for name, argv in _commands(_month(context.now.date())):
        seconds, code, out, err = _timed([*argv, "--json"], context)
        if code != 0:
            return _stopped(code, out, err)
        sys.stderr.write(err)
        taken.append((name, argv, seconds))
        document = json.loads(out)
        if argv[0] == "ingest":
            new_events = sum(source["new_events"] for source in document["sources"])
        if argv[0] == "report" and argv[1] == "timesheet":
            entries = sum(len(day["entries"]) for day in document["days"])
    print(f"lines: {total}")
    print(f"new events: {new_events}")
    print(f"timesheet entries: {entries}")
    print()
    print("Each time is one command through `cli.main`, timed from its call to its end: in the"
          " time are the reading of the two configurations, the command, and the JSON document"
          " that it writes into a stream in memory; outside every time are the start of the"
          " interpreter and the imports, and the writing of the invented native logs.")
    print()
    for name, argv, seconds in taken:
        print(f"{name}, `{' '.join(argv)} --json`: {seconds:.3f} s")
    print(f"processor: {processor()}")
    return 0


def _context(root: Path) -> cli.Context:
    """The context of the commands of the probe, built here and never taken from the
    running process: the home and the machine-local data folders below the folder of the
    probe, the instant of the run, a call of a scheduler program that no command of the
    probe reaches, no installation identifier, so that the guard of a write keeps the
    invented machine identifier, no question, the adapter of the temporary home, the
    invented time zone, and the version of this checkout."""
    home = root / "home"
    return cli.Context(
        system=platform.system(),
        environ=_environ(root),
        home=home,
        now=datetime.now(timezone.utc),
        new_uid=lambda: str(uuid.uuid4()),
        run=_no_program,
        executable=Path(PROGRAM),
        installation=None,
        ask=None,
        adapters=[ClaudeCodeAdapter(managed_file=home / "managed-settings.json")],
        time_zone=lambda: ZONE,
        version=writer_version(),
        uid=os.getuid() if hasattr(os, "getuid") else None,
    )


def _environ(root: Path) -> dict[str, str]:
    """The environment of the commands of the probe: `AI_EFFORT_LEDGER_DEVELOPMENT=1`, which
    lets the development version of this checkout write to the store (architecture.md ›
    Runtime), and the machine-local data folders of every operating system below the folder
    of the probe, so that no command writes outside it."""
    return {
        DEVELOPMENT_VARIABLE: "1",
        "LOCALAPPDATA": str(root / "app-data"),
        "XDG_STATE_HOME": str(root / "state"),
        "XDG_DATA_HOME": str(root / "share"),
    }


def _no_program(words: list[str]) -> None:
    """The call of a scheduler program, which no command of the probe reaches: the probe
    ingests and reports, and never sets up a schedule."""
    raise AssertionError(f"no command of the probe runs a scheduler program: {words}")


def _timed(argv: list[str], context: cli.Context) -> tuple[float, int, str, str]:
    """One command of the probe through `cli.main`, in JSON: the seconds from its call to
    its end, its exit code, and what it wrote to the standard output and to the standard
    error, which stay off the terminal while the command is timed."""
    out, err = io.StringIO(), io.StringIO()
    start = perf_counter()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli.main([*argv, "--json"], context)
    return perf_counter() - start, code, out.getvalue(), err.getvalue()


def _stopped(code: int, out: str, err: str) -> int:
    """End the probe where one of its commands stopped: what the command wrote goes to the
    terminal, and its exit code is the exit code of the probe."""
    sys.stdout.write(out)
    sys.stderr.write(err)
    return code


def _month(end: date) -> list[date]:
    """The `MONTH` calendar days of the period of the timesheet, up to and including `end`."""
    return [end - timedelta(offset) for offset in range(MONTH - 1, -1, -1)]


def processor() -> str:
    """The processor of this machine, or its machine type when the processor is not named."""
    named = platform.processor()
    return named if named else platform.machine()


def _write_session(
    folder: Path, session_id: str, project: str, start: datetime, phase: int, lines: int,
) -> None:
    """Write the file of one session, and give it a time of change two settle times in the
    past, so that the reading of the ingestion takes every event of it as complete."""
    cwd = folder.parent / "work" / project
    cwd.mkdir(parents=True, exist_ok=True)
    _own_repository(cwd, project)
    lines_of_file = []
    for record in _records(cwd, start, phase, lines):
        stamped = dict(record)
        stamped["sessionId"] = session_id
        stamped["cwd"] = str(cwd)
        lines_of_file.append(
            json.dumps(stamped, separators=(",", ":"), ensure_ascii=False))
    path = folder / f"{session_id}.jsonl"
    path.write_text("".join(line + "\n" for line in lines_of_file), encoding="utf-8")
    settled = datetime.now(timezone.utc).timestamp() - 2 * SETTLE_TIME
    os.utime(path, (settled, settled))


def _own_repository(cwd: Path, project: str) -> None:
    """Give the working folder its own repository, as the working folders of the scenarios
    hold: a `.git` folder that holds one root commit, to which `HEAD` points through
    `refs/heads/main`, built by hand and read without running git (ADR 0004). The message
    of the commit names the project, so that the working folders of the probe resolve to
    their own repository identity and their own project."""
    git_folder = cwd / ".git"
    git_folder.mkdir(parents=True, exist_ok=True)
    (git_folder / "config").write_text(
        "[core]\n    repositoryformatversion = 0\n", encoding="utf-8")
    name = _write_loose_object(git_folder, _commit_object(project))
    (git_folder / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    reference = git_folder / "refs" / "heads" / "main"
    reference.parent.mkdir(parents=True, exist_ok=True)
    reference.write_text(name + "\n", encoding="utf-8")


def _commit_object(project: str) -> bytes:
    """The content of one root commit object, with the invented person, instant, and a
    message that names the project of the working folder."""
    return (f"tree {TREE}\n"
            f"author {PERSON} {INSTANT}\n"
            f"committer {PERSON} {INSTANT}\n"
            f"\nInvented root commit of the {project} working folder of the probe.\n"
            ).encode("utf-8")


def _write_loose_object(git_folder: Path, content: bytes) -> str:
    """Write the commit as one loose object under `objects/` and return its name."""
    header = b"commit " + str(len(content)).encode() + b"\0"
    name = hashlib.sha1(header + content).hexdigest()
    folder = git_folder / "objects" / name[:2]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name[2:]).write_bytes(zlib.compress(header + content))
    return name


def _records(cwd: Path, start: datetime, phase: int, count: int) -> list[dict[str, Any]]:
    """The records of one session, `count` long at `LINE_STEP` seconds from `start` on, in
    the cycle of the probe; the instants carry the milliseconds of the phase of the session."""
    records: list[dict[str, Any]] = []
    message_id = ""
    call_id = ""
    for number in range(count):
        step = number % CYCLE
        instant = format_instant(
            start + timedelta(seconds=number * LINE_STEP, milliseconds=phase))
        uid = uuid.uuid4().hex
        file_path = str(cwd / f"module_{number % 5}.py")
        if step in (1, 5, 9):
            message_id = f"msg-{uid}"
        if step == 0:
            records.append(_prompt(instant, uid, PROMPTS[number % len(PROMPTS)]))
        elif step in (1, 2, 5, 9):
            records.append(_response(instant, uid, message_id,
                                     OUTPUTS[number % len(OUTPUTS)],
                                     USAGE[number % len(USAGE)]))
        elif step == 3:
            call_id = f"toolu-{uid}"
            records.append(_file_edit(instant, uid, message_id, call_id, file_path))
        elif step == 4:
            records.append(_file_result(instant, uid, call_id, file_path))
        elif step == 6:
            records.append(_queued(instant, QUEUED[number % len(QUEUED)]))
        elif step == 7:
            call_id = f"toolu-{uid}"
            records.append(_file_read(instant, uid, message_id, call_id, file_path))
        elif step == 8:
            records.append(_file_result(instant, uid, call_id, None))
    return records


def _prompt(at: str, uid: str, text: str) -> dict[str, Any]:
    """A `user` record that holds a prompt of the person; the text is invented."""
    return {
        "type": "user",
        "uuid": uid,
        "timestamp": at,
        "version": FORMAT_VERSION,
        "gitBranch": BRANCH,
        "entrypoint": "cli",
        "origin": {"kind": "human"},
        "message": {"role": "user", "content": text},
    }


def _response(
    at: str, uid: str, message_id: str, text: str, usage: dict[str, Any],
) -> dict[str, Any]:
    """A record of the agent that holds one line of a response of the model; the text and the
    token counts are invented, and the lines of one response share the native identifier of
    their message."""
    return {
        "type": "assistant",
        "uuid": uid,
        "timestamp": at,
        "version": FORMAT_VERSION,
        "gitBranch": BRANCH,
        "entrypoint": "cli",
        "message": {
            "id": message_id,
            "model": "Invented-Model",
            "usage": dict(usage),
            "content": [{"type": "text", "text": text}],
        },
    }


def _file_edit(
    at: str, uid: str, message_id: str, call_id: str, file_path: str,
) -> dict[str, Any]:
    """A record of the agent whose content holds one use of the edit tool on a file of the
    working folder; the change is invented."""
    return {
        "type": "assistant",
        "uuid": uid,
        "timestamp": at,
        "version": FORMAT_VERSION,
        "gitBranch": BRANCH,
        "entrypoint": "cli",
        "message": {
            "id": message_id,
            "model": "Invented-Model",
            "usage": {},
            "content": [{"type": "tool_use", "id": call_id, "name": "Edit",
                         "input": {"file_path": file_path,
                                   "old_string": "alpha", "new_string": "beta"}}],
        },
    }


def _file_read(
    at: str, uid: str, message_id: str, call_id: str, file_path: str,
) -> dict[str, Any]:
    """A record of the agent whose content holds one use of the read tool on a file of the
    working folder."""
    return {
        "type": "assistant",
        "uuid": uid,
        "timestamp": at,
        "version": FORMAT_VERSION,
        "gitBranch": BRANCH,
        "entrypoint": "cli",
        "message": {
            "id": message_id,
            "model": "Invented-Model",
            "usage": {},
            "content": [{"type": "tool_use", "id": call_id, "name": "Read",
                         "input": {"file_path": file_path}}],
        },
    }


def _file_result(at: str, uid: str, call_id: str, file_path: str | None) -> dict[str, Any]:
    """A `user` record whose content holds the result of one use of a tool; the result of an
    edit also holds the invented patch that the size counters come from."""
    record: dict[str, Any] = {
        "type": "user",
        "uuid": uid,
        "timestamp": at,
        "version": FORMAT_VERSION,
        "gitBranch": BRANCH,
        "entrypoint": "cli",
        "message": {
            "role": "user",
            "content": [{"type": "tool_result", "tool_use_id": call_id,
                         "content": "Invented result text of the tool."}],
        },
    }
    if file_path is not None:
        record["toolUseResult"] = {
            "type": "update",
            "filePath": file_path,
            "structuredPatch": [{"oldStart": 1, "oldLines": 1, "newStart": 1, "newLines": 2,
                                 "lines": ["-alpha", "+beta one", "+beta two"]}],
        }
    return record


def _queued(at: str, text: str) -> dict[str, Any]:
    """A `queue-operation` record that holds a message typed while the agent worked; the text
    is invented and the record gives no native identifier."""
    return {
        "type": "queue-operation",
        "operation": "enqueue",
        "content": text,
        "timestamp": at,
        "version": FORMAT_VERSION,
    }


if __name__ == "__main__":
    sys.exit(main())
