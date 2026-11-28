"""Tests of the selection: the whole sessions of the period with the margin around it, the
confirmations by day, the declared intervals that intersect the period, the bookkeeping
events at any instant, the retraction of a retraction, the purged events, and the warnings
of the broken lines, of a newer schema version, and of the held-back sessions
(`architecture.md` › Data flow)."""

import unittest
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import support
from ai_effort_ledger import days, events, store
from ai_effort_ledger.configuration import DayStartEntry, ReportParameters, TimeZoneEntry
from ai_effort_ledger.index import BrokenLine, LocalIndex
from ai_effort_ledger.selection import Selection, cancelled, select

ROME = "Europe/Rome"
MACHINE = "3f0d5a1e-8c2b-4d6e-9f0a-1b2c3d4e5f60"
TOOL = "example_tool"
SESSION = "session-1"
OTHER_SESSION = "session-other"
# The local day 2026-11-30 of Rome (UTC+1 in winter) runs from 23:00 UTC of 11-29 to
# 23:00 UTC of 11-30; the report parameters of the tests give the margin of 4 h, so the
# sessions are sought from 19:00 UTC of 11-29 to 03:00 UTC of 12-01.
FIRST = date(2026, 11, 30)
SEGMENT = f"segments/{MACHINE}/2026-11.jsonl"
SEPTEMBER = support.utc("2026-09-10T09:00")
OCTOBER = support.utc("2026-10-05T09:00")
NOVEMBER = support.utc("2026-11-30T12:00")
INGESTED = events.format_instant(NOVEMBER)


def rome_days() -> days.LocalDays:
    """The local days of a person in Rome from 1970, with the day start at midnight."""
    return days.LocalDays(
        [TimeZoneEntry(ROME, support.utc("1970-01-01T00:00"), 2)],
        [DayStartEntry(time(0, 0), date(1970, 1, 1), 3)],
    )


def _event(timestamp: str, event_uid: str, **overrides: Any) -> events.Event:
    """A complete invented event of a session of the agent tool, without `ingested_at`."""
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
        "tool": TOOL,
        "session_id": SESSION,
    }
    event.update(overrides)
    return event


def _declared(timestamp: str, event_uid: str, **overrides: Any) -> events.Event:
    """A complete invented event that a command of the ledger writes, without `ingested_at`."""
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


def _purge(timestamp: str, event_uid: str, keys: list[events.EventKey]) -> events.Event:
    """A complete invented purge event that lists the keys."""
    return {
        "schema_version": events.SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": event_uid,
        "timestamp": timestamp,
        "writer_version": "0.1.0",
        "actor": "human",
        "kind": "purge",
        "machine": MACHINE,
        "purge_reason": "content",
        "purged_keys": [key.to_json() for key in keys],
    }


def _entry(timestamp: str, event_uid: str, start: str, end: str) -> events.Event:
    """A manual entry in the overlapping mode over the interval."""
    return _declared(timestamp, event_uid, manual_mode="overlapping", start=start, end=end)


def _line(event: events.Event, ingested_at: str = INGESTED) -> bytes:
    """One line of a segment written by hand: the event with its `ingested_at`."""
    return events.encode_event({**event, "ingested_at": ingested_at})


def _write(store_folder: Path, added: list[events.Event], now: datetime = NOVEMBER) -> None:
    """Append the events to the segment of the machine for the month of the instant."""
    store.append_events(store_folder, MACHINE, added, now)


def _write_segment(store_folder: Path, content: bytes) -> None:
    """Write the bytes of the segment of the tests by hand into the store folder."""
    path = store_folder / SEGMENT
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _select(
    store_folder: Path,
    index: LocalIndex | None = None,
    held_back: set[tuple[str, str]] | None = None,
) -> Selection:
    """The selection of the day of the tests, on the given index or on a new one."""
    own = index if index is not None else LocalIndex(store_folder / "index.sqlite")
    try:
        return select(own, store_folder, rome_days(), FIRST, FIRST, ReportParameters(),
                      set() if held_back is None else held_back)
    finally:
        own.close()


