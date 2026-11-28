"""Tests of the local index: the update from the segments, the chained hash, the broken and
newer lines, the winning copy among the copies that a purge leaves, the queries, the index on
the key that the lookups of a key read and the scans that name no key do not read, and the
session events of a period read from the winning copy of each key.

Every store of the tests lives in a temporary folder and holds invented events, written by the
real store writers or by hand; the index lives in a temporary file; no test reads the native
logs, the store, or the configuration of the machine.
"""

import hashlib
import json
import sqlite3
import time
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

import support
from ai_effort_ledger import events, store
from ai_effort_ledger import index as index_module
from ai_effort_ledger.index import (
    INDEX_FORMAT,
    BrokenLine,
    IndexBusy,
    LocalIndex,
    SegmentState,
)

_POLL_SECONDS = 15.0

MACHINE = "3f0d5a1e-8c2b-4d6e-9f0a-1b2c3d4e5f60"
OTHER_MACHINE = "7a1c4e8b-2d3f-4a5b-8c9d-0e1f2a3b4c5d"
NOVEMBER = support.utc("2026-11-30T23:30")
LATER = support.utc("2026-12-01T08:00")
INGESTED = events.format_instant(NOVEMBER)
LATER_INSTANT = events.format_instant(LATER)
SEGMENT = f"segments/{MACHINE}/2026-11.jsonl"
NOON = support.utc("2026-11-30T12:00")
"""The instant at which the first machine ingests its copy in the tests of two sessions."""
ONE_PM = support.utc("2026-11-30T13:00")
"""The instant at which the other machine ingests its copies in the tests of two sessions."""
TWO_DAYS_BEFORE_NOON = support.utc("2026-11-28T12:00")
AT_NOON = events.format_instant(NOON)
AT_ONE_PM = events.format_instant(ONE_PM)
AT_TWO_DAYS_BEFORE_NOON = events.format_instant(TWO_DAYS_BEFORE_NOON)
# The Rome day 2026-11-30 runs from 23:00 UTC of the 29th to 23:00 UTC of the 30th; a report
# seeks the sessions of a day with a margin of 4 h, so from 19:00 UTC of the 29th to 03:00 UTC
# of the 1st of December, and those of the two days 29 and 30 from 19:00 UTC of the 28th.
DAY_START = support.utc("2026-11-29T19:00")
DAY_END = support.utc("2026-12-01T03:00")
TWO_DAYS_START = support.utc("2026-11-28T19:00")


