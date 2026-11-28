"""Tests of the declared values: the latest timesheet confirmation of a day with its chain
of `replaces` and its warnings, the order of the buckets, the whole seconds of the parts
of a day, the timesheet proposal of a day, and the figures of one day that `reports`
reads (metrics.md › Declared values, ADR 0011, ADR 0014, product.md › Phase 1,
acceptance criteria 4 and 5)."""

import unittest
from datetime import date, time
from typing import Any

import support
from ai_effort_ledger import events
from ai_effort_ledger.attribution import split
from ai_effort_ledger.configuration import (
    DayStartEntry,
    PersonConfiguration,
    ProjectName,
    TimeZoneEntry,
)
from ai_effort_ledger.days import LocalDays
from ai_effort_ledger.declared import (
    SetAboveTotal,
    TimesheetLine,
    bucket_order,
    day_figures,
    latest_confirmation,
    proposal,
    whole_seconds,
)
from ai_effort_ledger.events import Event, EventKey
from ai_effort_ledger.metrics import (
    HumanInterval,
    Metrics,
    MetricsParameters,
    compute_metrics,
    stream_of,
)

_DAY = date(2026, 6, 15)
_MACHINE = "3f0d5a1e-8c2b-4d6e-9f0a-1b2c3d4e5f60"
_TOOL = "example_tool"
_SESSION = "session-1"
_ALPHA = "example.org/team/alpha"
_BETA = "example.org/team/beta"

_PARAMETERS = MetricsParameters(idle_gap=600, minimum_attention=60, stale_limit=14400,
                                headless_prompts=False)
"""The report parameters of the tests, at the defaults of the ledger."""


def _person(projects: list[ProjectName] | None = None) -> PersonConfiguration:
    """A person configuration with the invented entries given and no other fact."""
    return PersonConfiguration(
        time_zones=[TimeZoneEntry("Etc/UTC", support.utc("1970-01-01T00:00"), 2)],
        day_starts=[DayStartEntry(time(0, 0), date(1970, 1, 1), 3)],
        projects=list(projects or []),
        work_items=[],
        identity_rules=[],
        category_rules=[],
        preferred_remotes=["origin"],
        settle_time=14400,
        report={},
    )


def _at(clock: str) -> str:
    """The instant of the day of the tests at the `HH:MM` clock time."""
    return f"2026-06-15T{clock}:00.000Z"


def _ms(clock: str) -> int:
    """The instant of the day of the tests as milliseconds since the epoch."""
    return round(support.utc(_at(clock)).timestamp() * 1000)


def _event(timestamp: str, event_uid: str, **overrides: Any) -> events.Event:
    """A complete invented event of a session, with the identity fields the overrides
    give; the local days of the tests make its instant fall on `_DAY`."""
    event: events.Event = {
        "schema_version": events.SCHEMA_VERSION,
        "source": "example_tool",
        "native_id": "native-" + event_uid,
        "event_uid": event_uid,
        "timestamp": timestamp,
        "writer_version": "0.1.0",
        "actor": "agent",
        "kind": "tool_call",
        "machine": _MACHINE,
        "tool": _TOOL,
        "session_id": _SESSION,
    }
    event.update(overrides)
    return event


def _signal(timestamp: str, event_uid: str, **overrides: Any) -> events.Event:
    """A prompt of the person, the human signal of the tests."""
    return _event(timestamp, event_uid, kind="prompt", actor="human", **overrides)


def _confirmation(
    event_uid: str,
    timestamp: str,
    entries: list[dict[str, Any]],
    replaces: str | None = None,
) -> events.Event:
    """A timesheet confirmation that a command writes, with the entries of one day and
    the event identifier of the confirmation it replaces."""
    made: events.Event = {
        "schema_version": events.SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": event_uid,
        "timestamp": timestamp,
        "writer_version": "0.1.0",
        "actor": "human",
        "kind": "timesheet_confirmation",
        "machine": _MACHINE,
        "day": _DAY.isoformat(),
        "entries": entries,
    }
    if replaces is not None:
        made["replaces"] = {"source": "ledger", "event_uid": replaces}
    return made


def _entry(project: str | None, duration: int, work_item: str | None = None) -> dict[str, Any]:
    """One entry of a timesheet confirmation: a duration in whole seconds for a project
    and its optional work item, or for the unattributed time without a project."""
    given: dict[str, Any] = {"duration": duration}
    if project is not None:
        given["project"] = project
    if work_item is not None:
        given["work_item"] = work_item
    return given


