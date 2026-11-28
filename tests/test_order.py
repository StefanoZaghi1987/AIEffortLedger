"""Order tests: the same native logs in any order of files, and the same segments in any
order, give the same store and the same reports — two stores are the same when they hold
the same event keys, and each key with the same fields except `ingested_at` — and the
report of a day gives the same figures for that day as a report of a longer period that
holds it. The three cases of `ingestion.md` › Adapters, whose stores differ as that
section says — the tool result after the settle time, the fork whose copies entered the
store before its original, and the repository identity of the first ingestion — hold
their own tests (architecture.md › Tests › Order tests, product.md › Phase 1,
acceptance criterion 2).

Every store of every test is built by the real ingestion (`run_ingestion`) from native
logs written by hand with invented text, and every report is computed by the one
pipeline that the report commands share (`figures_of_days`); a comparison never holds a
hand-built side (ADR 0004, CLAUDE.md › Core).
"""

import unittest
from datetime import date
from pathlib import Path

import support
from ai_effort_ledger import events, ingestion, reports
from ai_effort_ledger.cli.figures import Figures
from ai_effort_ledger.configuration import read_machine_configuration, read_person_configuration
from ai_effort_ledger.events import Event, EventKey

DAY = date(2026, 11, 23)
"""The local day that the tests report; the longer period of the day test runs from it
to its Sunday."""
WEEK_LAST = date(2026, 11, 29)
"""The last day of the longer period that holds the day of the tests."""
MACHINE_ONE = "1a2b3c4d-5e6f-4a7b-8c9d-0e1f2a3b4c5d"
MACHINE_TWO = "7f6e5d4c-3b2a-4c1d-8e9f-0a1b2c3d4e5f"
"""The machine identifiers of the tests; the same identifiers in both worlds of a test,
because the `machine` field of an event is one of the fields that must be the same."""
SOURCE = "claude-code-jsonl"
"""The source of every event that the adapter of the tests writes."""
UUID_ONE = "3f1c0000-0000-4000-8000-0000000000a1"
UUID_TWO = "3f1c0000-0000-4000-8000-0000000000a2"
UUID_THREE = "3f1c0000-0000-4000-8000-0000000000a3"
UUID_FOUR = "3f1c0000-0000-4000-8000-0000000000a4"
UUID_FIVE = "3f1c0000-0000-4000-8000-0000000000a5"
"""The native identifiers of the records of the sessions of the tests, invented."""
FORK_INSTANT = "2026-11-23T09:04:00.000Z"
"""The instant of the fork of the tests: the timestamp of the last record that the
forked session shares with its original (event-schema.md › Keys and invariants)."""


def _ingest(world: support.World) -> ingestion.IngestionResult:
    """Run one ingestion of the world into its store folder, through the real ingestion
    with the machine configuration and the person configuration that the world wrote, and
    the adapters, the instant, and the writer version of its context: the same in every
    world of a test, so that the stores hold the same `ingested_at` as well."""
    return ingestion.run_ingestion(
        read_machine_configuration(world.machine_folder), world.machine_folder, world.store,
        read_person_configuration(world.store), world.context.adapters, world.context.now,
        world.home, world.context.system, world.environ, world.context.version)


def _documents(figures: Figures) -> tuple[dict, dict]:
    """The documents of `report timesheet` over the period of the figures and of
    `report day` for its first day, as the reports build them from the figures and the
    names that the attribution of the figures computed."""
    names = reports.Names(figures.attribution.names, figures.attribution.work_item_names)
    return (reports.timesheet_document(figures.days, names),
            reports.day_document(figures.days[0], names))


def _stored(store_folder: Path) -> dict[EventKey, Event]:
    """The store folder as every reader sees it: one event for each key, the winning copy
    — the earliest `ingested_at`, and, at equal instants, the copy in the segment whose
    name sorts first (`event-schema.md` › Keys and invariants) — folded, with the merge
    rule of the product, over the copies that `support.stored_events` reads."""
    copies: dict[EventKey, list[tuple[Event, str]]] = {}
    for event, name in support.stored_events(store_folder):
        copies.setdefault(events.event_key(event), []).append((event, name))
    winners: dict[EventKey, Event] = {}
    for key, group in copies.items():
        winner = group[0]
        for other in group[1:]:
            winner = events.winning_copy(winner, other)
        winners[key] = winner[0]
    return winners


def _key_order(key: EventKey) -> tuple[str, str, str, str]:
    """A stable order of two event keys for a comparison: by source, then native
    identifier, then session, then event identifier, each absent part first."""
    return (key.source, key.native_id or "", key.session_id or "", key.event_uid or "")