def _event(timestamp: str, event_uid: str, **overrides: Any) -> events.Event:
    """A complete invented event of schema version 1, without `ingested_at`."""
    event: events.Event = {
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
    event.update(overrides)
    return event


def _line(timestamp: str, event_uid: str, ingested_at: str, **overrides: Any) -> bytes:
    """One line of a segment written by hand: the invented event with its `ingested_at`."""
    return events.encode_event(_event(timestamp, event_uid, ingested_at=ingested_at, **overrides))


def _write_segment(store_folder: Path, content: bytes) -> None:
    """Write the bytes of the segment of the tests by hand into the store folder."""
    path = store_folder / SEGMENT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _purge(
    event_uid: str,
    keys: list[events.EventKey],
    corrected: str | None = None,
) -> events.Event:
    """A complete invented purge event that lists the keys."""
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
    return event


def _ledger_event(timestamp: str, event_uid: str, **overrides: Any) -> events.Event:
    """A complete invented event of the source `ledger` (a manual entry), without `ingested_at`."""
    event: events.Event = {
        "schema_version": events.SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": event_uid,
        "timestamp": timestamp,
        "writer_version": "0.1.0",
        "actor": "human",
        "kind": "manual_entry",
        "machine": MACHINE,
    }
    event.update(overrides)
    return event


def _chained(lines: list[bytes]) -> str:
    """The chained hash of the lines as D4 gives it: each digest chains the one before it."""
    chained = hashlib.sha256(b"").digest()
    for data in lines:
        chained = hashlib.sha256(chained + data).digest()
    return chained.hex()


def _lines_of(store_folder: Path) -> list[bytes]:
    """The complete lines that the segment of the tests holds."""
    content = (store_folder / SEGMENT).read_bytes()
    return [line + b"\n" for line in content.split(b"\n")[:-1]]


class TestUpdate(unittest.TestCase):
    """The update follows architecture.md › Local index and ingestion.md › Store."""

    def test_update_reads_only_new_bytes(self) -> None:
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2")], NOVEMBER)
            first = index.update(store_folder)
            self.assertEqual(first.lines_read, 2)
            self.assertEqual(first.broken, [])
            self.assertFalse(first.newer)
            self.assertEqual(index.counts(), (1, 2))
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:20:00.000Z", "uid-3")], NOVEMBER)
            second = index.update(store_folder)
            self.assertEqual(second.lines_read, 1)
            self.assertEqual(index.counts(), (1, 3))
            self.assertTrue(index.has_key(
                events.EventKey(source="example_tool", native_id="native-uid-3"),
                store.PurgeSet.from_events([])))
            index.close()

    def test_numbers_continue_after_an_offset(self) -> None:
        head = (_line("2026-11-30T10:00:00.000Z", "uid-1", "2026-11-30T12:00:00.000Z")
                + b"not an event\n"
                + _line("2026-11-30T10:10:00.000Z", "uid-2", "2026-11-30T12:00:00.000Z"))
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            _write_segment(store_folder, head)
            first = index.update(store_folder)
            self.assertEqual(first.broken, [BrokenLine(SEGMENT, 2)])
            self.assertEqual(first.lines_read, 3)
            _write_segment(store_folder, head + b"broken again\n")
            second = index.update(store_folder)
            self.assertEqual(second.broken, [BrokenLine(SEGMENT, 4)])
            self.assertEqual(second.lines_read, 1)
            self.assertEqual(index.broken_lines(),
                             [BrokenLine(SEGMENT, 2), BrokenLine(SEGMENT, 4)])
            index.close()

    def test_moved_last_line_reads_segment_again(self) -> None:
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2"),
                _event("2026-11-30T10:20:00.000Z", "uid-3")], NOVEMBER)
            index.update(store_folder)
            removed = events.EventKey(source="example_tool", native_id="native-uid-2")
            store.rewrite_segment(
                store_folder, SEGMENT, lambda line: b'"uid-2"' not in line.data)
            second = index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            content = (store_folder / SEGMENT).read_bytes()
            chained = _chained(_lines_of(store_folder))
            kept = events.EventKey(source="example_tool", native_id="native-uid-1")
            self.assertEqual(second.lines_read, 2)
            self.assertFalse(index.has_key(removed, purges))
            self.assertTrue(index.has_key(kept, purges))
            self.assertEqual(index.segment_states(),
                             [SegmentState(SEGMENT, len(content), chained)])
            index.close()

    def test_removed_segment_removes_its_events(self) -> None:
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2")], NOVEMBER)
            index.update(store_folder)
            self.assertEqual(index.counts(), (1, 2))
            (store_folder / SEGMENT).unlink()
            second = index.update(store_folder)
            self.assertEqual(second.lines_read, 0)
            self.assertEqual(index.counts(), (0, 0))
            self.assertEqual(index.segment_states(), [])
            self.assertFalse(index.has_key(
                events.EventKey(source="example_tool", native_id="native-uid-1"),
                store.PurgeSet.from_events([])))
            index.close()

    def test_other_format_rebuilds(self) -> None:
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2")], NOVEMBER)
            index.update(store_folder)
            tamper = sqlite3.connect(store_folder / "index.sqlite")
            tamper.execute("UPDATE meta SET format = 0")
            tamper.execute("DELETE FROM lines WHERE offset = 0")
            tamper.commit()
            tamper.close()
            index.update(store_folder)
            stored = sqlite3.connect(store_folder / "index.sqlite")
            row = stored.execute("SELECT format FROM meta").fetchone()
            stored.close()
            self.assertEqual(row[0], INDEX_FORMAT)
            self.assertEqual(index.counts(), (1, 2))
            self.assertTrue(index.has_key(
                events.EventKey(source="example_tool", native_id="native-uid-1"),
                store.PurgeSet.from_events([])))
            index.close()

    def test_two_updates_add_each_line_once(self) -> None:
        with support.TemporaryFolder() as store_folder:
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2")], NOVEMBER)
            first = LocalIndex(store_folder / "index.sqlite")
            second = LocalIndex(store_folder / "index.sqlite")
            first_update = first.update(store_folder)
            second_update = second.update(store_folder)
            self.assertEqual(first_update.lines_read, 2)
            self.assertEqual(second_update.lines_read, 0)
            self.assertEqual(second.counts(), (1, 2))
            self.assertTrue(second.has_key(
                events.EventKey(source="example_tool", native_id="native-uid-2"),
                store.PurgeSet.from_events([])))
            first.close()
            second.close()

    def test_rebuild_reads_every_segment_again(self) -> None:
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2")], NOVEMBER)
            index.update(store_folder)
            tamper = sqlite3.connect(store_folder / "index.sqlite")
            tamper.execute("DELETE FROM lines")
            tamper.commit()
            tamper.close()
            self.assertEqual(index.counts(), (1, 0))
            index.rebuild(store_folder)
            self.assertEqual(index.counts(), (1, 2))
            self.assertTrue(index.has_key(
                events.EventKey(source="example_tool", native_id="native-uid-1"),
                store.PurgeSet.from_events([])))
            index.close()

    def test_chained_hash(self) -> None:
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2")], NOVEMBER)
            index.update(store_folder)
            lines = _lines_of(store_folder)
            content = (store_folder / SEGMENT).read_bytes()
            h0 = hashlib.sha256(b"").digest()
            h1 = hashlib.sha256(h0 + lines[0]).digest()
            h2 = hashlib.sha256(h1 + lines[1]).digest()
            self.assertEqual(index.segment_states(),
                             [SegmentState(SEGMENT, len(content), h2.hex())])
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:20:00.000Z", "uid-3")], NOVEMBER)
            index.update(store_folder)
            lines = _lines_of(store_folder)
            h3 = hashlib.sha256(h2 + lines[2]).digest()
            self.assertEqual(index.segment_states()[0].chained_hash, h3.hex())
            index.close()

    def test_wal_mode(self) -> None:
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(
                store_folder, MACHINE, [_event("2026-11-30T10:00:00.000Z", "uid-1")], NOVEMBER)
            index.update(store_folder)
            connection = sqlite3.connect(store_folder / "index.sqlite")
            mode = connection.execute("PRAGMA journal_mode").fetchone()[0]
            connection.close()
            index.close()
        self.assertEqual(mode, "wal")


class TestLineStates(unittest.TestCase):
    """A broken line and a line of a newer schema version stay as rows of the index."""

    def test_newer_schema_is_flagged(self) -> None:
        head = (_line("2026-11-30T10:00:00.000Z", "uid-1", "2026-11-30T12:00:00.000Z")
                + _line("2026-11-30T10:10:00.000Z", "uid-2", "2026-11-30T12:00:00.000Z",
                        schema_version=2, kind="invented_kind"))
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            _write_segment(store_folder, head)
            first = index.update(store_folder)
            self.assertTrue(first.newer)
            self.assertTrue(index.has_newer())
            self.assertEqual(index.counts(), (1, 2))
            second = index.update(store_folder)
            self.assertFalse(second.newer)
            self.assertTrue(index.has_newer())
            index.close()

    def test_broken_and_newer_lines_stay_after_update(self) -> None:
        head = (b"not an event\n"
                + _line("2026-11-30T10:00:00.000Z", "uid-1", "2026-11-30T12:00:00.000Z",
                        schema_version=2, kind="invented_kind"))
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            _write_segment(store_folder, head)
            first = index.update(store_folder)
            self.assertEqual(first.broken, [BrokenLine(SEGMENT, 1)])
            self.assertTrue(first.newer)
            second = index.update(store_folder)
            self.assertEqual(second.lines_read, 0)
            self.assertEqual(index.broken_lines(), [BrokenLine(SEGMENT, 1)])
            self.assertTrue(index.has_newer())
            index.close()