def _figures_of(
    session_events: list[events.Event],
    confirmations: list[events.Event] = (),
    manual_entries: list[events.Event] = (),
    person: PersonConfiguration | None = None,
    days: LocalDays | None = None,
    day: date = _DAY,
) -> tuple[Any, split.Attribution]:
    """The figures of the day of the tests, with the report that holds them: the metrics
    of the sessions and the manual entries, the attribution with the confirmations, and
    the day figures that `reports` reads."""
    entries = list(manual_entries)
    local_days = days or support.scenario_days()
    metrics = compute_metrics(session_events, entries, _PARAMETERS)
    report = split.attribute(session_events, [], entries, metrics, person or _person(),
                             local_days, confirmations)
    figures = day_figures(day, report, stream_of(session_events),
                          confirmations, set(), local_days, _PARAMETERS)
    return figures, report


class LatestConfirmationTests(unittest.TestCase):
    """The latest timesheet confirmation of a day (metrics.md › Declared values, ADR
    0014): the one with the latest `timestamp`, equal instants by event key, the chain
    of `replaces` through the retracted confirmations, and the warnings of two
    machines."""

    def test_latest_by_timestamp_then_key(self) -> None:
        """The latest confirmation is the one with the latest `timestamp`, and equal
        instants resolve by event key, the larger key, as every rule that applies over
        another."""
        earlier = _confirmation("uid-one", _at("10:00"), [_entry(_ALPHA, 3600)])
        later = _confirmation("uid-two", _at("12:00"), [_entry(_ALPHA, 1800)])
        tie_low = _confirmation("uid-one", _at("10:00"), [_entry(_ALPHA, 3600)])
        tie_high = _confirmation("uid-two", _at("10:00"), [_entry(_ALPHA, 1800)])
        self.assertIs(latest_confirmation([earlier, later], set()).latest, later)
        self.assertIs(latest_confirmation([tie_low, tie_high], set()).latest, tie_high)

    def test_retracting_latest_brings_back_earlier(self) -> None:
        """A retraction of the latest confirmation brings back the one before it: the
        latest is then the earlier confirmation, without a warning."""
        first = _confirmation("uid-one", _at("10:00"), [_entry(_ALPHA, 3600)])
        second = _confirmation("uid-two", _at("11:00"), [_entry(_ALPHA, 1800)],
                               replaces="uid-one")
        cancelled = {EventKey("ledger", event_uid="uid-two")}
        declaration = latest_confirmation([first, second], cancelled)
        self.assertIs(declaration.latest, first)
        self.assertEqual(declaration.warnings, [])

    def test_all_retracted_is_measured_day(self) -> None:
        """A day whose confirmations are all retracted is a measured day again: the
        latest is none, and no confirmation warns (metrics.md › Declared values, ADR
        0014)."""
        first = _confirmation("uid-one", _at("10:00"), [_entry(_ALPHA, 3600)])
        second = _confirmation("uid-two", _at("11:00"), [_entry(_BETA, 1800)])
        cancelled = {EventKey("ledger", event_uid="uid-one"),
                     EventKey("ledger", event_uid="uid-two")}
        declaration = latest_confirmation([first, second], cancelled)
        self.assertIsNone(declaration.latest)
        self.assertEqual(declaration.warnings, [])

    def test_confirmation_not_seen(self) -> None:
        """Two machines confirmed the day without seeing each other: an earlier
        confirmation that no `replaces` names is not named by the latest one, directly
        or through the confirmations between them, and the report warns (product.md ›
        Phase 1, acceptance criterion 5)."""
        first = _confirmation("uid-one", _at("10:00"), [_entry(_ALPHA, 3600)])
        second = _confirmation("uid-two", _at("11:00"), [_entry(_ALPHA, 1800)])
        declaration = latest_confirmation([first, second], set())
        self.assertIs(declaration.latest, second)
        self.assertEqual(declaration.warnings,
                         [{"code": "confirmation_not_seen",
                           "values": {"event_uid": "uid-one"}}])

    def test_chain_through_retracted_confirmation(self) -> None:
        """A retracted confirmation still carries the chain of `replaces`: the earlier
        confirmation that the latest names through a retracted confirmation between them
        is named, and no confirmation warns (metrics.md › Declared values)."""
        first = _confirmation("uid-one", _at("10:00"), [_entry(_ALPHA, 3600)])
        second = _confirmation("uid-two", _at("10:30"), [_entry(_ALPHA, 3000)],
                               replaces="uid-one")
        third = _confirmation("uid-three", _at("11:00"), [_entry(_ALPHA, 1800)],
                              replaces="uid-two")
        cancelled = {EventKey("ledger", event_uid="uid-two")}
        declaration = latest_confirmation([first, second, third], cancelled)
        self.assertIs(declaration.latest, third)
        self.assertEqual(declaration.warnings, [])

    def test_confirmation_before_replaced(self) -> None:
        """A confirmation whose `timestamp` is earlier than the confirmation that it
        replaces warns about its clock, and because the latest is the one with the
        latest `timestamp`, its own confirmation is also not named by the latest
        one."""
        first = _confirmation("uid-one", _at("10:00"), [_entry(_ALPHA, 3600)])
        second = _confirmation("uid-two", _at("11:00"), [_entry(_ALPHA, 3000)],
                               replaces="uid-one")
        third = _confirmation("uid-three", _at("10:30"), [_entry(_ALPHA, 1800)],
                              replaces="uid-two")
        declaration = latest_confirmation([first, second, third], set())
        self.assertIs(declaration.latest, second)
        self.assertEqual(declaration.warnings, [
            {"code": "confirmation_before_replaced",
             "values": {"event_uid": "uid-three"}},
            {"code": "confirmation_not_seen",
             "values": {"event_uid": "uid-three"}},
        ])


