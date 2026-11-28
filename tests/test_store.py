"""Tests of the store module: the segments with their lines, the store metadata, the frozen
reports, and the purges.

Every store of the tests lives in a temporary folder and holds invented events and invented
bytes, written by hand; no test reads the native logs, the store, or the configuration of the
machine.
"""

import json
import time
import unittest
from pathlib import Path
from platform import system as running_system
from unittest import mock

import support
from ai_effort_ledger import events, platform, reports, store

_POLL_SECONDS = 15.0

MACHINE = "3f0d5a1e-8c2b-4d6e-9f0a-1b2c3d4e5f60"
OTHER_MACHINE = "7a1c4e8b-2d3f-4a5b-8c9d-0e1f2a3b4c5d"
FIRST_ID = "b1946ac9-4d5e-4f0a-9b7c-2e8d1a3c5f6b"
SECOND_ID = "84f2d1a7-9c3b-4e8d-a5f0-6b1c2d3e4a5f"
NOVEMBER = support.utc("2026-11-30T23:30")
FROZEN_AT = "2026-11-24T12:00:00.000Z"
"""The instant of the freeze of every frozen report that the tests write by hand."""

_MEASURES = {"human_time": 60, "agent_time": 300, "blocked_time": 0,
             "activity_classes": {"person_only": 60, "unattended": 300}}
"""The measures of the person, of the one project, and of the one work item of the day."""

_SHARES = {"inferred_human_share": 0.0, "inferred_agent_share": 0.0}
"""The shares of the inferred repository identity of the project and of the work item."""

_ALPHA = {"id": "alpha", "name": "Alpha"}
"""The project object and the work item object of the documents, as the reports show them."""

_RECORD = {
    "ledger": "0.1.0",
    "tzdata": "2026a",
    "parameters": {"idle_gap": 600, "minimum_attention": 60, "stale_limit": 14400,
                   "headless_prompts": False, "timesheet_granularity": 900, "language": "en"},
    "identity_rules": [{"project": "alpha", "repository": None, "folder": None,
                        "branch": None, "from": None, "to": None}],
    "category_rules": [],
    "dated_facts": {"time_zones": [{"zone": "Etc/UTC", "from": "1970-01-01T00:00:00.000Z"}],
                    "day_starts": [{"hour": "00:00", "from": "1970-01-01"}]},
    "configuration_errors": [],
    "segments": [],
    "broken_lines": [],
}
"""The report record of the documents, as `reports.report_record` writes one."""

_DAY_DOCUMENT = {
    "day": "2026-11-20", "state": "measured_day", "unknown_invocation_share": 0.0,
    "human_time_at_idle_gaps": {"300": 60, "600": 60, "900": 60},
    "person": dict(_MEASURES),
    "projects": [{"project": dict(_ALPHA), **_MEASURES, **_SHARES}],
    "work_items": [{"work_item": dict(_ALPHA), **_MEASURES, **_SHARES}],
    "record": _RECORD, "command": "report day", "warnings": [], "configuration_errors": [],
}
"""The document of `report day` of a measured day, written by hand as the command writes
one (command-line.md › JSON documents)."""

_TIMESHEET_DOCUMENT = {
    "days": [{
        "day": "2026-11-20", "state": "measured_day", "total": 60, "measured_total": 60,
        "unknown_invocation_share": 0.0,
        "human_time_at_idle_gaps": {"300": 60, "600": 60, "900": 60},
        "entries": [{"project": dict(_ALPHA), "work_item": None, "measured": 60,
                     "with_manual_entries": 60, "declared": None, **_SHARES}],
    }],
    "record": _RECORD, "command": "report timesheet", "warnings": [],
    "configuration_errors": [],
}
"""The document of `report timesheet` of the same day, written by hand as the command
writes one."""


