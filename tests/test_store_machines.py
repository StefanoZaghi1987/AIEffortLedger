"""Store tests with two machines: two store folders act as two machines, each set up by
`support.world`, and `support.copy_segments` acts as a file-sync service with a delay
between them; one test gives its two machines one store folder, as a synced folder would
(architecture.md › Tests › Store tests). The file proves that:

- a last line without a line break, still carried by the service, is ignored on the other
  machine without a warning, and that machine leaves it where it is (architecture.md ›
  Concurrency, ingestion.md › Store);
- a broken line stays out of every figure, is named with its segment and its number from 1,
  and gives every command that computes figures the exit code 3, and `ingest`, which
  computes none, the exit code 0 (ingestion.md › Store, command-line.md › Exit codes);
- a purge without a corrected version keeps its key out on both machines for good: the
  store reads no copy of it, each machine removes its own copy at its next ingestion, and
  no ingestion brings a copy back (ADR 0008, ingestion.md › Store);
- a purge with a corrected version blocks the copies under it only: the corrected copy of
  the other machine replaces the blocked one (ADR 0015);
- of two timesheet confirmations of one day from two machines, the latest by `timestamp`
  declares the day and the other warns `confirmation_not_seen`, with the exit code 0; a
  confirmation that names the earlier one, as a copy lets it, warns nothing
  (metrics.md › Declared values, ADR 0014, command-line.md › Exit codes);
- only the machine that wrote a frozen report removes it (command-line.md › Frozen
  reports);
- an output that names a machine to a person shows its machine label when the store holds
  one, and its identifier otherwise, while the documents keep the identifier
  (command-line.md › JSON documents, › Exit codes);
- store metadata that the ledger cannot read shows the identifier and gives one warning for
  the file in each command, and none in the stop error of `frozen remove`
  (command-line.md › JSON documents, › Exit codes).

Every store is built by the real command `ingest` from native logs written by hand with
invented text, in a working folder with its repository, settled; every command runs
through `main`, and a test asserts an exit code, the lines of the standard error, and a
document. The two machines of a test share one maker of identifiers, so that the events
they write never share an event key.

The person of every store is the one that the world creates — the time zone `Etc/UTC`,
the day start 00:00, the settle time and the report parameters at their defaults, no
project and no rule — so the project of the session is the repository identity of its
repository, `example.com/machines/product`, shown as `product`. The day of the tests is
`2026-11-23`; the instant of a world is `2026-11-24T12:00` UTC unless a test gives a
later one. The session of the tests holds one prompt of the person at 09:00 and one answer
of the model at 09:05, in the interactive invocation: the prompt is the one human signal
and counts the minimum attention time, the 60 seconds from 08:59 to 09:00, and the turn
from the prompt to the answer gives 300 seconds of agent time (metrics.md › Human time,
› Agent time).
"""

import json
import unittest
from collections.abc import Sequence
from datetime import date, timedelta
from pathlib import Path

import support
from ai_effort_ledger.events import Event, EventKey, event_key

DAY = date(2026, 11, 23)
"""The local day of the session of the tests, and the day that every report reports."""
DAY_TEXT = DAY.isoformat()
MACHINE_A = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
MACHINE_B = "7f6e5d4c-3b2a-4c1d-8e9f-0a1b2c3d4e5f"
"""The machine identifiers of the two machines of the tests, invented; each writes its own
segment."""
SOURCE = "claude-code-jsonl"
"""The source of every event that the adapter of the tests writes."""
SESSION = "session-product"
"""The identifier of the session of the tests."""
REPOSITORY = "https://Example.com/Machines/Product.git"
"""The remote of the repository in which the session works: each machine holds a clone of
the same repository."""
PROJECT = "example.com/machines/product"
"""The repository identity of the repository, and so the project of the session of the
tests (ADR 0009)."""
UUID_PROMPT = "5e1d0000-0000-4000-8000-0000000000b1"
UUID_ANSWER = "5e1d0000-0000-4000-8000-0000000000b2"
UUID_LATER = "5e1d0000-0000-4000-8000-0000000000b3"
"""The native identifiers of the records of the session of the tests, invented."""
ANSWER_ID = "msg-store-machines-answer"
"""The native identifier of the answer: the identifier of its message."""
PROMPT_AT = "2026-11-23T09:00:00.000Z"
ANSWER_AT = "2026-11-23T09:05:00.000Z"
LATER_PROMPT_AT = "2026-11-23T11:00:00.000Z"
SEGMENT_A = f"segments/{MACHINE_A}/2026-11.jsonl"
SEGMENT_B = f"segments/{MACHINE_B}/2026-11.jsonl"
"""The segments of the two machines for the month of the instant of the tests."""
ANSWER_KEY = EventKey(SOURCE, native_id=ANSWER_ID)
"""The event key of the answer of the session of the tests."""
ANSWER_JSON = json.dumps(ANSWER_KEY.to_json())
"""The key of the answer as the `--key` of `purge` takes it: its JSON object."""
LATER = support.FIXTURE_NOW + timedelta(hours=1)
"""The instant of the commands of machine B in the tests of the confirmations: an hour
after the instant of machine A, so that a confirmation of B is the later one."""
NOTE = "Invented note of the frozen report."
"""The note that the frozen report of the tests carries."""
LABEL = "Invented office desk"
"""The machine label that machine A gives itself in the test of the labels."""
PERIOD = ("report", "timesheet", "--from", DAY_TEXT, "--to", DAY_TEXT)
DAY_REPORT = ("report", "day", DAY_TEXT)
TIMESHEET = ("timesheet", DAY_TEXT)
"""The words of the three commands that report the day of the tests."""


