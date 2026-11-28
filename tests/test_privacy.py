"""The privacy test: the store that the ingestion of every fixture of Claude Code builds
holds only fields of the schema version that the ledger writes, and no text of the fixtures
(architecture.md › Tests, product.md › Phase 1, ADR 0003, ADR 0012).

Every fixture holds an invented marker word, and each marker takes part in two checks: the
files of the store folder and the files that the machine keeps beside the store, read as
bytes, hold no marker, and the events of the store hold no text value that a fixture holds
without a marker. The text values of a fixture are the texts of its prompts, of the
responses of its model, of the input of its uses of a tool — the code and the file paths
inside it —, of the results of its tools, of its records, and of its session titles; the
store holds none of them.
"""

import json
import shutil
import tempfile
import unittest
from collections.abc import Iterator
from datetime import date
from pathlib import Path

import support
from ai_effort_ledger import events, store
from ai_effort_ledger.cli import inside_folder
from ai_effort_ledger.configuration.person import PERSON_FILE
from ai_effort_ledger.ingestion.run import INDEX_FILE

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "claude_code"
"""The folder that holds the fixtures of the adapter of Claude Code."""

MACHINE = "machine-privacy"
"""The machine identifier of the machine configuration of the test."""

MACHINE_LABEL = "Invented Machine"
"""The machine label that the machine writes in its store metadata."""

NOTE = "Invented note of the frozen report of the privacy test."
"""The note that the frozen report of the test carries."""

TEXT_CLASSES = {"prompt", "response", "input", "result", "record", "title"}
"""The classes of the text values of a fixture that the walk of a record names."""

TOOL_USE_RESULT_SKIP = ("agentId", "type")
"""The keys of a result of a use of a tool that hold no text of the fixture: the
identifier of the subagent that answered and the kind of the result are facts that the
schema stores, never content."""

MARKERS: dict[str, str] = {
    "absent_tokens": "duskmeadow",
    "agent_text_result": "wrenlow",
    "cache_write_5m": "corrlight",
    "categories": "kelpward",
    "decisions": "wexholm",
    "empty_message_id": "sablefen",
    "interrupted_records": "ellersmoor",
    "interruption": "quinmere",
    "interruption_blocks": "dovengate",
    "interruption_image": "thistleburn",
    "invalid_line": "bramblewick",
    "meta_records": "ilverton",
    "missing_message": "thornwick",
    "model_angle": "gorsevale",
    "no_event_types": "ombervale",
    "notification_with_results": "trelver",
    "notifications": "ferndean",
    "origin_unknown": "pelmworth",
    "parent_input": "netherby",
    "permission_other": "brantmere",
    "permission_person": "harrowdene",
    "permission_rule": "sterley",
    "permission_two": "ostlewick",
    "prompt": "bramblewick",
    "prompt_headless": "calderbank",
    "prompt_no_origin": "skirbeck",
    "prompt_no_origin_blocks": "hallowfield",
    "prompt_no_uuid": "terswell",
    "question_tools": "inkwold",
    "queue_blocks": "galewick",
    "queue_tag": "tarnhold",
    "queue_two": "mosswell",
    "requests_price": "emberlot",
    "response_lines": "fennwick",
    "resumed": "nettlefold",
    "server_mcp": "jerquay",
    "size_counters": "marlford",
    "tool_result": "loomfeather",
    "tool_use": "hollowbrook",
    "unknown_structure": "crowsend",
}
"""The invented marker word that the text fields of each fixture hold. The copy of the
prompt record in `invalid_line` carries the marker of the `prompt` fixture, and no other
fixture carries it."""