class TestReads(unittest.TestCase):
    """A read gives a copy of the key only when no purge blocks it (ingestion.md › Store)."""

    def test_has_key_ignores_blocked_copy(self) -> None:
        key = events.EventKey(source="example_tool", native_id="native-uid-copy")
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-copy")], NOVEMBER)
            store.append_events(store_folder, OTHER_MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-copy", writer_version="0.2.0")], NOVEMBER)
            index.update(store_folder)
            self.assertTrue(index.has_key(key, store.PurgeSet.from_events([])))
            blocking = store.PurgeSet.from_events([_purge("purge-1", [key])])
            self.assertFalse(index.has_key(key, blocking))
            correcting = store.PurgeSet.from_events([_purge("purge-2", [key], corrected="0.2.0")])
            self.assertTrue(index.has_key(key, correcting))
            index.close()


class TestBusy(unittest.TestCase):
    """A command that cannot write within the limit stops with `IndexBusy`."""

    def test_index_busy_past_the_limit(self) -> None:
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite", limit_seconds=0.5)
            store.append_events(
                store_folder, MACHINE, [_event("2026-11-30T10:00:00.000Z", "uid-1")], NOVEMBER)
            index.update(store_folder)
            held = sqlite3.connect(store_folder / "index.sqlite")
            held.execute("BEGIN EXCLUSIVE")
            start = time.monotonic()
            with self.assertRaises(IndexBusy) as stopped:
                index.update(store_folder)
            elapsed = time.monotonic() - start
            held.rollback()
            held.close()
            free = index.update(store_folder)
            index.close()
        self.assertGreaterEqual(elapsed, 0.45)
        self.assertLess(elapsed, _POLL_SECONDS)
        self.assertEqual(stopped.exception.code, "index_busy")
        self.assertEqual(stopped.exception.values, {})
        self.assertEqual(stopped.exception.exit_code, 1)
        self.assertEqual(free.lines_read, 0)


class TestQueries(unittest.TestCase):
    """The queries of the index give one copy for each key, through the winning copy that the
    purges leave (`architecture.md` › Local index)."""

    def test_query_gives_winning_copy(self) -> None:
        # two machines hold one key: earliest ingested_at
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            early = _event("2026-11-30T10:00:00.000Z", "uid-shared",
                           session_id="session-early", tool="example_tool", cwd="/work/one")
            late = _event("2026-11-30T10:00:00.000Z", "uid-shared",
                          session_id="session-late", tool="example_tool", cwd="/work/two")
            store.append_events(store_folder, MACHINE, [early], NOVEMBER)
            store.append_events(store_folder, OTHER_MACHINE, [late], LATER)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            self.assertEqual(
                index.sessions_between(
                    support.utc("2026-11-30T09:00"), support.utc("2026-11-30T11:00"),
                    purges=purges),
                {("example_tool", "session-early")})
            self.assertEqual(
                index.session_events([("example_tool", "session-late")], purges=purges), [])
            self.assertEqual(
                index.session_events([("example_tool", "session-early")], purges=purges),
                [{**early, "ingested_at": INGESTED}])
            index.close()

    def test_blocked_copy_never_wins(self) -> None:
        # earlier copy blocked -> the later unblocked copy is given
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            entry = _ledger_event("2026-11-30T10:00:00.000Z", "entry-uid")
            later_copy = _ledger_event("2026-11-30T10:00:00.000Z", "entry-uid",
                                       writer_version="0.2.0")
            store.append_events(store_folder, MACHINE, [entry], NOVEMBER)
            store.append_events(store_folder, OTHER_MACHINE, [later_copy], LATER)
            index.update(store_folder)
            parts = [(support.utc("2026-11-30T09:00"), support.utc("2026-11-30T11:00"))]
            given = index.ledger_events_between(parts, purges=store.PurgeSet.from_events([]))
            self.assertEqual(given, [{**entry, "ingested_at": INGESTED}])
            key = events.EventKey(source="ledger", event_uid="entry-uid")
            blocking = store.PurgeSet.from_events([_purge("purge-1", [key], corrected="0.2.0")])
            given = index.ledger_events_between(parts, purges=blocking)
            self.assertEqual(given, [{**later_copy, "ingested_at": LATER_INSTANT}])
            index.close()

    def test_sessions_between_and_session_events(self) -> None:
        # two sessions in the range, one outside; the events of the inside ones only
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            first = _event("2026-11-30T10:00:00.000Z", "uid-1",
                           session_id="session-1", tool="example_tool", cwd="/work/one")
            second = _event("2026-11-30T11:00:00.000Z", "uid-2",
                            session_id="session-1", tool="example_tool", cwd="/work/one")
            third = _event("2026-11-30T12:00:00.000Z", "uid-3",
                           session_id="session-2", tool="other_tool", cwd="/work/two")
            outside = _event("2026-11-30T13:00:00.000Z", "uid-4",
                             session_id="session-3", tool="example_tool")
            store.append_events(store_folder, MACHINE, [first, second, third, outside], NOVEMBER)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            sessions = index.sessions_between(
                support.utc("2026-11-30T10:00"), support.utc("2026-11-30T13:00"), purges=purges)
            self.assertEqual(
                sessions, {("example_tool", "session-1"), ("other_tool", "session-2")})
            self.assertEqual(
                index.session_events(sessions, purges=purges),
                [{**first, "ingested_at": INGESTED},
                 {**second, "ingested_at": INGESTED},
                 {**third, "ingested_at": INGESTED}])
            index.close()

    def test_tools_of_session(self) -> None:
        # one id in two agent tools -> both
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1",
                       session_id="session-shared", tool="example_tool"),
                _event("2026-11-30T11:00:00.000Z", "uid-2",
                       session_id="session-shared", tool="other_tool"),
                _event("2026-11-30T12:00:00.000Z", "uid-3",
                       session_id="session-other", tool="example_tool")], NOVEMBER)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            self.assertEqual(index.tools_of_session("session-shared", purges=purges),
                             {"example_tool", "other_tool"})
            self.assertEqual(index.tools_of_session("session-unknown", purges=purges), set())
            index.close()

    def test_keys_written_below(self) -> None:
        # writer 0.1.0 and 0.1.1, below 0.1.1 -> the first only; the purge is never selected
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            key = events.EventKey(source="example_tool", native_id="native-uid-1")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1", session_id="session-1"),
                _event("2026-11-30T11:00:00.000Z", "uid-2", session_id="session-1",
                       writer_version="0.1.1"),
                _purge("purge-1", [key])], NOVEMBER)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            self.assertEqual(index.keys_written_below("0.1.1", purges=purges), [key])
            self.assertEqual(index.keys_written_below("0.1.0", purges=purges), [])
            self.assertEqual(index.keys_written_below("9.0.0", purges=purges),
                             [key, events.EventKey(source="example_tool",
                                                   native_id="native-uid-2")])
            self.assertEqual(index.keys_written_below("0.9.0", source="ledger", purges=purges),
                             [])
            index.close()

    def test_sessions_of_keys(self) -> None:
        # the sessions that hold the keys, as a purge with a corrected version names them
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1",
                       session_id="session-1", tool="example_tool"),
                _event("2026-11-30T11:00:00.000Z", "uid-2",
                       session_id="session-2", tool="other_tool")], NOVEMBER)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            keys = [
                events.EventKey(source="example_tool", native_id="native-uid-1"),
                events.EventKey(source="example_tool", native_id="native-uid-2"),
                events.EventKey(source="example_tool", native_id="native-unknown"),
            ]
            self.assertEqual(index.sessions_of_keys(keys, purges=purges),
                             {("example_tool", "session-1"), ("other_tool", "session-2")})
            self.assertEqual(index.sessions_of_keys([], purges=purges), set())
            index.close()

    def test_ledger_event_by_uid(self) -> None:
        # unknown event_uid -> None
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            entry = _ledger_event("2026-11-30T10:00:00.000Z", "entry-uid")
            store.append_events(store_folder, MACHINE, [entry], NOVEMBER)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            self.assertEqual(index.ledger_event_by_uid("entry-uid", purges=purges),
                             {**entry, "ingested_at": INGESTED})
            self.assertIsNone(index.ledger_event_by_uid("other-uid", purges=purges))
            index.close()

    def test_ledger_events_between(self) -> None:
        # by timestamp, not by start and end; two parts of one day
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            morning = _ledger_event(
                "2026-11-30T10:00:00.000Z", "entry-uid-1",
                start="2026-11-30T08:00:00.000Z", end="2026-11-30T09:30:00.000Z")
            afternoon = _ledger_event(
                "2026-11-30T14:00:00.000Z", "entry-uid-2",
                start="2026-11-30T15:30:00.000Z", end="2026-11-30T16:00:00.000Z")
            evening = _ledger_event(
                "2026-11-30T16:00:00.000Z", "entry-uid-3",
                start="2026-11-30T14:00:00.000Z", end="2026-11-30T14:30:00.000Z")
            store.append_events(store_folder, MACHINE, [morning, afternoon, evening], NOVEMBER)
            index.update(store_folder)
            parts = [
                (support.utc("2026-11-30T09:00"), support.utc("2026-11-30T12:00")),
                (support.utc("2026-11-30T13:00"), support.utc("2026-11-30T15:00")),
            ]
            given = index.ledger_events_between(parts, purges=store.PurgeSet.from_events([]))
            self.assertEqual(
                given,
                [{**morning, "ingested_at": INGESTED}, {**afternoon, "ingested_at": INGESTED}])
            index.close()

    def test_purge_events_need_no_purge_set(self) -> None:
        # a purge that lists a key -> purge_events() gives it
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            key = events.EventKey(source="example_tool", native_id="native-uid-1")
            purge = _purge("purge-1", [key])
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"), purge], NOVEMBER)
            index.update(store_folder)
            self.assertEqual(index.purge_events(), [{**purge, "ingested_at": INGESTED}])
            blocked = store.PurgeSet.from_events(index.purge_events())
            self.assertFalse(index.has_key(key, blocked))
            index.close()

    def test_confirmations_of(self) -> None:
        # the confirmations whose day is one of the days
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            first = _ledger_event("2026-11-30T10:00:00.000Z", "confirm-uid-1",
                                  kind="timesheet_confirmation", day="2026-11-30",
                                  entries=[{"project": "project-one", "duration": 3600}])
            second = _ledger_event("2026-11-30T12:00:00.000Z", "confirm-uid-2",
                                   kind="timesheet_confirmation", day="2026-11-30",
                                   entries=[{"duration": 1800}])
            other = _ledger_event("2026-11-30T12:00:00.000Z", "confirm-uid-3",
                                  kind="timesheet_confirmation", day="2026-12-01",
                                  entries=[{"project": "project-one", "duration": 3600}])
            store.append_events(store_folder, MACHINE, [first, second, other], NOVEMBER)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            self.assertEqual(
                index.confirmations_of(["2026-11-30"], purges=purges),
                [{**first, "ingested_at": INGESTED}, {**second, "ingested_at": INGESTED}])
            self.assertEqual(index.confirmations_of([], purges=purges), [])
            index.close()

    def test_intervals_between(self) -> None:
        # the manual entries and interval annotations whose interval meets the range
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            entry = _ledger_event("2026-11-30T08:00:00.000Z", "entry-uid-1",
                                  manual_mode="overlapping",
                                  start="2026-11-30T08:00:00.000Z",
                                  end="2026-11-30T09:30:00.000Z")
            note = _ledger_event("2026-11-30T12:00:00.000Z", "note-uid-1", kind="annotation",
                                 project="project-one",
                                 start="2026-11-30T12:00:00.000Z",
                                 end="2026-11-30T13:00:00.000Z")
            session_note = _ledger_event("2026-11-30T12:30:00.000Z", "note-uid-2",
                                         kind="annotation", project="project-one",
                                         annotates={"tool": "example_tool",
                                                    "session_id": "session-1"})
            away = _ledger_event("2026-11-30T13:00:00.000Z", "entry-uid-2",
                                 manual_mode="additional",
                                 start="2026-11-30T13:00:00.000Z",
                                 end="2026-11-30T14:00:00.000Z")
            store.append_events(store_folder, MACHINE, [entry, note, session_note, away],
                                NOVEMBER)
            index.update(store_folder)
            given = index.intervals_between(
                support.utc("2026-11-30T09:00"), support.utc("2026-11-30T12:30"),
                purges=store.PurgeSet.from_events([]))
            self.assertEqual(
                given,
                [{**entry, "ingested_at": INGESTED}, {**note, "ingested_at": INGESTED}])
            index.close()

    def test_bookkeeping(self) -> None:
        # the retractions, the purges, and the session annotations; no entry, no interval note
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            key = events.EventKey(source="example_tool", native_id="native-uid-1")
            purge = _purge("purge-1", [key])
            retraction = _ledger_event("2026-11-30T13:00:00.000Z", "retract-uid-1",
                                       kind="retraction", retracts=key.to_json())
            session_note = _ledger_event("2026-11-30T14:00:00.000Z", "note-uid-1",
                                         kind="annotation", project="project-one",
                                         annotates={"tool": "example_tool",
                                                    "session_id": "session-1"})
            interval_note = _ledger_event("2026-11-30T15:00:00.000Z", "note-uid-2",
                                          kind="annotation", project="project-one",
                                          start="2026-11-30T15:00:00.000Z",
                                          end="2026-11-30T16:00:00.000Z")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1"), purge, retraction, session_note,
                interval_note], NOVEMBER)
            index.update(store_folder)
            self.assertEqual(
                index.bookkeeping(purges=store.PurgeSet.from_events([])),
                [{**purge, "ingested_at": INGESTED},
                 {**retraction, "ingested_at": INGESTED},
                 {**session_note, "ingested_at": INGESTED}])
            index.close()

    def test_native_id_owner(self) -> None:
        # the session that holds the key, or None
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1",
                       session_id="session-1", tool="example_tool")], NOVEMBER)
            index.update(store_folder)
            key = events.EventKey(source="example_tool", native_id="native-uid-1")
            purges = store.PurgeSet.from_events([])
            self.assertEqual(
                index.native_id_owner("example_tool", "native-uid-1", purges=purges),
                ("example_tool", "session-1"))
            self.assertIsNone(
                index.native_id_owner("example_tool", "native-unknown", purges=purges))
            self.assertIsNone(
                index.native_id_owner("example_tool", "native-uid-1",
                                      purges=store.PurgeSet.from_events([_purge("p", [key])])))
            index.close()

    def test_close_releases_the_index_file(self) -> None:
        # the closed index holds no file, and a write opens the index again
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(
                store_folder, MACHINE, [_event("2026-11-30T10:00:00.000Z", "uid-1")], NOVEMBER)
            index.update(store_folder)
            key = events.EventKey(source="example_tool", native_id="native-uid-1")
            purges = store.PurgeSet.from_events([])
            index.close()
            (store_folder / "index.sqlite").unlink()
            self.assertFalse((store_folder / "index.sqlite").exists())
            index.update(store_folder)
            self.assertTrue(index.has_key(key, purges))
            index.close()