def _prompt(instant: str, uuid_value: str = UUID_PROMPT) -> dict:
    """A prompt of the person, typed in the interactive invocation; the text is invented."""
    return {**support.prompt_record("Invented prompt of the store tests.", instant,
                                    uuid_value), "entrypoint": "cli"}


def _answer(instant: str = ANSWER_AT) -> dict:
    """One answer of the model to the prompt of the person; the text is invented."""
    return support.output_record("Invented answer of the store tests.", instant,
                                 UUID_ANSWER, ANSWER_ID)


MEASURED = [_prompt(PROMPT_AT), _answer()]
"""The records of the session of the tests: one prompt at 09:00 and one answer at 09:05."""


def _day_figures(day: dict) -> tuple:
    """The figures of one day of the document of `report timesheet` that a test recomputes
    by hand: its state, its total, its measured total, and, for each entry, its project,
    its measured human time, and its measured human time with manual entries."""
    return (day["state"], day["total"], day["measured_total"],
            [(entry["project"], entry["measured"], entry["with_manual_entries"])
             for entry in day["entries"]])


def _keys(store: Path) -> set[EventKey]:
    """The event keys of the copies that the segments of the store hold."""
    return {event_key(event) for event, _ in support.stored_events(store)}


def _copies(store: Path, key: EventKey) -> list[tuple[Event, str]]:
    """The copies of the event key that the segments of the store hold, as the bytes of
    the segments hold them whatever a purge does to them: each with the name of its
    segment."""
    return [(event, name) for event, name in support.stored_events(store)
            if event_key(event) == key]


def _written_by(store: Path, key: EventKey) -> list[tuple[str, str, str]]:
    """The copies of the event key that the segments of the store hold, each as the writer
    version, the machine, and the segment of the copy."""
    return [(event["writer_version"], event["machine"], name)
            for event, name in _copies(store, key)]


