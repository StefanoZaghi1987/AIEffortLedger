"""Scenario tests: the scenarios of the prototype, with values computed by hand, run on the
core (architecture.md › Tests, validation-2026-11.md › Scenarios).

The values come from `prototype/tests/test_scenarios.py`; the records are in the native
forms of the fixtures of the adapter. Minimum attention differs from the prototype on
purpose: the first signal of a chain ends no interval, so it gets minimum attention too
(metrics.md › Human time, ADR 0021, ruled 2026-11-20), and a chain of more than one signal
therefore holds 1 minute more than the prototype gives.
"""

import unittest
from collections.abc import Sequence
from datetime import date, time
from itertools import count
from typing import Any

import support
from ai_effort_ledger import declared, days, events
from ai_effort_ledger.attribution import split
from ai_effort_ledger.configuration import (
    DayStartEntry,
    PersonConfiguration,
    TimeZoneEntry,
)
from ai_effort_ledger.events import Event, format_instant, parse_instant
from ai_effort_ledger.metrics import Metrics, activity_classes, compute_metrics, stream_of
from ai_effort_ledger.metrics import intersect, total, turns, union

_TOOL_OF_SCENARIO = "claude-code"

ROME = "Europe/Rome"
# Europe/Rome is UTC+1 in winter and UTC+2 in summer; America/New_York is UTC-5 in winter.

_IDS = count(1)
_RESPONSES = count(1)


def _uuid() -> str:
    """An invented native identifier, different in every record the scenarios write."""
    return f"3f1c0000-0000-4000-8000-{next(_IDS):012x}"


def _at(day: int, hour: int, minute: int, second: int = 0) -> str:
    """The instant of a scenario, as the schema stores it: the 10th or 11th of November 2026
    at the given time. The text always carries the `Z` of UTC, so it names the given time in
    the scenario's zone only while that zone is UTC, as it is when no dated fact gives
    another; a scenario of another zone reads its instants through `local_instant` and
    `format_instant`, as the scenarios of the dated facts do."""
    return f"2026-11-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}.000Z"


def _prompt(instant: str, text: str = "Invented text that the person typed.") -> dict[str, Any]:
    """A record of the person that holds a prompt; the text is invented."""
    return support.prompt_record(text, instant, _uuid())


def _notification(instant: str) -> dict[str, Any]:
    """A record of the person whose origin names the notification of a task; the text is
    invented."""
    record = _prompt(instant, "Invented note that the invented run ended.")
    record["origin"] = {"kind": "task-notification"}
    return record


def _prompt_without_origin(instant: str, text: str) -> dict[str, Any]:
    """A record of the person of an old format that gives no `origin`; its text decides what
    the record holds (claude-code-adapter.md › Records and events)."""
    return {"type": "user", "uuid": _uuid(), "timestamp": instant,
            "version": support.VERSION, "message": {"role": "user", "content": text}}


def _meta(instant: str) -> dict[str, Any]:
    """A record of the person that the machine wrote, which the adapter skips."""
    return {"type": "user", "uuid": _uuid(), "timestamp": instant, "version": support.VERSION,
            "isMeta": True, "message": {"role": "user", "content": "Invented note."}}


def _output(instant: str) -> dict[str, Any]:
    """A record of the agent that holds a response of the model; the text is invented."""
    number = next(_RESPONSES)
    return support.output_record(f"Invented response {number} of the model.", instant,
                                 _uuid(), f"msg_scenario_{number:04d}")


def _tool_use(
    tool_name: str, call_id: str, tool_input: dict[str, Any], instant: str,
) -> dict[str, Any]:
    """A record of the agent whose content holds one use of a tool; the input is invented."""
    return support.tool_use(tool_name, call_id, tool_input, instant, _uuid(), f"msg_{call_id}")


