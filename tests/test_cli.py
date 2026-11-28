"""Tests of the cli module: the context of one run, the outcome of an action and its
output, the exit codes, the requirement of a set-up ledger, the guards of every action
that writes, the arguments of the commands, their help, and `main`
(command-line.md › Form, › Output, › Exit codes, › Commands, › Setup, › JSON documents)."""

import argparse
import contextlib
import importlib
import io
import json
import os
import pkgutil
import shutil
import subprocess
import sys
import unittest
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path, PurePath
from platform import system as running_system
from types import ModuleType
from typing import NamedTuple
from unittest import mock

import support
import ai_effort_ledger
from ai_effort_ledger import (
    configuration,
    days,
    events,
    ingestion,
    language,
    platform,
    store,
)
from ai_effort_ledger.adapters import (
    Adapter,
    ReadContext,
    ReadResult,
    Retention,
    SessionFiles,
)
from ai_effort_ledger.cli import _ask as cli_ask
from ai_effort_ledger.cli import (
    ACTIONS,
    INCOMPLETE_CODES,
    LOCALTIME,
    Context,
    Outcome,
    WrongUse,
    _installed_executable,
    _run_program,
    build_arguments,
    check_values,
    emit,
    figures,
    json_document,
    main,
    resolved_store,
    stopped,
)
from ai_effort_ledger.cli.arguments import (
    DAY_WORDS,
    PROGRAM,
    _fault_of,
    read_day,
    read_hour,
    read_instant,
    read_instant_or_day,
)
from ai_effort_ledger.cli.figures import Figures, report_warnings
from ai_effort_ledger.configuration.person import PERSON_FILE
from ai_effort_ledger.ingestion.run import DEVELOPMENT_VARIABLE

SYSTEM = running_system()
"""The system of the machine that runs the tests; every context of the tests gives it."""
NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)
"""The instant of every context of the tests."""
ZONE = "Etc/UTC"
"""The IANA time zone that the fixed time zone of the contexts gives."""
VERSION = "0.1.0"
"""A release version of the ledger for the contexts of the tests."""
DEV_VERSION = "0.1.0.dev0"
"""A version with a development mark, which the guard of the tests refuses or allows."""
EXECUTABLE = Path("D:/Work/Product/ai-effort-ledger")
"""The absolute path of the installed command, invented."""
INSTALLATION_ONE = "Installation-One-2026"
"""The installation identifier that the contexts of the tests give first."""
INSTALLATION_TWO = "Installation-Two-2026"
"""The installation identifier of the machine that the home folder was copied to."""
MACHINE = "machine-one"
"""The machine identifier that a set-up world of the tests holds."""
OTHER_MACHINE = "7f6e5d4c-3b2a-4c1d-8e9f-0a1b2c3d4e5f"
"""The machine identifier of another machine, whose segment a purge never rewrites."""
SETTLE = 14400
"""The settle time of the person configuration that setup creates, in seconds."""
PROMPT_AT = "2026-11-20T09:15:00.000Z"
"""The instant that the prompt record of the tests holds."""
UUID_ONE = "3f1c0000-0000-4000-8000-0000000000a1"
"""The native identifier of the prompt record of the tests."""
PROMPT_KEY = '{"source": "claude-code-jsonl", "native_id": "%s"}' % UUID_ONE
"""The event key of the prompt record of the tests, as its JSON object."""
SCHEDULER_PROGRAM = {"windows": "schtasks", "launchd": "launchctl", "systemd": "systemctl"}
"""The program whose name the `scheduler_failed` stop error of each scheduler kind holds."""


class AnyValues(dict):
    """Values that answer every placeholder with its name in braces, so a test renders the
    text of a code whose values it does not hold."""

    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def test_environ(base: Path, **extra: str) -> dict[str, str]:
    """The environment of the tests: the local data folders of the system inside the
    temporary folder, and the variable that lets a development version write."""
    environ = {
        DEVELOPMENT_VARIABLE: "1",
        "LOCALAPPDATA": str(base / "app-data"),
        "XDG_STATE_HOME": str(base / "state"),
        "XDG_DATA_HOME": str(base / "share"),
    }
    environ.update(extra)
    return environ


class World(NamedTuple):
    """The folders and the environment of one test: the home of the person, the store
    folder, the machine-local data folder, and the environment the contexts give."""

    home: Path
    store: Path
    machine: Path
    environ: dict[str, str]


def build_world(base: Path, **extra: str) -> World:
    """The world of a test: a home folder, and the machine-local data folder and the store
    folder inside the temporary folder, both reached through the environment."""
    home = base / "home"
    home.mkdir(parents=True)
    environ = test_environ(base, **extra)
    machine = Path(platform.machine_folder(SYSTEM, environ, home))
    return World(home, base / "store", machine, environ)


def write_machine(world: World, recorded: str | None = None,
                  logs: Sequence[Path] = ()) -> None:
    """Write the machine configuration of the world, with the recorded store folder and
    the folders of native logs of Claude Code when given."""
    world.machine.mkdir(parents=True, exist_ok=True)
    configuration.write_machine_configuration(world.machine, configuration.MachineConfiguration(
        machine=MACHINE, installation=None, salt=None, store=recorded,
        native_logs={"claude-code": [str(folder) for folder in logs]}))


def set_up(world: World, store: Path, recorded: str | None = None,
           logs: Sequence[Path] = ()) -> None:
    """Prepare a set-up ledger: the machine configuration in the machine-local data folder,
    with the recorded store folder and the folders of native logs when given, and the
    person configuration in the store folder, as setup leaves them."""
    write_machine(world, recorded, logs)
    store.mkdir(parents=True, exist_ok=True)
    configuration.create_person_configuration(store, ZONE)


def counting_uids() -> tuple[Callable[[], str], list[int]]:
    """A maker of machine identifiers that records how often it was called, so a test sees
    when the machine identifier is made again."""
    counter = [0]

    def new_uid() -> str:
        counter[0] += 1
        return f"1a2b3c4d-0000-4000-8000-{counter[0]:012d}"

    return new_uid, counter


def build_context(
    world: World,
    version: str = VERSION,
    installation: str | None = INSTALLATION_ONE,
    environ: dict[str, str] | None = None,
    new_uid: Callable[[], str] | None = None,
    run: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
) -> Context:
    """The context of a test: a fixed instant, a fixed time zone, the adapters of the
    temporary home, a maker of machine identifiers of its own when none is given, and a
    fake of the scheduler call when none is given."""
    uids, _ = counting_uids()
    return Context(
        system=SYSTEM,
        environ=world.environ if environ is None else environ,
        home=world.home,
        now=NOW,
        new_uid=new_uid if new_uid is not None else uids,
        run=run if run is not None else _no_run,
        executable=EXECUTABLE,
        installation=installation,
        ask=None,
        adapters=[support.adapters_for_tests(world.home)],
        time_zone=lambda: ZONE,
        version=version,
        uid=501,
    )


def _no_run(words: list[str]) -> subprocess.CompletedProcess:
    """The call of a scheduler program that no test of the module reaches."""
    raise AssertionError("no test of the module runs a scheduler program")


def settle(paths: Sequence[Path]) -> None:
    """Give the files of native logs a time of change two settle times before the instant
    of the tests, so that a reading takes them as settled."""
    moment = NOW.timestamp() - 2 * SETTLE
    for path in paths:
        os.utime(path, (moment, moment))


def write_session(world: World, logs: Path) -> Path:
    """Write one settled session that holds one prompt of the person into the folder of
    native logs, and give the path of its file."""
    support.write_session(logs, "session-one",
                          [support.prompt_record("Invented prompt text.", PROMPT_AT, UUID_ONE)],
                          {}, world.home / "work")
    path = logs / "session-one.jsonl"
    settle([path])
    return path


class GoneAfterSelection:
    """The adapter of Claude Code of a test whose agent tool deletes the file of one session
    between the selection that named the session and the read of its file: the selection and
    the read are the real adapter's, and the deletion is the real one of the file's path
    (ingestion.md › Frequency, claude-code-adapter.md › Reading rules)."""

    def __init__(self, inner: Adapter, gone: Path) -> None:
        self._inner = inner
        self._gone = gone
        self.source = inner.source
        self.tools = inner.tools

    def default_folders(
        self, environ: Mapping[str, str], home: Path, system: str
    ) -> dict[str, list[PurePath]]:
        return self._inner.default_folders(environ, home, system)

    def retention(
        self,
        tool: str,
        environ: Mapping[str, str],
        home: Path,
        system: str,
        native_logs: Mapping[str, Sequence[str]],
        project_folders: Iterable[str],
    ) -> Retention:
        return self._inner.retention(tool, environ, home, system, native_logs,
                                     project_folders)

    def sessions(self, tool: str, folder: Path) -> list[SessionFiles]:
        found = self._inner.sessions(tool, folder)
        self._gone.unlink()  # the agent tool deletes it once the selection has named it
        return found

    def read_sessions(self, sessions: Sequence[SessionFiles],
                      context: ReadContext) -> ReadResult:
        return self._inner.read_sessions(sessions, context)