class BucketOrderTests(unittest.TestCase):
    """The order of the entries of a day: larger measured human time first, then the
    project and work item identifiers as text, the unattributed time last (metrics.md ›
    Declared values)."""

    def test_bucket_order(self) -> None:
        """The measured human time decides first, the identifiers as text decide at
        equal time, and the unattributed time comes last whatever its time."""
        measured = {(_ALPHA, None): 300, (_BETA, None): 300, ("acme/gamma", None): 0,
                    (None, None): 900}
        ordered = sorted(measured, key=lambda bucket: bucket_order(bucket, measured))
        self.assertEqual(ordered, [(_ALPHA, None), (_BETA, None), ("acme/gamma", None),
                                   (None, None)])


class WholeSecondsTests(unittest.TestCase):
    """The whole seconds of the parts of a day (decision D12): the whole seconds of the
    total divided among the parts with the largest-remainder method, ties in the order
    of the entries (metrics.md › Declared values)."""

    def test_whole_seconds_add_up(self) -> None:
        """Three parts of 1500 ms, 1500 ms, and 1000 ms give 2, 1, and 1 seconds: the
        parts add up to the 4 whole seconds of the total, the tie of the two 1500 ms
        parts goes to the larger measured human time, and at equal measured time the
        identifiers decide."""
        tied = {("a", None): 1500, ("b", None): 1500, ("c", None): 1000}
        by_time = {("a", None): 1500, ("b", None): 1400, ("c", None): 900}
        self.assertEqual(whole_seconds(tied, by_time),
                         {("a", None): 2, ("b", None): 1, ("c", None): 1})
        pair = {("a", None): 1500, ("b", None): 1500}
        self.assertEqual(whole_seconds(pair, {("a", None): 5, ("b", None): 5}),
                         {("a", None): 2, ("b", None): 1})
        self.assertEqual(sum(whole_seconds(tied, by_time).values()), 4)

    def test_whole_seconds_of_a_part_below_one_second(self) -> None:
        """A total of 900400 ms gives 900 whole seconds: the part of the total below one
        whole second stays out, and the parts add up to it."""
        parts = {("a", None): 900400}
        self.assertEqual(whole_seconds(parts, parts), {("a", None): 900})
        self.assertEqual(whole_seconds({}, {}), {})


