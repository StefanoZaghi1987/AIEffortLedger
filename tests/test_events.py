"""Tests of the event values, the line encoding, the keys, and the events a command writes."""

import json
import unittest
import uuid
from typing import Any

from ai_effort_ledger import events

import support


def sample_event(**overrides: Any) -> events.Event:
    """A complete event of schema version 1, of kind `prompt`, with the given fields replaced."""
    event: events.Event = {
        "schema_version": 1,
        "source": "claude-code-jsonl",
        "event_uid": "prompt:2026-11-19T08:30:00.125Z:0",
        "timestamp": "2026-11-19T08:30:00.125Z",
        "ingested_at": "2026-11-19T08:30:01.000Z",
        "writer_version": "0.1.0.dev0",
        "actor": "human",
        "kind": "prompt",
        "machine": "0d5b3f52-9d8a-4c1e-b6e7-2a4f8e1d3c90",
    }
    event.update(overrides)
    return event


class TestEvents(unittest.TestCase):
    """The values, the encoding, the keys, and the events that a command writes act as the schema
    says."""

    def test_instant_reads_back_equal(self) -> None:
        self.assertEqual(events.format_instant(support.utc("2026-11-19T08:30:00.125")),
                         "2026-11-19T08:30:00.125Z")
        self.assertEqual(events.parse_instant("2026-11-19T09:30:00.125+01:00"),
                         support.utc("2026-11-19T08:30:00.125"))

    def test_version_order(self) -> None:
        k = events.version_key
        self.assertLess(k("1.9.0"), k("1.10.0"))
        self.assertLess(k("1.3.0.dev0"), k("1.3.0"))
        self.assertLess(k("1.3.0.dev0"), k("1.3.0.dev1"))
        with self.assertRaises(ValueError):
            k("v1.3")

    def test_encode_is_one_sorted_line(self) -> None:
        event = {
            "note": "deux lignes\net un à", "kind": "prompt", "actor": "human", "machine": "m-1"}
        data = events.encode_event(event)
        parsed = json.loads(data)
        self.assertTrue(data.endswith(b"\n"))
        self.assertEqual(data.count(b"\n"), 1)
        self.assertTrue(data.rstrip(b"\n").endswith(b"}"))
        self.assertEqual(list(parsed), sorted(parsed))
        self.assertNotIn(b": ", data)
        self.assertNotIn(b", ", data)
        self.assertNotIn(b"\\u", data)
        self.assertIn(b"\\n", data)
        self.assertIn("et un à".encode("utf-8"), data)

    def test_encode_refuses_null(self) -> None:
        with self.assertRaises(ValueError):
            events.encode_event({"model": None})

    def test_decode_event(self) -> None:
        event = sample_event()
        decoded = events.decode_line(events.encode_event(event))
        self.assertEqual(decoded.state, "event")
        self.assertFalse(decoded.newer)
        self.assertEqual(decoded.event, event)

    def test_decode_not_json_is_broken(self) -> None:
        decoded = events.decode_line(b"{this is not json}")
        self.assertEqual(decoded.state, "broken")
        self.assertIsNone(decoded.event)
        self.assertFalse(decoded.newer)

    def test_decode_missing_required_field_is_broken(self) -> None:
        event = sample_event()
        del event["machine"]
        decoded = events.decode_line(events.encode_event(event))
        self.assertEqual(decoded.state, "broken")
        self.assertIsNone(decoded.event)
        self.assertFalse(decoded.newer)

    def test_decode_unknown_kind_of_schema_1_is_broken(self) -> None:
        decoded = events.decode_line(events.encode_event(sample_event(kind="daydream")))
        self.assertEqual(decoded.state, "broken")
        self.assertIsNone(decoded.event)
        self.assertFalse(decoded.newer)

    def test_newer_unknown_kind_is_left_out(self) -> None:
        decoded = events.decode_line(
            events.encode_event(sample_event(schema_version=2, kind="future")))
        self.assertEqual(decoded.state, "left_out")
        self.assertTrue(decoded.newer)
        self.assertIsNone(decoded.event)

    def test_newer_unknown_fixed_value_is_left_out(self) -> None:
        decoded = events.decode_line(
            events.encode_event(sample_event(schema_version=2, tool_category="paint")))
        self.assertEqual(decoded.state, "left_out")
        self.assertTrue(decoded.newer)
        self.assertIsNone(decoded.event)

    def test_newer_unknown_field_is_dropped(self) -> None:
        decoded = events.decode_line(events.encode_event(sample_event(schema_version=2, x=5)))
        self.assertEqual(decoded.state, "event")
        self.assertTrue(decoded.newer)
        self.assertNotIn("x", decoded.event)
        self.assertEqual(decoded.event, sample_event(schema_version=2))

    def test_open_sets_pass_through(self) -> None:
        event = sample_event(
            kind="agent_output",
            actor="agent",
            tokens={"input": 10, "reasoning_output": 5},
            requests={"web_search": 2},
            price_factors={"speed": "fast", "service_tier": "standard"},
        )
        decoded = events.decode_line(events.encode_event(event))
        self.assertEqual(decoded.state, "event")
        self.assertFalse(decoded.newer)
        self.assertEqual(decoded.event["tokens"], {"input": 10, "reasoning_output": 5})
        self.assertEqual(decoded.event["requests"], {"web_search": 2})
        self.assertEqual(
            decoded.event["price_factors"], {"speed": "fast", "service_tier": "standard"})

    def test_decode_whole_number_writer_version_is_broken(self) -> None:
        """A line that holds the `writer_version` the table of the encoding names in
        another shape is not an event of any schema version, whatever its schema version,
        because a new schema version never changes the encoding of a field: the line is
        broken, out of every figure, and the warning names its segment and its line
        (`event-schema.md` › Encoding; `ingestion.md` › Store)."""
        decoded = events.decode_line(events.encode_event(sample_event(writer_version=1)))
        self.assertEqual(decoded.state, "broken")
        self.assertIsNone(decoded.event)

    def _broken_of(self, **overrides: Any) -> None:
        """The line of the sample event with the field replaced is broken, without an
        event."""
        decoded = events.decode_line(events.encode_event(sample_event(**overrides)))
        self.assertEqual(decoded.state, "broken", overrides)
        self.assertIsNone(decoded.event)

    def test_decode_validates_every_field_the_encoding_table_owns(self) -> None:
        """Each typed column of the table of the encoding is read as the table gives it:
        a version text is whole numbers separated by dots as text, an instant is an RFC
        3339 text in UTC with `Z` and milliseconds, a day is a local date, a count is a
        whole number, a key is an object that names its identity, and the other fields
        take the shapes the table gives them (`event-schema.md` › Encoding)."""
        self._broken_of(corrected_version="1.0.o")
        self._broken_of(timestamp="2026-11-19T08:30:00Z")
        self._broken_of(timestamp="2026-11-19 08:30:00.000Z")
        self._broken_of(ingested_at=1)
        self._broken_of(ingested_at="2026-11-19T09:30:00.000+01:00")
        self._broken_of(ingested_at="2026-13-19T08:30:00.000Z")
        self._broken_of(start="2026-11-19T08:30:00.000Z ")
        self._broken_of(end="not an instant")
        self._broken_of(day="2026-2-3")
        self._broken_of(duration="900")
        self._broken_of(kind="agent_output", actor="agent", tokens={"input": "10"})
        self._broken_of(kind="agent_output", actor="agent", requests={"web_search": 0})
        self._broken_of(kind="agent_output", actor="agent", price_factors={"speed": 2})
        self._broken_of(cost=12.5)
        self._broken_of(currency="euro")
        self._broken_of(forked_from={"session_id": "s-1"})
        self._broken_of(forked_from={"session_id": "s-1", "instant": "yesterday"})
        self._broken_of(kind="retraction", retracts={"source": "ledger"})
        self._broken_of(kind="retraction", retracts="u-1")
        self._broken_of(kind="timesheet_confirmation", day="2026-11-19",
                        replaces={"source": "ledger", "session_id": "s-1"})
        self._broken_of(kind="purge", purge_reason="content", purged_keys=["u-1"])
        self._broken_of(kind="purge", purge_reason="content",
                        purged_keys=[{"source": "ledger", "note": "u-1"}])
        self._broken_of(kind="timesheet_confirmation", day="2026-11-19",
                        entries=[{"project": "alpha", "duration": "900"}])
        self._broken_of(kind="purge", purge_reason="content", purged_sessions=["s-1"])
        self._broken_of(kind="annotation", annotates="session-1")
        self._broken_of(machine=7)
        self._broken_of(repo_hint=7)
        self._broken_of(labels={"team": 1})

    def test_decode_holds_an_event_whole_in_every_typed_column(self) -> None:
        """An event whose typed columns all hold the shapes the table gives them decodes
        as an event, and the reading keeps every field (`event-schema.md` › Encoding)."""
        event = sample_event(
            kind="agent_output", actor="agent",
            tokens={"input": 10}, requests={"web_search": 2},
            price_factors={"speed": "fast"}, duration=900,
            start="2026-11-19T08:00:00.000Z", end="2026-11-19T09:00:00.000Z",
            day="2026-11-19", cost="12.50", currency="EUR",
            forked_from={"session_id": "s-9", "instant": "2026-11-19T08:00:00.000Z"},
            retracts={"source": "ledger", "event_uid": "u-1"},
            replaces={"source": "ledger", "event_uid": "u-2"},
            purged_keys=[{"source": "claude-code-jsonl", "native_id": "n-1"},
                         {"source": "ledger", "event_uid": "u-3"}],
            entries=[{"project": "alpha", "duration": 900}],
            purged_sessions=[{"tool": "claude-code", "session_id": "s-1"}],
            annotates={"tool": "claude-code", "session_id": "s-1"},
            repo_hint="example.org/team/app", labels={"team": "invented"},
            corrected_version="1.2.3")
        decoded = events.decode_line(events.encode_event(event))
        self.assertEqual(decoded.state, "event")
        self.assertFalse(decoded.newer)
        self.assertEqual(decoded.event, event)

    def test_newer_line_of_an_unknown_kind_stays_left_out(self) -> None:
        """A line of a newer schema version that holds a kind this schema does not know is
        left out, not broken, even when a typed column of the table is in another shape
        too: the unknown kind decides first (`event-schema.md` › Encoding)."""
        decoded = events.decode_line(
            events.encode_event(sample_event(schema_version=2, kind="daydream",
                                             writer_version=1)))
        self.assertEqual(decoded.state, "left_out")
        self.assertTrue(decoded.newer)
        self.assertIsNone(decoded.event)

    def test_key_with_native_identifier(self) -> None:
        event = sample_event(native_id="m1", session_id="s-1", event_uid="u-1")
        self.assertEqual(events.event_key(event), events.EventKey("claude-code-jsonl", "m1"))

    def test_key_without_native_identifier(self) -> None:
        event = sample_event(session_id="s-1", event_uid="u-1")
        self.assertEqual(
            events.event_key(event),
            events.EventKey("claude-code-jsonl", session_id="s-1", event_uid="u-1"))

    def test_key_without_session_identifier(self) -> None:
        """The key of an event that holds neither a native identifier nor a session
        identifier, as the mapping of a record whose `sessionId` is absent gives: the key
        is the source and the event identifier, with the session part absent — the absent
        part of a key stays absent, as the key order reads it (`event-schema.md` › Keys
        and invariants)."""
        event = sample_event(event_uid="u-1")
        self.assertEqual(
            events.event_key(event),
            events.EventKey("claude-code-jsonl", session_id=None, event_uid="u-1"))

    def test_key_of_a_ledger_event(self) -> None:
        event = sample_event(source="ledger", event_uid="5e8f2c1a-9b4d-4e3a-8c7d-1f2e3a4b5c6d")
        self.assertEqual(
            events.event_key(event),
            events.EventKey("ledger", event_uid="5e8f2c1a-9b4d-4e3a-8c7d-1f2e3a4b5c6d"))

    def test_key_json_forms(self) -> None:
        self.assertEqual(events.EventKey("ledger", None, None, "u").to_json(),
                         {"source": "ledger", "event_uid": "u"})
        self.assertEqual(events.EventKey("claude-code-jsonl", "m1").to_json(),
                         {"source": "claude-code-jsonl", "native_id": "m1"})
        self.assertEqual(
            events.EventKey("claude-code-jsonl", session_id="s-1", event_uid="u-1").to_json(),
            {"source": "claude-code-jsonl", "session_id": "s-1", "event_uid": "u-1"})

    def test_key_from_json_reads_back_equal(self) -> None:
        keys = [
            events.EventKey("claude-code-jsonl", native_id="m1"),
            events.EventKey("claude-code-jsonl", session_id="s-1", event_uid="u-1"),
            events.EventKey("ledger", event_uid="u-2"),
        ]
        for key in keys:
            self.assertEqual(events.EventKey.from_json(key.to_json()), key)

    def test_absent_part_sorts_first(self) -> None:
        absent = sample_event(event_uid="u-1")
        given = sample_event(session_id="a", event_uid="u-2")
        self.assertLess(events.event_order(absent), events.event_order(given))
        self.assertLess(
            events.event_order(given),
            events.event_order(sample_event(session_id="b", event_uid="u-3")))

    def test_earliest_ingested_at_wins(self) -> None:
        early = (sample_event(ingested_at="2026-11-19T08:30:01.000Z"), "segments/a/2026-11.jsonl")
        late = (sample_event(ingested_at="2026-11-19T09:30:01.000Z"), "segments/b/2026-11.jsonl")
        self.assertEqual(events.winning_copy(early, late), early)
        self.assertEqual(events.winning_copy(late, early), early)

    def test_equal_instants_resolve_by_segment_name(self) -> None:
        same = "2026-11-19T08:30:01.000Z"
        first = (sample_event(ingested_at=same), "segments/a/2026-11.jsonl")
        second = (sample_event(ingested_at=same, event_uid="u-9"), "segments/b/2026-11.jsonl")
        self.assertEqual(events.winning_copy(first, second), first)
        self.assertEqual(events.winning_copy(second, first), first)

    def test_ledger_event_fields(self) -> None:
        moment = support.utc("2026-11-19T08:30:00.125")
        event = events.ledger_event(
            "timesheet_confirmation", "human", "0d5b3f52-9d8a-4c1e-b6e7-2a4f8e1d3c90", moment,
            {"day": "2026-11-19", "entries": [{"project": "p-1", "duration": 3600}]})
        self.assertEqual(event["schema_version"], 1)
        self.assertEqual(event["source"], "ledger")
        self.assertEqual(event["actor"], "human")
        self.assertEqual(event["kind"], "timesheet_confirmation")
        self.assertEqual(event["machine"], "0d5b3f52-9d8a-4c1e-b6e7-2a4f8e1d3c90")
        self.assertEqual(event["timestamp"], "2026-11-19T08:30:00.125Z")
        self.assertEqual(event["writer_version"], events.writer_version())
        self.assertNotIn("ingested_at", event)
        self.assertEqual(uuid.UUID(event["event_uid"]).version, 4)
        self.assertEqual(event["day"], "2026-11-19")
        self.assertEqual(event["entries"], [{"project": "p-1", "duration": 3600}])
        fixed = events.ledger_event(
            "annotation", "human", "m-1", moment, {"labels": {}},
            new_uid=lambda: "fixed-uid", version="5.0.0")
        self.assertEqual(fixed["event_uid"], "fixed-uid")
        self.assertEqual(fixed["writer_version"], "5.0.0")