class FakeRun:
    """A fake of the call of a scheduler program: it records every call and ends with its
    code, so no test reaches the scheduler of the machine that runs the tests. A temporary
    XML that a call names is read and kept, so a test sees the entry the scheduler was
    given."""

    def __init__(self, code: int = 0) -> None:
        self.code = code
        self.calls: list[list[str]] = []
        self.documents: list[str] = []

    def __call__(self, words: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(list(words))
        for word in words:
            if word.endswith(".xml") and Path(word).is_file():
                self.documents.append(Path(word).read_text(encoding="utf-8"))
        return subprocess.CompletedProcess(words, self.code, "", "")


class HoldingRun(FakeRun):
    """A fake of the call of a scheduler program that holds the entry as the Task Scheduler
    does: a create keeps the XML it was given, a query answers with it, or ends with the
    code 1 when the fake holds none, and a delete drops it. On launchd and systemd the
    files of the entry in the home of the world hold it, so on every runner `schedule show`
    reads back the entry that `schedule create` made."""

    def __init__(self) -> None:
        super().__init__()
        self.held: str | None = None

    def __call__(self, words: list[str]) -> subprocess.CompletedProcess:
        done = super().__call__(words)
        if words[:2] == ["schtasks", "/Create"]:
            self.held = self.documents[-1]
        elif words[:2] == ["schtasks", "/Delete"]:
            self.held = None
        elif words[:2] == ["schtasks", "/Query"]:
            answer = self.held if self.held is not None and "/XML" in words else ""
            return subprocess.CompletedProcess(
                words, 1 if self.held is None else 0, answer, "")
        return done


SEEN_OPTIONS: list[argparse.Namespace] = []
"""The values that the action of the tests saw, for the test that reads them after."""


def _ingest_without_setup(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of the tests for `main`: the requirement of a set-up ledger, as every
    command but `setup`, `version`, and `--help` applies it before it reads the store
    (command-line.md › Setup)."""
    SEEN_OPTIONS.append(options)
    return stopped(context.require_setup(options.store))


def _modules() -> Iterator[ModuleType]:
    """Every module of the package: the package itself and each module below it."""
    package = ai_effort_ledger
    yield package
    for info in pkgutil.walk_packages(package.__path__, package.__name__ + "."):
        yield importlib.import_module(info.name)


def _exception_classes(modules: Iterator[ModuleType]) -> Iterator[type]:
    """Every exception class that the package defines, once, in the module that defines it."""
    seen: set[type] = set()
    for module in modules:
        for value in vars(module).values():
            if (isinstance(value, type) and issubclass(value, BaseException)
                    and value.__module__ == module.__name__ and value not in seen):
                seen.add(value)
                yield value


class TestContext(unittest.TestCase):
    """`cli` builds the `SetupContext` of setup from its own context."""

    def test_setup_context_carries_the_fields(self) -> None:
        """Every field of the run reaches the context of setup; its questions are asked by
        key in the language given, through the question of the run, and a run that asks
        nothing gives a setup that asks nothing (command-line.md › Output)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            context = build_context(world)
            self.assertIsNone(context.setup_context("en").ask)
            asked: list[str] = []

            def person(text: str) -> str:
                asked.append(text)
                return "Invented"

            context = context._replace(ask=person)
            built = context.setup_context("it")
            self.assertEqual(built.ask("setup_schedule", time="06:30"), "Invented")
            self.assertEqual(built.ask("setup_label"), "Invented")
            self.assertEqual(asked, [
                language.question("setup_schedule", "it").format(time="06:30"),
                language.question("setup_label", "it")])
            self.assertEqual(built.system, context.system)
            self.assertIs(built.environ, context.environ)
            self.assertEqual(built.home, context.home)
            self.assertEqual(built.now, context.now)
            self.assertIs(built.new_uid, context.new_uid)
            self.assertIs(built.run, context.run)
            self.assertEqual(built.executable, context.executable)
            self.assertEqual(built.installation, context.installation)
            self.assertIs(built.adapters, context.adapters)
            self.assertIs(built.time_zone, context.time_zone)
            self.assertEqual(built.version, context.version)
            self.assertEqual(built.uid, context.uid)


class TestRequireSetup(unittest.TestCase):
    """`require_setup` reads the two configurations and the store folder, and stops when
    either configuration is missing (command-line.md › Setup)."""

    def test_require_setup_without_configuration_stops(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            context = build_context(world)
            with self.assertRaises(configuration.SetupRequired):
                context.require_setup(None)  # no machine configuration
            set_up(world, world.store)
            (world.machine / "machine.toml").unlink()
            with self.assertRaises(configuration.SetupRequired):
                context.require_setup(world.store)  # no machine configuration, --store given
            write_machine(world)
            (world.store / PERSON_FILE).unlink()
            with self.assertRaises(configuration.SetupRequired):
                context.require_setup(None)  # no person configuration in the store folder

    def test_store_folder_order(self) -> None:
        with support.TemporaryFolder() as base:  # the store of --store wins
            world = build_world(base)
            elsewhere = base / "elsewhere"
            set_up(world, world.store, recorded=str(elsewhere))
            context = build_context(world)
            machine, person, chosen = context.require_setup(world.store)
            self.assertEqual(chosen, world.store)
            self.assertEqual(machine.machine, MACHINE)
            self.assertEqual(person.time_zones[0].zone, ZONE)
        with support.TemporaryFolder() as base:  # then the store the machine configuration holds
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            _, _, chosen = build_context(world).require_setup(None)
            # The recorded folder is read resolved, so the folder that setup wrote comes
            # back whatever form the machine configuration holds its path in.
            self.assertEqual(chosen, world.store.resolve())
        with support.TemporaryFolder() as base:  # then the default store folder
            world = build_world(base)
            default = Path(platform.default_store_folder(SYSTEM, world.environ, world.home))
            set_up(world, default, recorded=None)
            _, _, chosen = build_context(world).require_setup(None)
            self.assertEqual(chosen, default)

    def test_the_recorded_store_is_read_resolved(self) -> None:
        """The store folder that the machine configuration records is resolved before a
        command reads it: a recording that is already absolute is unchanged, and a word
        that is not one resolves against the working directory of the command — the
        reading of a recording that an earlier setup wrote before the resolve
        (command-line.md › Setup). The recording itself stays as the machine configuration
        holds it."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded="recorded/store")
            outside = Path.cwd()
            os.chdir(base)  # the word of the recording resolves where the command runs
            try:
                resolved = Path("recorded/store").resolve()
                resolved.mkdir(parents=True, exist_ok=True)
                configuration.create_person_configuration(resolved, ZONE)
                context = build_context(world)
                machine, _, chosen = context.require_setup(None)
                found = resolved_store(context, None)
            finally:
                os.chdir(outside)
            self.assertEqual(machine.store, "recorded/store")
            self.assertEqual(chosen, resolved)
            self.assertEqual(found, resolved)
        with support.TemporaryFolder() as base:  # a recording that is absolute stays
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            context = build_context(world)
            self.assertEqual(resolved_store(context, None), world.store.resolve())


class TestEmit(unittest.TestCase):
    """`emit` writes the warnings and the configuration errors of the outcome, and gives
    the exit codes (command-line.md › Output, › Exit codes, › JSON documents)."""

    def test_json_envelope(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = Outcome(
            {"day": "2026-06-15", "total": 3600},
            [{"code": "unknown_tool_name", "values": {"tool": "Invented-Tool"}}],
            [{"code": "project_name_conflict", "values": {"first": "Alpha", "second": "Beta"}}],
            False,
        )
        self.assertEqual(emit(outcome, "report timesheet", True, "en", stdout, stderr), 3)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(envelope["command"], "report timesheet")
        self.assertEqual(envelope["warnings"], [{
            "code": "unknown_tool_name",
            "values": {"tool": "Invented-Tool"},
            "message": "The tool name Invented-Tool is in no table of its adapter and no"
                       " category rule matches it.",
        }])
        self.assertEqual(envelope["configuration_errors"], [{
            "code": "project_name_conflict",
            "values": {"first": "Alpha", "second": "Beta"},
            "message": "The person configuration gives one name to two project identifiers:"
                       " Alpha and Beta.",
        }])
        self.assertEqual(envelope["day"], "2026-06-15")  # the keys of the document
        self.assertEqual(envelope["total"], 3600)

    def test_warnings_go_to_standard_error(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = Outcome(
            {}, [{"code": "unknown_tool_name", "values": {"tool": "Invented-Tool"}}], [], False)
        self.assertEqual(emit(outcome, "ingest", False, "en", stdout, stderr), 0)
        self.assertEqual(
            stderr.getvalue(),
            "warning: The tool name Invented-Tool is in no table of its adapter and no"
            " category rule matches it.\n")
        self.assertEqual(stdout.getvalue(), "")

    def test_configuration_error_line_starts_error(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = Outcome({}, [], [{"code": "identity_rule_conflict", "values": {
            "first": "example.org/team/alpha", "second": "example.org/team/beta"}}], False)
        self.assertEqual(emit(outcome, "report day", False, "en", stdout, stderr), 3)
        self.assertTrue(stderr.getvalue().startswith("error: Two identity rules match an event"))
        self.assertEqual(len(stderr.getvalue().splitlines()), 1)
        self.assertEqual(stdout.getvalue(), "")

    def test_lines_already_written_are_not_written_again(self) -> None:
        """An outcome whose action wrote the warning and configuration-error lines itself
        gives `emit` none of them again; the lists stay in the outcome, so the envelope
        of `--json` still carries them (command-line.md › Output)."""
        outcome = Outcome(
            {}, [{"code": "unknown_tool_name", "values": {"tool": "Invented-Tool"}}],
            [{"code": "project_name_conflict", "values": {"first": "Alpha",
                                                          "second": "Beta"}}],
            False, True)
        for as_json in (False, True):
            stdout, stderr = io.StringIO(), io.StringIO()
            # the configuration error keeps its hold on the exit code; only its line
            # is not written again
            self.assertEqual(
                emit(outcome, "purge", as_json, "en", stdout, stderr), 3)
            self.assertEqual(stderr.getvalue(), "")
            envelope = json.loads(stdout.getvalue()) if as_json else None
            if as_json:
                self.assertEqual([warning["code"] for warning
                                  in envelope["warnings"]], ["unknown_tool_name"])
                self.assertEqual([error["code"] for error
                                  in envelope["configuration_errors"]],
                                 ["project_name_conflict"])

    def test_json_stop_writes_error_envelope(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = stopped(configuration.SetupRequired())
        self.assertEqual(emit(outcome, "ingest", True, "en", stdout, stderr), 1)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(envelope["command"], "ingest")
        self.assertEqual(envelope["warnings"], [])
        self.assertEqual(envelope["configuration_errors"], [])
        self.assertEqual(envelope["error"], {
            "code": "setup_required",
            "values": {},
            "message": "The store folder holds no person configuration; run setup first.",
        })
        self.assertNotIn("day", envelope)  # the error stands instead of the document
        self.assertEqual(
            stderr.getvalue(),
            "error: The store folder holds no person configuration; run setup first.\n")
        stdout, stderr = io.StringIO(), io.StringIO()  # a wrong value stops with exit code 2
        outcome = stopped(configuration.WrongValue("--idle-gap", "Invented"))
        self.assertEqual(emit(outcome, "report day", True, "en", stdout, stderr), 2)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(envelope["error"]["code"], "wrong_value")
        self.assertEqual(envelope["error"]["values"], {"key": "--idle-gap", "value": "Invented"})
        self.assertEqual(
            stderr.getvalue(),
            "error: The value Invented is not valid for --idle-gap.\n")

    def test_text_stop_writes_one_error_line(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = stopped(configuration.SetupRequired())
        self.assertEqual(emit(outcome, "ingest", False, "en", stdout, stderr), 1)
        self.assertEqual(
            stderr.getvalue(),
            "error: The store folder holds no person configuration; run setup first.\n")
        self.assertEqual(stdout.getvalue(), "")

    def test_italian_messages(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = Outcome(
            {}, [{"code": "held_back_events", "values": {"session_id": "session-invented"}}],
            [], False)
        emit(outcome, "timesheet", False, "it", stdout, stderr)
        self.assertEqual(
            stderr.getvalue(),
            "warning: La sessione session-invented non è ancora completa: questa macchina"
            " trattiene i suoi eventi.\n")
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = stopped(configuration.SetupRequired())
        emit(outcome, "ingest", True, "it", stdout, stderr)
        envelope = json.loads(stdout.getvalue())
        self.assertEqual(
            envelope["error"]["message"],
            "La cartella dell'archivio non contiene la configurazione personale; eseguire"
            " prima setup.")

    def test_each_incomplete_code_exits_3(self) -> None:
        for code in sorted(INCOMPLETE_CODES):
            stdout, stderr = io.StringIO(), io.StringIO()
            outcome = Outcome({}, [{"code": code, "values": AnyValues()}], [], False)
            self.assertEqual(emit(outcome, "ingest", False, "en", stdout, stderr), 3, code)

    def test_json_document_composes_the_document_once(self) -> None:
        """`json_document` composes the JSON document of a command from the outcome: the
        keys of the document of the outcome, then `command`, `warnings`, and
        `configuration_errors` with their texts in the language (command-line.md › JSON
        documents); it is the one composition, and `emit` writes exactly it with `--json`
        (command-line.md › Frozen reports)."""
        warning = {"code": "unknown_tool_name", "values": {"tool": "Invented-Tool"}}
        error = {"code": "project_name_conflict", "values": {"first": "a", "second": "b"}}
        outcome = Outcome({"day": "2026-06-15", "record": {"ledger": "0.1.0"}}, [warning],
                          [error], False)
        document = json_document(outcome, "report day", "en")
        self.assertEqual(document, {
            "day": "2026-06-15", "record": {"ledger": "0.1.0"}, "command": "report day",
            "warnings": [{"code": "unknown_tool_name", "values": {"tool": "Invented-Tool"},
                          "message": "The tool name Invented-Tool is in no table of its"
                                     " adapter and no category rule matches it."}],
            "configuration_errors": [{
                "code": "project_name_conflict", "values": {"first": "a", "second": "b"},
                "message": "The person configuration gives one name to two project"
                           " identifiers: a and b."}]})
        self.assertEqual(list(document), ["day", "record", "command", "warnings",
                                          "configuration_errors"])
        # the composition changes nothing of the outcome
        self.assertEqual(outcome.warnings, [warning])
        self.assertEqual(outcome.document, {"day": "2026-06-15",
                                            "record": {"ledger": "0.1.0"}})
        stdout, stderr = io.StringIO(), io.StringIO()
        code = emit(outcome, "report day", True, "en", stdout, stderr)
        self.assertEqual(code, 3)
        self.assertEqual(stdout.getvalue(),
                         json.dumps(document, ensure_ascii=False) + "\n")

    def test_other_warnings_keep_exit_0(self) -> None:
        for code, values in (
            ("declared_value_below_measured", {"project": "example.org/team/alpha"}),
            ("unknown_tool_name", {"tool": "Invented-Tool"}),
        ):
            stdout, stderr = io.StringIO(), io.StringIO()
            outcome = Outcome({}, [{"code": code, "values": values}], [], False)
            self.assertEqual(
                emit(outcome, "report timesheet", False, "en", stdout, stderr), 0, code)

    def test_parameters_that_keep_exit_0(self) -> None:
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = Outcome(
            {}, [{"code": "held_back_events", "values": {"session_id": "session-invented"}}],
            [], False)
        self.assertEqual(
            emit(outcome, "timesheet confirm", False, "en", stdout, stderr,
                 held_back_is_incomplete=False), 0)
        stdout, stderr = io.StringIO(), io.StringIO()
        outcome = Outcome(
            {}, [], [{"code": "project_name_conflict", "values": {"first": "A", "second": "B"}}],
            False)
        self.assertEqual(
            emit(outcome, "config show", False, "en", stdout, stderr,
                 configuration_errors_are_incomplete=False), 0)
        stdout, stderr = io.StringIO(), io.StringIO()  # the flag of the outcome still counts
        outcome = Outcome({}, [], [], True)
        self.assertEqual(emit(outcome, "report day", False, "en", stdout, stderr), 3)


class TestGuards(unittest.TestCase):
    """`before_write` refuses a development version that may not write, and makes the
    machine identifier again when the installation identifier changed
    (architecture.md › Runtime, command-line.md › Exit codes)."""

    def test_before_write_refused_for_development_version(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            environ = {key: value for key, value in world.environ.items()
                       if key != DEVELOPMENT_VARIABLE}
            context = build_context(world, version=DEV_VERSION, environ=environ)
            with self.assertRaises(ingestion.DevelopmentVersion):
                context.before_write()
            self.assertFalse(world.machine.exists())  # nothing is written before the guard
        with support.TemporaryFolder() as base:  # a release version writes whatever the
            world = build_world(base)            # environment holds
            build_context(world).before_write()
            self.assertEqual(
                configuration.read_machine_configuration(world.machine).machine,
                "1a2b3c4d-0000-4000-8000-000000000001")
        with support.TemporaryFolder() as base:  # the variable lets a development version
            world = build_world(base)            # write
            build_context(world, version=DEV_VERSION).before_write()
            self.assertIsNotNone(configuration.read_machine_configuration(world.machine))

    def test_before_write_after_home_folder_copy(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            world.machine.mkdir(parents=True)
            salt = platform.new_salt()
            configuration.write_machine_configuration(
                world.machine,
                configuration.MachineConfiguration(
                    machine=MACHINE, installation=platform.salted_hash(INSTALLATION_ONE, salt),
                    salt=salt, store=None, native_logs={}))
            uids, counter = counting_uids()  # the same installation keeps the machine
            build_context(world, installation=INSTALLATION_ONE, new_uid=uids).before_write()
            kept = configuration.read_machine_configuration(world.machine)
            self.assertEqual(kept.machine, MACHINE)
            self.assertEqual(counter, [0])
            uids, counter = counting_uids()  # another installation makes the machine again
            build_context(world, installation=INSTALLATION_TWO, new_uid=uids).before_write()
            moved = configuration.read_machine_configuration(world.machine)
            self.assertNotEqual(moved.machine, MACHINE)
            self.assertNotEqual(moved.salt, salt)
            self.assertEqual(moved.installation,
                             platform.salted_hash(INSTALLATION_TWO, moved.salt))
            self.assertEqual(counter, [1])


DAY = "2026-11-24"
"""The day of the command lines of the wrong uses, the day of `NOW`."""
FROM = "2026-11-24T08:00"
"""The start of the intervals of the command lines of the wrong uses."""
TO = "2026-11-24T09:00"
"""The end of the intervals of the command lines of the wrong uses."""
TWO_PROJECTS = (
    ("project", "--id", "alpha-one", "--name", "Same"),
    ("project", "--id", "alpha-two", "--name", "Same"),
)
"""The entries of a person configuration that gives one name to two projects."""
TWO_WORK_ITEMS = (
    ("project", "--id", "alpha", "--name", "Alpha"),
    ("work-item", "--project", "alpha", "--id", "story-one", "--name", "Same"),
    ("work-item", "--project", "alpha", "--id", "story-two", "--name", "Same"),
)
"""The entries of a person configuration that gives one name to two work items of one
project."""


class TestWrongUse(unittest.TestCase):
    """A command line that the command cannot read stops with the code of its cause and
    exit code 2: no command, an argument that the command needs, an argument that it does
    not know, or arguments that it does not take together; a name that two entries of the
    person configuration give stops with `ambiguous_name` and exit code 1. The values name
    the command words that the person typed, wherever they stand among the options, and
    every argument of the fault; the line is the text of the code in the language of the
    command line, with a list value written as its items (command-line.md › Exit codes)."""

    def _stops(
        self, words: Sequence[str], code: str, values: dict, english: str, italian: str,
        exit_code: int = 2, action_name: str | None = None,
        entries: Sequence[Sequence[str]] = (),
    ) -> None:
        """Run the words through `main` on a set-up world whose person configuration
        holds the entries given, in English and in Italian, as text and with `--json`:
        each run stops with the exit code and the line and writes nothing to the store,
        the text run writes nothing to the standard output, and the envelope of `--json`
        holds the command, the code, the values, and the line."""
        if action_name is None:
            action_name = values.get("command", "ai-effort-ledger")
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            for entry in entries:
                added, _, error = run_action(world, ["config", "add", *entry])
                self.assertEqual(added, 0, error)
            for chosen, line in (("en", english), ("it", italian)):
                with self.subTest(language=chosen):
                    given = ["--language", chosen, *words]
                    self.assertEqual(run_action(world, given),
                                     (exit_code, "", f"error: {line}\n"))
                    stopped_with, shown, error = run_action(world, ["--json", *given])
                    self.assertEqual((stopped_with, error), (exit_code, f"error: {line}\n"))
                    self.assertEqual(json.loads(shown), {
                        "command": action_name, "warnings": [], "configuration_errors": [],
                        "error": {"code": code, "values": values, "message": line}})
            self.assertEqual(stored_events(world), [])  # nothing is written

    def _missing(self, words: Sequence[str], action_name: str, arguments: list[str]) -> None:
        """The words stop with `missing_argument`, which names the command and every
        argument that it needs."""
        shown = ", ".join(arguments)
        self._stops(words, "missing_argument",
                    {"command": action_name, "arguments": arguments},
                    f"The command {action_name} needs {shown}.",
                    f"Il comando {action_name} richiede {shown}.")

    def _unknown(self, words: Sequence[str], action_name: str, arguments: list[str]) -> None:
        """The words stop with `unknown_argument`, which names the command and every
        argument that it does not know."""
        shown = ", ".join(arguments)
        self._stops(words, "unknown_argument",
                    {"command": action_name, "arguments": arguments},
                    f"The command {action_name} does not know {shown}.",
                    f"Il comando {action_name} non conosce {shown}.")

    def _conflicting(
        self, words: Sequence[str], action_name: str, arguments: list[str],
    ) -> None:
        """The words stop with `conflicting_arguments`, which names the command and every
        argument that it does not take together."""
        shown = ", ".join(arguments)
        self._stops(words, "conflicting_arguments",
                    {"command": action_name, "arguments": arguments},
                    f"The command {action_name} does not take {shown} together.",
                    f"Il comando {action_name} non accetta {shown} insieme.")

    def _ambiguous(self, words: Sequence[str], action_name: str, option: str,
                   identifiers: list[str], entries: Sequence[Sequence[str]]) -> None:
        """The words stop with `ambiguous_name` and exit code 1: the name `Same` gives
        more than one identifier, which the values hold sorted."""
        shown = ", ".join(identifiers)
        self._stops(
            words, "ambiguous_name",
            {"option": option, "name": "Same", "identifiers": identifiers},
            f"The name Same gives more than one identifier: name one of {shown} with"
            f" {option}.",
            f"Il nome Same corrisponde a più di un identificativo: indicarne uno tra {shown}"
            f" con {option}.", exit_code=1, action_name=action_name, entries=entries)

    def test_no_word_names_no_action(self) -> None:
        self._stops(
            [], "no_command", {},
            "No command was given; ai-effort-ledger --help lists the commands.",
            "Nessun comando indicato; ai-effort-ledger --help elenca i comandi.")

    def test_unknown_action(self) -> None:
        self._unknown(["nosuchcommand"], "ai-effort-ledger", ["nosuchcommand"])

    def test_unknown_subcommand_names_its_action(self) -> None:
        for parent in ("machine", "config", "report"):
            with self.subTest(action=parent):
                self._unknown([parent, "nosuchsub"], parent, ["nosuchsub"])

    def test_action_without_its_subcommand(self) -> None:
        self._missing(["schedule"], "schedule", ["show | create | remove"])
        self._missing(["config"], "config", ["show | add"])

    def test_timesheet_alone_needs_a_day_or_a_subcommand(self) -> None:
        self._missing(["timesheet"], "timesheet", ["<day> | confirm | retract"])

    def test_timesheet_subcommand_without_its_day(self) -> None:
        self._missing(["timesheet", "confirm"], "timesheet confirm", ["<day>"])
        self._missing(["timesheet", "retract"], "timesheet retract", ["<day>"])

    def test_action_without_its_positional(self) -> None:
        self._missing(["sessions"], "sessions", ["<day>"])
        self._missing(["entries"], "entries", ["<day>"])
        self._missing(["retract"], "retract", ["<event_uid>"])

    def test_timesheet_day_with_a_word_too_many(self) -> None:
        self._unknown(["timesheet", DAY, "extra"], "timesheet", ["extra"])

    def test_timesheet_word_that_is_no_day_is_a_wrong_value(self) -> None:
        self._stops(
            ["timesheet", "nosuchword"], "wrong_value", {"key": "<day>", "value": "nosuchword"},
            "The value nosuchword is not valid for <day>.",
            "Il valore nosuchword non è valido per <day>.", action_name="timesheet")

    def test_unknown_option_after_the_action(self) -> None:
        self._unknown(["setup", "--nosuchoption"], "setup", ["--nosuchoption"])
        self._unknown(["sessions", "--nope"], "sessions", ["--nope"])

    def test_unknown_option_before_the_action(self) -> None:
        self._unknown(["--nosuchoption", "ingest"], "ingest", ["--nosuchoption"])

    def test_option_without_its_value(self) -> None:
        self._missing(["timesheet", "--total"], "timesheet", ["--total <duration>"])

    def test_every_required_option_is_named(self) -> None:
        self._missing(["report", "timesheet"], "report timesheet", ["--from", "--to"])
        self._missing(["entry", "add", "--project", "alpha"], "entry add",
                      ["--from", "--to", "--mode"])

    def test_value_out_of_the_choices_is_a_wrong_value(self) -> None:
        self._stops(
            ["--language", "xx"], "wrong_value", {"key": "--language", "value": "xx"},
            "The value xx is not valid for --language.",
            "Il valore xx non è valido per --language.")
        self._stops(
            ["entry", "add", "--from", FROM, "--to", TO, "--mode", "xx"], "wrong_value",
            {"key": "--mode", "value": "xx"}, "The value xx is not valid for --mode.",
            "Il valore xx non è valido per --mode.", action_name="entry add")
        self._stops(
            ["config", "add", "nosuchentry"], "wrong_value",
            {"key": "<entry>", "value": "nosuchentry"},
            "The value nosuchentry is not valid for <entry>.",
            "Il valore nosuchentry non è valido per <entry>.", action_name="config add")

    def test_word_too_many_for_an_action_without_arguments(self) -> None:
        self._unknown(["version", "extra"], "version", ["extra"])
        self._unknown(["ingest", "extra"], "ingest", ["extra"])

    def test_purge_by_key_and_by_writer_version_together(self) -> None:
        self._conflicting(
            ["purge", "--key", "k", "--writer-version-below", "1.0.0", "--reason", "content",
             "--yes"], "purge", ["--key", "--writer-version-below"])

    def test_annotate_without_project_or_work_item(self) -> None:
        self._missing(["annotate", "--from", FROM, "--to", TO], "annotate",
                      ["--project | --work-item"])
        self._missing(["annotate", "--session", "session-one", "--to", TO], "annotate",
                      ["--project | --work-item"])

    def test_annotate_without_session_or_interval(self) -> None:
        self._missing(["annotate", "--to", TO], "annotate", ["--session | --from"])

    def test_annotate_session_with_an_interval_end(self) -> None:
        self._conflicting(
            ["annotate", "--session", "session-one", "--to", TO, "--project", "alpha"],
            "annotate", ["--session", "--to"])

    def test_annotate_interval_without_its_end(self) -> None:
        self._missing(["annotate", "--from", FROM, "--project", "alpha"], "annotate",
                      ["--to"])

    def test_annotate_interval_with_a_tool(self) -> None:
        """`--tool` names the agent tool of a session: the interval form does not take it
        (command-line.md › Commands, `annotate`)."""
        self._conflicting(
            ["annotate", "--tool", "claude-code", "--from", FROM, "--to", TO, "--project",
             "alpha"], "annotate", ["--tool", "--from"])

    def test_timesheet_day_with_an_option_of_confirm(self) -> None:
        """`--total`, `--set`, and `--note` belong to `timesheet confirm <day>`: the day form
        does not know them, so a line that forgets `confirm` declares nothing and stops
        (command-line.md › Commands, › Exit codes)."""
        self._unknown(["timesheet", DAY, "--total", "6h"], "timesheet", ["--total"])
        self._unknown(["timesheet", DAY, "--note", "Invented note.", "--set", "alpha=1h"],
                      "timesheet", ["--set", "--note"])

    def test_timesheet_retract_with_an_option_of_another_form(self) -> None:
        """`timesheet retract <day>` takes no option of `confirm` and no report parameter,
        because it computes no figures (command-line.md › Commands, › Form)."""
        self._unknown(["timesheet", "retract", DAY, "--total", "6h"], "timesheet retract",
                      ["--total"])
        self._unknown(
            ["timesheet", "retract", DAY, "--headless-prompts", "yes", "--idle-gap", "10min",
             "--minimum-attention", "1min", "--stale-limit", "4h",
             "--timesheet-granularity", "15min"], "timesheet retract",
            ["--idle-gap", "--minimum-attention", "--stale-limit", "--headless-prompts",
             "--timesheet-granularity"])

    def test_report_note_without_freeze(self) -> None:
        """`--note` is the note of a frozen report: without `--freeze` it needs it
        (command-line.md › Commands, › Frozen reports)."""
        self._missing(["report", "day", DAY, "--note", "Invented note."], "report day",
                      ["--freeze"])
        self._missing(["report", "timesheet", "--from", DAY, "--to", DAY, "--note",
                       "Invented note."], "report timesheet", ["--freeze"])

    def test_duration_option_without_its_value_names_a_duration(self) -> None:
        """The report parameters that are durations read the forms of a duration, so a
        missing value is named `<duration>` (command-line.md › Form)."""
        for option in ("--idle-gap", "--minimum-attention", "--stale-limit",
                       "--timesheet-granularity"):
            with self.subTest(option=option):
                self._missing(["sessions", DAY, option], "sessions", [f"{option} <duration>"])

    def test_entry_add_work_item_without_project(self) -> None:
        self._missing(
            ["entry", "add", "--from", FROM, "--to", TO, "--mode", "additional",
             "--work-item", "story-1"], "entry add", ["--project"])

    def test_purge_forget_with_corrected_version(self) -> None:
        self._conflicting(
            ["purge", "--key", "k", "--reason", "forget", "--corrected-version", "9.0.0",
             "--yes"], "purge", ["--reason forget", "--corrected-version"])

    def test_purge_by_key_with_a_source(self) -> None:
        self._conflicting(
            ["purge", "--key", "k", "--source", "claude-code-jsonl", "--reason", "content",
             "--yes"], "purge", ["--key", "--source"])

    def test_config_add_option_that_the_entry_does_not_read(self) -> None:
        self._conflicting(["config", "add", "project", "--hour", "12:00"], "config add",
                          ["project", "--hour"])
        self._conflicting(
            ["config", "add", "project", "--hour", "12:00", "--zone", "Etc/UTC"],
            "config add", ["project", "--zone", "--hour"])

    def test_config_add_entry_without_its_keys(self) -> None:
        self._missing(["config", "add", "project", "--id", "alpha"], "config add",
                      ["--name"])
        self._missing(["config", "add", "work-item", "--name", "Story"], "config add",
                      ["--project", "--id"])

    def test_config_add_identity_rule_without_a_condition(self) -> None:
        self._missing(["config", "add", "identity-rule", "--project", "alpha"], "config add",
                      ["--repository | --folder | --branch | --from | --to"])

    def test_values_outside_the_forms(self) -> None:
        """A value of an option that no form of command-line.md › Form holds stops the
        command with `wrong_value`, which names the option or the placeholder of the
        positional and the value, with the exit code 2, in both languages: a compact date
        and a week date where a day is read, a space for `T`, the seconds of a local
        time, a day where an instant is read, an offset without the second, an hour with
        seconds, the local time of a time-zone entry, whose `--from` is always an RFC
        3339 instant, and the time of the scheduled ingestion."""
        cases = (
            (["sessions", "20261110"], "sessions", "<day>", "20261110"),
            (["sessions", "2026-W46-1"], "sessions", "<day>", "2026-W46-1"),
            (["annotate", "--from", "2026-11-10 09:30"], "annotate", "--from",
             "2026-11-10 09:30"),
            (["annotate", "--from", "2026-11-10T09:30:00"], "annotate", "--from",
             "2026-11-10T09:30:00"),
            (["annotate", "--from", "2026-11-10"], "annotate", "--from", "2026-11-10"),
            (["annotate", "--from", "2026-11-10T09:30Z"], "annotate", "--from",
             "2026-11-10T09:30Z"),
            (["config", "add", "day-start", "--hour", "04:00:00", "--from", "today"],
             "config add", "--hour", "04:00:00"),
            (["config", "add", "time-zone", "--zone", "Europe/Rome", "--from",
              "2026-12-01T00:00"], "config add", "--from", "2026-12-01T00:00"),
            (["schedule", "create", "--time", "04:00:00"], "schedule create", "--time",
             "04:00:00"),
        )
        for words, action_name, key, value in cases:
            with self.subTest(words=" ".join(words)):
                self._stops(words, "wrong_value", {"key": key, "value": value},
                            f"The value {value} is not valid for {key}.",
                            f"Il valore {value} non è valido per {key}.",
                            action_name=action_name)

    def test_name_of_two_projects(self) -> None:
        self._ambiguous(["annotate", "--session", "session-one", "--project", "Same"],
                        "annotate", "--project", ["alpha-one", "alpha-two"], TWO_PROJECTS)

    def test_name_of_two_work_items(self) -> None:
        self._ambiguous(["annotate", "--session", "session-one", "--work-item", "Same"],
                        "annotate", "--work-item", ["story-one", "story-two"],
                        TWO_WORK_ITEMS)

    def test_name_of_two_projects_in_a_set_value(self) -> None:
        self._ambiguous(["timesheet", "confirm", DAY, "--set", "Same=1:00"],
                        "timesheet confirm", "--set", ["alpha-one", "alpha-two"],
                        TWO_PROJECTS)


class TestArguments(unittest.TestCase):
    """`build_arguments` reads the command line of every command, and `check_values`
    checks, after the parse, the words that hold a format and the two words of
    `timesheet` (command-line.md › Form, › Commands)."""

    def test_timesheet_day_or_action(self) -> None:
        words = ["timesheet", "--store", "D:/Work/Product/store"]
        options = build_arguments().parse_args(words + ["2026-06-15"])
        check_values(options)
        self.assertEqual(options.action, "timesheet")  # the day form
        self.assertEqual(options.day, "2026-06-15")  # the value stays as the person typed it
        options = build_arguments().parse_args(words + ["confirm", "2026-06-15"])
        check_values(options)
        self.assertEqual(options.action, "timesheet confirm")
        self.assertEqual(options.day, "2026-06-15")
        options = build_arguments().parse_args(words + ["retract", "today"])
        check_values(options)
        self.assertEqual(options.action, "timesheet retract")
        self.assertEqual(options.day, "today")  # the words of the day of the run stay text
        options = build_arguments().parse_args(words + ["not-a-day"])
        with self.assertRaises(configuration.WrongValue) as wrong:
            check_values(options)
        self.assertEqual(wrong.exception.values, {"key": "<day>", "value": "not-a-day"})
        with self.assertRaises(WrongUse):  # the day form without its day
            check_values(build_arguments().parse_args(words))
        with self.assertRaises(WrongUse):  # the confirm form without its day
            check_values(build_arguments().parse_args(words + ["confirm"]))

    def test_the_duration_report_parameters_name_a_duration(self) -> None:
        """The help of the report parameters that are durations names the form that their
        reader reads, a duration (command-line.md › Form), in the language of the help;
        `600` is no duration, `10min` and `0:10` are."""
        for chosen in language.LANGUAGES:
            word = language.help_text("metavar_duration", chosen).upper()
            for name in ("sessions", "timesheet"):
                with self.subTest(language=chosen, command=name):
                    shown = subreaders(build_arguments(chosen))[name].format_help()
                    for option in ("--idle-gap", "--minimum-attention", "--stale-limit",
                                   "--timesheet-granularity"):
                        self.assertIn(f"[{option} {word}]", shown)
                        self.assertIn(f"  {option} {word} ", shown)
        words = ["sessions", DAY, "--idle-gap"]
        for value in ("10min", "0:10"):
            check_values(build_arguments().parse_args([*words, value]))
        with self.assertRaises(configuration.WrongValue):
            check_values(build_arguments().parse_args([*words, "600"]))

    def test_language_out_of_the_choices_is_a_wrong_value(self) -> None:
        with self.assertRaises(configuration.WrongValue) as wrong:
            build_arguments().parse_args(["--language", "fr"])
        self.assertEqual(wrong.exception.values, {"key": "--language", "value": "fr"})

    def test_fault_of_a_text_that_names_no_word(self) -> None:
        """Where the words and the text of argparse show no fault — a refusal that no
        version of today reaches — the tail of `_fault_of` holds: the words that start
        with `--` are the ones the command does not know, else the first word after the
        last command word, even when it is a valid day of the day form (command-line.md ›
        Exit codes). The branch stays, pinned here against drift."""
        def faults(words: list[str]) -> tuple[str, dict, str]:
            fault = _fault_of(build_arguments(), words, "a text that names no word")
            return fault.code, fault.values, fault.action_name

        self.assertEqual(faults(["sessions", DAY, "--json"]),
                         ("unknown_argument",
                          {"command": "sessions", "arguments": ["--json"]}, "sessions"))
        self.assertEqual(faults(["timesheet", DAY]),
                         ("unknown_argument", {"command": "timesheet", "arguments": [DAY]},
                          "timesheet"))

    def test_day_instant_and_hour_readers_read_the_forms_alone(self) -> None:
        """The readers of the command line take the forms of command-line.md › Form alone:
        every text of the shared table that no form of the reader's kind holds raises
        ValueError, which `check_values` turns into `wrong_value`; the words of the day of
        the run stay text for the day readers, and `read_instant_or_day` also takes a day,
        which `config add` reads as the `from` of a day-start entry."""
        for one in support.FORM_TEXTS:
            with self.subTest(text=one.text):
                cases = (
                    (read_day, one.day or one.text in DAY_WORDS),
                    (read_instant, one.local_instant or one.offset_instant),
                    (read_instant_or_day, one.day or one.local_instant
                     or one.offset_instant or one.text in DAY_WORDS),
                    (read_hour, one.hour),
                )
                for reader, takes in cases:
                    if takes:
                        reader(one.text)
                    else:
                        with self.assertRaises(ValueError):
                            reader(one.text)


def small_reader(prog: str, output_language: str = "en") -> argparse.ArgumentParser:
    """A parser without arguments whose help the formatter of the ledger lays out in the
    language, as it lays out the help of every command (command-line.md › Commands)."""
    return argparse.ArgumentParser(
        prog, add_help=False, formatter_class=build_arguments(output_language).formatter_class)


def subreaders(reader: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """The parsers of the subcommands of a parser, by their word."""
    table = next(action for action in reader._actions
                 if isinstance(action, argparse._SubParsersAction))
    return table.choices


class TestHelpUsage(unittest.TestCase):
    """The usage of the help of a command is laid out by the ledger, by one rule on every
    interpreter, within 96 columns whatever the terminal: the first row follows the name of
    the program and the words of the command, each next row starts under the first part,
    and a row breaks between two parts, never inside one; the main help keeps the usage it
    is given and fits the width (command-line.md › Commands). Every expected usage is
    computed by hand."""

    def test_a_usage_that_fits_stays_on_one_line(self) -> None:
        reader = small_reader("ledger")
        reader.add_argument("--store")
        reader.add_argument("day", nargs="?")
        # 7 columns of `usage: `, 6 of the name, then 1 + 15 + 1 + 5: 35 columns.
        self.assertEqual(reader.format_usage().strip(), "usage: ledger [--store STORE] [day]")
        self.assertEqual(small_reader("ledger", "it").format_usage().strip(), "uso: ledger")
        # `ingest`: 7 + 23 + 1 + 16 + 1 + 8 + 1 + 20 + 1 + 4 = 82 columns, in both languages.
        for language, expected in (
                ("en", "usage: ai-effort-ledger ingest [--store FOLDER] [--json] "
                       "[--language {en,it}] [-h]"),
                ("it", "uso: ai-effort-ledger ingest [--store CARTELLA] [--json] "
                       "[--language {en,it}] [-h]")):
            with self.subTest(language=language):
                ingest = subreaders(build_arguments(language))["ingest"]
                self.assertEqual(ingest.format_usage().strip(), expected)

    def test_a_group_of_options_breaks_after_its_separator(self) -> None:
        # 14 columns before the first part; `[--long …]` is 49 (63); the first member of
        # the group, 20 (84); the second, 15, would reach 100: it starts the next row, at
        # column 14.
        for required, opening, closing in ((True, "(", ")"), (False, "[", "]")):
            with self.subTest(required=required):
                reader = small_reader("ledger")
                reader.add_argument("--long", metavar="V" * 40)
                about = reader.add_mutually_exclusive_group(required=required)
                about.add_argument("--session")
                about.add_argument("--from", metavar="INSTANT")
                self.assertEqual(
                    reader.format_usage().strip(),
                    f"usage: ledger [--long {'V' * 40}] {opening}--session SESSION |\n"
                    f"{' ' * 14}--from INSTANT{closing}")

    def test_a_required_option_stays_with_its_argument(self) -> None:
        # 14 columns before the first part; `[--long …]` is 49 (63); `[--more …]` is 23
        # (87); `--from INSTANT`, 14, would reach 102: it starts the next row, at column
        # 14, with its argument, and `--to INSTANT` joins it (41).
        reader = small_reader("ledger")
        reader.add_argument("--long", metavar="V" * 40)
        reader.add_argument("--more", metavar="V" * 14)
        reader.add_argument("--from", required=True, metavar="INSTANT")
        reader.add_argument("--to", required=True, metavar="INSTANT")
        self.assertEqual(
            reader.format_usage().strip(),
            f"usage: ledger [--long {'V' * 40}] [--more {'V' * 14}]\n"
            "              --from INSTANT --to INSTANT")

    def test_a_part_longer_than_the_width_stands_whole_on_its_row(self) -> None:
        # `--label LLL… MMM…` is 8 + 48 + 1 + 48 = 105 columns: more than the width, so it
        # stands whole on its row (119 columns), and `[--yes]` takes the row after it.
        label = "L" * 48 + " " + "M" * 48
        reader = small_reader("ledger")
        reader.add_argument("--json", action="store_true")
        reader.add_argument("--label", required=True, metavar=label)
        reader.add_argument("--yes", action="store_true")
        self.assertEqual(
            reader.format_usage().strip(),
            "usage: ledger [--json]\n"
            f"              --label {label}\n"
            "              [--yes]")

    def test_the_first_row_follows_the_name_and_the_others_start_under_the_first_part(
            self) -> None:
        # 14 columns before the first part; `[--long …]` is 49 (63); `[--more …]` is 49
        # and does not join: it starts the next row, at column 14, and `DAY` joins it (67).
        reader = small_reader("ledger")
        reader.add_argument("--long", metavar="V" * 40)
        reader.add_argument("--more", metavar="V" * 40)
        reader.add_argument("day", metavar="DAY")
        self.assertEqual(
            reader.format_usage().strip(),
            f"usage: ledger [--long {'V' * 40}]\n"
            f"              [--more {'V' * 40}] DAY")
        # A name of 66 columns takes no row of its own: `usage: ` and the name make 73,
        # `[--one ONE]` joins the first row (85), `[--two TWO]` would reach 97 and starts
        # the next row, at column 74 (85), and `[--three THREE]` takes the row after it.
        name = "p" * 66
        reader = small_reader(name)
        for option in ("--one", "--two", "--three"):
            reader.add_argument(option)
        under = " " * 74
        self.assertEqual(
            reader.format_usage().strip(),
            f"usage: {name} [--one ONE]\n{under}[--two TWO]\n{under}[--three THREE]")

    def test_the_program_name_of_an_action_and_of_a_subcommand(self) -> None:
        top = build_arguments()
        # the main parser keeps the usage it is given (command-line.md › Form)
        self.assertEqual(top.format_usage().strip(),
                         "usage: ai-effort-ledger <command> [<subcommand>] [options]")
        words = subreaders(top)
        self.assertEqual(words["annotate"].prog, "ai-effort-ledger annotate")
        self.assertEqual(words["schedule"].prog, "ai-effort-ledger schedule")
        show = subreaders(words["schedule"])["show"]
        self.assertEqual(show.prog, "ai-effort-ledger schedule show")
        # 7 + 30 + 1 + 16 + 1 + 8 + 1 + 20 + 1 + 4 = 89 columns.
        self.assertEqual(
            show.format_usage().strip(),
            "usage: ai-effort-ledger schedule show [--store FOLDER] [--json] "
            "[--language {en,it}] [-h]")

    def test_the_main_help_holds_the_metavar_and_fits_the_width(self) -> None:
        # The metavar of the choices of the main parser is one word, 9 columns, alone on
        # its line at the indent 2; the texts of the options and of the choices start at
        # column 22, two columns after `--language {en,it}`, and wrap at 74.
        for language, metavar in (("en", "  <command>"), ("it", "  <comando>")):
            lines = build_arguments(language).format_help().splitlines()
            with self.subTest(language=language, claim="the metavar"):
                self.assertIn(metavar, lines)
            with self.subTest(language=language, claim="the width"):
                self.assertLessEqual(max(map(len, lines)), 96)

    def test_the_width_of_the_terminal_changes_nothing(self) -> None:
        reader = small_reader("ledger")
        reader.add_argument("--store")
        reader.description = " ".join(["word"] * 30)
        with mock.patch.dict(os.environ, {"COLUMNS": "40"}):
            narrow = reader.format_help()
        with mock.patch.dict(os.environ, {"COLUMNS": "250"}):
            wide = reader.format_help()
        self.assertEqual(narrow, wide)
        # 19 words make 94 columns and 20 would make 99: the description wraps at 96.
        lines = narrow.splitlines()
        self.assertEqual(lines[:4], ["usage: ledger [--store STORE]", "",
                                     " ".join(["word"] * 19), " ".join(["word"] * 11)])


class TestMain(unittest.TestCase):
    """`main` reads the command line in the language of `--language`, runs the action of
    the command through the table of `cli`, and gives the exit code of the outcome or of
    the stop error (command-line.md › Form, › Commands, › Exit codes, › Setup)."""

    def test_unknown_action_exits_2(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["reprot", "--store", str(world.store)], build_context(world))
            self.assertEqual(code, 2)
            lines = stderr.getvalue().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertTrue(lines[0].startswith("error: "))
            self.assertEqual(lines[0],
                             "error: The command ai-effort-ledger does not know reprot.")
            self.assertNotIn("usage:", stderr.getvalue())  # no usage of argparse
            self.assertNotIn("usage:", stdout.getvalue())
            self.assertEqual(stdout.getvalue(), "")  # the text of no document

    def test_wrong_duration_exits_2(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            words = ["report", "timesheet", "--store", str(world.store),
                     "--from", "2026-06-01", "--to", "2026-06-30", "--idle-gap", "Invented"]
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(words, build_context(world))
            self.assertEqual(code, 2)
            self.assertEqual(
                stderr.getvalue(), "error: The value Invented is not valid for --idle-gap.\n")
            self.assertEqual(stdout.getvalue(), "")
            stdout, stderr = io.StringIO(), io.StringIO()  # the same fault with --json
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(words + ["--json"], build_context(world))
            self.assertEqual(code, 2)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "report timesheet")
            self.assertEqual(envelope["warnings"], [])
            self.assertEqual(envelope["error"]["code"], "wrong_value")
            self.assertEqual(
                envelope["error"]["values"], {"key": "--idle-gap", "value": "Invented"})
            self.assertEqual(
                envelope["error"]["message"],
                "The value Invented is not valid for --idle-gap.")

    def test_wrong_use_in_italian(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            words = ["report", "timesheet", "--store", str(world.store), "--language", "it"]
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(words, build_context(world))
            self.assertEqual(code, 2)  # --from and --to are missing
            self.assertEqual(
                stderr.getvalue(),
                "error: Il comando report timesheet richiede --from, --to.\n")
            stdout, stderr = io.StringIO(), io.StringIO()  # an action that no command holds
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["reprot", "--store", str(world.store), "--language", "it"],
                            build_context(world))
            self.assertEqual(code, 2)
            self.assertEqual(
                stderr.getvalue(),
                "error: Il comando ai-effort-ledger non conosce reprot.\n")

    def test_action_before_setup_exits_1_and_asks_for_setup(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            held = ACTIONS.get("ingest")

            def restore() -> None:
                if held is None:
                    ACTIONS.pop("ingest", None)
                else:
                    ACTIONS["ingest"] = held

            ACTIONS["ingest"] = ("test_cli", "_ingest_without_setup")
            self.addCleanup(restore)
            self.addCleanup(SEEN_OPTIONS.clear)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["--store", str(world.store), "ingest"], build_context(world))
            self.assertEqual(code, 1)
            self.assertEqual(
                stderr.getvalue(),
                "error: The store folder holds no person configuration; run setup first.\n")
            self.assertEqual(stdout.getvalue(), "")
            self.assertEqual(SEEN_OPTIONS[-1].store, world.store)  # --store before the command
            self.assertFalse(SEEN_OPTIONS[-1].json)
            self.assertEqual(SEEN_OPTIONS[-1].language, "en")
            stdout, stderr = io.StringIO(), io.StringIO()  # the same stop with --json
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["ingest", "--store", str(world.store), "--json"],
                            build_context(world))
            self.assertEqual(code, 1)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "ingest")
            self.assertEqual(envelope["error"]["code"], "setup_required")
            self.assertEqual(envelope["error"]["values"], {})
            self.assertTrue(SEEN_OPTIONS[-1].json)
            self.assertEqual(
                stderr.getvalue(),
                "error: The store folder holds no person configuration; run setup first.\n")

    def test_help_lists_commands(self) -> None:
        self.assertEqual(build_arguments().prog, "ai-effort-ledger")  # without a language
        with support.TemporaryFolder() as base:
            world = build_world(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["--store", str(world.store), "--help"], None)
            self.assertEqual(code, 0)  # the help completes before any store is read
            listing = stdout.getvalue()
            for name in ("setup", "schedule", "ingest", "machine", "config", "sessions",
                         "annotate", "entry", "timesheet", "entries", "retract", "purge",
                         "report", "frozen", "index", "version"):
                self.assertIn(name, listing, name)
            self.assertIn("commands:", listing)
            self.assertIn("options:", listing)
            self.assertEqual(stderr.getvalue(), "")
            stdout, stderr = io.StringIO(), io.StringIO()  # the help of one command
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["report", "timesheet", "--store", str(world.store), "--help"],
                            None)
            self.assertEqual(code, 0)
            for word in ("--from", "--to", "--freeze", "--note", "--idle-gap",
                         "--minimum-attention", "--stale-limit", "--headless-prompts",
                         "--timesheet-granularity", "--store", "--json", "--language"):
                self.assertIn(word, stdout.getvalue(), word)
            self.assertEqual(stderr.getvalue(), "")

    def test_help_in_italian(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["--language", "it", "--store", str(world.store), "--help"], None)
            self.assertEqual(code, 0)
            listing = stdout.getvalue()
            self.assertIn("uso:", listing)
            self.assertIn("comandi:", listing)
            self.assertIn("opzioni:", listing)
            self.assertIn("mostra questo aiuto ed esce", listing)
            self.assertIn("setup", listing)  # the names of the commands stay as they are
            self.assertNotIn("usage:", listing)
            self.assertNotIn("options:", listing)
            self.assertNotIn("Commands:", listing)
            self.assertEqual(stderr.getvalue(), "")
            stdout, stderr = io.StringIO(), io.StringIO()  # the help of one command
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["report", "timesheet", "--language", "it",
                             "--store", str(world.store), "--help"], None)
            self.assertEqual(code, 0)
            shown = stdout.getvalue()
            self.assertIn("uso:", shown)
            self.assertIn("opzioni:", shown)
            self.assertIn("--from GIORNO", shown)
            self.assertIn("--to GIORNO", shown)
            self.assertNotIn("usage:", shown)
            self.assertNotIn("options:", shown)
            self.assertNotIn("Commands:", shown)

    def test_the_from_of_config_add_names_both_forms(self) -> None:
        """The `--from` of `config add` takes an instant for a time-zone entry and a day
        for the other entries (command-line.md › Configuration entries), so its metavar
        names both, in the language of the help."""
        for words, wanted, other in (([], "--from INSTANT|DAY", "--from INSTANT "),
                                     (["--language", "it"], "--from ISTANTE|GIORNO",
                                      "--from ISTANTE ")):
            with self.subTest(words=" ".join(words)):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(["config", "add", *words, "--help"], None)
                self.assertEqual((code, stderr.getvalue()), (0, ""))
                self.assertIn(wanted, stdout.getvalue())
                self.assertNotIn(other, stdout.getvalue())


class TestOptionsBeforeTheParse(unittest.TestCase):
    """The `--language` and the `--json` of the words of the command line, read before the
    parse through the prefix rule of the parsers of the commands themselves: a word that a
    parser reads as one of the two options — an abbreviation that one option alone holds,
    as the parse reads it — feeds the language of the help and of the faults, and the JSON
    envelope of a fault, exactly as the full word does (command-line.md › Form)."""

    def test_an_abbreviation_feeds_the_language_of_the_fault(self) -> None:
        message = language.message("missing_argument",
                                   {"command": "machine", "arguments": ["label"]}, "it")
        for words in (["--language", "it", "machine"], ["--lang", "it", "machine"]):
            with self.subTest(words=" ".join(words)):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(words)
                self.assertEqual(code, 2)
                self.assertEqual(stderr.getvalue(), f"error: {message}\n")
                self.assertEqual(stdout.getvalue(), "")  # the line gives no --json

    def test_an_abbreviation_feeds_the_json_envelope_of_a_fault(self) -> None:
        for words in (["--json", "machine"], ["--jso", "machine"]):
            with self.subTest(words=" ".join(words)):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    code = main(words)
                self.assertEqual(code, 2)
                envelope = json.loads(stdout.getvalue())
                self.assertEqual(envelope["command"], "machine")
                self.assertEqual(envelope["error"]["code"], "missing_argument")
                self.assertEqual(envelope["error"]["values"],
                                 {"command": "machine", "arguments": ["label"]})
                self.assertTrue(stderr.getvalue().startswith("error: "))


# The child of the probes of the outputs and of the installed command: one run of the
# ledger, or of its context, in a second process, as a scheduler or a redirection holds it.
_UTF8_CHILD = '''\
import sys

from ai_effort_ledger.cli import main

raise SystemExit(main(sys.argv[1:]))
'''

_EXECUTABLE_CHILD = '''\
import sys

from ai_effort_ledger.cli import _running_context

print(_running_context().executable)
'''


def run_child(words: list[str], environ: Mapping[str, str], out: Path,
              cwd: Path | None = None) -> subprocess.CompletedProcess:
    """One run of the child in a second process, whose standard output is the file that
    `out` holds, whose working directory is the one given, and whose streams the variable
    `PYTHONIOENCODING` forces to cp1252, as a redirection on a machine of the Windows code
    page holds them; the environment of the child is the one given over the environment of
    the tests."""
    with out.open("wb") as stdout:
        return subprocess.run([sys.executable, "-I", "-c", _UTF8_CHILD, *words],
                              env={**os.environ, **environ, "PYTHONIOENCODING": "cp1252"},
                              cwd=None if cwd is None else str(cwd),
                              stdout=stdout, stderr=subprocess.PIPE, check=False)


class TestUtf8Outputs(unittest.TestCase):
    """The two streams of a command carry UTF-8 (command-line.md › Form): a redirected run
    never dies of an output character, and the envelope of `--json` and the text tables
    reach their file whole. The probe runs the command in a second process whose streams
    hold cp1252, as every redirected run of a scheduler does, over a world whose folders
    of native logs and whose project folder hold a character outside cp1252."""

    def _world_outside_cp1252(self, base: Path) -> tuple[World, Path]:
        """The world of the probe, set up, with one settled session ingested by the
        command of the parent: its folder of native logs and the project folder of the
        session are invented names that cp1252 holds not."""
        world = build_world(base)
        logs = base / "logs-表"
        logs.mkdir()
        support.write_session(
            logs, "session-one",
            [support.prompt_record("Invented prompt text.", PROMPT_AT, UUID_ONE)],
            {}, base / "project-表")
        settle([logs / "session-one.jsonl"])
        set_up(world, world.store, recorded=str(world.store), logs=[logs])
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            self.assertEqual(main(["ingest"], build_context(world)), 0)
        return world, logs

    def test_ingest_writes_the_envelope_of_the_folders_whole(self) -> None:
        with support.TemporaryFolder() as base:
            world, logs = self._world_outside_cp1252(base)
            out = base / "ingest.json"
            done = run_child(["ingest", "--store", str(world.store), "--json"],
                             world.environ, out)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stderr, b"")
            envelope = json.loads(out.read_bytes().decode("utf-8"))
            self.assertEqual(envelope["command"], "ingest")
            self.assertEqual(envelope["sources"][0]["folder"], str(logs))

    def test_sessions_writes_the_text_of_the_project_folders_whole(self) -> None:
        with support.TemporaryFolder() as base:
            world, _ = self._world_outside_cp1252(base)
            out = base / "sessions.txt"
            done = run_child(["sessions", "2026-11-20", "--store", str(world.store)],
                             world.environ, out)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stderr, b"")
            self.assertIn("project-表", out.read_bytes().decode("utf-8"))


class TestRecordedStore(unittest.TestCase):
    """The store folder that setup writes in the machine configuration is an absolute
    path: a relative `--store` word is resolved before it is written, and every command
    reads the recorded store resolved again, so no command adopts a folder that another
    working directory holds under the same name, and the scheduled ingestion finds the
    store whatever its own working directory is (command-line.md › Setup, architecture.md
    › Files of a machine). The probe runs the commands in a second process, one whose
    working directory the parent chooses."""

    def _environ(self, base: Path, home: Path) -> dict[str, str]:
        """The environment of the children of the probe: the data folders and the home of
        the person inside `base`, so no child reads the machine that runs the tests."""
        return {DEVELOPMENT_VARIABLE: "1",
                "LOCALAPPDATA": str(base / "app-data"),
                "XDG_STATE_HOME": str(base / "state"),
                "XDG_DATA_HOME": str(base / "share"),
                "USERPROFILE": str(home), "HOME": str(home),
                "APPDATA": str(base / "app-data" / "roaming")}

    def test_setup_records_the_resolved_word_and_no_other_folder_is_adopted(self) -> None:
        with support.TemporaryFolder() as base:
            environ = self._environ(base, base / "home")
            first, second = base / "first", base / "second"
            first.mkdir()
            second.mkdir()
            machine = Path(platform.machine_folder(SYSTEM, environ, base / "home"))
            out = base / "setup.txt"
            done = run_child(["setup", "--store", "worklog", "--schedule", "no"],
                             environ, out, cwd=first)
            self.assertEqual(done.returncode, 0, done.stderr)
            written = configuration.read_machine_configuration(machine)
            self.assertEqual(written.store, str((first / "worklog").resolve()))
            # The folder that another working directory holds under the same name, with a
            # person configuration of its own, is not adopted as the store of the machine.
            planted = second / "worklog"
            planted.mkdir(parents=True)
            configuration.create_person_configuration(planted, ZONE)
            person = planted / PERSON_FILE
            person.write_text(
                person.read_text(encoding="utf-8")
                + '\n[[project]]\nid = "planted"\nname = "Invented planted project."\n',
                encoding="utf-8")
            out = base / "show.json"
            done = run_child(["config", "show", "--json"], environ, out, cwd=second)
            self.assertEqual(done.returncode, 0, done.stderr)
            shown = json.loads(out.read_bytes().decode("utf-8"))
            self.assertNotIn("planted", json.dumps(shown))


class TestInstalledExecutable(unittest.TestCase):
    """The absolute path of the installed command that the entry of the scheduled
    ingestion carries (ingestion.md › Frequency): the command that the PATH of the
    machine holds, else the path that started the process, resolved, when `sys.argv[0]`
    is a path, else the bare name of the program."""

    def test_a_scrubbed_path_leaves_the_path_of_the_start(self) -> None:
        with support.TemporaryFolder() as folder:
            started = folder / "started-by-its-path.py"
            started.write_text(_EXECUTABLE_CHILD, encoding="utf-8")
            done = subprocess.run(
                [sys.executable, "-I", str(started)],
                env={**os.environ, "PATH": "", "LOCALAPPDATA": str(folder / "app-data"),
                     "XDG_STATE_HOME": str(folder / "state"),
                     "XDG_DATA_HOME": str(folder / "share"),
                     "USERPROFILE": str(folder / "home"), "HOME": str(folder / "home"),
                     "APPDATA": str(folder / "app-data" / "roaming")},
                capture_output=True, check=False)
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertEqual(done.stdout.decode("utf-8").strip(), str(started.resolve()))

    def test_the_executable_the_path_holds_wins(self) -> None:
        found = Path("D:/Work/Product/ai-effort-ledger")
        self.assertEqual(_installed_executable(lambda _: str(found), "-c"), found)

    def test_the_path_of_the_start_when_it_is_one(self) -> None:
        with support.TemporaryFolder() as folder:
            started = folder / "ai-effort-ledger"
            started.write_text("", encoding="utf-8")
            self.assertEqual(_installed_executable(lambda _: None, str(started)),
                             started.resolve())

    def test_the_bare_word_without_a_path_of_the_start(self) -> None:
        # The word that started the process is no path: the interpreter of `-c`, the
        # bare name that no folder of the PATH holds, or no word at all.
        for started in (PROGRAM, "-c", ""):
            self.assertEqual(_installed_executable(lambda _: None, started),
                             Path(PROGRAM))


class TestRunProgram(unittest.TestCase):
    """The call of a scheduler program captures its output as text: a byte that the code
    page of the machine holds not degrades, and the read keeps a decodable stdout, so one
    byte of an answer can no longer turn a live entry into none (architecture.md ›
    Runtime)."""

    def test_a_byte_outside_the_code_page_degrades(self) -> None:
        done = _run_program([sys.executable, "-I", "-c",
                             "import sys; sys.stdout.buffer.write(bytes([0x90, 0x41]))"])
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout, "�A")  # the byte 0x90 degrades
        self.assertEqual(done.stderr, "")


def write_person_language(store: Path, chosen: str) -> None:
    """Add the key `language` of the `[report]` table to the person configuration of a
    store folder, which holds no `[report]` table yet."""
    path = store / PERSON_FILE
    path.write_text(path.read_text(encoding="utf-8") + f'\n[report]\nlanguage = "{chosen}"\n',
                    encoding="utf-8")


class TestLanguageOfThePerson(support.FixtureStores):
    """The language of the output after the parse takes its value through the layers of
    configuration.md › Order: `--language`, then `[report] language` of the person
    configuration, then `en`; the help and the faults of the parse, and the stop of a
    ledger that gives no person configuration to read, take it from the command line alone
    (command-line.md › Form)."""

    STORES = ("manual_entries",)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._context = cls._contexts["manual_entries"]
        write_person_language(support.fixture_store_folder(cls._homes["manual_entries"]), "it")
        cls._day = support.FIXTURE_DAY_ONE.isoformat()
        values = {"event_uid": support.build_uid(1)}
        cls._overlap = {chosen: language.message("manual_entry_overlap", values, chosen)
                        for chosen in language.LANGUAGES}

    def test_a_report_takes_the_language_of_the_person_without_the_option(self) -> None:
        for words, chosen, other in (
                (["report", "day", self._day], "it", "en"),
                (["report", "day", self._day, "--language", "en"], "en", "it"),
                (["report", "day", self._day, "--language", "it"], "it", "en")):
            with self.subTest(words=" ".join(words)):
                code, shown, error = support.run_main(self._context, *words)
                self.assertEqual(code, 0, error)
                self.assertEqual(error, f"warning: {self._overlap[chosen]}\n")
                self.assertIn(language.label("human_time", chosen), shown)
                self.assertNotIn(language.label("human_time", other), shown)
                code, shown, error = support.run_main(self._context, *words, "--json")
                self.assertEqual(code, 0, error)
                document = json.loads(shown)
                self.assertEqual(document["warnings"][0]["message"], self._overlap[chosen])
                self.assertEqual(document["record"]["parameters"]["language"], chosen)

    def test_an_action_without_figures_takes_the_language_of_the_person(self) -> None:
        code, shown, error = support.run_main(self._context, "entries", self._day)
        self.assertEqual((code, error), (0, ""))
        self.assertIn(language.label("events", "it"), shown)
        self.assertNotIn(language.label("events", "en"), shown)
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            write_person_language(world.store, "it")
            code, shown, error = run_action(world, ["machine", "label", "Invented Machine"])
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(shown, f"{language.label('machine', 'it')}: {MACHINE}\n"
                                    f"{language.label('label', 'it')}: Invented Machine\n")

    def test_a_stop_error_of_the_action_takes_the_language_of_the_person(self) -> None:
        values = {"target": "no-such-uid"}
        wanted = {chosen: language.message("target_not_found", values, chosen)
                  for chosen in language.LANGUAGES}
        code, shown, error = support.run_main(self._context, "retract", "no-such-uid")
        self.assertEqual((code, shown, error), (1, "", f"error: {wanted['it']}\n"))
        code, shown, error = support.run_main(self._context, "retract", "no-such-uid", "--json")
        self.assertEqual((code, error), (1, f"error: {wanted['it']}\n"))
        self.assertEqual(json.loads(shown)["error"]["message"], wanted["it"])
        code, _, error = support.run_main(
            self._context, "retract", "no-such-uid", "--language", "en")
        self.assertEqual((code, error), (1, f"error: {wanted['en']}\n"))

    def test_the_help_and_the_faults_of_the_parse_stay_in_the_words_language(self) -> None:
        for words, wanted in ((["--help"], "usage:"), (["report", "day", "--help"], "usage:"),
                              (["--language", "it", "--help"], "uso:")):
            with self.subTest(words=" ".join(words)):
                code, shown, error = support.run_main(self._context, *words)
                self.assertEqual((code, error), (0, ""))
                self.assertIn(wanted, shown)
        code, shown, error = support.run_main(self._context, "reprot")
        self.assertEqual((code, shown), (2, ""))
        self.assertEqual(error, "error: The command ai-effort-ledger does not know reprot.\n")
        code, shown, error = support.run_main(self._context, "report", "timesheet")
        self.assertEqual((code, shown), (2, ""))
        self.assertEqual(error, "error: The command report timesheet needs --from, --to.\n")

    def test_the_faults_of_the_values_stay_in_the_words_language(self) -> None:
        code, shown, error = support.run_main(
            self._context, "report", "day", self._day, "--idle-gap", "Invented")
        self.assertEqual((code, shown), (2, ""))
        self.assertEqual(error, "error: The value Invented is not valid for --idle-gap.\n")

    def test_a_ledger_that_gives_no_configuration_stops_in_the_words_language(self) -> None:
        wanted = {chosen: f"error: {language.message('setup_required', {}, chosen)}\n"
                  for chosen in language.LANGUAGES}
        with support.TemporaryFolder() as base:
            world = build_world(base)
            self.assertEqual(run_action(world, ["entries", self._day])[1:], ("", wanted["en"]))
            self.assertEqual(
                run_action(world, ["entries", self._day, "--language", "it"])[1:],
                ("", wanted["it"]))
            write_machine(world, recorded=str(world.store))  # a machine without a person
            self.assertEqual(run_action(world, ["entries", self._day])[1:], ("", wanted["en"]))
            world.store.mkdir()
            (world.store / PERSON_FILE).write_text("[[time_zone]]\nzone = \"\"\n",
                                                   encoding="utf-8")
            code, shown, error = run_action(world, ["entries", self._day])
            self.assertEqual((code, shown), (1, ""))
            self.assertTrue(error.startswith("error: The configuration file "), error)
            code, shown, error = run_action(world, ["entries", self._day, "--language", "it"])
            self.assertEqual((code, shown), (1, ""))
            self.assertTrue(error.startswith("error: Il file di configurazione "), error)

    def test_a_language_outside_the_languages_stops_with_the_unreadable_file(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            write_person_language(world.store, "fr")
            code, shown, error = run_action(world, ["entries", self._day])
            self.assertEqual((code, shown), (1, ""))
            self.assertTrue(error.startswith("error: The configuration file "), error)

    def test_setup_stops_on_a_person_configuration_that_cannot_be_read(self) -> None:
        """`setup` creates the person configuration only when none exists: on a store
        folder whose person configuration cannot be read it stops with exit code 1 and
        `configuration_unreadable`, in the language of the command line, and leaves the
        file as it was (command-line.md › Form)."""
        for chosen in language.LANGUAGES:
            with self.subTest(language=chosen), support.TemporaryFolder() as base:
                world = build_world(base)
                world.store.mkdir()
                path = world.store / PERSON_FILE
                path.write_text('[[time_zone]]\nzone = ""\n', encoding="utf-8")
                for as_json in ((), ("--json",)):
                    code, shown, error = run_action(
                        world, ["setup", "--store", str(world.store), "--language", chosen,
                                *as_json],
                        build_context(world, run=FakeRun()))
                    self.assertEqual(code, 1, error)
                    values = {"path": str(path), "line": 1}
                    wanted = language.message("configuration_unreadable", values, chosen)
                    self.assertEqual(error, f"error: {wanted}\n")
                    if as_json:
                        self.assertEqual(json.loads(shown)["error"], {
                            "code": "configuration_unreadable", "values": values,
                            "message": wanted})
                    else:
                        self.assertEqual(shown, "")
                self.assertEqual(path.read_text(encoding="utf-8"), '[[time_zone]]\nzone = ""\n')

    def test_setup_takes_the_language_of_the_person(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            write_person_language(world.store, "it")
            code, shown, error = run_action(
                world, ["setup", "--store", str(world.store)],
                build_context(world, run=FakeRun()))
            self.assertEqual((code, error), (0, ""))
            self.assertIn(f"{language.label('machine', 'it')}:", shown)
            self.assertNotIn("Machine:", shown)
        with support.TemporaryFolder() as base:  # a ledger without a person configuration
            world = build_world(base)
            code, shown, error = run_action(
                world, ["setup", "--store", str(world.store)],
                build_context(world, run=FakeRun()))
            self.assertEqual((code, error), (0, ""))
            self.assertIn("Machine:", shown)

    def test_setup_of_a_new_machine_takes_the_language_of_the_store(self) -> None:
        """A machine without a machine configuration that sets up a store folder whose
        person configuration exists reads `[report] language` of it, because the ledger
        gives a person configuration to read (command-line.md › Form)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            world.store.mkdir()
            configuration.create_person_configuration(world.store, ZONE)
            write_person_language(world.store, "it")
            self.assertIsNone(configuration.read_machine_configuration(world.machine))
            code, shown, error = run_action(
                world, ["setup", "--store", str(world.store)],
                build_context(world, run=FakeRun()))
            self.assertEqual((code, error), (0, ""))
            self.assertIn(f"{language.label('machine', 'it')}:", shown)
            self.assertNotIn("Machine:", shown)

    def test_config_show_names_the_layer_of_the_language(self) -> None:
        code, shown, error = support.run_main(self._context, "config", "show", "--json")
        self.assertEqual((code, error), (0, ""))
        parameters = {one["name"]: one for one in json.loads(shown)["parameters"]}
        self.assertEqual(parameters["language"],
                         {"name": "language", "value": "it", "layer": "person"})
        code, shown, error = support.run_main(self._context, "config", "show")
        self.assertEqual((code, error), (0, ""))
        self.assertIn(language.label("parameters", "it"), shown)
        self.assertNotIn(language.label("parameters", "en") + "\n", shown)

    def test_version_reads_no_configuration(self) -> None:
        """`version` reads no configuration: on the store of the class, whose person
        configuration gives the language `it`, its text stays in English; on a ledger
        whose person configuration cannot be read — where every other command stops with
        the unreadable file — it completes with exit code 0, in the language of the
        command line (command-line.md › Setup, › Form)."""
        code, shown, error = support.run_main(self._context, "version")
        self.assertEqual((code, error), (0, ""))
        self.assertIn("Ledger:", shown)
        self.assertNotIn("ledger:", shown)
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            (world.store / PERSON_FILE).write_text('[[time_zone]]\nzone = ""\n',
                                                   encoding="utf-8")
            context = build_context(world)
            code, shown, error = support.run_main(context, "version")
            self.assertEqual((code, error), (0, ""))
            self.assertIn("Ledger:", shown)
            code, shown, error = support.run_main(context, "version", "--language", "it")
            self.assertEqual((code, error), (0, ""))
            self.assertIn("ledger:", shown)
            self.assertNotIn("Ledger:", shown)
            code, shown, error = support.run_main(context, "entries", "2026-11-20")
            self.assertEqual((code, shown), (1, ""))
            self.assertTrue(error.startswith("error: The configuration file "), error)


class TestStopErrors(unittest.TestCase):
    """Every stop error that an exception class of the package carries is a stop code with
    its text in both languages (command-line.md › Exit codes)."""

    def test_every_stop_error_has_its_texts(self) -> None:
        carried: set[str] = set()
        for cls in _exception_classes(_modules()):
            code = getattr(cls, "code", None)
            if isinstance(code, str):
                self.assertIn(code, language.STOP_CODES, str(cls))
                carried.add(code)
            for value in vars(cls).values():
                holder = value.__func__ if isinstance(value, (classmethod, staticmethod)) \
                    else value
                body = getattr(holder, "__code__", None)
                for const in getattr(body, "co_consts", ()):
                    if const in language.STOP_CODES:
                        carried.add(const)
        self.assertTrue(carried)  # the walk finds the stop errors of the package
        for code in language.STOP_CODES:
            for lang in language.LANGUAGES:
                self.assertTrue(language.message(code, AnyValues(), lang), f"{code}/{lang}")


class TestSetupAction(unittest.TestCase):
    """The action of `setup`: the seven steps through `main`, their JSON document and
    their text (command-line.md › Setup, › JSON documents)."""

    def test_setup_json(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            write_session(world, logs)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["setup", "--store", str(world.store), "--json"],
                            build_context(world, run=FakeRun()))
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "setup")
            self.assertEqual(envelope["warnings"], [])
            self.assertEqual(envelope["configuration_errors"], [])
            self.assertEqual(envelope["machine"], "1a2b3c4d-0000-4000-8000-000000000001")
            self.assertEqual(envelope["store"], str(world.store))
            self.assertTrue(envelope["configuration_created"])
            self.assertEqual(envelope["schedule"], {
                "name": platform.ENTRY_NAME,
                "command": f"{EXECUTABLE} ingest --store {world.store}",
                "time": "12:00",
            })
            self.assertEqual(envelope["ingest"], {"sources": [{
                "source": "claude-code-jsonl", "folder": str(logs),
                "new_events": 1, "sessions_held_back": 0}]})
            person = configuration.read_person_configuration(world.store)
            self.assertEqual(person.time_zones[0].zone, ZONE)
            self.assertEqual(person.day_starts[0].hour, time(0, 0))
            machine = configuration.read_machine_configuration(world.machine)
            self.assertIn(str(logs), machine.native_logs["claude-code"])
        with support.TemporaryFolder() as base:  # the text of the same steps
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            write_session(world, logs)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["setup", "--store", str(world.store)],
                            build_context(world, run=FakeRun()))
            self.assertEqual(code, 0)
            shown = stdout.getvalue()
            for line in ("Machine: 1a2b3c4d-0000-4000-8000-000000000001",
                         f"Store folder: {world.store}",
                         "Created: yes",
                         "Entries",
                         "time_zone zone=Etc/UTC from=1970-01-01T00:00:00Z",
                         "day_start hour=00:00 from=1970-01-01",
                         "Retention",
                         "claude-code cleanupPeriodDays 30",
                         "claude-desktop desktopSessionCleanupPeriodDays none",
                         "Scheduled ingestion:",
                         f"Command: {EXECUTABLE} ingest --store {world.store}",
                         "Hour: 12:00",
                         "Ingestion",
                         "New events: 1",
                         "Sessions held back: 0"):
                self.assertIn(line, shown, line)
            self.assertEqual(stderr.getvalue(), "")

    def test_setup_text_shows_the_machine_label(self) -> None:
        """The text of `setup` shows the machine label beside the identifier when the store
        holds one, as `machine label` does — the line of the label after the line of the
        machine, in the language of the output — and the identifier alone otherwise; the
        document keeps the identifier under `machine` and holds the label as
        `machine_label`, after `machine`, only when the store holds one (command-line.md ›
        Setup, › JSON documents)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            context = build_context(world, run=FakeRun())
            code, shown, error = support.run_main(context, "setup", "--store",
                                                  str(world.store))
            self.assertEqual((code, error), (0, ""))
            machine = configuration.read_machine_configuration(world.machine).machine
            self.assertEqual(shown.splitlines()[:2],
                             [f"Machine: {machine}", f"Store folder: {world.store}"])
            code, shown, error = support.run_main(context, "setup", "--store",
                                                  str(world.store), "--json")
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(list(json.loads(shown))[:2], ["machine", "store"])
            for chosen in language.LANGUAGES:
                code, shown, error = support.run_main(
                    context, "setup", "--store", str(world.store), "--label",
                    "Invented Machine", "--language", chosen)
                self.assertEqual((code, error), (0, ""))
                self.assertEqual(shown.splitlines()[:2], [
                    f"{language.label('machine', chosen)}: {machine}",
                    f"{language.label('label', chosen)}: Invented Machine"])
            code, shown, error = support.run_main(context, "setup", "--store",
                                                  str(world.store), "--json")
            self.assertEqual((code, error), (0, ""))
            document = json.loads(shown)
            self.assertEqual(list(document)[:3], ["machine", "machine_label", "store"])
            self.assertEqual((document["machine"], document["machine_label"]),
                             (machine, "Invented Machine"))

    def test_setup_text_gives_the_retention_advice(self) -> None:
        """Step 5 of the text of `setup`: after the retention period of each agent tool, what
        the period means, then the advice of a longer retention period with the setting to
        change and its cost, before the scheduled ingestion, in the language of the output;
        the JSON document holds none of it (command-line.md › Setup, › JSON documents;
        ingestion.md › Frequency)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            context = build_context(world, run=FakeRun())
            for chosen in language.LANGUAGES:
                code, shown, error = support.run_main(
                    context, "setup", "--store", str(world.store), "--language", chosen)
                self.assertEqual((code, error), (0, ""))
                lines = shown.splitlines()
                at = lines.index(language.label("retention", chosen))
                self.assertEqual(lines[at + 3:at + 6], [
                    language.note("retention_meaning", chosen),
                    language.note("retention_advice", chosen),
                    f"{language.label('scheduled_ingestion', chosen)}:"])
            code, shown, error = support.run_main(context, "setup", "--store",
                                                  str(world.store), "--json")
            self.assertEqual((code, error), (0, ""))
            self.assertNotIn("retention", shown)

    def test_setup_text_names_the_person_configuration_file(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["setup", "--store", str(world.store)],
                            build_context(world, run=FakeRun()))
            self.assertEqual(code, 0)
            lines = stdout.getvalue().splitlines()
            line = f"Person configuration: {world.store / PERSON_FILE}"
            self.assertEqual(lines[lines.index("Created: yes") + 1], line)
            self.assertEqual(lines[lines.index(line) + 1], "Entries")
            stdout = io.StringIO()  # a second setup finds the file and names nothing
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["setup", "--store", str(world.store)],
                            build_context(world, run=FakeRun()))
            self.assertEqual(code, 0)
            self.assertIn("Created: no", stdout.getvalue())
            self.assertNotIn("Person configuration", stdout.getvalue())
            self.assertNotIn("Entries", stdout.getvalue())
        with support.TemporaryFolder() as base:  # the same line in Italian
            world = build_world(base)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                code = main(["setup", "--store", str(world.store), "--language", "it"],
                            build_context(world, run=FakeRun()))
            self.assertEqual(code, 0)
            self.assertIn(f"configurazione personale: {world.store / PERSON_FILE}",
                          stdout.getvalue().splitlines())

    def test_setup_json_holds_no_key_for_the_person_configuration_file(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(io.StringIO()):
                code = main(["setup", "--store", str(world.store), "--json"],
                            build_context(world, run=FakeRun()))
            self.assertEqual(code, 0)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(
                set(envelope) - {"command", "warnings", "configuration_errors"},
                {"machine", "store", "configuration_created", "schedule", "ingest"})

    def test_setup_wrong_native_logs_stops_before_any_write(self) -> None:
        for value in ("no-equals-sign", "=folder", "tool="):
            for version in (VERSION, DEV_VERSION):
                with self.subTest(value=value, version=version):
                    with support.TemporaryFolder() as base:
                        world = build_world(base)
                        environ = {key: held for key, held in world.environ.items()
                                   if key != DEVELOPMENT_VARIABLE}  # no leave to write
                        words = ["setup", "--native-logs", value, "--store",
                                 str(world.store)]
                        context = build_context(world, version=version, environ=environ)
                        stdout, stderr = io.StringIO(), io.StringIO()
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main(words, context)
                        self.assertEqual(code, 2)
                        self.assertEqual(stdout.getvalue(), "")
                        self.assertEqual(
                            stderr.getvalue(),
                            f"error: The value {value} is not valid for "
                            "--native-logs.\n")
                        stdout = io.StringIO()
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(io.StringIO()):
                            code = main(words + ["--json"], context)
                        self.assertEqual(code, 2)
                        envelope = json.loads(stdout.getvalue())
                        self.assertEqual(envelope["command"], "setup")
                        self.assertEqual(envelope["error"]["code"], "wrong_value")
                        self.assertEqual(envelope["error"]["values"],
                                         {"key": "--native-logs", "value": value})
                        self.assertFalse(world.machine.exists())  # no configuration, no lock
                        self.assertFalse(world.store.exists())

    def test_setup_wrong_native_logs_in_italian(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            stderr = io.StringIO()
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                code = main(["setup", "--native-logs", "tool=", "--store", str(world.store),
                             "--language", "it"], build_context(world))
            self.assertEqual(code, 2)
            self.assertEqual(
                stderr.getvalue(),
                "error: " + language.message(
                    "wrong_value", {"key": "--native-logs", "value": "tool="}, "it")
                + "\n")
            self.assertFalse(world.machine.exists())


class TestScheduleActions(unittest.TestCase):
    """The three actions of `schedule`: the entry shown, created, and removed through the
    fake of the scheduler program, so no test reaches the scheduler of the machine that
    runs the tests (command-line.md › Commands)."""

    def _schedule(self, world: World, system: str, words: list[str],
                  run: Callable[[list[str]], subprocess.CompletedProcess]
                  ) -> tuple[int, str, str]:
        """Run one `schedule` command on the world as the system: its exit code, standard
        output, and standard error."""
        stdout, stderr = io.StringIO(), io.StringIO()
        context = build_context(world, run=run)._replace(system=system)
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(["schedule", *words], context)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_schedule_show_create_remove(self) -> None:
        """`schedule show` gives the entry that `schedule create` made, and the entry at its
        new time after a replace, on every scheduler that keeps one: the Task Scheduler
        through the fake that holds it, launchd and systemd through the files in the home
        of the world; cron holds none. A remove takes the entry away, and a remove without
        an entry completes with the warning `no_schedule_entry`, also when the scheduler
        program would end with an error. The test runs as each system on every runner; the
        Linux case runs twice, with `shutil.which` patched to find `systemctl` (systemd)
        and to find nothing (cron), so all four kinds run on every runner. The working
        folder is the temporary folder: on a runner that is not Windows the machine-local
        data folder of a `Windows` context is a pure path whose text reads as a relative
        name."""
        no_entry = [{
            "code": "no_schedule_entry", "values": {},
            "message": "The ledger has no scheduled ingestion to remove.",
        }]
        cases = (("Windows", None), ("Darwin", None),
                 ("Linux", "/usr/bin/systemctl"), ("Linux", None))
        for system, program in cases:
            with (mock.patch("shutil.which", return_value=program),
                  self.subTest(system=system, systemctl=program),
                  support.TemporaryFolder() as base, contextlib.chdir(base)):
                kind = platform.scheduler_kind(system, shutil.which)
                world = build_world(base)
                world = world._replace(
                    machine=Path(platform.machine_folder(system, world.environ, world.home)))
                set_up(world, world.store, recorded=str(world.store))
                scheduler = HoldingRun()

                def entry(hour: str) -> dict[str, str]:
                    return {"name": platform.ENTRY_NAME,
                            "command": f"{EXECUTABLE} ingest --store {world.store}",
                            "time": hour}

                code, stdout, _ = self._schedule(world, system, ["show", "--json"], scheduler)
                self.assertEqual(code, 0)
                self.assertIsNone(json.loads(stdout)["schedule"])
                code, stdout, _ = self._schedule(world, system, ["create", "--json"], scheduler)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(stdout)["schedule"], entry("12:00"))
                code, stdout, _ = self._schedule(world, system, ["show", "--json"], scheduler)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(stdout)["schedule"],
                                 None if kind == "cron" else entry("12:00"))
                code, stdout, _ = self._schedule(  # another time of day
                    world, system, ["create", "--time", "06:30", "--json"], scheduler)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(stdout)["schedule"], entry("06:30"))
                code, stdout, _ = self._schedule(world, system, ["show", "--json"], scheduler)
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(stdout)["schedule"],
                                 None if kind == "cron" else entry("06:30"))
                code, stdout, _ = self._schedule(world, system, ["remove", "--json"], scheduler)
                self.assertEqual(code, 0)
                envelope = json.loads(stdout)
                self.assertIsNone(envelope["schedule"])
                self.assertEqual(envelope["warnings"], no_entry if kind == "cron" else [])
                code, stdout, _ = self._schedule(world, system, ["show", "--json"], scheduler)
                self.assertEqual(code, 0)
                self.assertIsNone(json.loads(stdout)["schedule"])
                code, stdout, stderr = self._schedule(  # no entry to remove
                    world, system, ["remove", "--json"], FakeRun(code=1))
                self.assertEqual(code, 0)
                envelope = json.loads(stdout)
                self.assertIsNone(envelope["schedule"])
                self.assertEqual(envelope["warnings"], no_entry)
                self.assertEqual(
                    stderr, "warning: The ledger has no scheduled ingestion to remove.\n")
        with support.TemporaryFolder() as base:  # the text of the entry and of none
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            kind = platform.scheduler_kind(SYSTEM, shutil.which)
            scheduler = HoldingRun()
            code, stdout, _ = self._schedule(world, SYSTEM, ["show"], scheduler)
            self.assertEqual(code, 0)
            self.assertEqual(stdout, "Scheduled ingestion: none\n")
            code, created, _ = self._schedule(world, SYSTEM, ["create"], scheduler)
            self.assertEqual(code, 0)
            self.assertIn("Scheduled ingestion:", created)
            self.assertIn(f"Command: {EXECUTABLE} ingest --store {world.store}", created)
            self.assertIn("Hour: 12:00", created)
            code, stdout, _ = self._schedule(world, SYSTEM, ["show"], scheduler)
            self.assertEqual(code, 0)
            self.assertEqual(
                stdout, "Scheduled ingestion: none\n" if kind == "cron" else created)
            code, stdout, _ = self._schedule(world, SYSTEM, ["remove"], scheduler)
            self.assertEqual(code, 0)
            self.assertEqual(stdout, "Scheduled ingestion: none\n")
            code, stdout, stderr = self._schedule(world, SYSTEM, ["remove"], FakeRun(code=1))
            self.assertEqual(code, 0)
            self.assertEqual(stdout, "Scheduled ingestion: none\n")
            self.assertIn("warning: The ledger has no scheduled ingestion", stderr)

    def test_schedule_create_refuses_a_word_the_kind_cannot_carry(self) -> None:
        """`schedule create` refuses a store folder with a word the scheduler of the
        operating system cannot carry, with the code of a wrong value, before it writes
        anything: no scheduler program runs and no file of the entry appears, whatever
        the kind of the machine that runs the test."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            store = world.store / "Sto\x01re"
            run = FakeRun()
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["schedule", "create", "--store", str(store), "--json"],
                            build_context(world, run=run))
            self.assertEqual(code, 2)
            self.assertEqual(run.calls, [])  # the scheduler is never called
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["error"]["code"], "wrong_value")
            self.assertEqual(envelope["error"]["values"],
                             {"key": "--store", "value": str(store)})
            self.assertEqual(
                stderr.getvalue(),
                "error: " + language.message(
                    "wrong_value", {"key": "--store", "value": str(store)}, "en") + "\n")
            self.assertFalse(
                (world.home / "Library" / "LaunchAgents").exists())
            self.assertFalse(
                (world.home / ".config" / "systemd" / "user").exists())
            self.assertFalse(store.exists())

    def test_schedule_create_refuses_the_configured_store_the_kind_cannot_carry(self) -> None:
        """`schedule create` refuses the store folder that the machine configuration
        records when it holds a word the scheduler of the operating system cannot
        carry, with the code of a wrong value, before it writes anything, also without
        `--store`: no scheduler program runs and no file of the entry appears, whatever
        the kind of the machine that runs the test."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            store = world.store / "Sto\x01re"
            write_machine(world, recorded=str(store))
            run = FakeRun()
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["schedule", "create", "--json"], build_context(world, run=run))
            self.assertEqual(code, 2)
            self.assertEqual(run.calls, [])  # the scheduler is never called
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["error"]["code"], "wrong_value")
            self.assertEqual(envelope["error"]["values"],
                             {"key": "--store", "value": str(store)})
            self.assertEqual(
                stderr.getvalue(),
                "error: " + language.message(
                    "wrong_value", {"key": "--store", "value": str(store)}, "en") + "\n")
            self.assertFalse(
                (world.home / "Library" / "LaunchAgents").exists())
            self.assertFalse(
                (world.home / ".config" / "systemd" / "user").exists())
            self.assertFalse(store.exists())

    def test_schedule_create_failed_scheduler_exits_1(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["schedule", "create", "--json"],
                            build_context(world, run=FakeRun(code=1)))
            kind = platform.scheduler_kind(SYSTEM, shutil.which)
            if kind == "cron":  # cron neither writes nor calls a program
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(stdout.getvalue())["warnings"], [])
            else:
                self.assertEqual(code, 1)
                program = SCHEDULER_PROGRAM[kind]
                envelope = json.loads(stdout.getvalue())
                self.assertEqual(envelope["error"], {
                    "code": "scheduler_failed",
                    "values": {"program": program, "exit_code": 1},
                    "message": f"The scheduler program {program} ended with exit code 1.",
                })
                self.assertNotIn("schedule", envelope)  # no document beside the error
                self.assertEqual(
                    stderr.getvalue(),
                    f"error: The scheduler program {program} ended with exit code 1.\n")

    def test_schedule_create_refused_for_development_version(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            run = FakeRun()  # the environment lets the version write: it is refused anyway
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["schedule", "create", "--json"],
                            build_context(world, run=run, version=DEV_VERSION))
            self.assertEqual(code, 1)
            self.assertEqual(run.calls, [])  # the scheduler is never called
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["error"], {
                "code": "development_version",
                "values": {},
                "message": "A development version does not write to the store; set"
                           " AI_EFFORT_LEDGER_DEVELOPMENT=1 to allow it.",
            })
            self.assertEqual(
                stderr.getvalue(),
                "error: A development version does not write to the store; set"
                " AI_EFFORT_LEDGER_DEVELOPMENT=1 to allow it.\n")

    def test_schedule_entry_runs_context_executable(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            run = FakeRun()
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["schedule", "create", "--json"], build_context(world, run=run))
            self.assertEqual(code, 0)
            schedule = json.loads(stdout.getvalue())["schedule"]
            self.assertEqual(schedule["command"],
                             f"{EXECUTABLE} ingest --store {world.store}")
            kind = platform.scheduler_kind(SYSTEM, shutil.which)
            if kind == "windows":
                created = [words for words in run.calls if "/Create" in words]
                self.assertEqual(len(created), 1)
                self.assertTrue(any(str(EXECUTABLE) in document for document in run.documents))
            elif kind == "launchd":
                self.assertEqual([words[0] for words in run.calls],
                                 ["launchctl", "launchctl"])
            elif kind == "systemd":
                self.assertEqual([words[0] for words in run.calls],
                                 ["systemctl", "systemctl"])
            else:
                self.assertEqual(run.calls, [])  # cron writes no entry and calls no program


