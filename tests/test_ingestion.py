"""Tests of the ingestion module: the record of the sources of one store, the sessions that an
ingestion reads, the warning for the events that the retention of an agent tool can have
deleted, the sessions with events held back that a report names, and the ingestion of the
native logs of all adapters into the store (architecture.md › Data flow, ingestion.md ›
Frequency)."""

import json
import os
import unittest
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path
from platform import system as running_system
from typing import NamedTuple
from unittest import mock

import support
from ai_effort_ledger import configuration, events, ingestion, platform, store
from ai_effort_ledger.adapters import Retention, SessionFiles

READ_AT = "2026-11-20T12:00:00.000Z"
"""The instant that the tests record as the last ingestion of a folder of native logs."""


def write_log(path: Path, text: str) -> Path:
    """Write invented text to a file of native logs, creating the folders above it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def session_files(logs: Path, session_id: str, subagents: tuple[str, ...]) -> SessionFiles:
    """The files of one session of Claude Code in a folder of native logs: the file of the
    main agent and the file of each named subagent."""
    return SessionFiles(
        "claude-code",
        session_id,
        logs,
        logs / f"{session_id}.jsonl",
        {name: logs / session_id / "subagents" / f"agent-{name}.jsonl" for name in subagents},
    )


def one_subagent_session(base: Path) -> SessionFiles:
    """One session with a file of the main agent and a file of one subagent, written with
    invented text."""
    session = session_files(base / "logs", "session-one", ("alpha",))
    write_log(session.main, "records of the main agent, invented\n")
    write_log(session.subagents["alpha"], "records of the subagent, invented\n")
    return session


def session_paths(session: SessionFiles) -> list[Path]:
    """The files of the session: the file of the main agent when it exists, and the files of
    its subagents."""
    return [path for path in [session.main, *session.subagents.values()] if path is not None]


def state_with_files(session: SessionFiles) -> ingestion.SourcesState:
    """A state whose record holds every file of the session as the file is on the disk now,
    and the folder of the session as read at `READ_AT`."""
    state = ingestion.SourcesState()
    state.folders[str(session.folder)] = READ_AT
    for path in session_paths(session):
        state.files[str(path)] = ingestion.file_stamp(path)
    return state


class SessionsToRead(unittest.TestCase):
    """The sessions that one ingestion reads, and those it leaves at rest."""

    def test_changed_file_selects_its_whole_session(self) -> None:
        """A change of the size, or only of the time of change, of one subagent file selects
        the session, whose files are all read again; a file that the record holds and that is
        gone from the disk is a change too."""
        with support.TemporaryFolder() as base:
            session = one_subagent_session(base)
            state = state_with_files(session)
            self.assertEqual(ingestion.sessions_to_read(state, [session], []), [])
            # A longer subagent file is a change of size: the whole session is read again.
            write_log(session.subagents["alpha"],
                      "records of the subagent, invented\nmore invented records\n")
            self.assertEqual(ingestion.sessions_to_read(state, [session], []), [session])

        with support.TemporaryFolder() as base:
            session = one_subagent_session(base)
            state = state_with_files(session)
            # The same size with a later time of change is a change too.
            stamp = state.files[str(session.subagents["alpha"])]
            os.utime(session.subagents["alpha"], ns=(stamp[1] + 1_000_000,) * 2)
            self.assertEqual(ingestion.sessions_to_read(state, [session], []), [session])

        with support.TemporaryFolder() as base:
            session = one_subagent_session(base)
            state = state_with_files(session)
            # A file of the session that is gone is a change: the session is read again.
            session.subagents["alpha"].unlink()
            self.assertEqual(ingestion.sessions_to_read(state, [session], []), [session])

    def test_held_back_session_is_read_again(self) -> None:
        """A session whose events the machine holds back is read again even when none of its
        files changed since the last ingestion."""
        with support.TemporaryFolder() as base:
            session = one_subagent_session(base)
            state = state_with_files(session)
            state.held_back[session.tool] = [session.session_id]
            self.assertEqual(ingestion.sessions_to_read(state, [session], []), [session])

    def test_purged_session_is_read_again(self) -> None:
        """A session that a purge with a corrected version names is read again when the
        machine has not applied the purge, even when none of its files changed."""
        with support.TemporaryFolder() as base:
            session = one_subagent_session(base)
            state = state_with_files(session)
            purged = [(session.tool, session.session_id)]
            self.assertEqual(ingestion.sessions_to_read(state, [session], purged), [session])

    def test_unchanged_session_is_not_read(self) -> None:
        """A session whose files are all as the record holds them is left at rest, while a
        session that the record never saw is read."""
        with support.TemporaryFolder() as base:
            session = one_subagent_session(base)
            state = state_with_files(session)
            other = session_files(base / "logs", "session-two", ())
            write_log(other.main, "records of the main agent, invented\n")
            self.assertEqual(ingestion.sessions_to_read(state, [session], []), [])
            self.assertEqual(ingestion.sessions_to_read(state, [session, other], []), [other])


class LostEvents(unittest.TestCase):
    """The warning for the native logs that the retention of an agent tool can have deleted."""

    def test_lost_events_after_long_gap(self) -> None:
        """A previous ingestion of the folder 40 days before now, with a retention of 30 days,
        gives a warning that names the folder, the earlier instant, and now."""
        with support.TemporaryFolder() as base:
            folder = str(base / "logs")
            state = ingestion.SourcesState()
            state.folders[folder] = "2026-10-01T12:00:00.000Z"
            retention = Retention("cleanupPeriodDays", 30)
            warning = ingestion.lost_events(
                state, folder, retention, support.utc("2026-11-10T12:00"))
            self.assertEqual(warning, {"code": "lost_events", "values": {
                "folder": folder,
                "from": "2026-10-01T12:00:00.000Z",
                "to": "2026-11-10T12:00:00.000Z",
            }})

    def test_lost_events_at_the_retention_edge(self) -> None:
        """A gap of exactly the retention period gives no warning; one day more gives one."""
        with support.TemporaryFolder() as base:
            folder = str(base / "logs")
            state = ingestion.SourcesState()
            state.folders[folder] = "2026-10-01T12:00:00.000Z"
            retention = Retention("cleanupPeriodDays", 30)
            self.assertIsNone(
                ingestion.lost_events(
                    state, folder, retention, support.utc("2026-10-31T12:00")))
            warning = ingestion.lost_events(
                state, folder, retention, support.utc("2026-11-01T12:00"))
            self.assertEqual(warning["values"]["from"], "2026-10-01T12:00:00.000Z")
            self.assertEqual(warning["values"]["to"], "2026-11-01T12:00:00.000Z")

    def test_no_lost_events_without_age_limit(self) -> None:
        """An agent tool with no age limit on its native logs deletes none: however long the
        gap since the previous ingestion, the ingestion gives no warning."""
        with support.TemporaryFolder() as base:
            folder = str(base / "logs")
            state = ingestion.SourcesState()
            state.folders[folder] = "2025-10-01T12:00:00.000Z"
            retention = Retention("desktopSessionCleanupPeriodDays", None)
            self.assertIsNone(
                ingestion.lost_events(
                    state, folder, retention, support.utc("2026-11-10T12:00")))

    def test_no_lost_events_at_first_ingestion(self) -> None:
        """The first ingestion of a folder has no earlier instant of the folder to measure a
        gap from: it gives no warning."""
        with support.TemporaryFolder() as base:
            folder = str(base / "logs")
            state = ingestion.SourcesState()
            self.assertIsNone(
                ingestion.lost_events(
                    state, folder, Retention("cleanupPeriodDays", 30),
                    support.utc("2026-11-10T12:00")))


class SourcesStateFile(unittest.TestCase):
    """The record of the sources in its file."""

    def test_saved_state_reads_back_the_same(self) -> None:
        """A saved state reads back with the same folders, files, held-back sessions, and
        applied purges, and the file names no null value."""
        with support.TemporaryFolder() as base:
            path = base / "machine" / "stores" / "1a2b3c4d5e6f7a8b" / "sources.json"
            state = ingestion.SourcesState(
                {"D:\\Work\\Logs": READ_AT},
                {"D:\\Work\\Logs\\one.jsonl": (1234, 1790000000000000000)},
                {"claude-code": ["session-one", "session-two"]},
                ["purge-one", "purge-two"])
            state.save(path)
            read = ingestion.SourcesState.load(path)
            self.assertEqual(read.folders, {"D:\\Work\\Logs": READ_AT})
            self.assertEqual(read.files,
                             {"D:\\Work\\Logs\\one.jsonl": (1234, 1790000000000000000)})
            self.assertEqual(read.held_back, {"claude-code": ["session-one", "session-two"]})
            self.assertEqual(read.applied_purges, ["purge-one", "purge-two"])
            self.assertNotIn("null", path.read_text(encoding="utf-8"))

    def test_missing_file_reads_empty(self) -> None:
        """A state read from a path that holds no file yet is empty: the first ingestion of a
        store starts with nothing recorded."""
        with support.TemporaryFolder() as base:
            state = ingestion.SourcesState.load(
                base / "machine" / "stores" / "1a2b3c4d5e6f7a8b" / "sources.json")
            self.assertEqual(state.folders, {})
            self.assertEqual(state.files, {})
            self.assertEqual(state.held_back, {})
            self.assertEqual(state.applied_purges, [])

    def test_file_of_another_shape_reads_empty(self) -> None:
        """A file that holds no JSON document reads as an empty state, so that a write that
        stopped cannot stop the ingestions of the machine."""
        with support.TemporaryFolder() as base:
            path = base / "sources.json"
            path.write_text("not a json document\n", encoding="utf-8")
            state = ingestion.SourcesState.load(path)
            self.assertEqual(
                (state.folders, state.files, state.held_back, state.applied_purges),
                ({}, {}, {}, []))

    def test_save_replaces_the_file_in_one_step(self) -> None:
        """A save leaves no file beside the record in the folder, and a save over a record
        that exists replaces it whole: the record reads back with the new content."""
        with support.TemporaryFolder() as base:
            folder = base / "machine" / "stores" / "1a2b3c4d5e6f7a8b"
            path = folder / "sources.json"
            state = ingestion.SourcesState({"D:\\Work\\Logs": READ_AT})
            state.save(path)
            self.assertEqual(sorted(item.name for item in folder.iterdir()), ["sources.json"])
            state.files["D:\\Work\\Logs\\one.jsonl"] = (12, 34)
            state.save(path)
            read = ingestion.SourcesState.load(path)
            self.assertEqual(read.folders, {"D:\\Work\\Logs": READ_AT})
            self.assertEqual(read.files, {"D:\\Work\\Logs\\one.jsonl": (12, 34)})
            self.assertEqual(sorted(item.name for item in folder.iterdir()), ["sources.json"])

    def test_save_that_cannot_replace_keeps_the_record(self) -> None:
        """A replace that the operating system refuses past the limit stops the save and
        leaves the record as it was and no file beside it: the file of the record never holds
        half of a document."""
        with support.TemporaryFolder() as base:
            path = base / "sources.json"
            state = ingestion.SourcesState({"D:\\Work\\Logs": READ_AT})
            state.save(path)
            changed = ingestion.SourcesState({"D:\\Other\\Logs": READ_AT})
            with mock.patch("ai_effort_ledger.ingestion.state.os.replace",
                            side_effect=PermissionError()) as refused:
                with self.assertRaises(platform.LockUnavailable) as stopped:
                    changed.save(path, limit_seconds=0.0)
            self.assertTrue(refused.called)
            self.assertEqual(stopped.exception.code, "lock_unavailable")
            self.assertEqual(stopped.exception.values, {"path": str(path)})
            self.assertEqual(stopped.exception.exit_code, 1)
            self.assertEqual(sorted(item.name for item in base.iterdir()), ["sources.json"])
            self.assertEqual(ingestion.SourcesState.load(path).folders,
                             {"D:\\Work\\Logs": READ_AT})

    def test_save_retries_a_refused_replace(self) -> None:
        """A replace that the operating system refuses once is tried again after half a
        second and then succeeds: the record reads back with the new content and no file
        beside it stays."""
        with support.TemporaryFolder() as base:
            path = base / "sources.json"
            changed = ingestion.SourcesState({"D:\\Other\\Logs": READ_AT})
            attempts: list[Path] = []
            real_replace = os.replace
            def refuse_once(new_path: Path, target: Path) -> None:
                attempts.append(new_path)
                if len(attempts) == 1:
                    raise PermissionError()
                real_replace(new_path, target)
            with mock.patch("ai_effort_ledger.ingestion.state.os.replace",
                            side_effect=refuse_once):
                changed.save(path, limit_seconds=30.0)
            self.assertEqual(len(attempts), 2)
            self.assertEqual(sorted(item.name for item in base.iterdir()), ["sources.json"])
            self.assertEqual(ingestion.SourcesState.load(path).folders,
                             {"D:\\Other\\Logs": READ_AT})


class HeldBackSessions(unittest.TestCase):
    """The sessions with events held back that a report names."""

    def test_held_back_sessions_of_one_store(self) -> None:
        """The held-back sessions of the record of the store, each as its agent tool and its
        session identifier, read from the file below the identifier of the store folder."""
        with support.TemporaryFolder() as base:
            machine_folder = base / "machine"
            store_folder = base / "store"
            state = ingestion.SourcesState()
            state.held_back = {"claude-code": ["session-one", "session-two"],
                               "claude-desktop": ["session-three"]}
            state.save(ingestion.sources_path(machine_folder, store_folder, "Linux"))
            identifier = platform.store_identifier(store_folder, "Linux")
            self.assertTrue(
                (machine_folder / "stores" / identifier / "sources.json").is_file())
            self.assertEqual(
                ingestion.held_back_sessions(machine_folder, store_folder, "Linux"),
                {("claude-code", "session-one"), ("claude-code", "session-two"),
                 ("claude-desktop", "session-three")})

    def test_no_held_back_session_without_record(self) -> None:
        """A machine that holds no record of the sources of a store gives no held-back
        session, so that a report on it warns of nothing."""
        with support.TemporaryFolder() as base:
            self.assertEqual(
                ingestion.held_back_sessions(base / "machine", base / "store", "Linux"),
                set())


NOW = support.utc("2026-11-20T12:00")
"""The instant of every ingestion of the tests."""
LATER = support.utc("2026-11-21T08:00")
"""The instant at which the tests append the events that a command writes."""
SETTLE = 14400
"""The settle time of the person configuration of the tests, in seconds."""
MACHINE = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
"""The machine identifier of the machine configuration of the tests."""
OTHER_MACHINE = "7f6e5d4c-3b2a-4c1d-8e9f-0a1b2c3d4e5f"
"""The machine identifier of another machine whose segment the tests write by hand."""
_PROMPT_AT = "2026-11-19T09:15:00.000Z"
"""The instant that the prompt records of the tests hold."""
_TOOL_AT = "2026-11-19T10:00:00.000Z"
_TOOL_LATER = "2026-11-19T10:05:00.000Z"
_UUID_ONE = "3f1c0000-0000-4000-8000-0000000000a1"
_UUID_TWO = "3f1c0000-0000-4000-8000-0000000000a2"
DEVELOPMENT = {"AI_EFFORT_LEDGER_DEVELOPMENT": "1"}
"""The environment of the ingestions of the tests, which lets the development version of the
package write to the store (architecture.md › Runtime)."""


class World(NamedTuple):
    """The folders of one ingestion of the tests: the home of the person, the machine-local
    data folder, the store folder, and the folder of native logs of Claude Code."""

    home: Path
    machine_folder: Path
    store_folder: Path
    logs: Path


def build_world(base: Path, store_name: str = "store") -> World:
    """The world of a test: a home with its `.claude/projects` folder, the machine-local data
    folder beside it, and the store folder named, all inside the temporary folder."""
    home = base / "home"
    (home / ".claude" / "projects").mkdir(parents=True)
    return World(home, base / "machine", base / store_name, home / ".claude" / "projects")


def person_with(
    rules: Sequence[configuration.CategoryRule] = (),
) -> configuration.PersonConfiguration:
    """The person configuration of the tests: no dated facts and no names, the settle time of
    the tests, and the category rules given."""
    return configuration.PersonConfiguration(
        time_zones=[], day_starts=[], projects=[], work_items=[], identity_rules=[],
        category_rules=list(rules), preferred_remotes=["origin"], settle_time=SETTLE, report={})


def machine_for(folders: Sequence[Path]) -> configuration.MachineConfiguration:
    """The machine configuration of the tests: the machine identifier of the tests and the
    folders of native logs of Claude Code given."""
    return configuration.MachineConfiguration(
        machine=MACHINE, installation=None, salt=None, store=None,
        native_logs={"claude-code": [str(folder) for folder in folders]})


def ingest(
    world: World,
    *,
    person: configuration.PersonConfiguration | None = None,
    machine: configuration.MachineConfiguration | None = None,
    now: datetime = NOW,
    environ: Mapping[str, str] | None = None,
    version: str | None = None,
) -> "ingestion.IngestionResult":
    """Run one ingestion of the world: an adapter of Claude Code whose managed settings file
    is in the home of the world, the folders of native logs that the machine configuration
    names, and an environment that lets the development version write when none is given."""
    return ingestion.run_ingestion(
        machine if machine is not None else machine_for([world.logs]),
        world.machine_folder,
        world.store_folder,
        person if person is not None else person_with(),
        [support.adapters_for_tests(world.home)],
        now,
        world.home,
        running_system(),
        environ if environ is not None else DEVELOPMENT,
        version)


def settle(paths: Sequence[Path]) -> None:
    """Give the files a time of change two settle times before the instant of the tests, so
    that a reading takes them as settled."""
    moment = NOW.timestamp() - 2 * SETTLE
    for path in paths:
        os.utime(path, (moment, moment))


def touch(paths: Sequence[Path]) -> None:
    """Give the files the instant of the tests as their time of change, so that a reading
    takes them as not settled yet."""
    for path in paths:
        os.utime(path, (NOW.timestamp(), NOW.timestamp()))


def prompt_of(uuid_value: str) -> dict:
    """A prompt record of the person of the tests."""
    return support.prompt_record("Invented prompt text.", _PROMPT_AT, uuid_value)


def write_prompt_session(logs: Path, cwd: Path, session_id: str = "session-one") -> Path:
    """Write a settled session that holds one prompt of the person into the folder of native
    logs, and give the path of its file."""
    support.write_session(logs, session_id, [prompt_of(_UUID_ONE)], {}, cwd)
    path = logs / f"{session_id}.jsonl"
    settle([path])
    return path


def write_second_prompt(
    path: Path, logs: Path, cwd: Path, session_id: str = "session-one"
) -> None:
    """Write the session again with a second prompt of the person, and settle it."""
    support.write_session(logs, session_id, [prompt_of(_UUID_ONE), prompt_of(_UUID_TWO)], {}, cwd)
    settle([path])


def stored_events(store_folder: Path) -> list[events.Event]:
    """Every event that the segments of the store hold, in the order of their segments."""
    found = []
    for name in store.segment_names(store_folder):
        found.extend(events_of_segment(store_folder, name))
    return found


def events_of_segment(store_folder: Path, name: str) -> list[events.Event]:
    """The events that one segment holds, in the order of its lines."""
    found = []
    for line in store.read_lines(store_folder, name):
        decoded = events.decode_line(line.data)
        if decoded.event is not None:
            found.append(decoded.event)
    return found


def own_segment(store_folder: Path, machine: str) -> list[events.Event]:
    """The events of the segment of the machine for the month of the instant of the tests."""
    return events_of_segment(store_folder, f"segments/{machine}/2026-11.jsonl")


def purge_event(
    event_uid: str,
    keys: Sequence[events.EventKey],
    corrected: str | None = None,
    sessions: list[dict[str, str]] | None = None,
) -> events.Event:
    """A complete invented purge event that names the keys, its corrected version and its
    sessions when they are given."""
    event: events.Event = {
        "schema_version": events.SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": event_uid,
        "timestamp": "2026-11-19T12:00:00.000Z",
        "ingested_at": "2026-11-19T12:00:00.000Z",
        "writer_version": "0.1.0",
        "actor": "human",
        "kind": "purge",
        "machine": MACHINE,
        "purge_reason": "correction",
        "purged_keys": [key.to_json() for key in keys],
    }
    if corrected is not None:
        event["corrected_version"] = corrected
    if sessions is not None:
        event["purged_sessions"] = sessions
    return event


def write_remote_repository(folder: Path) -> None:
    """Write a repository into the folder: a `.git` folder whose config names a remote of the
    repository (ADR 0004: no test runs git)."""
    git_folder = folder / ".git"
    git_folder.mkdir(parents=True)
    (git_folder / "config").write_text(
        '[remote "origin"]\n    url = https://Example.org/Example/Product.git\n',
        encoding="utf-8")


def write_root_repository(folder: Path) -> str:
    """Write a repository without a remote into the folder: one commit of invented content as
    its root, with `HEAD` and its reference pointing at it, and give the name of the commit."""
    git_folder = folder / ".git"
    git_folder.mkdir(parents=True)
    content = support.commit_object(support.TREE, [], "Invented root commit.")
    name = support.write_loose_object(git_folder, "commit", content)
    support.write_loose_ref(git_folder, "refs/heads/main", name)
    support.write_head(git_folder, "refs/heads/main")
    return name


def tool_warnings(result: "ingestion.IngestionResult") -> list[str]:
    """The tool names of the warnings about tool names that no table lists."""
    return [warning["values"]["tool"] for warning in result.warnings
            if warning["code"] == "unknown_tool_name"]


class RunIngestion(unittest.TestCase):
    """The ingestion of the native logs into the store, in the order of the eleven steps of
    the data flow (architecture.md › Data flow)."""

    def test_second_ingestion_adds_nothing(self) -> None:
        """A second ingestion whose only session did not change appends no event: the store
        keeps the events of the first one (product.md › Phase 1, acceptance criterion 1)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home / "work")
            first = ingest(world)
            second = ingest(world)
            stored = stored_events(world.store_folder)
        self.assertEqual(sum(result.new_events for result in first.sources), 1)
        self.assertEqual(sum(result.new_events for result in second.sources), 0)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["native_id"], _UUID_ONE)

    def test_events_get_repository_identity(self) -> None:
        """An event whose folder holds a repository with a remote stores the normalized remote
        as its `repo_hint` and `observed` as its `repo_basis`; a repository without a remote
        gives the identity of its root commit, which `repositories.json` keeps."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            product = world.home / "work" / "product"
            product.mkdir(parents=True)
            write_remote_repository(product)
            support.write_session(world.logs, "session-one", [prompt_of(_UUID_ONE)], {}, product)
            settle([world.logs / "session-one.jsonl"])
            library = world.home / "work" / "library"
            library.mkdir()
            root_name = write_root_repository(library)
            support.write_session(world.logs, "session-two", [prompt_of(_UUID_TWO)], {}, library)
            settle([world.logs / "session-two.jsonl"])
            ingest(world)
            stored = stored_events(world.store_folder)
            kept = json.loads(
                (world.machine_folder / "repositories.json").read_text(encoding="utf-8"))
        identities = {event["session_id"]: (event["repo_hint"], event["repo_basis"])
                      for event in stored}
        self.assertEqual(identities["session-one"], ("example.org/example/product", "observed"))
        self.assertEqual(identities["session-two"], ("root-commit:" + root_name, "observed"))
        self.assertEqual(list(kept.values()), [root_name])

    def test_cwd_with_non_ascii_letters(self) -> None:
        """A session whose folder has spaces and non-ASCII letters stores the folder text as
        it is, written as UTF-8 and never as an escape (Review Focus 2)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            folder = world.home / "work" / "Città Example"
            folder.mkdir(parents=True)
            write_prompt_session(world.logs, folder)
            result = ingest(world)
            stored = stored_events(world.store_folder)
            segment = world.store_folder / f"segments/{MACHINE}/2026-11.jsonl"
            line = segment.read_bytes()
        self.assertEqual(result.sources[0].new_events, 1)
        self.assertEqual(stored[0]["cwd"], str(folder))
        self.assertIn("Città Example".encode("utf-8"), line)
        self.assertNotIn(b"\\u", line)

    def test_store_folder_with_non_ascii_letters(self) -> None:
        """An ingestion into a store folder whose name has spaces and non-ASCII letters
        appends to the segment below it and records the sources beside it (Review Focus 2)."""
        with support.TemporaryFolder() as base:
            world = build_world(base, "Città Example Store")
            write_prompt_session(world.logs, world.home / "work")
            result = ingest(world)
            segment = world.store_folder / f"segments/{MACHINE}/2026-11.jsonl"
            stored = own_segment(world.store_folder, MACHINE)
            state = ingestion.SourcesState.load(
                ingestion.sources_path(world.machine_folder, world.store_folder,
                                       running_system()))
            self.assertTrue(segment.is_file())
            self.assertEqual([event["native_id"] for event in stored], [_UUID_ONE])
            self.assertEqual(state.folders, {str(world.logs): events.format_instant(NOW)})
        self.assertEqual(result.sources[0].new_events, 1)

    def test_missing_native_log_folder(self) -> None:
        """A folder of native logs that the machine configuration lists and that does not exist
        completes the ingestion with no new event for it, no stop, and its own instant recorded
        (Review Focus 4)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home / "work")
            gone = world.home / "gone"
            result = ingest(world, machine=machine_for([world.logs, gone]))
            state = ingestion.SourcesState.load(
                ingestion.sources_path(world.machine_folder, world.store_folder,
                                       running_system()))
        self.assertEqual([source.folder for source in result.sources],
                         [str(world.logs), str(gone)])
        self.assertEqual(result.sources[1],
                         ingestion.SourceResult("claude-code-jsonl", str(gone), 0, 0))
        self.assertEqual(sum(source.new_events for source in result.sources), 1)
        self.assertEqual(state.folders,
                         {str(world.logs): events.format_instant(NOW),
                          str(gone): events.format_instant(NOW)})

    def test_purged_key_is_not_appended(self) -> None:
        """A purge without a corrected version keeps its key out for good: an ingestion that
        reads the session again appends the new event and no copy of the purged key, whose
        copy leaves the segment of the machine (product.md › Phase 1, acceptance criterion 6;
        architecture.md › Data flow, step 10)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            path = write_prompt_session(world.logs, world.home / "work")
            first = ingest(world)
            key = events.EventKey("claude-code-jsonl", native_id=_UUID_ONE)
            store.append_events(world.store_folder, MACHINE,
                                [purge_event("purge-one", [key])], LATER)
            write_second_prompt(path, world.logs, world.home / "work")
            second = ingest(world)
            stored = stored_events(world.store_folder)
        self.assertEqual(first.sources[0].new_events, 1)
        self.assertEqual(second.sources[0].new_events, 1)
        self.assertEqual([event["kind"] for event in stored], ["purge", "prompt"])
        self.assertEqual(stored[1]["native_id"], _UUID_TWO)

    def test_corrected_version_brings_corrected_events(self) -> None:
        """A purge with a corrected version, followed by an ingestion with that version, gives
        the corrected events: the session is read again, the copy of the corrected version
        enters, the older copy leaves the segment, and the purge counts as applied
        (product.md › Phase 1, acceptance criterion 6)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home / "work")
            first = ingest(world, version="0.1.0")
            key = events.EventKey("claude-code-jsonl", native_id=_UUID_ONE)
            store.append_events(
                world.store_folder, MACHINE,
                [purge_event("purge-one", [key], corrected="0.2.0",
                             sessions=[{"tool": "claude-code", "session_id": "session-one"}])],
                LATER)
            second = ingest(world, version="0.2.0")
            third = ingest(world, version="0.2.0")
            copies = [event for event in stored_events(world.store_folder)
                      if event["kind"] != "purge"]
            state = ingestion.SourcesState.load(
                ingestion.sources_path(world.machine_folder, world.store_folder,
                                       running_system()))
        self.assertEqual(first.sources[0].new_events, 1)
        self.assertEqual(second.sources[0].new_events, 1)
        self.assertEqual(third.sources[0].new_events, 0)
        self.assertEqual(len(copies), 1)
        self.assertEqual(copies[0]["writer_version"], "0.2.0")
        self.assertEqual(state.applied_purges, ["purge-one"])

    def test_blocked_copies_leave_own_segments(self) -> None:
        """Step 10 removes the copies that a purge blocks from the segments of the machine,
        and leaves the copy in the segment of another machine untouched."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home / "work")
            ingest(world, version="0.1.0")
            key = events.EventKey("claude-code-jsonl", native_id=_UUID_ONE)
            store.append_events(world.store_folder, MACHINE,
                                [purge_event("purge-one", [key])], LATER)
            copy = dict(own_segment(world.store_folder, MACHINE)[0])
            copy["machine"] = OTHER_MACHINE
            store.append_events(world.store_folder, OTHER_MACHINE, [copy], LATER)
            second = ingest(world)
            mine = own_segment(world.store_folder, MACHINE)
            others = own_segment(world.store_folder, OTHER_MACHINE)
        self.assertEqual(second.sources[0].new_events, 0)
        self.assertEqual([event["kind"] for event in mine], ["purge"])
        self.assertEqual([event["native_id"] for event in others], [_UUID_ONE])

    def test_unknown_tool_warns_once_unless_category_rule(self) -> None:
        """One warning for each tool name that no table of its adapter lists, once however
        many records of the reading name it, and none when a category rule matches the name
        (ingestion.md › Adapters)."""
        records = [
            support.tool_use("mcp__invented__lookup", "toolu_1", {"file_path": "invented"},
                             _TOOL_AT, _UUID_ONE, "msg_tool_01"),
            support.tool_use("mcp__invented__lookup", "toolu_2", {"file_path": "invented"},
                             _TOOL_LATER, _UUID_TWO, "msg_tool_02"),
        ]
        with support.TemporaryFolder() as base:
            world = build_world(base)
            support.write_session(world.logs, "session-one", records, {}, world.home / "work")
            settle([world.logs / "session-one.jsonl"])
            warned = ingest(world)
        self.assertEqual(tool_warnings(warned), ["mcp__invented__lookup"])
        self.assertEqual(warned.sources[0].new_events, 4)
        with support.TemporaryFolder() as base:
            world = build_world(base)
            support.write_session(world.logs, "session-one", records, {}, world.home / "work")
            settle([world.logs / "session-one.jsonl"])
            ruled = ingest(world, person=person_with(
                [configuration.CategoryRule("mcp__*", "other", 1)]))
        self.assertEqual(tool_warnings(ruled), [])
        self.assertEqual(ruled.sources[0].new_events, 4)

    def test_key_already_stored_is_not_appended(self) -> None:
        """The store holds one copy of each key: a session read again gives no second copy of
        a key that the store holds, and a session read for the first time gives no copy when
        the store holds the key in the segment of another machine."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            path = write_prompt_session(world.logs, world.home / "work")
            ingest(world)
            write_second_prompt(path, world.logs, world.home / "work")
            second = ingest(world)
            mine = own_segment(world.store_folder, MACHINE)
        self.assertEqual([event.get("native_id") for event in mine], [_UUID_ONE, _UUID_TWO])
        self.assertEqual(second.sources[0].new_events, 1)
        with support.TemporaryFolder() as base:
            world = build_world(base)
            path = write_prompt_session(world.logs, world.home / "work")
            ingest(world)
            stored = own_segment(world.store_folder, MACHINE)[0]
            (world.store_folder / f"segments/{MACHINE}/2026-11.jsonl").unlink()
            copy = dict(stored)
            copy["machine"] = OTHER_MACHINE
            store.append_events(world.store_folder, OTHER_MACHINE, [copy], LATER)
            write_second_prompt(path, world.logs, world.home / "work")
            again = ingest(world)
            held = [event for event in stored_events(world.store_folder)
                    if event.get("native_id") == _UUID_ONE]
            mine = own_segment(world.store_folder, MACHINE)
        self.assertEqual(again.sources[0].new_events, 1)
        self.assertEqual(len(held), 1)
        self.assertEqual(held[0]["machine"], OTHER_MACHINE)
        self.assertEqual([event.get("native_id") for event in mine], [_UUID_TWO])

    def test_development_version_needs_variable(self) -> None:
        """A version with a development mark writes to the store only when the environment
        gives `AI_EFFORT_LEDGER_DEVELOPMENT` as `1`: the ingestion stops with
        `development_version` before it takes the lock, and runs with the variable set."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            write_prompt_session(world.logs, world.home / "work")
            with self.assertRaises(ingestion.DevelopmentVersion) as stopped:
                ingest(world, version="0.1.0.dev0", environ={})
            with self.assertRaises(ingestion.DevelopmentVersion):
                ingest(world, environ={})
            self.assertEqual(stopped.exception.code, "development_version")
            self.assertEqual(stopped.exception.values, {})
            self.assertEqual(stopped.exception.exit_code, 1)
            self.assertFalse((world.machine_folder / "stores").exists())
            allowed = ingest(world, version="0.1.0.dev0",
                             environ={"AI_EFFORT_LEDGER_DEVELOPMENT": "1"})
        self.assertEqual(sum(result.new_events for result in allowed.sources), 1)

    def test_counts_by_folder(self) -> None:
        """One result per folder of native logs, in the order of the machine configuration,
        with its new events and its sessions held back: a settled session counts its events,
        a held-back session counts itself and no event."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            more = world.home / ".claude" / "more-projects"
            more.mkdir(parents=True)
            write_prompt_session(world.logs, world.home / "work")
            support.write_session(more, "session-two",
                                  [support.tool_use("Edit", "toolu_1",
                                                    {"file_path": "invented.py"}, _TOOL_AT,
                                                    _UUID_TWO, "msg_tool_01")],
                                  {}, world.home / "work")
            touch([more / "session-two.jsonl"])
            result = ingest(world, machine=machine_for([world.logs, more]))
        self.assertEqual(len(result.sources), 2)
        self.assertEqual(result.sources[0],
                         ingestion.SourceResult("claude-code-jsonl", str(world.logs), 1, 0))
        self.assertEqual(result.sources[1],
                         ingestion.SourceResult("claude-code-jsonl", str(more), 0, 1))

    def test_held_back_session_counts_for_retention(self) -> None:
        """The retention reads the project settings of the folder of a session it holds back
        too: the local setting of 7 days of its folder wins over the person setting of 30, so
        a gap of 10 days warns of lost events (ruled 2026-11-20)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            (world.logs.parent / "settings.json").write_text(
                '{"cleanupPeriodDays": 30}\n', encoding="utf-8")
            product = world.home / "work" / "product"
            (product / ".claude").mkdir(parents=True)
            (product / ".claude" / "settings.local.json").write_text(
                '{"cleanupPeriodDays": 7}\n', encoding="utf-8")
            support.write_session(world.logs, "session-one",
                                  [support.tool_use("Edit", "toolu_1",
                                                    {"file_path": "invented.py"}, _TOOL_AT,
                                                    _UUID_ONE, "msg_tool_01")],
                                  {}, product)
            touch([world.logs / "session-one.jsonl"])
            previous = ingestion.SourcesState()
            previous.folders[str(world.logs)] = "2026-11-10T12:00:00.000Z"
            previous.save(ingestion.sources_path(world.machine_folder, world.store_folder,
                                                 running_system()))
            result = ingest(world)
        self.assertEqual(result.sources[0],
                         ingestion.SourceResult("claude-code-jsonl", str(world.logs), 0, 1))
        lost = [warning for warning in result.warnings if warning["code"] == "lost_events"]
        self.assertEqual(lost, [{"code": "lost_events", "values": {
            "folder": str(world.logs),
            "from": "2026-11-10T12:00:00.000Z",
            "to": events.format_instant(NOW)}}])

    def test_a_folder_two_tools_record_is_read_once(self) -> None:
        """A machine configuration that records one folder of native logs for two agent
        tools of one adapter reads the folder once, for the first tool of the adapter, and
        gives one result for the folder, with a warning that names the folder and both
        tools: a wrong recording of the machine configuration must be loud, never a doubled
        reading of the same sessions (ingestion.md › Adapters)."""
        with support.TemporaryFolder() as base:
            world = build_world(base)
            folder = world.home / "recorded-twice"
            (folder / ".claude" / "projects").mkdir(parents=True)
            support.write_session(folder, "session-one", [prompt_of(_UUID_ONE)], {},
                                  world.home / "work")
            support.write_session(folder / ".claude" / "projects", "session-one",
                                  [prompt_of(_UUID_ONE)], {}, world.home / "work")
            settle([folder / "session-one.jsonl",
                    folder / ".claude" / "projects" / "session-one.jsonl"])
            machine = configuration.MachineConfiguration(
                machine=MACHINE, installation=None, salt=None, store=None,
                native_logs={"claude-code": [str(folder)],
                             "claude-desktop": [str(folder)]})
            result = ingest(world, machine=machine)
            stored = stored_events(world.store_folder)
        self.assertEqual(len(result.sources), 1)
        self.assertEqual(result.sources[0],
                         ingestion.SourceResult("claude-code-jsonl", str(folder), 1, 0))
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0]["tool"], "claude-code")
        self.assertEqual(result.warnings, [{"code": "ambiguous_folder", "values": {
            "folder": str(folder), "tools": ["claude-code", "claude-desktop"]}}])