def _tool_result(
    call_id: str, instant: str, use_result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A record of the person whose content holds the result of one use of a tool;
    `use_result` becomes the `toolUseResult` of the record, such as the identifier of the
    subagent that the result links (claude-code-adapter.md › Session fields)."""
    return support.tool_result_record(call_id, instant, _uuid(), use_result)


def _permission(call_id: str, instant: str, source: str) -> dict[str, Any]:
    """The result of one use of a tool whose permission the person or a configured rule
    decides."""
    record = _tool_result(call_id, instant)
    record["permissionDecision"] = {"source": source, "behavior": "allow"}
    return record


def _queued(instant: str) -> dict[str, Any]:
    """A message that the person typed while the agent worked; the text is invented."""
    return support.queue_record("Invented message typed while the agent worked.", instant)


def _subagent_input(instant: str) -> dict[str, Any]:
    """A record of a subagent that holds the input that the starting agent gave to it."""
    return {"type": "user", "uuid": _uuid(), "timestamp": instant, "version": support.VERSION,
            "message": {"role": "user", "content": "Invented input that the starting agent gave."}}


def _minutes(milliseconds: int | float) -> float:
    """A figure in milliseconds, in minutes, rounded to three decimals."""
    return round(milliseconds / 60000, 3)


def _parts_ms(parts: Sequence[tuple[Any, Any]]) -> list[tuple[int, int]]:
    """The UTC limits of the parts of a day, in milliseconds, the unit of a span."""
    return [(round(start.timestamp() * 1000), round(end.timestamp() * 1000))
            for start, end in parts]


def _note(instant: str, uid_value: str, **fields: Any) -> Event:
    """An annotation that a command writes: of a session when it holds `annotates`, of an
    interval when it holds `start` and `end`."""
    return {"schema_version": events.SCHEMA_VERSION, "source": "ledger",
            "event_uid": uid_value, "timestamp": instant, "writer_version": "0.1.0",
            "actor": "human", "kind": "annotation", "machine": "machine-one", **fields}


def _entry(
    start: str, end: str, uid_value: str, mode: str, instant: str, **fields: Any,
) -> Event:
    """A manual entry that a command writes, with its mode and the project it declares."""
    return {"schema_version": events.SCHEMA_VERSION, "source": "ledger",
            "event_uid": uid_value, "timestamp": instant, "writer_version": "0.1.0",
            "actor": "human", "kind": "manual_entry", "machine": "machine-one",
            "start": start, "end": end, "manual_mode": mode, **fields}


def _person() -> PersonConfiguration:
    """The person configuration of a scenario of the dated facts by default: no identity
    rule, no category rule, and no given name, so that every declared project is its own
    name and warns while nothing resolves it."""
    return PersonConfiguration(
        time_zones=[TimeZoneEntry("Etc/UTC", support.utc("1970-01-01T00:00"), 2)],
        day_starts=[DayStartEntry(time(0, 0), date(1970, 1, 1), 3)],
        projects=[], work_items=[], identity_rules=[], category_rules=[],
        preferred_remotes=["origin"], settle_time=14400, report={})


def _human_of(metrics: Metrics) -> list[tuple[int, int]]:
    """The intervals of the measured human time of a scenario, as spans."""
    return [(interval.start, interval.end) for interval in metrics.human]


def _agent_of(metrics: Metrics) -> list[tuple[int, int]]:
    """The parts of agent time of a scenario, as spans."""
    return [(part.start, part.end) for part in metrics.agent]


def _blocked_of(metrics: Metrics) -> list[tuple[int, int]]:
    """The blocked time of a scenario, as spans."""
    return [(blocked.start, blocked.end) for blocked in metrics.blocked]


def _classes(
    events: Sequence[Event], metrics: Metrics, person: days.LocalDays,
) -> dict[str, int]:
    """The activity classes of the person, over the day parts of every local day that holds
    an event of the scenario (metrics.md › Activity classes). The rest of the window, which
    the class idle holds, is not part of the hand values."""
    instants = [parse_instant(event["timestamp"]) for event in events]
    window = [part
              for day in sorted({person.local_day(instant) for instant in instants})
              for part in _parts_ms(person.day_parts(day))]
    return activity_classes(
        _human_of(metrics) + [(part.start, part.end) for part in metrics.manual],
        _agent_of(metrics), _blocked_of(metrics), window)


def _four(classes: dict[str, int]) -> dict[str, float]:
    """The four classes of the hand values, without idle, in minutes."""
    return {name: _minutes(value) for name, value in classes.items() if name != "idle"}


class ExampleMorning(unittest.TestCase):
    """09:00 prompt, 09:05 queued message, 09:20-10:00 blocked on a permission of the
    person, 10:10-10:25 foreground subagent, 10:30 last output, 10:34 prompt, 10:35 output."""

    def test_example_morning(self) -> None:
        """Human 11 min (the prototype gives 10): the 5 min of signals to 09:05, the minimum
        attention before the isolated decision at 10:00, the 4 min of the response to 10:34,
        and the minimum attention before the first signal. Agent 50 min: 35 in the first
        turn, 1 in the second, 14 in the subagent. Blocked 40 min. Person only 6, supervised
        5, unattended 45, blocked 39 minutes."""
        records = [
            _prompt(_at(10, 9, 0)),
            _output(_at(10, 9, 1)),
            _queued(_at(10, 9, 5)),
            _tool_use("Bash", "toolu_s1", {"command": "invented"}, _at(10, 9, 20)),
            _permission("toolu_s1", _at(10, 10, 0), "user_temporary"),
            _output(_at(10, 10, 5)),
            _tool_use("Agent", "toolu_s2", {"prompt": "invented"}, _at(10, 10, 10)),
            _tool_result("toolu_s2", _at(10, 10, 25), {"agentId": "a1"}),
            _output(_at(10, 10, 30)),
            _prompt(_at(10, 10, 34)),
            _output(_at(10, 10, 35)),
        ]
        subagents = {0: {"a1": [_subagent_input(_at(10, 10, 10)), _output(_at(10, 10, 24))]}}
        events, metrics, person = support.scenario([records], subagents=subagents)
        self.assertEqual(_minutes(total(_human_of(metrics))), 11)
        self.assertEqual(_minutes(sum(part.end - part.start for part in metrics.agent)), 50)
        self.assertEqual(_minutes(total(_blocked_of(metrics))), 40)
        self.assertEqual(_four(_classes(events, metrics, person)),
                         dict(person_only=6, supervised=5, unattended=45, blocked=39))
        subagent_events = [event for event in events if event.get("agent_id") == "a1"]
        self.assertTrue(all(event.get("subagent_mode") == "foreground"
                            for event in subagent_events))
        decisions = [event for event in events if event["kind"] == "decision"]
        self.assertEqual([(event["decision_type"], event["actor"]) for event in decisions],
                         [("permission", "human")])


class OvernightNotification(unittest.TestCase):
    """22:00-23:00 work, a notification of a task wakes the agent at 03:00, work to 03:30,
    next prompt 08:00."""

    def test_overnight_notification(self) -> None:
        """The idle night is no agent time and the notification is no human signal: agent 90
        min in two turns, human 2 min of two isolated prompts, unattended 90 min."""
        records = [
            _prompt(_at(10, 22, 0)),
            _output(_at(10, 22, 30)),
            _output(_at(10, 23, 0)),
            _notification(_at(11, 3, 0)),
            _output(_at(11, 3, 30)),
            _prompt(_at(11, 8, 0)),
        ]
        events, metrics, person = support.scenario([records])
        self.assertEqual(_minutes(sum(part.end - part.start for part in metrics.agent)), 90)
        self.assertEqual(_minutes(total(_human_of(metrics))), 2)
        self.assertEqual(_four(_classes(events, metrics, person)),
                         dict(person_only=2, supervised=0, unattended=90, blocked=0))


class Decisions(unittest.TestCase):
    """A permission that a configured rule answers, a permission that blocks the night, and
    a question to the person."""

    def test_rule_permission(self) -> None:
        """A permission whose source is the configuration gives no decision event and no
        request of a decision: agent 2 min, human 1 min, no blocked time."""
        records = [
            _prompt(_at(10, 10, 59)),
            _tool_use("Bash", "toolu_r1", {"command": "invented"}, _at(10, 11, 0)),
            _permission("toolu_r1", _at(10, 11, 0, 5), "config"),
            _output(_at(10, 11, 1)),
        ]
        events, metrics, person = support.scenario([records])
        self.assertFalse([event for event in events if event["kind"] == "decision"])
        self.assertFalse([event for event in events if event["kind"] == "decision_request"])
        self.assertEqual(metrics.blocked, [])
        self.assertEqual(_minutes(sum(part.end - part.start for part in metrics.agent)), 2)
        self.assertEqual(_minutes(total(_human_of(metrics))), 1)

    def test_permission_overnight(self) -> None:
        """A permission asked at 20:01 and answered at 09:00 blocks 779 min and the turn
        goes stale in between: agent 2 min, and of the blocked class 778 min, because the
        minute before the decision is person only."""
        records = [
            _prompt(_at(10, 20, 0)),
            _tool_use("Bash", "toolu_o1", {"command": "invented"}, _at(10, 20, 1)),
            _permission("toolu_o1", _at(11, 9, 0), "user_temporary"),
            _output(_at(11, 9, 1)),
        ]
        events, metrics, person = support.scenario([records])
        self.assertEqual(len([event for event in events if event["kind"] == "decision"]), 1)
        self.assertEqual(_minutes(total(_blocked_of(metrics))), 779)
        self.assertEqual(_minutes(sum(part.end - part.start for part in metrics.agent)), 2)
        self.assertEqual(_minutes(_classes(events, metrics, person)["blocked"]), 778)

    def test_question_to_the_person(self) -> None:
        """A question blocks 3 min, the agent works 2 min, and the human time is 5 min: the
        signal gap of 13:00-13:04 and the minimum attention before the prompt."""
        records = [
            _prompt(_at(10, 13, 0)),
            _tool_use("AskUserQuestion", "toolu_q1", {"questions": "invented"}, _at(10, 13, 1)),
            _tool_result("toolu_q1", _at(10, 13, 4)),
            _output(_at(10, 13, 5)),
        ]
        events, metrics, person = support.scenario([records])
        self.assertEqual(_minutes(total(_blocked_of(metrics))), 3)
        self.assertEqual(_minutes(sum(part.end - part.start for part in metrics.agent)), 2)
        self.assertEqual(_minutes(total(_human_of(metrics))), 5)


class Subagents(unittest.TestCase):
    """A subagent that runs in the background returns its result at once."""

    def test_background_subagent(self) -> None:
        """The 2 s wait for the background subagent is subtracted from the agent time, which
        is 178 s (the prototype gives 3 min, the wait being near zero)."""
        records = [
            _prompt(_at(10, 12, 0)),
            _tool_use("Agent", "toolu_b1",
                      {"prompt": "invented", "run_in_background": True}, _at(10, 12, 1)),
            _tool_result("toolu_b1", _at(10, 12, 1, 2)),
            _output(_at(10, 12, 2)),
            _notification(_at(10, 12, 30)),
            _output(_at(10, 12, 31)),
        ]
        events, metrics, person = support.scenario([records])
        self.assertEqual(sum(part.end - part.start for part in metrics.agent), 178_000)


class Parallel(unittest.TestCase):
    """Two sessions of two projects, whose signals form the one stream of the person."""

    def test_parallel_sessions_one_stream(self) -> None:
        """The stream 14:00, 14:04, 14:08, 14:12 and 15:00, 15:06 gives 12 + 6 min, and each
        first signal of a chain its minimum attention: human 20 min."""
        first = [_prompt(_at(10, 14, 0)), _prompt(_at(10, 14, 8)), _prompt(_at(10, 15, 0))]
        second = [_prompt(_at(10, 14, 4)), _prompt(_at(10, 14, 12)), _prompt(_at(10, 15, 6))]
        events, metrics, person = support.scenario([first, second])
        self.assertEqual(_minutes(total(_human_of(metrics))), 20)

    def test_alternating_sessions(self) -> None:
        """Signals that alternate between the sessions keep the person present: human 19 min
        together, and 4 min when the sessions are measured one by one."""
        first = [_prompt(_at(10, 14, 0)), _prompt(_at(10, 14, 12))]
        second = [_prompt(_at(10, 14, 6)), _prompt(_at(10, 14, 18))]
        events, metrics, person = support.scenario([first, second])
        self.assertEqual(_minutes(total(_human_of(metrics))), 19)
        folders = sorted({event["cwd"] for event in events})
        self.assertEqual(len(folders), 2)
        one_by_one = sum(
            total(_human_of(compute_metrics(
                [event for event in events if event["cwd"] == folder], [],
                support.SCENARIO_PARAMETERS)))
            for folder in folders)
        self.assertEqual(_minutes(one_by_one), 4)


class Invocation(unittest.TestCase):
    """A session that a script started."""

    def test_programmatic_session(self) -> None:
        """The prompts of a session of headless invocation are notifications of scripted
        input, not human signals: human 0, unattended 8 min."""
        records = [
            _prompt(_at(10, 2, 0)),
            _output(_at(10, 2, 5)),
            _prompt(_at(10, 2, 6)),
            _output(_at(10, 2, 9)),
        ]
        for record in records:
            record["entrypoint"] = "sdk-cli"
        events, metrics, person = support.scenario([records])
        self.assertEqual(_minutes(total(_human_of(metrics))), 0)
        self.assertEqual(_four(_classes(events, metrics, person)),
                         dict(person_only=0, supervised=0, unattended=8, blocked=0))


class Boundaries(unittest.TestCase):
    """Work that crosses midnight, a turn that goes stale, and prompts of an old format."""

    def test_midnight_split(self) -> None:
        """One hour of work from the 23:30 of the 10th divides 30 + 30 min over the two
        local days, by the parts that `LocalDays.day_parts` gives."""
        records = [_prompt(_at(10, 23, 30)), _output(_at(11, 0, 30))]
        events, metrics, person = support.scenario([records])
        instants = sorted(parse_instant(event["timestamp"]) for event in events)
        self.assertEqual([person.local_day(instant) for instant in instants],
                         [date(2026, 11, 10), date(2026, 11, 11)])
        working = union(_agent_of(metrics))
        splits = [total(intersect(working, _parts_ms(person.day_parts(day))))
                  for day in (date(2026, 11, 10), date(2026, 11, 11))]
        self.assertEqual([_minutes(split) for split in splits], [30, 30])

    def test_stale_turn(self) -> None:
        """A turn with no event from 08:01 to 13:00 ends at its last event: the turns are
        08:00-08:01 and 13:00-13:01, 2 min together."""
        records = [
            _prompt(_at(10, 8, 0)),
            _tool_use("Bash", "toolu_t1", {"command": "invented"}, _at(10, 8, 1)),
            _tool_result("toolu_t1", _at(10, 13, 0)),
            _output(_at(10, 13, 1)),
        ]
        events, metrics, person = support.scenario([records])
        found = turns(events, 14400)
        self.assertEqual([(turn.start, turn.end) for turn in found],
                         [(round(parse_instant(_at(10, 8, 0)).timestamp() * 1000),
                           round(parse_instant(_at(10, 8, 1)).timestamp() * 1000)),
                          (round(parse_instant(_at(10, 13, 0)).timestamp() * 1000),
                           round(parse_instant(_at(10, 13, 1)).timestamp() * 1000))])
        self.assertEqual(sum(turn.end - turn.start for turn in found), 120_000)

    def test_prompt_without_origin(self) -> None:
        """A record of an old format without `origin`: a text of the person is a prompt, a
        text that begins with the tag of a task notification is a notification, a text that
        begins with `<command-message>` is a prompt, and a record of the machine gives no
        event. The two prompts are the only signals: human 3 min."""
        records = [
            _prompt_without_origin(_at(10, 9, 0), "Invented text that the person typed."),
            _prompt_without_origin(_at(10, 9, 1), "<task-notification>The invented run ended."),
            _prompt_without_origin(_at(10, 9, 2),
                                   "<command-message>Invented command of the person."),
            _meta(_at(10, 9, 3)),
        ]
        events, metrics, person = support.scenario([records])
        self.assertEqual(sorted((event["timestamp"], event["kind"]) for event in events), [
            (_at(10, 9, 0), "prompt"),
            (_at(10, 9, 1), "notification"),
            (_at(10, 9, 2), "prompt"),
        ])
        self.assertFalse([event for event in events if event["timestamp"] == _at(10, 9, 3)])
        self.assertEqual(_minutes(total(_human_of(metrics))), 3)


class DatedFacts(unittest.TestCase):
    """Human time across a change of the day start hour, a day with a change of daylight
    saving, and a journey to another time zone."""

    def test_human_time_across_a_day_start_change(self) -> None:
        """With the day start at 04:00 from 2026-12-01, the signals at 01:02 and 01:08 of
        that day count for 2026-11-30: human 7 min (the 6 min of the signal gap and the
        minimum attention of the first signal)."""
        day_starts = [DayStartEntry(time(0, 0), date(1970, 1, 1), 3),
                      DayStartEntry(time(4, 0), date(2026, 12, 1), 5)]
        records = [_prompt("2026-12-01T01:02:00.000Z"), _prompt("2026-12-01T01:08:00.000Z")]
        events, metrics, person = support.scenario([records], day_starts=day_starts)
        self.assertEqual(person.local_day(parse_instant(records[0]["timestamp"])),
                         date(2026, 11, 30))
        human = union(_human_of(metrics))
        self.assertEqual(_minutes(total(human)), 7)
        self.assertEqual(_minutes(total(intersect(human, _parts_ms(person.day_parts(
            date(2026, 11, 30)))))), 7)

    def test_human_time_on_a_daylight_saving_day(self) -> None:
        """The day 2026-10-25 in Europe/Rome lasts 25 h and repeats its 02:00-03:00: the
        signals at 02:30 and 02:36 local, each at its first occurrence, count for that day:
        human 7 min (the 6 min of the signal gap and the minimum attention of the first
        signal)."""
        time_zones = [TimeZoneEntry(ROME, support.utc("1970-01-01T00:00"), 2)]
        reader = support.scenario_days(time_zones)
        records = [
            _prompt(format_instant(reader.local_instant("2026-10-25T02:30"))),
            _prompt(format_instant(reader.local_instant("2026-10-25T02:36"))),
        ]
        events, metrics, person = support.scenario([records], time_zones=time_zones)
        human = union(_human_of(metrics))
        self.assertEqual(_minutes(total(human)), 7)
        self.assertEqual(_minutes(total(intersect(human, _parts_ms(person.day_parts(
            date(2026, 10, 25)))))), 7)

    def test_human_time_across_a_journey(self) -> None:
        """The person travels from Europe/Rome to America/New_York, valid from
        2026-12-01T03:00Z: the 04:00Z of 12-01 is the 23:00 of 11-30, so the signal and the
        work after it count for 2026-11-30, and human is 1 min (the minimum attention of the
        isolated signal)."""
        time_zones = [TimeZoneEntry(ROME, support.utc("1970-01-01T00:00"), 2),
                      TimeZoneEntry("America/New_York", support.utc("2026-12-01T03:00"), 4)]
        records = [_prompt("2026-12-01T04:00:00.000Z"), _output("2026-12-01T04:10:00.000Z")]
        events, metrics, person = support.scenario([records], time_zones=time_zones)
        self.assertEqual(person.local_day(parse_instant(records[0]["timestamp"])),
                         date(2026, 11, 30))
        human = union(_human_of(metrics))
        self.assertEqual(_minutes(total(human)), 1)
        self.assertEqual(_minutes(total(intersect(human, _parts_ms(person.day_parts(
            date(2026, 11, 30)))))), 1)
        self.assertEqual(_minutes(total(intersect(human, _parts_ms(person.day_parts(
            date(2026, 12, 1)))))), 0)


class AttributionScenario(unittest.TestCase):
    """Two parallel sessions of two projects that the one stream of the person and the
    split rule divide, with annotations that overlap, a manual entry of each mode, and a
    manual entry across the end of the report period (metrics.md › Attribution, ADR 0021).

    The signals alternate 14:00, 14:04, 14:08, 14:12 between the sessions, each session
    holds one output, and the annotations name the sessions `acme/alpha` and `acme/beta`;
    two annotations of intervals overlap over the prompt at 14:08, and the later one wins,
    so that it moves the human time of that prompt to `acme/beta` with its work item.
    """

    def test_project_figures_of_two_sessions(self) -> None:
        """The split gives `acme/alpha` the minimum attention before 14:00 and the interval
        14:04-14:08, whose prompt the later annotation names, and `acme/beta` the intervals
        14:00-14:04 and 14:08-14:12: alpha holds 1 min of human time and 2 min of agent
        time, beta 12 min and 2 min, and the project figures are unions, so the classes of
        beta hold supervised time where no bucket of it holds any. The entry of mode
        `overlapping` adds its 10 min inside the day of `acme/beta`, the entry of mode
        `additional` its 10 min to `acme/alpha`; the classes of each rest on its human
        time with the entries, so the class person only of alpha holds the minute and the
        10 min, and that of the project beta its 12 min and the 10 min of the crossing
        entry, beside 2 min supervised. The project of an annotation that nothing resolves
        warns once per identifier."""
        first = [
            _prompt(_at(10, 14, 0)),
            _output(_at(10, 14, 2)),
            _prompt(_at(10, 14, 8)),
        ]
        second = [
            _prompt(_at(10, 14, 4)),
            _output(_at(10, 14, 6)),
            _prompt(_at(10, 14, 12)),
        ]
        alpha, beta, gamma = "acme/alpha", "acme/beta", "acme/gamma"
        notes = [
            _note(_at(10, 15, 0), "note-alpha",
                  annotates={"tool": _TOOL_OF_SCENARIO, "session_id": "session-0"},
                  project=alpha),
            _note(_at(10, 15, 1), "note-beta",
                  annotates={"tool": _TOOL_OF_SCENARIO, "session_id": "session-1"},
                  project=beta),
            _note(_at(10, 15, 2), "note-gamma", start=_at(10, 14, 7),
                  end=_at(10, 14, 11), project=gamma),
            _note(_at(10, 15, 3), "note-delta", start=_at(10, 14, 8),
                  end=_at(10, 14, 10), project=beta, work_item="invented-2"),
        ]
        entries = [
            _entry(_at(10, 23, 50), _at(11, 0, 10), "entry-crossing", "overlapping",
                   _at(10, 20, 0), project=beta),
            _entry(_at(10, 16, 0), _at(10, 16, 10), "entry-apart", "additional",
                   _at(10, 20, 1), project=alpha),
        ]
        read, metrics, person = support.scenario([first, second], annotations=notes,
                                                 manual_entries=entries)
        session_events = [event for event in read if event["source"] != "ledger"]
        report = split.attribute(session_events, notes, entries, metrics, _person(),
                                 support.scenario_days())
        window = _parts_ms(person.day_parts(date(2026, 11, 10)))
        self.assertEqual(report.names, {alpha: alpha, beta: beta})
        self.assertEqual(report.warnings, [
            {"code": "declared_project_unknown", "values": {"project": alpha}},
            {"code": "declared_project_unknown", "values": {"project": beta}},
            {"code": "declared_project_unknown", "values": {"project": gamma}},
        ])
        figures = report.figures(window)
        self.assertEqual(figures[(alpha, None)].human_time, 60_000)
        self.assertEqual(figures[(alpha, None)].agent_time, 120_000)
        self.assertEqual(figures[(alpha, None)].with_manual, 660_000)
        self.assertEqual(figures[(alpha, None)].activity_classes,
                         {"person_only": 660_000, "supervised": 0, "unattended": 120_000,
                          "blocked": 0})
        self.assertEqual(figures[(beta, None)].human_time, 480_000)
        self.assertEqual(figures[(beta, None)].agent_time, 120_000)
        self.assertEqual(figures[(beta, None)].with_manual, 1_080_000)
        self.assertEqual(figures[(beta, "invented-2")].human_time, 240_000)
        projects = report.project_figures(window)
        self.assertEqual(set(projects), {alpha, beta})
        self.assertEqual(projects[alpha].human_time, 60_000)
        self.assertEqual(projects[alpha].with_manual, 660_000)
        self.assertEqual(projects[beta].human_time, 720_000)
        self.assertEqual(projects[beta].with_manual, 1_320_000)
        self.assertEqual(projects[beta].activity_classes,
                         {"person_only": 1_200_000, "supervised": 120_000,
                          "unattended": 0, "blocked": 0})
        parts = report.session_parts(window)
        self.assertEqual(parts, {
            (_TOOL_OF_SCENARIO, "session-0"): {(alpha, None): (60_000, 120_000),
                                               (beta, "invented-2"): (240_000, 0)},
            (_TOOL_OF_SCENARIO, "session-1"): {(beta, None): (480_000, 120_000)},
        })

    def test_day_figures_of_two_sessions(self) -> None:
        """The figures of the day that `reports` reads: the day of the two sessions is
        measured, its total is the union of the measured human time and the manual
        entries, 33 min, its measured total 13 min, the lines hold the measured time of
        each bucket after the split rule, the person holds the unions over every bucket
        with the class idle, and the agent time and the presence span appear as
        context (metrics.md › Declared values, ADR 0014)."""
        first = [
            _prompt(_at(10, 14, 0)),
            _output(_at(10, 14, 2)),
            _prompt(_at(10, 14, 8)),
        ]
        second = [
            _prompt(_at(10, 14, 4)),
            _output(_at(10, 14, 6)),
            _prompt(_at(10, 14, 12)),
        ]
        alpha, beta, gamma = "acme/alpha", "acme/beta", "acme/gamma"
        notes = [
            _note(_at(10, 15, 0), "note-alpha",
                  annotates={"tool": _TOOL_OF_SCENARIO, "session_id": "session-0"},
                  project=alpha),
            _note(_at(10, 15, 1), "note-beta",
                  annotates={"tool": _TOOL_OF_SCENARIO, "session_id": "session-1"},
                  project=beta),
            _note(_at(10, 15, 2), "note-gamma", start=_at(10, 14, 7),
                  end=_at(10, 14, 11), project=gamma),
            _note(_at(10, 15, 3), "note-delta", start=_at(10, 14, 8),
                  end=_at(10, 14, 10), project=beta, work_item="invented-2"),
        ]
        entries = [
            _entry(_at(10, 23, 50), _at(11, 0, 10), "entry-crossing", "overlapping",
                   _at(10, 20, 0), project=beta),
            _entry(_at(10, 16, 0), _at(10, 16, 10), "entry-apart", "additional",
                   _at(10, 20, 1), project=alpha),
        ]
        read, metrics, local_days = support.scenario([first, second], annotations=notes,
                                                     manual_entries=entries)
        session_events = [event for event in read if event["source"] != "ledger"]
        report = split.attribute(session_events, notes, entries, metrics, _person(),
                                 local_days)
        figures = declared.day_figures(date(2026, 11, 10), report,
                                       stream_of(session_events), [], set(),
                                       local_days, support.SCENARIO_PARAMETERS)
        timesheet = figures.timesheet
        self.assertEqual(timesheet.day, date(2026, 11, 10))
        self.assertEqual(timesheet.state, "measured_day")
        self.assertEqual(timesheet.total, 1980)
        self.assertEqual(timesheet.measured_total, 780)
        self.assertEqual([(line.bucket, line.measured, line.with_manual, line.declared)
                          for line in timesheet.lines], [
            ((beta, None), 480, 1080, None),
            ((alpha, None), 60, 660, None),
            ((beta, "invented-2"), 240, 240, None),
        ])
        self.assertEqual(timesheet.human_time_at_idle_gaps,
                         {300: 780, 600: 780, 900: 780})
        self.assertEqual(timesheet.unknown_invocation_share, 1.0)
        # The records of the scenario name no entrypoint, so the adapter gives every
        # session the invocation unknown (event-schema.md › Fields).
        self.assertEqual(timesheet.agent_time, 240)
        self.assertEqual(timesheet.presence_span, 720)
        self.assertEqual(timesheet.warnings, [])
        self.assertEqual(figures.buckets[(alpha, None)].human_time, 60_000)
        self.assertEqual(figures.buckets[(alpha, None)].with_manual, 660_000)
        self.assertEqual(figures.buckets[(beta, "invented-2")].human_time, 240_000)
        self.assertEqual(set(figures.projects), {alpha, beta})
        self.assertEqual(figures.projects[beta].with_manual, 1_320_000)
        self.assertEqual(figures.person.human_time, 780_000)
        self.assertEqual(figures.person.with_manual, 1_980_000)
        self.assertEqual(figures.person.agent_time, 240_000)
        self.assertEqual(figures.person.blocked_time, 0)
        self.assertEqual(figures.person.activity_classes,
                         {"person_only": 1_740_000, "supervised": 240_000,
                          "unattended": 0, "blocked": 0, "idle": 84_420_000})
        self.assertEqual(figures.person.inferred_human_share, 0.0)
        self.assertEqual(figures.person.inferred_agent_share, 0.0)


def _attributed_two_sessions() -> tuple[split.Attribution, days.LocalDays]:
    """The attribution of the scenario of the two sessions of two projects, with the
    annotations that name the sessions and the intervals and a manual entry of each
    mode, the same records that the tests of the attribution compute figures for."""
    first = [
        _prompt(_at(10, 14, 0)),
        _output(_at(10, 14, 2)),
        _prompt(_at(10, 14, 8)),
    ]
    second = [
        _prompt(_at(10, 14, 4)),
        _output(_at(10, 14, 6)),
        _prompt(_at(10, 14, 12)),
    ]
    alpha, beta, gamma = "acme/alpha", "acme/beta", "acme/gamma"
    notes = [
        _note(_at(10, 15, 0), "note-alpha",
              annotates={"tool": _TOOL_OF_SCENARIO, "session_id": "session-0"},
              project=alpha),
        _note(_at(10, 15, 1), "note-beta",
              annotates={"tool": _TOOL_OF_SCENARIO, "session_id": "session-1"},
              project=beta),
        _note(_at(10, 15, 2), "note-gamma", start=_at(10, 14, 7),
              end=_at(10, 14, 11), project=gamma),
        _note(_at(10, 15, 3), "note-delta", start=_at(10, 14, 8),
              end=_at(10, 14, 10), project=beta, work_item="invented-2"),
    ]
    entries = [
        _entry(_at(10, 23, 50), _at(11, 0, 10), "entry-crossing", "overlapping",
               _at(10, 20, 0), project=beta),
        _entry(_at(10, 16, 0), _at(10, 16, 10), "entry-apart", "additional",
               _at(10, 20, 1), project=alpha),
    ]
    read, metrics, local_days = support.scenario([first, second], annotations=notes,
                                                 manual_entries=entries)
    session_events = [event for event in read if event["source"] != "ledger"]
    report = split.attribute(session_events, notes, entries, metrics, _person(),
                             local_days)
    return report, local_days


def _shown_with_manual(
    report: split.Attribution, local_days: days.LocalDays
) -> dict[declared.Bucket, int]:
    """The measured human time with manual entries of each bucket of the day of the two
    sessions, in the whole seconds that the report shows (decision D12)."""
    window = _parts_ms(local_days.day_parts(date(2026, 11, 10)))
    with_manual = {bucket: held.with_manual
                   for bucket, held in report.figures(window).items()}
    return declared.whole_seconds(with_manual, with_manual)


class ProposalScenario(unittest.TestCase):
    """The timesheet proposal of the day of the two sessions, computed from the
    `with_manual` figures that `attribute` gives (metrics.md › Declared values)."""

    def test_timesheet_proposal(self) -> None:
        """Without a total, each entry is its value rounded up to the granularity of
        15 min: the 11 min of `acme/alpha` propose 15 min, the 18 min of `acme/beta`
        propose 30 min, and the 4 min of the work item propose one unit, 15 min."""
        report, local_days = _attributed_two_sessions()
        shown = _shown_with_manual(report, local_days)
        self.assertEqual(shown, {("acme/alpha", None): 660, ("acme/beta", None): 1080,
                                 ("acme/beta", "invented-2"): 240})
        self.assertEqual(declared.proposal(shown, 900), {
            ("acme/alpha", None): 900,
            ("acme/beta", None): 1800,
            ("acme/beta", "invented-2"): 900,
        })

    def test_division_of_a_given_total(self) -> None:
        """With a total of 90 min and the value of the work item given at its proposed
        15 min, the rest of 75 min divides by the shares of the two projects, 11 min
        and 18 min, in units of 15 min: `acme/alpha` takes 2 units and `acme/beta`
        3, so that the entries add up to the total."""
        report, local_days = _attributed_two_sessions()
        shown = _shown_with_manual(report, local_days)
        proposed = declared.proposal(shown, 900, 5400,
                                     {("acme/beta", "invented-2"): 900})
        self.assertEqual(proposed, {
            ("acme/alpha", None): 1800,
            ("acme/beta", None): 2700,
            ("acme/beta", "invented-2"): 900,
        })


if __name__ == "__main__":
    unittest.main()