def _prompt(instant: str, uuid_value: str) -> dict:
    """A prompt of the person of the tests, typed in the interactive invocation; the text
    is invented."""
    return {**support.prompt_record("Invented prompt of the order tests.", instant,
                                    uuid_value), "entrypoint": "cli"}


def _answer(instant: str, uuid_value: str, response_id: str) -> dict:
    """One output of the model that answers a prompt of the tests; the text is invented."""
    return support.output_record("Invented answer of the order tests.", instant,
                                 uuid_value, response_id)


class OrderTests(unittest.TestCase):
    """The stores and the reports of two worlds of each order of files and of segments,
    and the three cases whose stores differ as `ingestion.md` › Adapters says."""

    def _assert_same_store(
        self,
        first: dict[EventKey, Event],
        second: dict[EventKey, Event],
        allowed: frozenset[str] = frozenset(),
    ) -> list[EventKey]:
        """Assert that the two stores of one comparison hold the same event keys, and
        each key the same fields except `ingested_at` and the allowed fields, and give
        the keys whose fields differ: some field is allowed only where a store differs
        as the spec says, and every difference must stay within the allowed fields
        (architecture.md › Tests › Order tests)."""
        keys_of_first = sorted(first, key=_key_order)
        keys_of_second = sorted(second, key=_key_order)
        self.assertEqual(keys_of_first, keys_of_second, "the event keys of the stores")
        differing: list[EventKey] = []
        for key in keys_of_first:
            names = {name for name in set(first[key]) | set(second[key])
                     if first[key].get(name) != second[key].get(name)}
            names.discard("ingested_at")
            steady_first = {name: value for name, value in first[key].items()
                            if name != "ingested_at" and name not in allowed}
            steady_second = {name: value for name, value in second[key].items()
                             if name != "ingested_at" and name not in allowed}
            self.assertEqual(steady_first, steady_second,
                             f"the fields of the key {key.to_json()}")
            if names:
                self.assertTrue(names <= set(allowed),
                                f"the key {key.to_json()} differs in {sorted(names)}")
                differing.append(key)
        self.assertEqual(bool(differing), bool(allowed),
                         "a difference the spec allows must exist, and none beside it")
        return differing

    def test_shuffled_file_order_gives_same_store(self) -> None:
        """The same native logs read in another order of files — the forked session first,
        alone in its own folder of native logs, ahead of the folder of its original and
        of the other session — give the same store: the same event keys, and each key
        with the same fields except `ingested_at`, which is the same instant here. The
        copy that the fork made of a record of its original is one event, held by the
        original, and the events of its own after the fork instant name it
        (event-schema.md › Keys and invariants), whatever order the reading follows."""
        with support.TemporaryFolder() as base:
            work = support.remote_repository(base / "work", "https://Example.com/Order/Shared.git")
            original = [_prompt("2026-11-23T09:00:00.000Z", UUID_ONE),
                        support.queue_record("Invented queued message.",
                                             "2026-11-23T09:02:00.000Z"),
                        _answer("2026-11-23T09:04:00.000Z", UUID_TWO, "msg-order-shared")]
            forked = [_prompt("2026-11-23T09:00:00.000Z", UUID_ONE),
                      _answer("2026-11-23T09:04:00.000Z", UUID_TWO, "msg-order-shared"),
                      _prompt("2026-11-23T11:00:00.000Z", UUID_THREE)]
            other = [_prompt("2026-11-23T10:00:00.000Z", UUID_FOUR),
                     _answer("2026-11-23T10:05:00.000Z", UUID_FIVE, "msg-order-other")]
            logs = base / "logs-sorted"
            first = support.world(base / "sorted", MACHINE_ONE, logs=[logs])
            support.write_session(logs, "session-alpha", original, {}, work)
            support.write_session(logs, "session-beta", other, {}, work)
            support.write_session(logs, "session-zeta", forked, {}, work)
            support.settle([logs])
            _ingest(first)
            ahead = base / "logs-fork-ahead"
            behind = base / "logs-rest-behind"
            second = support.world(base / "shuffled", MACHINE_ONE, logs=[ahead, behind])
            support.write_session(ahead, "session-zeta", forked, {}, work)
            support.write_session(behind, "session-alpha", original, {}, work)
            support.write_session(behind, "session-beta", other, {}, work)
            support.settle([ahead, behind])
            _ingest(second)
            held_first, held_second = _stored(first.store), _stored(second.store)
        self._assert_same_store(held_first, held_second)
        self.assertEqual(len(held_first), 6)
        shared = EventKey(SOURCE, native_id=UUID_ONE)
        self.assertEqual(held_first[shared]["session_id"], "session-alpha")
        own = EventKey(SOURCE, native_id=UUID_THREE)
        self.assertEqual(held_first[own]["forked_from"],
                         {"session_id": "session-alpha", "instant": FORK_INSTANT})

    def test_segment_order_gives_same_reports(self) -> None:
        """The segments of two machines, each written by its own ingestion into the store
        folder of its world, give the same store and the same reports when the local
        index holds them in the opposite order: the machine that ingested first indexed
        the segments of its world in one order, the machine that ingested second in the
        other, and the documents of `report timesheet` and of `report day` for the day,
        computed through the one pipeline on the index of that second machine, are the
        same, as the keys and the fields of the two stores are, except `ingested_at`
        (ingestion.md › Store, event-schema.md › Keys and invariants)."""
        with support.TemporaryFolder() as base:
            first_work = support.remote_repository(base / "work-first",
                                                   "https://Example.com/Order/First.git")
            second_work = support.remote_repository(base / "work-second",
                                                    "https://Example.com/Order/Second.git")
            alpha = [_prompt("2026-11-23T09:00:00.000Z", UUID_ONE),
                     _answer("2026-11-23T09:06:00.000Z", UUID_TWO, "msg-order-alpha")]
            beta = [_prompt("2026-11-23T09:02:00.000Z", UUID_THREE),
                    _answer("2026-11-23T09:10:00.000Z", UUID_FOUR, "msg-order-beta")]
            alpha_logs = base / "logs-alpha"
            beta_logs = base / "logs-beta"
            support.write_session(alpha_logs, "session-alpha", alpha, {}, first_work)
            support.write_session(beta_logs, "session-beta", beta, {}, second_work)
            support.settle([alpha_logs, beta_logs])
            first_store, second_store = base / "store-one-first", base / "store-two-first"
            one_ahead = support.world(base / "one-ahead", MACHINE_ONE, store=first_store,
                                      logs=[alpha_logs])
            two_behind = support.world(base / "two-behind", MACHINE_TWO, store=first_store,
                                       logs=[beta_logs])
            _ingest(one_ahead)
            _ingest(two_behind)
            two_ahead = support.world(base / "two-ahead", MACHINE_TWO, store=second_store,
                                      logs=[beta_logs])
            one_behind = support.world(base / "one-behind", MACHINE_ONE, store=second_store,
                                       logs=[alpha_logs])
            _ingest(two_ahead)
            _ingest(one_behind)
            held_first, held_second = _stored(first_store), _stored(second_store)
            sheet_first, day_first = _documents(
                support.store_figures(two_behind.context, two_behind.store, DAY, DAY))
            sheet_second, day_second = _documents(
                support.store_figures(one_behind.context, one_behind.store, DAY, DAY))
        self.assertEqual(len(held_first), 4)
        self.assertEqual(self._assert_same_store(held_first, held_second), [])
        self.assertEqual(sheet_first, sheet_second)
        self.assertEqual(day_first, day_second)
        projects = [entry["project"]["id"] for entry in day_first["projects"]
                    if entry["project"]]
        self.assertEqual(projects, ["example.com/order/first", "example.com/order/second"])

    def test_day_equals_day_inside_week(self) -> None:
        """The report of the day gives the same figures for that day as the report of the
        week that holds it: the document of `report day` and the entry of the day in the
        document of `report timesheet` are the same. The day holds the signal gap that
        reaches into it from the evening before — two signals of two sessions eight
        minutes apart over the change of the day — which the margin of the selection
        reads in the report of the day as well as in the report of the week, so the
        human time of the day is the same 240 seconds in both
        (architecture.md › Tests › Order tests, selection.py)."""
        with support.TemporaryFolder() as base:
            world = support.world(base / "week", MACHINE_ONE, logs=[base / "logs"])
            eve = support.remote_repository(base / "work-eve", "https://Example.com/Order/Eve.git")
            morning = support.remote_repository(base / "work-morning",
                                                "https://Example.com/Order/Morning.git")
            later = support.remote_repository(base / "work-later",
                                              "https://Example.com/Order/Later.git")
            support.write_session(world.logs[0], "session-eve",
                                  [_prompt("2026-11-22T23:56:00.000Z", UUID_ONE)], {}, eve)
            support.write_session(world.logs[0], "session-morning",
                                  [_prompt("2026-11-23T00:04:00.000Z", UUID_TWO),
                                   _answer("2026-11-23T00:09:00.000Z", UUID_THREE,
                                           "msg-order-morning")], {}, morning)
            support.write_session(world.logs[0], "session-later",
                                  [_prompt("2026-11-25T10:00:00.000Z", UUID_FOUR),
                                   _answer("2026-11-25T10:05:00.000Z", UUID_FIVE,
                                           "msg-order-later")], {}, later)
            support.settle(world.logs)
            _ingest(world)
            sheet_day, day_day = _documents(
                support.store_figures(world.context, world.store, DAY, DAY))
            sheet_week, day_week = _documents(
                support.store_figures(world.context, world.store, DAY, WEEK_LAST))
        self.assertEqual(day_day, day_week)
        self.assertEqual(sheet_day["days"][0], sheet_week["days"][0])
        self.assertEqual(sheet_day["days"][0]["total"], 240)
        projects = [entry["project"]["id"] for entry in day_day["projects"]
                    if entry["project"]]
        self.assertEqual(projects, ["example.com/order/morning"])

    def test_tool_result_after_settle_time(self) -> None:
        """A tool result that arrives after the settle time finds its tool call stored
        without the size counters: the store that read the settled session with the call
        alone, and read the result at a later ingestion, and the store that read the
        call and its result together hold the same event keys, and each key the same
        fields except `ingested_at` and the size counters of that one tool call, which
        only the store of the reading together holds (ingestion.md › Adapters,
        event-schema.md › Keys and invariants)."""
        with support.TemporaryFolder() as base:
            work = support.remote_repository(base / "work", "https://Example.com/Order/Edit.git")
            call = support.tool_use(
                "Edit", "toolu-order-one",
                {"file_path": "D:\\Work\\Product\\order_notes.py", "old_string": "alpha",
                 "new_string": "beta one\nbeta two"},
                "2026-11-23T10:00:00.000Z", UUID_ONE, "msg-order-edit")
            result = support.tool_result_record(
                "toolu-order-one", "2026-11-23T10:01:00.000Z", UUID_TWO,
                {"type": "update",
                 "structuredPatch": [{"lines": ["-alpha", "+beta one", "+beta two"]}]})
            together = support.world(base / "together", MACHINE_ONE,
                                     logs=[base / "logs-together"])
            support.write_session(together.logs[0], "session-edit", [call, result], {}, work)
            support.settle([together.logs[0] / "session-edit.jsonl"])
            _ingest(together)
            apart = support.world(base / "apart", MACHINE_ONE, logs=[base / "logs-apart"])
            support.write_session(apart.logs[0], "session-edit", [call], {}, work)
            support.settle([apart.logs[0] / "session-edit.jsonl"])
            _ingest(apart)
            support.write_session(apart.logs[0], "session-edit", [call, result], {}, work)
            support.settle([apart.logs[0] / "session-edit.jsonl"])
            _ingest(apart)
            held_together, held_apart = _stored(together.store), _stored(apart.store)
        counters = frozenset(("lines_added", "lines_removed", "file_ext", "size_basis"))
        differing = self._assert_same_store(held_together, held_apart, allowed=counters)
        self.assertEqual(len(held_together), 3)
        self.assertEqual([key.native_id for key in differing], ["tool_call:toolu-order-one"])
        call_key = EventKey(SOURCE, native_id="tool_call:toolu-order-one")
        self.assertEqual({name: held_together[call_key][name] for name in counters},
                         {"lines_added": 2, "lines_removed": 1, "file_ext": "py",
                          "size_basis": "patch"})
        for name in counters:
            self.assertNotIn(name, held_apart[call_key])

    def test_fork_read_before_its_original(self) -> None:
        """A forked session whose copied events entered the store before the session that
        holds them as its own keeps them: the store that read the fork first and the
        store that read the pair fresh hold the same event keys, and each key the same
        fields except `ingested_at`, the session of the copies — the fork where they
        entered first, the original where the pair was read together — the agent of the
        session that the event names, which follows its session, and the `forked_from`
        that only the fresh reading writes on the events of its own of the fork, because
        an event already in the store keeps its session
        (ingestion.md › Adapters, event-schema.md › Keys and invariants)."""
        with support.TemporaryFolder() as base:
            work = support.remote_repository(base / "work", "https://Example.com/Order/Fork.git")
            original = [_prompt("2026-11-23T09:00:00.000Z", UUID_ONE),
                        support.queue_record("Invented queued message.",
                                             "2026-11-23T09:02:00.000Z"),
                        _answer("2026-11-23T09:04:00.000Z", UUID_TWO, "msg-order-fork")]
            forked = [_prompt("2026-11-23T09:00:00.000Z", UUID_ONE),
                      _answer("2026-11-23T09:04:00.000Z", UUID_TWO, "msg-order-fork"),
                      _prompt("2026-11-23T11:00:00.000Z", UUID_THREE)]
            first = support.world(base / "fork-first", MACHINE_ONE,
                                  logs=[base / "logs-fork-first"])
            support.write_session(first.logs[0], "session-zeta", forked, {}, work)
            support.settle([first.logs[0] / "session-zeta.jsonl"])
            _ingest(first)
            support.write_session(first.logs[0], "session-alpha", original, {}, work)
            support.settle([first.logs[0] / "session-alpha.jsonl"])
            _ingest(first)
            second = support.world(base / "fork-second", MACHINE_ONE,
                                   logs=[base / "logs-fork-second"])
            support.write_session(second.logs[0], "session-alpha", original, {}, work)
            support.write_session(second.logs[0], "session-zeta", forked, {}, work)
            support.settle(second.logs)
            _ingest(second)
            held_first, held_second = _stored(first.store), _stored(second.store)
        differing = self._assert_same_store(
            held_first, held_second,
            allowed=frozenset(("session_id", "agent_id", "forked_from")))
        self.assertEqual(len(held_first), 4)
        shared = sorted((EventKey(SOURCE, native_id=UUID_ONE),
                         EventKey(SOURCE, native_id="msg-order-fork")), key=_key_order)
        self.assertEqual(sorted(differing, key=_key_order),
                         sorted([*shared, EventKey(SOURCE, native_id=UUID_THREE)],
                                key=_key_order))
        for key in shared:
            self.assertEqual(held_first[key]["session_id"], "session-zeta")
            self.assertEqual(held_second[key]["session_id"], "session-alpha")
            self.assertEqual(held_first[key]["agent_id"], "session-zeta")
            self.assertEqual(held_second[key]["agent_id"], "session-alpha")
        own = EventKey(SOURCE, native_id=UUID_THREE)
        self.assertNotIn("forked_from", held_first[own])
        self.assertEqual(held_second[own]["forked_from"],
                         {"session_id": "session-alpha", "instant": FORK_INSTANT})

    def test_repository_identity_at_first_ingestion(self) -> None:
        """The repository identity of an event is the one that its first ingestion reads
        from the folder as it is at that hour: the store that read the session while the
        folder named the first remote, read the changed folder at a later ingestion, and
        the store that read the whole session after the change hold the same event keys,
        and each key the same fields except `ingested_at` and the `repo_hint` of the
        events of the first ingestion, which name the remote that the folder held then;
        the event that a later ingestion wrote names the remote that the folder holds
        now, in both stores (ingestion.md › Adapters, › Repository identity)."""
        with support.TemporaryFolder() as base:
            work = support.remote_repository(base / "work", "https://Example.com/Order/First.git")
            records = [_prompt("2026-11-23T09:00:00.000Z", UUID_ONE),
                       _answer("2026-11-23T09:05:00.000Z", UUID_TWO, "msg-order-repo"),
                       _prompt("2026-11-23T10:30:00.000Z", UUID_THREE)]
            first = support.world(base / "repo-first", MACHINE_ONE,
                                  logs=[base / "logs-repo-first"])
            support.write_session(first.logs[0], "session-repo", records[:2], {}, work)
            support.settle([first.logs[0] / "session-repo.jsonl"])
            _ingest(first)
            support.remote_repository(work, "https://Example.com/Order/Second.git")
            support.write_session(first.logs[0], "session-repo", records, {}, work)
            support.settle([first.logs[0] / "session-repo.jsonl"])
            _ingest(first)
            second = support.world(base / "repo-second", MACHINE_ONE,
                                   logs=[base / "logs-repo-second"])
            support.write_session(second.logs[0], "session-repo", records, {}, work)
            support.settle([second.logs[0] / "session-repo.jsonl"])
            _ingest(second)
            held_first, held_second = _stored(first.store), _stored(second.store)
        differing = self._assert_same_store(held_first, held_second,
                                            allowed=frozenset(("repo_hint",)))
        self.assertEqual(len(held_first), 3)
        early = sorted((EventKey(SOURCE, native_id=UUID_ONE),
                        EventKey(SOURCE, native_id="msg-order-repo")), key=_key_order)
        self.assertEqual(sorted(differing, key=_key_order), early)
        for key in early:
            self.assertEqual(held_first[key]["repo_hint"], "example.com/order/first")
            self.assertEqual(held_second[key]["repo_hint"], "example.com/order/second")
            self.assertEqual(held_first[key]["repo_basis"], "observed")
        late = EventKey(SOURCE, native_id=UUID_THREE)
        self.assertEqual(held_first[late]["repo_hint"], "example.com/order/second")
        self.assertEqual(held_second[late]["repo_hint"], "example.com/order/second")