def _session_event(
    timestamp: str, event_uid: str, session_id: str, **overrides: Any,
) -> events.Event:
    """An invented event of a session of the agent tool `example_tool`."""
    return _event(timestamp, event_uid, tool="example_tool", session_id=session_id, **overrides)


def _three_sessions(store_folder: Path) -> list[events.Event]:
    """A store of three sessions: two events of the first, whose first event has a copy that
    another machine wrote, and five events of each of the two others, so that the rows of
    the keys of the first session are fewer than a third of the rows of the store. The
    events come in the order of their timestamps."""
    first = _session_event("2026-11-30T10:00:00.000Z", "own-1", "session-1")
    second = _session_event("2026-11-30T10:10:00.000Z", "own-2", "session-1")
    copy = _session_event("2026-11-30T10:00:00.000Z", "own-1", "session-1", writer_version="0.2.0")
    others = [
        _session_event("2026-11-30T10:20:00.000Z", "other-1", "session-2"),
        _session_event("2026-11-30T10:25:00.000Z", "other-2", "session-2"),
        _session_event("2026-11-30T10:30:00.000Z", "other-3", "session-2"),
        _session_event("2026-11-30T10:35:00.000Z", "other-4", "session-2"),
        _session_event("2026-11-30T10:40:00.000Z", "other-5", "session-2"),
        _session_event("2026-11-30T10:45:00.000Z", "other-6", "session-3"),
        _session_event("2026-11-30T10:50:00.000Z", "other-7", "session-3"),
        _session_event("2026-11-30T10:55:00.000Z", "other-8", "session-3"),
        _session_event("2026-11-30T11:00:00.000Z", "other-9", "session-3"),
        _session_event("2026-11-30T11:05:00.000Z", "other-10", "session-3"),
    ]
    store.append_events(store_folder, MACHINE, [first, second, *others], NOVEMBER)
    store.append_events(store_folder, OTHER_MACHINE, [copy], LATER)
    return [first, second, *others]