class TestIngestAction(unittest.TestCase):
    """The action of `ingest`: the counts of each folder of native logs, and the exit
    code 3 when the figures are not complete — lost events, or the file of a session that
    the agent tool deleted between the selection and the read (command-line.md ›
    Commands, › Exit codes)."""

    def test_ingest_counts_and_lost_events_exit_3(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            write_session(world, logs)
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["ingest", "--json"], build_context(world))
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "ingest")
            self.assertEqual(envelope["sources"], [{
                "source": "claude-code-jsonl", "folder": str(logs),
                "new_events": 1, "sessions_held_back": 0}])
            self.assertEqual(envelope["warnings"], [])
        with support.TemporaryFolder() as base:  # the text of the counts
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            write_session(world, logs)
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["ingest"], build_context(world))
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "Source: claude-code-jsonl\n"
                             f"Folder: {logs}\nNew events: 1\nSessions held back: 0\n")
        with support.TemporaryFolder() as base:  # native logs deleted before the reading
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            path = write_session(world, logs)
            (logs.parent / "settings.json").write_text('{"cleanupPeriodDays": 7}\n',
                                                       encoding="utf-8")
            state = ingestion.SourcesState()
            state.folders[str(logs)] = "2026-11-10T12:00:00.000Z"
            state.files[str(path)] = ingestion.file_stamp(path)
            state.save(ingestion.sources_path(world.machine, world.store, SYSTEM))
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["ingest", "--json"], build_context(world))
            self.assertEqual(code, 3)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["sources"], [{
                "source": "claude-code-jsonl", "folder": str(logs),
                "new_events": 0, "sessions_held_back": 0}])
            self.assertEqual(envelope["warnings"], [{
                "code": "lost_events",
                "values": {"folder": str(logs), "from": "2026-11-10T12:00:00.000Z",
                           "to": "2026-11-24T12:00:00.000Z"},
                "message": "Native logs of the folder " f"{logs} were deleted before the"
                           " ingestion read them, between 2026-11-10T12:00:00.000Z and"
                           " 2026-11-24T12:00:00.000Z.",
            }])
            self.assertTrue(stderr.getvalue().startswith("warning: Native logs of the"))

    def test_ingest_of_a_file_gone_between_selection_and_read_exits_3(self) -> None:
        """The agent tool can delete the file of a session between the selection that named
        it and the read of the file: the ingestion completes, but the figures are not
        complete — the events the file held are lost — and the warning `native_log_gone`
        gives the exit code 3 (command-line.md › Exit codes, ingestion.md › Frequency,
        claude-code-adapter.md › Reading rules)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            path = write_session(world, logs)
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            context = build_context(world)._replace(adapters=[GoneAfterSelection(
                support.adapters_for_tests(world.home), path)])
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["ingest", "--json"], context)
            self.assertEqual(code, 3)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "ingest")
            self.assertEqual(envelope["sources"], [{
                "source": "claude-code-jsonl", "folder": str(logs),
                "new_events": 0, "sessions_held_back": 0}])
            self.assertEqual(envelope["warnings"], [{
                "code": "native_log_gone", "values": {"file": str(path)},
                "message": f"The native log {path} is gone; it gives no event.",
            }])
            self.assertEqual(stderr.getvalue(),
                             f"warning: The native log {path} is gone; it gives no"
                             " event.\n")


class TestStoreActions(unittest.TestCase):
    """The actions that read or write the store: the label of the machine, the two config
    commands, the rebuild of the index, and `version` (command-line.md › Commands, ›
    Configuration entries, › JSON documents)."""

    def test_machine_label(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["machine", "label", "Invented Machine", "--json"],
                            build_context(world))
            self.assertEqual(code, 0)
            self.assertEqual(stderr.getvalue(), "")
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "machine label")
            self.assertEqual(envelope["machine"], MACHINE)
            self.assertEqual(envelope["label"], "Invented Machine")
            self.assertEqual(store.machine_labels(world.store, [MACHINE]),
                             ({MACHINE: "Invented Machine"}, []))
            stdout, stderr = io.StringIO(), io.StringIO()  # another label replaces it
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["machine", "label", "Renamed Machine", "--json"],
                            build_context(world))
            self.assertEqual(code, 0)
            self.assertEqual(store.machine_labels(world.store, [MACHINE]),
                             ({MACHINE: "Renamed Machine"}, []))
            stdout, stderr = io.StringIO(), io.StringIO()  # the text of the label
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["machine", "label", "Invented Machine"], build_context(world))
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(),
                             f"Machine: {MACHINE}\nMachine label: Invented Machine\n")

    def test_machine_label_refuses_a_blank_label(self) -> None:
        """A label that is blank after `strip()` shows no name where an output names the
        machine, so `machine label` stops with the wrong value of its `<text>`, the exit
        code 2, in both languages, and the label that the store holds stays
        (command-line.md › Commands, › Exit codes)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            code, _, error = support.run_main(build_context(world), "machine", "label",
                                              "Invented Machine")
            self.assertEqual((code, error), (0, ""))
            texts = {"en": "The value  \t  is not valid for <text>.",
                     "it": "Il valore  \t  non è valido per <text>."}
            for chosen, text in texts.items():
                with self.subTest(language=chosen):
                    code, shown, error = support.run_main(
                        build_context(world), "machine", "label", " \t ", "--language",
                        chosen, "--json")
                    self.assertEqual((code, error), (2, f"error: {text}\n"))
                    self.assertEqual(json.loads(shown)["error"], {
                        "code": "wrong_value", "values": {"key": "<text>", "value": " \t "},
                        "message": text})
            self.assertEqual(store.machine_labels(world.store, [MACHINE]),
                             ({MACHINE: "Invented Machine"}, []))

    def test_config_show_layers_and_errors_exit_0(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_machine(world, recorded=str(world.store))
            world.store.mkdir(parents=True)
            (world.store / PERSON_FILE).write_text(
                "[[time_zone]]\nzone = \"Etc/UTC\"\nfrom = 1970-01-01T00:00:00Z\n"
                "\n[[day_start]]\nhour = 00:00:00\nfrom = 1970-01-01\n"
                "\n[[project]]\nid = \"example-one\"\nname = \"Same Name\"\n"
                "\n[[project]]\nid = \"example-two\"\nname = \"Same Name\"\n"
                "\n[report]\nidle_gap = \"12min\"\n", encoding="utf-8")
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["config", "show", "--json"], build_context(world))
            self.assertEqual(code, 0)  # config show computes no figures
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "config show")
            self.assertEqual(envelope["configuration_errors"], [{
                "code": "project_name_conflict",
                "values": {"first": "example-one", "second": "example-two"},
                "message": "The person configuration gives one name to two project"
                           " identifiers: example-one and example-two.",
            }])
            parameters = {one["name"]: one for one in envelope["parameters"]}
            self.assertEqual(parameters["idle_gap"],
                             {"name": "idle_gap", "value": 720, "layer": "person"})
            self.assertEqual(parameters["minimum_attention"],
                             {"name": "minimum_attention", "value": 60, "layer": "default"})
            self.assertEqual(parameters["headless_prompts"],
                             {"name": "headless_prompts", "value": False,
                              "layer": "default"})
            self.assertEqual(parameters["language"],
                             {"name": "language", "value": "en", "layer": "default"})
            self.assertEqual(parameters["settle_time"],
                             {"name": "settle_time", "value": 14400, "layer": "default"})
            self.assertEqual(parameters["preferred_remotes"],
                             {"name": "preferred_remotes", "value": ["origin"],
                              "layer": "default"})
            self.assertEqual(envelope["entries"], [
                {"entry": "time_zone", "zone": "Etc/UTC",
                 "from": "1970-01-01T00:00:00.000Z", "layer": "person"},
                {"entry": "day_start", "hour": "00:00", "from": "1970-01-01",
                 "layer": "person"},
                {"entry": "project", "id": "example-one", "name": "Same Name",
                 "layer": "person"},
                {"entry": "project", "id": "example-two", "name": "Same Name",
                 "layer": "person"},
            ])
            self.assertEqual(
                stderr.getvalue(),
                "error: The person configuration gives one name to two project identifiers:"
                " example-one and example-two.\n")
            self.assertFalse((world.machine / "stores" /
                              platform.store_identifier(world.store, SYSTEM) /
                              "index.sqlite").exists())  # no event is read
            stdout, stderr = io.StringIO(), io.StringIO()  # the text of the layers
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["config", "show"], build_context(world))
            self.assertEqual(code, 0)
            shown = stdout.getvalue()
            for line in ("Parameters",
                         "idle_gap 0:12 person",
                         "minimum_attention 0:01 default",
                         "stale_limit 4:00 default",
                         "headless_prompts false default",
                         "timesheet_granularity 0:15 default",
                         "settle_time 4:00 default",
                         "preferred_remotes [\"origin\"] default",
                         "Entries",
                         "time_zone zone=Etc/UTC from=1970-01-01T00:00:00Z person",
                         "day_start hour=00:00 from=1970-01-01 person",
                         "project id=example-one name=Same Name person",
                         "project id=example-two name=Same Name person"):
                self.assertIn(line, shown, line)

    def test_config_show_text_in_the_forms_of_the_tables(self) -> None:
        """The text of `config show` shows the durations as `H:MM` (command-line.md ›
        Output), the layer that gives each value in the language of the output, and an
        instant as setup shows the entries it creates, RFC 3339 in UTC with `Z` and the
        fraction of a second only when it is not zero; the JSON document keeps the
        seconds, the layer names, and the milliseconds (command-line.md › JSON
        documents)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_machine(world, recorded=str(world.store))
            world.store.mkdir(parents=True)
            (world.store / PERSON_FILE).write_text(
                "[[time_zone]]\nzone = \"Etc/UTC\"\nfrom = 1970-01-01T00:00:00Z\n"
                "\n[[time_zone]]\nzone = \"Asia/Tokyo\"\nfrom = 2026-12-01T00:00:00.250Z\n"
                "\n[[day_start]]\nhour = 00:00:00\nfrom = 1970-01-01\n"
                "\n[report]\nidle_gap = \"1h30min\"\n", encoding="utf-8")
            for chosen in language.LANGUAGES:
                with self.subTest(language=chosen):
                    code, shown, error = run_action(
                        world, ["config", "show", "--language", chosen])
                    self.assertEqual((code, error), (0, ""))

                    def layer(name: str) -> str:
                        return language.label(f"layer_{name}", chosen)

                    self.assertEqual(shown.splitlines(), [
                        language.label("parameters", chosen),
                        f"idle_gap 1:30 {layer('person')}",
                        f"minimum_attention 0:01 {layer('default')}",
                        f"stale_limit 4:00 {layer('default')}",
                        f"headless_prompts false {layer('default')}",
                        f"timesheet_granularity 0:15 {layer('default')}",
                        f"language {chosen} {layer('option')}",
                        f"settle_time 4:00 {layer('default')}",
                        f"preferred_remotes [\"origin\"] {layer('default')}",
                        language.label("entries", chosen),
                        f"time_zone zone=Etc/UTC from=1970-01-01T00:00:00Z {layer('person')}",
                        "time_zone zone=Asia/Tokyo from=2026-12-01T00:00:00.250Z"
                        f" {layer('person')}",
                        f"day_start hour=00:00 from=1970-01-01 {layer('person')}"])
            code, shown, error = run_action(world, ["config", "show", "--json"])
            self.assertEqual((code, error), (0, ""))
            document = json.loads(shown)
            self.assertEqual(document["parameters"][0],
                             {"name": "idle_gap", "value": 5400, "layer": "person"})
            self.assertEqual(document["entries"][1]["from"], "2026-12-01T00:00:00.250Z")
        self.assertEqual({(language.label(f"layer_{name}", "en"),
                           language.label(f"layer_{name}", "it"))
                          for name in ("person", "default", "option")},
                         {("person", "persona"), ("default", "predefinito"),
                          ("option", "opzione")})

    def test_config_show_gives_the_language_option_the_layer_option(self) -> None:
        """The option `--language` of `config show` is the first layer of the parameter
        `language` (configuration.md › Order): its value with the layer `option`; without
        the option, the layer that gives the language, the person configuration or the
        default."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            for words, value, layer in ((["--language", "it"], "it", "option"),
                                        (["--language", "en"], "en", "option"),
                                        ([], "en", "default")):
                with self.subTest(words=" ".join(words)):
                    code, shown, error = run_action(world, ["config", "show", *words])
                    self.assertEqual((code, error), (0, ""))
                    word = language.label(f"layer_{layer}", value)
                    self.assertIn(f"\nlanguage {value} {word}\n", shown)
                    code, shown, error = run_action(
                        world, ["config", "show", *words, "--json"])
                    self.assertEqual((code, error), (0, ""))
                    parameters = {one["name"]: one for one in json.loads(shown)["parameters"]}
                    self.assertEqual(parameters["language"],
                                     {"name": "language", "value": value, "layer": layer})
            write_person_language(world.store, "it")
            code, shown, error = run_action(world, ["config", "show", "--json"])
            self.assertEqual((code, error), (0, ""))
            parameters = {one["name"]: one for one in json.loads(shown)["parameters"]}
            self.assertEqual(parameters["language"],
                             {"name": "language", "value": "it", "layer": "person"})
            code, shown, error = run_action(world, ["config", "show", "--language", "en"])
            self.assertEqual((code, error), (0, ""))
            self.assertIn("\nlanguage en option\n", shown)

    def test_config_add_each_entry(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            cases = [
                (["time-zone", "--zone", "Asia/Tokyo", "--from", "2026-12-01T00:00:00Z"],
                 {"entry": "time_zone", "zone": "Asia/Tokyo",
                  "from": "2026-12-01T00:00:00.000Z"}),
                (["day-start", "--hour", "04:00", "--from", "today"],
                 {"entry": "day_start", "hour": "04:00", "from": "2026-11-24"}),
                (["project", "--id", "example-product", "--name", "Example Product"],
                 {"entry": "project", "id": "example-product", "name": "Example Product"}),
                (["work-item", "--project", "example-product", "--id", "example-task",
                  "--name", "Example Task"],
                 {"entry": "work_item", "project": "example-product", "id": "example-task",
                  "name": "Example Task"}),
                (["identity-rule", "--project", "example-product", "--repository",
                  "https://Git@Example.org:8443/Team/Example.git/"],
                 {"entry": "identity_rule", "project": "example-product",
                  "repository": "example.org/team/example"}),
                (["category-rule", "--tool", "mcp__*", "--category", "other"],
                 {"entry": "category_rule", "tool": "mcp__*", "category": "other"}),
            ]
            for words, document in cases:
                with self.subTest(entry=document["entry"]):
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with contextlib.redirect_stdout(stdout), \
                            contextlib.redirect_stderr(stderr):
                        code = main(["config", "add", *words, "--json"],
                                    build_context(world))
                    self.assertEqual(code, 0)
                    envelope = json.loads(stdout.getvalue())
                    self.assertEqual(envelope["command"], "config add")
                    for key, value in document.items():
                        self.assertEqual(envelope[key], value, key)
            person = configuration.read_person_configuration(world.store)
            self.assertEqual([entry.zone for entry in person.time_zones],
                             ["Etc/UTC", "Asia/Tokyo"])
            self.assertEqual([entry.hour for entry in person.day_starts],
                             [time(0, 0), time(4, 0)])
            self.assertEqual([entry.id for entry in person.projects], ["example-product"])
            self.assertEqual([entry.id for entry in person.work_items], ["example-task"])
            self.assertEqual(person.identity_rules[0].repository, "example.org/team/example")
            self.assertEqual([rule.category for rule in person.category_rules], ["other"])
        with support.TemporaryFolder() as base:  # the text of one entry
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["config", "add", "category-rule", "--tool", "mcp__*",
                             "--category", "other"], build_context(world))
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(),
                             "category_rule tool=mcp__* category=other\n")

    def test_config_add_wrong_value_exits_2(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            before = (world.store / PERSON_FILE).read_bytes()
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["config", "add", "category-rule", "--tool", "Edit",
                             "--category", "invented", "--json"], build_context(world))
            self.assertEqual(code, 2)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["error"], {
                "code": "wrong_value",
                "values": {"key": "--category", "value": "invented"},
                "message": "The value invented is not valid for --category.",
            })
            self.assertEqual(
                stderr.getvalue(), "error: The value invented is not valid for --category.\n")
            self.assertEqual((world.store / PERSON_FILE).read_bytes(), before)
            for words, key, value in (  # a value names the option that the person typed
                    (["identity-rule", "--project", "alpha", "--repository", "not a url"],
                     "--repository", "not a url"),
                    (["time-zone", "--zone", "Invented/Zone", "--from",
                      "2026-12-01T00:00:00Z"], "--zone", "Invented/Zone"),
                    (["project", "--id", "", "--name", "Alpha"], "--id", "")):
                with self.subTest(key=key):
                    code, shown, error = run_action(world, ["config", "add", *words, "--json"])
                    self.assertEqual(code, 2, error)
                    self.assertEqual(json.loads(shown)["error"]["values"],
                                     {"key": key, "value": value})
            self.assertEqual((world.store / PERSON_FILE).read_bytes(), before)
            stdout, stderr = io.StringIO(), io.StringIO()  # a day that no form holds
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["config", "add", "day-start", "--hour", "04:00",
                             "--from", "not-a-day", "--json"], build_context(world))
            self.assertEqual(code, 2)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["error"]["values"],
                             {"key": "--from", "value": "not-a-day"})
            stdout, stderr = io.StringIO(), io.StringIO()  # a local time is no RFC 3339
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["config", "add", "time-zone", "--zone", "Asia/Tokyo",
                             "--from", "2026-12-01T00:00", "--json"], build_context(world))
            self.assertEqual(code, 2)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["error"]["values"],
                             {"key": "--from", "value": "2026-12-01T00:00"})
            self.assertEqual(envelope["error"]["message"],
                             "The value 2026-12-01T00:00 is not valid for --from.")
            self.assertEqual((world.store / PERSON_FILE).read_bytes(), before)

    def test_index_rebuild_counts(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            write_session(world, logs)
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["ingest", "--json"], build_context(world))
            self.assertEqual(code, 0)
            segment = next((world.store / "segments").glob("*/*.jsonl"))
            with segment.open("ab") as appended:
                appended.write(b"invented line\n")  # a line that is not a valid event
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["index", "rebuild", "--json"], build_context(world))
            self.assertEqual(code, 0)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "index rebuild")
            self.assertEqual(envelope["segments"], 1)
            self.assertEqual(envelope["events"], 2)  # the event line and the broken line
        with support.TemporaryFolder() as base:  # the text of the numbers
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["index", "rebuild"], build_context(world))
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(), "Segments: 0\nEvents: 0\n")

    def test_version_shows_tzdata(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["version", "--json"], build_context(world))
            self.assertEqual(code, 0)
            envelope = json.loads(stdout.getvalue())
            self.assertEqual(envelope["command"], "version")
            self.assertEqual(envelope["ledger"], VERSION)
            self.assertEqual(envelope["tzdata"], days.tzdata_version())
            self.assertEqual(envelope["warnings"], [])
        with support.TemporaryFolder() as base:  # the text
            world = build_world(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["version"], build_context(world))
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(),
                             f"Ledger: {VERSION}\ntzdata: {days.tzdata_version()}\n")

    def test_version_works_before_setup(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            stdout, stderr = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = main(["version"], None)  # the context of the running process
            self.assertEqual(code, 0)
            self.assertEqual(stdout.getvalue(),
                             f"Ledger: {events.writer_version()}\n"
                             f"tzdata: {days.tzdata_version()}\n")
            self.assertEqual(stderr.getvalue(), "")
            self.assertFalse(world.machine.exists())  # nothing is set up


class TestEntryActions(unittest.TestCase):
    """The actions of the declared events: `annotate`, `entry add`, `entries`, and
    `retract` write one event of their kind under the lock of the machine and the store,
    and `entries` lists the events of a local day (command-line.md › Commands, › JSON
    documents)."""

    def _world_with_session(self, base: Path, desktop: bool = False) -> World:
        """A set-up world whose store holds one ingested session of Claude Code. With
        `desktop`, Claude Desktop holds the same session identifier too, through another
        file of native logs with another native identifier, below the folder that the
        machine configuration records for it."""
        world = build_world(base)
        logs = world.home / ".claude" / "projects"
        write_session(world, logs)
        if desktop:
            other = base / "desktop" / "someone" / ".claude" / "projects"
            support.write_session(other, "session-one", [
                support.prompt_record("Invented prompt text.", PROMPT_AT,
                                      "3f1c0000-0000-4000-8000-0000000000b2")],
                {}, world.home / "work")
            settle([other / "session-one.jsonl"])
            world.machine.mkdir(parents=True, exist_ok=True)
            world.store.mkdir(parents=True, exist_ok=True)
            configuration.create_person_configuration(world.store, ZONE)
            configuration.write_machine_configuration(
                world.machine, configuration.MachineConfiguration(
                    machine=MACHINE, installation=None, salt=None, store=str(world.store),
                    native_logs={"claude-code": [str(logs)],
                                 "claude-desktop": [str(base / "desktop")]}))
        else:
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
        return world

    def test_annotate_session_and_interval(self) -> None:
        with support.TemporaryFolder() as base:
            world = self._world_with_session(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            code, shown, error = run_action(world, [
                "annotate", "--session", "session-one", "--project", "example-product",
                "--note", "Invented note.", "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["command"], "annotate")
            self.assertEqual(envelope["warnings"], [])
            self.assertEqual(envelope["configuration_errors"], [])
            held = envelope["event_uid"]
            self.assertTrue(held)
            written = [one for one in stored_events(world) if one["source"] == "ledger"]
            self.assertEqual([one["kind"] for one in written], ["annotation"])
            annotation = written[0]
            self.assertEqual(annotation["event_uid"], held)
            self.assertEqual(annotation["annotates"],
                             {"tool": "claude-code", "session_id": "session-one"})
            self.assertEqual(annotation["project"], "example-product")
            self.assertEqual(annotation["note"], "Invented note.")
            self.assertEqual(annotation["actor"], "human")
            self.assertEqual(annotation["machine"], MACHINE)
            self.assertEqual(annotation["timestamp"], "2026-11-24T12:00:00.000Z")
            self.assertEqual(annotation["writer_version"], VERSION)
            self.assertNotIn("start", annotation)
            code, shown, error = run_action(world, [  # the text of the event identifier
                "annotate", "--session", "session-one", "--project", "example-product"],
                context)
            self.assertEqual(code, 0, error)
            self.assertTrue(shown.startswith("Event identifier: "))
            code, shown, error = run_action(world, [
                "annotate", "--from", "2026-11-20T10:00", "--to", "2026-11-20T11:00",
                "--project", "p-interval", "--work-item", "w-interval", "--json"], context)
            self.assertEqual(code, 0, error)
            interval = [one for one in stored_events(world)
                        if one["source"] == "ledger" and "start" in one][0]
            self.assertEqual(interval["start"], "2026-11-20T10:00:00.000Z")
            self.assertEqual(interval["end"], "2026-11-20T11:00:00.000Z")
            self.assertNotIn("annotates", interval)
            self.assertEqual(interval["project"], "p-interval")
            self.assertEqual(interval["work_item"], "w-interval")

    def test_annotate_unknown_session_exits_1(self) -> None:
        with support.TemporaryFolder() as base:
            world = self._world_with_session(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            code, shown, error = run_action(world, [
                "annotate", "--session", "no-such-session", "--project", "p", "--json"],
                context)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(shown)["error"], {
                "code": "target_not_found", "values": {"target": "no-such-session"},
                "message": "The store does not hold the target no-such-session.",
            })
            self.assertEqual(
                error, "error: The store does not hold the target no-such-session.\n")
            written = [one for one in stored_events(world) if one["source"] == "ledger"]
            self.assertEqual(written, [])  # nothing is written

    def test_annotate_ambiguous_session_needs_tool(self) -> None:
        with support.TemporaryFolder() as base:
            world = self._world_with_session(base, desktop=True)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            code, shown, error = run_action(world, [
                "annotate", "--session", "session-one", "--project", "p", "--json"],
                context)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(shown)["error"], {
                "code": "ambiguous_session",
                "values": {"session_id": "session-one",
                           "tools": ["claude-code", "claude-desktop"]},
                "message": "The session session-one is held by more than one agent tool:"
                           " name one of claude-code, claude-desktop with --tool.",
            })
            written = [one for one in stored_events(world) if one["source"] == "ledger"]
            self.assertEqual(written, [])  # nothing is written
            code, shown, error = run_action(world, [
                "annotate", "--session", "session-one", "--tool", "claude-code",
                "--project", "p", "--json"], context)
            self.assertEqual(code, 0, error)
            [annotation] = [one for one in stored_events(world)
                            if one["source"] == "ledger"]
            self.assertEqual(annotation["annotates"],
                             {"tool": "claude-code", "session_id": "session-one"})
            code, shown, error = run_action(world, [
                "annotate", "--session", "session-one", "--tool", "no-such-tool",
                "--project", "p", "--json"], context)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(shown)["error"]["values"],
                             {"target": "no-such-tool session-one"})

    def test_project_given_as_name(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            context = build_context(world)
            run_action(world, ["config", "add", "project", "--id", "example-product",
                                "--name", "Example Product"], context)
            run_action(world, ["config", "add", "work-item", "--project",
                                "example-product", "--id", "example-task", "--name",
                                "Example Task"], context)
            code, shown, error = run_action(world, [
                "entry", "add", "--from", "2026-11-24T08:00", "--to", "2026-11-24T09:00",
                "--mode", "overlapping", "--project", "Example Product", "--work-item",
                "Example Task", "--json"], context)
            self.assertEqual(code, 0, error)
            [held] = [one for one in stored_events(world)
                      if one["kind"] == "manual_entry"]
            self.assertEqual(held["project"], "example-product")
            self.assertEqual(held["work_item"], "example-task")

    def test_entry_add_unattributed(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            context = build_context(world)
            words = ["entry", "add", "--from", "2026-11-24T08:00", "--to",
                     "2026-11-24T09:00"]
            code, shown, error = run_action(
                world, [*words, "--mode", "additional", "--json"], context)
            self.assertEqual(code, 0, error)
            [held] = [one for one in stored_events(world)
                      if one["kind"] == "manual_entry"]
            self.assertNotIn("project", held)  # the unattributed time holds no project
            self.assertNotIn("work_item", held)
            self.assertEqual(held["manual_mode"], "additional")
            self.assertEqual(held["start"], "2026-11-24T08:00:00.000Z")
            self.assertEqual(held["end"], "2026-11-24T09:00:00.000Z")
            code, shown, error = run_action(  # `--project -` is the unattributed time
                world, [*words, "--mode", "overlapping", "--project", "-", "--json"],
                context)
            self.assertEqual(code, 0, error)
            both = [one for one in stored_events(world) if one["kind"] == "manual_entry"]
            self.assertEqual(len(both), 2)
            self.assertNotIn("project", both[1])
            self.assertEqual(both[1]["manual_mode"], "overlapping")
            code, shown, error = run_action(world, [*words, "--mode", "additional"],
                                             context)
            self.assertEqual(code, 0, error)
            self.assertTrue(shown.startswith("Event identifier: "))

    def test_entries_lists_by_local_day(self) -> None:
        with support.TemporaryFolder() as base:
            world = self._world_with_session(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            _, shown, _ = run_action(world, [
                "annotate", "--from", "2026-11-20T10:00", "--to", "2026-11-20T11:00",
                "--project", "p", "--json"], context)
            annotated = json.loads(shown)["event_uid"]
            _, shown, _ = run_action(world, [
                "entry", "add", "--from", "2026-11-24T08:00", "--to", "2026-11-24T09:00",
                "--mode", "additional", "--json"], context)
            entered = json.loads(shown)["event_uid"]
            _, shown, _ = run_action(world, ["retract", annotated, "--json"], context)
            retracted = json.loads(shown)["event_uid"]
            machine = configuration.read_machine_configuration(world.machine).machine
            confirmation = events.ledger_event(
                "timesheet_confirmation", "human", machine, NOW,
                {"day": "2026-11-24", "entries": []})
            store.append_events(world.store, machine, [confirmation], NOW)
            purge = events.ledger_event(
                "purge", "human", machine, NOW,
                {"purged_keys": [{"source": "ledger", "event_uid": "3f1c0000-0000-4000"
                                                 "-8000-0000000000c3"}],
                 "purge_reason": "forget"})
            store.append_events(world.store, machine, [purge], NOW)
            code, shown, error = run_action(world, ["entries", "2026-11-24", "--json"],
                                             context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["day"], "2026-11-24")
            kinds = [entry["kind"] for entry in envelope["entries"]]
            self.assertEqual(sorted(kinds),
                             ["annotation", "manual_entry", "retraction",
                              "timesheet_confirmation"])
            self.assertNotIn("purge", kinds)  # a purge is not listed
            held = {entry["kind"]: entry["event_uid"] for entry in envelope["entries"]}
            self.assertEqual(held["annotation"], annotated)
            self.assertEqual(held["manual_entry"], entered)
            self.assertEqual(held["retraction"], retracted)
            self.assertEqual(held["timesheet_confirmation"], confirmation["event_uid"])
            for entry in envelope["entries"]:
                self.assertEqual(list(entry)[:3], ["event_uid", "kind", "timestamp"])
            code, shown, error = run_action(world, ["entries", "2026-11-23", "--json"],
                                             context)
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(shown)["entries"], [])
            code, shown, error = run_action(world, ["entries", "today", "--json"],
                                             context)
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(shown)["day"], "2026-11-24")
            code, shown, error = run_action(world, ["entries", "2026-11-24"], context)
            self.assertEqual(code, 0, error)
            self.assertIn("2026-11-24  Events", shown)
            for held_uid in (annotated, entered, retracted):
                self.assertIn(held_uid, shown)

    def test_retract_and_retract_retraction(self) -> None:
        with support.TemporaryFolder() as base:
            world = self._world_with_session(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            _, shown, _ = run_action(world, [
                "annotate", "--session", "session-one", "--project", "p", "--json"],
                context)
            annotated = json.loads(shown)["event_uid"]
            code, shown, error = run_action(world, ["retract", annotated, "--json"],
                                             context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["command"], "retract")
            retraction = envelope["event_uid"]
            [held] = [one for one in stored_events(world) if one["kind"] == "retraction"]
            self.assertEqual(held["event_uid"], retraction)
            self.assertEqual(held["retracts"],
                             {"source": "ledger", "event_uid": annotated})
            self.assertEqual(held["actor"], "human")
            code, shown, error = run_action(world,  # a retraction brings the event back
                                             ["retract", retraction, "--json"], context)
            self.assertEqual(code, 0, error)
            undo = json.loads(shown)["event_uid"]
            [last] = [one for one in stored_events(world)
                      if one["kind"] == "retraction" and one["event_uid"] == undo]
            self.assertEqual(last["retracts"],
                             {"source": "ledger", "event_uid": retraction})
            code, shown, error = run_action(world, ["retract", annotated], context)
            self.assertEqual(code, 0, error)
            self.assertTrue(shown.startswith("Event identifier: "))

    def test_retract_unknown_event_uid_exits_1(self) -> None:
        with support.TemporaryFolder() as base:
            world = self._world_with_session(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            code, shown, error = run_action(world, ["retract", "no-such-uid", "--json"],
                                             context)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(shown)["error"], {
                "code": "target_not_found", "values": {"target": "no-such-uid"},
                "message": "The store does not hold the target no-such-uid.",
            })
            self.assertEqual(error, "error: The store does not hold the target"
                                    " no-such-uid.\n")
            written = [one for one in stored_events(world) if one["source"] == "ledger"]
            self.assertEqual(written, [])  # nothing is written

    def test_retract_of_a_purge_exits_2(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            machine = configuration.read_machine_configuration(world.machine).machine
            purge = events.ledger_event(
                "purge", "human", machine, NOW,
                {"purged_keys": [{"source": "ledger", "event_uid":
                                  "3f1c0000-0000-4000-8000-0000000000c3"}],
                 "purge_reason": "forget"})
            store.append_events(world.store, machine, [purge], NOW)
            code, shown, error = run_action(
                world, ["retract", purge["event_uid"], "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(shown)["error"], {
                "code": "wrong_kind",
                "values": {"command": "retract", "event_uid": purge["event_uid"],
                           "kind": "purge"},
                "message": f"The command retract cannot act on the event"
                           f" {purge['event_uid']}: its kind is purge.",
            })
            self.assertEqual([one["kind"] for one in stored_events(world)],
                             ["purge"])  # nothing is written

    def test_annotate_without_project_or_work_item_exits_2(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            words = ["annotate", "--from", "2026-11-24T08:00", "--to", "2026-11-24T09:00"]
            code, shown, error = run_action(world, [*words, "--json"])
            self.assertEqual(code, 2)
            wanted = {
                "code": "missing_argument",
                "values": {"command": "annotate", "arguments": ["--project | --work-item"]},
                "message": "The command annotate needs --project | --work-item.",
            }
            self.assertEqual(json.loads(shown)["error"], wanted)
            self.assertEqual(stored_events(world), [])  # nothing is written
            # `-` gives no project; the project comes before the shape of the annotation,
            # and before the store is read.
            for given in ([*words, "--project", "-"], ["annotate", "--session", "session-one"],
                          ["annotate", "--session", "session-one", "--to", TO],
                          ["annotate", "--from", FROM]):
                with self.subTest(words=given):
                    code, shown, error = run_action(world, [*given, "--json"])
                    self.assertEqual((code, json.loads(shown)["error"]), (2, wanted))

    def test_annotate_inverted_interval_exits_2(self) -> None:
        """An interval of `annotate` whose start does not come before its end holds no
        time: the command stops with a wrong value that names `--to` and the value, and
        writes nothing, instead of writing an interval that the metrics would silently
        drop (command-line.md › Commands)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_session(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            for start, end in (("2026-11-24T09:00", "2026-11-24T08:00"),
                               ("2026-11-24T08:00", "2026-11-24T08:00")):
                code, shown, error = run_action(world, [
                    "annotate", "--from", start, "--to", end, "--project", "p", "--json"],
                    context)
                self.assertEqual(code, 2, error)
                self.assertEqual(json.loads(shown)["error"], {
                    "code": "wrong_value", "values": {"key": "--to", "value": end},
                    "message": f"The value {end} is not valid for --to.",
                })
                self.assertEqual(error, f"error: The value {end} is not valid for --to.\n")
            self.assertEqual([one for one in stored_events(world)
                              if one["source"] == "ledger"], [])  # nothing is written
            code, shown, error = run_action(world, [  # a session takes no interval check
                "annotate", "--session", "session-one", "--project", "p", "--json"],
                context)
            self.assertEqual(code, 0, error)

    def test_entry_add_inverted_interval_exits_2(self) -> None:
        """An interval of `entry add` whose start does not come before its end holds no
        time: the command stops with a wrong value that names `--to` and the value, and
        writes nothing (command-line.md › Commands)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            for start, end in (("2026-11-24T09:00", "2026-11-24T08:00"),
                               ("2026-11-24T08:00", "2026-11-24T08:00")):
                code, shown, error = run_action(world, [
                    "entry", "add", "--from", start, "--to", end, "--mode", "additional",
                    "--json"], build_context(world))
                self.assertEqual(code, 2, error)
                self.assertEqual(json.loads(shown)["error"], {
                    "code": "wrong_value", "values": {"key": "--to", "value": end},
                    "message": f"The value {end} is not valid for --to.",
                })
            self.assertEqual(stored_events(world), [])  # nothing is written

    def test_entry_actions_take_the_lock(self) -> None:
        """`annotate`, `entry add`, and `retract` take the lock of the machine and the
        store, and refuse a development version that the environment does not let write,
        before the lock (architecture.md › Concurrency, › Runtime)."""
        original = platform.StoreLock.__enter__

        def recording(taker: platform.StoreLock, takes: list[str]) -> platform.StoreLock:
            takes.append(str(taker.path))
            return original(taker)

        annotate_words = ["annotate", "--from", "2026-11-24T08:00", "--to",
                          "2026-11-24T09:00", "--project", "p"]
        entry_words = ["entry", "add", "--from", "2026-11-24T08:00", "--to",
                       "2026-11-24T09:00", "--mode", "additional"]
        retract_words = ["retract", "invented"]
        for name, words, prepared in (
                ("annotate", annotate_words, None),
                ("entry add", entry_words, None),
                ("retract", retract_words, annotate_words)):
            with self.subTest(action=name):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    context = build_context(world)
                    if prepared is not None:  # the target that the retraction names
                        code, shown, error = run_action(world, [*prepared, "--json"],
                                                         context)
                        self.assertEqual(code, 0, error)
                        words = [*words[:1], json.loads(shown)["event_uid"]]
                    lock = (world.machine / "stores" /
                            platform.store_identifier(world.store, SYSTEM) / "lock")
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main([*words, "--store", str(world.store), "--json"],
                                        context)
                    self.assertEqual(code, 0, stderr.getvalue())
                    self.assertTrue(takes, name)  # the lock was taken
                    self.assertEqual(takes[0], str(lock))
            with self.subTest(action=f"{name} refused"):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    if prepared is not None:  # the target, written by a release version
                        run_action(world, [*prepared, "--json"], build_context(world))
                    environ = {key: value for key, value in world.environ.items()
                               if key != DEVELOPMENT_VARIABLE}
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main([*words, "--store", str(world.store), "--json"],
                                        build_context(world, version=DEV_VERSION,
                                                      environ=environ))
                    self.assertEqual(code, 1)
                    envelope = json.loads(stdout.getvalue())
                    self.assertEqual(envelope["error"]["code"], "development_version")
                    self.assertEqual(takes, [])  # nothing is locked before the guard


def run_action(world: World, words: Sequence[str],
                context: Context | None = None) -> tuple[int, str, str]:
    """One command through `main` with the context of the world, or the context given
    when one is, so that a test runs its commands through one context: its exit code,
    its standard output, and its standard error."""
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        code = main(list(words), context if context is not None else build_context(world))
    return code, stdout.getvalue(), stderr.getvalue()


class _Recorded(io.TextIOBase):
    """A stream that records each write into one list shared with another stream, under
    the name of the stream, so that a test reads the order of the writes of two streams."""

    def __init__(self, name: str, writes: list[tuple[str, str]]) -> None:
        super().__init__()
        self._name = name
        self._writes = writes

    def write(self, text: str) -> int:
        """Record one write under the name of the stream."""
        self._writes.append((self._name, text))
        return len(text)


def run_in_order(words: Sequence[str], context: Context) -> tuple[int, list[tuple[str, str]]]:
    """One command through `main` with the context given: its exit code, and the writes of
    its standard output and of its standard error in the order the command made them, each
    as the name of its stream, `stdout` or `stderr`, and its text."""
    writes: list[tuple[str, str]] = []
    with contextlib.redirect_stdout(_Recorded("stdout", writes)), \
            contextlib.redirect_stderr(_Recorded("stderr", writes)):
        code = main(list(words), context)
    return code, writes


def stored_events(world: World) -> list[events.Event]:
    """Every event that the segments of the store of the world hold, in the order of the
    segments and of their lines."""
    found = []
    for name in store.segment_names(world.store):
        for line in store.read_lines(world.store, name):
            decoded = events.decode_line(line.data)
            if decoded.event is not None:
                found.append(decoded.event)
    return found


def machine_segment(world: World, machine: str) -> list[events.Event]:
    """The events of the segment of the machine for the month of the instant of the tests,
    wherever the store holds it."""
    found = []
    for name in store.segment_names(world.store):
        if f"/{machine}/" not in name:
            continue
        for line in store.read_lines(world.store, name):
            decoded = events.decode_line(line.data)
            if decoded.event is not None:
                found.append(decoded.event)
    return found


class TracedStream:
    """A stream of the test that records each write, with the name of the stream it
    stands for, in one log that the test reads: the order of the lines that a command
    writes to the standard output and to the standard error."""

    def __init__(self, log: list[tuple[str, str]], stream: str) -> None:
        self._log = log
        self._stream = stream

    def write(self, text: str) -> int:
        self._log.append((self._stream, text))
        return len(text)

    def flush(self) -> None:
        """The stream holds no buffer, so there is nothing to flush."""


def traced(context: Context, words: Sequence[str]) -> tuple[int, list[tuple[str, str]]]:
    """One command through `main` with both streams replaced by streams that record
    every write in one log: the exit code and the log, each write with `stdout` or
    `stderr`."""
    log: list[tuple[str, str]] = []
    with contextlib.redirect_stdout(TracedStream(log, "stdout")), \
            contextlib.redirect_stderr(TracedStream(log, "stderr")):
        code = main(list(words), context)
    return code, log


class TestStoreActionsLocks(unittest.TestCase):
    """The actions that write take the lock of the machine and the store, and refuse a
    development version that the environment does not let write, before the lock
    (architecture.md › Concurrency, › Runtime)."""

    WORDS = (
        ("setup", ("setup",)),
        ("ingest", ("ingest",)),
        ("machine label", ("machine", "label", "Invented Machine")),
        ("config add", ("config", "add", "time-zone", "--zone", "Asia/Tokyo",
                        "--from", "2026-12-01T00:00:00Z")),
    )
    """The words of each action that writes, with the store folder of its world added."""

    def test_store_actions_take_the_lock(self) -> None:
        original = platform.StoreLock.__enter__

        def recording(taker: platform.StoreLock, takes: list[str]) -> platform.StoreLock:
            takes.append(str(taker.path))
            return original(taker)

        for name, words in self.WORDS:
            with self.subTest(action=name):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    lock = (world.machine / "stores" /
                            platform.store_identifier(world.store, SYSTEM) / "lock")
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main([*words, "--store", str(world.store), "--json"],
                                        build_context(world, run=FakeRun()))
                    self.assertEqual(code, 0, stderr.getvalue())
                    self.assertTrue(takes, name)  # the lock was taken
                    self.assertEqual(takes[0], str(lock))
            with self.subTest(action=f"{name} refused"):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    environ = {key: value for key, value in world.environ.items()
                               if key != DEVELOPMENT_VARIABLE}
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main([*words, "--store", str(world.store), "--json"],
                                        build_context(world, version=DEV_VERSION,
                                                      environ=environ, run=FakeRun()))
                    self.assertEqual(code, 1)
                    envelope = json.loads(stdout.getvalue())
                    self.assertEqual(envelope["error"]["code"], "development_version")
                    self.assertEqual(takes, [])  # nothing is locked before the guard


class TestFiguresOfDays(unittest.TestCase):
    """`figures_of_days` is the one pipeline that `timesheet confirm` and every report
    command share: each of its stages runs once for the period, and `day_figures` runs
    once for each of its days (architecture.md › Modules)."""

    def test_figures_of_days_runs_each_stage_once(self) -> None:
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            write_session(world, logs)
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            run_action(world, ["ingest", "--json"], build_context(world))
            context = build_context(world)
            _, person, store = context.require_setup(None)
            parameters, _ = configuration.resolve_parameters({}, person)
            watchers = {}
            for name in ("select", "compute_metrics", "attribute", "day_figures"):
                watcher = mock.Mock(wraps=getattr(figures, name))
                watchers[name] = watcher
                patcher = mock.patch.object(figures, name, watcher)
                patcher.start()
                self.addCleanup(patcher.stop)
            first, last = date(2026, 11, 23), date(2026, 11, 24)
            held = figures.figures_of_days(context, store, person, parameters, first, last)
            self.assertEqual(watchers["select"].call_count, 1)
            self.assertEqual(watchers["compute_metrics"].call_count, 1)
            self.assertEqual(watchers["attribute"].call_count, 1)
            self.assertEqual(watchers["day_figures"].call_count, 2)  # once for each day
            self.assertIs(watchers["day_figures"].call_args_list[0][0][1],
                          watchers["day_figures"].call_args_list[1][0][1])
            self.assertIs(watchers["attribute"].call_args[0][6],
                          held.selection.confirmations)  # with the confirmations
            self.assertEqual(held.selection.first, first)
            self.assertEqual(held.selection.last, last)
            self.assertEqual([one.timesheet.day for one in held.days], [first, last])
            self.assertIs(held.attribution, watchers["day_figures"].call_args_list[1][0][1])

    def test_report_warnings_in_the_order_of_the_report(self) -> None:
        """`report_warnings` gives the warnings of a report in the order that every report
        writes them (command-line.md › Reports): the ones of the selection, then the ones
        of the attribution, then the timesheet warnings of each day of the period in the
        order of the days; a caller that computed the figures of the days again, as
        `timesheet confirm` does after its confirmation, gives those days."""

        def one_warning_each() -> Figures:
            """Figures whose three sources of warnings and two days each hold one."""
            selection = mock.Mock()
            selection.warnings = [{"code": "broken_line", "values": {}}]
            attribution = mock.Mock()
            attribution.warnings = [{"code": "unknown_tool_name", "values": {}}]
            return Figures(
                selection, attribution,
                [mock.Mock(timesheet=mock.Mock(warnings=[{"code": "held_back_events",
                                                          "values": {}}])),
                 mock.Mock(timesheet=mock.Mock(warnings=[{"code": "manual_entry_overlap",
                                                          "values": {}}]))])

        self.assertEqual([warning["code"]
                          for warning in report_warnings(one_warning_each())],
                         ["broken_line", "unknown_tool_name", "held_back_events",
                          "manual_entry_overlap"])
        after = [mock.Mock(timesheet=mock.Mock(warnings=[{"code": "declared_value_below_measured",
                                                          "values": {}}]))]
        self.assertEqual([warning["code"]
                          for warning in report_warnings(one_warning_each(), after)],
                         ["broken_line", "unknown_tool_name",
                          "declared_value_below_measured"])


class TestTimesheetActions(unittest.TestCase):
    """The actions of the two `timesheet` commands: `timesheet confirm` writes one
    timesheet confirmation of a day through the figures of `figures_of_days`, and
    `timesheet retract` retracts the latest confirmation of the day, both under the lock
    of the machine and the store (command-line.md › Timesheet, › Commands, metrics.md ›
    Declared values)."""

    def _world_with_prompt(self, base: Path, settled: bool = True) -> World:
        """A set-up world whose store holds one ingested session with a prompt of the
        person at nine in the morning of the day of the tests, answered by a response of
        the model. With `settled`, the file of native logs has a time of change two
        settle times old, so the ingestion reads the response as complete; without it,
        the response has no later record, and the machine holds the session back."""
        world = build_world(base)
        logs = world.home / ".claude" / "projects"
        support.write_session(logs, "session-one", [
            support.prompt_record("Invented prompt text.", "2026-11-24T09:00:00.000Z",
                                  UUID_ONE),
            support.output_record("Invented response text.", "2026-11-24T09:01:00.000Z",
                                  "3f1c0000-0000-4000-8000-0000000000b1", "msg-invented-1")],
            {}, world.home / "work")
        path = logs / "session-one.jsonl"
        if settled:
            settle([path])
        set_up(world, world.store, recorded=str(world.store), logs=[logs])
        return world

    def test_timesheet_confirm_without_options(self) -> None:
        """`timesheet confirm` without options confirms the proposal that the day shows:
        the measured human time with manual entries of each bucket, rounded up to the
        timesheet granularity (command-line.md › Timesheet, metrics.md › Declared
        values)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            code, shown, error = run_action(world, ["timesheet", "confirm", "2026-11-24",
                                                    "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["command"], "timesheet confirm")
            self.assertEqual(envelope["warnings"], [])
            self.assertEqual(envelope["configuration_errors"], [])
            [confirmation] = [one for one in stored_events(world)
                              if one["source"] == "ledger"]
            self.assertEqual(confirmation["kind"], "timesheet_confirmation")
            self.assertEqual(confirmation["day"], "2026-11-24")
            self.assertEqual(confirmation["entries"], [{"duration": 900}])
            self.assertNotIn("replaces", confirmation)
            self.assertNotIn("note", confirmation["entries"][0])
            self.assertEqual(confirmation["actor"], "human")
            self.assertEqual(confirmation["machine"], MACHINE)
            self.assertEqual(confirmation["timestamp"], "2026-11-24T12:00:00.000Z")
            self.assertEqual(confirmation["writer_version"], VERSION)
            self.assertEqual(envelope["event_uid"], confirmation["event_uid"])
            self.assertEqual(envelope["entries"], [{
                "project": None, "work_item": None, "measured": 60,
                "with_manual_entries": 60, "declared": 900, "inferred_human_share": 0.0,
                "inferred_agent_share": 0.0, "proposed": 900}])
            self.assertEqual(envelope["entries"], self._timesheet_entries(world, context))
        with support.TemporaryFolder() as base:  # the text of the confirmation
            world = self._world_with_prompt(base)
            context = build_context(world)
            run_action(world, ["ingest"], context)
            code, shown, error = run_action(world, ["timesheet", "confirm", "2026-11-24"],
                                            context)
            self.assertEqual(code, 0, error)
            [confirmation] = [one for one in stored_events(world)
                              if one["source"] == "ledger"]
            self.assertEqual(shown, "\n".join([
                f"Event identifier: {confirmation['event_uid']}",
                "",
                "Project       Work item  Measured  With manual entries  Declared"
                "  Inferred human share  Inferred agent share  Proposed",
                "Unattributed" + " " * 17 + "0:01" + " " * 17 + "0:01      0:15"
                + " " * 18 + "0.00" + " " * 18 + "0.00      0:15",
                ""]))

    def test_timesheet_confirm_set_and_total(self) -> None:
        """`--set` gives the value of one entry, also of one that the proposal does not
        hold; `--total` gives the total human time of the day, and the rest of the total
        divides among the entries that `--set` does not give, by the shares of the
        measured human time with manual entries (command-line.md › Timesheet, metrics.md
        › Declared values)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            code, shown, error = run_action(world, [
                "entry", "add", "--from", "2026-11-24T08:00", "--to", "2026-11-24T09:00",
                "--mode", "overlapping", "--project", "example-product", "--json"], context)
            self.assertEqual(code, 0, error)
            code, shown, error = run_action(world, [
                "timesheet", "confirm", "2026-11-24", "--set", "example-product=30min",
                "--total", "2h", "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            [confirmation] = [one for one in stored_events(world)
                              if one["kind"] == "timesheet_confirmation"]
            self.assertEqual(confirmation["entries"], [
                {"project": "example-product", "duration": 1800},
                {"duration": 5400},
            ])
            self.assertEqual([one["project"] for one in envelope["entries"]],
                             [{"id": "example-product", "name": "example-product"}, None])
            self.assertEqual([one["declared"] for one in envelope["entries"]], [1800, 5400])
            self.assertEqual([one["proposed"] for one in envelope["entries"]], [1800, 5400])
            self.assertEqual([one["measured"] for one in envelope["entries"]], [0, 60])
            self.assertEqual([one["with_manual_entries"] for one in envelope["entries"]],
                             [3600, 0])
            self.assertEqual(envelope["entries"], self._timesheet_entries(world, context))
            code, shown, error = run_action(world, [  # a project that no event names yet
                "timesheet", "confirm", "2026-11-24", "--set", "brand-new-product=1h",
                "--json"], context)
            self.assertEqual(code, 0, error)
            [confirmation] = [one for one in stored_events(world)
                              if one["kind"] == "timesheet_confirmation" and
                              one["writer_version"] == VERSION and
                              len(one["entries"]) == 3]
            self.assertEqual(confirmation["entries"], [
                {"project": "brand-new-product", "duration": 3600},
                {"project": "example-product", "duration": 1800},
                {"duration": 5400},
            ])
            envelope = json.loads(shown)
            # the entries of the day as `timesheet <day>` shows them: in the order of the
            # measured human time with manual entries, the unattributed time last
            self.assertEqual([one["project"] for one in envelope["entries"]],
                             [{"id": "example-product", "name": "example-product"},
                              {"id": "brand-new-product", "name": "brand-new-product"}, None])
            self.assertEqual([one["declared"] for one in envelope["entries"]],
                             [1800, 3600, 5400])
            self.assertEqual(envelope["entries"], self._timesheet_entries(world, context))

    def _timesheet_entries(self, world: World, context: Context) -> list[dict]:
        """The `entries` of the document of `timesheet 2026-11-24` on the world."""
        code, shown, error = run_action(world, ["timesheet", "2026-11-24", "--json"], context)
        self.assertEqual(code, 0, error)
        return json.loads(shown)["entries"]

    def test_confirm_names_latest_in_replaces(self) -> None:
        """A new confirmation of the same day names, in `replaces`, the latest
        confirmation of the day that the machine has, also when a retraction cancelled
        it, so that the chain of `replaces` of the day stays whole (command-line.md ›
        Timesheet, metrics.md › Declared values)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            _, shown, _ = run_action(world, ["timesheet", "confirm", "2026-11-24", "--json"],
                                     context)
            first = json.loads(shown)["event_uid"]
            code, shown, error = run_action(world, ["timesheet", "confirm", "2026-11-24",
                                                    "--json"], context)
            self.assertEqual(code, 0, error)
            second = json.loads(shown)["event_uid"]
            written = [one for one in stored_events(world)
                       if one["kind"] == "timesheet_confirmation"]
            self.assertEqual([one["event_uid"] for one in written], [first, second])
            self.assertNotIn("replaces", written[0])
            self.assertEqual(written[1]["replaces"], {"source": "ledger",
                                                      "event_uid": first})
            code, shown, error = run_action(world, ["timesheet", "retract", "2026-11-24",
                                                    "--json"], context)
            self.assertEqual(code, 0, error)
            code, shown, error = run_action(world, ["timesheet", "confirm", "2026-11-24",
                                                    "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["warnings"], [])  # the chain of the day is whole
            third = envelope["event_uid"]
            [confirmation] = [one for one in stored_events(world)
                              if one["event_uid"] == third]
            self.assertEqual(confirmation["replaces"], {"source": "ledger",
                                                        "event_uid": second})

    def test_timesheet_confirm_future_day_exits_1(self) -> None:
        """A day after the day of the run stops `timesheet confirm` with `day_after_today`
        and writes nothing (command-line.md › Timesheet)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base)
            before = stored_events(world)
            code, shown, error = run_action(world, ["timesheet", "confirm", "2026-11-25",
                                                    "--json"], build_context(world))
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(shown)["error"], {
                "code": "day_after_today", "values": {"day": "2026-11-25"},
                "message": "The day 2026-11-25 is after today.",
            })
            self.assertEqual(error, "error: The day 2026-11-25 is after today.\n")
            self.assertEqual(stored_events(world), before)  # nothing is written
            code, shown, error = run_action(world, ["timesheet", "confirm", "2026-11-25",
                                                    "--language", "it"],
                                            build_context(world))
            self.assertEqual(code, 1)
            self.assertEqual(error, "error: Il giorno 2026-11-25 è dopo oggi.\n")

    def test_confirm_warns_held_back_and_exits_0(self) -> None:
        """The command warns when the machine holds back events of the day that are not
        complete yet, and keeps the exit code 0, because its entries are the declaration
        of the person (command-line.md › Exit codes, › Timesheet)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base, settled=False)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            code, shown, error = run_action(world, ["timesheet", "confirm", "2026-11-24",
                                                    "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual([warning["code"] for warning in envelope["warnings"]],
                             ["held_back_events"])
            self.assertEqual(envelope["warnings"][0]["values"],
                             {"session_id": "session-one"})
            self.assertTrue(error.startswith("warning: The session session-one is not"
                                             " complete yet"), error)
            [confirmation] = [one for one in stored_events(world)
                              if one["kind"] == "timesheet_confirmation"]
            self.assertEqual(confirmation["entries"], [{"duration": 900}])

    def test_confirm_writes_its_warning_lines_before_its_text(self) -> None:
        """The warning lines of `timesheet confirm` reach the standard error before its
        text reaches the standard output, as those of `timesheet <day>`, whose entries it
        shows, do: on a day whose manual entry of a project that nothing resolves overlaps
        the measured human time, the lines of the two warnings come first in both modes,
        and each line reaches its stream once (command-line.md › Reports, › Output)."""
        for as_json in ((), ("--json",)):
            with self.subTest(json=bool(as_json)), support.TemporaryFolder() as base:
                world = self._world_with_prompt(base)
                context = build_context(world)
                run_action(world, ["ingest"], context)
                _, shown, _ = run_action(world, [
                    "entry", "add", "--from", "2026-11-24T08:00", "--to", "2026-11-24T09:00",
                    "--mode", "overlapping", "--project", "example-product", "--json"],
                    context)
                entered = json.loads(shown)["event_uid"]
                code, writes = run_in_order(
                    ["timesheet", "confirm", "2026-11-24", *as_json], context)
                self.assertEqual(code, 0, writes)
                lines = "".join(f"warning: {language.message(code, values, 'en')}\n"
                                for code, values in (
                                    ("declared_project_unknown",
                                     {"project": "example-product"}),
                                    ("manual_entry_overlap", {"event_uid": entered})))
                first = [stream for stream, _ in writes].index("stdout")
                self.assertEqual("".join(text for _, text in writes[:first]), lines)
                self.assertNotIn("stderr", [stream for stream, _ in writes[first:]])
                standard = "".join(text for _, text in writes[first:])
                if as_json:
                    self.assertEqual([warning["code"] for warning
                                      in json.loads(standard)["warnings"]],
                                     ["declared_project_unknown", "manual_entry_overlap"])
                else:
                    self.assertTrue(standard.startswith("Event identifier: "), standard)

    def test_confirm_warns_when_replaced_is_later(self) -> None:
        """The command warns when the confirmation that it replaces has a later
        `timestamp` than the instant of the machine, because the clocks of two machines
        differ and the latest confirmation is the one with the latest `timestamp`
        (command-line.md › Timesheet)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            _, shown, _ = run_action(world, ["timesheet", "confirm", "2026-11-24", "--json"],
                                     context)
            first = json.loads(shown)["event_uid"]
            machine = configuration.read_machine_configuration(world.machine).machine
            later = events.ledger_event(
                "timesheet_confirmation", "human", machine, NOW + timedelta(hours=1),
                {"day": "2026-11-24", "entries": [{"duration": 3600}],
                 "replaces": {"source": "ledger", "event_uid": first}})
            store.append_events(world.store, machine, [later], NOW + timedelta(hours=1))
            code, shown, error = run_action(world, ["timesheet", "confirm", "2026-11-24",
                                                    "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            new = envelope["event_uid"]
            warnings = {(warning["code"], warning["values"]["event_uid"])
                        for warning in envelope["warnings"]}
            self.assertIn(("confirmation_before_replaced", new), warnings)
            self.assertIn(("confirmation_not_seen", new), warnings)
            self.assertIn(f"warning: The timesheet confirmation {new} has a timestamp"
                          " earlier than the confirmation that it replaces.", error)
            [confirmation] = [one for one in stored_events(world)
                              if one["event_uid"] == new]
            self.assertEqual(confirmation["replaces"], {"source": "ledger",
                                                        "event_uid": later["event_uid"]})
            self.assertEqual(confirmation["entries"], [{"duration": 3600}])

    def test_confirm_malformed_set_exits_2(self) -> None:
        """The parser holds the values of `--set` as text, so the action checks their
        shape: a value without a duration, with a duration of no format, or a work item
        without a project stops with a wrong value that names `--set` and the value
        (command-line.md › Form)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            for value in ("example-product", "example-product=invented", "#invented=1h",
                          "-#invented=1h"):  # a value that starts with - needs the = form
                given = [f"--set={value}"] if value.startswith("-") else ["--set", value]
                code, shown, error = run_action(world, ["timesheet", "confirm",
                                                        "2026-11-24", *given, "--json"],
                                                context)
                self.assertEqual(code, 2, value)
                self.assertEqual(json.loads(shown)["error"], {
                    "code": "wrong_value", "values": {"key": "--set", "value": value},
                    "message": f"The value {value} is not valid for --set.",
                })
                self.assertEqual(error, f"error: The value {value} is not valid for"
                                        " --set.\n")
            self.assertEqual([one for one in stored_events(world)
                              if one["kind"] == "timesheet_confirmation"], [])

    def test_timesheet_retract(self) -> None:
        """`timesheet retract` writes one retraction of the latest confirmation of the
        day, and a day whose latest confirmation is retracted holds none any more
        (command-line.md › Commands, › Timesheet)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            _, shown, _ = run_action(world, ["timesheet", "confirm", "2026-11-24", "--json"],
                                     context)
            confirmed = json.loads(shown)["event_uid"]
            code, shown, error = run_action(world, ["timesheet", "retract", "2026-11-24"],
                                            context)
            self.assertEqual(code, 0, error)
            self.assertTrue(shown.startswith("Event identifier: "), shown)
            retraction = shown.split("Event identifier: ", 1)[1].strip()
            [held] = [one for one in stored_events(world) if one["kind"] == "retraction"]
            self.assertEqual(held["event_uid"], retraction)
            self.assertEqual(held["retracts"], {"source": "ledger", "event_uid": confirmed})
            self.assertEqual(held["actor"], "human")
            self.assertEqual(held["machine"], MACHINE)
            self.assertEqual(held["timestamp"], "2026-11-24T12:00:00.000Z")
            code, shown, error = run_action(world,  # the day is measured again
                                            ["timesheet", "retract", "2026-11-24",
                                             "--json"], context)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(shown)["error"]["code"], "target_not_found")

    def test_timesheet_retract_unknown_day_exits_1(self) -> None:
        """A day whose confirmations the store does not hold names the day and stops
        (command-line.md › Commands)."""
        with support.TemporaryFolder() as base:
            world = self._world_with_prompt(base)
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            before = stored_events(world)
            code, shown, error = run_action(world, ["timesheet", "retract", "2026-11-23",
                                                    "--json"], context)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(shown)["error"], {
                "code": "target_not_found", "values": {"target": "2026-11-23"},
                "message": "The store does not hold the target 2026-11-23.",
            })
            self.assertEqual(error, "error: The store does not hold the target"
                                    " 2026-11-23.\n")
            code, shown, error = run_action(world, ["timesheet", "retract", "yesterday",
                                                    "--json"], context)
            self.assertEqual(code, 1)
            self.assertEqual(json.loads(shown)["error"]["values"], {"target": "2026-11-23"})
            self.assertEqual(stored_events(world), before)  # nothing is written

    def test_timesheet_actions_take_the_lock(self) -> None:
        """`timesheet confirm` and `timesheet retract` take the lock of the machine and
        the store, and refuse a development version that the environment does not let
        write, before the lock (architecture.md › Concurrency, › Runtime)."""
        original = platform.StoreLock.__enter__

        def recording(taker: platform.StoreLock, takes: list[str]) -> platform.StoreLock:
            takes.append(str(taker.path))
            return original(taker)

        confirm_words = ["timesheet", "confirm", "2026-11-24"]
        retract_words = ["timesheet", "retract", "2026-11-24"]
        for name, words, prepared in (("timesheet confirm", confirm_words, None),
                                      ("timesheet retract", retract_words, confirm_words)):
            with self.subTest(action=name):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    context = build_context(world)
                    if prepared is not None:  # the confirmation the retraction cancels
                        code, shown, error = run_action(world, [*prepared, "--json"],
                                                        context)
                        self.assertEqual(code, 0, error)
                    lock = (world.machine / "stores" /
                            platform.store_identifier(world.store, SYSTEM) / "lock")
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main([*words, "--store", str(world.store), "--json"],
                                        context)
                    self.assertEqual(code, 0, stderr.getvalue())
                    self.assertTrue(takes, name)  # the lock was taken
                    self.assertEqual(takes[0], str(lock))
            with self.subTest(action=f"{name} refused"):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    if prepared is not None:  # the confirmation, written by a release
                        run_action(world, [*prepared, "--json"], build_context(world))
                    environ = {key: value for key, value in world.environ.items()
                               if key != DEVELOPMENT_VARIABLE}
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main([*words, "--store", str(world.store), "--json"],
                                        build_context(world, version=DEV_VERSION,
                                                      environ=environ))
                    self.assertEqual(code, 1)
                    envelope = json.loads(stdout.getvalue())
                    self.assertEqual(envelope["error"]["code"], "development_version")
                    self.assertEqual(takes, [])  # nothing is locked before the guard


class TestReportActions(support.FixtureStores):
    """The actions of the report commands (command-line.md › Reports, › Frozen reports,
    › Output, › Exit codes; architecture.md › Concurrency): `report timesheet`, `report
    day`, and `timesheet <day>` write their warnings and configuration errors to the
    standard error before the table, compare each day of the period with its latest
    frozen report, refuse an inverted period, read the day words as local days of the
    person, take no lock, hold the language of their output in the record, and `timesheet
    <day>` shows no difference. Their text and JSON output against the expected files is
    in `test_reports_output.py`."""

    STORES = ("measured_day", "manual_entries", "frozen_period")
    """The stores that the tests of the class only read; a test that changes a store, or
    that needs another one, builds it in a temporary folder of its own."""

    def test_report_writes_its_warnings_before_the_table(self) -> None:
        """In text mode a report command writes its warning and configuration-error lines
        to the standard error before it writes its text, each line exactly once, and
        `emit` writes none of them again; in JSON mode the envelope carries each one with
        its text, and its line reaches the standard error once (command-line.md › Output,
        › Reports)."""
        context = self._contexts["manual_entries"]
        message = (f"The manual entry {support.build_uid(1)} overlaps measured "
                   "human time.")
        one = support.FIXTURE_DAY_ONE.isoformat()
        for words in (("report", "timesheet", "--from", one, "--to", one),
                      ("report", "day", one), ("timesheet", one)):
            with self.subTest(command=" ".join(words)):
                code, log = traced(context, words)
                self.assertEqual(code, 0)
                streams = [stream for stream, text in log if text.strip()]
                self.assertEqual(streams[0], "stderr")  # the lines come before the table
                self.assertEqual("".join(text for stream, text in log
                                         if stream == "stderr"), f"warning: {message}\n")
                self.assertEqual(streams.count("stdout"), 1)
                code, shown, error = support.run_main(context, *words, "--json")
                self.assertEqual(code, 0, error)
                self.assertEqual(json.loads(shown)["warnings"], [{
                    "code": "manual_entry_overlap",
                    "values": {"event_uid": support.build_uid(1)},
                    "message": message}])
                self.assertEqual(error, f"warning: {message}\n")

    def test_report_with_a_configuration_error_exits_3(self) -> None:
        """A configuration error leaves the figures of a report computable, and the
        report shows it: its line reaches the standard error before the table in text
        mode, the envelope carries it in JSON mode, and the command completes with the
        exit code 3 (command-line.md › Exit codes, › Output)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            code, shown, error = support.run_main(
                context, "config", "add", "project", "--id", "gamma", "--name", "Alpha")
            self.assertEqual(code, 0, error)
            one = support.FIXTURE_DAY_ONE.isoformat()
            message = ("The person configuration gives one name to two project "
                       "identifiers: alpha and gamma.")
            code, log = traced(context, ["report", "timesheet", "--from", one, "--to", one])
            self.assertEqual(code, 3)
            streams = [stream for stream, text in log if text.strip()]
            self.assertEqual(streams[0], "stderr")
            self.assertEqual("".join(text for stream, text in log if stream == "stderr"),
                             f"error: {message}\n")
            self.assertIn("2026-11-20  Measured day",
                          "".join(text for stream, text in log if stream == "stdout"))
            code, shown, error = support.run_main(
                context, "report", "timesheet", "--from", one, "--to", one, "--json")
            self.assertEqual(code, 3)
            self.assertEqual(json.loads(shown)["configuration_errors"], [{
                "code": "project_name_conflict",
                "values": {"first": "alpha", "second": "gamma"},
                "message": message}])
            self.assertEqual(error, f"error: {message}\n")

    def test_report_of_a_day_with_held_back_events_exits_3(self) -> None:
        """A report whose figures cover a session whose events this machine holds back
        warns about the session and completes with the exit code 3, in both modes; only
        `timesheet confirm` keeps the exit code 0 for that warning (command-line.md › Exit
        codes)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            support.write_session(logs, "session-one", [
                support.prompt_record("Invented prompt text.", "2026-11-24T09:00:00.000Z",
                                      UUID_ONE),
                support.output_record("Invented response text.", "2026-11-24T09:01:00.000Z",
                                      "3f1c0000-0000-4000-8000-0000000000b1", "msg-invented-1")],
                {}, world.home / "work")  # not settled: the machine holds the response back
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            context = build_context(world)
            run_action(world, ["ingest", "--json"], context)
            line = ("warning: The session session-one is not complete yet: this machine "
                    "holds its events back.\n")
            one = "2026-11-24"  # the day of the prompt, the day of the instant of the tests
            for words in (("report", "day", one), ("timesheet", one), ("sessions", one),
                          ("report", "timesheet", "--from", one, "--to", one)):
                with self.subTest(command=" ".join(words)):
                    code, shown, error = run_action(world, [*words, "--json"], context)
                    self.assertEqual(code, 3)
                    self.assertEqual([warning["code"]
                                      for warning in json.loads(shown)["warnings"]],
                                     ["held_back_events"])
                    self.assertEqual(error, line)
                    code, shown, error = run_action(world, list(words), context)
                    self.assertEqual(code, 3)
                    self.assertEqual(error, line)

    def test_each_day_compares_with_its_latest_frozen_report(self) -> None:
        """Where frozen reports overlap over one period, each day compares with the
        latest frozen report that holds it (command-line.md › Frozen reports): the figure
        rows of a pair cover only the days that its frozen report wins; the pairs follow
        the order of the first day of the period that each one wins, so the rows read in
        the order of the days; the rows of `changed` of the pairs merge in that order, an
        identical row once; and a frozen report that wins no day gives no row."""
        one, two = (support.FIXTURE_DAY_ONE.isoformat(), support.FIXTURE_DAY_TWO.isoformat())
        alpha = {"id": "alpha", "name": "Alpha"}
        beta = {"id": "beta", "name": "Beta"}
        at_first_freeze = {"id": "example.com/acme/beta", "name": "beta"}
        attention = {"path": "parameters.minimum_attention", "frozen": 60, "now": 120}
        rule = {"path": "identity_rules[1]",
                "now": {"project": "beta", "repository": "example.com/acme/beta",
                        "folder": None, "branch": None, "from": None, "to": None}}
        hour = timedelta(hours=1)

        def gaps(seconds: int, keys: Sequence[int] = (300, 600, 900)) -> dict[str, int]:
            """The human time of a day of one prompt at the idle gaps given."""
            return {str(key): seconds for key in keys}

        def rows(day: str, project: dict, frozen_gaps: dict) -> list[dict]:
            """The figure rows of a day of one prompt whose figures all differ between
            its frozen document, computed at a minimum attention of one minute, and the
            document of now at two minutes."""
            return [
                {"day": day, "figure": "total", "frozen": 60, "now": 120},
                {"day": day, "figure": "measured_total", "frozen": 60, "now": 120},
                {"day": day, "figure": "human_time_at_idle_gaps", "frozen": frozen_gaps,
                 "now": gaps(120)},
                {"day": day, "project": project, "work_item": None, "figure": "measured",
                 "frozen": 60, "now": 120},
                {"day": day, "project": project, "work_item": None,
                 "figure": "with_manual_entries", "frozen": 60, "now": 120},
            ]

        with support.TemporaryFolder() as home:
            context = support.fixture_store("frozen_period", home)
            # a later frozen report of the first day alone, at an idle gap of 20 minutes
            later = context._replace(now=support.FIXTURE_NOW + hour)
            code, shown, error = support.run_main(
                later, "report", "timesheet", "--from", one, "--to", one,
                "--idle-gap", "20min", "--freeze", "--json")
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(shown)["frozen_id"], support.FIXTURE_FIRST_UID)
            words = ["report", "timesheet", "--from", one, "--to", two,
                     "--minimum-attention", "2min"]
            code, shown, error = support.run_main(context, *words, "--json")
            self.assertEqual(code, 0, error)
            document = json.loads(shown)
            # the first day is against the later frozen report, which holds it alone
            # and was computed at another idle gap; the second day is against the frozen
            # report of the fixture, which holds both days but wins the second only
            self.assertEqual(document["differences"], [
                *rows(one, alpha, gaps(60, (300, 600, 900, 1200))),
                {"day": two, "figure": "total", "frozen": 60, "now": 120},
                {"day": two, "figure": "measured_total", "frozen": 60, "now": 120},
                {"day": two, "figure": "human_time_at_idle_gaps", "frozen": gaps(60),
                 "now": gaps(120)},
                {"day": two, "project": at_first_freeze, "work_item": None,
                 "figure": "measured", "frozen": 60},
                {"day": two, "project": at_first_freeze, "work_item": None,
                 "figure": "with_manual_entries", "frozen": 60},
                {"day": two, "project": at_first_freeze, "work_item": None,
                 "figure": "inferred_human_share", "frozen": 0.0},
                {"day": two, "project": at_first_freeze, "work_item": None,
                 "figure": "inferred_agent_share", "frozen": 0.0},
                {"day": two, "project": beta, "work_item": None, "figure": "measured",
                 "now": 120},
                {"day": two, "project": beta, "work_item": None,
                 "figure": "with_manual_entries", "now": 120},
                {"day": two, "project": beta, "work_item": None,
                 "figure": "inferred_human_share", "now": 0.0},
                {"day": two, "project": beta, "work_item": None,
                 "figure": "inferred_agent_share", "now": 0.0},
            ])
            # the minimum attention changed against both frozen reports: one row
            self.assertEqual(document["changed"], [
                {"path": "parameters.idle_gap", "frozen": 1200, "now": 600},
                attention, rule])
            code, shown, error = support.run_main(context, *words)
            self.assertEqual(code, 0, error)
            # a report parameter that is a duration shows as H:MM (command-line.md ›
            # Output); the rule shows as one row for each scalar leaf that differs and
            # no row for its null fields
            self.assertEqual(shown.split("\n\n")[-1].splitlines(), [
                "Changed",
                "Path" + " " * 26 + "Frozen  Now",
                "parameters.idle_gap" + " " * 13 + "0:20  0:10",
                "parameters.minimum_attention" + " " * 4 + "0:01  0:02",
                "identity_rules[1].project" + " " * 13 + "beta",
                "identity_rules[1].repository" + " " * 10 + "example.com/acme/beta"])
            latest = context._replace(now=support.FIXTURE_NOW + 2 * hour)
            code, shown, error = support.run_main(
                latest, "report", "timesheet", "--from", one, "--to", two, "--freeze",
                "--json")
            self.assertEqual(code, 0, error)
            code, shown, error = support.run_main(context, *words, "--json")
            self.assertEqual(code, 0, error)
            document = json.loads(shown)
            # the latest frozen report wins both days: the two others give no row
            self.assertEqual(document["differences"],
                             rows(one, alpha, gaps(60)) + rows(two, beta, gaps(60)))
            self.assertEqual(document["changed"], [attention])

    def test_a_figure_that_is_an_object_shows_one_row_for_each_leaf(self) -> None:
        """In the text of a report against frozen reports, a figure or a fact whose value
        is an object shows as one row for each scalar leaf that differs, named by its
        dotted path, each leaf by its kind — a duration as H:MM — and a leaf that is the
        same on both sides gives no row; the JSON document holds the object unchanged
        (command-line.md › Output, › Frozen reports)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            one = support.FIXTURE_DAY_ONE.isoformat()
            code, shown, error = support.run_main(
                context, "report", "day", one, "--minimum-attention", "2min", "--freeze",
                "--json")
            self.assertEqual(code, 0, error)
            code, shown, error = support.run_main(context, "report", "day", one, "--json")
            self.assertEqual(code, 0, error)
            document = json.loads(shown)
            # the frozen report counted the lone prompt as two minutes and now counts
            # one: the human time of the day halved, and the idle time gained a minute
            self.assertEqual(document["differences"], [
                {"day": one, "figure": "human_time_at_idle_gaps",
                 "frozen": {"300": 120, "600": 120, "900": 120},
                 "now": {"300": 60, "600": 60, "900": 60}},
                {"day": one, "figure": "human_time", "frozen": 120, "now": 60},
                {"day": one, "figure": "activity_classes",
                 "frozen": {"person_only": 120, "supervised": 0, "unattended": 300,
                            "blocked": 0, "idle": 85980},
                 "now": {"person_only": 60, "supervised": 0, "unattended": 300,
                         "blocked": 0, "idle": 86040}},
                {"day": one, "project": {"id": "alpha", "name": "Alpha"},
                 "figure": "human_time", "frozen": 120, "now": 60},
                {"day": one, "project": {"id": "alpha", "name": "Alpha"},
                 "figure": "activity_classes",
                 "frozen": {"person_only": 120, "supervised": 0, "unattended": 300,
                            "blocked": 0},
                 "now": {"person_only": 60, "supervised": 0, "unattended": 300,
                         "blocked": 0}}])
            self.assertEqual(document["changed"], [
                {"path": "parameters.minimum_attention", "frozen": 120, "now": 60}])
            code, shown, error = support.run_main(context, "report", "day", one)
            self.assertEqual(code, 0, error)
            differences, changed = shown.split("\n\n")[-2:]
            day = "2026-11-20" + " " * 22  # the day, then no project and no work item
            alpha = "2026-11-20  Alpha" + " " * 15  # its two cells padded, the work item empty
            # the Now column is five wide, so a value of four comes one space in
            self.assertEqual(differences.splitlines(), [
                "Differences",
                "Day" + " " * 9 + "Project  Work item  Figure" + " " * 24
                + "Frozen    Now",
                day + "human_time_at_idle_gaps.300" + " " * 5 + "0:02" + " " * 3
                + "0:01",
                day + "human_time_at_idle_gaps.600" + " " * 5 + "0:02" + " " * 3
                + "0:01",
                day + "human_time_at_idle_gaps.900" + " " * 5 + "0:02" + " " * 3
                + "0:01",
                day + "human_time" + " " * 22 + "0:02" + " " * 3 + "0:01",
                day + "activity_classes.person_only" + " " * 4 + "0:02" + " " * 3
                + "0:01",
                day + "activity_classes.idle" + " " * 10 + "23:53" + " " * 2 + "23:54",
                alpha + "human_time" + " " * 22 + "0:02" + " " * 3 + "0:01",
                alpha + "activity_classes.person_only" + " " * 4 + "0:02" + " " * 3
                + "0:01"])
            self.assertEqual(changed.splitlines(), [
                "Changed",
                "Path" + " " * 26 + "Frozen   Now",
                "parameters.minimum_attention" + " " * 4 + "0:02" + " " * 2 + "0:01"])

    def test_a_frozen_report_of_another_action_compares_only_what_both_hold(
            self) -> None:
        """A report whose latest frozen report is of another command compares only on the
        figures that both documents hold under the same name, and `changed` compares
        always (command-line.md › Frozen reports): `report day` of the
        second day of `frozen_period` against its frozen `report timesheet` holds no
        difference — the entries of the one and the person and the projects of the other
        are figures of one document — and the rule that the record of now holds; its text
        shows the header of the differences alone, and the rule as one row for each
        scalar leaf that differs and none for its null fields."""
        context = self._contexts["frozen_period"]
        two = support.FIXTURE_DAY_TWO.isoformat()
        rule = {"path": "identity_rules[1]",
                "now": {"project": "beta", "repository": "example.com/acme/beta",
                        "folder": None, "branch": None, "from": None, "to": None}}
        code, shown, error = support.run_main(context, "report", "day", two, "--json")
        self.assertEqual(code, 0, error)
        document = json.loads(shown)
        self.assertEqual(document["differences"], [])
        self.assertEqual(document["changed"], [rule])
        code, shown, error = support.run_main(context, "report", "day", two)
        self.assertEqual(code, 0, error)
        differences, changed = shown.split("\n\n")[-2:]
        # no row: every column as wide as its header alone
        self.assertEqual(differences.splitlines(), [
            "Differences", "Day  Project  Work item  Figure  Frozen  Now"])
        self.assertEqual(changed.splitlines(), [
            "Changed",
            "Path" + " " * 26 + "Frozen  Now",
            "identity_rules[1].project" + " " * 13 + "beta",
            "identity_rules[1].repository" + " " * 10 + "example.com/acme/beta"])

    def test_two_reports_of_one_action_keep_a_one_sided_row(self) -> None:
        """Between two reports of one command, a figure that only one of them holds is a
        difference: a bucket that appears after the freeze gives its rows with the value
        of now alone, and the other figures stay as they were (command-line.md › Frozen
        reports)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            one = support.FIXTURE_DAY_ONE.isoformat()
            code, shown, error = support.run_main(
                context, "report", "timesheet", "--from", one, "--to", one, "--freeze",
                "--json")
            self.assertEqual(code, 0, error)
            code, shown, error = support.run_main(
                context, "entry", "add", "--from", "2026-11-20T12:00", "--to",
                "2026-11-20T13:00", "--project", "beta", "--mode", "additional")
            self.assertEqual(code, 0, error)
            code, shown, error = support.run_main(
                context, "report", "timesheet", "--from", one, "--to", one, "--json")
            self.assertEqual(code, 0, error)
            document = json.loads(shown)
            beta = {"id": "beta", "name": "Beta"}
            self.assertEqual(document["differences"], [
                {"day": one, "figure": "total", "frozen": 60, "now": 3660},
                {"day": one, "project": beta, "work_item": None, "figure": "measured",
                 "now": 0},
                {"day": one, "project": beta, "work_item": None,
                 "figure": "with_manual_entries", "now": 3600},
                {"day": one, "project": beta, "work_item": None,
                 "figure": "inferred_human_share", "now": 0.0},
                {"day": one, "project": beta, "work_item": None,
                 "figure": "inferred_agent_share", "now": 0.0}])
            self.assertEqual(document["changed"], [])

    def test_a_shared_figure_that_differs_stays_for_another_action(self) -> None:
        """The other half of the rule for a frozen report of another command: a figure
        that both documents hold under the same name and that differs stays, with its
        frozen value and its value of now, and `changed` compares always. `report day` of
        the second day of `frozen_period` at a minimum attention of two minutes against
        its frozen `report timesheet` keeps the human time at the idle gaps, which both
        documents hold, and the two facts of the record that differ (command-line.md ›
        Frozen reports)."""
        context = self._contexts["frozen_period"]
        two = support.FIXTURE_DAY_TWO.isoformat()
        code, shown, error = support.run_main(
            context, "report", "day", two, "--minimum-attention", "2min", "--json")
        self.assertEqual(code, 0, error)
        document = json.loads(shown)
        self.assertEqual(document["differences"], [{
            "day": two, "figure": "human_time_at_idle_gaps",
            "frozen": {"300": 60, "600": 60, "900": 60},
            "now": {"300": 120, "600": 120, "900": 120}}])
        self.assertEqual(document["changed"], [
            {"path": "parameters.minimum_attention", "frozen": 60, "now": 120},
            {"path": "identity_rules[1]",
             "now": {"project": "beta", "repository": "example.com/acme/beta",
                     "folder": None, "branch": None, "from": None, "to": None}}])
        code, shown, error = support.run_main(
            context, "report", "day", two, "--minimum-attention", "2min")
        self.assertEqual(code, 0, error)
        differences = shown.split("\n\n")[-2].splitlines()
        self.assertEqual(differences[0], "Differences")
        header = ("Day" + " " * 9 + "Project  Work item  Figure" + " " * 23
                  + "Frozen" + " " * 3 + "Now")
        self.assertEqual(differences[1], header)
        self.assertEqual(differences[2:5], [
            "2026-11-21" + " " * 22 + "human_time_at_idle_gaps.300" + " " * 4
            + "0:01" + "  " + "0:02",
            "2026-11-21" + " " * 22 + "human_time_at_idle_gaps.600" + " " * 4
            + "0:01" + "  " + "0:02",
            "2026-11-21" + " " * 22 + "human_time_at_idle_gaps.900" + " " * 4
            + "0:01" + "  " + "0:02"])

    def test_the_record_holds_the_language_of_the_output(self) -> None:
        """The report record holds the language of the output as the report parameter
        `language`: the option `--language` over the person configuration and the
        defaults, as for every report parameter (command-line.md › Form, › Reports;
        metrics.md › Reproducibility)."""
        context = self._contexts["measured_day"]
        one = support.FIXTURE_DAY_ONE.isoformat()
        for words, expected in (
                (["report", "day", one, "--language", "it"], "it"),
                (["report", "day", one], "en"),
                (["report", "timesheet", "--from", one, "--to", one, "--language", "it"],
                 "it")):
            with self.subTest(words=" ".join(words)):
                code, shown, error = support.run_main(context, *words, "--json")
                self.assertEqual(code, 0, error)
                self.assertEqual(
                    json.loads(shown)["record"]["parameters"]["language"], expected)

    def test_report_timesheet_inverted_period_exits_2(self) -> None:
        """A period whose first day comes after its last day holds no day: the command
        stops with a wrong value that names `--to` and the value as the person typed it,
        in both modes, and writes no table; a period whose ends are the same day is a
        period of one day (command-line.md › Form)."""
        context = self._contexts["measured_day"]
        one = support.FIXTURE_DAY_ONE.isoformat()
        for first, last in ((one, "2026-11-19"), ("today", "yesterday")):
            with self.subTest(period=f"{first}..{last}"):
                code, shown, error = support.run_main(
                    context, "report", "timesheet", "--from", first, "--to", last, "--json")
                self.assertEqual(code, 2)
                self.assertEqual(json.loads(shown)["error"], {
                    "code": "wrong_value", "values": {"key": "--to", "value": last},
                    "message": f"The value {last} is not valid for --to."})
                self.assertEqual(error,
                                 f"error: The value {last} is not valid for --to.\n")
                code, shown, error = support.run_main(
                    context, "report", "timesheet", "--from", first, "--to", last)
                self.assertEqual(code, 2)
                self.assertEqual(shown, "")
                self.assertEqual(error,
                                 f"error: The value {last} is not valid for --to.\n")
        code, shown, error = support.run_main(
            context, "report", "timesheet", "--from", one, "--to", one, "--json")
        self.assertEqual(code, 0, error)
        self.assertEqual([day["day"] for day in json.loads(shown)["days"]], [one])

    def test_day_words_name_the_local_days_of_the_person(self) -> None:
        """`today` and `yesterday` name the local days of the person at the instant of the
        run, through the time-zone history and the day start hours: with a day start at
        four, two in the morning still belongs to the day before (command-line.md › Form;
        metrics.md › Days and weeks)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("declared_day", home)
            code, shown, error = support.run_main(
                context, "config", "add", "day-start", "--hour", "04:00", "--from",
                "2026-11-19")
            self.assertEqual(code, 0, error)
            context = context._replace(now=support.utc("2026-11-24T02:00:00"))
            declared = support.FIXTURE_DAY_THREE.isoformat()
            code, shown, error = support.run_main(
                context, "report", "day", "today", "--json")
            self.assertEqual(code, 0, error)
            document = json.loads(shown)
            self.assertEqual((document["day"], document["state"]),
                             (declared, "declared_day"))
            code, shown, error = support.run_main(
                context, "report", "timesheet", "--from", "yesterday", "--to", "today",
                "--json")
            self.assertEqual(code, 0, error)
            self.assertEqual([day["day"] for day in json.loads(shown)["days"]],
                             ["2026-11-22", declared])
            code, shown, error = support.run_main(context, "timesheet", "today", "--json")
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(shown)["day"], declared)

    def test_timesheet_shows_no_difference(self) -> None:
        """`timesheet <day>` shows the proposal and the entries of the day and no
        difference, also on a day that a frozen report holds (command-line.md ›
        Reports)."""
        context = self._contexts["frozen_period"]
        two = support.FIXTURE_DAY_TWO.isoformat()
        code, shown, error = support.run_main(context, "timesheet", two, "--json")
        self.assertEqual(code, 0, error)
        document = json.loads(shown)
        self.assertNotIn("differences", document)
        self.assertNotIn("changed", document)
        code, shown, error = support.run_main(context, "timesheet", two)
        self.assertEqual(code, 0, error)
        self.assertNotIn(language.label("differences", "en"), shown)
        self.assertNotIn(language.label("changed", "en"), shown)

    def test_report_timesheet_holds_the_inactive_days_of_a_period(self) -> None:
        """A period holds also its local days without events and without a confirmation:
        each one is a measured day of total zero, with no entry and no human time at any
        idle gap (command-line.md › Reports)."""
        context = self._contexts["measured_day"]
        words = ["report", "timesheet", "--from", "2026-11-19", "--to", "2026-11-21"]
        code, shown, error = support.run_main(context, *words, "--json")
        self.assertEqual(code, 0, error)
        days = json.loads(shown)["days"]
        self.assertEqual([day["day"] for day in days],
                         ["2026-11-19", "2026-11-20", "2026-11-21"])
        for day in (days[0], days[2]):
            self.assertEqual(day, {
                "day": day["day"], "state": "measured_day", "total": 0,
                "measured_total": 0, "unknown_invocation_share": 0.0, "entries": [],
                "human_time_at_idle_gaps": {"300": 0, "600": 0, "900": 0}})
        code, shown, error = support.run_main(context, *words)
        self.assertEqual(code, 0, error)
        first, following, gaps = shown.split("\n\n")[:3]
        self.assertEqual(first.splitlines()[0], "2026-11-19  Measured day")
        self.assertTrue(first.endswith("Total                   0:00                 0:00"), first)
        self.assertEqual(following, "Unknown invocation share  0.00")
        self.assertEqual(gaps.splitlines(), [
            "Human time at idle gaps", "Idle gap  Human time",
            "0:05            0:00", "0:10            0:00", "0:15            0:00"])

    def test_report_commands_take_no_lock(self) -> None:
        """A report reads the lines that the segments hold and takes no lock
        (architecture.md › Concurrency)."""
        original = platform.StoreLock.__enter__

        def recording(taker: platform.StoreLock, takes: list[str]) -> platform.StoreLock:
            takes.append(str(taker.path))
            return original(taker)

        one = support.FIXTURE_DAY_ONE.isoformat()
        for words in (("report", "timesheet", "--from", one, "--to", one),
                      ("report", "day", one), ("timesheet", one)):
            with self.subTest(command=" ".join(words)):
                takes: list[str] = []
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(platform.StoreLock, "__enter__",
                                       lambda taker, takes=takes: recording(taker, takes)):
                    with contextlib.redirect_stdout(stdout), \
                            contextlib.redirect_stderr(stderr):
                        code = main(list(words), self._contexts["measured_day"])
                self.assertEqual(code, 0, stderr.getvalue())
                self.assertEqual(takes, [])


class TestSessionsAction(unittest.TestCase):
    """The action of `sessions <day>` (command-line.md › Commands, › JSON documents): the
    sessions with at least one event in the day, each with the instants of its first and
    its last event in the day and the parts of the day that the split rule gives it. As a
    report, it writes its warnings to the standard error before its table, holds the
    report record, and completes with the exit code 3 when a figure is incomplete."""

    def _world_with_sessions(self, base: Path) -> tuple[World, Context]:
        """A set-up world whose store holds four settled sessions around the day
        2026-11-20, all in one folder without a repository: one that crosses the start of
        the day, one that crosses its end, one of the day before alone, and one whose only
        event is a prompt at exactly the start of the day."""
        world = build_world(base)
        logs = world.home / ".claude" / "projects"
        prefix = "3f1c0000-0000-4000-8000-0000000000"
        sessions = {
            "session-start": [
                support.prompt_record("Invented prompt before the day.",
                                      "2026-11-19T23:50:00.000Z", prefix + "d1"),
                support.output_record("Invented answer inside the day.",
                                      "2026-11-20T00:10:00.000Z", prefix + "d2",
                                      "msg-invented-d1"),
                support.prompt_record("Invented prompt inside the day.",
                                      "2026-11-20T00:40:00.000Z", prefix + "d3"),
                support.output_record("Invented second answer.", "2026-11-20T00:45:00.000Z",
                                      prefix + "d4", "msg-invented-d2"),
            ],
            "session-end": [
                support.prompt_record("Invented prompt of the morning.",
                                      "2026-11-20T10:00:00.000Z", prefix + "e1"),
                support.output_record("Invented answer of the morning.",
                                      "2026-11-20T10:05:00.000Z", prefix + "e2",
                                      "msg-invented-e1"),
                support.prompt_record("Invented prompt after the day.",
                                      "2026-11-21T00:05:00.000Z", prefix + "e3"),
            ],
            "session-before": [
                support.prompt_record("Invented prompt of the day before.",
                                      "2026-11-19T10:00:00.000Z", prefix + "f1"),
            ],
            "session-midnight": [
                support.prompt_record("Invented prompt at the start of the day.",
                                      "2026-11-20T00:00:00.000Z", prefix + "g1"),
            ],
        }
        for session_id, records in sessions.items():
            support.write_session(logs, session_id, records, {}, world.home / "work")
        settle(sorted(logs.rglob("*.jsonl")))
        set_up(world, world.store, recorded=str(world.store), logs=[logs])
        return world, build_context(world)

    def test_sessions_list_the_sessions_with_an_event_in_the_day(self) -> None:
        """A session that crosses the start or the end of the day shows its first and its
        last event inside the day and the parts of the day alone; a session with events in
        the day and no part in it is listed with `parts` empty; a session of the day before
        is not listed. The sessions follow the order of their start. The document holds no
        `branch`, because no record of the store holds one. The warnings go before the
        table and `record` is in the document (command-line.md › Commands)."""
        with support.TemporaryFolder() as base:
            world, context = self._world_with_sessions(base)
            run_action(world, ["ingest", "--json"], context)
            code, shown, error = run_action(
                world, ["config", "add", "project", "--id", "p", "--name", "P", "--json"],
                context)
            self.assertEqual(code, 0, error)
            code, shown, error = run_action(world, [
                "entry", "add", "--from", "2026-11-20T09:30", "--to", "2026-11-20T10:30",
                "--project", "p", "--mode", "overlapping", "--json"], context)
            self.assertEqual(code, 0, error)
            entered = json.loads(shown)["event_uid"]
            cwd = str(world.home / "work")
            day = "2026-11-20"
            message = f"The manual entry {entered} overlaps measured human time."
            code, log = traced(context, ["sessions", day])
            self.assertEqual(code, 0)
            streams = [stream for stream, text in log if text.strip()]
            self.assertEqual(streams[0], "stderr")  # the lines come before the table
            self.assertEqual("".join(text for stream, text in log if stream == "stderr"),
                             f"warning: {message}\n")
            self.assertEqual(streams.count("stdout"), 1)
            code, shown, error = support.run_main(context, "sessions", day, "--json")
            self.assertEqual(code, 0, error)
            document = json.loads(shown)
            self.assertEqual(document["warnings"], [{
                "code": "manual_entry_overlap", "values": {"event_uid": entered},
                "message": message}])
            self.assertEqual(error, f"warning: {message}\n")
            self.assertEqual(document["day"], day)
            self.assertEqual(document["command"], "sessions")
            self.assertEqual(document["record"]["parameters"]["language"], "en")
            # the prompt at midnight counts its minimum attention before the day, and no
            # agent answers it: the session holds an event of the day and no part
            self.assertEqual(document["sessions"], [
                {"session_id": "session-midnight", "tool": "claude-code",
                 "start": "2026-11-20T00:00:00.000Z", "end": "2026-11-20T00:00:00.000Z",
                 "cwd": cwd, "parts": []},
                # the turn from the day before ends at 00:10: ten minutes of agent time
                {"session_id": "session-start", "tool": "claude-code",
                 "start": "2026-11-20T00:10:00.000Z", "end": "2026-11-20T00:45:00.000Z",
                 "cwd": cwd, "parts": [{"project": None, "work_item": None,
                                        "human_time": 60, "agent_time": 900}]},
                # the parts take the attribution of the signals by the split rule: the
                # manual entry in mode `overlapping` moves the time in the timesheet of
                # the day, which it warns about, and changes no part
                {"session_id": "session-end", "tool": "claude-code",
                 "start": "2026-11-20T10:00:00.000Z", "end": "2026-11-20T10:05:00.000Z",
                 "cwd": cwd, "parts": [{"project": None, "work_item": None,
                                        "human_time": 60, "agent_time": 300}]}])
            code, shown, error = support.run_main(context, "sessions", "2026-11-21", "--json")
            self.assertEqual(code, 0, error)
            self.assertEqual(json.loads(shown)["sessions"], [
                {"session_id": "session-end", "tool": "claude-code",
                 "start": "2026-11-21T00:05:00.000Z", "end": "2026-11-21T00:05:00.000Z",
                 "cwd": cwd, "parts": [{"project": None, "work_item": None,
                                        "human_time": 60, "agent_time": 0}]}])

    def test_sessions_of_a_day_that_holds_none(self) -> None:
        """`sessions <day>` of a day that holds no session, the day before the day of the
        store `measured_day`: the text is the title of the day and the header of the table
        alone, and the document holds no session, with its report record; both compared
        with the expected pair `sessions_empty_day` through `support.normalize`, in
        English and in Italian — `--language it`, the only word that the Italian run adds,
        reads the folder `it` of the expected files (command-line.md › Commands, › JSON
        documents, › Form). The command only reads the store, so one store serves both
        languages."""
        expected = Path(__file__).resolve().parent / "fixtures" / "expected"
        day = (support.FIXTURE_DAY_ONE - timedelta(days=1)).isoformat()
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            for chosen in language.LANGUAGES:
                spoken = () if chosen == "en" else ("--language", chosen)
                for kind, extra in (("txt", ()), ("json", ("--json",))):
                    with self.subTest(language=chosen, output=kind):
                        code, shown, error = support.run_main(
                            context, "sessions", day, *extra, *spoken)
                        self.assertEqual(code, 0, error)
                        self.assertEqual(error, "")
                        self.assertEqual(support.normalize(shown, [home]), support.normalize(
                            (expected / chosen / f"sessions_empty_day.{kind}").read_text(
                                encoding="utf-8"), [home]))


class TestFrozenActions(unittest.TestCase):
    """The actions of `--freeze` and of the three `frozen` commands (command-line.md ›
    Frozen reports, › JSON documents, › Exit codes; architecture.md › Concurrency): a
    report with `--freeze` keeps its JSON document, without its differences, as a frozen
    report under the lock; `frozen list` and `frozen show` read the frozen reports and
    take no lock, `frozen show` computing the report of now over the days of the frozen
    one; `frozen remove` takes the lock and reads no file; a file that the ledger cannot
    read and a command that this version does not know stop with their own errors. A test
    that freezes builds its own store, because the freeze changes it."""

    UNKNOWN = "20000000-0000-4000-8000-000000000099"
    """The identifier of a frozen report that no store of the tests holds."""

    def _file(self, home: Path, frozen_id: str) -> Path:
        """The path of the file of one frozen report of the machine of the fixtures."""
        return (support.fixture_store_folder(home) / "frozen"
                / support.FIXTURE_MACHINE / f"{frozen_id}.json")

    def _frozen(self, home: Path) -> list[tuple[str, str]]:
        """The names of the frozen reports of one store of the fixtures."""
        return store.frozen_names(support.fixture_store_folder(home))

    def test_frozen_actions_take_the_lock(self) -> None:
        """`report timesheet --freeze`, `report day --freeze`, and `frozen remove` take
        the lock of the machine and the store, and refuse a development version that the
        environment does not let write, before the lock; a report without `--freeze`,
        `frozen list`, and `frozen show` take no lock (architecture.md › Concurrency)."""
        original = platform.StoreLock.__enter__

        def recording(taker: platform.StoreLock, takes: list[str]) -> platform.StoreLock:
            takes.append(str(taker.path))
            return original(taker)

        day = "2026-11-24"
        keeping = ["report", "day", day, "--freeze"]
        for name, words, prepared in (
                ("report timesheet --freeze",
                 ["report", "timesheet", "--from", day, "--to", day, "--freeze"], None),
                ("report day --freeze", list(keeping), None),
                ("frozen remove", ["frozen", "remove", "invented"], keeping)):
            with self.subTest(action=name):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    context = build_context(world)
                    if prepared is not None:  # the frozen report the removal removes
                        code, shown, error = run_action(world, [*prepared, "--json"],
                                                        context)
                        self.assertEqual(code, 0, error)
                        words = [*words[:2], json.loads(shown)["frozen_id"]]
                    lock = (world.machine / "stores" /
                            platform.store_identifier(world.store, SYSTEM) / "lock")
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main([*words, "--store", str(world.store), "--json"],
                                        context)
                    self.assertEqual(code, 0, stderr.getvalue())
                    self.assertTrue(takes, name)  # the lock was taken
                    self.assertEqual(takes[0], str(lock))
            with self.subTest(action=f"{name} refused"):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    if prepared is not None:  # written by a release version
                        run_action(world, [*prepared, "--json"], build_context(world))
                        words = [*words[:2], support.FIXTURE_FIRST_UID]
                    environ = {key: value for key, value in world.environ.items()
                               if key != DEVELOPMENT_VARIABLE}
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main([*words, "--store", str(world.store), "--json"],
                                        build_context(world, version=DEV_VERSION,
                                                      environ=environ))
                    self.assertEqual(code, 1)
                    envelope = json.loads(stdout.getvalue())
                    self.assertEqual(envelope["error"]["code"], "development_version")
                    self.assertEqual(takes, [])  # nothing is locked before the guard
        with support.TemporaryFolder() as home:
            context = support.fixture_store("frozen_period", home)
            one = support.FIXTURE_DAY_ONE.isoformat()
            for name, words in (
                    ("report without --freeze", ["report", "day", one]),
                    ("frozen list", ["frozen", "list"]),
                    ("frozen show", ["frozen", "show", support.build_uid(1)])):
                with self.subTest(action=name):
                    takes: list[str] = []
                    stdout, stderr = io.StringIO(), io.StringIO()
                    with mock.patch.object(platform.StoreLock, "__enter__",
                                           lambda taker, takes=takes: recording(taker,
                                                                                takes)):
                        with contextlib.redirect_stdout(stdout), \
                                contextlib.redirect_stderr(stderr):
                            code = main(list(words), context)
                    self.assertEqual(code, 0, stderr.getvalue())
                    self.assertEqual(takes, [])

    def test_freeze_refused_by_the_guard_leaves_no_line(self) -> None:
        """The figures and the differences of a report with `--freeze` are computed as
        every report computes them, but nothing reaches a stream before the file is
        written: a development version that the environment does not let write stops the
        command with exit code 1, and the warning of the day, which a completed report
        writes before its table, stays out of the standard error (architecture.md ›
        Concurrency)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("manual_entries", home)
            environ = {key: value for key, value in context.environ.items()
                       if key != DEVELOPMENT_VARIABLE}
            refused = context._replace(version=DEV_VERSION, environ=environ)
            one = support.FIXTURE_DAY_ONE.isoformat()
            for words in (("report", "timesheet", "--from", one, "--to", one, "--freeze"),
                          ("report", "day", one, "--freeze")):
                with self.subTest(command=" ".join(words)):
                    code, log = traced(refused, list(words))
                    self.assertEqual(code, 1)
                    self.assertEqual(log, [(
                        "stderr", "error: A development version does not write to the"
                                  " store; set AI_EFFORT_LEDGER_DEVELOPMENT=1 to allow"
                                  " it.\n")])
            self.assertEqual(self._frozen(home), [])

    def test_frozen_remove_of_unknown_id_exits_1(self) -> None:
        """An identifier that the store does not hold stops `frozen remove` with the exit
        code 1 in both modes and names the target; the standard output stays empty in text
        mode, and no file is written or removed (command-line.md › Commands)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("frozen_period", home)
            before = self._frozen(home)
            self.assertEqual(len(before), 1)
            message = f"The store does not hold the target {self.UNKNOWN}."
            for extra in ([], ["--json"]):
                with self.subTest(json=bool(extra)):
                    code, shown, error = support.run_main(
                        context, "frozen", "remove", self.UNKNOWN, *extra)
                    self.assertEqual(code, 1)
                    self.assertEqual(error, f"error: {message}\n")
                    if extra:
                        self.assertEqual(json.loads(shown)["error"], {
                            "code": "target_not_found", "values": {"target": self.UNKNOWN},
                            "message": message})
                    else:
                        self.assertEqual(shown, "")
            self.assertEqual(self._frozen(home), before)

    def test_frozen_remove_refuses_an_identifier_that_names_a_path(self) -> None:
        """The identifier of `frozen remove` is one name of a file below the frozen folder
        of a machine: a word with a separator or a parent step would name a file outside
        that folder, so the command line refuses it with the wrong-value stop before any
        file is read or removed, and the file that the word would reach keeps its place
        (command-line.md › Frozen reports, › Exit codes)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("frozen_period", home)
            outside = support.fixture_store_folder(home) / "frozen" / "victim.json"
            outside.write_text("{}\n", encoding="utf-8")  # one folder above the machine
            message = "The value ../victim is not valid for <id>."
            for extra in ([], ["--json"]):
                with self.subTest(json=bool(extra)):
                    code, shown, error = support.run_main(
                        context, "frozen", "remove", "../victim", *extra)
                    self.assertEqual(code, 2)
                    self.assertEqual(error, f"error: {message}\n")
                    if extra:
                        self.assertEqual(json.loads(shown)["error"], {
                            "code": "wrong_value",
                            "values": {"key": "<id>", "value": "../victim"},
                            "message": message})
                    else:
                        self.assertEqual(shown, "")
                    self.assertTrue(outside.is_file())

    def test_frozen_show_of_unknown_id_exits_1(self) -> None:
        """An identifier that the store does not hold stops `frozen show` with the exit
        code 1 in both modes and names the target; the standard output stays empty in text
        mode, and no file is written or removed (command-line.md › Commands)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("frozen_period", home)
            before = self._frozen(home)
            message = f"The store does not hold the target {self.UNKNOWN}."
            for extra in ([], ["--json"]):
                with self.subTest(json=bool(extra)):
                    code, shown, error = support.run_main(
                        context, "frozen", "show", self.UNKNOWN, *extra)
                    self.assertEqual(code, 1)
                    self.assertEqual(error, f"error: {message}\n")
                    if extra:
                        self.assertEqual(json.loads(shown)["error"]["code"],
                                         "target_not_found")
                    else:
                        self.assertEqual(shown, "")
            self.assertEqual(self._frozen(home), before)

    def test_freeze_keeps_the_document_without_its_differences(self) -> None:
        """A report with `--freeze` keeps as the frozen report its JSON document — the
        command, the warnings and the configuration errors, the figures, the record, and
        the identifier — without `differences` and without `changed`; its differences are
        computed against the frozen reports that exist before the freeze, so they equal
        those of the run without `--freeze` and never compare with the file being written;
        with `--json` and no older frozen report the output is the document of the file;
        the text ends with the line of the identifier (command-line.md › Frozen reports)."""
        one, two = (support.FIXTURE_DAY_ONE.isoformat(), support.FIXTURE_DAY_TWO.isoformat())
        with support.TemporaryFolder() as home:
            context = support.fixture_store("frozen_period", home)
            words = ["report", "timesheet", "--from", one, "--to", two]
            code, shown, error = support.run_main(context, *words, "--json")
            self.assertEqual(code, 0, error)
            before = json.loads(shown)
            self.assertEqual(len(before["differences"]), 8)  # against the older report
            # an hour later, so that the new frozen report is the latest of its days
            later = context._replace(now=support.FIXTURE_NOW + timedelta(hours=1))
            code, shown, error = support.run_main(
                later, *words, "--freeze", "--note", "Sent again", "--json")
            self.assertEqual(code, 0, error)
            document = json.loads(shown)
            frozen_id = support.FIXTURE_FIRST_UID
            self.assertEqual(document["frozen_id"], frozen_id)
            envelope = json.loads(self._file(home, frozen_id).read_text(encoding="utf-8"))
            self.assertEqual(list(envelope), ["document", "note", "frozen_at"])
            self.assertEqual(envelope["note"], "Sent again")
            self.assertEqual(envelope["frozen_at"], "2026-11-24T13:00:00.000Z")
            kept = envelope["document"]
            self.assertEqual(set(kept), {"command", "warnings", "configuration_errors",
                                         "record", "days", "frozen_id"})
            self.assertEqual(kept["command"], "report timesheet")
            self.assertEqual(kept["warnings"], [])
            self.assertEqual(kept["configuration_errors"], [])
            self.assertEqual(kept["days"][0]["day"], one)
            self.assertEqual(kept["record"]["parameters"]["language"], "en")
            self.assertNotIn("differences", kept)
            self.assertNotIn("changed", kept)
            # the output is the document of the file, then the two lists, then the keys
            # of the envelope
            self.assertEqual({key: document[key] for key in kept}, kept)
            self.assertEqual(list(document)[:2], ["days", "record"])
            self.assertEqual(list(document)[-3:], ["command", "warnings",
                                                  "configuration_errors"])
            self.assertEqual(document["differences"], before["differences"])
            self.assertEqual(document["changed"], before["changed"])
            # a later report compares with the file just written, which equals now
            code, shown, error = support.run_main(context, *words, "--json")
            self.assertEqual(code, 0, error)
            after = json.loads(shown)
            self.assertEqual((after["differences"], after["changed"]), ([], []))
        for extra in ([], ["--json"]):
            with self.subTest(json=bool(extra)), support.TemporaryFolder() as home:
                context = support.fixture_store("measured_day", home)
                day = support.FIXTURE_DAY_ONE.isoformat()
                code, shown, error = support.run_main(
                    context, "report", "day", day, "--freeze", *extra)
                self.assertEqual(code, 0, error)
                self.assertEqual(error, "")
                frozen_id = support.FIXTURE_FIRST_UID
                envelope = json.loads(self._file(home, frozen_id).read_text(
                    encoding="utf-8"))
                self.assertEqual(list(envelope), ["document", "frozen_at"])
                if extra:  # no older frozen report: the output is the document of the file
                    self.assertEqual(json.loads(shown), envelope["document"])
                else:
                    self.assertEqual(shown.rstrip("\n").split("\n")[-1],
                                     f"Frozen report  {frozen_id}")

    def test_a_frozen_file_that_the_ledger_cannot_read_stops_every_reader(self) -> None:
        """A file of a frozen report that is not JSON, that is no JSON object, that holds
        no `document` object, whose document holds no `command` or no `record`, or that
        holds no instant as `frozen_at`, and a file whose envelope is well-formed and whose
        document no reader can use — no day, a `days` that is not a list, a day without
        `day`, a key that the command always writes absent, a duration or a part of the
        record in another kind — stops `report timesheet`, `report day`, `frozen list`,
        and `frozen show` with the exit code 1 and one `error:` line that names the file,
        before any write; then `frozen remove` removes the damaged file, which it reads
        never, the four commands complete, and the healthy frozen report beside it stays
        (command-line.md › Frozen reports, › Exit codes)."""
        one = support.FIXTURE_DAY_ONE.isoformat()
        instant = "2026-11-24T12:00:00.000Z"
        document = {"command": "report day", "record": {}, "day": one}
        damages = {
            "not JSON": b"not a frozen report",
            "no text": b"\xff\xfe\x00",
            "no object": b"[]",
            "no document": json.dumps({"frozen_at": instant}).encode("utf-8"),
            "a document that is no object": json.dumps(
                {"document": [], "frozen_at": instant}).encode("utf-8"),
            "no command": json.dumps({"document": {"record": {}, "day": one},
                                      "frozen_at": instant}).encode("utf-8"),
            "a command that is no text": json.dumps({"document": {"command": 3, "record": {}},
                                                     "frozen_at": instant}).encode("utf-8"),
            "no record": json.dumps({"document": {"command": "report day"},
                                     "frozen_at": instant}).encode("utf-8"),
            "a record that is no object": json.dumps({"document": {"command": "report day",
                                                                   "record": []},
                                                      "frozen_at": instant}).encode("utf-8"),
            "no frozen_at": json.dumps({"document": document}).encode("utf-8"),
            "a frozen_at that is no instant": json.dumps(
                {"document": document, "frozen_at": "yesterday"}).encode("utf-8"),
            "a frozen_at without offset": json.dumps(
                {"document": document, "frozen_at": "2026-11-24T12:00:00"}).encode("utf-8"),
        }
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            code, shown, error = support.run_main(
                context, "report", "day", one, "--freeze", "--note", "Kept", "--json")
            self.assertEqual(code, 0, error)
            real = json.loads(shown)  # the document of the file of the healthy report
            healthy = real["frozen_id"]
            record = real["record"]
            # the damages of the document: the envelope is well-formed, the document is the
            # real one with one change that a reader cannot use
            damages.update({
                "no day": json.dumps({"document": {"command": "report timesheet",
                                                   "record": record, "days": []},
                                      "frozen_at": instant}).encode("utf-8"),
                "a days that is not a list": json.dumps(
                    {"document": {"command": "report timesheet", "record": record,
                                  "days": "abc"}, "frozen_at": instant}).encode("utf-8"),
                "a day without day": json.dumps(
                    {"document": {"command": "report timesheet", "record": record,
                                  "days": [{"total": 1}]}, "frozen_at": instant},
                    ).encode("utf-8"),
                "a required key absent": json.dumps(
                    {"document": {key: value for key, value in real.items()
                                  if key != "person"}, "frozen_at": instant},
                    ).encode("utf-8"),
                "a duration in another kind": json.dumps(
                    {"document": {**real, "person": {**real["person"], "human_time": "60"}},
                     "frozen_at": instant}).encode("utf-8"),
                "a part of the record in another kind": json.dumps(
                    {"document": {**real, "record": {**record, "parameters": []}},
                     "frozen_at": instant}).encode("utf-8"),
            })
            damaged = self.UNKNOWN
            path = self._file(home, damaged)
            path.parent.mkdir(parents=True, exist_ok=True)
            named = f"frozen/{support.FIXTURE_MACHINE}/{damaged}.json"
            text = (f"The file {named} of a frozen report is not readable; remove it"
                    " with frozen remove.")
            line = f"error: {text}\n"
            readers = (("report", "timesheet", "--from", one, "--to", one),
                       ("report", "day", one), ("frozen", "list"), ("frozen", "show", healthy))
            for name, content in damages.items():
                with self.subTest(damage=name):
                    path.write_bytes(content)
                    for words in readers:
                        with self.subTest(command=" ".join(words)):
                            code, shown, error = support.run_main(context, *words)
                            self.assertEqual(code, 1)
                            self.assertEqual(shown, "")  # no table before the stop
                            self.assertEqual(error, line)
                            code, shown, error = support.run_main(context, *words, "--json")
                            self.assertEqual(code, 1)
                            self.assertEqual(json.loads(shown)["error"], {
                                "code": "frozen_report_unreadable", "values": {"path": named},
                                "message": text})
                            self.assertEqual(error, line)
                    code, shown, error = support.run_main(
                        context, "report", "day", one, "--freeze", "--language", "it")
                    self.assertEqual(code, 1)
                    self.assertEqual(shown, "")
                    self.assertEqual(error, "error: Il file " + named + " di un report"
                                     " congelato non è leggibile; rimuoverlo con frozen"
                                     " remove.\n")
                    self.assertEqual(self._frozen(home),
                                     [(support.FIXTURE_MACHINE, healthy),
                                      (support.FIXTURE_MACHINE, damaged)])
            code, shown, error = support.run_main(context, "frozen", "remove", damaged)
            self.assertEqual(code, 0, error)
            self.assertEqual(shown, f"Id: {damaged}\n")
            self.assertFalse(path.exists())
            for words in readers:
                code, shown, error = support.run_main(context, *words)
                self.assertEqual(code, 0, error)
            self.assertEqual(self._frozen(home), [(support.FIXTURE_MACHINE, healthy)])

    def test_a_frozen_file_that_the_operating_system_refuses_stops_every_reader(
            self) -> None:
        """A file of a frozen report that the operating system refuses to give stops the
        four readers as a damaged file does: the exit code 1 and one `error:` line that
        names the file, in both modes and in Italian too, before any write; only that file
        is refused, and the healthy frozen report beside it stays (command-line.md › Frozen
        reports, › Exit codes)."""
        one = support.FIXTURE_DAY_ONE.isoformat()
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            code, shown, error = support.run_main(
                context, "report", "day", one, "--freeze", "--json")
            self.assertEqual(code, 0, error)
            healthy = json.loads(shown)["frozen_id"]
            refused = self.UNKNOWN
            path = self._file(home, refused)
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(self._file(home, healthy), path)  # a well-formed file
            named = f"frozen/{support.FIXTURE_MACHINE}/{refused}.json"
            text = (f"The file {named} of a frozen report is not readable; remove it"
                    " with frozen remove.")
            line = f"error: {text}\n"
            readers = (("report", "timesheet", "--from", one, "--to", one),
                       ("report", "day", one), ("frozen", "list"),
                       ("frozen", "show", healthy))
            read_text = Path.read_text

            def refusing(source, *arguments, **keywords):
                """The read of every text file but the one that the operating system
                refuses."""
                if source.parent.parent.name == "frozen" and source.stem == refused:
                    raise PermissionError(13, "The process cannot access the file")
                return read_text(source, *arguments, **keywords)

            with mock.patch.object(Path, "read_text", refusing):
                for words in readers:
                    with self.subTest(command=" ".join(words)):
                        code, shown, error = support.run_main(context, *words)
                        self.assertEqual(code, 1)
                        self.assertEqual(shown, "")
                        self.assertEqual(error, line)
                        code, shown, error = support.run_main(context, *words, "--json")
                        self.assertEqual(code, 1)
                        self.assertEqual(json.loads(shown)["error"], {
                            "code": "frozen_report_unreadable", "values": {"path": named},
                            "message": text})
                        self.assertEqual(error, line)
                code, shown, error = support.run_main(
                    context, "report", "day", one, "--freeze", "--language", "it")
                self.assertEqual(code, 1)
                self.assertEqual(shown, "")
                self.assertEqual(error, "error: Il file " + named + " di un report"
                                 " congelato non è leggibile; rimuoverlo con frozen"
                                 " remove.\n")
            self.assertEqual(self._frozen(home),
                             [(support.FIXTURE_MACHINE, healthy),
                              (support.FIXTURE_MACHINE, refused)])

    def test_freeze_keeps_the_warnings_with_their_messages(self) -> None:
        """The file of a frozen report holds the warnings of its report with their messages:
        on a day whose manual entry overlaps measured human time, the document of the file
        holds the warning with its code, its values, and its text in the language of the
        output, and no configuration error (command-line.md › Frozen reports, › JSON
        documents)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("manual_entries", home)
            one = support.FIXTURE_DAY_ONE.isoformat()
            message = (f"The manual entry {support.build_uid(1)} overlaps measured human"
                       " time.")
            for words in (("report", "timesheet", "--from", one, "--to", one),
                          ("report", "day", one)):
                with self.subTest(command=" ".join(words)):
                    code, shown, error = support.run_main(
                        context, *words, "--freeze", "--json")
                    self.assertEqual(code, 0, error)
                    envelope = json.loads(self._file(
                        home, json.loads(shown)["frozen_id"]).read_text(encoding="utf-8"))
                    self.assertEqual(envelope["document"]["warnings"], [{
                        "code": "manual_entry_overlap",
                        "values": {"event_uid": support.build_uid(1)},
                        "message": message}])
                    self.assertEqual(envelope["document"]["configuration_errors"], [])

    def test_frozen_show_of_an_action_this_version_does_not_know_exits_1(self) -> None:
        """A frozen report whose document names a command that this version of the ledger
        does not know, as a file that a newer version wrote on another machine: `frozen
        show` stops with the exit code 1 in both modes and names the report and the
        command; the reports compare it as a frozen report of another command, on the
        figures that both documents hold, and complete; `frozen list` names its command
        (command-line.md › Frozen reports)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            one = support.FIXTURE_DAY_ONE.isoformat()
            code, shown, error = support.run_main(
                context, "report", "timesheet", "--from", one, "--to", one, "--freeze",
                "--json")
            self.assertEqual(code, 0, error)
            frozen_id = json.loads(shown)["frozen_id"]
            path = self._file(home, frozen_id)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["document"]["command"] = "report week"  # as a newer version wrote it
            path.write_text(json.dumps(envelope, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
            text = (f"The frozen report {frozen_id} comes from the command report week,"
                    " which this version of the ledger does not know.")
            for extra in ([], ["--json"]):
                with self.subTest(json=bool(extra)):
                    code, shown, error = support.run_main(
                        context, "frozen", "show", frozen_id, *extra)
                    self.assertEqual(code, 1)
                    self.assertEqual(error, f"error: {text}\n")
                    if extra:
                        self.assertEqual(json.loads(shown)["error"], {
                            "code": "frozen_command_unknown",
                            "values": {"id": frozen_id, "command": "report week"},
                            "message": text})
                    else:
                        self.assertEqual(shown, "")
            code, shown, error = support.run_main(
                context, "report", "timesheet", "--from", one, "--to", one, "--json")
            self.assertEqual(code, 0, error)
            document = json.loads(shown)
            self.assertEqual(document["differences"], [])  # the figures that both hold
            self.assertEqual(document["changed"], [])
            code, shown, error = support.run_main(context, "frozen", "list", "--json")
            self.assertEqual(code, 0, error)
            self.assertEqual([row["report"] for row in json.loads(shown)["frozen"]],
                             ["report week"])

    def test_frozen_remove_of_the_file_of_another_machine_exits_1(self) -> None:
        """Only the machine that wrote a frozen report removes it: on another machine
        `frozen remove` stops with the exit code 1, names the machine in both modes, and
        the file stays (command-line.md › Frozen reports)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("measured_day", home)
            day = support.FIXTURE_DAY_ONE.isoformat()
            code, shown, error = support.run_main(
                context, "report", "day", day, "--freeze", "--json")
            self.assertEqual(code, 0, error)
            frozen_id = json.loads(shown)["frozen_id"]
            kept = support.fixture_store_folder(home) / "frozen" / OTHER_MACHINE
            kept.mkdir(parents=True)
            path = self._file(home, frozen_id)
            path.rename(kept / path.name)  # the file-sync service brought it over
            text = (f"The frozen report {frozen_id} was written by the machine"
                    f" {OTHER_MACHINE}; only that machine removes it.")
            for extra in ([], ["--json"]):
                with self.subTest(json=bool(extra)):
                    code, shown, error = support.run_main(
                        context, "frozen", "remove", frozen_id, *extra)
                    self.assertEqual(code, 1)
                    self.assertEqual(error, f"error: {text}\n")
                    if extra:
                        self.assertEqual(json.loads(shown)["error"]["values"],
                                         {"id": frozen_id, "machine": OTHER_MACHINE})
                    else:
                        self.assertEqual(shown, "")
            self.assertEqual(self._frozen(home), [(OTHER_MACHINE, frozen_id)])

    def test_frozen_list_computes_no_figure(self) -> None:
        """`frozen list` reads the names, the commands, the periods, the notes, the
        machines, and the instants of the frozen reports and computes no figure: the
        selection of a report never runs, and the command completes with the exit code 0
        (command-line.md › Commands)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("frozen_period", home)
            with mock.patch.object(figures, "select",
                                   side_effect=AssertionError("a figure was computed")):
                code, shown, error = support.run_main(context, "frozen", "list")
            self.assertEqual(code, 0, error)
            self.assertEqual(shown.splitlines()[0], "Frozen reports")

    def test_frozen_show_is_a_report_for_its_warnings_and_its_exit_code(self) -> None:
        """`frozen show` writes the warnings and the configuration errors of the figures
        of now to the standard error before its text, carries them in its envelope, and
        completes with the exit code 3 when a figure is incomplete (command-line.md ›
        Output, › Exit codes)."""
        with support.TemporaryFolder() as home:
            context = support.fixture_store("manual_entries", home)
            one = support.FIXTURE_DAY_ONE.isoformat()
            code, shown, error = support.run_main(
                context, "report", "day", one, "--freeze", "--json")
            self.assertEqual(code, 0, error)
            frozen_id = json.loads(shown)["frozen_id"]
            message = (f"The manual entry {support.build_uid(1)} overlaps measured human"
                       " time.")
            code, log = traced(context, ["frozen", "show", frozen_id])
            self.assertEqual(code, 0)
            streams = [stream for stream, text in log if text.strip()]
            self.assertEqual(streams[0], "stderr")  # the lines come before the text
            self.assertEqual("".join(text for stream, text in log if stream == "stderr"),
                             f"warning: {message}\n")
            self.assertEqual(streams.count("stdout"), 1)
            code, shown, error = support.run_main(
                context, "config", "add", "project", "--id", "gamma", "--name", "Alpha",
                "--json")
            self.assertEqual(code, 0, error)
            conflict = ("The person configuration gives one name to two project"
                        " identifiers: alpha and gamma.")
            code, shown, error = support.run_main(
                context, "frozen", "show", frozen_id, "--json")
            self.assertEqual(code, 3)
            self.assertEqual([held["code"]
                              for held in json.loads(shown)["configuration_errors"]],
                             ["project_name_conflict"])
            code, shown, error = support.run_main(context, "frozen", "show", frozen_id)
            self.assertEqual(code, 3)
            self.assertEqual(error, f"warning: {message}\nerror: {conflict}\n")


class TestPurgeActions(unittest.TestCase):
    """The action of `purge`: the keys that `--key` names, or of every kind but `purge`
    that a writer version under `--writer-version-below` wrote, leave the store once the
    command has written the purge with `--yes` or the consent of the person
    (command-line.md › Purge; ADR 0008, ADR 0015)."""

    def _world_with_session(self, base: Path) -> tuple[World, Context]:
        """A set-up world whose store holds one ingested session of Claude Code, and the
        context that ingested it."""
        world = build_world(base)
        logs = world.home / ".claude" / "projects"
        write_session(world, logs)
        set_up(world, world.store, recorded=str(world.store), logs=[logs])
        context = build_context(world)
        run_action(world, ["ingest", "--json"], context)
        return world, context

    def _prompt_key(self) -> str:
        """The event key of the prompt of the session, as its JSON object."""
        return '{"source": "claude-code-jsonl", "native_id": "%s"}' % UUID_ONE

    def test_purge_by_key_and_by_writer_version(self) -> None:
        """A purge by key removes the keys that the command line names, in the order they
        are typed, and a purge by writer version removes every key of the source whose
        winning copy a version under the one given wrote; the purge event holds the keys
        and its reason, and holds no corrected version and no sessions without one
        (command-line.md › Purge; event-schema.md › Fields)."""
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            _, shown, _ = run_action(world, [
                "annotate", "--from", "2026-11-20T10:00", "--to", "2026-11-20T11:00",
                "--project", "p", "--json"], context)
            annotated = json.loads(shown)["event_uid"]
            code, shown, error = run_action(world, [
                "purge", "--key", annotated, "--key", self._prompt_key(),
                "--reason", "content", "--yes", "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["command"], "purge")
            self.assertEqual(envelope["warnings"], [])
            self.assertEqual(envelope["configuration_errors"], [])
            self.assertEqual(envelope["keys"], [
                {"source": "ledger", "event_uid": annotated},
                {"source": "claude-code-jsonl", "native_id": UUID_ONE},
            ])
            self.assertEqual(envelope["keys_without_source"], [])
            self.assertIs(envelope["written"], True)
            [purge] = [one for one in stored_events(world) if one["kind"] == "purge"]
            self.assertEqual(purge["purged_keys"], envelope["keys"])
            self.assertEqual(purge["purge_reason"], "content")
            self.assertNotIn("corrected_version", purge)
            self.assertNotIn("purged_sessions", purge)
            self.assertEqual(purge["actor"], "human")
            self.assertEqual(purge["machine"], MACHINE)
            self.assertEqual(purge["timestamp"], "2026-11-24T12:00:00.000Z")
            self.assertEqual(purge["writer_version"], VERSION)
            self.assertEqual([one["kind"] for one in stored_events(world)], ["purge"])
            code, shown, error = run_action(world, ["purge", "--key", annotated,
                                                    "--reason", "forget", "--yes"],
                                             context)
            self.assertEqual(code, 0, error)
            self.assertTrue(shown.startswith("Keys\n"))
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            code, shown, error = run_action(world, [
                "purge", "--writer-version-below", "9.0.0", "--source",
                "claude-code-jsonl", "--reason", "correction", "--yes", "--json"],
                context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["keys"],
                             [{"source": "claude-code-jsonl", "native_id": UUID_ONE}])
            self.assertIs(envelope["written"], True)
            self.assertEqual([one["kind"] for one in stored_events(world)], ["purge"])

    def test_purge_by_writer_version_without_a_key_writes_nothing(self) -> None:
        """A selection by writer version that holds no key writes nothing and asks
        nobody: the command completes with the warning `no_key_selected`, its document
        keeps `keys`, `keys_without_source`, and `written` false, and its text is the
        one of a purge that wrote nothing (command-line.md › Purge, › JSON documents)."""
        words = ["purge", "--writer-version-below", "0.1.0", "--reason", "forget"]
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            code, shown, error = run_action(world, [*words, "--yes", "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["command"], "purge")
            self.assertEqual(envelope["keys"], [])
            self.assertEqual(envelope["keys_without_source"], [])
            self.assertIs(envelope["written"], False)
            self.assertEqual(envelope["configuration_errors"], [])
            self.assertEqual(envelope["warnings"], [{
                "code": "no_key_selected", "values": {},
                "message": "The selection holds no key: there is nothing to purge.",
            }])
            self.assertEqual([one["kind"] for one in stored_events(world)], ["prompt"])
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            asked: list[str] = []

            def person(question: str, asked: list[str] = asked) -> str:
                asked.append(question)
                return "yes"

            code, shown, error = run_action(world, [*words, "--json"],
                                            context._replace(ask=person))
            self.assertEqual(code, 0, error)
            self.assertEqual(asked, [])
            self.assertIs(json.loads(shown)["written"], False)
            self.assertEqual([one["kind"] for one in stored_events(world)], ["prompt"])
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            code, shown, error = run_action(world, [*words, "--yes"], context)
            self.assertEqual(code, 0, error)
            self.assertEqual(shown, "Keys\nWritten: no\n")
            self.assertEqual(
                error,
                "warning: The selection holds no key: there is nothing to purge.\n")

    def test_purge_needs_yes_without_terminal(self) -> None:
        """Without a terminal on the standard input the command asks nobody and writes
        nothing; with one, the answer of the person decides, and an empty answer counts as
        a refusal (command-line.md › Output, › Purge)."""
        words = ["purge", "--writer-version-below", "9.0.0", "--reason", "forget"]
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            code, shown, error = run_action(world, [*words, "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertIs(envelope["written"], False)
            self.assertEqual(envelope["warnings"], [])
            self.assertEqual(envelope["keys"],
                             [{"source": "claude-code-jsonl", "native_id": UUID_ONE}])
            self.assertEqual([one["kind"] for one in stored_events(world)], ["prompt"])
        for answer, written in (("yes", True), ("sì", True), ("no", False), ("", False)):
            with self.subTest(answer=answer):
                with support.TemporaryFolder() as base:
                    world, context = self._world_with_session(base)
                    asked: list[str] = []

                    def person(question: str, asked: list[str] = asked,
                               answer: str = answer) -> str:
                        asked.append(question)
                        return answer

                    code, shown, error = run_action(
                        world, [*words, "--json"], context._replace(ask=person))
                    self.assertEqual(code, 0, error)
                    self.assertEqual(asked, [language.question("purge_consent", "en")])
                    self.assertIs(json.loads(shown)["written"], written)
                    kinds = [one["kind"] for one in stored_events(world)]
                    self.assertEqual("purge" in kinds, written)

    def test_purge_forget_with_corrected_version_exits_2(self) -> None:
        """`--corrected-version` is not accepted with `--reason forget` (ADR 0015): the
        command stops with `conflicting_arguments` and writes nothing."""
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            before = stored_events(world)
            code, shown, error = run_action(world, [
                "purge", "--writer-version-below", "9.0.0", "--reason", "forget",
                "--corrected-version", "9.0.0", "--yes", "--json"], context)
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(shown)["error"], {
                "code": "conflicting_arguments",
                "values": {"command": "purge",
                           "arguments": ["--reason forget", "--corrected-version"]},
                "message": "The command purge does not take --reason forget,"
                           " --corrected-version together.",
            })
            self.assertEqual(stored_events(world), before)  # nothing is written

    def test_purge_by_key_with_a_source_exits_2(self) -> None:
        """`--source` narrows a selection by writer version alone (command-line.md ›
        Purge): beside `--key` it stops the command with `conflicting_arguments`, which
        names both, in both modes and in the language of the output, before the guards of
        an action that writes, so a development version stops the same way; nothing is
        written."""
        values = {"command": "purge", "arguments": ["--key", "--source"]}
        words = ["purge", "--key", self._prompt_key(), "--source", "claude-code-jsonl",
                 "--reason", "content", "--yes"]
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            before = stored_events(world)
            environ = {key: value for key, value in world.environ.items()
                       if key != DEVELOPMENT_VARIABLE}
            for chosen in language.LANGUAGES:
                wanted = language.message("conflicting_arguments", values, chosen)
                for held in (context, build_context(world, version=DEV_VERSION,
                                                    environ=environ)):
                    with self.subTest(language=chosen, version=held.version):
                        code, shown, error = run_action(
                            world, [*words, "--language", chosen, "--json"], held)
                        self.assertEqual((code, error), (2, f"error: {wanted}\n"))
                        self.assertEqual(json.loads(shown)["error"], {
                            "code": "conflicting_arguments", "values": values,
                            "message": wanted})
                        code, shown, error = run_action(
                            world, [*words, "--language", chosen], held)
                        self.assertEqual((code, shown, error), (2, "", f"error: {wanted}\n"))
            self.assertEqual(stored_events(world), before)  # nothing is written

    def test_purge_warns_key_source_gone(self) -> None:
        """The command warns once for each source that a selected key names and that no
        folder of native logs feeds any more, holds those keys in
        `keys_without_source`, and completes (command-line.md › Purge, › JSON documents;
        event-schema.md › Keys and invariants)."""
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            code, shown, error = run_action(world, [
                "purge", "--key", '{"source": "invented-source", "native_id":'
                                 ' "invented-record"}',
                "--key", '{"source": "invented-source", "session_id": "invented",'
                         ' "event_uid": "invented"}',
                "--key", "invented-uid", "--reason", "forget", "--yes", "--json"],
                context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["keys_without_source"], [
                {"source": "invented-source", "native_id": "invented-record"},
                {"source": "invented-source", "session_id": "invented",
                 "event_uid": "invented"},
            ])
            self.assertEqual([warning["code"] for warning in envelope["warnings"]],
                             ["purged_key_source_gone"])
            self.assertEqual(envelope["warnings"][0]["values"],
                             {"source": "invented-source"})
            self.assertEqual(
                error, "warning: A purged key names the source invented-source, which no"
                       " longer exists.\n")
            self.assertIs(envelope["written"], True)

    def test_purge_with_corrected_version_names_sessions(self) -> None:
        """A purge with a corrected version also names the sessions that hold its keys, so
        every machine knows which sessions to read again once its own writer version
        reaches the corrected version (event-schema.md › Fields; ADR 0015)."""
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            code, shown, error = run_action(world, [
                "purge", "--key", self._prompt_key(), "--reason", "correction",
                "--corrected-version", "0.2.0", "--yes", "--json"], context)
            self.assertEqual(code, 0, error)
            self.assertIs(json.loads(shown)["written"], True)
            [purge] = [one for one in stored_events(world) if one["kind"] == "purge"]
            self.assertEqual(purge["corrected_version"], "0.2.0")
            self.assertEqual(purge["purged_sessions"],
                             [{"tool": "claude-code", "session_id": "session-one"}])

    def test_purge_names_the_sessions_of_more_keys_than_one_statement_takes(self) -> None:
        """A purge with a corrected version names the sessions of every key it lists, also
        when the keys are more than the placeholders one SQL statement takes: the lookup
        of the sessions runs in chunks like the other chunked read of the index, so the
        purge of a store that holds 33 000 keys below the version completes instead of
        stopping in a raw traceback of the SQL engine (command-line.md › Purge; ADR 0015).
        The store holds events that the real store writer wrote, with invented text."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            context = build_context(world)
            count = 33_000
            below = [
                {
                    "schema_version": 1,
                    "source": "claude-code-jsonl",
                    "native_id": f"3f1c0000-0000-4000-8000-{number:012d}",
                    "session_id": f"session-{number % 7}",
                    "event_uid": f"7f1c0000-0000-4000-8000-{number:012d}",
                    "timestamp": "2026-11-20T09:15:00.000Z",
                    "writer_version": "0.1.0",
                    "actor": "agent",
                    "kind": "tool_call",
                    "machine": MACHINE,
                    "tool": "claude-code",
                }
                for number in range(count)]
            store.append_events(world.store, MACHINE, below, NOW)
            code, shown, error = run_action(world, [
                "purge", "--writer-version-below", "0.2.0", "--reason", "correction",
                "--corrected-version", "0.2.0", "--yes", "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(len(envelope["keys"]), count)
            self.assertEqual(envelope["keys_without_source"], [])
            [purge] = [one for one in stored_events(world) if one["kind"] == "purge"]
            self.assertEqual(purge["corrected_version"], "0.2.0")
            self.assertEqual(purge["purged_sessions"],
                             [{"tool": "claude-code", "session_id": f"session-{number}"}
                              for number in range(7)])
            self.assertEqual([one["kind"] for one in stored_events(world)], ["purge"])

    def test_purge_completes_on_a_store_whose_line_breaks_the_encoding(self) -> None:
        """A line that is a JSON object with every required field, whose typed columns the
        table of the encoding does not shape — here a `writer_version` that is a whole
        number — is a broken line: it never enters the index as an event, and a purge of
        the store completes instead of dying in a raw traceback on the version of such an
        event (event-schema.md › Encoding; ingestion.md › Store). The store holds one
        valid event of the same session, written by hand with invented text."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            context = build_context(world)
            segment = world.store / "segments" / MACHINE / "2026-11.jsonl"
            segment.parent.mkdir(parents=True)

            def line(fields: dict) -> str:
                return json.dumps(fields, sort_keys=True, separators=(",", ":"))

            valid = {
                "schema_version": 1,
                "source": "claude-code-jsonl",
                "session_id": "session-one",
                "event_uid": "7f1c0000-0000-4000-8000-0000000000b1",
                "timestamp": "2026-11-20T09:15:00.000Z",
                "ingested_at": "2026-11-20T09:15:00.000Z",
                "writer_version": "0.1.0",
                "actor": "agent",
                "kind": "tool_call",
                "machine": MACHINE,
                "tool": "claude-code",
            }
            probed = {**valid, "event_uid": "7f1c0000-0000-4000-8000-0000000000b2",
                      "writer_version": 1}
            segment.write_text(f"{line(valid)}\n{line(probed)}\n", encoding="utf-8")
            code, shown, error = run_action(world, [
                "purge", "--writer-version-below", "9.0.0", "--reason", "correction",
                "--corrected-version", "9.0.0", "--yes", "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["warnings"], [])
            self.assertEqual(envelope["keys"],
                             [{"source": "claude-code-jsonl", "session_id": "session-one",
                               "event_uid": valid["event_uid"]}])
            self.assertEqual([one["kind"] for one in stored_events(world)], ["purge"])
            lines = list(store.read_lines(world.store,
                                          f"segments/{MACHINE}/2026-11.jsonl"))
            # the rewrite of the purge keeps the broken line in its place, and the purge
            # event, appended before the rewrite, follows it
            self.assertEqual([events.decode_line(one.data).state for one in lines],
                             ["broken", "event"])

    def test_purge_takes_the_lock(self) -> None:
        """`purge` takes the lock of the machine and the store, and refuses a development
        version that the environment does not let write, before the lock
        (architecture.md › Concurrency, › Runtime)."""
        original = platform.StoreLock.__enter__

        def recording(taker: platform.StoreLock, takes: list[str]) -> platform.StoreLock:
            takes.append(str(taker.path))
            return original(taker)

        words = ["purge", "--key", self._prompt_key(), "--reason", "forget", "--yes"]
        with self.subTest(action="purge"):
            with support.TemporaryFolder() as base:
                world, context = self._world_with_session(base)
                lock = (world.machine / "stores" /
                        platform.store_identifier(world.store, SYSTEM) / "lock")
                takes: list[str] = []
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(platform.StoreLock, "__enter__",
                                       lambda taker, takes=takes: recording(taker,
                                                                            takes)):
                    with contextlib.redirect_stdout(stdout), \
                            contextlib.redirect_stderr(stderr):
                        code = main([*words, "--store", str(world.store), "--json"],
                                    context)
                self.assertEqual(code, 0, stderr.getvalue())
                self.assertTrue(takes)  # the lock was taken
                self.assertEqual(takes[0], str(lock))
        with self.subTest(action="purge refused"):
            with support.TemporaryFolder() as base:
                world, context = self._world_with_session(base)
                environ = {key: value for key, value in world.environ.items()
                           if key != DEVELOPMENT_VARIABLE}
                takes: list[str] = []
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(platform.StoreLock, "__enter__",
                                       lambda taker, takes=takes: recording(taker,
                                                                            takes)):
                    with contextlib.redirect_stdout(stdout), \
                            contextlib.redirect_stderr(stderr):
                        code = main([*words, "--store", str(world.store), "--json"],
                                    build_context(world, version=DEV_VERSION,
                                                  environ=environ))
                self.assertEqual(code, 1)
                envelope = json.loads(stdout.getvalue())
                self.assertEqual(envelope["error"]["code"], "development_version")
                self.assertEqual(takes, [])  # nothing is locked before the guard

    def test_purge_of_a_purge_exits_2(self) -> None:
        """A `--key` whose event is a purge stops the command with the exit code for wrong
        use: a purge cannot be undone, because the copies that it removed do not come
        back (command-line.md › Purge)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            set_up(world, world.store, recorded=str(world.store))
            machine = configuration.read_machine_configuration(world.machine).machine
            purge = events.ledger_event(
                "purge", "human", machine, NOW,
                {"purged_keys": [{"source": "ledger", "event_uid": "3f1c0000-0000-4000"
                                                 "-8000-0000000000c3"}],
                 "purge_reason": "forget"})
            store.append_events(world.store, machine, [purge], NOW)
            code, shown, error = run_action(world, [
                "purge", "--key", purge["event_uid"], "--reason", "forget", "--yes",
                "--json"])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(shown)["error"], {
                "code": "wrong_kind",
                "values": {"command": "purge", "event_uid": purge["event_uid"],
                           "kind": "purge"},
                "message": f"The command purge cannot act on the event"
                           f" {purge['event_uid']}: its kind is purge.",
            })
            self.assertEqual([one["kind"] for one in stored_events(world)],
                             ["purge"])  # nothing is written

    def test_purge_by_writer_version_leaves_a_purge_alone(self) -> None:
        """A selection by writer version holds no purge event: the command removes the keys
        of the events of every other kind that a version under the one given wrote, and the
        purge event that the store already holds stays, beside the purge that the command
        writes, because no purge removes a purge event (command-line.md › Purge)."""
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            machine = configuration.read_machine_configuration(world.machine).machine
            earlier = events.ledger_event(
                "purge", "human", machine, NOW,
                {"purged_keys": [{"source": "ledger", "event_uid": "3f1c0000-0000-4000"
                                                 "-8000-0000000000c3"}],
                 "purge_reason": "forget"})
            store.append_events(world.store, machine, [earlier], NOW)
            code, shown, error = run_action(world, [
                "purge", "--writer-version-below", "9.0.0", "--reason", "correction",
                "--corrected-version", "9.0.1", "--yes", "--json"], context)
            self.assertEqual(code, 0, error)
            envelope = json.loads(shown)
            self.assertEqual(envelope["keys"],
                             [{"source": "claude-code-jsonl", "native_id": UUID_ONE}])
            self.assertIs(envelope["written"], True)
            stored = stored_events(world)
            self.assertEqual([one["kind"] for one in stored], ["purge", "purge"])
            self.assertEqual(stored[0]["event_uid"], earlier["event_uid"])
            self.assertEqual(stored[0]["purge_reason"], "forget")
            self.assertEqual(stored[1]["purged_keys"], envelope["keys"])
            self.assertEqual(stored[1]["purge_reason"], "correction")
            self.assertEqual([one["kind"] for one in machine_segment(world, MACHINE)],
                             ["purge", "purge"])  # the copy of the prompt left the segment

    def test_purge_shows_keys_and_warnings_before_the_question(self) -> None:
        """At a terminal the person answers on what they see: the keys (in text mode) and
        the warning lines (in both modes) reach the streams before the question, and each
        line reaches the standard error once however the command ends (command-line.md ›
        Purge; event-schema.md › Keys and invariants)."""
        for as_json, answer, written in ((False, "no", False), (True, "no", False),
                                         (True, "yes", True)):
            with self.subTest(json=as_json, answer=answer):
                with support.TemporaryFolder() as base:
                    world, context = self._world_with_session(base)
                    words = ["purge", "--key", '{"source": "invented-source",'
                                             ' "native_id": "invented-record"}',
                             "--key", self._prompt_key(), "--reason", "forget"]
                    if as_json:
                        words.append("--json")
                    stdout, stderr = io.StringIO(), io.StringIO()
                    asked: list[tuple[str, str]] = []

                    def person(question: str) -> str:
                        asked.append((stdout.getvalue(), stderr.getvalue()))
                        return answer

                    with contextlib.redirect_stdout(stdout), \
                            contextlib.redirect_stderr(stderr):
                        code = main(words, context._replace(ask=person))
                    self.assertEqual(code, 0)
                    self.assertEqual(len(asked), 1)  # the question was asked once
                    at_ask_out, at_ask_err = asked[0]
                    self.assertEqual(
                        at_ask_err,
                        "warning: A purged key names the source invented-source, which"
                        " no longer exists.\n")
                    if not as_json:
                        self.assertTrue(at_ask_out.startswith("Keys\n"))
                        self.assertIn(UUID_ONE, at_ask_out)
                    else:
                        self.assertEqual(at_ask_out, "")  # the envelope comes after
                    self.assertEqual(stderr.getvalue().count("warning:"), 1)
                    if as_json:
                        self.assertIs(json.loads(stdout.getvalue())["written"], written)
                    else:
                        self.assertIn("Written: no" if not written else "Written: yes",
                                      stdout.getvalue())
                        self.assertEqual(stdout.getvalue().count("Keys\n"), 1)

    def test_purge_malformed_key_exits_2(self) -> None:
        """A malformed `--key` value stops the command with a wrong value that names the
        whole text the person typed, before anything is written (command-line.md › Purge):
        text that is not valid JSON where JSON is required, a JSON value that is no key
        object, a missing `source`, or an empty value."""
        for value in ('{', '{"source": "claude-code-jsonl"}',
                      '{"session_id": "invented", "event_uid": "invented"}',
                      '["invented"]', '',
                      '{"source": "ledger", "native_id": "invented", "event_uid":'
                      ' "invented"}',
                      '{"source": "claude-code-jsonl", "event_uid": "invented"}',
                      'null'):
            with self.subTest(value=value):
                with support.TemporaryFolder() as base:
                    world = build_world(base)
                    set_up(world, world.store, recorded=str(world.store))
                    code, shown, error = run_action(world, [
                        "purge", "--key", value, "--reason", "forget", "--yes",
                        "--json"])
                    self.assertEqual(code, 2)
                    self.assertEqual(json.loads(shown)["error"], {
                        "code": "wrong_value",
                        "values": {"key": "--key", "value": value},
                        "message": f"The value {value} is not valid for --key.",
                    })
                    self.assertEqual(stored_events(world), [])  # nothing is written

    def test_purge_removes_own_blocked_copies_at_once(self) -> None:
        """After it writes the purge, the command removes the copies that the purge blocks
        from the segments of its own machine before the command ends; the segment of
        another machine keeps its copy, which its own ingestion removes
        (command-line.md › Purge; architecture.md › Data flow, step 10)."""
        with support.TemporaryFolder() as base:
            world, context = self._world_with_session(base)
            copy = dict(machine_segment(world, MACHINE)[0])
            copy["machine"] = OTHER_MACHINE
            store.append_events(world.store, OTHER_MACHINE, [copy], NOW)
            code, shown, error = run_action(world, [
                "purge", "--key", self._prompt_key(), "--reason", "forget", "--yes",
                "--json"], context)
            self.assertEqual(code, 0, error)
            self.assertIs(json.loads(shown)["written"], True)
            self.assertEqual([one["kind"] for one in machine_segment(world, MACHINE)],
                             ["purge"])
            self.assertEqual([one["native_id"]
                              for one in machine_segment(world, OTHER_MACHINE)],
                             [UUID_ONE])  # the segment of the other machine is unchanged


class TestQuestions(unittest.TestCase):
    """A question of the ledger goes to the standard error, in the language of the output,
    and its answer is one line of the standard input, so the standard output holds the text
    or the JSON document of the command alone (command-line.md › Output)."""

    def _asked(self, answers: str, words: Sequence[str],
               context: Context) -> tuple[int, str, str]:
        """One command through `main` with the standard input holding `answers`: its exit
        code, its standard output, and its standard error."""
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                mock.patch("sys.stdin", io.StringIO(answers)):
            code = main(list(words), context)
        return code, stdout.getvalue(), stderr.getvalue()

    def _scheduler_calls_of_show(self, world: World) -> list[list[str]]:
        """The calls of the scheduler program that `schedule show` makes on the world: the
        calls of a command that shows the entry and creates none."""
        run = FakeRun()
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["schedule", "show"], build_context(world, run=run))
        self.assertEqual(code, 0)
        return run.calls

    def test_a_question_goes_to_the_standard_error(self) -> None:
        """The question of the running context reaches the standard error and nothing
        reaches the standard output; the answer is the line of the standard input without
        its end, and an end of the input is an empty answer, which every command reads as
        no answer."""
        for answers, wanted in (("Invented answer\n", "Invented answer"),
                                ("Invented answer", "Invented answer"), ("\n", ""),
                                ("", "")):
            with self.subTest(answers=answers):
                stdout, stderr = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr), \
                        mock.patch("sys.stdin", io.StringIO(answers)):
                    self.assertEqual(cli_ask("Invented question? [yes/no]"), wanted)
                self.assertEqual((stdout.getvalue(), stderr.getvalue()),
                                 ("", "Invented question? [yes/no]"))

    def test_setup_at_an_end_of_the_input_answers_nothing(self) -> None:
        """`setup` without `--schedule` and without `--label`, at a terminal whose input
        ends before its questions: both questions reach the standard error, and the command
        completes as with an empty answer to each — the exit code of the empty answers, no
        machine label written, the scheduled ingestion not created (command-line.md ›
        Setup, › Output)."""
        codes = {}
        for answers in ("\n\n", ""):
            with self.subTest(answers=answers), support.TemporaryFolder() as base:
                world = build_world(base)
                run = FakeRun()
                context = build_context(world, run=run)._replace(ask=cli_ask)
                codes[answers], _, error = self._asked(
                    answers, ["setup", "--store", str(world.store)], context)
                self.assertEqual(error, language.question("setup_label", "en")
                                 + language.question("setup_schedule", "en").format(
                                     time="12:00"))
                machine = configuration.read_machine_configuration(world.machine).machine
                self.assertEqual(store.machine_labels(world.store, [machine]), ({}, []))
                self.assertEqual(run.calls, self._scheduler_calls_of_show(world))
        self.assertEqual(codes[""], codes["\n\n"])

    def test_purge_at_an_end_of_the_input_writes_nothing(self) -> None:
        """A `purge` without `--yes` at a terminal whose input ends before its question:
        the question reaches the standard error, and the command completes as with an
        empty answer — the exit code of the empty answer, no purge written, the store as
        it was (command-line.md › Purge, › Output)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            write_session(world, logs)
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            context = build_context(world)
            run_action(world, ["ingest"], context)
            before = stored_events(world)
            codes = {}
            for answers in ("\n", ""):
                with self.subTest(answers=answers):
                    codes[answers], shown, error = self._asked(
                        answers, ["purge", "--key", PROMPT_KEY, "--reason", "forget",
                                  "--json"], context._replace(ask=cli_ask))
                    self.assertEqual(error, language.question("purge_consent", "en"))
                    self.assertIs(json.loads(shown)["written"], False)
                    self.assertEqual(stored_events(world), before)
            self.assertEqual(codes[""], codes["\n"])

    def test_purge_with_json_writes_the_document_alone(self) -> None:
        """A `purge --json` that asks through the question of the running context, with
        the standard input holding `yes`, writes the purge and the JSON document alone on
        the standard output; the question goes to the standard error."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            logs = world.home / ".claude" / "projects"
            write_session(world, logs)
            set_up(world, world.store, recorded=str(world.store), logs=[logs])
            context = build_context(world)
            run_action(world, ["ingest"], context)
            code, shown, error = self._asked(
                "yes\n", ["purge", "--key", PROMPT_KEY, "--reason", "forget", "--json"],
                context._replace(ask=cli_ask))
            self.assertEqual(code, 0, error)
            self.assertIs(json.loads(shown)["written"], True)
            self.assertEqual(error, language.question("purge_consent", "en"))
            self.assertIn("purge", [one["kind"] for one in stored_events(world)])

    def test_setup_asks_its_questions_in_the_language_of_the_output(self) -> None:
        """`setup` without `--schedule` and without `--label`, at a terminal and under
        `--language it`: each of its two questions reaches the standard error in Italian,
        the label first, and the command completes with the answers of the standard
        input — the label written, the scheduled ingestion refused (command-line.md ›
        Setup, › Output)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            run = FakeRun()
            context = build_context(world, run=run)._replace(ask=cli_ask)
            code, shown, error = self._asked(
                "Invented Machine\nno\n", ["setup", "--store", str(world.store),
                                           "--language", "it"], context)
            self.assertEqual(code, 0, error)
            self.assertEqual(error, language.question("setup_label", "it")
                             + language.question("setup_schedule", "it").format(time="12:00"))
            self.assertIn(f"{language.label('machine', 'it')}:", shown)
            machine = configuration.read_machine_configuration(world.machine).machine
            self.assertEqual(store.machine_labels(world.store, [machine]),
                             ({machine: "Invented Machine"}, []))
            self.assertEqual(run.calls, self._scheduler_calls_of_show(world))


if __name__ == "__main__":
    unittest.main()
