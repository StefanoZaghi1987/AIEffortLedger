"""Tests of the `claude_code` adapter: the folders of native logs of its agent tools, the
sessions of a folder of native logs, the reading of the files of a session, the invocation
that each entrypoint of a record gives, the forked sessions of a reading, and the retention
that the settings files of Claude Code give each of its agent tools."""

import json
import os
import platform
import unittest
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from unittest import mock

import support
from ai_effort_ledger import adapters
from ai_effort_ledger.adapters import claude_code
from ai_effort_ledger.adapters.claude_code import size

_HOME = Path("/home/person")
_INSTANT = "2026-03-01T09:15:00.000Z"
_UUID = "3f1c0000-0000-4000-8000-000000000001"
_SETTLE = 14400
_FIXTURES = Path(__file__).resolve().parent / "fixtures" / "claude_code"
_RESPONSE_SESSION = "33333333-3333-5333-9333-333333333333"
_TOOL_USE_SESSION = "88888888-8888-5888-9888-888888888888"
_MOMENT = "2026-03-01T12:00"
_MARKERS = [
    ("absent_tokens", "duskmeadow"),
    ("agent_text_result", "wrenlow"),
    ("cache_write_5m", "corrlight"),
    ("categories", "kelpward"),
    ("empty_message_id", "sablefen"),
    ("missing_message", "thornwick"),
    ("model_angle", "gorsevale"),
    ("question_tools", "inkwold"),
    ("queue_blocks", "galewick"),
    ("queue_two", "mosswell"),
    ("requests_price", "emberlot"),
    ("resumed", "nettlefold"),
    ("response_lines", "fennwick"),
    ("server_mcp", "jerquay"),
    ("size_counters", "marlford"),
    ("tool_result", "loomfeather"),
    ("tool_use", "hollowbrook"),
]
_PERSON_MARKERS = [
    ("prompt", "bramblewick"),
    ("decisions", "wexholm"),
    ("interruption", "quinmere"),
    ("interruption_blocks", "dovengate"),
    ("interruption_image", "thistleburn"),
    ("interrupted_records", "ellersmoor"),
    ("meta_records", "ilverton"),
    ("no_event_types", "ombervale"),
    ("notifications", "ferndean"),
    ("notification_with_results", "trelver"),
    ("origin_unknown", "pelmworth"),
    ("parent_input", "netherby"),
    ("prompt_no_uuid", "terswell"),
    ("permission_other", "brantmere"),
    ("permission_person", "harrowdene"),
    ("permission_rule", "sterley"),
    ("permission_two", "ostlewick"),
    ("prompt_headless", "calderbank"),
    ("prompt_no_origin", "skirbeck"),
    ("prompt_no_origin_blocks", "hallowfield"),
    ("queue_tag", "tarnhold"),
    ("unknown_structure", "crowsend"),
]
_FORK_PROMPT = "3f1c0000-0000-4000-8000-000000000501"
_FORK_OWN = "3f1c0000-0000-4000-8000-000000000504"
_TWO_FOLDERS_OLD = "3f1c0000-0000-4000-8000-000000000541"
_TWO_FOLDERS_NEW = "3f1c0000-0000-4000-8000-000000000542"
_BEFORE = "2026-03-01T09:00:00.000Z"
_BETWEEN = "2026-03-01T09:16:00.000Z"
_LAST_SHARED = "2026-03-01T09:17:00.000Z"
_AFTER = "2026-03-01T09:18:00.000Z"