def _decoded_rows(counting: mock.Mock) -> list[tuple[str, str]]:
    """The rows that the `loads` of a module `json` wrapped by `mock` read, one for each
    text, as (`event_uid`, `writer_version`): the writer version tells the copies of one key
    apart."""
    return [(event["event_uid"], event["writer_version"])
            for event in map(json.loads, (call.args[0] for call in counting.loads.call_args_list))]


class TestSessionEvents(unittest.TestCase):
    """The session events of a period are the winning copies of the keys of its sessions,
    whatever session holds the other copies of a key (`event-schema.md` › Keys and
    invariants, `architecture.md` › Data flow)."""

    def test_copy_in_two_sessions_winner_in_the_period(self) -> None:
        # one key in two sessions: the first machine holds the copy with the earliest
        # `ingested_at`, in the period; the copy of the other machine lies in the period
        # (1a) or two days before it (1b). The event is the first copy; the session of the
        # other copy holds no other event in the period, so nothing of it is given
        winner = _session_event("2026-11-30T10:00:00.000Z", "shared", "session-one")
        own = _session_event("2026-11-30T11:00:00.000Z", "own-1", "session-one")
        given = [{**winner, "ingested_at": AT_NOON}, {**own, "ingested_at": AT_ONE_PM}]
        for at in ("2026-11-30T10:00:00.000Z", "2026-11-28T10:00:00.000Z"):
            with self.subTest(other_copy_at=at), support.TemporaryFolder() as store_folder:
                other = _session_event(at, "shared", "session-two",
                                       writer_version="0.2.0", cwd="/work/two")
                index = LocalIndex(store_folder / "index.sqlite")
                store.append_events(store_folder, MACHINE, [winner], NOON)
                store.append_events(store_folder, OTHER_MACHINE, [other, own], ONE_PM)
                index.update(store_folder)
                purges = store.PurgeSet.from_events([])
                self.assertEqual(
                    index.sessions_between(DAY_START, DAY_END, purges=purges),
                    {("example_tool", "session-one")})
                self.assertEqual(
                    index.session_events([("example_tool", "session-one")], purges=purges),
                    given)
                self.assertEqual(
                    index.session_events([("example_tool", "session-two")], purges=purges), [])
                self.assertEqual(
                    index.sessions_and_events(DAY_START, DAY_END, purges=purges),
                    ({("example_tool", "session-one")}, given))
                index.close()

    def test_copy_in_two_sessions_winner_outside_the_period(self) -> None:
        # the copy with the earliest `ingested_at` lies two days before the period, in a
        # session that no event of the period names; the other copy is in the period, in a
        # wanted session. The key is read whole: its winning copy is of a session that is
        # not wanted, so nothing of the key is given. The events of a third session, all
        # outside the period, hold enough rows of the store that the rows of the wanted
        # keys are fewer than a third of them, so the query takes them by row identifier
        winner = _session_event("2026-11-28T10:00:00.000Z", "shared", "session-two")
        inside = _session_event("2026-11-30T10:00:00.000Z", "shared", "session-one",
                                writer_version="0.2.0", cwd="/work/two")
        own = _session_event("2026-11-30T11:00:00.000Z", "own-1", "session-one")
        filler = [_session_event(f"2026-11-28T10:{5 * number:02d}:00.000Z", f"away-{number}",
                                 "session-three") for number in range(1, 7)]
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [winner, *filler], TWO_DAYS_BEFORE_NOON)
            store.append_events(store_folder, OTHER_MACHINE, [inside, own], ONE_PM)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            given = [{**own, "ingested_at": AT_ONE_PM}]
            self.assertEqual(
                index.sessions_between(DAY_START, DAY_END, purges=purges),
                {("example_tool", "session-one")})
            self.assertEqual(
                index.session_events([("example_tool", "session-one")], purges=purges), given)
            self.assertEqual(
                index.sessions_and_events(DAY_START, DAY_END, purges=purges),
                ({("example_tool", "session-one")}, given))
            index.close()

    def test_copy_in_two_sessions_winner_blocked_by_a_purge(self) -> None:
        # a purge with a corrected version blocks the copy with the earliest `ingested_at`;
        # the other copy, in the period, is of a wanted session: it is the event. Wanted
        # alone, the session of the blocked copy holds nothing, as a blocked copy never
        # wins; without the purge it holds the blocked copy, and the wanted session
        # loses the key
        earliest = _session_event("2026-11-30T10:00:00.000Z", "shared", "session-two")
        unblocked = _session_event("2026-11-30T10:05:00.000Z", "shared", "session-one",
                                   writer_version="0.2.0", cwd="/work/two")
        own = _session_event("2026-11-30T11:00:00.000Z", "own-1", "session-one")
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [earliest], NOON)
            store.append_events(store_folder, OTHER_MACHINE, [unblocked, own], ONE_PM)
            index.update(store_folder)
            key = events.EventKey(source="example_tool", native_id="native-shared")
            purges = store.PurgeSet.from_events([_purge("purge-1", [key], corrected="0.2.0")])
            given = [{**unblocked, "ingested_at": AT_ONE_PM},
                     {**own, "ingested_at": AT_ONE_PM}]
            self.assertEqual(
                index.sessions_between(DAY_START, DAY_END, purges=purges),
                {("example_tool", "session-one")})
            self.assertEqual(
                index.session_events([("example_tool", "session-one")], purges=purges), given)
            self.assertEqual(
                index.session_events([("example_tool", "session-two")], purges=purges), [])
            self.assertEqual(
                index.sessions_and_events(DAY_START, DAY_END, purges=purges),
                ({("example_tool", "session-one")}, given))
            free = store.PurgeSet.from_events([])
            self.assertEqual(
                index.session_events([("example_tool", "session-two")], purges=free),
                [{**earliest, "ingested_at": AT_NOON}])
            self.assertEqual(
                index.session_events([("example_tool", "session-one")], purges=free),
                [{**own, "ingested_at": AT_ONE_PM}])
            index.close()

    def test_session_across_the_boundary_of_the_period(self) -> None:
        # a session with an event before the start of the day and one after it, inside the
        # margin, is whole and in the order of its timestamps; a session whose only event is
        # 3 h before the start is in the period, one whose only event is 13 h before is not
        first = _session_event("2026-11-29T22:30:00.000Z", "span-1", "session-span")
        second = _session_event("2026-11-30T00:30:00.000Z", "span-2", "session-span")
        far = _session_event("2026-11-29T10:00:00.000Z", "far", "session-far")
        margin = _session_event("2026-11-29T20:00:00.000Z", "margin", "session-margin")
        with support.TemporaryFolder() as store_folder:
            index = LocalIndex(store_folder / "index.sqlite")
            store.append_events(store_folder, MACHINE, [first, second, far, margin], NOON)
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            sessions = {("example_tool", "session-span"), ("example_tool", "session-margin")}
            given = [{**margin, "ingested_at": AT_NOON}, {**first, "ingested_at": AT_NOON},
                     {**second, "ingested_at": AT_NOON}]
            self.assertEqual(index.sessions_between(DAY_START, DAY_END, purges=purges), sessions)
            self.assertEqual(index.session_events(sessions, purges=purges), given)
            self.assertEqual(
                index.sessions_and_events(DAY_START, DAY_END, purges=purges), (sessions, given))
            both = sessions | {("example_tool", "session-far")}
            whole = [{**far, "ingested_at": AT_NOON}, *given]
            self.assertEqual(
                index.sessions_and_events(TWO_DAYS_START, DAY_END, purges=purges), (both, whole))
            index.close()

    def test_session_events_decodes_no_row_of_another_session(self) -> None:
        # the rows decoded for the events of one session are the copies of its keys, and no
        # row of another session
        with support.TemporaryFolder() as store_folder:
            first, second, *_ = _three_sessions(store_folder)
            index = LocalIndex(store_folder / "index.sqlite")
            index.update(store_folder)
            counting = mock.Mock(wraps=json)
            with mock.patch.object(index_module, "json", counting):
                given = index.session_events([("example_tool", "session-1")],
                                             purges=store.PurgeSet.from_events([]))
            self.assertEqual(given, [{**first, "ingested_at": INGESTED},
                                     {**second, "ingested_at": INGESTED}])
            self.assertCountEqual(_decoded_rows(counting),
                                  [("own-1", "0.1.0"), ("own-1", "0.2.0"), ("own-2", "0.1.0")])
            index.close()

    def test_sessions_and_events_decodes_each_row_once(self) -> None:
        # the sessions of the period and their events: a row that the first query decoded
        # is not decoded again by the second
        with support.TemporaryFolder() as store_folder:
            _three_sessions(store_folder)
            index = LocalIndex(store_folder / "index.sqlite")
            index.update(store_folder)
            counting = mock.Mock(wraps=json)
            with mock.patch.object(index_module, "json", counting):
                sessions, _ = index.sessions_and_events(
                    DAY_START, DAY_END, purges=store.PurgeSet.from_events([]))
            self.assertEqual(sessions, {("example_tool", "session-1"),
                                        ("example_tool", "session-2"),
                                        ("example_tool", "session-3")})
            self.assertCountEqual(_decoded_rows(counting),
                                  [("own-1", "0.1.0"), ("own-1", "0.2.0"), ("own-2", "0.1.0"),
                                  *[("other-" + str(number), "0.1.0")
                                    for number in range(1, 11)]])
            index.close()