def string_leaves(value: object) -> list[str]:
    """Every string that a JSON value holds at any depth, in no order."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        found: list[str] = []
        for one in value.values():
            found.extend(string_leaves(one))
        return found
    if isinstance(value, list):
        found = []
        for one in value:
            found.extend(string_leaves(one))
        return found
    return []


def text_values(record: object) -> list[tuple[str, str]]:
    """The text values of one record of a fixture, each with its class: the text of a
    prompt of the person or of a message that arrives while the agent works, the text of a
    response of the model, the input of a use of a tool with every string inside it, the
    text of the result of a tool, the text that a record of no kind holds, and the title of
    a session. The values that identify a record — its identifiers, its kinds, the name of
    a tool, the model, the folder of the work — are not text values."""
    held: list[tuple[str, str]] = []
    if not isinstance(record, dict):
        return held
    for key, name in (("content", "prompt"), ("text", "record"), ("title", "title")):
        value = record.get(key)
        if isinstance(value, str):
            held.append((name, value))
        elif key == "content" and isinstance(value, list):
            held.extend((name, part["text"]) for part in value
                        if isinstance(part, dict) and isinstance(part.get("text"), str))
    message = record.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str):
            held.append(("prompt", content))
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                held.extend(_text_of_part(part))
    used = record.get("toolUseResult")
    if isinstance(used, str):
        held.append(("result", used))
    elif isinstance(used, dict):
        held.extend(("result", text) for key, one in used.items()
                    if key not in TOOL_USE_RESULT_SKIP
                    for text in string_leaves(one))
    return [(name, text) for name, text in held if text]


def _text_of_part(part: dict) -> list[tuple[str, str]]:
    """The text values of one part of the content of a message: the input of a use of a
    tool, the text of the result of a tool, and the text of a response."""
    part_type = part.get("type")
    if part_type == "tool_use":
        return [("input", leaf) for leaf in string_leaves(part.get("input"))]
    if part_type == "tool_result":
        if isinstance(part.get("content"), str):
            return [("result", part["content"])]
        return []
    if isinstance(part.get("text"), str):
        return [("response", part["text"])]
    return []


def fixture_records(name: str) -> Iterator[object]:
    """Every record of one fixture: a line that is not JSON gives nothing, so that a
    fixture can hold a line that warns."""
    for line in (FIXTURES / f"{name}.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def fixture_days() -> list[date]:
    """The days of the instants that the fixtures hold, each as the UTC day of its
    timestamp; a report of the store covers all of them."""
    found = set()
    for name in MARKERS:
        for record in fixture_records(name):
            stamp = record.get("timestamp") if isinstance(record, dict) else None
            if isinstance(stamp, str) and len(stamp) >= 10:
                found.add(date.fromisoformat(stamp[:10]))
    return sorted(found)


def build_world(base: Path) -> support.World:
    """The world of the test: a home below the temporary folder, and one folder of native
    logs per fixture below it, named after the fixture."""
    logs = base / "home" / "logs"
    return support.world(base / "home", MACHINE,
                         logs=[logs / name for name in sorted(MARKERS)])


def copy_fixtures(world: support.World) -> None:
    """Copy every fixture into its folder of native logs with the working folder of the
    world in every record, and give the copies a time of change two settle times before
    the instant of the world, so that a reading takes every session as settled."""
    for folder in world.logs:
        support.copy_fixture(folder.name, folder, world.home.parent / "work")
    support.settle(world.logs)


def freeze_report(world: support.World) -> None:
    """Keep the document of `report timesheet` over the days of the fixtures as a frozen
    report of the machine, through the real command: the figures come from the one pipeline
    of the reports, and the document is the one composition of a report document, which the
    test reads back from the file that the command writes."""
    span = fixture_days()
    code, _, stderr = support.run_main(
        world.context, "report", "timesheet", "--from", span[0].isoformat(),
        "--to", span[-1].isoformat(), "--freeze", "--note", NOTE)
    assert code == 0, f"report timesheet --freeze stopped with exit code {code}: {stderr}"


def literals_of_fixtures() -> list[str]:
    """The text values that a fixture holds without its marker: no event of the store
    holds one of them as a value."""
    found: list[str] = []
    for name, marker in MARKERS.items():
        for record in fixture_records(name):
            for _, text in text_values(record):
                if marker not in text:
                    found.append(text)
    return found


class TestPrivacy(unittest.TestCase):
    """The store that the ingestion of every fixture of Claude Code builds: its lines hold
    only fields of the schema that the ledger writes, and no text of the fixtures reaches
    any file of the store folder, any file that the machine keeps beside the store, or any
    event (architecture.md › Tests, ADR 0003, ADR 0012)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._temporary = tempfile.mkdtemp(prefix=support.TEMPORARY_PREFIX + "privacy_")
        world = build_world(Path(cls._temporary))
        copy_fixtures(world)
        code, _, stderr = support.run_main(world.context, "ingest")
        assert code == 0, f"ingest stopped with exit code {code}: {stderr}"
        lines = [line for line in stderr.splitlines() if not line.startswith("warning:")]
        assert lines == [], f"ingest wrote lines of no warning on the standard error: {lines}"
        code, _, stderr = support.run_main(world.context, "machine", "label", MACHINE_LABEL)
        assert code == 0, f"machine label stopped with exit code {code}: {stderr}"
        freeze_report(world)
        cls.world = world
        cls.events = [event for event, _ in support.stored_events(world.store)]
        cls.literals = literals_of_fixtures()

    @classmethod
    def tearDownClass(cls) -> None:
        shutil.rmtree(cls._temporary, ignore_errors=True)

    def test_fixtures_hold_their_marker_words(self) -> None:
        """Every fixture of the folder is named in the table of the markers, the text
        values of every fixture hold its marker, and the classes that the walk of a record
        names are the classes of the texts of the fixtures (prompts, responses, tool input
        with its code and its file paths, results, records, and titles)."""
        self.assertEqual(sorted(path.stem for path in FIXTURES.glob("*.jsonl")),
                         sorted(MARKERS))
        classes: set[str] = set()
        for name, marker in MARKERS.items():
            values = [value for record in fixture_records(name) for value in text_values(record)]
            classes.update(name_of for name_of, _ in values)
            self.assertTrue(any(marker in text for _, text in values),
                            f"the text fields of {name} hold no marker {marker}")
        self.assertEqual(classes, TEXT_CLASSES)

    def test_store_lines_hold_schema_fields_only(self) -> None:
        """Every line of every segment of the store is an event of this schema version,
        and no line holds a field outside `events.FIELDS`: the lines are read as the bytes
        of the segments hold them, without the reading of the store module."""
        names = store.segment_names(self.world.store)
        self.assertTrue(names, "the store holds no segment")
        total = 0
        for name in names:
            data = (self.world.store / name).read_bytes()
            for number, line in enumerate(line for line in data.split(b"\n") if line):
                total += 1
                record = json.loads(line)
                extra = sorted(set(record) - set(events.FIELDS))
                self.assertEqual(extra, [], f"{name}, line {number}: fields outside FIELDS")
                self.assertEqual(record.get("schema_version"), 1, f"{name}, line {number}")
                decoded = events.decode_line(line)
                self.assertEqual(decoded.state, "event",
                                 f"{name}, line {number}: {decoded.state}")
                self.assertFalse(decoded.newer, f"{name}, line {number} is of a newer schema")
        self.assertGreater(total, 0, "the segments of the store hold no line")

    def test_no_marker_word_in_any_file_of_the_store_folder(self) -> None:
        """No marker word appears in any file of the store folder, read as bytes: the
        segments, the store metadata of the machine, the person configuration, and the
        frozen reports are all there for the scan to cover."""
        store_folder = self.world.store
        self.assertTrue(list((store_folder / "segments").rglob("*.jsonl")),
                        "the store holds no segment file")
        self.assertTrue((store_folder / "machines" / f"{MACHINE}.toml").is_file(),
                        "the store folder holds no store metadata")
        self.assertTrue((store_folder / PERSON_FILE).is_file(),
                        "the store folder holds no person configuration")
        self.assertEqual(len(store.list_frozen(store_folder)), 1,
                         "the store folder holds no frozen report")
        self._assert_no_marker(store_folder)

    def test_no_marker_word_in_the_files_of_the_machine_local_folder(self) -> None:
        """No marker word appears in any file that the machine keeps beside the store in
        the machine-local data folder, read as bytes: the local index is there for the
        scan to cover."""
        inside = inside_folder(self.world.context, self.world.store)
        index = inside / INDEX_FILE
        self.assertTrue(index.is_file(), "the machine-local data folder holds no local index")
        self.assertGreater(index.stat().st_size, 0, "the local index is empty")
        self._assert_no_marker(inside)

    def test_no_text_value_of_a_fixture_in_an_event(self) -> None:
        """No event of the store holds a text value that a fixture holds without its
        marker: the values of every event at every depth are read, and none of them is one
        of the texts that the byte scan cannot reach through a marker word."""
        self.assertTrue(self.literals, "the fixtures hold no text value without a marker")
        self.assertTrue(self.events, "the store holds no event")
        held: set[str] = set()
        for event in self.events:
            held.update(string_leaves(event))
        for text in sorted(set(self.literals)):
            self.assertTrue(text not in held,
                            f"a text value of a fixture is stored: {text!r}")

    def _assert_no_marker(self, base: Path) -> None:
        """Assert that no file below `base`, read as bytes, holds any marker word of the
        fixtures."""
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            data = path.read_bytes()
            for marker in sorted(set(MARKERS.values())):
                self.assertTrue(marker.encode("utf-8") not in data,
                                f"{path.relative_to(base)} holds the marker {marker}")


if __name__ == "__main__":
    unittest.main()