def _fixture_records(name: str, agent: str = "") -> list[adapters.SessionRecord]:
    """The records of a fixture as the rows of one file of the session, of the main agent
    unless another agent names the file."""
    lines = (_FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8").splitlines()
    return [adapters.SessionRecord(agent, 0, number, json.loads(line))
            for number, line in enumerate(lines, start=1) if line.strip()]


def _mapped(name: str) -> tuple[list[dict], list[dict]]:
    """The events and warnings that the mapping of one fixture gives."""
    return claude_code.map_session(_fixture_records(name), "claude-code", "machine-one")


def _of_kind(events: list[dict], kind: str) -> list[dict]:
    """The events of one kind, in the order that the mapping wrote them."""
    return [event for event in events if event["kind"] == kind]


def _counters_of(events: list[dict], call_id: str) -> dict[str, object]:
    """The size counters that the event of one use of a tool holds, without the counter fields
    that it does not hold."""
    calls = {call["call_id"]: call for call in _of_kind(events, "tool_call")}
    call = calls[call_id]
    return {key: call[key] for key in
            ("lines_added", "lines_removed", "file_ext", "size_basis") if key in call}


def _no_owner(session_id: str, native_id: str) -> tuple[str, str] | None:
    """The lookup of a native identifier that names no session in the store."""
    return None


def _places(warnings: list[dict]) -> list[tuple[str, int]]:
    """The file and the line of each warning about a record that is not a valid record."""
    return [(warning["values"]["file"], warning["values"]["line"])
            for warning in warnings if warning["code"] == "invalid_record"]


def _read_session(
    main: list[dict], subagents: dict[str, list[dict]]
) -> adapters.ReadResult:
    """The result of reading one session of identifier `session-1`: the helper writes its
    files into a folder of native logs and settles them before the reading."""
    adapter = claude_code.ClaudeCodeAdapter()
    moment = support.utc(_MOMENT)
    context = adapters.ReadContext("machine-one", moment, _SETTLE, _no_owner)
    with support.TemporaryFolder() as folder:
        projects = folder / "projects"
        projects.mkdir()
        support.write_session(projects, "session-1", main, subagents, folder / "work")
        sessions = adapter.sessions("claude-code", projects)
        past = moment.timestamp() - _SETTLE
        for session in sessions:
            for path in [session.main, *session.subagents.values()]:
                if path is not None:
                    os.utime(path, (past, past))
        return adapter.read_sessions(sessions, context)


def _mapped_session(records: list[dict]) -> list[dict]:
    """The events that the mapping of the records of one session gives; the tests of the
    forks build the sessions of a reading out of these events."""
    rows = [adapters.SessionRecord("", 0, number, record)
            for number, record in enumerate(records, start=1)]
    events, _ = claude_code.map_session(rows, "claude-code", "machine-one")
    return events


def _forked_pair() -> tuple[list[dict], list[dict]]:
    """The records of a session and of the forked session that copied its first and its last
    record: the original holds a response of its own between the shared records, and the fork
    holds an input of its own after the last shared record."""
    origin = [
        support.prompt_record(
            "Invented text of the person with the vesperholt word.", _INSTANT, _FORK_PROMPT),
        support.output_record(
            "Invented response text.", _BETWEEN,
            "3f1c0000-0000-4000-8000-000000000502", "msg_origin_own"),
        support.output_record(
            "More invented response text.", _LAST_SHARED,
            "3f1c0000-0000-4000-8000-000000000503", "msg_fork_last"),
    ]
    fork = [
        support.prompt_record(
            "Invented text of the person with the vesperholt word.", _INSTANT, _FORK_PROMPT),
        support.output_record(
            "More invented response text.", _LAST_SHARED,
            "3f1c0000-0000-4000-8000-000000000503", "msg_fork_last"),
        support.prompt_record(
            "Invented input of the person with the cranmoor word.", _AFTER, _FORK_OWN),
    ]
    return origin, fork


def _server_record(call_id: str, uuid_value: str, message_id: str) -> dict:
    """A record of the agent whose content holds one use of a tool that the provider runs
    inside its response; the text is invented."""
    record = support.output_record("Invented provider text.", _INSTANT, uuid_value, message_id)
    record["message"]["content"].append({
        "type": "server_tool_use",
        "id": call_id,
        "name": "web_search",
        "input": {"query": "invented"},
    })
    return record


def _complete(rows: list[adapters.SessionRecord], settled: bool) -> tuple[list[dict], bool]:
    """What the pipeline of the reading keeps from the rows: the mapping, the link of the
    subagents, and the gate of completeness."""
    events, _ = claude_code.map_session(rows, "claude-code", "machine-one")
    claude_code.link_subagents(events, rows)
    return claude_code.complete_events(events, rows, settled)


_SYSTEM = platform.system()


def _write_settings(path: Path, values: dict[str, int]) -> Path:
    """Write one settings file of Claude Code, with the given values, into its folder."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def _retention_of(
    tool: str,
    folder: Path,
    native_logs: Mapping[str, Sequence[str]] | None = None,
    project_folders: Iterable[str] = (),
    environ: Mapping[str, str] | None = None,
) -> adapters.Retention:
    """The retention that the settings files of a temporary folder give one agent tool: the
    adapter of the tests reads the managed file of the folder, so that no test reads the
    managed file of the machine that runs the tests."""
    return support.adapters_for_tests(folder).retention(
        tool, environ or {}, folder, _SYSTEM, native_logs or {}, project_folders)


class TestMarkerTables(unittest.TestCase):
    """The two tables of marker words of this module against the folder of fixtures: every
    fixture but `invalid_line`, which the tests of the reading open by name, is named in one
    of the tables, so a fixture added to the folder without its marker cannot skip the
    checks that the events of the mapping hold no text."""

    def test_tables_name_every_fixture_but_invalid_line(self) -> None:
        names = [name for name, _ in _MARKERS] + [name for name, _ in _PERSON_MARKERS]
        stems = [path.stem for path in _FIXTURES.glob("*.jsonl") if path.stem != "invalid_line"]
        self.assertEqual(sorted(names), sorted(stems))


class TestSurface(unittest.TestCase):
    """The surface of the adapters package and of the claude_code adapter."""

    def test_adapters_surface(self) -> None:
        self.assertEqual(sorted(adapters.__all__), [
            "ADAPTERS", "Adapter", "ClaudeCodeAdapter", "ENTRYPOINTS", "ReadContext",
            "ReadResult", "Retention", "SOURCE", "SessionFiles", "SessionRecord",
            "TOOL_CATEGORIES", "complete_events", "deduplicate", "event_identifiers",
            "link_subagents", "map_session", "read_file"])
        self.assertEqual(len(adapters.ADAPTERS), 1)
        self.assertIsInstance(adapters.ADAPTERS[0], claude_code.ClaudeCodeAdapter)

    def test_source_and_tools(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        self.assertEqual(adapter.source, "claude-code-jsonl")
        self.assertEqual(adapter.tools, ("claude-code", "claude-desktop"))

    def test_result_types(self) -> None:
        moment = support.utc("2026-03-01T12:00")
        context = adapters.ReadContext("machine-one", moment, _SETTLE, _no_owner)
        self.assertEqual(context, ("machine-one", moment, _SETTLE, _no_owner))
        self.assertEqual(
            adapters.ReadResult([], set(), [], set()), ([], set(), [], set()))
        self.assertEqual(
            adapters.SessionFiles("claude-code", "session-1", Path("/logs"), None, {}),
            ("claude-code", "session-1", Path("/logs"), None, {}))
        self.assertEqual(
            adapters.Retention("cleanupPeriodDays", 30), ("cleanupPeriodDays", 30))


class TestDefaultFolders(unittest.TestCase):
    """The folders of native logs that each agent tool uses on each operating system, as pure
    paths of that system, built also when they do not exist."""

    def test_default_folders(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        found = adapter.default_folders({"CLAUDE_CONFIG_DIR": "/claude-config"}, _HOME, "Linux")
        self.assertEqual(found, {
            "claude-code": [PurePosixPath("/claude-config/projects")],
            "claude-desktop": []})
        found = adapter.default_folders({}, _HOME, "Linux")
        self.assertEqual(found, {
            "claude-code": [PurePosixPath("/home/person/.claude/projects")],
            "claude-desktop": []})
        found = adapter.default_folders(
            {"CLAUDE_CONFIG_DIR": r"C:\Config", "APPDATA": r"C:\Users\Person\AppData\Roaming"},
            Path(r"C:\Users\Person"), "Windows")
        self.assertIsInstance(found["claude-code"][0], PureWindowsPath)
        self.assertNotIsInstance(found["claude-code"][0], Path)
        self.assertEqual(found, {
            "claude-code": [PureWindowsPath(r"C:\Config\projects")],
            "claude-desktop": [PureWindowsPath(
                r"C:\Users\Person\AppData\Roaming\Claude\local-agent-mode-sessions")]})
        found = adapter.default_folders({}, Path(r"C:\Users\Person"), "Windows")
        self.assertEqual(found, {
            "claude-code": [PureWindowsPath(r"C:\Users\Person\.claude\projects")],
            "claude-desktop": [PureWindowsPath(
                r"C:\Users\Person\AppData\Roaming\Claude\local-agent-mode-sessions")]})

    def test_desktop_folder_on_macos(self) -> None:
        found = claude_code.ClaudeCodeAdapter().default_folders({}, _HOME, "Darwin")
        self.assertEqual(found, {
            "claude-code": [PurePosixPath("/home/person/.claude/projects")],
            "claude-desktop": [PurePosixPath(
                "/home/person/Library/Application Support/Claude/"
                "local-agent-mode-sessions")]})


class TestSessions(unittest.TestCase):
    """The sessions that a folder of native logs holds, and the search below the recorded
    folder of Claude Desktop."""

    def test_sessions_of_a_folder(self) -> None:
        record = support.prompt_record("Invented text.", _INSTANT, _UUID)
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            support.write_session(
                projects, "session-1", [record],
                {"a1": [support.prompt_record("Invented for the agent.", _INSTANT, _UUID)]},
                folder / "work")
            support.write_session(projects, "session-2", [], {"b2": [record]}, folder / "work")
            (projects / "notes.txt").write_text("invented", encoding="utf-8")
            (projects / "plain").mkdir()
            (projects / "plain" / "keep.jsonl").write_text("invented", encoding="utf-8")
            found = claude_code.ClaudeCodeAdapter().sessions("claude-code", projects)
        self.assertEqual(found, [
            adapters.SessionFiles(
                "claude-code", "session-1", projects, projects / "session-1.jsonl",
                {"a1": projects / "session-1" / "subagents" / "agent-a1.jsonl"}),
            adapters.SessionFiles(
                "claude-code", "session-2", projects, None,
                {"b2": projects / "session-2" / "subagents" / "agent-b2.jsonl"}),
        ])

    def test_sessions_of_a_missing_folder(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        with support.TemporaryFolder() as folder:
            found = adapter.sessions("claude-code", folder / "gone")
            desktop = adapter.sessions("claude-desktop", folder / "also-gone")
        self.assertEqual(found, [])
        self.assertEqual(desktop, [])

    def test_a_folder_lost_after_its_check_holds_no_session(self) -> None:
        """The agent tool can delete the folder of native logs while the walk holds it,
        between the check that found the folder and the listing of its entries — a window
        between two lines of the walk that no test can reach, so the listing raises the
        `FileNotFoundError` that the listing of the deleted folder raises: a folder that
        is not there holds no session, and the walk raises nothing
        (claude-code-adapter.md › Native logs)."""
        adapter = claude_code.ClaudeCodeAdapter()
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            support.write_session(
                projects, "session-1",
                [support.prompt_record("Invented text of the session.", _INSTANT, _UUID)],
                {}, folder / "work")
            listing = Path.iterdir

            def vanishing(source, *arguments, **keywords):
                """The listing of every folder but the one that the agent tool deleted
                between the check and the listing."""
                if source == projects:
                    raise FileNotFoundError(2, "The system cannot find the path specified")
                return listing(source, *arguments, **keywords)

            with mock.patch.object(Path, "iterdir", vanishing):
                found = adapter.sessions("claude-code", projects)
        self.assertEqual(found, [])

    def test_a_session_lost_before_its_subagents_keeps_the_rest(self) -> None:
        """The agent tool can delete the folder of subagents of a session while the walk
        holds it, between the check that found it and the listing of its files — a window
        between two lines of the walk that no test can reach, so the listing raises the
        `FileNotFoundError` that the listing of the deleted folder raises: that session
        holds no subagent, the walk raises nothing, and the sessions that the rest of
        the folder holds are still found, the session of the lost subagents with its
        main file (claude-code-adapter.md › Native logs)."""
        adapter = claude_code.ClaudeCodeAdapter()
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            record = support.prompt_record("Invented text of the session.", _INSTANT, _UUID)
            support.write_session(projects, "session-1", [record], {}, folder / "work")
            support.write_session(projects, "session-2", [record],
                                  {"b2": [record]}, folder / "work")
            subagents = projects / "session-2" / "subagents"
            listing = Path.glob

            def vanishing(source, *arguments, **keywords):
                """The listing of every folder but the one that the agent tool deleted
                between the check and the listing."""
                if source == subagents:
                    raise FileNotFoundError(2, "The system cannot find the path specified")
                return listing(source, *arguments, **keywords)

            with mock.patch.object(Path, "glob", vanishing):
                found = adapter.sessions("claude-code", projects)
        self.assertEqual(found, [
            adapters.SessionFiles("claude-code", "session-1", projects,
                                  projects / "session-1.jsonl", {}),
            adapters.SessionFiles("claude-code", "session-2", projects,
                                  projects / "session-2.jsonl", {}),
        ])

    def test_desktop_folders_are_searched(self) -> None:
        record = support.prompt_record("Invented text.", _INSTANT, _UUID)
        with support.TemporaryFolder() as folder:
            recorded = folder / "Claude" / "local-agent-mode-sessions"
            first = recorded / "one" / ".claude" / "projects"
            second = recorded / "two" / "deep" / ".claude" / "projects"
            support.write_session(first, "session-1", [record], {}, folder / "work")
            support.write_session(second, "session-2", [], {"b2": [record]}, folder / "work")
            found = claude_code.ClaudeCodeAdapter().sessions("claude-desktop", recorded)
        self.assertEqual(found, [
            adapters.SessionFiles(
                "claude-desktop", "session-1", first, first / "session-1.jsonl", {}),
            adapters.SessionFiles(
                "claude-desktop", "session-2", second, None,
                {"b2": second / "session-2" / "subagents" / "agent-b2.jsonl"}),
        ])


class TestReadFile(unittest.TestCase):
    """The reading of one file of a native log, line by line, with each line decoded on its
    own."""

    def test_invalid_json_line_warns(self) -> None:
        with support.TemporaryFolder() as folder:
            path = folder / "one.jsonl"
            lines = [
                json.dumps(support.prompt_record("Invented text.", _INSTANT, _UUID)),
                "this line is not JSON",
                json.dumps(support.prompt_record("More invented text.", _INSTANT, _UUID)),
            ]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            records, unread, warnings = claude_code.read_file(path, settled=True)
        self.assertEqual([number for number, _ in records], [1, 3])
        self.assertFalse(unread)
        self.assertEqual(
            warnings, [{"code": "invalid_record", "values": {"file": str(path), "line": 2}}])

    def test_invalid_utf8_line_is_invalid_record(self) -> None:
        with support.TemporaryFolder() as folder:
            path = folder / "two.jsonl"
            head = json.dumps(support.prompt_record("Invented text.", _INSTANT, _UUID))
            path.write_bytes(head.encode("utf-8") + b"\n" + b"a line \xff not UTF-8\n")
            records, unread, warnings = claude_code.read_file(path, settled=True)
        self.assertEqual([number for number, _ in records], [1])
        self.assertFalse(unread)
        self.assertEqual(
            warnings, [{"code": "invalid_record", "values": {"file": str(path), "line": 2}}])

    def test_partial_last_line_is_not_read_without_warning(self) -> None:
        with support.TemporaryFolder() as folder:
            path = folder / "three.jsonl"
            first = json.dumps(support.prompt_record("Invented text.", _INSTANT, _UUID))
            second = json.dumps(support.prompt_record("More invented text.", _INSTANT, _UUID))
            path.write_text(first + "\n" + second, encoding="utf-8")
            records, unread, warnings = claude_code.read_file(path, settled=False)
            self.assertEqual([number for number, _ in records], [1])
            self.assertTrue(unread)
            self.assertEqual(warnings, [])
            records, unread, warnings = claude_code.read_file(path, settled=True)
            self.assertEqual([number for number, _ in records], [1, 2])
            self.assertFalse(unread)
            self.assertEqual(warnings, [])

    def test_15_bad_lines_give_10_warnings_and_one_summary(self) -> None:
        """A file that holds more lines that give no record than the reading names warns its
        first 10 with the file and the line, and one warning names the count of all the bad
        lines of the file (claude-code-adapter.md › Native logs)."""
        with support.TemporaryFolder() as folder:
            path = folder / "many.jsonl"
            lines = [f"a line {number} that is not JSON" for number in range(1, 16)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            records, unread, warnings = claude_code.read_file(path, settled=True)
        self.assertEqual(records, [])
        self.assertFalse(unread)
        self.assertEqual([warning["code"] for warning in warnings],
                         ["invalid_record"] * 10 + ["invalid_records_summary"])
        self.assertEqual([warning["values"] for warning in warnings[:10]],
                         [{"file": str(path), "line": number} for number in range(1, 11)])
        self.assertEqual(warnings[10], {"code": "invalid_records_summary",
                                        "values": {"file": str(path), "count": 15}})

    def test_the_summary_counts_only_the_lines_that_give_no_record(self) -> None:
        """A line that gives a record is no bad line: the count of the summary names the
        lines that give no record only, and the named lines keep their own numbers."""
        with support.TemporaryFolder() as folder:
            path = folder / "mixed.jsonl"
            good = json.dumps(support.prompt_record("Invented text.", _INSTANT, _UUID))
            lines = [good if number == 5 else f"a line {number} that is not JSON"
                     for number in range(1, 16)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            records, unread, warnings = claude_code.read_file(path, settled=True)
        self.assertEqual([number for number, _ in records], [5])
        self.assertFalse(unread)
        self.assertEqual([warning["values"]["line"] for warning in warnings[:10]],
                         [1, 2, 3, 4, 6, 7, 8, 9, 10, 11])
        self.assertEqual(warnings[10], {"code": "invalid_records_summary",
                                        "values": {"file": str(path), "count": 14}})

    def test_10_bad_lines_need_no_summary(self) -> None:
        """A file whose lines all give no record warns each of the first 10 by name; one
        more bad line brings the summary with its count."""
        for total, codes in ((10, ["invalid_record"] * 10), (11, ["invalid_record"] * 10
                                                            + ["invalid_records_summary"])):
            with self.subTest(total=total), support.TemporaryFolder() as folder:
                path = folder / f"{total}.jsonl"
                lines = [f"a line {number} that is not JSON" for number in range(1, total + 1)]
                path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                records, unread, warnings = claude_code.read_file(path, settled=True)
                self.assertEqual(records, [])
                self.assertFalse(unread)
                self.assertEqual([warning["code"] for warning in warnings], codes)
                if len(codes) == 11:
                    self.assertEqual(warnings[10]["values"],
                                     {"file": str(path), "count": 11})

    def test_a_break_less_last_bad_line_settled_crosses_the_cap(self) -> None:
        """A last line without a line break that gives no record crosses the cap of the named
        lines once the file is settled: the reading reads it, counts it among the bad lines
        of the file, and the summary names the count of all of them; while the file is not
        settled the line stays unread, the count stays at the named 10, and no summary
        fires (claude-code-adapter.md › Native logs)."""
        with support.TemporaryFolder() as folder:
            path = folder / "open.jsonl"
            lines = [f"a line {number} that is not JSON" for number in range(1, 11)]
            path.write_text("\n".join(lines) + "\n" + "a line 11 that is not JSON",
                            encoding="utf-8")
            records, unread, warnings = claude_code.read_file(path, settled=True)
            self.assertEqual(records, [])
            self.assertFalse(unread)
            self.assertEqual([warning["code"] for warning in warnings],
                             ["invalid_record"] * 10 + ["invalid_records_summary"])
            self.assertEqual([warning["values"]["line"] for warning in warnings[:10]],
                             list(range(1, 11)))
            self.assertEqual(warnings[10]["values"], {"file": str(path), "count": 11})
            records, unread, warnings = claude_code.read_file(path, settled=False)
            self.assertEqual(records, [])
            self.assertTrue(unread)
            self.assertEqual([warning["code"] for warning in warnings],
                             ["invalid_record"] * 10)

    def test_unknown_record_type_warns_once_per_type_and_version(self) -> None:
        with support.TemporaryFolder() as folder:
            path = folder / "four.jsonl"
            unknown = support.prompt_record("Invented text.", _INSTANT, _UUID)
            unknown["type"] = "new-kind"
            again = support.prompt_record("More invented text.", _INSTANT, _UUID)
            again["type"] = "new-kind"
            other = support.prompt_record("And more invented text.", _INSTANT, _UUID)
            other["type"] = "new-kind"
            other["version"] = "9.9.9"
            known = support.prompt_record("Still invented text.", _INSTANT, _UUID)
            lines = [json.dumps(record) for record in (unknown, again, other, known)]
            path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            records, unread, warnings = claude_code.read_file(path, settled=True)
        self.assertEqual(len(records), 4)
        self.assertFalse(unread)
        self.assertEqual(
            [warning["code"] for warning in warnings],
            ["unknown_record_type", "unknown_record_type"])
        self.assertEqual(
            [warning["values"] for warning in warnings],
            [{"type": "new-kind", "version": support.VERSION},
             {"type": "new-kind", "version": "9.9.9"}])


class TestReadSessions(unittest.TestCase):
    """The reading of whole sessions: the warnings of their files, and no event yet."""

    def test_read_sessions_gives_warnings_of_files(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        moment = support.utc("2026-03-01T12:00")
        context = adapters.ReadContext("machine-one", moment, _SETTLE, _no_owner)
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            projects.mkdir()
            main = support.copy_fixture("invalid_line", projects, folder / "work")
            with main.open("ab") as stream:
                stream.write(b"a line still being written")
            whole = support.copy_fixture("prompt", projects, folder / "work")
            agent = projects / "invalid_line" / "subagents" / "agent-a1.jsonl"
            agent.parent.mkdir(parents=True)
            agent.write_text(main.read_text(encoding="utf-8"), encoding="utf-8")
            found = adapter.sessions("claude-code", projects)
            self.assertEqual(
                [session.session_id for session in found], ["invalid_line", "prompt"])
            for path in (main, agent, whole):
                os.utime(path, (moment.timestamp(), moment.timestamp()))
            fresh = adapter.read_sessions(found, context)
            self.assertEqual([event["kind"] for event in fresh.events],
                             ["prompt", "prompt"])
            self.assertEqual(fresh.held_back, {("claude-code", "invalid_line")})
            self.assertEqual(fresh.unknown_tools, set())
            self.assertEqual(_places(fresh.warnings), [(str(main), 2), (str(agent), 2)])
            past = moment.timestamp() - _SETTLE
            for path in (main, agent, whole):
                os.utime(path, (past, past))
            settled = adapter.read_sessions(found, context)
            self.assertEqual([event["kind"] for event in settled.events],
                             ["prompt", "prompt"])
            self.assertEqual(settled.held_back, set())
            self.assertEqual(_places(settled.warnings), [
                (str(main), 2), (str(main), 3), (str(agent), 2), (str(agent), 3)])

    def test_a_file_gone_after_the_selection_warns_and_gives_no_event(self) -> None:
        """The agent tool can delete a file of a session between the selection that found
        the sessions and the reading of their files: a file that is gone is a file that is
        gone — the reading completes, gives no event from it, and warns once with the file
        (ingestion.md › Frequency names deletion a case that warns and completes)."""
        adapter = claude_code.ClaudeCodeAdapter()
        moment = support.utc(_MOMENT)
        context = adapters.ReadContext("machine-one", moment, _SETTLE, _no_owner)
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            projects.mkdir()
            support.write_session(
                projects, "session-1",
                [support.prompt_record("Invented text of the kept session.", _INSTANT,
                                       _UUID)],
                {}, folder / "work")
            support.write_session(
                projects, "session-2",
                [support.prompt_record("Invented text of the gone session.", _INSTANT,
                                       _UUID)],
                {}, folder / "work")
            found = adapter.sessions("claude-code", projects)
            past = moment.timestamp() - _SETTLE
            for session in found:
                for path in [session.main, *session.subagents.values()]:
                    if path is not None:
                        os.utime(path, (past, past))
            gone = projects / "session-2.jsonl"
            gone.unlink()
            result = adapter.read_sessions(found, context)
        self.assertEqual([event["session_id"] for event in result.events], ["session-1"])
        self.assertEqual([event["kind"] for event in result.events], ["prompt"])
        self.assertEqual(result.held_back, set())
        self.assertEqual(
            result.warnings,
            [{"code": "native_log_gone", "values": {"file": str(gone)}}])

    def test_a_session_of_two_folders_of_one_tool_is_read_once(self) -> None:
        """Two folders of native logs that the machine configuration records for one agent
        tool can hold the same session identifier, one with the newer records and one with an
        older copy: the reading of the folder recorded first wins and loses nothing, and the
        reading of the later folder is skipped with one warning that names both folders and
        the session, so the loss of the later reading is never silent."""
        adapter = claude_code.ClaudeCodeAdapter()
        context = adapters.ReadContext("machine-one", support.utc(_MOMENT), _SETTLE, _no_owner)
        older = support.prompt_record(
            "Invented text of the person with the rayfield word.",
            "2026-03-01T09:00:00.000Z", _TWO_FOLDERS_OLD)
        newer = support.prompt_record(
            "More invented text of the person.", "2026-03-01T09:05:00.000Z", _TWO_FOLDERS_NEW)
        with support.TemporaryFolder() as folder:
            live = folder / "live"
            stale = folder / "stale"
            live.mkdir()
            stale.mkdir()
            support.write_session(live, "session-1", [older, newer], {}, folder / "work")
            support.write_session(stale, "session-1", [dict(older)], {}, folder / "work")
            past = support.utc(_MOMENT).timestamp() - _SETTLE
            for projects in (live, stale):
                for session in adapter.sessions("claude-code", projects):
                    for path in [session.main, *session.subagents.values()]:
                        if path is not None:
                            os.utime(path, (past, past))
            live_first = adapter.read_sessions(
                adapter.sessions("claude-code", live)
                + adapter.sessions("claude-code", stale), context)
            stale_first = adapter.read_sessions(
                adapter.sessions("claude-code", stale)
                + adapter.sessions("claude-code", live), context)
        self.assertEqual(
            [event["native_id"] for event in live_first.events],
            [_TWO_FOLDERS_OLD, _TWO_FOLDERS_NEW])
        self.assertEqual(live_first.warnings, [{
            "code": "ambiguous_session_folder",
            "values": {"session_id": "session-1",
                       "first": str(live), "second": str(stale)}}])
        self.assertEqual(
            [event["native_id"] for event in stale_first.events], [_TWO_FOLDERS_OLD])
        self.assertEqual(stale_first.warnings, [{
            "code": "ambiguous_session_folder",
            "values": {"session_id": "session-1",
                       "first": str(stale), "second": str(live)}}])


class TestRecordsWithoutInstant(unittest.TestCase):
    """The records that give no event need no instant; an unknown type warns once."""

    def test_reading_warns_once_for_unknown_type_and_never_for_known_no_event_type(
        self
    ) -> None:
        unknown = {"type": "invented-record-type", "version": support.VERSION}
        mode = {"type": "permission-mode", "sessionId": "session-1"}
        result = _read_session([unknown, mode], {})
        self.assertEqual(result.events, [])
        self.assertEqual([w["code"] for w in result.warnings], ["unknown_record_type"])


class TestEntrypoints(unittest.TestCase):
    """The invocation that each value of the entrypoint of a record gives."""

    def test_entrypoints(self) -> None:
        self.assertEqual(claude_code.ENTRYPOINTS, {
            "cli": "interactive",
            "local-agent": "interactive",
            "sdk-cli": "headless",
            "sdk-ts": "headless",
            "sdk-py": "headless",
        })
        of = claude_code.invocation_of
        self.assertEqual(of({"entrypoint": "cli"}), ("interactive", None))
        self.assertEqual(of({"entrypoint": "local-agent"}), ("interactive", None))
        self.assertEqual(of({"entrypoint": "sdk-cli"}), ("headless", None))
        self.assertEqual(of({"entrypoint": "sdk-ts"}), ("headless", None))
        self.assertEqual(of({"entrypoint": "sdk-py"}), ("headless", None))
        self.assertEqual(
            of({"entrypoint": "x-new"}),
            ("unknown", {"code": "unknown_entrypoint", "values": {"value": "x-new"}}))
        self.assertEqual(of({}), ("unknown", None))


class TestMapping(unittest.TestCase):
    """The mapping of the records of the agent to events, one test for each row of the table of
    records and of the tables of token categories, and price factors, from its fixture."""

    def test_response_on_three_lines_is_one_agent_output(self) -> None:
        events, warnings = _mapped("response_lines")
        self.assertEqual(warnings, [])
        outputs = _of_kind(events, "agent_output")
        self.assertEqual(len(outputs), 1)
        out = outputs[0]
        self.assertEqual(out["native_id"], "msg_response_01")
        self.assertEqual(out["event_uid"], "msg_response_01")
        self.assertEqual(out["tokens"], {"input": 30, "output": 20, "cache_read": 7,
                                         "cache_write_5m": 3, "cache_write_1h": 2})
        self.assertEqual(out["timestamp"], "2026-11-19T09:00:00.300Z")
        self.assertEqual(out["source"], "claude-code-jsonl")
        self.assertEqual(out["source_format"], support.VERSION)
        self.assertEqual(out["session_id"], _RESPONSE_SESSION)
        self.assertEqual(out["actor"], "agent")
        self.assertEqual(out["invocation"], "interactive")
        self.assertEqual(out["agent_id"], _RESPONSE_SESSION)
        self.assertEqual(out["machine"], "machine-one")
        self.assertEqual(out["tool"], "claude-code")
        self.assertEqual(len(events), 1)

    def test_cache_write_5m_without_cache_creation(self) -> None:
        events, _ = _mapped("cache_write_5m")
        out = _of_kind(events, "agent_output")[0]
        self.assertEqual(out["tokens"], {"input": 5, "output": 6, "cache_write_5m": 100})
        self.assertNotIn("cache_write_1h", out["tokens"])

    def test_cache_write_5m_fallback_takes_the_response_write_1h(self) -> None:
        first = support.output_record("First invented word.", _INSTANT, _UUID, "msg_mixed_01")
        first["message"]["usage"] = {"cache_creation": {"ephemeral_1h_input_tokens": 9}}
        second = support.output_record("Second invented word.", _INSTANT, _UUID, "msg_mixed_01")
        second["message"]["usage"] = {"cache_creation_input_tokens": 14}
        rows = [adapters.SessionRecord("", 0, 1, first),
                adapters.SessionRecord("", 0, 2, second)]
        events, _ = claude_code.map_session(rows, "claude-code", "machine-one")
        out = _of_kind(events, "agent_output")[0]
        self.assertEqual(out["tokens"], {"cache_write_1h": 9, "cache_write_5m": 5})

    def test_absent_token_key_is_absent(self) -> None:
        events, _ = _mapped("absent_tokens")
        out = _of_kind(events, "agent_output")[0]
        self.assertEqual(out["tokens"], {"input": 5, "output": 6})
        self.assertNotIn("cache_read", out["tokens"])
        self.assertNotIn("cache_write_5m", out["tokens"])
        self.assertNotIn("cache_write_1h", out["tokens"])
        self.assertNotIn("requests", out)
        self.assertNotIn("price_factors", out)

    def test_requests_and_price_factors(self) -> None:
        events, warnings = _mapped("requests_price")
        self.assertEqual(warnings, [])
        out = _of_kind(events, "agent_output")[0]
        self.assertEqual(len(_of_kind(events, "agent_output")), 1)
        self.assertEqual(out["requests"], {"web_search": 2})
        self.assertEqual(out["price_factors"], {"speed": "high", "service_tier": "standard"})
        self.assertEqual(out["tokens"], {"input": 12, "output": 6})

    def test_model_starting_with_angle_bracket_gives_no_event(self) -> None:
        events, warnings = _mapped("model_angle")
        self.assertEqual(events, [])
        self.assertEqual(warnings, [])

    def test_record_without_message_warns_and_gives_no_event(self) -> None:
        events, warnings = _mapped("missing_message")
        self.assertEqual(
            warnings, [{"code": "invalid_record", "values": {"file": 0, "line": 2}}])
        outputs = _of_kind(events, "agent_output")
        self.assertEqual([out["native_id"] for out in outputs], ["msg_missing_01"])
        self.assertEqual(len(events), 1)

    def test_malformed_timestamp_warns_and_gives_no_event(self) -> None:
        rows = [
            adapters.SessionRecord(
                "", 0, 1,
                support.output_record("First invented word.", "not an instant",
                                      "3f1c0000-0000-4000-8000-000000000101", "msg_bad_01")),
            adapters.SessionRecord(
                "", 0, 2,
                support.output_record("Second invented word.", "2026-03-01T09:15:00",
                                      "3f1c0000-0000-4000-8000-000000000102", "msg_bad_02")),
            adapters.SessionRecord(
                "", 0, 3,
                support.output_record("Third invented word.", _INSTANT,
                                      "3f1c0000-0000-4000-8000-000000000103", "msg_good_01")),
        ]
        events, warnings = claude_code.map_session(rows, "claude-code", "machine-one")
        self.assertEqual(warnings, [
            {"code": "invalid_record", "values": {"file": 0, "line": 1}},
            {"code": "invalid_record", "values": {"file": 0, "line": 2}},
        ])
        self.assertEqual([event["native_id"] for event in events], ["msg_good_01"])

    def test_missing_timestamp_warns_and_gives_no_event(self) -> None:
        record = support.prompt_record("First invented word.", _INSTANT, _UUID)
        del record["timestamp"]
        rows = [adapters.SessionRecord("", 0, 1, record)]
        events, warnings = claude_code.map_session(rows, "claude-code", "machine-one")
        self.assertEqual(
            warnings, [{"code": "invalid_record", "values": {"file": 0, "line": 1}}])
        self.assertEqual(events, [])

    def test_record_that_gives_no_event_needs_no_instant(self) -> None:
        rows = [
            adapters.SessionRecord("", 0, 1, {"type": "permission-mode", "sessionId": _UUID}),
            adapters.SessionRecord("", 0, 2, {"type": "last-prompt", "sessionId": _UUID}),
            adapters.SessionRecord("", 0, 3, {"type": "invented-record-type"}),
        ]
        events, warnings = claude_code.map_session(rows, "claude-code", "machine-one")
        self.assertEqual(events, [])
        self.assertEqual([w for w in warnings if w["code"] == "invalid_record"], [])

    def test_instant_that_overflows_warns_and_gives_no_event(self) -> None:
        record = support.prompt_record(
            "First invented word.", "0001-01-01T00:00:00+01:00", _UUID)
        events, warnings = claude_code.map_session(
            [adapters.SessionRecord("", 0, 1, record)], "claude-code", "machine-one")
        self.assertEqual(events, [])
        self.assertEqual(
            warnings, [{"code": "invalid_record", "values": {"file": 0, "line": 1}}])

    def test_cache_write_5m_fallback_does_not_depend_on_the_line_order(self) -> None:
        first = support.output_record("First invented word.", _INSTANT, _UUID, "msg_mixed_01")
        first["message"]["usage"] = {"cache_creation_input_tokens": 14}
        second = support.output_record("Second invented word.", _INSTANT, _UUID, "msg_mixed_01")
        second["message"]["usage"] = {"cache_creation": {"ephemeral_1h_input_tokens": 9}}
        rows = [adapters.SessionRecord("", 0, 1, first),
                adapters.SessionRecord("", 0, 2, second)]
        events, _ = claude_code.map_session(rows, "claude-code", "machine-one")
        out = _of_kind(events, "agent_output")[0]
        self.assertEqual(out["tokens"], {"cache_write_1h": 9, "cache_write_5m": 5})

    def test_empty_message_id_takes_the_identifier_of_the_record(self) -> None:
        events, warnings = _mapped("empty_message_id")
        self.assertEqual(warnings, [])
        outputs = _of_kind(events, "agent_output")
        self.assertEqual(len(outputs), 1)
        self.assertNotIn("native_id", outputs[0])
        self.assertEqual(outputs[0]["event_uid"], "agent_output:2026-11-19T09:50:00.000Z:0")

    def test_tool_use_gives_tool_call(self) -> None:
        events, warnings = _mapped("tool_use")
        self.assertEqual(warnings, [])
        calls = _of_kind(events, "tool_call")
        self.assertEqual(len(calls), 1)
        call = calls[0]
        self.assertEqual(call["native_id"], "tool_call:toolu_a1")
        self.assertEqual(call["event_uid"], "tool_call:toolu_a1")
        self.assertEqual(call["call_id"], "toolu_a1")
        self.assertEqual(call["tool_name"], "Edit")
        self.assertEqual(call["tool_category"], "edit")
        self.assertEqual(call["actor"], "agent")
        self.assertEqual(call["timestamp"], "2026-11-19T10:00:00.000Z")
        self.assertEqual(call["session_id"], _TOOL_USE_SESSION)
        self.assertEqual(len(_of_kind(events, "agent_output")), 1)

    def test_question_tool_use_gives_decision_request(self) -> None:
        events, warnings = _mapped("question_tools")
        self.assertEqual(warnings, [])
        questions = _of_kind(events, "decision_request")
        self.assertEqual(len(questions), 2)
        first, second = questions
        self.assertEqual(first["native_id"], "decision_request:question:toolu_q1")
        self.assertEqual(first["decision_type"], "question")
        self.assertEqual(first["call_id"], "toolu_q1")
        self.assertEqual(first["actor"], "agent")
        self.assertEqual(first["timestamp"], "2026-11-19T10:05:00.000Z")
        self.assertEqual(second["native_id"], "decision_request:plan_approval:toolu_q2")
        self.assertEqual(second["decision_type"], "plan_approval")
        self.assertEqual(second["call_id"], "toolu_q2")
        self.assertEqual(
            [call["tool_category"] for call in _of_kind(events, "tool_call")],
            ["decide", "decide"])
        self.assertEqual(len(_of_kind(events, "agent_output")), 1)

    def test_categories(self) -> None:
        self.assertEqual(claude_code.TOOL_CATEGORIES, {
            "Edit": "edit", "Write": "edit", "MultiEdit": "edit", "NotebookEdit": "edit",
            "Bash": "execute", "PowerShell": "execute",
            "Read": "read",
            "Grep": "search", "Glob": "search",
            "WebFetch": "web", "WebSearch": "web",
            "Agent": "delegate", "Task": "delegate", "SendMessage": "delegate",
            "SubagentHandback": "delegate", "ListAgents": "delegate",
            "AskUserQuestion": "decide", "ExitPlanMode": "decide",
            "ToolSearch": "other", "Skill": "other", "TodoWrite": "other",
            "TaskCreate": "other", "TaskUpdate": "other", "TaskStop": "other",
            "Monitor": "other", "ListMcpResourcesTool": "other",
        })
        rows = [
            ("toolu_c01", "Edit", "edit"), ("toolu_c02", "Write", "edit"),
            ("toolu_c03", "MultiEdit", "edit"), ("toolu_c04", "NotebookEdit", "edit"),
            ("toolu_c05", "Bash", "execute"), ("toolu_c06", "PowerShell", "execute"),
            ("toolu_c07", "Read", "read"), ("toolu_c08", "Grep", "search"),
            ("toolu_c09", "Glob", "search"), ("toolu_c10", "WebFetch", "web"),
            ("toolu_c11", "WebSearch", "web"), ("toolu_c12", "Agent", "delegate"),
            ("toolu_c13", "Task", "delegate"), ("toolu_c14", "SendMessage", "delegate"),
            ("toolu_c15", "SubagentHandback", "delegate"),
            ("toolu_c16", "ListAgents", "delegate"),
            ("toolu_c17", "AskUserQuestion", "decide"),
            ("toolu_c18", "ExitPlanMode", "decide"),
            ("toolu_c19", "ToolSearch", "other"), ("toolu_c20", "Skill", "other"),
            ("toolu_c21", "TodoWrite", "other"), ("toolu_c22", "TaskCreate", "other"),
            ("toolu_c23", "TaskUpdate", "other"), ("toolu_c24", "TaskStop", "other"),
            ("toolu_c25", "Monitor", "other"),
            ("toolu_c26", "ListMcpResourcesTool", "other"),
            ("toolu_mcp", "mcp__x__y", "other"),
        ]
        events, warnings = _mapped("categories")
        calls = {call["call_id"]: call for call in _of_kind(events, "tool_call")}
        self.assertEqual(len(calls), len(rows))
        for call_id, name, category in rows:
            self.assertEqual(calls[call_id]["tool_name"], name)
            self.assertEqual(calls[call_id]["tool_category"], category)
        self.assertEqual(
            warnings, [{"code": "unknown_tool_name", "values": {"tool": "mcp__x__y"}}])

    def test_server_and_mcp_tool_use(self) -> None:
        events, warnings = _mapped("server_mcp")
        calls = _of_kind(events, "tool_call")
        self.assertEqual(len(calls), 2)
        first, second = calls
        self.assertEqual(first["native_id"], "tool_call:srvtool_01")
        self.assertEqual(first["call_id"], "srvtool_01")
        self.assertEqual(first["tool_name"], "web_search")
        self.assertEqual(first["tool_category"], "other")
        self.assertEqual(second["native_id"], "tool_call:mcptool_01")
        self.assertEqual(second["call_id"], "mcptool_01")
        self.assertEqual(second["tool_name"], "mcp__books__lookup")
        self.assertEqual(second["tool_category"], "other")
        self.assertEqual(warnings, [
            {"code": "unknown_tool_name", "values": {"tool": "web_search"}},
            {"code": "unknown_tool_name", "values": {"tool": "mcp__books__lookup"}},
        ])

    def test_tool_result_row(self) -> None:
        events, warnings = _mapped("tool_result")
        self.assertEqual(warnings, [])
        results = _of_kind(events, "tool_result")
        self.assertEqual(len(results), 1)
        result = results[0]
        self.assertEqual(result["native_id"], "tool_result:toolu_a1")
        self.assertEqual(result["event_uid"], "tool_result:toolu_a1")
        self.assertEqual(result["call_id"], "toolu_a1")
        self.assertEqual(result["actor"], "system")
        self.assertEqual(result["timestamp"], "2026-11-19T10:15:00.000Z")
        self.assertEqual(result["invocation"], "interactive")
        self.assertEqual(len(events), 1)

    def test_text_result_names_no_subagent(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        context = adapters.ReadContext(
            "machine-one", support.utc(_MOMENT), _SETTLE, _no_owner)
        past = support.utc(_MOMENT).timestamp() - _SETTLE
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            projects.mkdir()
            main = support.copy_fixture("agent_text_result", projects, folder / "work")
            os.utime(main, (past, past))
            found = adapter.read_sessions(adapter.sessions("claude-code", projects), context)
        self.assertEqual(found.warnings, [])
        self.assertEqual(found.held_back, set())
        self.assertEqual(
            [event["kind"] for event in found.events],
            ["agent_output", "tool_call", "tool_result"])
        out, call, result = found.events
        self.assertEqual(out["actor"], "agent")
        self.assertEqual(out["native_id"], "msg_agent_text_01")
        self.assertEqual(out["event_uid"], "msg_agent_text_01")
        self.assertEqual(out["timestamp"], "2026-11-19T13:00:00.000Z")
        self.assertEqual(out["model"], "Invented-Model")
        self.assertNotIn("tokens", out)
        self.assertNotIn("requests", out)
        self.assertNotIn("price_factors", out)
        self.assertEqual(call["native_id"], "tool_call:toolu_w1")
        self.assertEqual(call["event_uid"], "tool_call:toolu_w1")
        self.assertEqual(call["call_id"], "toolu_w1")
        self.assertEqual(call["tool_name"], "Agent")
        self.assertEqual(call["tool_category"], "delegate")
        self.assertEqual(call["timestamp"], "2026-11-19T13:00:00.000Z")
        self.assertEqual(_counters_of(found.events, "toolu_w1"), {})
        self.assertEqual(result["kind"], "tool_result")
        self.assertEqual(result["actor"], "system")
        self.assertEqual(result["native_id"], "tool_result:toolu_w1")
        self.assertEqual(result["event_uid"], "tool_result:toolu_w1")
        self.assertEqual(result["call_id"], "toolu_w1")
        self.assertEqual(result["timestamp"], "2026-11-19T13:05:00.000Z")
        for event in found.events:
            self.assertEqual(event["schema_version"], 1)
            self.assertEqual(event["source"], "claude-code-jsonl")
            self.assertEqual(event["invocation"], "interactive")
            self.assertEqual(event["agent_id"], "7d7d7d7d-7d7d-57d7-97d7-7d7d7d7d7d7d")
            self.assertEqual(event["source_format"], "2.1.0")
            self.assertEqual(event["session_id"], "7d7d7d7d-7d7d-57d7-97d7-7d7d7d7d7d7d")
            self.assertEqual(event["cwd"], str(folder / "work"))
            self.assertEqual(event["branch"], "main")
            self.assertEqual(event["machine"], "machine-one")
            self.assertEqual(event["tool"], "claude-code")
            self.assertNotIn("parent_agent_id", event)
            self.assertNotIn("subagent_mode", event)

    def test_position_counts_across_files(self) -> None:
        moment = "2026-11-19T11:00:00.500Z"
        rows = [
            adapters.SessionRecord("", 0, 1,
                                   support.queue_record("First invented word.", moment)),
            adapters.SessionRecord("", 0, 2,
                                   support.queue_record("Second invented word.", moment)),
            adapters.SessionRecord("b-second", 2, 1,
                                   support.queue_record("Third invented word.", moment)),
            adapters.SessionRecord("a-first", 1, 1,
                                   support.queue_record("Fourth invented word.", moment)),
        ]
        identifiers = claude_code.event_identifiers(rows)
        self.assertEqual(identifiers, {
            (0, 1): f"queued_message:{moment}:0",
            (0, 2): f"queued_message:{moment}:1",
            (1, 1): f"queued_message:{moment}:2",
            (2, 1): f"queued_message:{moment}:3",
        })

    def test_event_identifier_text(self) -> None:
        identifiers = claude_code.event_identifiers(_fixture_records("queue_two"))
        self.assertEqual(identifiers, {
            (0, 1): "queued_message:2026-11-19T08:30:00.125Z:0",
            (0, 2): "queued_message:2026-11-19T08:30:00.125Z:1",
        })

    def test_invocation_of_each_record(self) -> None:
        events, warnings = _mapped("resumed")
        self.assertEqual(warnings, [])
        outputs = _of_kind(events, "agent_output")
        self.assertEqual([out["invocation"] for out in outputs], ["interactive", "headless"])
        self.assertEqual(
            [out["native_id"] for out in outputs], ["msg_resumed_01", "msg_resumed_02"])

    def test_tool_of_the_session_files(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        context = adapters.ReadContext(
            "machine-one", support.utc(_MOMENT), _SETTLE, _no_owner)
        with support.TemporaryFolder() as folder:
            recorded = folder / "Claude" / "local-agent-mode-sessions"
            projects = recorded / "one" / ".claude" / "projects"
            projects.mkdir(parents=True)
            main = support.copy_fixture("tool_result", projects, folder / "work")
            past = support.utc(_MOMENT).timestamp() - _SETTLE
            os.utime(main, (past, past))
            sessions = adapter.sessions("claude-desktop", recorded)
            self.assertEqual([session.tool for session in sessions], ["claude-desktop"])
            found = adapter.read_sessions(sessions, context)
        self.assertTrue(found.events)
        for event in found.events:
            self.assertEqual(event["tool"], "claude-desktop")
        self.assertEqual(found.unknown_tools, set())

    def test_read_sessions_maps_each_session(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        context = adapters.ReadContext(
            "machine-one", support.utc(_MOMENT), _SETTLE, _no_owner)
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            projects.mkdir()
            first = support.copy_fixture("response_lines", projects, folder / "work")
            second = support.copy_fixture("tool_use", projects, folder / "work")
            past = support.utc(_MOMENT).timestamp() - _SETTLE
            for path in (first, second):
                os.utime(path, (past, past))
            sessions = adapter.sessions("claude-code", projects)
            self.assertEqual(
                [session.session_id for session in sessions], ["response_lines", "tool_use"])
            found = adapter.read_sessions(sessions, context)
        self.assertEqual(found.held_back, set())
        self.assertEqual(found.unknown_tools, set())
        self.assertEqual(
            sorted({event["session_id"] for event in found.events}),
            sorted([_RESPONSE_SESSION, _TOOL_USE_SESSION]))
        mine = [event for event in found.events if event["session_id"] == _RESPONSE_SESSION]
        other = [event for event in found.events if event["session_id"] == _TOOL_USE_SESSION]
        self.assertEqual([event["kind"] for event in mine], ["agent_output"])
        self.assertEqual(sorted(event["kind"] for event in other),
                         ["agent_output", "tool_call"])
        for event in found.events:
            self.assertEqual(event["source"], "claude-code-jsonl")

    def test_read_names_the_file_of_a_message_that_is_not_an_object(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        context = adapters.ReadContext(
            "machine-one", support.utc(_MOMENT), _SETTLE, _no_owner)
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            projects.mkdir()
            main = support.copy_fixture("missing_message", projects, folder / "work")
            found = adapter.read_sessions(adapter.sessions("claude-code", projects), context)
        self.assertEqual(_places(found.warnings), [(str(main), 2)])
        self.assertEqual([event["native_id"] for event in found.events], ["msg_missing_01"])

    def test_no_text_in_agent_events(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        context = adapters.ReadContext(
            "machine-one", support.utc(_MOMENT), _SETTLE, _no_owner)
        past = support.utc(_MOMENT).timestamp() - _SETTLE
        with support.TemporaryFolder() as folder:
            for name, marker in _MARKERS:
                projects = folder / name
                projects.mkdir()
                main = support.copy_fixture(name, projects, folder / "work")
                os.utime(main, (past, past))
                found = adapter.read_sessions(
                    adapter.sessions("claude-code", projects), context)
                for event in found.events:
                    self.assertNotIn(marker, json.dumps(event), (name, marker))

    def test_question_and_approval_requests(self) -> None:
        events, warnings = _mapped("decisions")
        self.assertEqual(warnings, [])
        decisions = _of_kind(events, "decision")
        self.assertEqual(len(decisions), 2)
        first, second = decisions
        self.assertEqual(first["native_id"], "decision:question:toolu_d1")
        self.assertEqual(first["event_uid"], "decision:question:toolu_d1")
        self.assertEqual(first["decision_type"], "question")
        self.assertEqual(first["call_id"], "toolu_d1")
        self.assertEqual(first["actor"], "human")
        self.assertEqual(first["timestamp"], "2026-11-19T10:06:30.000Z")
        self.assertEqual(second["native_id"], "decision:plan_approval:toolu_d2")
        self.assertEqual(second["decision_type"], "plan_approval")
        self.assertEqual(second["call_id"], "toolu_d2")
        self.assertEqual(second["timestamp"], "2026-11-19T10:07:00.000Z")
        requests = _of_kind(events, "decision_request")
        self.assertEqual(
            [request["native_id"] for request in requests],
            ["decision_request:question:toolu_d1", "decision_request:plan_approval:toolu_d2"])
        self.assertEqual(
            [request["timestamp"] for request in requests],
            ["2026-11-19T10:06:00.000Z", "2026-11-19T10:06:00.000Z"])

    def test_permission_of_the_person(self) -> None:
        events, warnings = _mapped("permission_person")
        self.assertEqual(warnings, [])
        requests = _of_kind(events, "decision_request")
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request["native_id"], "decision_request:permission:toolu_p1")
        self.assertEqual(request["decision_type"], "permission")
        self.assertEqual(request["call_id"], "toolu_p1")
        self.assertEqual(request["actor"], "agent")
        self.assertEqual(request["timestamp"], "2026-11-19T10:10:00.000Z")
        self.assertEqual(request["invocation"], "interactive")
        decisions = _of_kind(events, "decision")
        self.assertEqual(len(decisions), 1)
        decision = decisions[0]
        self.assertEqual(decision["native_id"], "decision:permission:toolu_p1")
        self.assertEqual(decision["decision_type"], "permission")
        self.assertEqual(decision["call_id"], "toolu_p1")
        self.assertEqual(decision["actor"], "human")
        self.assertEqual(decision["timestamp"], "2026-11-19T10:11:00.000Z")
        self.assertEqual(len(_of_kind(events, "tool_result")), 1)

    def test_permission_of_a_rule_gives_no_event(self) -> None:
        events, warnings = _mapped("permission_rule")
        self.assertEqual(warnings, [])
        self.assertEqual(_of_kind(events, "decision"), [])
        self.assertEqual(_of_kind(events, "decision_request"), [])
        self.assertEqual(len(_of_kind(events, "tool_result")), 1)

    def test_unknown_permission_source_warns(self) -> None:
        events, warnings = _mapped("permission_other")
        self.assertEqual(
            warnings,
            [{"code": "unknown_permission_source", "values": {"source": "sudoers"}}])
        self.assertEqual(_of_kind(events, "decision"), [])
        self.assertEqual(_of_kind(events, "decision_request"), [])
        self.assertEqual(len(_of_kind(events, "tool_result")), 1)

    def test_permission_with_two_tool_results_warns(self) -> None:
        events, warnings = _mapped("permission_two")
        self.assertEqual(warnings, [{"code": "multi_tool_result_permission", "values": {}}])
        self.assertEqual(_of_kind(events, "decision"), [])
        self.assertEqual(_of_kind(events, "decision_request"), [])
        self.assertEqual(len(_of_kind(events, "tool_result")), 2)

    def test_prompt_of_interactive_session(self) -> None:
        events, warnings = _mapped("prompt")
        self.assertEqual(warnings, [])
        prompts = _of_kind(events, "prompt")
        self.assertEqual(len(prompts), 1)
        prompt = prompts[0]
        self.assertEqual(prompt["actor"], "human")
        self.assertEqual(prompt["native_id"], "3f1c0000-0000-4000-8000-000000000001")
        self.assertEqual(prompt["event_uid"], "3f1c0000-0000-4000-8000-000000000001")
        self.assertEqual(prompt["timestamp"], "2026-03-01T09:15:00.000Z")
        self.assertEqual(prompt["invocation"], "interactive")
        self.assertEqual(prompt["session_id"], "11111111-1111-5111-9111-111111111111")
        self.assertEqual(prompt["tool"], "claude-code")
        self.assertEqual(len(events), 1)

    def test_prompt_of_headless_session_is_scripted_notification(self) -> None:
        events, warnings = _mapped("prompt_headless")
        self.assertEqual(warnings, [])
        self.assertEqual(_of_kind(events, "prompt"), [])
        notes = _of_kind(events, "notification")
        self.assertEqual(len(notes), 1)
        note = notes[0]
        self.assertEqual(note["actor"], "system")
        self.assertEqual(note["input_origin"], "scripted")
        self.assertEqual(note["invocation"], "headless")
        self.assertEqual(note["native_id"], "4e4e0000-0000-4000-8000-00000000004e")
        self.assertEqual(len(events), 1)

    def test_interruption_gives_no_prompt(self) -> None:
        events, warnings = _mapped("interruption")
        self.assertEqual(warnings, [])
        self.assertEqual([event["kind"] for event in events], ["interruption"])
        self.assertEqual(events[0]["actor"], "human")
        self.assertEqual(events[0]["native_id"], "5f5f0000-0000-4000-8000-00000000005f")

    def test_notification_coordinator_peer(self) -> None:
        events, warnings = _mapped("notifications")
        self.assertEqual(warnings, [])
        notes = _of_kind(events, "notification")
        self.assertEqual(len(notes), 3)
        self.assertEqual(
            [note["input_origin"] for note in notes],
            ["task_notification", "coordinator", "peer"])
        for note in notes:
            self.assertEqual(note["actor"], "system")
            self.assertEqual(note["kind"], "notification")
        self.assertEqual(len(events), 3)

    def test_unknown_origin_kind_warns(self) -> None:
        events, warnings = _mapped("origin_unknown")
        self.assertEqual(events, [])
        self.assertEqual(
            warnings, [{"code": "unknown_origin_kind", "values": {"kind": "automated"}}])

    def test_notification_and_warning_of_origin_with_results(self) -> None:
        events, warnings = _mapped("notification_with_results")
        self.assertEqual(len(_of_kind(events, "tool_result")), 2)
        notes = _of_kind(events, "notification")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["input_origin"], "coordinator")
        self.assertEqual(notes[0]["actor"], "system")
        self.assertEqual(
            warnings, [{"code": "unknown_origin_kind", "values": {"kind": "automated"}}])

    def test_interrupted_input_precedence(self) -> None:
        records = _fixture_records("interrupted_records")
        events, warnings = claude_code.map_session(records[:2], "claude-code", "machine-one")
        self.assertEqual(warnings, [])
        self.assertEqual([event["kind"] for event in events], ["interruption", "notification"])
        self.assertEqual(events[0]["invocation"], "headless")
        self.assertEqual(events[0]["actor"], "human")
        self.assertEqual(events[1]["input_origin"], "coordinator")
        events, _ = claude_code.map_session(
            _fixture_records("interrupted_records", "b-second")[2:], "claude-code", "machine-one")
        self.assertEqual([event["kind"] for event in events], ["notification"])
        self.assertEqual(events[0]["input_origin"], "parent")

    def test_prompt_without_uuid_takes_the_identifier_of_the_record(self) -> None:
        events, warnings = _mapped("prompt_no_uuid")
        self.assertEqual(warnings, [])
        prompts = _of_kind(events, "prompt")
        self.assertEqual(len(prompts), 1)
        self.assertNotIn("native_id", prompts[0])
        self.assertEqual(prompts[0]["event_uid"], "prompt:2026-11-19T17:30:00.000Z:0")

    def test_queued_message(self) -> None:
        events, warnings = _mapped("queue_two")
        self.assertEqual(warnings, [])
        queued = _of_kind(events, "queued_message")
        self.assertEqual(len(queued), 2)
        first, second = queued
        self.assertEqual(first["event_uid"], "queued_message:2026-11-19T08:30:00.125Z:0")
        self.assertEqual(second["event_uid"], "queued_message:2026-11-19T08:30:00.125Z:1")
        self.assertNotIn("native_id", first)
        self.assertNotIn("native_id", second)
        self.assertEqual(first["actor"], "human")
        self.assertEqual(first["timestamp"], "2026-11-19T08:30:00.125Z")
        self.assertEqual(first["invocation"], "unknown")

    def test_queue_content_starting_with_angle_bracket_gives_no_event(self) -> None:
        events, warnings = _mapped("queue_tag")
        self.assertEqual(warnings, [])
        self.assertEqual([event["timestamp"] for event in events],
                         ["2026-11-19T08:40:05.000Z"])

    def test_blank_enqueue_gives_a_queued_message(self) -> None:
        events, warnings = _mapped("queue_tag")
        self.assertEqual(warnings, [])
        queued = _of_kind(events, "queued_message")
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["event_uid"], "queued_message:2026-11-19T08:40:05.000Z:0")
        self.assertEqual(queued[0]["actor"], "human")
        self.assertEqual(queued[0]["timestamp"], "2026-11-19T08:40:05.000Z")

    def test_is_meta_gives_no_event(self) -> None:
        events, warnings = _mapped("meta_records")
        self.assertEqual(events, [])
        self.assertEqual(warnings, [])

    def test_unknown_structure_of_known_type_is_unknown_record_type(self) -> None:
        events, warnings = _mapped("unknown_structure")
        self.assertEqual(events, [])
        self.assertEqual(warnings, [{"code": "unknown_record_type",
                                     "values": {"type": "user", "version": support.VERSION}}])

    def test_record_types_without_event(self) -> None:
        events, warnings = _mapped("no_event_types")
        self.assertEqual(events, [])
        self.assertEqual(warnings, [])
        records, unread, warnings = claude_code.read_file(
            _FIXTURES / "no_event_types.jsonl", settled=True)
        self.assertEqual(len(records), 19)
        self.assertFalse(unread)
        self.assertEqual(warnings, [])

    def test_prompt_without_origin(self) -> None:
        events, warnings = _mapped("prompt_no_origin")
        self.assertEqual(warnings, [])
        self.assertEqual(sorted(event["kind"] for event in events),
                         ["interruption", "notification", "prompt"])
        notes = _of_kind(events, "notification")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["input_origin"], "task_notification")
        self.assertEqual(_of_kind(events, "prompt")[0]["invocation"], "interactive")

    def test_interruption_of_list_content_gives_no_prompt(self) -> None:
        # Claude Code 2.1 writes the content of a record of the person as a list of blocks
        # with no `origin`: the text of the record is the text of its text blocks, so the
        # interruption rule reads the list shape as it reads the string shape
        events, warnings = _mapped("interruption_blocks")
        self.assertEqual(warnings, [])
        self.assertEqual([event["kind"] for event in events], ["interruption"])
        self.assertEqual(events[0]["actor"], "human")
        self.assertEqual(events[0]["native_id"], "9a1b0000-0000-4000-8000-0000000000a1")
        self.assertEqual(events[0]["event_uid"], "9a1b0000-0000-4000-8000-0000000000a1")

    def test_tags_of_list_content_without_origin(self) -> None:
        # the tags of the version-without-origin rule read the list shape too: the
        # notification tag gives a notification, the other tags give no event
        events, warnings = _mapped("prompt_no_origin_blocks")
        self.assertEqual(warnings, [])
        self.assertEqual(sorted(event["kind"] for event in events),
                         ["interruption", "notification", "prompt"])
        notes = _of_kind(events, "notification")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0]["input_origin"], "task_notification")
        self.assertEqual(_of_kind(events, "prompt")[0]["invocation"], "interactive")

    def test_interruption_of_text_and_image_parts(self) -> None:
        # a part of another type than `text` gives no text: the record keeps the text of
        # its text part alone
        events, warnings = _mapped("interruption_image")
        self.assertEqual(warnings, [])
        self.assertEqual([event["kind"] for event in events], ["interruption"])
        self.assertEqual(events[0]["actor"], "human")
        self.assertEqual(events[0]["native_id"], "77d50000-0000-4000-8000-0000000000d5")

    def test_queued_message_of_list_content(self) -> None:
        events, warnings = _mapped("queue_blocks")
        self.assertEqual(warnings, [])
        queued = _of_kind(events, "queued_message")
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]["event_uid"],
                         "queued_message:2026-11-19T09:10:00.250Z:0")
        self.assertEqual(queued[0]["actor"], "human")
        self.assertEqual(queued[0]["timestamp"], "2026-11-19T09:10:00.250Z")

    def test_input_of_a_subagent_is_a_parent_notification(self) -> None:
        events, warnings = claude_code.map_session(
            _fixture_records("parent_input", "b-second"), "claude-code", "machine-one")
        self.assertEqual(warnings, [])
        notes = _of_kind(events, "notification")
        self.assertEqual(len(notes), 4)
        self.assertEqual(
            sorted(note["input_origin"] for note in notes),
            ["parent", "parent", "peer", "task_notification"])
        self.assertEqual(notes[0]["agent_id"], "b-second")
        self.assertEqual(_of_kind(events, "prompt"), [])

    def test_session_title_and_provider_hint_are_not_written(self) -> None:
        for name in ("prompt", "no_event_types"):
            events, _ = _mapped(name)
            for event in events:
                self.assertNotIn("session_title", event)
                self.assertNotIn("provider_hint", event)

    def test_no_text_in_person_events(self) -> None:
        adapter = claude_code.ClaudeCodeAdapter()
        context = adapters.ReadContext(
            "machine-one", support.utc(_MOMENT), _SETTLE, _no_owner)
        past = support.utc(_MOMENT).timestamp() - _SETTLE
        with support.TemporaryFolder() as folder:
            for name, marker in _PERSON_MARKERS:
                projects = folder / name
                projects.mkdir()
                main = support.copy_fixture(name, projects, folder / "work")
                os.utime(main, (past, past))
                found = adapter.read_sessions(
                    adapter.sessions("claude-code", projects), context)
                for event in found.events:
                    self.assertNotIn(marker, json.dumps(event), (name, marker))


class TestSubagents(unittest.TestCase):
    """The subagents of a session: the agent that each event belongs to, the copy of one
    record that gives its event when the source wrote it in the files of several agents, and
    the link of each subagent to the call that started it."""

    def test_main_agent_id_is_session(self) -> None:
        found = _read_session(
            [support.output_record("Invented response text.", _INSTANT, _UUID, "msg_sub_01")],
            {})
        self.assertEqual([event["kind"] for event in found.events], ["agent_output"])
        self.assertEqual(found.events[0]["agent_id"], "session-1")

    def test_subagent_id_from_file_name(self) -> None:
        record = support.output_record("Invented response text.", _INSTANT, _UUID, "msg_sub_02")
        found = _read_session([], {"a1": [record]})
        self.assertEqual([event["kind"] for event in found.events], ["agent_output"])
        self.assertEqual(found.events[0]["agent_id"], "a1")
        self.assertNotIn("agentId", record)

    def test_link_from_agent_result(self) -> None:
        call = support.tool_use("Agent", "toolu_link1", {"prompt": "Invented task text."},
                                _INSTANT, "3f1c0000-0000-4000-8000-000000000301", "msg_sub_03")
        result = support.tool_result_record(
            "toolu_link1", "2026-11-19T09:16:00.000Z",
            "3f1c0000-0000-4000-8000-000000000302", {"agentId": "a1"})
        answer = support.output_record(
            "Invented response text.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000303", "msg_sub_04")
        answer["agentId"] = "a1"
        found = _read_session([call, result], {"a1": [answer]})
        self.assertEqual(
            [(event["kind"], event["agent_id"]) for event in found.events],
            [("agent_output", "session-1"), ("tool_call", "session-1"),
             ("tool_result", "session-1"), ("agent_output", "a1")])
        linked = found.events[3]
        self.assertEqual(linked["parent_agent_id"], "session-1")
        self.assertEqual(linked["subagent_mode"], "foreground")
        for event in found.events[:3]:
            self.assertNotIn("parent_agent_id", event)
            self.assertNotIn("subagent_mode", event)

    def test_background_mode(self) -> None:
        first = support.tool_use("Agent", "toolu_link2", {"prompt": "Invented task text."},
                                 _INSTANT, "3f1c0000-0000-4000-8000-000000000304", "msg_sub_05")
        first_result = support.tool_result_record(
            "toolu_link2", "2026-11-19T09:16:00.000Z",
            "3f1c0000-0000-4000-8000-000000000305", {"agentId": "b1", "isAsync": True})
        second = support.tool_use(
            "Task", "toolu_link3",
            {"prompt": "Invented task text.", "run_in_background": True},
            _INSTANT, "3f1c0000-0000-4000-8000-000000000306", "msg_sub_06")
        second_result = support.tool_result_record(
            "toolu_link3", "2026-11-19T09:17:00.000Z",
            "3f1c0000-0000-4000-8000-000000000307", {"agentId": "c1"})
        first_answer = support.output_record(
            "Invented response text.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000308", "msg_sub_07")
        first_answer["agentId"] = "b1"
        second_answer = support.output_record(
            "More invented response text.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000309", "msg_sub_08")
        second_answer["agentId"] = "c1"
        found = _read_session(
            [first, first_result, second, second_result],
            {"b1": [first_answer], "c1": [second_answer]})
        for event in found.events:
            if event["agent_id"] == "session-1":
                self.assertNotIn("subagent_mode", event)
        modes = {event["agent_id"]: event["subagent_mode"]
                 for event in found.events if "subagent_mode" in event}
        self.assertEqual(modes, {"b1": "background", "c1": "background"})

    def test_parent_input_is_notification(self) -> None:
        record = support.prompt_record(
            "Invented input of the subagent.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000310")
        found = _read_session([], {"a1": [record]})
        self.assertEqual([event["kind"] for event in found.events], ["notification"])
        note = found.events[0]
        self.assertEqual(note["input_origin"], "parent")
        self.assertEqual(note["agent_id"], "a1")
        self.assertEqual(note["actor"], "system")
        self.assertEqual(note["native_id"], record["uuid"])

    def test_copy_in_two_files_gives_one_event(self) -> None:
        record = support.prompt_record(
            "Invented text of the person.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000311")
        found = _read_session([record], {"a1": [dict(record)]})
        self.assertEqual([event["kind"] for event in found.events], ["prompt"])
        self.assertEqual(found.events[0]["agent_id"], "session-1")
        self.assertEqual(found.warnings, [])

    def test_differing_copies_warn(self) -> None:
        main_copy = support.prompt_record(
            "Invented text of the person.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000312")
        main_copy["agentId"] = "a1"
        agent_copy = support.prompt_record(
            "Invented text of the person.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000312")
        agent_copy["agentId"] = "a1"
        agent_copy["gitBranch"] = "feature"
        found = _read_session([main_copy], {"a1": [agent_copy]})
        self.assertEqual([event["kind"] for event in found.events], ["notification"])
        self.assertEqual(found.events[0]["agent_id"], "a1")
        self.assertEqual(found.events[0]["branch"], "feature")
        self.assertEqual(found.warnings, [
            {"code": "record_copies_differ", "values": {"fields": ["gitBranch"]}}])

    def test_copies_differ_names_fields_only(self) -> None:
        marker = "quillfern"
        main_copy = support.prompt_record(
            f"Invented text with the {marker} word.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000313")
        agent_copy = support.prompt_record(
            "Invented text without the word.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000313")
        kept, warnings = claude_code.deduplicate([
            adapters.SessionRecord("", 0, 1, main_copy),
            adapters.SessionRecord("a1", 1, 1, agent_copy),
        ])
        self.assertEqual([row.agent for row in kept], [""])
        self.assertEqual(warnings, [
            {"code": "record_copies_differ", "values": {"fields": ["message"]}}])
        self.assertNotIn(marker, json.dumps(warnings))


class TestCompleteEvents(unittest.TestCase):
    """The gate of completeness: an event of a session stays out of the store while a later
    record of the source can still change it, and the reading names a session held back when
    the gate holds an event back or the last line of a file stayed unread."""

    def test_last_response_is_held_back(self) -> None:
        # no later record of the same agent: a second line of the same response is no later
        # record, so the response stays held back
        rows = [
            adapters.SessionRecord(
                "", 0, 1, support.output_record(
                    "Invented text.", _INSTANT,
                    "3f1c0000-0000-4000-8000-000000000401", "msg_gate_01")),
            adapters.SessionRecord(
                "", 0, 2, support.output_record(
                    "More invented text.", _INSTANT,
                    "3f1c0000-0000-4000-8000-000000000402", "msg_gate_01")),
        ]
        self.assertEqual(_complete(rows, False), ([], True))

    def test_response_complete_after_later_record(self) -> None:
        rows = [
            adapters.SessionRecord(
                "", 0, 1, support.output_record(
                    "Invented text.", _INSTANT,
                    "3f1c0000-0000-4000-8000-000000000401", "msg_gate_01")),
            adapters.SessionRecord(
                "", 0, 2, support.output_record(
                    "More invented text.", _INSTANT,
                    "3f1c0000-0000-4000-8000-000000000402", "msg_gate_01")),
            adapters.SessionRecord(
                "", 0, 3, support.prompt_record(
                    "Invented text of the person.", _INSTANT,
                    "3f1c0000-0000-4000-8000-000000000403")),
        ]
        kept, held = _complete(rows, False)
        self.assertEqual([event["kind"] for event in kept], ["agent_output", "prompt"])
        self.assertEqual(kept[0]["native_id"], "msg_gate_01")
        self.assertFalse(held)

    def test_tool_call_waits_for_its_result(self) -> None:
        call = support.tool_use(
            "Edit", "toolu_gate_02",
            {"file_path": "D:\\Work\\Product\\module_one.py", "old_string": "alpha",
             "new_string": "beta"},
            _INSTANT, "3f1c0000-0000-4000-8000-000000000401", "msg_gate_02")
        prompt = support.prompt_record(
            "Invented text of the person.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000402")
        rows = [adapters.SessionRecord("", 0, 1, call), adapters.SessionRecord("", 0, 2, prompt)]
        kept, held = _complete(rows, False)
        self.assertEqual([event["kind"] for event in kept], ["agent_output", "prompt"])
        self.assertTrue(held)
        rows.append(adapters.SessionRecord(
            "", 0, 3, support.tool_result_record(
                "toolu_gate_02", _INSTANT, "3f1c0000-0000-4000-8000-000000000403")))
        kept, held = _complete(rows, False)
        self.assertEqual(
            [event["kind"] for event in kept],
            ["agent_output", "tool_call", "prompt", "tool_result"])
        self.assertFalse(held)

    def test_provider_tool_complete_with_response(self) -> None:
        record = _server_record(
            "srvtool_gate_01", "3f1c0000-0000-4000-8000-000000000404", "msg_gate_03")
        rows = [adapters.SessionRecord("", 0, 1, record)]
        self.assertEqual(_complete(rows, False), ([], True))
        rows.append(adapters.SessionRecord(
            "", 0, 2, support.prompt_record(
                "Invented text of the person.", _INSTANT,
                "3f1c0000-0000-4000-8000-000000000405")))
        kept, held = _complete(rows, False)
        self.assertEqual(
            [event["kind"] for event in kept], ["agent_output", "tool_call", "prompt"])
        self.assertEqual(kept[1]["call_id"], "srvtool_gate_01")
        self.assertFalse(held)

    def test_subagent_waits_for_its_link(self) -> None:
        # no result of the Agent call yet: all events of the subagent stay held back
        call = support.tool_use(
            "Agent", "toolu_gate_03", {"prompt": "Invented task text."},
            _INSTANT, "3f1c0000-0000-4000-8000-000000000406", "msg_gate_04")
        prompt = support.prompt_record(
            "Invented text of the person.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000407")
        answer = support.output_record(
            "Invented answer text.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000408", "msg_gate_05")
        answer["agentId"] = "a7"
        rows = [
            adapters.SessionRecord("", 0, 1, call),
            adapters.SessionRecord("", 0, 2, prompt),
            adapters.SessionRecord("a7", 1, 1, answer),
        ]
        kept, held = _complete(rows, False)
        self.assertEqual([event["kind"] for event in kept], ["agent_output", "prompt"])
        self.assertTrue(held)
        rows.append(adapters.SessionRecord(
            "", 0, 3, support.tool_result_record(
                "toolu_gate_03", _INSTANT, "3f1c0000-0000-4000-8000-000000000409",
                {"agentId": "a7"})))
        kept, held = _complete(rows, False)
        self.assertEqual(
            [event["kind"] for event in kept],
            ["agent_output", "tool_call", "prompt", "tool_result", "agent_output"])
        self.assertEqual(kept[4]["agent_id"], "a7")
        self.assertEqual(kept[4]["subagent_mode"], "foreground")
        self.assertFalse(held)

    def test_settled_session_is_complete(self) -> None:
        # the call without a result is stored without counters; the subagent without a link
        # holds no subagent_mode
        call = support.tool_use(
            "Edit", "toolu_gate_04",
            {"file_path": "D:\\Work\\Product\\module_one.py", "old_string": "alpha",
             "new_string": "beta"},
            _INSTANT, "3f1c0000-0000-4000-8000-000000000410", "msg_gate_06")
        prompt = support.prompt_record(
            "Invented text of the person.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000411")
        answer = support.output_record(
            "Invented answer text.", _INSTANT,
            "3f1c0000-0000-4000-8000-000000000412", "msg_gate_07")
        answer["agentId"] = "a6"
        rows = [
            adapters.SessionRecord("", 0, 1, call),
            adapters.SessionRecord("", 0, 2, prompt),
            adapters.SessionRecord("a6", 1, 1, answer),
        ]
        kept, held = _complete(rows, True)
        self.assertFalse(held)
        self.assertEqual(
            sorted(event["kind"] for event in kept),
            ["agent_output", "agent_output", "prompt", "tool_call"])
        for event in kept:
            if event["kind"] == "tool_call":
                for field in ("lines_added", "lines_removed", "file_ext", "size_basis"):
                    self.assertNotIn(field, event)
            else:
                self.assertNotIn("subagent_mode", event)

    def test_same_store_at_any_hour(self) -> None:
        # a read at t1 and a read at t2 > t1 store together the events that one settled read
        # stores, so the same native log gives the same store at any hour of ingestion
        adapter = claude_code.ClaudeCodeAdapter()
        first_now = support.utc(_MOMENT)
        later_now = support.utc("2026-03-01T16:00")
        early_context = adapters.ReadContext("machine-one", first_now, _SETTLE, _no_owner)
        late_context = adapters.ReadContext("machine-one", later_now, _SETTLE, _no_owner)
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            projects.mkdir()
            records = [
                support.prompt_record(
                    "Invented text of the person.", _INSTANT,
                    "3f1c0000-0000-4000-8000-000000000413"),
                support.tool_use(
                    "Edit", "toolu_gate_05",
                    {"file_path": "D:\\Work\\Product\\module_one.py", "old_string": "alpha",
                     "new_string": "beta"},
                    _INSTANT, "3f1c0000-0000-4000-8000-000000000414", "msg_gate_08"),
                support.tool_result_record(
                    "toolu_gate_05", _INSTANT, "3f1c0000-0000-4000-8000-000000000415"),
                support.output_record(
                    "Invented final text.", _INSTANT,
                    "3f1c0000-0000-4000-8000-000000000416", "msg_gate_09"),
            ]
            support.write_session(projects, "session-1", records, {}, folder / "work")
            main = projects / "session-1.jsonl"
            os.utime(main, (first_now.timestamp(), first_now.timestamp()))
            sessions = adapter.sessions("claude-code", projects)
            early = adapter.read_sessions(sessions, early_context)
            late = adapter.read_sessions(sessions, late_context)
        stored_early = {event["event_uid"] for event in early.events}
        stored_late = {event["event_uid"] for event in late.events}
        self.assertEqual(early.held_back, {("claude-code", "session-1")})
        self.assertTrue(stored_early)
        self.assertLess(len(stored_early), len(stored_late))
        self.assertEqual(stored_early | stored_late, stored_late)
        self.assertEqual(late.held_back, set())
        self.assertEqual(
            sorted(event["kind"] for event in late.events),
            ["agent_output", "agent_output", "prompt", "tool_call", "tool_result"])

    def test_unread_last_line_holds_the_session_back(self) -> None:
        # not settled: the last line stayed unread, so the session counts as held back;
        # settled: the line is read and its event is stored
        adapter = claude_code.ClaudeCodeAdapter()
        first_now = support.utc(_MOMENT)
        later_now = support.utc("2026-03-01T16:00")
        early_context = adapters.ReadContext("machine-one", first_now, _SETTLE, _no_owner)
        late_context = adapters.ReadContext("machine-one", later_now, _SETTLE, _no_owner)
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            projects.mkdir()
            first = support.prompt_record(
                "Invented text of the person.", _INSTANT,
                "3f1c0000-0000-4000-8000-000000000417")
            second = support.prompt_record(
                "More invented text of the person.", _INSTANT,
                "3f1c0000-0000-4000-8000-000000000418")
            support.write_session(projects, "session-1", [first], {}, folder / "work")
            main = projects / "session-1.jsonl"
            with main.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(second))
            os.utime(main, (first_now.timestamp(), first_now.timestamp()))
            sessions = adapter.sessions("claude-code", projects)
            early = adapter.read_sessions(sessions, early_context)
            self.assertEqual([event["native_id"] for event in early.events], [first["uuid"]])
            self.assertEqual(early.held_back, {("claude-code", "session-1")})
            late = adapter.read_sessions(sessions, late_context)
        self.assertEqual(
            [event["native_id"] for event in late.events], [first["uuid"], second["uuid"]])
        self.assertEqual(late.held_back, set())


class TestForks(unittest.TestCase):
    """The forked sessions of a reading: the events that two sessions share move to the
    original of the pair, the events that stay in the fork name the session and the instant
    that its history was copied from, and a fork read alone is found through the index."""

    def test_original_holds_own_records_in_shared_range(self) -> None:
        # the original is the session that holds a record of its own inside the range of the
        # shared records, although the identifier of the fork sorts first; its own copy
        # stands for each shared event, and the copy of the fork leaves
        origin, fork = _forked_pair()
        sessions = {
            ("claude-code", "session-origin"): _mapped_session(origin),
            ("claude-code", "session-fork"): _mapped_session(fork),
        }
        warnings = claude_code.assign_forks(sessions, _no_owner)
        self.assertEqual(warnings, [])
        self.assertEqual(
            [event["event_uid"] for event in sessions[("claude-code", "session-origin")]],
            [_FORK_PROMPT, "msg_origin_own", "msg_fork_last"])
        for event in sessions[("claude-code", "session-origin")]:
            self.assertNotIn("forked_from", event)
        kept = [event["event_uid"] for event in sessions[("claude-code", "session-fork")]]
        self.assertEqual(kept, [_FORK_OWN])

    def test_fork_instant_is_last_shared_record(self) -> None:
        # every event that stays in the fork names the original and the instant of the last
        # shared record
        origin, fork = _forked_pair()
        sessions = {
            ("claude-code", "session-origin"): _mapped_session(origin),
            ("claude-code", "session-fork"): _mapped_session(fork),
        }
        warnings = claude_code.assign_forks(sessions, _no_owner)
        self.assertEqual(warnings, [])
        kept = sessions[("claude-code", "session-fork")]
        self.assertEqual([event["forked_from"] for event in kept],
                         [{"session_id": "session-origin", "instant": _LAST_SHARED}])

    def test_both_or_neither_sort_by_identifier_and_warn(self) -> None:
        # when both sessions hold a record of their own inside the range, or neither holds
        # one, the identifier that sorts first is the original, and the reading warns
        alpha = [
            support.prompt_record(
                "Invented text of the person with the aldenwick word.", _INSTANT,
                "3f1c0000-0000-4000-8000-000000000511"),
            support.output_record(
                "Invented response text.", _BETWEEN,
                "3f1c0000-0000-4000-8000-000000000512", "msg_alpha_own"),
            support.output_record(
                "More invented response text.", _LAST_SHARED,
                "3f1c0000-0000-4000-8000-000000000514", "msg_both_last"),
        ]
        bravo = [
            support.prompt_record(
                "Invented text of the person with the aldenwick word.", _INSTANT,
                "3f1c0000-0000-4000-8000-000000000511"),
            support.output_record(
                "Invented response text.", _BETWEEN,
                "3f1c0000-0000-4000-8000-000000000513", "msg_bravo_own"),
            support.output_record(
                "More invented response text.", _LAST_SHARED,
                "3f1c0000-0000-4000-8000-000000000514", "msg_both_last"),
            support.prompt_record(
                "More invented text of the person.", _AFTER,
                "3f1c0000-0000-4000-8000-000000000515"),
        ]
        north = [
            support.prompt_record(
                "Invented text of the person.", _BEFORE,
                "3f1c0000-0000-4000-8000-000000000521"),
            support.prompt_record(
                "Invented text of the person with the elmswick word.", _INSTANT,
                "3f1c0000-0000-4000-8000-000000000522"),
            support.output_record(
                "Invented response text.", _LAST_SHARED,
                "3f1c0000-0000-4000-8000-000000000523", "msg_neither_last"),
        ]
        south = [
            support.prompt_record(
                "Invented text of the person with the elmswick word.", _INSTANT,
                "3f1c0000-0000-4000-8000-000000000522"),
            support.output_record(
                "Invented response text.", _LAST_SHARED,
                "3f1c0000-0000-4000-8000-000000000523", "msg_neither_last"),
            support.prompt_record(
                "More invented text of the person.", _AFTER,
                "3f1c0000-0000-4000-8000-000000000524"),
        ]
        sessions = {
            ("claude-code", "session-alpha"): _mapped_session(alpha),
            ("claude-code", "session-bravo"): _mapped_session(bravo),
            ("claude-code", "session-north"): _mapped_session(north),
            ("claude-code", "session-south"): _mapped_session(south),
        }
        warnings = claude_code.assign_forks(sessions, _no_owner)
        unknown = {"code": "fork_original_unknown", "values": {}}
        self.assertEqual(warnings, [unknown, unknown])
        self.assertEqual(
            [event["event_uid"] for event in sessions[("claude-code", "session-alpha")]],
            ["3f1c0000-0000-4000-8000-000000000511", "msg_alpha_own", "msg_both_last"])
        for event in sessions[("claude-code", "session-alpha")]:
            self.assertNotIn("forked_from", event)
        kept = sessions[("claude-code", "session-bravo")]
        self.assertEqual([event["event_uid"] for event in kept],
                         ["msg_bravo_own", "3f1c0000-0000-4000-8000-000000000515"])
        # the own record that predates the instant of the fork carries no forked_from
        self.assertEqual([event.get("forked_from") for event in kept],
                         [None, {"session_id": "session-alpha", "instant": _LAST_SHARED}])
        self.assertEqual(
            [event["event_uid"] for event in sessions[("claude-code", "session-north")]],
            ["3f1c0000-0000-4000-8000-000000000521",
             "3f1c0000-0000-4000-8000-000000000522", "msg_neither_last"])
        kept = sessions[("claude-code", "session-south")]
        self.assertEqual([event["event_uid"] for event in kept],
                         ["3f1c0000-0000-4000-8000-000000000524"])
        self.assertEqual([event["forked_from"] for event in kept],
                         [{"session_id": "session-north", "instant": _LAST_SHARED}])

    def test_records_without_a_native_identifier_never_pair(self) -> None:
        # two sessions can hold records that share a millisecond and no native identifier,
        # such as one message in the queue of each: a fork copy is a copy of one record, and
        # copies share their native identifier, so an event that takes the identifier of its
        # record belongs to its own session alone — both messages stay and nothing warns
        moment = "2026-03-01T09:20:00.125Z"
        sessions = {
            ("claude-code", "session-first"): _mapped_session(
                [support.queue_record(
                    "Invented queued text with the fernwhistle word.", moment)]),
            ("claude-code", "session-second"): _mapped_session(
                [support.queue_record("More invented queued text.", moment)]),
        }
        warnings = claude_code.assign_forks(sessions, _no_owner)
        self.assertEqual(warnings, [])
        for key in sessions:
            kept = sessions[key]
            self.assertEqual([event["kind"] for event in kept], ["queued_message"], key)
            self.assertEqual([event["event_uid"] for event in kept],
                             ["queued_message:2026-03-01T09:20:00.125Z:0"], key)
            self.assertNotIn("forked_from", kept[0], key)

    def test_fork_read_alone_uses_the_index(self) -> None:
        # native_id_owner names the original: the events that the store already holds under
        # the original leave the fork, and the events that stay name it
        _, fork = _forked_pair()
        sessions = {("claude-code", "session-fork"): _mapped_session(fork)}

        def owner(session_id: str, native_id: str) -> tuple[str, str] | None:
            """The index of a store that holds the shared events of the original."""
            if native_id in (_FORK_PROMPT, "msg_fork_last"):
                return ("claude-code", "session-origin")
            return None

        warnings = claude_code.assign_forks(sessions, owner)
        self.assertEqual(warnings, [])
        kept = sessions[("claude-code", "session-fork")]
        self.assertEqual([event["event_uid"] for event in kept], [_FORK_OWN])
        self.assertEqual([event["forked_from"] for event in kept],
                         [{"session_id": "session-origin", "instant": _LAST_SHARED}])

    def test_read_sessions_gives_the_forks_of_its_sessions(self) -> None:
        # the reading applies the rule of the forks to the sessions that it read: each
        # shared event stays once, with the session of the original, and the events of the
        # fork name it
        adapter = claude_code.ClaudeCodeAdapter()
        context = adapters.ReadContext(
            "machine-one", support.utc(_MOMENT), _SETTLE, _no_owner)
        origin, fork = _forked_pair()
        with support.TemporaryFolder() as folder:
            projects = folder / "projects"
            projects.mkdir()
            support.write_session(projects, "session-origin", origin, {}, folder / "work")
            support.write_session(projects, "session-fork", fork, {}, folder / "work")
            past = support.utc(_MOMENT).timestamp() - _SETTLE
            sessions = adapter.sessions("claude-code", projects)
            for session in sessions:
                os.utime(session.main, (past, past))
            found = adapter.read_sessions(sessions, context)
        self.assertEqual(sorted(event["event_uid"] for event in found.events),
                         sorted([_FORK_PROMPT, "msg_origin_own", "msg_fork_last", _FORK_OWN]))
        for event in found.events:
            if event["event_uid"] == _FORK_OWN:
                self.assertEqual(event["session_id"], "session-fork")
                self.assertEqual(event["forked_from"],
                                 {"session_id": "session-origin", "instant": _LAST_SHARED})
            else:
                self.assertEqual(event["session_id"], "session-origin")
                self.assertNotIn("forked_from", event)
        self.assertEqual(found.warnings, [])

    def test_original_without_own_copy_takes_the_moved_copy(self) -> None:
        # ada loses its copies as the fork of cleo, so when the pair of ada and ben is
        # decided, the original holds no copy of the shared record and the copy of ben
        # moves to ada with the identifier of ada as its session
        shared_prompt = support.prompt_record(
            "Invented text of the person with the ormelight word.",
            "2026-03-01T09:10:00.000Z", "3f1c0000-0000-4000-8000-000000000531")
        shared_late = support.prompt_record(
            "More invented text of the person.",
            "2026-03-01T09:12:00.000Z", "3f1c0000-0000-4000-8000-000000000532")
        cleo = [dict(shared_prompt, sessionId="session-cleo"),
                dict(shared_late, sessionId="session-cleo"),
                dict(support.output_record(
                    "Invented response text.", "2026-03-01T09:11:00.000Z",
                    "3f1c0000-0000-4000-8000-000000000533", "msg_cleo_own"),
                    sessionId="session-cleo")]
        ada = [dict(shared_prompt, sessionId="session-ada"),
               dict(shared_late, sessionId="session-ada")]
        ben = [dict(shared_prompt, sessionId="session-ben")]
        sessions = {
            ("claude-code", "session-cleo"): _mapped_session(cleo),
            ("claude-code", "session-ada"): _mapped_session(ada),
            ("claude-code", "session-ben"): _mapped_session(ben),
        }
        warnings = claude_code.assign_forks(sessions, _no_owner)
        unknown = {"code": "fork_original_unknown", "values": {}}
        self.assertEqual(warnings, [unknown, unknown])
        self.assertEqual([(event["event_uid"], event["session_id"])
                          for event in sessions[("claude-code", "session-ada")]],
                         [("3f1c0000-0000-4000-8000-000000000531", "session-ada")])
        self.assertEqual(sessions[("claude-code", "session-ben")], [])

    def test_forked_from_starts_at_the_fork_instant(self) -> None:
        # a kept event whose timestamp is before the instant of the fork carries no
        # forked_from; the events at or after the instant name the original
        origin, fork = _forked_pair()
        fork.insert(2, support.prompt_record(
            "More invented input of the person.", "2026-03-01T09:14:00.000Z",
            "3f1c0000-0000-4000-8000-000000000534"))
        sessions = {
            ("claude-code", "session-origin"): _mapped_session(origin),
            ("claude-code", "session-fork"): _mapped_session(fork),
        }
        warnings = claude_code.assign_forks(sessions, _no_owner)
        self.assertEqual(warnings, [])
        kept = sessions[("claude-code", "session-fork")]
        self.assertEqual([event["event_uid"] for event in kept],
                         ["3f1c0000-0000-4000-8000-000000000534", _FORK_OWN])
        self.assertEqual([event.get("forked_from") for event in kept],
                         [None, {"session_id": "session-origin", "instant": _LAST_SHARED}])


class TestSizeCounters(unittest.TestCase):
    """The size counters of a call of a tool of the edit category: the lines of a text, the
    extension of a file, the counters that the patch of the change gives, and those that the
    input gives without a patch, in the events of the mapping."""

    def test_count_lines(self) -> None:
        self.assertEqual((size.count_lines("a\nb"), size.count_lines("a\nb\n")), (2, 2))
        self.assertEqual(size.count_lines(""), 0)
        self.assertEqual(size.count_lines("\n"), 1)

    def test_file_extension(self) -> None:
        e = size.file_extension
        self.assertEqual(
            (e("a.PY"), e("a.tar.gz"), e(".bashrc"), e("Makefile")), ("py", "gz", None, None))
        self.assertEqual(e("D:\\Work\\Product\\module_one.py"), "py")
        self.assertIsNone(e("D:\\Work\\Product.v2\\Makefile"))

    def test_patch_counts(self) -> None:
        result = {"structuredPatch": [
            {"lines": ["-alpha", "+beta one", "+beta two", " gamma stays"]},
            {"lines": ["-delta one", "-delta two", "+epsilon"]},
        ]}
        counters = size.size_counters(
            "Edit",
            {"file_path": "D:\\Work\\Product\\module_one.py", "old_string": "alpha",
             "new_string": "invented"},
            result, False)
        self.assertEqual(counters, {"lines_added": 3, "lines_removed": 3, "file_ext": "py",
                                    "size_basis": "patch"})

    def test_patch_without_hunks_falls_back_to_input(self) -> None:
        counters = size.size_counters(
            "Edit",
            {"file_path": "D:\\Work\\Product\\module_one.py",
             "old_string": "alpha one\nalpha two", "new_string": "beta"},
            {"structuredPatch": []}, False)
        self.assertEqual(counters, {"lines_added": 1, "lines_removed": 2, "file_ext": "py",
                                    "size_basis": "input"})

    def test_edit_input(self) -> None:
        counters = size.size_counters(
            "Edit",
            {"file_path": "D:\\Work\\Product\\module_one.py",
             "old_string": "alpha one\nalpha two", "new_string": "beta"},
            {}, False)
        self.assertEqual(counters, {"lines_added": 1, "lines_removed": 2, "file_ext": "py",
                                    "size_basis": "input"})

    def test_insertion_counts_no_removed_line(self) -> None:
        counters = size.size_counters(
            "Edit",
            {"file_path": "D:\\Work\\Product\\module_one.py", "old_string": "",
             "new_string": "beta"},
            {}, False)
        self.assertEqual(counters, {"lines_added": 1, "lines_removed": 0, "file_ext": "py",
                                    "size_basis": "input"})

    def test_multiedit_sums_items(self) -> None:
        counters = size.size_counters(
            "MultiEdit",
            {"file_path": "D:\\Work\\Product\\module_one.py",
             "edits": [{"old_string": "alpha one", "new_string": "beta one\nbeta two"},
                       {"old_string": "gamma", "new_string": "delta"}]},
            {}, False)
        self.assertEqual(counters, {"lines_added": 3, "lines_removed": 2, "file_ext": "py",
                                    "size_basis": "input"})

    def test_write_create_has_zero_removed(self) -> None:
        counters = size.size_counters(
            "Write",
            {"file_path": "D:\\Work\\Product\\module_one.py", "content": "one\ntwo\nthree"},
            {"type": "create"}, False)
        self.assertEqual(counters, {"lines_added": 3, "lines_removed": 0, "file_ext": "py",
                                    "size_basis": "input"})

    def test_write_update_without_patch_has_removed_absent(self) -> None:
        counters = size.size_counters(
            "Write",
            {"file_path": "D:\\Work\\Product\\module_one.py", "content": "one\ntwo"},
            {"type": "update"}, False)
        self.assertEqual(counters, {"lines_added": 2, "file_ext": "py", "size_basis": "input"})

    def test_notebookedit(self) -> None:
        counters = size.size_counters(
            "NotebookEdit",
            {"notebook_path": "D:\\Work\\Product\\marlford.ipynb",
             "new_source": "plotted = marlford_read()"},
            {}, False)
        self.assertEqual(counters, {"lines_added": 1, "file_ext": "ipynb",
                                    "size_basis": "input"})

    def test_error_result_has_no_counters(self) -> None:
        counters = size.size_counters(
            "Edit",
            {"file_path": "D:\\Work\\Product\\module_one.py", "old_string": "alpha",
             "new_string": "beta"},
            {"structuredPatch": [{"lines": ["-alpha", "+beta"]}]}, True)
        self.assertEqual(counters, {})

    def test_call_without_result_has_no_counters(self) -> None:
        counters = size.size_counters(
            "Edit",
            {"file_path": "D:\\Work\\Product\\module_one.py", "old_string": "alpha",
             "new_string": "beta"},
            None, False)
        self.assertEqual(counters, {})

    def test_no_counters_outside_the_edit_category(self) -> None:
        counters = size.size_counters("Bash", {"command": "invented text"},
                                      {"structuredPatch": []}, False)
        self.assertEqual(counters, {})

    def test_size_counters_of_each_edit_tool(self) -> None:
        events, warnings = _mapped("size_counters")
        self.assertEqual(warnings, [])
        self.assertEqual(_counters_of(events, "toolu_s1"),
                         {"lines_added": 2, "lines_removed": 1, "file_ext": "py",
                          "size_basis": "patch"})
        self.assertEqual(_counters_of(events, "toolu_s2"),
                         {"lines_added": 1, "lines_removed": 2, "file_ext": "py",
                          "size_basis": "input"})
        self.assertEqual(_counters_of(events, "toolu_s3"),
                         {"lines_added": 3, "lines_removed": 0, "file_ext": "py",
                          "size_basis": "input"})
        self.assertEqual(_counters_of(events, "toolu_s4"),
                         {"lines_added": 2, "file_ext": "py", "size_basis": "input"})
        self.assertEqual(_counters_of(events, "toolu_s5"),
                         {"lines_added": 1, "file_ext": "ipynb", "size_basis": "input"})
        self.assertEqual(_counters_of(events, "toolu_s6"),
                         {"lines_added": 3, "lines_removed": 2, "file_ext": "py",
                          "size_basis": "input"})
        self.assertEqual(_counters_of(events, "toolu_s7"), {})
        self.assertEqual(_counters_of(events, "toolu_s8"), {})
        self.assertEqual(_counters_of(events, "toolu_s9"),
                         {"lines_added": 1, "lines_removed": 2, "file_ext": "py",
                          "size_basis": "input"})

    def test_no_path_in_events(self) -> None:
        events, _ = _mapped("size_counters")
        self.assertTrue(events)
        for event in events:
            self.assertNotIn("marlford", json.dumps(event))


class TestRetention(unittest.TestCase):
    """The retention that the settings files of Claude Code give each agent tool of the
    adapter: the shortest `cleanupPeriodDays` in effect for `claude-code`, and the desktop
    rule for `claude-desktop` (claude-code-adapter.md › Retention)."""

    def test_default_claude_code(self) -> None:
        # no settings file of the temporary folder gives a value: the default of 30 days
        with support.TemporaryFolder() as folder:
            self.assertEqual(
                _retention_of("claude-code", folder),
                adapters.Retention("cleanupPeriodDays", 30))

    def test_setting_of_the_person(self) -> None:
        # the settings file beside the recorded projects folder holds 60: the period is 60
        with support.TemporaryFolder() as folder:
            config = folder / "config"
            (config / "projects").mkdir(parents=True)
            _write_settings(config / "settings.json", {"cleanupPeriodDays": 60})
            self.assertEqual(
                _retention_of(
                    "claude-code", folder, {"claude-code": [str(config / "projects")]}),
                adapters.Retention("cleanupPeriodDays", 60))

    def test_cleanup_of_zero_gives_no_value(self) -> None:
        # a cleanupPeriodDays of 0 fails validation in Claude Code, so the settings file gives
        # no value and the default stays
        with support.TemporaryFolder() as folder:
            config = folder / "config"
            (config / "projects").mkdir(parents=True)
            _write_settings(config / "settings.json", {"cleanupPeriodDays": 0})
            self.assertEqual(
                _retention_of(
                    "claude-code", folder, {"claude-code": [str(config / "projects")]}),
                adapters.Retention("cleanupPeriodDays", 30))

    def test_desktop_has_no_age_limit_by_default(self) -> None:
        # no settings file sets a desktop value: no age limit
        with support.TemporaryFolder() as folder:
            self.assertEqual(
                _retention_of("claude-desktop", folder),
                adapters.Retention("desktopSessionCleanupPeriodDays", None))

    def test_desktop_longer_of_two(self) -> None:
        # the settings file beside the recorded projects folder holds a desktop limit of 90:
        # the longer of 90 and the cleanup of 30 in the same call wins
        with support.TemporaryFolder() as folder:
            config = folder / "config"
            (config / "projects").mkdir(parents=True)
            _write_settings(config / "settings.json", {"desktopSessionCleanupPeriodDays": 90})
            self.assertEqual(
                _retention_of(
                    "claude-desktop", folder, {"claude-code": [str(config / "projects")]}),
                adapters.Retention("desktopSessionCleanupPeriodDays", 90))

    def test_desktop_cleanup_longer(self) -> None:
        # a desktop limit of 7 with the cleanup at its default of 30 still keeps 30 days, the
        # example of the documentation
        with support.TemporaryFolder() as folder:
            config = folder / "config"
            (config / "projects").mkdir(parents=True)
            _write_settings(config / "settings.json", {"desktopSessionCleanupPeriodDays": 7})
            self.assertEqual(
                _retention_of(
                    "claude-desktop", folder, {"claude-code": [str(config / "projects")]}),
                adapters.Retention("desktopSessionCleanupPeriodDays", 30))

    def test_managed_cleanup_applies_alone(self) -> None:
        # the managed file in the temporary folder holds a cleanup of 14: it applies alone to
        # claude-desktop although the person settings hold a desktop limit of 90 and a cleanup
        # of 60, and it is the value of claude-code as well
        with support.TemporaryFolder() as folder:
            config = folder / "config"
            (config / "projects").mkdir(parents=True)
            _write_settings(config / "settings.json", {
                "cleanupPeriodDays": 60, "desktopSessionCleanupPeriodDays": 90})
            _write_settings(folder / "managed-settings.json", {"cleanupPeriodDays": 14})
            self.assertEqual(
                _retention_of(
                    "claude-desktop", folder, {"claude-code": [str(config / "projects")]}),
                adapters.Retention("cleanupPeriodDays", 14))
            self.assertEqual(
                _retention_of(
                    "claude-code", folder, {"claude-code": [str(config / "projects")]}),
                adapters.Retention("cleanupPeriodDays", 14))

    def test_managed_cleanup_without_desktop_setting(self) -> None:
        # the managed file holds a cleanup of 14 and no settings file holds a desktop value:
        # the managed cleanup applies alone
        with support.TemporaryFolder() as folder:
            _write_settings(folder / "managed-settings.json", {"cleanupPeriodDays": 14})
            self.assertEqual(
                _retention_of("claude-desktop", folder),
                adapters.Retention("cleanupPeriodDays", 14))

    def test_managed_settings_path(self) -> None:
        # the managed settings file of each system, as a pure path of that system; a pure path
        # reads no file
        found = claude_code.managed_settings_path("Windows")
        self.assertEqual(
            found, PureWindowsPath(r"C:\Program Files\ClaudeCode\managed-settings.json"))
        self.assertIsInstance(found, PureWindowsPath)
        self.assertNotIsInstance(found, Path)
        found = claude_code.managed_settings_path("Darwin")
        self.assertEqual(
            found, PurePosixPath("/Library/Application Support/ClaudeCode/managed-settings.json"))
        self.assertIsInstance(found, PurePosixPath)
        self.assertNotIsInstance(found, Path)
        found = claude_code.managed_settings_path("Linux")
        self.assertEqual(found, PurePosixPath("/etc/claude-code/managed-settings.json"))
        self.assertIsInstance(found, PurePosixPath)
        self.assertNotIsInstance(found, Path)

    def test_shorter_local_project_value_wins(self) -> None:
        # the person settings hold 30 and the local project settings of a folder of the
        # sessions hold 7: the shortest of the values in effect wins
        with support.TemporaryFolder() as folder:
            config = folder / "config"
            (config / "projects").mkdir(parents=True)
            _write_settings(config / "settings.json", {"cleanupPeriodDays": 30})
            work = folder / "work"
            _write_settings(work / ".claude" / "settings.local.json", {"cleanupPeriodDays": 7})
            self.assertEqual(
                _retention_of(
                    "claude-code", folder,
                    {"claude-code": [str(config / "projects")]}, [str(work)]),
                adapters.Retention("cleanupPeriodDays", 7))

    def test_precedence_inside_one_folder(self) -> None:
        # in the same folder the local settings hold 60 and the shared settings hold 7: the
        # local value is the one in effect for the folder, so the period is 60
        with support.TemporaryFolder() as folder:
            work = folder / "work"
            _write_settings(work / ".claude" / "settings.local.json", {"cleanupPeriodDays": 60})
            _write_settings(work / ".claude" / "settings.json", {"cleanupPeriodDays": 7})
            self.assertEqual(
                _retention_of("claude-code", folder, {}, [str(work)]),
                adapters.Retention("cleanupPeriodDays", 60))

    def test_missing_project_folder_is_skipped(self) -> None:
        # a folder of the sessions that no longer exists is skipped: no folder and no settings
        # file is created in it, and the default stays
        with support.TemporaryFolder() as folder:
            gone = folder / "gone"
            self.assertEqual(
                _retention_of("claude-code", folder, {}, [str(gone)]),
                adapters.Retention("cleanupPeriodDays", 30))
            self.assertFalse(gone.exists())

    def test_person_settings_follow_recorded_folder(self) -> None:
        # the machine records X/projects and CLAUDE_CONFIG_DIR names Y at run time: the
        # settings file of X gives the value, the one of Y never does
        with support.TemporaryFolder() as folder:
            recorded = folder / "recorded"
            (recorded / "projects").mkdir(parents=True)
            _write_settings(recorded / "settings.json", {"cleanupPeriodDays": 60})
            other = folder / "other"
            (other / "projects").mkdir(parents=True)
            _write_settings(other / "settings.json", {"cleanupPeriodDays": 7})
            self.assertEqual(
                _retention_of(
                    "claude-code", folder,
                    {"claude-code": [str(recorded / "projects")]},
                    environ={"CLAUDE_CONFIG_DIR": str(other)}),
                adapters.Retention("cleanupPeriodDays", 60))