class SelectionTests(unittest.TestCase):
    """The selection follows `architecture.md` › Data flow and `metrics.md` › Declared
    values: a report of an empty index gives the same figures."""

    def test_whole_session_is_selected(self) -> None:
        # a session with an event inside: also its event 5 h before the start, outside
        # the margin; a session of another day stays out
        with support.TemporaryFolder() as store_folder:
            inside = _event("2026-11-30T10:00:00.000Z", "uid-inside")
            earlier = _event("2026-11-29T18:00:00.000Z", "uid-earlier")
            away = _event("2026-11-20T10:00:00.000Z", "uid-away", session_id=OTHER_SESSION)
            _write(store_folder, [earlier, inside, away])
            given = _select(store_folder)
            self.assertEqual(
                given.session_events,
                [{**earlier, "ingested_at": INGESTED}, {**inside, "ingested_at": INGESTED}])

    def test_margin_around_the_period(self) -> None:
        # margin = max(stale_limit, idle_gap) = 4 h: a session whose only event is 3 h
        # before the start or after the end -> selected; 5 h -> not
        with support.TemporaryFolder() as store_folder:
            before_in = _event("2026-11-29T20:00:00.000Z", "uid-before-in",
                               session_id="session-before-in")
            before_out = _event("2026-11-29T18:00:00.000Z", "uid-before-out",
                                session_id="session-before-out")
            after_in = _event("2026-12-01T02:00:00.000Z", "uid-after-in",
                              session_id="session-after-in")
            after_out = _event("2026-12-01T04:00:00.000Z", "uid-after-out",
                               session_id="session-after-out")
            _write(store_folder, [after_out, before_out, after_in, before_in])
            given = _select(store_folder)
            self.assertEqual(
                given.session_events,
                [{**before_in, "ingested_at": INGESTED}, {**after_in, "ingested_at": INGESTED}])

    def test_confirmations_by_day(self) -> None:
        # every confirmation of the day of the period, retracted or not; the days outside
        # the period stay out
        with support.TemporaryFolder() as store_folder:
            first = _declared("2026-11-30T09:00:00.000Z", "confirm-uid-1",
                              kind="timesheet_confirmation", day="2026-11-30",
                              entries=[{"project": "project-one", "duration": 3600}])
            second = _declared("2026-11-30T12:00:00.000Z", "confirm-uid-2",
                               kind="timesheet_confirmation", day="2026-11-30",
                               entries=[{"duration": 1800}],
                               replaces=events.event_key(first).to_json())
            third = _declared("2026-11-30T15:00:00.000Z", "confirm-uid-3",
                              kind="timesheet_confirmation", day="2026-11-30",
                              entries=[{"project": "project-one", "duration": 7200}])
            retraction = _declared("2026-11-30T16:00:00.000Z", "retract-uid-1",
                                   kind="retraction", retracts=events.event_key(third).to_json())
            before = _declared("2026-11-29T09:00:00.000Z", "confirm-uid-4",
                               kind="timesheet_confirmation", day="2026-11-29", entries=[])
            after = _declared("2026-12-01T09:00:00.000Z", "confirm-uid-5",
                              kind="timesheet_confirmation", day="2026-12-01", entries=[])
            _write(store_folder, [after, before, first, second, third, retraction])
            given = _select(store_folder)
            self.assertEqual(
                given.confirmations,
                [{**first, "ingested_at": INGESTED}, {**second, "ingested_at": INGESTED},
                 {**third, "ingested_at": INGESTED}])
            self.assertEqual(given.cancelled, {events.event_key(third)})
            self.assertEqual(given.retractions, [{**retraction, "ingested_at": INGESTED}])

    def test_intervals_that_intersect(self) -> None:
        # manual entry crossing the period start; an interval that ends at the start or
        # starts at the end does not intersect
        with support.TemporaryFolder() as store_folder:
            crossing = _entry("2026-11-29T20:00:00.000Z", "entry-uid-1",
                              "2026-11-29T20:00:00.000Z", "2026-11-30T02:00:00.000Z")
            before = _entry("2026-11-29T20:00:00.000Z", "entry-uid-2",
                            "2026-11-29T20:00:00.000Z", "2026-11-29T22:00:00.000Z")
            touching_start = _entry("2026-11-29T21:00:00.000Z", "entry-uid-3",
                                    "2026-11-29T21:00:00.000Z", "2026-11-29T23:00:00.000Z")
            touching_end = _entry("2026-11-30T23:00:00.000Z", "entry-uid-4",
                                  "2026-11-30T23:00:00.000Z", "2026-12-01T00:00:00.000Z")
            note = _declared("2026-11-29T22:00:00.000Z", "note-uid-1", kind="annotation",
                             project="project-one", start="2026-11-29T22:00:00.000Z",
                             end="2026-11-30T01:00:00.000Z")
            _write(store_folder, [before, touching_start, crossing, touching_end, note])
            given = _select(store_folder)
            self.assertEqual(given.manual_entries, [{**crossing, "ingested_at": INGESTED}])
            self.assertEqual(given.annotations, [{**note, "ingested_at": INGESTED}])

    def test_bookkeeping_at_any_instant(self) -> None:
        # retraction and purge from months before, and an annotation of a session after
        # the period: all of them count, at any instant
        with support.TemporaryFolder() as store_folder:
            inside = _event("2026-11-30T10:00:00.000Z", "uid-inside")
            old_entry = _declared("2026-10-01T08:00:00.000Z", "entry-uid-old",
                                  manual_mode="overlapping", start="2026-10-01T08:00:00.000Z",
                                  end="2026-10-01T09:00:00.000Z")
            retraction = _declared("2026-10-05T08:00:00.000Z", "retract-uid-old",
                                   kind="retraction",
                                   retracts=events.event_key(old_entry).to_json())
            absent = events.EventKey(source="example_tool", native_id="native-gone")
            purge = _purge("2026-09-10T08:00:00.000Z", "purge-uid-old", [absent])
            note = _declared("2026-12-05T08:00:00.000Z", "note-uid-late", kind="annotation",
                             project="project-one",
                             annotates={"tool": TOOL, "session_id": SESSION})
            _write(store_folder, [purge], SEPTEMBER)
            _write(store_folder, [old_entry, retraction], OCTOBER)
            _write(store_folder, [note, inside])
            given = _select(store_folder)
            self.assertEqual(given.session_events, [{**inside, "ingested_at": INGESTED}])
            self.assertEqual(given.manual_entries, [])
            self.assertEqual(given.annotations, [{**note, "ingested_at": INGESTED}])
            self.assertEqual(
                given.retractions, [{**retraction, "ingested_at": events.format_instant(OCTOBER)}])
            self.assertEqual(given.cancelled, {events.event_key(old_entry)})

    def test_retraction_of_retraction_brings_back(self) -> None:
        # a retraction that a retraction cancels cancels nothing: the event it named
        # counts again
        with support.TemporaryFolder() as store_folder:
            kept = _event("2026-11-30T10:00:00.000Z", "uid-kept")
            named = _event("2026-11-30T11:00:00.000Z", "uid-named")
            first = _declared("2026-11-30T12:00:00.000Z", "retract-uid-1", kind="retraction",
                              retracts=events.event_key(named).to_json())
            second = _declared("2026-11-30T13:00:00.000Z", "retract-uid-2", kind="retraction",
                               retracts=events.event_key(first).to_json())
            _write(store_folder, [named, first, kept, second])
            given = _select(store_folder)
            self.assertEqual(
                given.session_events,
                [{**kept, "ingested_at": INGESTED}, {**named, "ingested_at": INGESTED}])
            self.assertEqual(given.cancelled, {events.event_key(first)})
            self.assertEqual(cancelled([first]), {events.event_key(named)})
            self.assertEqual(cancelled([first, second]), {events.event_key(first)})

    def test_third_retraction_cancels_the_event_again(self) -> None:
        # a retraction of the retraction of a retraction: the event it named is cancelled
        # again, so the selection leaves it out
        with support.TemporaryFolder() as store_folder:
            kept = _event("2026-11-30T10:00:00.000Z", "uid-kept")
            named = _event("2026-11-30T11:00:00.000Z", "uid-named")
            first = _retraction("2026-11-30T12:00:00.000Z", "retract-uid-1", named)
            second = _retraction("2026-11-30T13:00:00.000Z", "retract-uid-2", first)
            third = _retraction("2026-11-30T14:00:00.000Z", "retract-uid-3", second)
            _write(store_folder, [named, first, kept, second, third])
            given = _select(store_folder)
            self.assertEqual(given.session_events, [{**kept, "ingested_at": INGESTED}])
            self.assertEqual(given.cancelled,
                             {events.event_key(second), events.event_key(named)})

    def test_purged_events_left_out(self) -> None:
        # a purge that lists the key blocks every copy of it
        with support.TemporaryFolder() as store_folder:
            inside = _event("2026-11-30T10:00:00.000Z", "uid-inside")
            purge = _purge("2026-11-25T08:00:00.000Z", "purge-uid-1",
                           [events.event_key(inside)])
            _write(store_folder, [purge, inside])
            given = _select(store_folder)
            self.assertEqual(given.session_events, [])
            self.assertEqual(given.retractions, [])

    def test_broken_lines_warn_and_are_recorded(self) -> None:
        # warning "broken_line", values segment and line; the events around it count
        with support.TemporaryFolder() as store_folder:
            inside = _event("2026-11-30T10:00:00.000Z", "uid-inside")
            _write_segment(store_folder, b"not an event\n" + _line(inside))
            given = _select(store_folder)
            self.assertEqual(given.broken, [BrokenLine(SEGMENT, 1)])
            self.assertIn({"code": "broken_line", "values": {"segment": SEGMENT, "line": 1}},
                          given.warnings)
            self.assertEqual(given.session_events, [{**inside, "ingested_at": INGESTED}])

    def test_held_back_session_warns(self) -> None:
        # "held_back_events": the selected sessions that this machine holds back, once
        # each; a held-back session outside the period gives no warning
        with support.TemporaryFolder() as store_folder:
            first = _event("2026-11-30T10:00:00.000Z", "uid-inside")
            second = _event("2026-11-30T11:00:00.000Z", "uid-inside-2")
            away = _event("2026-11-20T10:00:00.000Z", "uid-away", session_id=OTHER_SESSION)
            _write(store_folder, [first, away, second])
            given = _select(store_folder, held_back={(TOOL, SESSION), (TOOL, OTHER_SESSION)})
            held = [warning for warning in given.warnings
                    if warning["code"] == "held_back_events"]
            self.assertEqual(
                held, [{"code": "held_back_events", "values": {"session_id": SESSION}}])

    def test_newer_schema_warns(self) -> None:
        # "newer_schema_version"; newer is True (ADR 0023)
        with support.TemporaryFolder() as store_folder:
            inside = _event("2026-11-30T10:00:00.000Z", "uid-inside")
            ahead = _event("2026-11-30T11:00:00.000Z", "uid-ahead",
                           schema_version=2, kind="invented_kind")
            _write_segment(store_folder, _line(inside) + _line(ahead))
            given = _select(store_folder)
            self.assertTrue(given.newer)
            self.assertIn({"code": "newer_schema_version", "values": {}}, given.warnings)
            self.assertEqual(given.session_events, [{**inside, "ingested_at": INGESTED}])

    def test_lines_of_an_earlier_update_still_warn(self) -> None:
        # an ingestion updates the index, then select: broken_line and
        # newer_schema_version again, from the state of the index
        with support.TemporaryFolder() as store_folder:
            inside = _event("2026-11-30T10:00:00.000Z", "uid-inside")
            ahead = _event("2026-11-30T11:00:00.000Z", "uid-ahead",
                           schema_version=2, kind="invented_kind")
            _write_segment(store_folder, b"not an event\n" + _line(inside) + _line(ahead))
            index = LocalIndex(store_folder / "index.sqlite")
            index.update(store_folder)
            index.close()
            given = _select(store_folder)
            self.assertEqual(given.broken, [BrokenLine(SEGMENT, 1)])
            self.assertTrue(given.newer)
            self.assertIn({"code": "broken_line", "values": {"segment": SEGMENT, "line": 1}},
                          given.warnings)
            self.assertIn({"code": "newer_schema_version", "values": {}}, given.warnings)

    def test_empty_index_gives_same_selection(self) -> None:
        # a report with an empty index gives the same figures as one with an index that
        # an earlier update filled
        with support.TemporaryFolder() as store_folder:
            inside = _event("2026-11-30T10:00:00.000Z", "uid-inside")
            confirmation = _declared("2026-11-30T15:00:00.000Z", "confirm-uid-1",
                                     kind="timesheet_confirmation", day="2026-11-30", entries=[])
            entry = _entry("2026-11-29T20:00:00.000Z", "entry-uid-1",
                           "2026-11-29T20:00:00.000Z", "2026-11-30T02:00:00.000Z")
            _write(store_folder, [entry, confirmation, inside])
            warmed = LocalIndex(store_folder / "index.sqlite")
            warmed.update(store_folder)
            warm = select(warmed, store_folder, rome_days(), FIRST, FIRST, ReportParameters(),
                          set())
            warmed.close()
            fresh = LocalIndex(store_folder / "index.sqlite")
            cold = select(fresh, store_folder, rome_days(), FIRST, FIRST, ReportParameters(),
                          set())
            fresh.close()
            self.assertEqual(cold, warm)