def _event(timestamp: str, event_uid: str) -> events.Event:
    """A complete invented event: the fields that the schema requires, without `ingested_at`."""
    return {
        "schema_version": events.SCHEMA_VERSION,
        "source": "example_tool",
        "native_id": "native-" + event_uid,
        "event_uid": event_uid,
        "timestamp": timestamp,
        "writer_version": "0.1.0",
        "actor": "agent",
        "kind": "tool_call",
        "machine": MACHINE,
    }


def _write_segment(store_folder: Path, name: str, content: bytes) -> None:
    """Write the bytes of one segment by hand into the store folder."""
    path = store_folder / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _purge(
    event_uid: str,
    keys: list[events.EventKey],
    *,
    corrected: str | None = None,
    sessions: list[dict[str, str]] | None = None,
) -> events.Event:
    """A complete invented purge event, as a segment holds it after the command wrote it."""
    event: events.Event = {
        "schema_version": events.SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": event_uid,
        "timestamp": "2026-11-30T12:00:00.000Z",
        "ingested_at": "2026-11-30T12:00:00.000Z",
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


def _copy(writer_version: str) -> events.Event:
    """A copy of the purged event, as a later ingestion or another machine brings it."""
    return {
        **_event("2026-11-30T10:00:00.000Z", "uid-copy"),
        "ingested_at": "2026-11-30T13:00:00.000Z",
        "writer_version": writer_version,
    }


class TestSegments(unittest.TestCase):
    """The segments follow ingestion.md › Store and architecture.md › Concurrency."""

    def test_append_sets_ingested_at_and_month(self) -> None:
        with support.TemporaryFolder() as store_folder:
            event = _event("2026-12-01T05:00:00.000Z", "uid-1")
            written = store.append_events(store_folder, MACHINE, [event], NOVEMBER)
            name = f"segments/{MACHINE}/2026-11.jsonl"
            self.assertEqual(written[0].segment, name)
            self.assertEqual((written[0].number, written[0].offset), (1, 0))
            self.assertEqual((store_folder / name).read_bytes(), written[0].data)
            decoded = events.decode_line(written[0].data)
            self.assertEqual(decoded.state, "event")
            self.assertEqual(decoded.event["ingested_at"], "2026-11-30T23:30:00.000Z")
            self.assertEqual(decoded.event["timestamp"], "2026-12-01T05:00:00.000Z")
            self.assertIsNone(event.get("ingested_at"))

    def test_each_line_ends_with_line_break(self) -> None:
        with support.TemporaryFolder() as store_folder:
            batch = [_event("2026-11-30T23:00:00.000Z", "uid-1"),
                     _event("2026-11-30T23:10:00.000Z", "uid-2")]
            store.append_events(store_folder, MACHINE, batch, NOVEMBER)
            content = (store_folder / f"segments/{MACHINE}/2026-11.jsonl").read_bytes()
        lines = content.split(b"\n")
        self.assertEqual(len(lines), 3)
        self.assertEqual(lines[-1], b"")
        self.assertEqual(events.decode_line(lines[0]).state, "event")
        self.assertEqual(events.decode_line(lines[1]).state, "event")

    def test_half_written_last_line_is_ignored(self) -> None:
        with support.TemporaryFolder() as store_folder:
            name = f"segments/{MACHINE}/2026-11.jsonl"
            _write_segment(store_folder, name, b'{"invented": true}\n{"torn": tr')
            lines = list(store.read_lines(store_folder, name))
        self.assertEqual(len(lines), 1)
        self.assertEqual((lines[0].number, lines[0].offset), (1, 0))
        self.assertEqual(lines[0].data, b'{"invented": true}\n')

    def test_append_cuts_own_torn_last_line(self) -> None:
        with support.TemporaryFolder() as store_folder:
            name = f"segments/{MACHINE}/2026-11.jsonl"
            _write_segment(store_folder, name, b'{"invented": true}\n{"torn": tr')
            written = store.append_events(
                store_folder, MACHINE, [_event("2026-11-30T23:00:00.000Z", "uid-1")], NOVEMBER)
            content = (store_folder / name).read_bytes()
        self.assertEqual((written[0].number, written[0].offset), (2, 19))
        self.assertNotIn(b'{"torn": tr', content)
        self.assertEqual(content.count(b"\n"), 2)
        self.assertEqual(events.decode_line(content.split(b"\n")[1]).state, "event")

    def test_broken_line_keeps_its_number(self) -> None:
        third = (
            b'{"actor": "agent", "event_uid": "uid-3", '
            b'"ingested_at": "2026-11-30T23:30:00.000Z", "kind": "tool_call", '
            b'"machine": "' + MACHINE.encode() + b'", "schema_version": 1, '
            b'"source": "example_tool", "timestamp": "2026-11-30T23:00:00.000Z", '
            b'"writer_version": "0.1.0"}\n'
        )
        with support.TemporaryFolder() as store_folder:
            name = f"segments/{MACHINE}/2026-11.jsonl"
            _write_segment(store_folder, name, b'{"invented": 1}\nnot an event\n' + third)
            lines = list(store.read_lines(store_folder, name))
        self.assertEqual([line.number for line in lines], [1, 2, 3])
        self.assertEqual(events.decode_line(lines[1].data).state, "broken")
        self.assertEqual(events.decode_line(lines[2].data).state, "event")

    def test_read_resumes_from_offset_with_first_number(self) -> None:
        with support.TemporaryFolder() as store_folder:
            name = f"segments/{MACHINE}/2026-11.jsonl"
            _write_segment(store_folder, name, b'{"invented": 1}\n{"other": 2}\n{"third": 3}\n')
            lines = list(store.read_lines(store_folder, name))
            resumed = list(store.read_lines(
                store_folder, name, offset=lines[1].offset, first_number=lines[1].number))
        self.assertEqual([line.number for line in resumed], [2, 3])
        self.assertEqual(resumed[0].data, b'{"other": 2}\n')
        self.assertEqual([line.offset for line in resumed], [lines[1].offset, lines[2].offset])

    def test_segment_names_sort_as_text(self) -> None:
        with support.TemporaryFolder() as store_folder:
            self.assertEqual(store.segment_names(store_folder), [])
            for machine, month in ((OTHER_MACHINE, "2026-01"), (MACHINE, "2025-12"),
                                   (MACHINE, "2026-01")):
                _write_segment(store_folder, f"segments/{machine}/{month}.jsonl", b"{}\n")
            names = store.segment_names(store_folder)
        self.assertEqual(names, sorted(names))
        self.assertEqual(names, [
            f"segments/{MACHINE}/2025-12.jsonl",
            f"segments/{MACHINE}/2026-01.jsonl",
            f"segments/{OTHER_MACHINE}/2026-01.jsonl",
        ])


class TestStoreFiles(unittest.TestCase):
    """The store metadata and the frozen reports follow ingestion.md › Store and
    architecture.md › Report record."""

    def test_label_with_quotes_reads_back_equal(self) -> None:
        label = 'Front "desk" \\ Level 1\tend\n'
        with support.TemporaryFolder() as store_folder:
            self.assertEqual(store.machine_labels(store_folder, [MACHINE]), ({}, []))
            store.write_label(store_folder, MACHINE, label)
            self.assertEqual(store.machine_labels(store_folder, [MACHINE]),
                             ({MACHINE: label}, []))

    def test_machine_labels_read_each_file_once(self) -> None:
        """The reader of the labels gives the machine label of each machine of one command
        whose store metadata holds one, and the warnings of the store metadata that it
        cannot read, each file read once however often the command names its machine
        (command-line.md › JSON documents). No store metadata, store metadata without
        `label`, and a label that is blank after `strip()` give no label and no warning;
        store metadata whose text is not TOML, that the operating system refuses — here a
        folder in its place —, or whose `label` is not text gives no label and one warning
        `machine_label_unreadable`, which names the file as the store holds it."""
        written = {
            "labelled": 'label = "Invented office desk"\n',
            "keyless": 'other = "Invented value"\n',
            "blank": 'label = "  \\t "\n',
            "broken": 'label = "Invented office\n',
            "number": "label = 7\n",
        }
        with support.TemporaryFolder() as store_folder:
            (store_folder / "machines").mkdir()
            for machine, content in written.items():
                (store_folder / "machines" / f"{machine}.toml").write_text(
                    content, encoding="utf-8")
            (store_folder / "machines" / "undecoded.toml").write_bytes(b'label = "\xff"\n')
            (store_folder / "machines" / "folder.toml").mkdir()
            named = ["labelled", "absent", "keyless", "blank", "broken", "number", "undecoded",
                     "folder", "broken", "labelled"]
            with mock.patch.object(store.files.tomllib, "load",
                                   wraps=store.files.tomllib.load) as load:
                labels, warnings = store.machine_labels(store_folder, named)
        self.assertEqual(labels, {"labelled": "Invented office desk"})
        self.assertEqual(warnings, [
            {"code": "machine_label_unreadable", "values": {"path": f"machines/{machine}.toml"}}
            for machine in ("broken", "number", "undecoded", "folder")])
        self.assertEqual(load.call_count, 6)

    def test_frozen_files(self) -> None:
        """The reader of the file gives each frozen report as the machine, the identifier,
        and the envelope, in the order of the paths of the files, and the reader of the
        reports gives the same two documents, which the two report commands write
        (command-line.md › JSON documents), one with the identifier of its file name as its
        `frozen_id`; the removal takes one file away."""
        first = {"document": _DAY_DOCUMENT, "frozen_at": FROZEN_AT}
        second = {"document": {**_TIMESHEET_DOCUMENT, "frozen_id": SECOND_ID},
                  "note": "Sent to the office",
                  "frozen_at": "2026-11-25T09:30:00.000Z"}
        with support.TemporaryFolder() as store_folder:
            self.assertEqual(store.list_frozen(store_folder), [])
            self.assertEqual(store.frozen_names(store_folder), [])
            store.write_frozen(store_folder, MACHINE, FIRST_ID, first)
            store.write_frozen(store_folder, OTHER_MACHINE, SECOND_ID, second)
            self.assertEqual(store.list_frozen(store_folder), [
                (MACHINE, FIRST_ID, first),
                (OTHER_MACHINE, SECOND_ID, second),
            ])
            self.assertEqual(reports.read_frozen(store_folder), [
                (MACHINE, FIRST_ID, first),
                (OTHER_MACHINE, SECOND_ID, second),
            ])
            self.assertEqual(store.frozen_name(MACHINE, FIRST_ID),
                             f"frozen/{MACHINE}/{FIRST_ID}.json")
            self.assertEqual(store.frozen_names(store_folder), [
                (MACHINE, FIRST_ID),
                (OTHER_MACHINE, SECOND_ID),
            ])
            store.remove_frozen(store_folder, MACHINE, FIRST_ID, MACHINE)
            self.assertEqual(store.list_frozen(store_folder), [(OTHER_MACHINE, SECOND_ID, second)])
            self.assertEqual(store.frozen_names(store_folder), [(OTHER_MACHINE, SECOND_ID)])

    def test_frozen_names_read_no_file(self) -> None:
        """The names of the frozen reports come from the names of their files alone, in the
        order of their paths as text: no file is opened, so a file that the ledger cannot
        read as a frozen report is named like any other (command-line.md › Frozen reports)."""
        with support.TemporaryFolder() as store_folder:
            path = store_folder / "frozen" / MACHINE / f"{FIRST_ID}.json"
            path.parent.mkdir(parents=True)
            path.write_bytes(b"\xff\xfe\x00 not a frozen report")
            with mock.patch.object(Path, "read_text", side_effect=AssertionError("a file "
                                                                                "was read")):
                self.assertEqual(store.frozen_names(store_folder), [(MACHINE, FIRST_ID)])

    def test_frozen_file_that_the_ledger_cannot_read_stops(self) -> None:
        """A file of a frozen report that is not a JSON object, that is nested deeper than
        the parser of JSON reads, that holds a number that is not finite, that holds no
        `document` object, whose document holds no `command` or no `record` object or a
        `frozen_id` other than the identifier of the file name, whose `note` is no text, or
        that holds no instant as `frozen_at` stops the reader of the file with
        `frozen_report_unreadable`, which names the file as the store holds it
        (command-line.md › Exit codes, › Frozen reports)."""
        instant = FROZEN_AT
        share = ('{"document": {"command": "report day", "record": {}, '
                 '"unknown_invocation_share": %s}, "frozen_at": "' + instant + '"}')
        # under a key that no consumer reads, so that the depth alone makes the file
        # unreadable; the parser of JSON stops near three thousand
        deep = "[" * 200_000 + "]" * 200_000
        nested = ('{"document": {"command": "report day", "record": {}, "invented": '
                  + deep + '}, "frozen_at": "' + instant + '"}')
        damaged = [
            b"not a frozen report", b"\xff\xfe\x00", b"[]", b"3",
            nested.encode("utf-8"),
            *((share % number).encode("utf-8")
              for number in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999")),
            json.dumps({"document": {"command": "report day", "record": {},
                                     "frozen_id": SECOND_ID},
                        "frozen_at": instant}).encode("utf-8"),
            json.dumps({"document": {"command": "report day", "record": {}},
                        "note": {"text": "Sent to the office"},
                        "frozen_at": instant}).encode("utf-8"),
            json.dumps({"document": {"command": "report day", "record": {}}, "note": None,
                        "frozen_at": instant}).encode("utf-8"),
            json.dumps({"frozen_at": instant}).encode("utf-8"),
            json.dumps({"document": [], "frozen_at": instant}).encode("utf-8"),
            json.dumps({"document": {"record": {}, "days": []}, "frozen_at": instant},
                       ).encode("utf-8"),
            json.dumps({"document": {"command": 3, "record": {}}, "frozen_at": instant},
                       ).encode("utf-8"),
            json.dumps({"document": {"command": "report day"}, "frozen_at": instant},
                       ).encode("utf-8"),
            json.dumps({"document": {"command": "report day", "record": []},
                        "frozen_at": instant}).encode("utf-8"),
            json.dumps({"document": {"command": "report day", "record": {},
                                     "frozen_id": 1763995200000},
                        "frozen_at": instant}).encode("utf-8"),
            json.dumps({"document": {"command": "report day", "record": {}}}).encode("utf-8"),
            json.dumps({"document": {"command": "report day", "record": {}},
                        "frozen_at": "yesterday"}).encode("utf-8"),
            json.dumps({"document": {"command": "report day", "record": {}},
                        "frozen_at": "2026-11-24T12:00:00"}).encode("utf-8"),
            json.dumps({"document": {"command": "report day", "record": {}},
                        "frozen_at": 1763995200000}).encode("utf-8"),
        ]
        healthy = {"document": {"command": "report day", "record": {}, "day": "2026-11-20"},
                   "frozen_at": instant}
        with support.TemporaryFolder() as store_folder:
            store.write_frozen(store_folder, OTHER_MACHINE, SECOND_ID, healthy)
            path = store_folder / "frozen" / MACHINE / f"{FIRST_ID}.json"
            path.parent.mkdir(parents=True)
            for content in damaged:
                with self.subTest(content=content[:120]):  # the start of a file names it
                    path.write_bytes(content)
                    with self.assertRaises(store.FrozenReportUnreadable) as raised:
                        store.list_frozen(store_folder)
                    error = raised.exception
                    self.assertEqual(error.code, "frozen_report_unreadable")
                    self.assertEqual(error.values, {"path": f"frozen/{MACHINE}/{FIRST_ID}.json"})
                    self.assertEqual(error.exit_code, 1)
                    self.assertEqual(store.frozen_names(store_folder),
                                     [(MACHINE, FIRST_ID), (OTHER_MACHINE, SECOND_ID)])
            store.remove_frozen(store_folder, MACHINE, FIRST_ID, MACHINE)
            self.assertEqual(store.list_frozen(store_folder),
                             [(OTHER_MACHINE, SECOND_ID, healthy)])

    def test_frozen_file_that_the_operating_system_refuses_stops(self) -> None:
        """A file of a frozen report that the operating system refuses to give stops the
        reader of the file as a damaged file does, never with its own error, as the reader
        of the person configuration stops on a file that it cannot read
        (configuration.md › Format); the names alone still come without a read."""
        with support.TemporaryFolder() as store_folder:
            store.write_frozen(store_folder, MACHINE, FIRST_ID,
                               {"document": _DAY_DOCUMENT, "frozen_at": FROZEN_AT})
            with mock.patch.object(Path, "read_text",
                                   side_effect=PermissionError("refused")) as refused:
                with self.assertRaises(store.FrozenReportUnreadable) as raised:
                    store.list_frozen(store_folder)
            self.assertEqual(refused.call_count, 1)
            error = raised.exception
            self.assertEqual(error.code, "frozen_report_unreadable")
            self.assertEqual(error.values, {"path": f"frozen/{MACHINE}/{FIRST_ID}.json"})
            self.assertEqual(error.exit_code, 1)
            self.assertEqual(store.frozen_names(store_folder), [(MACHINE, FIRST_ID)])

    def test_frozen_remove_on_other_machine_stops(self) -> None:
        """Only the machine that wrote a frozen report removes it: from another machine
        the removal stops with `frozen_other_machine` and the file stays
        (architecture.md › Report record)."""
        with support.TemporaryFolder() as store_folder:
            store.write_frozen(store_folder, MACHINE, FIRST_ID,
                               {"document": {"command": "report day", "record": {},
                                             "day": "2026-11-20"},
                                "frozen_at": FROZEN_AT})
            with self.assertRaises(store.FrozenOtherMachine) as raised:
                store.remove_frozen(store_folder, MACHINE, FIRST_ID, OTHER_MACHINE)
            error = raised.exception
            self.assertEqual(error.code, "frozen_other_machine")
            self.assertEqual(error.values, {"id": FIRST_ID, "machine": MACHINE})
            self.assertEqual(error.text_key, "frozen_other_machine")
            self.assertEqual(error.exit_code, 1)
            self.assertTrue((store_folder / f"frozen/{MACHINE}/{FIRST_ID}.json").is_file())

    def test_frozen_remove_with_unreadable_label_names_the_identifier(self) -> None:
        """When the store metadata of the machine that wrote the frozen report cannot be
        read, the stop error of another machine names the identifier, as for a machine
        without a label (command-line.md › Exit codes)."""
        with support.TemporaryFolder() as store_folder:
            store.write_frozen(store_folder, MACHINE, FIRST_ID,
                               {"document": {"command": "report day", "record": {},
                                             "day": "2026-11-20"},
                                "frozen_at": FROZEN_AT})
            (store_folder / "machines").mkdir()
            (store_folder / "machines" / f"{MACHINE}.toml").write_text(
                'label = "Invented office\n', encoding="utf-8")
            with self.assertRaises(store.FrozenOtherMachine) as raised:
                store.remove_frozen(store_folder, MACHINE, FIRST_ID, OTHER_MACHINE)
            error = raised.exception
            self.assertEqual(error.values, {"id": FIRST_ID, "machine": MACHINE})
            self.assertEqual(error.text_key, "frozen_other_machine")

    def test_frozen_remove_on_other_machine_names_the_machine_label(self) -> None:
        """When the store metadata of the machine that wrote the frozen report holds a
        machine label, the stop error of another machine carries it as `machine_label`
        beside the identifier, under the same code, and names the variant of its text that
        shows the label; the label of the machine that removes is not read
        (command-line.md › Exit codes)."""
        with support.TemporaryFolder() as store_folder:
            store.write_frozen(store_folder, MACHINE, FIRST_ID,
                               {"document": {"command": "report day", "record": {},
                                             "day": "2026-11-20"},
                                "frozen_at": FROZEN_AT})
            store.write_label(store_folder, MACHINE, "Office desk")
            store.write_label(store_folder, OTHER_MACHINE, "Invented laptop")
            with self.assertRaises(store.FrozenOtherMachine) as raised:
                store.remove_frozen(store_folder, MACHINE, FIRST_ID, OTHER_MACHINE)
            error = raised.exception
            self.assertEqual(error.code, "frozen_other_machine")
            self.assertEqual(error.values,
                             {"id": FIRST_ID, "machine": MACHINE, "machine_label": "Office desk"})
            self.assertEqual(error.text_key, "frozen_other_machine_with_label")
            self.assertEqual(error.exit_code, 1)
            self.assertTrue((store_folder / f"frozen/{MACHINE}/{FIRST_ID}.json").is_file())

    def test_remove_missing_frozen_stops_with_target_not_found(self) -> None:
        with support.TemporaryFolder() as store_folder:
            with self.assertRaises(store.TargetNotFound) as raised:
                store.remove_frozen(store_folder, MACHINE, FIRST_ID, MACHINE)
            error = raised.exception
        self.assertEqual(error.code, "target_not_found")
        self.assertEqual(error.values, {"target": f"frozen/{MACHINE}/{FIRST_ID}.json"})
        self.assertEqual(error.exit_code, 1)


class TestPurges(unittest.TestCase):
    """The purges follow event-schema.md › Keys and invariants and ADR 0008 with ADR 0015."""

    KEY = events.EventKey(source="example_tool", native_id="native-uid-copy")

    def test_purge_without_corrected_version_blocks_for_good(self) -> None:
        purges = store.PurgeSet.from_events([_purge(FIRST_ID, [self.KEY])])
        self.assertTrue(purges.blocks(_copy("0.1.0")))
        self.assertTrue(purges.blocks(_copy("9.9.9")))
        self.assertFalse(store.PurgeSet.from_events([]).blocks(_copy("0.1.0")))
        other = {**_copy("0.1.0"), "native_id": "native-uid-other"}
        self.assertFalse(purges.blocks(other))

    def test_corrected_version_lets_newer_copies_pass(self) -> None:
        # corrected "0.2.0": writer "0.1.0" blocked, "0.2.0" passes, "0.2.0.dev0" blocked,
        # "0.3.0" passes
        purges = store.PurgeSet.from_events([_purge(FIRST_ID, [self.KEY], corrected="0.2.0")])
        self.assertTrue(purges.blocks(_copy("0.1.0")))
        self.assertFalse(purges.blocks(_copy("0.2.0")))
        self.assertTrue(purges.blocks(_copy("0.2.0.dev0")))
        self.assertFalse(purges.blocks(_copy("0.3.0")))

    def test_two_purges_of_one_key(self) -> None:
        # one without corrected version -> blocked at any version
        purges = store.PurgeSet.from_events([
            _purge(FIRST_ID, [self.KEY], corrected="0.2.0"),
            _purge(SECOND_ID, [self.KEY]),
        ])
        self.assertTrue(purges.blocks(_copy("0.2.0")))
        self.assertTrue(purges.blocks(_copy("9.9.9")))

    def test_sessions_to_read(self) -> None:
        # purge with corrected "0.2.0", own version "0.2.0" -> its sessions
        sessions = [
            {"tool": "example_tool", "session_id": "session-1"},
            {"tool": "other_tool", "session_id": "session-2"},
        ]
        purges = store.PurgeSet.from_events(
            [_purge(FIRST_ID, [self.KEY], corrected="0.2.0", sessions=sessions)])
        expected = [("example_tool", "session-1"), ("other_tool", "session-2")]
        self.assertEqual(purges.sessions_to_read("0.2.0", set()), expected)
        self.assertEqual(purges.sessions_to_read("0.3.0", set()), expected)
        self.assertEqual(purges.sessions_to_read("0.2.0", {FIRST_ID}), [])

    def test_older_version_leaves_the_purge(self) -> None:
        # own version "0.1.0" -> no session
        purges = store.PurgeSet.from_events([_purge(
            FIRST_ID,
            [self.KEY],
            corrected="0.2.0",
            sessions=[{"tool": "example_tool", "session_id": "session-1"}])])
        self.assertEqual(purges.sessions_to_read("0.1.0", set()), [])
        self.assertEqual(purges.sessions_to_read("0.2.0.dev0", set()), [])


class TestRewriteSegment(unittest.TestCase):
    """The rewrite of a segment follows ingestion.md › Store: a new file in the same folder, then
    the replace of the old one."""

    def test_rewrite_removes_lines_in_one_step(self) -> None:
        with support.TemporaryFolder() as store_folder:
            name = f"segments/{MACHINE}/2026-11.jsonl"
            batch = [
                _event("2026-11-30T23:00:00.000Z", "uid-1"),
                _event("2026-11-30T23:10:00.000Z", "uid-2"),
                _event("2026-11-30T23:20:00.000Z", "uid-3"),
            ]
            store.append_events(store_folder, MACHINE, batch, NOVEMBER)
            lines = list(store.read_lines(store_folder, name))
            removed = store.rewrite_segment(
                store_folder, name, lambda line: b'"uid-2"' not in line.data)
            content = (store_folder / name).read_bytes()
            names = sorted(path.relative_to(store_folder).as_posix()
                           for path in (store_folder / "segments").glob("*/*"))
        self.assertEqual(removed, 1)
        self.assertEqual(content, lines[0].data + lines[2].data)
        self.assertEqual(names, [name])

    @unittest.skipUnless(
        running_system() == "Windows", "only Windows holds a file against a replace")
    def test_rewrite_retries_while_file_is_open(self) -> None:
        with support.TemporaryFolder() as store_folder:
            name = f"segments/{MACHINE}/2026-11.jsonl"
            store.append_events(
                store_folder, MACHINE,
                [_event("2026-11-30T23:00:00.000Z", "uid-1"),
                 _event("2026-11-30T23:10:00.000Z", "uid-2")], NOVEMBER)
            with open(store_folder / name, "rb") as held:
                start = time.monotonic()
                with self.assertRaises(platform.LockUnavailable) as stopped:
                    store.rewrite_segment(
                        store_folder, name, lambda line: False, limit_seconds=1.0)
                elapsed = time.monotonic() - start
                held_files = sorted(
                    path.name for path in (store_folder / "segments" / MACHINE).iterdir())
            removed = store.rewrite_segment(store_folder, name, lambda line: False)
            content = (store_folder / name).read_bytes()
        self.assertGreaterEqual(elapsed, 0.9)
        self.assertLess(elapsed, _POLL_SECONDS)
        self.assertEqual(stopped.exception.code, "lock_unavailable")
        self.assertEqual(stopped.exception.values, {"path": str(store_folder / name)})
        self.assertEqual(stopped.exception.exit_code, 1)
        self.assertEqual(held_files, ["2026-11.jsonl"])
        self.assertEqual(removed, 2)
        self.assertEqual(content, b"")