class ProposalTests(unittest.TestCase):
    """The timesheet proposal of a day (metrics.md › Declared values, command-line.md ›
    Timesheet): each entry rounded up to the granularity, the division of a given total
    by the shares with the largest-remainder method, and the values given that are more
    than the total, which stop the command."""

    def test_rounds_up_to_granularity(self) -> None:
        """Without a total, each entry is its value rounded up to the granularity:
        measured human time is a lower bound, so 50 min propose 60 min at the default
        granularity of 15 min."""
        self.assertEqual(proposal({("a", None): 3000}, 900), {("a", None): 3600})

    def test_zero_entries_are_left_out(self) -> None:
        """The proposal has one entry for each bucket whose measured human time with
        manual entries is not zero: an entry of zero holds no time and stays out, with
        and without a total."""
        entries = {("a", None): 0, ("b", None): 600}
        self.assertEqual(proposal(entries, 900), {("b", None): 900})
        self.assertEqual(proposal(entries, 900, 1800), {("b", None): 1800})

    def test_total_divides_by_shares(self) -> None:
        """With a total, the proposal divides the total by the shares of measured human
        time with manual entries, so that the entries add up to the total: 8 h over
        3 h and 1 h measured divides into 24 and 8 units of 15 min, 6 h and 2 h."""
        shares = {("a", None): 10800, ("b", None): 3600}
        self.assertEqual(proposal(shares, 900, 28800),
                         {("a", None): 21600, ("b", None): 7200})

    def test_shares_include_manual_entries(self) -> None:
        """The shares of the division are the measured human times with manual entries:
        30 min measured on `a` and a manual entry of 60 min on `b` divide a total of
        3 h into 1 h and 2 h."""
        shares = {("a", None): 1800, ("b", None): 3600}
        self.assertEqual(proposal(shares, 900, 10800),
                         {("a", None): 3600, ("b", None): 7200})

    def test_rest_below_one_unit_to_largest_remainder(self) -> None:
        """A part of the total smaller than one unit goes to the entry with the largest
        remainder: the 5 min below the 32 units of 8:05 go to `a`, whose remainders tie
        `b` at zero and whose measured human time is the larger one."""
        shares = {("a", None): 10800, ("b", None): 3600}
        self.assertEqual(proposal(shares, 900, 29100),
                         {("a", None): 21900, ("b", None): 7200})

    def test_equal_remainders_follow_bucket_order(self) -> None:
        """Between equal remainders, the entry with the larger measured human time with
        manual entries comes first, then the entry whose project and work item
        identifiers come first as text: a total of 30 min over 15 min and 45 min gives
        the extra unit to `b`, and 1:15 over two equal shares gives it to `a`, whose
        identifier comes first."""
        shares = {("a", None): 900, ("b", None): 2700}
        self.assertEqual(proposal(shares, 900, 1800),
                         {("a", None): 0, ("b", None): 1800})
        tied = {("b", None): 3375, ("a", None): 3375}
        self.assertEqual(proposal(tied, 900, 4500),
                         {("b", None): 1800, ("a", None): 2700})

    def test_given_entries_and_total(self) -> None:
        """When the person gives the value of some entries and a total, the rest of the
        total divides among the other entries in the same way: with the value of `a`
        fixed at 2 h, the other 6 h of a total of 8 h divide by equal shares into
        3 h and 3 h."""
        shares = {("a", None): 7200, ("b", None): 3600, ("c", None): 3600}
        self.assertEqual(proposal(shares, 900, 28800, {("a", None): 7200}),
                         {("a", None): 7200, ("b", None): 10800, ("c", None): 10800})

    def test_rest_without_other_entry_is_unattributed(self) -> None:
        """When no other entry exists, the rest of the total becomes the entry of the
        unattributed time: a total of 3 h proposes the unattributed 3 h, and a given
        unattributed value of 1 h takes the rest of 2 h, so that the entry holds 3 h."""
        self.assertEqual(proposal({}, 900, 10800), {(None, None): 10800})
        self.assertEqual(proposal({}, 900, 10800, {(None, None): 3600}),
                         {(None, None): 10800})

    def test_total_on_a_day_without_measured_time_is_unattributed(self) -> None:
        """A day whose buckets all hold no measured human time divides no total: the
        whole of the total becomes the entry of the unattributed time."""
        self.assertEqual(proposal({("a", None): 0}, 900, 10800),
                         {(None, None): 10800})

    def test_total_of_zero_proposes_no_entry(self) -> None:
        """A total of zero divides nothing: the rest of the total is zero and proposes
        no entry, not even the entry of the unattributed time, whose value is zero
        (metrics.md › Declared values); a value given with a total of zero is more than
        the total and stops."""
        self.assertEqual(proposal({}, 900, 0), {})
        self.assertEqual(proposal({("a", None): 0}, 900, 0), {})
        with self.assertRaises(SetAboveTotal):
            proposal({}, 900, 0, {("a", None): 900})

    def test_given_project_and_total_without_measured_time(self) -> None:
        """A value that the person gives can name a project that the proposal does not
        hold: with the entry of `a` fixed at 1 h and a total of 3 h on a day without
        measured time, the entry of `a` holds 1 h and the rest of 2 h becomes the
        unattributed entry."""
        self.assertEqual(proposal({}, 900, 10800, {("a", None): 3600}),
                         {("a", None): 3600, (None, None): 7200})

    def test_set_above_total_stops(self) -> None:
        """Values given that are more than the total stop the command: the error carries
        the code of the text of the output language, no values, and exit 1
        (command-line.md › Timesheet); values equal to the total are not more."""
        with self.assertRaises(SetAboveTotal) as raised:
            proposal({("a", None): 3600}, 900, 1800, {("a", None): 3600})
        self.assertEqual(raised.exception.code, "set_above_total")
        self.assertEqual(raised.exception.values, {})
        self.assertEqual(raised.exception.exit_code, 1)
        self.assertEqual(proposal({}, 900, 3600, {(None, None): 3600}),
                         {(None, None): 3600})

    def test_total_below_measured_is_allowed(self) -> None:
        """The total can be lower than the measured human time: a total of 1 h over 3 h
        and 1 h measured divides into 45 min and 15 min, each lower than its measured
        time; no error and no warning rise here, the warning rises on the declared day
        (metrics.md › Declared values)."""
        shares = {("a", None): 10800, ("b", None): 3600}
        self.assertEqual(proposal(shares, 900, 3600),
                         {("a", None): 2700, ("b", None): 900})