class StoreTests(unittest.TestCase):
    """The store of two machines and of the file-sync service between them: what each
    machine reads, counts, warns about, and removes, command by command."""

    def _json(self, world: support.World, *words: str) -> tuple[int, dict, str]:
        """Run the command with `--json` on the machine: its exit code, its document, and
        its standard error."""
        code, shown, error = support.run_main(world.context, *words, "--json")
        return code, json.loads(shown), error

    def _ingest(self, world: support.World, records: Sequence[dict] | None = None) -> None:
        """Run `ingest` on the machine. With `records`, the session of the tests is written
        first into the folder of native logs of the machine, in its working folder with its
        repository, and settled. The command completes with the exit code 0 and writes no
        line of warning or error."""
        if records is not None:
            work = support.remote_repository(world.home / "work", REPOSITORY)
            support.write_session(world.logs[0], SESSION, records, {}, work)
            support.settle(world.logs)
        code, _, error = support.run_main(world.context, "ingest")
        self.assertEqual((code, error), (0, ""), f"ingest on the machine {world.machine}")

    def _days(self, world: support.World) -> list[dict]:
        """The days of the document of `report timesheet` over the day of the tests, on the
        machine: the command completes with the exit code 0 and writes no warning and no
        configuration error, on the standard error or in the document."""
        code, document, error = self._json(world, *PERIOD)
        self.assertEqual((code, error), (0, ""), world.machine)
        self.assertEqual((document["warnings"], document["configuration_errors"]),
                         ([], []), world.machine)
        return document["days"]

    def _assert_measured(self, world: support.World, human_time: int,
                         agent_time: int) -> None:
        """Assert that `report day` of the day on the machine completes with the exit code
        0, writes no line on the standard error, and counts, in whole seconds, the human
        time and the agent time given, and no blocked time."""
        code, document, error = self._json(world, *DAY_REPORT)
        self.assertEqual((code, error), (0, ""), world.machine)
        person = document["person"]
        self.assertEqual((person["human_time"], person["agent_time"], person["blocked_time"]),
                         (human_time, agent_time, 0), world.machine)

    def test_half_written_last_line_on_other_machine_is_ignored(self) -> None:
        """A last line without a line break is a line that a machine or a file-sync service
        is still writing: the other machine ignores it, without a warning, and leaves it
        where it is (architecture.md › Concurrency, ingestion.md › Store).

        Machine A ingests the session, then writes one manual entry of half an hour of
        unattributed time in mode `additional`, at 10:00: its human time grows from 60 to
        1860 seconds. The service delivers the segment of A stopped before its last line
        break, so the entry is the line still carried: the figures of B are those that A
        gave before the entry, and the `ingest` of B completes, warns nothing, and changes
        neither the figures nor the file. The service completes the line: B gives the figures
        of A. The two machines are compared on their figures, never on their report
        records, which name the files that each machine read."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids)
            b = support.world(base / "b", MACHINE_B, new_uid=uids)
            self._ingest(a, MEASURED)
            before = self._days(a)
            code, _, error = support.run_main(
                a.context, "entry", "add", "--from", "2026-11-23T10:00", "--to",
                "2026-11-23T10:30", "--mode", "additional", "--json")
            self.assertEqual((code, error), (0, ""))
            after = self._days(a)
            support.copy_segments(a, b, cut_last_line=True)
            copied = b.store / SEGMENT_A
            self.assertFalse(copied.read_bytes().endswith(b"\n"))
            held = copied.read_bytes()
            self.assertEqual(self._days(b), before)
            code, document, error = self._json(b, *PERIOD)
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(document["record"]["broken_lines"], [])
            self._ingest(b)
            self.assertEqual(copied.read_bytes(), held)
            self.assertFalse(copied.read_bytes().endswith(b"\n"))
            self.assertEqual(self._days(b), before)
            support.copy_segments(a, b, cut_last_line=False)
            self.assertEqual(self._days(b), after)
            code, document, error = self._json(b, *PERIOD)
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(document["record"]["broken_lines"], [])
        project = {"id": PROJECT, "name": "product"}
        self.assertEqual(_day_figures(before[0]),
                         ("measured_day", 60, 60, [(project, 60, 60)]))
        self.assertEqual(_day_figures(after[0]),
                         ("measured_day", 1860, 60, [(project, 60, 60), (None, 0, 1800)]))

    def test_broken_line_warns_with_segment_and_number(self) -> None:
        """A line of a segment that is not a valid event is a broken line: every report
        leaves it out and names it with its segment and its number from 1, and the report
        completes with the exit code 3; an `ingest` computes no figure, so it completes
        with the exit code 0, and it touches no segment of another machine (ingestion.md ›
        Store, command-line.md › Exit codes).

        The session of A holds a message that the person typed while the agent worked, at
        09:02: A counts 180 seconds of human time, the minimum attention before the prompt
        and the signal gap of two minutes up to the message. The file-sync service delivers
        the segment of A to B, where the second of its three lines, the message, loses its
        second half and keeps its line break: B counts the prompt and the answer alone, 60
        seconds of human time and 300 of agent time, and its report names the line 2 of the
        segment of A, before and after its `ingest`. The same report on A completes with the
        exit code 0: the damage is on the copy of B."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids)
            b = support.world(base / "b", MACHINE_B, new_uid=uids)
            self._ingest(a, [_prompt(PROMPT_AT),
                             support.queue_record(
                                 "Invented message typed while the agent worked.",
                                 "2026-11-23T09:02:00.000Z"),
                             _answer()])
            support.copy_segments(a, b, cut_last_line=False)
            copied = b.store / SEGMENT_A
            lines = copied.read_bytes().splitlines(keepends=True)
            self.assertEqual(len(lines), 3)
            held = lines[1].rstrip(b"\n")
            lines[1] = held[:len(held) // 2] + b"\n"
            damaged = b"".join(lines)
            copied.write_bytes(damaged)
            self._assert_broken_copy(b)
            code, _, error = support.run_main(b.context, "ingest")
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(copied.read_bytes(), damaged)
            self._assert_broken_copy(b)
            code, document, error = self._json(a, *DAY_REPORT)
            self.assertEqual((code, document["warnings"], error), (0, [], ""))
            self.assertEqual(document["record"]["broken_lines"], [])
            self.assertEqual(document["person"], {
                "human_time": 180, "agent_time": 300, "parallel_ratio": 1.0,
                "blocked_time": 0,
                "activity_classes": {"person_only": 60, "supervised": 120,
                                     "unattended": 180, "blocked": 0, "idle": 86040}})

    def _assert_broken_copy(self, world: support.World) -> None:
        """Assert what the report of the day gives on a machine whose store holds the
        damaged copy of the segment of A: in both modes the exit code 3 and one line of
        warning on the standard error, which names the line 2 and the segment; in the
        document one warning `broken_line` with the segment and the line, the broken line
        in the record, and the figures of the prompt and of the answer alone."""
        named = f"line 2 of the segment {SEGMENT_A}"
        broken = {"segment": SEGMENT_A, "line": 2}
        code, document, error = self._json(world, *DAY_REPORT)
        self.assertEqual(code, 3, world.machine)
        self.assertEqual([(warning["code"], warning["values"])
                          for warning in document["warnings"]],
                         [("broken_line", broken)], world.machine)
        self.assertIn(named, document["warnings"][0]["message"])
        self.assertEqual(document["record"]["broken_lines"], [broken])
        self.assertEqual(document["person"], {
            "human_time": 60, "agent_time": 300, "parallel_ratio": 1.0, "blocked_time": 0,
            "activity_classes": {"person_only": 60, "supervised": 0, "unattended": 300,
                                 "blocked": 0, "idle": 86040}})
        code, _, error = support.run_main(world.context, *DAY_REPORT)
        self.assertEqual(code, 3, world.machine)
        [line] = error.splitlines()
        self.assertTrue(line.startswith("warning: "), line)
        self.assertIn(named, line)

    def test_purge_without_corrected_version_keeps_key_out_on_both(self) -> None:
        """A purge without a corrected version blocks every copy of its keys for good: the
        machine that writes it removes its own copies at once, every read leaves the copies
        of the other machines out, each other machine removes its own copies at its next
        ingestion, and no ingestion brings a copy back (ADR 0008, ingestion.md › Store).

        The person took the session to machine B before the purge: each machine ingested it
        into a segment of its own, and the file-sync service copied both stores both ways,
        so that each store holds two copies of the answer, one in the segment of each
        machine. A purges the key of the answer with the reason `forget`: its own copy
        leaves its segment, and its report counts no agent time. The service carries the
        purge to B, whose own copy is still in its segment but out of its report; the
        `ingest` of B removes that copy, and the next one, after the session went on, brings
        none back. Once the service carries the segment of B to A, neither store holds a
        copy of the key, and both machines count the day without the answer."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids)
            b = support.world(base / "b", MACHINE_B, new_uid=uids)
            self._ingest(a, MEASURED)
            self._ingest(b, MEASURED)
            self.assertEqual({name for _, name in support.stored_events(a.store)},
                             {SEGMENT_A})
            self.assertEqual({name for _, name in support.stored_events(b.store)},
                             {SEGMENT_B})
            self.assertEqual(_keys(a.store), _keys(b.store))
            support.copy_segments(a, b, cut_last_line=False)
            support.copy_segments(b, a, cut_last_line=False)
            for machine in (a, b):
                self.assertEqual(len(_copies(machine.store, ANSWER_KEY)), 2)
                self._assert_measured(machine, 60, 300)
            code, document, error = self._json(a, "purge", "--key", ANSWER_JSON,
                                               "--reason", "forget", "--yes")
            self.assertEqual((code, error), (0, ""))
            self.assertEqual((document["keys"], document["written"]),
                             ([ANSWER_KEY.to_json()], True))
            self.assertEqual([name for _, name in _copies(a.store, ANSWER_KEY)], [SEGMENT_B])
            self._assert_measured(a, 60, 0)
            support.copy_segments(a, b, cut_last_line=False)
            self.assertEqual([name for _, name in _copies(b.store, ANSWER_KEY)], [SEGMENT_B])
            self._assert_measured(b, 60, 0)
            self._ingest(b)
            self.assertEqual(_copies(b.store, ANSWER_KEY), [])
            self._assert_measured(b, 60, 0)
            self._ingest(b, [*MEASURED, _prompt(LATER_PROMPT_AT, UUID_LATER)])
            self.assertEqual(_copies(b.store, ANSWER_KEY), [])
            self._assert_measured(b, 120, 0)
            # the segment of B as A copied it before the purge still holds the old copy
            self.assertEqual([name for _, name in _copies(a.store, ANSWER_KEY)], [SEGMENT_B])
            support.copy_segments(b, a, cut_last_line=False)
            self.assertEqual(_copies(a.store, ANSWER_KEY), [])
            self._assert_measured(a, 120, 0)
            self._assert_measured(b, 120, 0)

    def test_corrected_copy_replaces_blocked_earlier_copy(self) -> None:
        """A purge with a corrected version blocks only the copies of its keys whose
        writer version is under the corrected version: a copy that the corrected version
        or a newer one writes replaces them, and a copy of an earlier version comes back
        by no way, not even when its machine reads the session again (ADR 0015,
        ingestion.md › Store).

        Machine A runs the version `0.1.0` and stores the answer of the session; a purge on
        A names the corrected version `0.1.1`, so its own copy leaves its segment and its
        report counts no agent time. The file-sync service carries the segment of A to
        machine B, which runs `0.1.1`; its native logs hold the corrected session, the same
        record of the answer at 09:06, and its `ingest` stores the corrected answer: its
        report counts 360 seconds of agent time, the turn up to 09:06. The service carries
        the segment of B to A, whose report counts the same; each store holds exactly one
        copy of the key, the one of B. The `ingest` of A at `0.1.0`, after its session went
        on and it reads the session again, brings its own copy back by no way."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids, version="0.1.0")
            b = support.world(base / "b", MACHINE_B, new_uid=uids, version="0.1.1")
            self._ingest(a, MEASURED)
            self.assertEqual(_written_by(a.store, ANSWER_KEY),
                             [("0.1.0", MACHINE_A, SEGMENT_A)])
            self._assert_measured(a, 60, 300)
            code, document, error = self._json(
                a, "purge", "--key", ANSWER_JSON, "--reason", "correction",
                "--corrected-version", "0.1.1", "--yes")
            self.assertEqual((code, error), (0, ""))
            self.assertEqual((document["keys"], document["written"]),
                             ([ANSWER_KEY.to_json()], True))
            [purge] = [event for event, _ in support.stored_events(a.store)
                       if event["kind"] == "purge"]
            self.assertEqual((purge["corrected_version"], purge["purged_keys"],
                              purge["purged_sessions"]),
                             ("0.1.1", [ANSWER_KEY.to_json()],
                              [{"tool": "claude-code", "session_id": SESSION}]))
            self.assertEqual(_copies(a.store, ANSWER_KEY), [])
            self._assert_measured(a, 60, 0)
            support.copy_segments(a, b, cut_last_line=False)
            self._assert_measured(b, 60, 0)
            self._ingest(b, [_prompt(PROMPT_AT), _answer("2026-11-23T09:06:00.000Z")])
            corrected = ("0.1.1", MACHINE_B, SEGMENT_B)
            self.assertEqual(_written_by(b.store, ANSWER_KEY), [corrected])
            self._assert_measured(b, 60, 360)
            support.copy_segments(b, a, cut_last_line=False)
            self.assertEqual(_written_by(a.store, ANSWER_KEY), [corrected])
            self._assert_measured(a, 60, 360)
            self._ingest(a, [*MEASURED, _prompt(LATER_PROMPT_AT, UUID_LATER)])
            self.assertEqual(_written_by(a.store, ANSWER_KEY), [corrected])
            self._assert_measured(a, 120, 360)

    def test_confirmations_of_one_day_from_two_machines(self) -> None:
        """Two timesheet confirmations of one day from two machines that saw none of the
        other are two declarations of the day: the latest by `timestamp` gives the
        timesheet entries, the other warns `confirmation_not_seen` with its event
        identifier, and the warning keeps the exit code 0 (metrics.md › Declared values,
        ADR 0014, command-line.md › Exit codes).

        Both machines hold the measured day: A ingests the session, and the file-sync
        service copies its segment to B. A confirms the proposal at its instant, 900 seconds
        for the project. B confirms the day an hour later, before the service carries the
        confirmation of A to it, so its confirmation names none in `replaces`, and with
        another value, 7200 seconds through `--set`. The service copies both stores both
        ways: on A and on B, `report day` and `timesheet` complete with the exit code 0, the
        day is declared with the entry of B, and one warning, on the standard error and in
        the document, names the confirmation of A. Neither names the confirmation of B."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids)
            b = support.world(base / "b", MACHINE_B, new_uid=uids, now=LATER)
            self._ingest(a, MEASURED)
            support.copy_segments(a, b, cut_last_line=False)
            code, document, error = self._json(a, "timesheet", "confirm", DAY_TEXT)
            self.assertEqual((code, error), (0, ""))
            first = document["event_uid"]
            code, document, error = self._json(
                b, "timesheet", "confirm", DAY_TEXT, "--set", f"{PROJECT}=2h")
            self.assertEqual((code, error), (0, ""))
            second = document["event_uid"]
            self.assertEqual((first, second),
                             (support.FIXTURE_FIRST_UID,
                              "00000000-0000-4000-8000-000000000002"))
            [confirmation] = [event for event, _ in support.stored_events(b.store)
                              if event["kind"] == "timesheet_confirmation"]
            self.assertNotIn("replaces", confirmation)
            support.copy_segments(b, a, cut_last_line=False)
            support.copy_segments(a, b, cut_last_line=False)
            line = (f"warning: The timesheet confirmation {first} is not named by the"
                    " latest confirmation of the day.\n")
            for machine in (a, b):
                for words in (DAY_REPORT, TIMESHEET):
                    with self.subTest(machine=machine.machine, command=words[0]):
                        code, document, error = self._json(machine, *words)
                        self.assertEqual((code, document["state"], error),
                                         (0, "declared_day", line))
                        self.assertEqual(
                            [(warning["code"], warning["values"])
                             for warning in document["warnings"]],
                            [("confirmation_not_seen", {"event_uid": first})])
                        self.assertNotIn(second, document["warnings"][0]["message"])
                        code, _, error = support.run_main(machine.context, *words)
                        self.assertEqual((code, error), (0, line))
                code, document, error = self._json(machine, *TIMESHEET)
                self.assertEqual((document["total"], document["measured_total"]),
                                 (7200, 60))
                self.assertEqual([(entry["project"]["id"], entry["declared"])
                                  for entry in document["entries"]], [(PROJECT, 7200)])

    def test_confirmation_seen_after_copy_has_no_warning(self) -> None:
        """A confirmation that the latest one names in `replaces` is a confirmation that
        the machine saw: no report warns (metrics.md › Declared values). With the test of
        the two confirmations that saw none of the other, this shows that the copy of the
        segments is what makes a confirmation seen.

        A confirms the day, and the file-sync service carries its segment to B before B
        confirms the same day an hour later with another value: the confirmation of B names
        the confirmation of A in `replaces`. The service carries the segment of B to A. On
        both machines `report day` and `timesheet` complete with the exit code 0, without
        one line of warning on the standard error or in the document, and the day is
        declared with the entry of B."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids)
            b = support.world(base / "b", MACHINE_B, new_uid=uids, now=LATER)
            self._ingest(a, MEASURED)
            code, document, error = self._json(a, "timesheet", "confirm", DAY_TEXT)
            self.assertEqual((code, error), (0, ""))
            first = document["event_uid"]
            support.copy_segments(a, b, cut_last_line=False)
            code, document, error = self._json(
                b, "timesheet", "confirm", DAY_TEXT, "--set", f"{PROJECT}=2h")
            self.assertEqual((code, error), (0, ""))
            second = document["event_uid"]
            confirmations = {event["event_uid"]: event
                             for event, _ in support.stored_events(b.store)
                             if event["kind"] == "timesheet_confirmation"}
            self.assertEqual(set(confirmations), {first, second})
            self.assertEqual(confirmations[second]["replaces"],
                             {"source": "ledger", "event_uid": first})
            support.copy_segments(b, a, cut_last_line=False)
            for machine in (a, b):
                for words in (DAY_REPORT, TIMESHEET):
                    with self.subTest(machine=machine.machine, command=words[0]):
                        code, document, error = self._json(machine, *words)
                        self.assertEqual((code, document["state"], document["warnings"],
                                          document["configuration_errors"], error),
                                         (0, "declared_day", [], [], ""))
                        code, _, error = support.run_main(machine.context, *words)
                        self.assertEqual((code, error), (0, ""))
                code, document, error = self._json(machine, *TIMESHEET)
                self.assertEqual((document["total"], document["measured_total"]),
                                 (7200, 60))
                self.assertEqual([(entry["project"]["id"], entry["declared"])
                                  for entry in document["entries"]], [(PROJECT, 7200)])

    def test_frozen_remove_on_other_machine_exits_1(self) -> None:
        """Only the machine that wrote a frozen report removes it, because each file of
        the store has one writer: on another machine `frozen remove` stops with the exit
        code 1 and names the machine, in both modes, and the file stays (command-line.md ›
        Frozen reports).

        The two machines share one store folder. A freezes the report of the day with a
        note, and the document gives the identifier of the frozen report. On B,
        `frozen remove` stops with the stop error `frozen_other_machine`, whose values name
        the identifier and the machine A, and with one line `error:` on the standard error
        that names A; the file stays, and `frozen list` on B still holds it. On A the same
        command completes with the exit code 0, and the file is gone."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids)
            b = support.world(base / "b", MACHINE_B, store=a.store, new_uid=uids)
            self.assertEqual(b.store, a.store)
            self._ingest(a, MEASURED)
            code, document, error = self._json(a, *DAY_REPORT, "--freeze", "--note", NOTE)
            self.assertEqual((code, error), (0, ""))
            frozen_id = document["frozen_id"]
            self.assertEqual(frozen_id, support.FIXTURE_FIRST_UID)
            file = a.store / "frozen" / MACHINE_A / f"{frozen_id}.json"
            self.assertTrue(file.is_file())
            text = (f"The frozen report {frozen_id} was written by the machine {MACHINE_A};"
                    " only that machine removes it.")
            for extra in ([], ["--json"]):
                with self.subTest(json=bool(extra)):
                    code, shown, error = support.run_main(
                        b.context, "frozen", "remove", frozen_id, *extra)
                    self.assertEqual(code, 1)
                    self.assertEqual(error, f"error: {text}\n")
                    if extra:
                        self.assertEqual(json.loads(shown), {
                            "command": "frozen remove", "warnings": [],
                            "configuration_errors": [],
                            "error": {"code": "frozen_other_machine",
                                      "values": {"id": frozen_id, "machine": MACHINE_A},
                                      "message": text}})
                    else:
                        self.assertEqual(shown, "")
            self.assertTrue(file.is_file())
            code, document, error = self._json(b, "frozen", "list")
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(document["frozen"], [{
                "id": frozen_id, "report": "report day", "from": DAY_TEXT, "to": DAY_TEXT,
                "note": NOTE, "machine": MACHINE_A, "frozen_at": "2026-11-24T12:00:00.000Z"}])
            code, _, error = support.run_main(a.context, "frozen", "remove", frozen_id)
            self.assertEqual((code, error), (0, ""))
            self.assertFalse(file.exists())

    def test_outputs_name_a_machine_by_its_label(self) -> None:
        """Where an output names a machine to a person, it shows the machine label when the
        store holds one for that machine, and the identifier otherwise; the documents keep
        the identifier under `machine` (command-line.md › JSON documents, › Exit codes;
        GLOSSARY.md › Machine label).

        The two machines share one store folder. A gives itself a label through `machine
        label`, B none. A ingests the session, freezes the report of the day, and confirms
        the day; B, an hour later, freezes the report of the day and confirms the day again.
        On B, each row of `frozen list` holds `machine`, the row of A also `machine_label`
        and the row of B none, and the column Machine of its text shows the label of A and
        the identifier of B; `entries` of the day holds the identifiers of both machines in
        its document, and its text shows the label of A and the identifier of B. `frozen
        remove` of the frozen report of A stops on B with the exit code 1, values that hold
        `machine_label` beside `machine`, and a line that names the label, in English and in
        Italian."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids)
            b = support.world(base / "b", MACHINE_B, store=a.store, new_uid=uids, now=LATER)
            code, _, error = support.run_main(a.context, "machine", "label", LABEL)
            self.assertEqual((code, error), (0, ""))
            self._ingest(a, MEASURED)
            frozen = []
            for machine in (a, b):
                code, document, error = self._json(machine, *DAY_REPORT, "--freeze")
                self.assertEqual((code, error), (0, ""), machine.machine)
                frozen.append(document["frozen_id"])
                code, _, error = self._json(machine, "timesheet", "confirm", DAY_TEXT)
                self.assertEqual((code, error), (0, ""), machine.machine)
            code, document, error = self._json(b, "frozen", "list")
            self.assertEqual((code, error), (0, ""))
            self.assertEqual(document["frozen"], [
                {"id": frozen[0], "report": "report day", "from": DAY_TEXT, "to": DAY_TEXT,
                 "machine": MACHINE_A, "machine_label": LABEL,
                 "frozen_at": "2026-11-24T12:00:00.000Z"},
                {"id": frozen[1], "report": "report day", "from": DAY_TEXT, "to": DAY_TEXT,
                 "machine": MACHINE_B, "frozen_at": "2026-11-24T13:00:00.000Z"}])
            code, document, error = self._json(b, "entries", DAY_TEXT)
            self.assertEqual((code, error), (0, ""))
            self.assertEqual([(entry["kind"], entry["machine"]) for entry in document["entries"]],
                             [("timesheet_confirmation", MACHINE_A),
                              ("timesheet_confirmation", MACHINE_B)])
            for words in (("frozen", "list"), ("entries", DAY_TEXT)):
                with self.subTest(command=words[0]):
                    code, shown, error = support.run_main(b.context, *words)
                    self.assertEqual((code, error), (0, ""))
                    first, second = shown.split("\n\n")[0].splitlines()[2:]
                    self.assertIn(f"  {LABEL}  ", first)
                    self.assertIn(f"  {MACHINE_B}  ", second)
                    self.assertNotIn(MACHINE_A, shown)
            texts = {
                "en": (f"The frozen report {frozen[0]} was written by the machine {LABEL};"
                       " only that machine removes it."),
                "it": (f"Il report congelato {frozen[0]} è stato scritto dalla macchina"
                       f" {LABEL}; solo quella macchina lo rimuove."),
            }
            for language, text in texts.items():
                with self.subTest(language=language):
                    code, shown, error = support.run_main(
                        b.context, "frozen", "remove", frozen[0], "--language", language,
                        "--json")
                    self.assertEqual((code, error), (1, f"error: {text}\n"))
                    self.assertEqual(json.loads(shown)["error"], {
                        "code": "frozen_other_machine",
                        "values": {"id": frozen[0], "machine": MACHINE_A,
                                   "machine_label": LABEL},
                        "message": text})
            self.assertTrue((a.store / "frozen" / MACHINE_A / f"{frozen[0]}.json").is_file())

    def test_unreadable_label_shows_the_identifier_and_warns_once(self) -> None:
        """Store metadata that the ledger cannot read is no label and one warning: the
        output shows the identifier, and the command warns `machine_label_unreadable` once
        for the file, however many of its rows name the machine, in its text and in its
        document, with the exit code 0; the stop error of `frozen remove` names the
        identifier and its envelope holds no warning (command-line.md › JSON documents, ›
        Exit codes).

        The two machines share one store folder. A ingests the session, freezes the report
        of the day and confirms the day, twice; then its store metadata ends inside its
        label, as a file-sync service can hand over a file that A is still writing. On B,
        `frozen list` and `entries` each show two rows of A, in English and in Italian."""
        with support.TemporaryFolder() as base:
            uids = support.fixture_uids()
            a = support.world(base / "a", MACHINE_A, new_uid=uids)
            b = support.world(base / "b", MACHINE_B, store=a.store, new_uid=uids, now=LATER)
            self._ingest(a, MEASURED)
            frozen = []
            for _ in range(2):
                code, document, error = self._json(a, *DAY_REPORT, "--freeze")
                self.assertEqual((code, error), (0, ""))
                frozen.append(document["frozen_id"])
                code, _, error = self._json(a, "timesheet", "confirm", DAY_TEXT)
                self.assertEqual((code, error), (0, ""))
            path = f"machines/{MACHINE_A}.toml"
            (a.store / "machines").mkdir(exist_ok=True)
            (a.store / path).write_text('label = "Invented off', encoding="utf-8")
            texts = {
                "en": f"The store metadata {path} is not readable; the machine is shown by its"
                      " identifier.",
                "it": f"I metadati dell'archivio {path} non sono leggibili; la macchina è"
                      " mostrata con il suo identificativo.",
            }
            warning = {"code": "machine_label_unreadable", "values": {"path": path},
                       "message": texts["en"]}
            for words, key in ((("frozen", "list"), "frozen"), (("entries", DAY_TEXT), "entries")):
                with self.subTest(command=words[0]):
                    code, document, error = self._json(b, *words)
                    self.assertEqual((code, error), (0, f"warning: {texts['en']}\n"))
                    self.assertEqual([row["machine"] for row in document[key]],
                                     [MACHINE_A, MACHINE_A])
                    self.assertTrue(all("machine_label" not in row for row in document[key]))
                    self.assertEqual(document["warnings"], [warning])
                for language, text in texts.items():
                    with self.subTest(command=words[0], language=language):
                        code, shown, error = support.run_main(b.context, *words, "--language",
                                                              language)
                        self.assertEqual((code, error), (0, f"warning: {text}\n"))
                        first, second = shown.split("\n\n")[0].splitlines()[2:]
                        self.assertIn(f"  {MACHINE_A}  ", first)
                        self.assertIn(f"  {MACHINE_A}  ", second)
            text = (f"The frozen report {frozen[0]} was written by the machine {MACHINE_A};"
                    " only that machine removes it.")
            code, shown, error = support.run_main(b.context, "frozen", "remove", frozen[0],
                                                  "--json")
            self.assertEqual((code, error), (1, f"error: {text}\n"))
            envelope = json.loads(shown)
            self.assertEqual(envelope["error"], {
                "code": "frozen_other_machine",
                "values": {"id": frozen[0], "machine": MACHINE_A}, "message": text})
            self.assertEqual(envelope["warnings"], [])