class _RecordingConnection:
    """The connection of an index that keeps every statement it runs with its parameters.

    A test explains the plan of a recorded statement through the wrapped connection, so the
    statement whose plan it reads is the one the code built, not a copy written in the test.
    """

    def __init__(self, connection: sqlite3.Connection) -> None:
        self._connection = connection
        self.statements: list[tuple[str, tuple[Any, ...]]] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._connection, name)

    def execute(self, statement: str, parameters: Any = ()) -> sqlite3.Cursor:
        """Run the statement on the wrapped connection, keeping it with its parameters."""
        self.statements.append((statement, tuple(parameters)))
        return self._connection.execute(statement, parameters)


class _RecordingIndex(LocalIndex):
    """A local index whose connection records every statement it runs with its parameters.

    `recorder` holds the recording connection once the index has opened one.
    """

    def _connect(self) -> Any:
        if not isinstance(self._connection, _RecordingConnection):
            self.recorder = _RecordingConnection(super()._connect())
            self._connection = self.recorder
        return self._connection


class TestKeyIndex(unittest.TestCase):
    """The lookups of a key read the index on it; the scans that name no key read the table."""

    def _plans_of_key_lookups(self, index: _RecordingIndex) -> list[tuple[str, str]]:
        """The plan of every statement that the index ran and that looks a key up (`key = ?`
        or `key IN (...)`), explained through the connection of the index."""
        plans: list[tuple[str, str]] = []
        # a snapshot of the statements: each explanation runs through the recorder too
        for statement, parameters in list(index.recorder.statements):
            if "key = ?" not in statement and "key IN (" not in statement:
                continue
            explained = index.recorder.execute(
                "EXPLAIN QUERY PLAN " + statement, parameters).fetchall()
            plans.append((statement, " ".join(row[3] for row in explained)))
        return plans

    def test_every_key_lookup_reads_the_index_on_the_key(self) -> None:
        # has_key, native_id_owner, ledger_event_by_uid and sessions_of_keys each look a key
        # up in one statement, and the index on the key serves each statement
        with support.TemporaryFolder() as store_folder:
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1",
                       tool="example_tool", session_id="session-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2",
                       tool="example_tool", session_id="session-2")], NOVEMBER)
            index = _RecordingIndex(store_folder / "index.sqlite")
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            index.has_key(
                events.EventKey(source="example_tool", native_id="native-uid-1"), purges)
            index.native_id_owner("example_tool", "native-uid-2", purges=purges)
            index.ledger_event_by_uid("uid-3", purges=purges)
            index.sessions_of_keys(
                [events.EventKey(source="example_tool", native_id="native-uid-1")],
                purges=purges)
            plans = self._plans_of_key_lookups(index)
            self.assertEqual(len(plans), 4)
            for statement, explanation in plans:
                self.assertIn("lines_key", explanation, statement)
                self.assertNotIn("SCAN lines", explanation, statement)
            index.close()

    def test_an_older_file_gains_the_index_on_the_key(self) -> None:
        # a file that a version without the index on the key wrote gains it at the next
        # update, which reads no line, and keeps every row
        with support.TemporaryFolder() as store_folder:
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1")], NOVEMBER)
            index = LocalIndex(store_folder / "index.sqlite")
            index.update(store_folder)
            index.close()
            older = sqlite3.connect(store_folder / "index.sqlite")
            older.execute("DROP INDEX IF EXISTS lines_key")
            older.commit()
            older.close()
            index = LocalIndex(store_folder / "index.sqlite")
            read = index.update(store_folder)
            self.assertEqual(read.lines_read, 0)
            held = sqlite3.connect(store_folder / "index.sqlite")
            names = {row[0] for row in held.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index'")}
            held.close()
            self.assertIn("lines_key", names)
            self.assertEqual(index.counts(), (1, 1))
            self.assertTrue(index.has_key(
                events.EventKey(source="example_tool", native_id="native-uid-1"),
                store.PurgeSet.from_events([])))
            index.close()

    def test_a_key_that_only_a_non_event_row_holds_stays_unfound(self) -> None:
        # the index on the key holds the key of every row, and the lookup keeps the state in
        # its where clause: a key written into a broken row is not found, as on the full scan
        with support.TemporaryFolder() as store_folder:
            _write_segment(store_folder, b"not an event\n"
                          + _line("2026-11-30T10:00:00.000Z", "uid-1",
                                  "2026-11-30T12:00:00.000Z"))
            index = _RecordingIndex(store_folder / "index.sqlite")
            index.update(store_folder)
            broken_key = events.EventKey(source="example_tool", native_id="native-uid-2")
            tamper = sqlite3.connect(store_folder / "index.sqlite")
            tamper.execute("UPDATE lines SET key = ? WHERE state = 'broken'",
                           (index_module._key_text(broken_key),))
            tamper.commit()
            tamper.close()
            purges = store.PurgeSet.from_events([])
            self.assertFalse(index.has_key(broken_key, purges))
            self.assertTrue(index.has_key(
                events.EventKey(source="example_tool", native_id="native-uid-1"), purges))
            plans = self._plans_of_key_lookups(index)
            self.assertEqual(len(plans), 2)
            for statement, explanation in plans:
                self.assertIn("lines_key", explanation, statement)
                self.assertNotIn("SCAN lines", explanation, statement)
            index.close()

    def test_a_scan_that_names_no_key_reads_the_table(self) -> None:
        # the clause-less scan, the timestamp scan and the ledger scan constrain no key, so the
        # index on the key gives them nothing: each reads the table once, not row by row in the
        # order of the keys
        with support.TemporaryFolder() as store_folder:
            store.append_events(store_folder, MACHINE, [
                _event("2026-11-30T10:00:00.000Z", "uid-1",
                       tool="example_tool", session_id="session-1"),
                _event("2026-11-30T10:10:00.000Z", "uid-2",
                       tool="example_tool", session_id="session-1"),
                _ledger_event("2026-11-30T11:00:00.000Z", "entry-uid",
                              start="2026-11-30T09:00:00.000Z",
                              end="2026-11-30T09:30:00.000Z")], NOVEMBER)
            index = _RecordingIndex(store_folder / "index.sqlite")
            index.update(store_folder)
            purges = store.PurgeSet.from_events([])
            ran = len(index.recorder.statements)
            self.assertEqual(
                len(index.session_events([("example_tool", "session-1")], purges=purges)), 2)
            self.assertEqual(index.sessions_between(DAY_START, DAY_END, purges=purges),
                             {("example_tool", "session-1")})
            self.assertEqual(len(index.ledger_events_between(
                [(DAY_START, DAY_END)], purges=purges)), 1)
            scans = [(statement, parameters)
                     for statement, parameters in index.recorder.statements[ran:]
                     if statement.startswith("SELECT")]
            # the narrow scan and the clause-less scan of session_events, the timestamp scan,
            # the ledger scan
            self.assertEqual(len(scans), 4)
            for statement, parameters in scans:
                explained = index.recorder.execute(
                    "EXPLAIN QUERY PLAN " + statement, parameters).fetchall()
                with self.subTest(statement=statement):
                    self.assertNotIn("lines_key", " ".join(row[3] for row in explained))
            index.close()