class DayFiguresTests(unittest.TestCase):
    """The figures of one day: the state of the day, the totals, the lines of the
    buckets, the warnings of the declared values, and the context of the person
    (metrics.md › Declared values, ADR 0014)."""

    def test_declared_total_is_sum_of_entries(self) -> None:
        """On a declared day the declared values add up to the total of the latest
        timesheet confirmation (product.md › Phase 1, acceptance criterion 4): the
        entries of three buckets, one of them without measured time, each hold their
        declared value, and a declared day shows no human time at the idle gaps."""
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        second = _signal(_at("10:04"), "uid-second", repo_hint=_ALPHA)
        confirmation = _confirmation("uid-one", _at("18:00"), [
            _entry(_ALPHA, 3600), _entry("acme/beta", 1800), _entry(None, 600)])
        person = _person([ProjectName("acme/beta", "Invented Beta")])
        figures, _ = _figures_of([first, second], [confirmation], person=person)
        timesheet = figures.timesheet
        self.assertEqual(timesheet.state, "declared_day")
        self.assertEqual(timesheet.total, 6000)
        self.assertEqual(timesheet.measured_total, 300)
        self.assertEqual(timesheet.lines, [
            TimesheetLine((_ALPHA, None), 300, 300, 3600),
            TimesheetLine(("acme/beta", None), 0, 0, 1800),
            TimesheetLine((None, None), 0, 0, 600),
        ])
        self.assertIsNone(timesheet.human_time_at_idle_gaps)
        self.assertEqual(timesheet.presence_span, 240)
        self.assertEqual(timesheet.agent_time, 0)
        self.assertEqual(timesheet.unknown_invocation_share, 0.0)
        self.assertEqual(timesheet.warnings, [])
        self.assertEqual(figures.buckets[(_ALPHA, None)].human_time, 300_000)
        self.assertEqual(figures.person.with_manual, 300_000)
        self.assertEqual(figures.person.activity_classes["idle"], 86_100_000)
        self.assertEqual(set(figures.projects), {_ALPHA})

    def test_declared_below_measured_warns_per_project(self) -> None:
        """The declared value of a project in a declared day that is lower than its
        measured human time warns, once for the project however many work items hold
        its entries, and also when the project has no entry (metrics.md › Declared
        values, ADR 0014)."""
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        second = _signal(_at("10:04"), "uid-second", repo_hint=_ALPHA)
        third = _signal(_at("11:00"), "uid-third", session_id="session-2",
                        repo_hint=_BETA)
        fourth = _signal(_at("11:04"), "uid-fourth", session_id="session-2",
                         repo_hint=_BETA)
        confirmation = _confirmation("uid-one", _at("18:00"), [
            _entry(_ALPHA, 30, "w1"), _entry(_ALPHA, 30)])
        figures, _ = _figures_of([first, second, third, fourth], [confirmation])
        self.assertEqual(figures.timesheet.warnings, [
            {"code": "declared_value_below_measured", "values": {"project": _ALPHA}},
            {"code": "declared_value_below_measured", "values": {"project": _BETA}},
        ])
        self.assertEqual(figures.timesheet.total, 60)
        self.assertEqual(figures.timesheet.measured_total, 600)

    def test_no_warning_when_declared_equals_shown_measured(self) -> None:
        """The comparison uses the values in whole seconds that the report shows:
        measured human time of 900.4 s shows 900, and a declared value of 900 warns
        not (metrics.md › Declared values)."""
        signal = _signal(_at("00:00"), "uid-only", repo_hint=_ALPHA)
        metrics = Metrics(
            [HumanInterval(_ms("00:00"), _ms("00:00") + 900400, signal, "signal_gap")],
            [], [], [], [])
        confirmation = _confirmation("uid-one", _at("18:00"), [_entry(_ALPHA, 900)])
        local_days = support.scenario_days()
        report = split.attribute([signal], [], [], metrics, _person(), local_days,
                                 [confirmation])
        figures = day_figures(_DAY, report, stream_of([signal]),
                              [confirmation], set(), local_days, _PARAMETERS)
        self.assertEqual(figures.timesheet.measured_total, 900)
        self.assertEqual(figures.timesheet.lines,
                         [TimesheetLine((_ALPHA, None), 900, 900, 900)])
        self.assertEqual(figures.timesheet.warnings, [])

    def test_entry_without_work_item_stays_in_project(self) -> None:
        """An entry without a work item stays in the part of the project that has no
        work item, and the ledger does not divide it among work items (metrics.md ›
        Declared values)."""
        signal = _signal(_at("10:00"), "uid-only", repo_hint=_ALPHA)
        confirmation = _confirmation("uid-one", _at("18:00"), [
            _entry(_ALPHA, 600), _entry(_ALPHA, 300, "w1")])
        figures, _ = _figures_of([signal], [confirmation])
        self.assertEqual(figures.timesheet.total, 900)
        self.assertEqual(figures.timesheet.lines, [
            TimesheetLine((_ALPHA, None), 60, 60, 600),
            TimesheetLine((_ALPHA, "w1"), 0, 0, 300),
        ])

    def test_confirmation_of_unknown_project_warns(self) -> None:
        """The project of a confirmation entry that no identity rule, no entry of the
        person configuration, and no repository identity gives warns once, and a
        project that the attribution already warned about is not warned again
        (metrics.md › Attribution, ADR 0019)."""
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        second = _signal(_at("10:04"), "uid-second")
        note = {"schema_version": events.SCHEMA_VERSION, "source": "ledger",
                "event_uid": "note-uid", "timestamp": _at("12:00"),
                "writer_version": "0.1.0", "actor": "human", "kind": "annotation",
                "machine": _MACHINE, "project": "acme/mystery",
                "start": _at("09:00"), "end": _at("12:00")}
        confirmation = _confirmation("uid-one", _at("18:00"), [
            _entry("acme/mystery", 600), _entry("acme/secret", 300)])
        entries = [first, second]
        metrics = compute_metrics(entries, [], _PARAMETERS)
        local_days = support.scenario_days()
        report = split.attribute(entries, [note], [], metrics, _person(), local_days,
                                 [confirmation])
        self.assertEqual(report.warnings,
                         [{"code": "declared_project_unknown",
                           "values": {"project": "acme/mystery"}}])
        figures = day_figures(_DAY, report, stream_of(entries),
                              [confirmation], set(), local_days, _PARAMETERS)
        self.assertEqual(figures.timesheet.warnings,
                         [{"code": "declared_project_unknown",
                           "values": {"project": "acme/secret"}}])

    def test_measured_day_total_is_union_with_manual(self) -> None:
        """On a measured day the values with manual entries add up to the total human
        time of the day, the union of measured human time and manual entries (ADR 0014,
        product.md › Phase 1, acceptance criterion 4), and every line holds no declared
        value."""
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        second = _signal(_at("10:04"), "uid-second", repo_hint=_ALPHA)
        entry = {"schema_version": events.SCHEMA_VERSION, "source": "ledger",
                 "event_uid": "entry-uid", "timestamp": _at("11:00"),
                 "writer_version": "0.1.0", "actor": "human", "kind": "manual_entry",
                 "machine": _MACHINE, "start": _at("10:02"), "end": _at("10:12"),
                 "manual_mode": "overlapping", "project": "acme/beta"}
        person = _person([ProjectName("acme/beta", "Invented Beta")])
        figures, _ = _figures_of([first, second], [], [entry], person)
        timesheet = figures.timesheet
        self.assertEqual(timesheet.state, "measured_day")
        self.assertEqual(timesheet.total, 780)
        self.assertEqual(timesheet.measured_total, 300)
        self.assertEqual(figures.person.with_manual, 780_000)
        self.assertEqual([line.bucket for line in timesheet.lines],
                         [("acme/beta", None), (_ALPHA, None)])
        self.assertEqual([(line.measured, line.with_manual, line.declared)
                          for line in timesheet.lines],
                         [(0, 600, None), (300, 180, None)])
        self.assertEqual(timesheet.warnings, [])

    def test_day_of_two_parts(self) -> None:
        """A journey to the west that crosses the start of the day gives that day two
        parts, and the day is the sum of its two parts: the figures of the window of
        both parts (metrics.md › Days and weeks)."""
        time_zones = [
            TimeZoneEntry("Europe/Rome", support.utc("1970-01-01T00:00"), 2),
            TimeZoneEntry("America/New_York", support.utc("2026-11-30T03:00"), 4),
        ]
        local_days = support.scenario_days(time_zones)
        day = date(2026, 11, 30)
        self.assertEqual(len(local_days.day_parts(day)), 2)
        first = _signal("2026-11-30T00:00:00.000Z", "uid-rome", repo_hint=_ALPHA)
        second = _signal("2026-11-30T06:00:00.000Z", "uid-york", repo_hint=_ALPHA)
        figures, _ = _figures_of([first, second], days=local_days, day=day)
        self.assertEqual(figures.timesheet.measured_total, 120)
        self.assertEqual(figures.person.with_manual, 120_000)
        self.assertEqual(figures.timesheet.lines,
                         [TimesheetLine((_ALPHA, None), 120, 120, None)])
        self.assertEqual(figures.timesheet.presence_span, 21600)

    def test_presence_span_of_the_day(self) -> None:
        """The presence span of the person is the time from the first to the last human
        signal of the day, the agent time and the human time at the idle gaps appear
        next to it, and the share of the signals of unknown invocation is shown
        (metrics.md › Uncertainty, command-line.md › Timesheet)."""
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        second = _signal(_at("11:30"), "uid-second", repo_hint=_ALPHA)
        output = _event(_at("10:01"), "uid-output", kind="agent_output", actor="system",
                        repo_hint=_ALPHA)
        later = _event(_at("11:31"), "uid-later", kind="agent_output", actor="system",
                       repo_hint=_ALPHA)
        figures, _ = _figures_of([first, output, second, later])
        timesheet = figures.timesheet
        self.assertEqual(timesheet.presence_span, 5400)
        self.assertEqual(timesheet.agent_time, 120)
        self.assertEqual(timesheet.human_time_at_idle_gaps,
                         {300: 120, 600: 120, 900: 120})
        self.assertEqual(timesheet.unknown_invocation_share, 0.0)
        self.assertEqual(timesheet.measured_total, 120)

    def test_agent_time_of_the_day_is_the_sum_over_the_agents(self) -> None:
        """The agent time of the context of the day is the agent time of the person, the sum
        over the agents: two sessions that each work from 10:00 to 10:01 give 60 + 60 = 120
        seconds, where the union of their turns is 60 (metrics.md › Agent time)."""
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        first_output = _event(_at("10:01"), "uid-first-output", kind="agent_output",
                              actor="system", repo_hint=_ALPHA)
        second = _signal(_at("10:00"), "uid-second", session_id="session-2",
                         repo_hint=_BETA)
        second_output = _event(_at("10:01"), "uid-second-output", kind="agent_output",
                               actor="system", session_id="session-2", repo_hint=_BETA)
        figures, _ = _figures_of([first, first_output, second, second_output])
        self.assertEqual(figures.timesheet.agent_time, 120)
        self.assertEqual(figures.person.agent_time, 120_000)


if __name__ == "__main__":
    unittest.main()