def _retraction(timestamp: str, event_uid: str, target: events.Event) -> events.Event:
    """A retraction that names the key of the target."""
    return _declared(timestamp, event_uid, kind="retraction",
                     retracts=events.event_key(target).to_json())


class RetractionChainTests(unittest.TestCase):
    """A retraction is active when no active retraction names it, at every depth of a
    chain, and the cancelled set is the keys that the active retractions name
    (command-line.md › Commands, `retract`)."""

    def setUp(self) -> None:
        self.event = _declared("2026-11-30T09:00:00.000Z", "entry-uid")
        self.chain: list[events.Event] = []
        target = self.event
        for depth in range(1, 5):
            target = _retraction(f"2026-11-30T1{depth}:00:00.000Z", f"retract-uid-{depth}",
                                 target)
            self.chain.append(target)

    def keys(self, *held: events.Event) -> set[events.EventKey]:
        """The keys of the events."""
        return {events.event_key(event) for event in held}

    def test_depth_one(self) -> None:
        # R1 is active: E is cancelled
        self.assertEqual(cancelled(self.chain[:1]), self.keys(self.event))

    def test_depth_two(self) -> None:
        # R2 is active, R1 is not: E counts again
        self.assertEqual(cancelled(self.chain[:2]), self.keys(self.chain[0]))

    def test_depth_three(self) -> None:
        # R3 is active, R2 is not, so R1 is active again
        self.assertEqual(cancelled(self.chain[:3]), self.keys(self.chain[1], self.event))

    def test_depth_four(self) -> None:
        # R4 and R2 are active, R3 and R1 are not
        self.assertEqual(cancelled(self.chain[:4]), self.keys(self.chain[2], self.chain[0]))

    def test_order_of_the_list_does_not_count(self) -> None:
        # the chain of depth three, listed from the last retraction to the first
        self.assertEqual(cancelled(list(reversed(self.chain[:3]))),
                         self.keys(self.chain[1], self.event))

    def test_branch(self) -> None:
        # R1 and O retract E; R2 retracts R1 and P retracts O, so E counts again; R3
        # retracts R2, so R1 is active again and E is cancelled once more
        other = _retraction("2026-11-30T11:30:00.000Z", "retract-uid-other", self.event)
        undo = _retraction("2026-11-30T12:30:00.000Z", "retract-uid-undo", other)
        self.assertEqual(cancelled([self.chain[0], other]), self.keys(self.event))
        self.assertEqual(cancelled([*self.chain[:2], other]),
                         self.keys(self.chain[0], self.event))
        self.assertEqual(cancelled([*self.chain[:2], other, undo]),
                         self.keys(self.chain[0], other))
        self.assertEqual(cancelled([*self.chain[:3], other, undo]),
                         self.keys(self.chain[1], other, self.event))

    def test_self_naming_retraction_is_not_active(self) -> None:
        own = _declared("2026-11-30T15:00:00.000Z", "retract-uid-own", kind="retraction")
        own["retracts"] = events.event_key(own).to_json()
        self.assertEqual(cancelled([own]), set())
        self.assertEqual(cancelled([own, self.chain[0]]), self.keys(self.event))

    def test_loop_is_not_active(self) -> None:
        # A names B and B names A: neither is active, and a retraction outside the loop
        # that names A still cancels it
        one = _declared("2026-11-30T15:00:00.000Z", "retract-uid-a", kind="retraction")
        two = _retraction("2026-11-30T16:00:00.000Z", "retract-uid-b", one)
        one["retracts"] = events.event_key(two).to_json()
        self.assertEqual(cancelled([one, two]), set())
        outside = _retraction("2026-11-30T17:00:00.000Z", "retract-uid-c", one)
        self.assertEqual(cancelled([one, two, outside]), self.keys(one))


if __name__ == "__main__":
    unittest.main()
