"""Tests of the setup module: the seven steps of setup in their order, the machine
configuration they write, the person configuration they create, the machine label, the
retention with its advice, the scheduled ingestion with the consent of the person, and the
first ingestion (command-line.md › Setup, ingestion.md › Frequency)."""

import contextlib
import json
import os
import shutil
import subprocess
import unittest
from collections.abc import Callable
from datetime import time
from pathlib import Path
from platform import system as running_system
from typing import NamedTuple
from unittest import mock

import support
from ai_effort_ledger import adapters, configuration, events, ingestion, platform, setup, store

SYSTEM = running_system()
"""The system of the machine that runs the tests; a test that names another system gives it
to the context."""
NOW = support.utc("2026-11-20T12:00")
"""The instant of every setup of the tests."""
SETTLE = 14400
"""The settle time of the person configuration that setup creates, in seconds."""
ZONE = "Etc/UTC"
"""The IANA time zone that the fixed `time_zone` of the context gives."""
VERSION = "0.1.0"
"""A release version of the ledger for the contexts of the tests."""
DEVELOPMENT_VERSION = "0.1.0.dev0"
"""A version with a development mark, which never creates the scheduler entry."""
EXECUTABLE = Path("D:/Work/Product/ai-effort-ledger")
"""The absolute path of the installed command, invented."""
INSTALLATION = "Installation-Identifier-2026"
"""The installation identifier that the contexts of the tests give."""
PROMPT_AT = "2026-11-19T09:15:00.000Z"
"""The instant that the prompt records of the tests hold."""
UUID_ONE = "3f1c0000-0000-4000-8000-0000000000a1"
UUID_TWO = "3f1c0000-0000-4000-8000-0000000000a2"
UUID_THREE = "3f1c0000-0000-4000-8000-0000000000a3"
UUID_FOUR = "3f1c0000-0000-4000-8000-0000000000a4"

_CREATED_BY = {"windows": "/Create", "launchd": "bootstrap", "systemd": "enable"}
"""The word of the call of each scheduler program that shows the entry was created; cron
holds no entry of the ledger, so there no call shows it."""
_SCHEDULER_PROGRAM = {"windows": "schtasks", "launchd": "launchctl", "systemd": "systemctl"}
"""The program whose name the `scheduler_failed` warning of each scheduler kind holds."""


class FakeRun:
    """A fake of the call of a scheduler program: it records every call and ends with its
    code, so no test reaches the scheduler of the machine that runs the tests. A `query`
    answer replaces the text a `/Query` of the Task Scheduler returns, which the ask for
    the existing entry reads."""

    def __init__(self, code: int = 0, query: str = "") -> None:
        self.code = code
        self.query = query
        self.calls: list[list[str]] = []

    def __call__(self, words: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(list(words))
        if "/Query" in words and self.query:
            return subprocess.CompletedProcess(words, 0, self.query, "")
        return subprocess.CompletedProcess(words, self.code, "stdout of the fake", "")


class World(NamedTuple):
    """The folders and the environment of one setup of the tests: the home of the person, the
    folder of native logs of Claude Code, the store folder of --store, the machine-local data
    folder as the setup computes it, and the environment the context gives."""

    home: Path
    logs: Path
    store: Path
    machine: Path
    environ: dict[str, str]


def counting_uids(start: int = 0) -> Callable[[], str]:
    """A maker of machine identifiers: each call gives the next invented identifier, so a
    test sees it when the machine identifier is made again."""
    counter = start

    def new_uid() -> str:
        nonlocal counter
        counter += 1
        return f"1a2b3c4d-0000-4000-8000-{counter:012d}"

    return new_uid


def test_environ(base: Path, **extra: str) -> dict[str, str]:
    """The environment of the tests: the local data folders of every system inside the
    temporary folder, and the variable that lets a development version write."""
    environ = {
        "AI_EFFORT_LEDGER_DEVELOPMENT": "1",
        "LOCALAPPDATA": str(base / "app-data"),
        "APPDATA": str(base / "roaming-data"),
        "XDG_STATE_HOME": str(base / "state"),
        "XDG_DATA_HOME": str(base / "share"),
    }
    environ.update(extra)
    return environ


def build_world(base: Path, system: str = SYSTEM, **environ_extra: str) -> World:
    """The world of a test: a home with its `.claude/projects` folder of native logs, and the
    machine-local data folder and store folder inside the temporary folder."""
    home = base / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    environ = test_environ(base, **environ_extra)
    machine = Path(platform.machine_folder(system, environ, home))
    return World(home, home / ".claude" / "projects", base / "store", machine, environ)


def build_context(
    world: World,
    run: Callable[[list[str]], subprocess.CompletedProcess] | None = None,
    ask: Callable[..., str] | None = None,
    time_zone: Callable[[], str | None] | None = None,
    version: str = VERSION,
    system: str = SYSTEM,
    new_uid: Callable[[], str] | None = None,
) -> setup.SetupContext:
    """The context of a test: a fake of the scheduler call when none is given, no ask (the
    standard input is no terminal), a fixed time zone, the adapters of the temporary home,
    and a maker of machine identifiers of its own when none is given."""
    return setup.SetupContext(
        system=system,
        environ=world.environ,
        home=world.home,
        now=NOW,
        executable=EXECUTABLE,
        run=run if run is not None else FakeRun(),
        installation=INSTALLATION,
        ask=ask,
        adapters=[support.adapters_for_tests(world.home)],
        time_zone=time_zone if time_zone is not None else (lambda: ZONE),
        new_uid=new_uid if new_uid is not None else counting_uids(),
        version=version,
        uid=501,
    )


def options_for(world: World, **overrides: object) -> setup.SetupOptions:
    """The options of a test: the store folder of the world, no label, no folder of native
    logs, the scheduled ingestion not asked for, at 12:00."""
    values: dict[str, object] = {
        "store": world.store, "label": None, "native_logs": [], "schedule": None, "time": "12:00"}
    values.update(overrides)
    return setup.SetupOptions(**values)


def write_prompt_session(logs: Path, home: Path, session_id: str, uuid_value: str) -> None:
    """Write one settled session that holds one prompt of the person into the folder of
    native logs, so that the first ingestion has an event to store."""
    support.write_session(
        logs, session_id, [support.prompt_record("Invented prompt text.", PROMPT_AT, uuid_value)],
        {}, home / "work")


def settle_logs(logs: Path) -> None:
    """Give every file of native logs a time of change two settle times before the instant
    of the tests, so that the reading takes every session as complete."""
    moment = NOW.timestamp() - 2 * SETTLE
    for path in logs.rglob("*.jsonl"):
        os.utime(path, (moment, moment))


def key_text(key: "events.EventKey") -> str:
    """The event key as one line of comparable text, its JSON with sorted keys."""
    return json.dumps(key.to_json(), sort_keys=True)


def complete_event_keys(world: World) -> list[str]:
    """The key of every complete event the native logs of the world hold, as the adapter
    reads them, in sorted order."""
    adapter = support.adapters_for_tests(world.home)
    reading = adapter.read_sessions(
        adapter.sessions("claude-code", world.logs),
        adapters.ReadContext("machine-of-the-reading", NOW, SETTLE, _without_owner))
    return sorted(key_text(events.event_key(event)) for event in reading.events)


def stored_event_keys(store_folder: Path) -> list[str]:
    """The key of every event the segments of the store folder hold, in sorted order."""
    found = []
    for name in store.segment_names(store_folder):
        for line in store.read_lines(store_folder, name):
            decoded = events.decode_line(line.data)
            if decoded.event is not None:
                found.append(key_text(events.event_key(decoded.event)))
    return sorted(found)


def entry_created(world: World, run: FakeRun, system: str = SYSTEM) -> bool:
    """Whether the setup of this run created the entry of the scheduled ingestion: the scheduler
    program received the create call of its kind (`_CREATED_BY`). Cron writes nothing, because its
    table of the person is one shared file, so there no test can observe the creation."""
    kind = platform.scheduler_kind(system, shutil.which)
    if kind == "cron":
        return False
    return any(_CREATED_BY[kind] in call for call in run.calls)


def intended_entry(world: World, time: str = "12:00") -> platform.SchedulerEntry:
    """The entry the scheduled ingestion would hold: the installed command with `ingest` and
    the store folder, once a day at the given time."""
    return platform.SchedulerEntry(
        platform.ENTRY_NAME, [str(EXECUTABLE), "ingest", "--store", str(world.store)], time)


def query_answer(world: World, time: str) -> str:
    """The XML the Task Scheduler answers a `/Query` with: the definition of the entry as
    the scheduler holds it, at the given time."""
    document = platform.entry_definition("windows", EXECUTABLE, world.store, time)
    return document[f"{platform.ENTRY_NAME}.xml"]


def existing_entry(world: World, time: str) -> platform.SchedulerEntry:
    """The entry that the scheduler holds already, at the given time, as the reading of the
    entry gives it back from the definition: the XML that the Task Scheduler answers, or the
    files of launchd and of systemd."""
    return platform.SchedulerEntry(
        platform.ENTRY_NAME, [str(EXECUTABLE), "ingest", "--store", str(world.store)], time)


def _without_owner(session_id: str, native_id: str) -> tuple[str, str] | None:
    """The lookup of a reading that has no store behind it."""
    return None


class RunSetup(unittest.TestCase):
    """The seven steps of setup, in their order (command-line.md › Setup)."""

    def test_first_setup_creates_all(self) -> None:
        """The first setup writes the machine configuration with the folders of native logs,
        creates the person configuration with its two entries, writes the machine label, and
        runs the first ingestion, which stores the event of the native logs."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home, "session-one", UUID_ONE)
            settle_logs(world.logs)
            result = setup.run_setup(
                options_for(world, label="work"), build_context(world))
            self.assertEqual(result.machine, "1a2b3c4d-0000-4000-8000-000000000001")
            written = configuration.read_machine_configuration(world.machine)
            self.assertIsNotNone(written)
            self.assertEqual(written.machine, result.machine)
            self.assertEqual(written.store, str(world.store))
            self.assertEqual(written.native_logs, {"claude-code": [str(world.logs)]})
            self.assertTrue(written.installation and written.salt)
            self.assertTrue(result.configuration_created)
            self.assertEqual(result.entries, [
                {"zone": ZONE, "from": "1970-01-01T00:00:00Z"},
                {"hour": "00:00", "from": "1970-01-01"},
            ])
            person = configuration.read_person_configuration(world.store)
            self.assertEqual(person.time_zones[0].zone, ZONE)
            self.assertEqual(person.day_starts[0].hour, time(0, 0))
            self.assertEqual(store.machine_labels(world.store, [result.machine]),
                             ({result.machine: "work"}, []))
            self.assertEqual(
                result.ingest.sources,
                [ingestion.SourceResult(adapters.SOURCE, str(world.logs), 1, 0)])
            self.assertEqual(len(stored_event_keys(world.store)), 1)

    def test_first_setup_stores_every_complete_event(self) -> None:
        """Acceptance criterion 1: after the first setup, the keys of the events in the store
        are exactly the keys of the complete events the native logs hold."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home, "session-one", UUID_ONE)
            write_prompt_session(world.logs, world.home, "session-two", UUID_TWO)
            support.write_session(
                world.logs, "session-three",
                [support.prompt_record("Invented prompt text.", PROMPT_AT, UUID_THREE),
                 support.prompt_record("Invented prompt text.", PROMPT_AT, UUID_FOUR)],
                {}, world.home / "other-work")
            settle_logs(world.logs)
            result = setup.run_setup(options_for(world), build_context(world))
            expected = complete_event_keys(world)
            self.assertEqual(len(expected), 4)
            self.assertEqual(stored_event_keys(result.store), expected)

    def test_second_setup_changes_only_options(self) -> None:
        """A second setup keeps the machine identifier, leaves the person configuration as it
        is, keeps the recorded folders and adds the given one, and changes only what its
        options name: the machine label."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            uids = counting_uids()
            first = setup.run_setup(
                options_for(world, label="work", schedule=True),
                build_context(world, new_uid=uids))
            person_text = (world.store / "configuration.toml").read_text(encoding="utf-8")
            added = base / "added-logs"
            second_run = FakeRun()
            second = setup.run_setup(
                options_for(world, label="home", native_logs=[("claude-code", str(added))]),
                build_context(world, run=second_run, new_uid=uids))
            self.assertEqual(second.machine, first.machine)
            self.assertFalse(second.configuration_created)
            self.assertEqual(second.entries, [])
            written = configuration.read_machine_configuration(world.machine)
            self.assertIsNotNone(written)
            self.assertEqual(written.store, str(world.store))
            self.assertEqual(written.native_logs,
                             {"claude-code": [str(world.logs), str(added)]})
            self.assertEqual(store.machine_labels(world.store, [second.machine]),
                             ({second.machine: "home"}, []))
            self.assertEqual((world.store / "configuration.toml").read_text(encoding="utf-8"),
                             person_text)
            self.assertFalse(entry_created(world, second_run))
            self.assertEqual([source.new_events for source in second.ingest.sources], [0, 0])

    def test_recorded_folder_stays(self) -> None:
        """A folder of native logs the person added is kept when setup records the folders
        the agent tools use, and the machine identifier of the recorded configuration
        stays."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            world.machine.mkdir(parents=True)
            added = base / "logs-the-person-added"
            configuration.write_machine_configuration(
                world.machine,
                configuration.MachineConfiguration(
                    machine="7e5d4c3b-0000-4000-8000-000000000009", installation=None,
                    salt=None, store=str(world.store),
                    native_logs={"claude-code": [str(world.logs), str(added)]}))
            result = setup.run_setup(options_for(world), build_context(world))
            written = configuration.read_machine_configuration(world.machine)
            self.assertIsNotNone(written)
            self.assertEqual(written.machine, "7e5d4c3b-0000-4000-8000-000000000009")
            self.assertEqual(written.native_logs["claude-code"], [str(world.logs), str(added)])
            self.assertEqual(result.machine, "7e5d4c3b-0000-4000-8000-000000000009")

    def test_claude_config_dir_is_recorded(self) -> None:
        """The folder of native logs that `CLAUDE_CONFIG_DIR` gives at setup is the one
        recorded, so a scheduled ingestion does not depend on the environment variables of
        the scheduler (claude-code-adapter.md › Native logs)."""
        with support.TemporaryFolder() as base:
            config = base / "claude-config"
            (config / "projects").mkdir(parents=True)
            world = build_world(base, CLAUDE_CONFIG_DIR=str(config))
            result = setup.run_setup(options_for(world), build_context(world))
            written = configuration.read_machine_configuration(world.machine)
            self.assertIsNotNone(written)
            self.assertEqual(written.native_logs["claude-code"], [str(config / "projects")])
            self.assertNotIn(str(world.logs), written.native_logs["claude-code"])

    def test_store_option_is_written(self) -> None:
        """The folder of `--store` becomes the store of the machine and is written in the
        machine configuration; without `--store` the default folder is used and no store key
        is written (architecture.md › Files of a machine)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            result = setup.run_setup(options_for(world), build_context(world))
            written = configuration.read_machine_configuration(world.machine)
            self.assertIsNotNone(written)
            self.assertEqual(written.store, str(world.store))
            self.assertEqual(result.store, world.store)
        with support.TemporaryFolder() as base:
            world = build_world(base)
            result = setup.run_setup(
                options_for(world, store=None), build_context(world))
            written = configuration.read_machine_configuration(world.machine)
            self.assertIsNotNone(written)
            self.assertIsNone(written.store)
            self.assertEqual(
                result.store,
                Path(platform.default_store_folder(SYSTEM, world.environ, world.home)))

    def test_no_label_without_terminal(self) -> None:
        """When standard input is not a terminal and `--label` is absent, setup writes no
        machine label; the command `machine label` sets it later. An empty or blank
        `--label` is no label either, as a blank answer of the person is not."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            result = setup.run_setup(options_for(world), build_context(world, ask=None))
            self.assertEqual(store.machine_labels(world.store, [result.machine]), ({}, []))
            self.assertFalse((world.store / "machines").exists())
        for given in ("", " \t "):
            with self.subTest(label=given), support.TemporaryFolder() as base:
                world = build_world(base)
                blank = setup.run_setup(
                    options_for(world, label=given), build_context(world, ask=None))
                self.assertEqual(store.machine_labels(world.store, [blank.machine]), ({}, []))
                self.assertFalse((world.store / "machines").exists())

    def test_schedule_only_with_consent(self) -> None:
        """Without `--schedule` and without a terminal the entry is only shown, never
        created; with `--schedule yes`, and with the consent of the person at a terminal, it
        is created; `--schedule no` never creates it, also with an ask. Cron holds no entry
        of the ledger and writes nothing, so there the shown entry stands in for the
        observation of the creation."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            kind = platform.scheduler_kind(SYSTEM, shutil.which)
            shown_run = FakeRun()
            shown = setup.run_setup(options_for(world), build_context(world, run=shown_run))
            self.assertEqual(shown.schedule, intended_entry(world))
            self.assertFalse(entry_created(world, shown_run))
            created_run = FakeRun()
            created = setup.run_setup(
                options_for(world, schedule=True), build_context(world, run=created_run))
            self.assertEqual(created.schedule, intended_entry(world))
            if kind != "cron":
                self.assertTrue(entry_created(world, created_run))
            else:
                self.assertEqual(created.schedule, intended_entry(world))

            asked_keys: list[tuple[str, dict[str, object]]] = []

            def consent(key: str, **values: object) -> str:
                asked_keys.append((key, values))
                return answer

            asked_run = FakeRun()
            answer = "yes"
            asked = setup.run_setup(
                options_for(world), build_context(world, run=asked_run, ask=consent))
            # setup asks by key, the label first, and holds the text of no question
            self.assertEqual(asked_keys, [("setup_label", {}),
                                          ("setup_schedule", {"time": "12:00"})])
            if kind != "cron":
                self.assertTrue(entry_created(world, asked_run))
            else:
                self.assertEqual(asked.schedule, intended_entry(world))
            asked_run.calls.clear()
            answer = "no"
            declined = setup.run_setup(
                options_for(world), build_context(world, run=asked_run, ask=consent))
            self.assertFalse(entry_created(world, asked_run))
            self.assertEqual(declined.schedule, intended_entry(world))
            refused_run = FakeRun()
            refused = setup.run_setup(
                options_for(world, schedule=False),
                build_context(world, run=refused_run, ask=consent))
            self.assertFalse(entry_created(world, refused_run))

    def test_shown_entry_is_the_existing_one_until_it_is_replaced(self) -> None:
        """When the scheduler holds the entry of the ledger already, setup shows the
        existing one, not the intended one; with consent it is replaced, and a replace that
        ends with an error leaves the existing one shown, with the `scheduler_failed`
        warning. The test runs its context as Windows on every runner: the fake of the query
        holds the existing entry whatever a create does, where a create changes the files of
        launchd and of systemd, failed or not; the next test reads the entry from those
        files. The working folder of the test is its temporary folder: on a
        runner that is not Windows the machine-local data folder of a `Windows` context is
        a pure path whose text reads as a relative name."""
        with support.TemporaryFolder() as base, contextlib.chdir(base):
            world = build_world(base, system="Windows")
            shown_run = FakeRun(query=query_answer(world, "09:30"))
            shown = setup.run_setup(
                options_for(world),
                build_context(world, run=shown_run, system="Windows"))
            self.assertEqual(shown.schedule, existing_entry(world, "09:30"))
            self.assertFalse(entry_created(world, shown_run, system="Windows"))
            failed_run = FakeRun(code=1, query=query_answer(world, "09:30"))
            failed = setup.run_setup(
                options_for(world, schedule=True),
                build_context(world, run=failed_run, system="Windows"))
            self.assertEqual(failed.schedule, existing_entry(world, "09:30"))
            self.assertEqual(failed.warnings, [{
                "code": "scheduler_failed",
                "values": {"program": "schtasks", "exit_code": 1},
            }])
            replaced_run = FakeRun(query=query_answer(world, "09:30"))
            replaced = setup.run_setup(
                options_for(world, schedule=True, time="06:30"),
                build_context(world, run=replaced_run, system="Windows"))
            self.assertEqual(replaced.schedule, intended_entry(world, "06:30"))
            self.assertTrue(entry_created(world, replaced_run, system="Windows"))

    def test_shown_entry_is_read_from_the_files_in_the_home(self) -> None:
        """On macOS and Linux the scheduler holds the entry of the ledger in the files that
        a create writes below the home of the person: setup shows the entry those files
        hold, not the intended one, and without consent asks no scheduler program. The
        Linux case runs twice, with `shutil.which` patched to find `systemctl` (systemd,
        which holds the entry in the files) and to find nothing (cron, which holds no
        entry of the ledger, so there setup shows the intended one)."""
        written = {"Darwin": ("launchd", ("Library", "LaunchAgents")),
                   "Linux": ("systemd", (".config", "systemd", "user"))}
        programs = {"Darwin": (None,), "Linux": ("/usr/bin/systemctl", None)}
        for system, (kind, parts) in written.items():
            for program in programs[system]:
                with (self.subTest(system=system, systemctl=program),
                      support.TemporaryFolder() as base,
                      mock.patch("shutil.which", return_value=program)):
                    world = build_world(base, system=system)
                    folder = world.home.joinpath(*parts)
                    folder.mkdir(parents=True)
                    definition = platform.entry_definition(kind, EXECUTABLE, world.store, "09:30")
                    for name, text in definition.items():
                        (folder / name).write_text(text, encoding="utf-8")
                    run = FakeRun()
                    shown = setup.run_setup(
                        options_for(world), build_context(world, run=run, system=system))
                    if platform.scheduler_kind(system, shutil.which) == "cron":
                        self.assertEqual(shown.schedule, intended_entry(world))
                    else:
                        self.assertEqual(shown.schedule, existing_entry(world, "09:30"))
                    self.assertEqual(run.calls, [])

    def test_development_version_never_creates_entry(self) -> None:
        """A version with a development mark shows the entry and never creates it, also with
        `--schedule yes`, because the scheduler does not pass the variable that lets such a
        version write; the first ingestion runs, because the tests let it write."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home, "session-one", UUID_ONE)
            settle_logs(world.logs)
            run = FakeRun()
            result = setup.run_setup(
                options_for(world, schedule=True),
                build_context(world, run=run, version=DEVELOPMENT_VERSION))
            self.assertFalse(entry_created(world, run))
            self.assertEqual(result.schedule, intended_entry(world))
            self.assertEqual([source.new_events for source in result.ingest.sources], [1])

    def test_retention_is_shown_with_advice(self) -> None:
        """The retention of each agent tool is shown with its setting and its period, and the
        advice of the scheduled ingestion; on Linux the advice names `loginctl
        enable-linger`, because a systemd user timer runs only while the person is logged in
        (ingestion.md › Frequency, ruled 2026-11-20)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            result = setup.run_setup(options_for(world), build_context(world))
            linger = "loginctl enable-linger" if SYSTEM == "Linux" else None
            self.assertEqual(result.retention, [
                {"tool": "claude-code", "setting": "cleanupPeriodDays", "days": 30,
                 "linger": linger},
                {"tool": "claude-desktop", "setting": "desktopSessionCleanupPeriodDays",
                 "days": None, "linger": linger},
            ])
        with support.TemporaryFolder() as base:
            linux = build_world(base, system="Linux")
            result = setup.run_setup(
                options_for(linux), build_context(linux, system="Linux"))
            self.assertEqual(result.retention, [
                {"tool": "claude-code", "setting": "cleanupPeriodDays", "days": 30,
                 "linger": "loginctl enable-linger"},
                {"tool": "claude-desktop", "setting": "desktopSessionCleanupPeriodDays",
                 "days": None, "linger": "loginctl enable-linger"},
            ])

    def test_windows_zone_unknown_writes_no_time_zone(self) -> None:
        """When the time zone of the operating system gives nothing the ledger can hold, the
        created person configuration holds no `[[time_zone]]` entry: the ledger never
        guesses a time zone (configuration.md › Writes)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            result = setup.run_setup(
                options_for(world), build_context(world, time_zone=lambda: None))
            self.assertEqual(result.entries, [{"hour": "00:00", "from": "1970-01-01"}])
            text = (world.store / "configuration.toml").read_text(encoding="utf-8")
            self.assertNotIn("[[time_zone]]", text)
            self.assertNotIn("zone", text)
            person = configuration.read_person_configuration(world.store)
            self.assertEqual(person.time_zones, [])
            self.assertEqual(person.day_starts[0].hour, time(0, 0))

    def test_failed_scheduler_warns_and_ingests(self) -> None:
        """When the scheduler of the operating system ends with an error while it creates the
        entry, setup warns with `scheduler_failed`, shows no entry, and goes on with the
        first ingestion, which stores the events of the native logs; setup completes."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home, "session-one", UUID_ONE)
            settle_logs(world.logs)
            run = FakeRun(code=1)
            result = setup.run_setup(
                options_for(world, schedule=True), build_context(world, run=run))
            kind = platform.scheduler_kind(SYSTEM, shutil.which)
            if kind != "cron":
                self.assertEqual(result.warnings, [{
                    "code": "scheduler_failed",
                    "values": {"program": _SCHEDULER_PROGRAM[kind], "exit_code": 1},
                }])
                self.assertIsNone(result.schedule)
            else:
                # Cron holds no entry of the ledger, so its create neither fails nor writes:
                # the shown entry is the intended one, and no warning is given.
                self.assertEqual(result.warnings, [])
                self.assertEqual(result.schedule, intended_entry(world))
            self.assertEqual([source.new_events for source in result.ingest.sources], [1])
            self.assertEqual(len(stored_event_keys(world.store)), 1)


    def test_step_6_refuses_a_store_word_the_scheduler_cannot_carry(self) -> None:
        """A machine configuration whose store folder holds a word the scheduler of the
        operating system cannot carry stops setup with the wrong value that names the
        folder and the machine configuration file to fix, before the entry is created and
        before the first ingestion runs (command-line.md › Setup). The first setup writes
        the folder of the test into the machine configuration with `--schedule no`, which
        creates no entry, so the second setup reads the word from the machine
        configuration when it resolves the store folder. The test runs its context as
        Linux with `shutil.which` patched to find no `systemctl`, so the scheduler kind is
        cron, whose refusal covers the `%` of the folder."""
        with support.TemporaryFolder() as base:
            world = build_world(base, system="Linux")
            setup.run_setup(
                options_for(world, store=base / "100%", schedule=False),
                build_context(world, system="Linux"))
            written = configuration.read_machine_configuration(world.machine)
            self.assertEqual(written.store, str(base / "100%"))
            with mock.patch("shutil.which", return_value=None), \
                    self.assertRaises(configuration.WrongValue) as stopped:
                setup.run_setup(
                    options_for(world, store=None, schedule=True),
                    build_context(world, system="Linux"))
            self.assertEqual(stopped.exception.values, {
                "key": str(world.machine / "machine.toml"), "value": str(base / "100%")})


class WindowsEntryXml(unittest.TestCase):
    """The XML of the entry of the Task Scheduler and the encoding of the file it is written
    to (Task 44, plan Step 4; the probe with the real scheduler is deferred to the owner)."""

    def test_store_path_with_non_ascii_letters_is_written_unchanged(self) -> None:
        """A store folder whose path holds `à` is in the written XML unchanged, after the
        round trip through the file the XML is written to with the encoding of the writer."""
        with support.TemporaryFolder() as base:
            store_folder = base / "café à product"
            document = platform.entry_definition("windows", EXECUTABLE, store_folder, "12:00")
            text = document[f"{platform.ENTRY_NAME}.xml"]
            written = base / "entry.xml"
            written.write_text(text, encoding="utf-8", newline="\n")
            self.assertIn(str(store_folder), written.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
