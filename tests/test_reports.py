"""Tests of the reports: the report record, the JSON documents of the commands, and the
frozen reports with their differences (command-line.md › JSON documents, › Frozen
reports, architecture.md › Report record, metrics.md › Reproducibility, › Uncertainty,
acceptance criterion 4)."""

import json
import unittest
from datetime import date, time
from pathlib import Path
from unittest import mock

import support
from ai_effort_ledger import reports, store
from ai_effort_ledger.reports import text
from ai_effort_ledger.configuration import (
    CategoryRule,
    DayStartEntry,
    IdentityRule,
    PersonConfiguration,
    ProjectName,
    ReportParameters,
    TimeZoneEntry,
    WorkItemName,
)
from ai_effort_ledger.declared import (
    UNATTRIBUTED,
    Bucket,
    BucketFigures,
    DayFigures,
    DayTimesheet,
    TimesheetLine,
)
from ai_effort_ledger.events import Event
from ai_effort_ledger.index import BrokenLine, SegmentState
from ai_effort_ledger.language import label, message, note
from ai_effort_ledger.selection import Selection
from ai_effort_ledger.store.files import FrozenOtherMachine, TargetNotFound

_DAY = date(2026, 6, 15)
_NEXT = date(2026, 6, 16)
_MACHINE = "3f0d5a1e-8c2b-4d6e-9f0a-1b2c3d4e5f60"
_OTHER_MACHINE = "9999b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"
"""A second machine of the tests, whose store metadata holds no machine label."""
_LABEL = "Invented laptop"
"""The machine label of `_MACHINE` in the tests whose store holds one."""
_SEGMENT = f"segments/{_MACHINE}/2026-06.jsonl"
"""The invented segment path that the state of the store of the tests holds."""
_ALPHA = "example.org/team/alpha"
_BETA = "example.org/team/beta"
_ITEM = "142"
_ITEM_NAME = "Feature 142"

_CONFLICT = {
    "code": "identity_rule_conflict",
    "values": {
        "event": {"source": "ledger", "event_uid": "uid-conflict"},
        "first": _ALPHA,
        "second": _BETA,
    },
}
"""A configuration error whose values hold the event key as a nested object (ruling of
2026-11-20): the record carries the values as produced."""


def _person() -> PersonConfiguration:
    """A person configuration with one entry of each kind and invented values."""
    return PersonConfiguration(
        time_zones=[TimeZoneEntry("Etc/UTC", support.utc("2026-01-01T00:00"), 2)],
        day_starts=[DayStartEntry(time(8, 30), date(2026, 6, 1), 5)],
        projects=[ProjectName(_ALPHA, "Alpha")],
        work_items=[WorkItemName(_ALPHA, _ITEM, _ITEM_NAME)],
        identity_rules=[IdentityRule(_ALPHA, _ALPHA, "D:\\Work\\Product\\alpha", "main",
                                     date(2026, 6, 1), date(2026, 6, 30), 7)],
        category_rules=[CategoryRule("example_tool", "edit", 9)],
        preferred_remotes=["origin"],
        settle_time=14400,
        report={},
    )


def _selection() -> Selection:
    """A selection whose state of the store holds one segment and one broken line."""
    return Selection(
        first=_DAY,
        last=_NEXT,
        session_events=[],
        confirmations=[],
        manual_entries=[],
        annotations=[],
        retractions=[],
        cancelled=set(),
        segments=[SegmentState(_SEGMENT, 1024, "ab12cd34")],
        broken=[BrokenLine(_SEGMENT, 3)],
        newer=False,
        warnings=[],
    )


def _names() -> reports.Names:
    """The names of the projects and work items of the tests."""
    return reports.Names(
        projects={_ALPHA: "Alpha", _BETA: "Beta"},
        work_items={(_ALPHA, _ITEM): _ITEM_NAME},
    )


def _figures(human: int = 0, agent: int = 0, blocked: int = 0,
             classes: dict[str, int] | None = None, inferred_human: float = 0.0,
             inferred_agent: float = 0.0) -> BucketFigures:
    """Figures of one bucket in milliseconds, the with-manual time equal to the human and,
    without other classes, the human time all person only, beside the agent time
    (metrics.md › Activity classes)."""
    return BucketFigures(human, human, agent, blocked,
                         {"person_only": human} if classes is None else classes,
                         inferred_human, inferred_agent)


def _sheet(day: date, state: str, declared: tuple[int, int, int] | None,
           idle_gaps: dict[int, int] | None) -> DayTimesheet:
    """The timesheet of one day of the tests: three lines, for the work item, for the
    project without a work item, and for the unattributed time, in whole seconds, that
    add up to the totals (acceptance criterion 4)."""
    measured = (3600, 3400, 0)
    with_manual = (4000, 3000, 200)
    given = declared if declared is not None else (None, None, None)
    lines = [TimesheetLine(bucket, measured[position], with_manual[position], given[position])
             for position, bucket in enumerate(
                 ((_ALPHA, _ITEM), (_ALPHA, None), UNATTRIBUTED))]
    return DayTimesheet(day, state, 7200, 7000, lines, idle_gaps, 0.25, 5200, 28000, [])


def _day_figures(day: date, state: str, declared: tuple[int, int, int] | None,
                 idle_gaps: dict[int, int] | None) -> DayFigures:
    """The figures of one day of the tests: its timesheet, the person, the projects with
    the unattributed time, and the buckets, in milliseconds. The person holds its five
    classes: person only all of its human time, unattended its agent time, blocked its
    blocked time, and idle the rest of the day, so that the five add up to the
    86 400 000 ms of the day (metrics.md › Activity classes)."""
    return DayFigures(
        _sheet(day, state, declared, idle_gaps),
        _figures(human=7200123, agent=5200499, blocked=1000500,
                 classes={"person_only": 7200123, "supervised": 0, "unattended": 5200499,
                          "blocked": 1000500, "idle": 72998878},
                 inferred_human=0.5, inferred_agent=0.25),
        {_ALPHA: _figures(human=7000123, agent=5000000, blocked=1000500,
                          inferred_human=0.5, inferred_agent=0.25),
         None: _figures(human=200000)},
        {(_ALPHA, _ITEM): _figures(human=3600123, agent=3800000, inferred_human=0.5,
                                   inferred_agent=0.25),
         (_ALPHA, None): _figures(human=3400000, agent=1200000),
         UNATTRIBUTED: _figures(human=200000)},
    )


def _measured() -> DayFigures:
    """The figures of a measured day of the tests, with its idle gaps."""
    return _day_figures(_DAY, "measured_day", None,
                        {300: 6900, 600: 6600, 900: 6300})


def _declared() -> DayFigures:
    """The figures of a declared day of the tests, without idle gaps."""
    return _day_figures(_NEXT, "declared_day", (5400, 1800, 0), None)


def _day_with_manual_entries(state: str) -> DayFigures:
    """The figures of one day of the tests whose buckets hold two manual entries in mode
    `additional`, each over no measured human time: one of an hour on the work item of
    Alpha and one of half an hour without a project. The measured human time is one
    minute on the work item and one minute on Beta, and the agent time 20 minutes on the
    work item; the human time with manual entries is 61 minutes, one minute, and 30
    minutes, so the person holds 92 minutes and the lines of the timesheet the same total
    (metrics.md › Declared values). The activity classes of the person and of each bucket
    come from that human time with manual entries: the class person only of each is all
    of it, beside the 20 minutes of unattended agent time of the work item (metrics.md ›
    Activity classes). On a declared day the entry of the timesheet of the work item
    declares 90 minutes."""
    item = BucketFigures(60_000, 3_660_000, 1_200_000, 0,
                         {"person_only": 3_660_000, "unattended": 1_200_000}, 0.5, 0.25)
    beta = BucketFigures(60_000, 60_000, 0, 0, {"person_only": 60_000}, 0.0, 0.0)
    unattributed = BucketFigures(0, 1_800_000, 0, 0, {"person_only": 1_800_000}, 0.0, 0.0)
    person = BucketFigures(120_000, 5_520_000, 1_200_000, 0,
                           {"person_only": 5_520_000, "supervised": 0, "unattended": 1_200_000,
                            "blocked": 0, "idle": 79_680_000}, 0.0, 0.0)
    declared = state == "declared_day"
    lines = [TimesheetLine(bucket, measured, with_manual, given)
             for bucket, measured, with_manual, given in (
                 ((_ALPHA, _ITEM), 60, 3660, 5400 if declared else None),
                 ((_BETA, None), 60, 60, None),
                 (UNATTRIBUTED, 0, 1800, None))]
    sheet = DayTimesheet(_DAY, state, 5400 if declared else 5520, 120, lines,
                         None if declared else {300: 5500, 600: 5480, 900: 5460},
                         0.25, 1200, 7260, [])
    buckets = {(_ALPHA, _ITEM): item, (_BETA, None): beta, UNATTRIBUTED: unattributed}
    return DayFigures(sheet, person, {_ALPHA: item, _BETA: beta, None: unattributed},
                      buckets)


def _day_of_milliseconds() -> DayFigures:
    """The figures of one measured day of the tests whose instants are not at whole
    seconds, the classes of every holder on its human time with manual entries: the person
    is present 1500.5 s — 400.4 s of person only and 1100.1 s supervised — beside 800.8 s
    of unattended agent time, 100.9 s of blocked time, and the rest of the day idle, and
    its agents work 2100.6 s. Alpha, in the work item of the tests, is present 1201.2 s,
    as much person only as supervised, and its agent works 1500.5 s, 300.3 s of them
    unattended. Beta holds no measured human time: a manual entry gives it 1099.5 s, all
    person only, beside 700.7 s of unattended agent time and 1400.6 s of blocked time
    (metrics.md › Activity classes). The human time at its idle gaps is 1100 s at 300 s,
    1000 s at 600 s, and 900 s at 900 s (command-line.md › Reports)."""
    person = BucketFigures(
        1_500_500, 1_500_500, 2_100_600, 100_900,
        {"person_only": 400_400, "supervised": 1_100_100, "unattended": 800_800,
         "blocked": 100_900, "idle": 83_997_800}, 0.0, 0.0)
    alpha = BucketFigures(
        1_201_200, 1_201_200, 1_500_500, 0,
        {"person_only": 600_600, "supervised": 600_600, "unattended": 300_300,
         "blocked": 0}, 0.5, 0.25)
    beta = BucketFigures(
        0, 1_099_500, 700_700, 1_400_600,
        {"person_only": 1_099_500, "supervised": 0, "unattended": 700_700,
         "blocked": 1_400_600}, 0.0, 0.0)
    lines = [TimesheetLine((_ALPHA, _ITEM), 1201, 1201, None),
             TimesheetLine((_BETA, None), 0, 1100, None)]
    sheet = DayTimesheet(_DAY, "measured_day", 2301, 1201, lines,
                         {300: 1100, 600: 1000, 900: 900}, 0.25, 2101, 28_000, [])
    return DayFigures(sheet, person, {_ALPHA: alpha, _BETA: beta},
                      {(_ALPHA, _ITEM): alpha, (_BETA, None): beta})


def _parallel_day() -> DayFigures:
    """The figures of one measured day of the tests whose two agents of Alpha work in
    parallel, as the figures of the core hold them (metrics.md › Agent time): the person
    holds 1 800 000 ms of agent time over the union of the agent intervals behind it,
    600 000 ms supervised and 600 000 ms unattended, so its parallel ratio is 1.5; Alpha
    holds 1 200 000 ms over 800 000 ms unattended — its two agents overlap —, so its
    ratio is 1.5 and the ratio of its work item the same; Beta holds 600 000 ms over
    600 000 ms, ratio 1.0; the unattributed time holds no agent time and no ratio. The
    human time of the person is 660 s, Alpha 60 and Beta 600, the presence span 600 s,
    and the agent time of the day 1800 s."""
    person = BucketFigures(660_000, 660_000, 1_800_000, 0,
                           {"person_only": 60_000, "supervised": 600_000,
                            "unattended": 600_000, "blocked": 0, "idle": 85_140_000},
                           0.0, 0.0)
    alpha = BucketFigures(60_000, 60_000, 1_200_000, 0,
                          {"person_only": 60_000, "unattended": 800_000}, 0.0, 0.0)
    beta = BucketFigures(600_000, 600_000, 600_000, 0,
                         {"person_only": 600_000, "unattended": 600_000}, 0.0, 0.0)
    unattributed = BucketFigures(0, 0, 0, 0, {"person_only": 0}, 0.0, 0.0)
    lines = [TimesheetLine((_ALPHA, _ITEM), 60, 60, None),
             TimesheetLine((_BETA, None), 600, 600, None),
             TimesheetLine(UNATTRIBUTED, 0, 0, None)]
    sheet = DayTimesheet(_DAY, "measured_day", 660, 660, lines,
                         {300: 120, 600: 660, 900: 660}, 0.0, 1800, 600, [])
    return DayFigures(sheet, person, {_ALPHA: alpha, _BETA: beta, None: unattributed},
                      {(_ALPHA, _ITEM): alpha, (_BETA, None): beta,
                       UNATTRIBUTED: unattributed})


def _event(event_uid: str, extra: dict[str, object]) -> Event:
    """One manual entry event of the tests with the fields that every event holds."""
    return {
        "schema_version": 1,
        "source": "ledger",
        "event_uid": event_uid,
        "timestamp": "2026-06-15T09:00:00.000Z",
        "ingested_at": "2026-06-15T09:00:05.000Z",
        "writer_version": "0.1.0",
        "actor": "human",
        "kind": "manual_entry",
        "machine": _MACHINE,
        **extra,
    }


def _record(person: PersonConfiguration | None = None, idle_gap: int = 600) -> dict:
    """The report record of the tests, with the person and the idle gap that it uses."""
    return reports.report_record(
        ReportParameters(idle_gap=idle_gap, stale_limit=7200, headless_prompts=True,
                         timesheet_granularity=1800, language="en"),
        person if person is not None else _person(),
        _selection(),
        [],
        "0.1.0",
        "2026a",
    )


def _person_with_beta() -> PersonConfiguration:
    """The person of the tests with the identity rule of Beta that the person added after
    the freeze."""
    return _person()._replace(identity_rules=[
        *_person().identity_rules,
        IdentityRule(_BETA, _BETA, "D:\\Work\\Product\\beta", "main", date(2026, 6, 15),
                     date(2026, 6, 16), 8),
    ])


def _timesheet_report(record: dict, days: list[DayFigures] | None = None) -> dict:
    """The JSON document of `report timesheet` over the days of the tests, with the
    record given."""
    return {
        "command": "report timesheet",
        "warnings": [],
        "configuration_errors": [],
        "record": record,
        "days": reports.timesheet_document(
            days if days is not None else [_measured(), _declared()], _names())["days"],
    }


def _day_report(record: dict) -> dict:
    """The JSON document of `report day` for the measured day of the tests, with the
    record given."""
    return {
        "command": "report day",
        "warnings": [],
        "configuration_errors": [],
        "record": record,
        **reports.day_document(_measured(), _names()),
    }


def _measured_with_beta() -> DayFigures:
    """The figures of the measured day after the identity rule of Beta: one hundred and
    twenty seconds of the human time with manual entries moved from the unattributed time
    to Beta, so that the totals of the day stay as they were."""
    measured = _measured()
    sheet = measured.timesheet
    lines = [*sheet.lines[:2], TimesheetLine(UNATTRIBUTED, 0, 80, None),
             TimesheetLine((_BETA, None), 0, 120, None)]
    return measured._replace(
        timesheet=sheet._replace(lines=lines),
        projects={**measured.projects, _BETA: _figures(human=120000)},
    )


def _frozen_timesheet(frozen_id: str, day_texts: list[str]) -> dict:
    """The document of one frozen report of the tests: a timesheet of the days named."""
    return {"command": "report timesheet", "frozen_id": frozen_id,
            "days": [{"day": text} for text in day_texts]}


def _envelope(document: dict, frozen_at: str) -> dict:
    """The envelope of one frozen report of the tests, as the store keeps the file."""
    return {"document": document, "frozen_at": frozen_at}


class ReportRecordTests(unittest.TestCase):
    """The report record (architecture.md › Report record, metrics.md ›
    Reproducibility): the versions, the parameters, the rules, the dated facts, the
    configuration errors, and the state of the store that a report used."""

    def test_record_holds_versions_parameters_rules_facts_segments(self) -> None:
        """The record holds one key for each fact of the report record and no other key;
        a configuration error is carried as produced, its values unchanged."""
        record = reports.report_record(
            ReportParameters(idle_gap=300, stale_limit=7200, headless_prompts=True,
                             timesheet_granularity=1800, language="it"),
            _person(),
            _selection(),
            [_CONFLICT],
            "0.1.0",
            "2026a",
        )
        self.assertEqual(set(record), {
            "ledger", "tzdata", "parameters", "identity_rules", "category_rules",
            "dated_facts", "configuration_errors", "segments", "broken_lines"})
        self.assertEqual(record["ledger"], "0.1.0")
        self.assertEqual(record["tzdata"], "2026a")
        self.assertEqual(record["parameters"], {
            "idle_gap": 300, "minimum_attention": 60, "stale_limit": 7200,
            "headless_prompts": True, "timesheet_granularity": 1800, "language": "it"})
        self.assertEqual(record["identity_rules"], [{
            "project": _ALPHA, "repository": _ALPHA, "folder": "D:\\Work\\Product\\alpha",
            "branch": "main", "from": "2026-06-01", "to": "2026-06-30"}])
        self.assertEqual(record["category_rules"], [
            {"tool": "example_tool", "category": "edit"}])
        self.assertEqual(record["dated_facts"], {
            "time_zones": [{"zone": "Etc/UTC", "from": "2026-01-01T00:00:00.000Z"}],
            "day_starts": [{"hour": "08:30", "from": "2026-06-01"}]})
        self.assertEqual(record["configuration_errors"], [_CONFLICT])
        self.assertEqual(record["segments"], [
            {"segment": _SEGMENT, "size": 1024, "chained_hash": "ab12cd34"}])
        self.assertEqual(record["broken_lines"], [{"segment": _SEGMENT, "line": 3}])


class TimesheetDocumentTests(unittest.TestCase):
    """The JSON document of `report timesheet` (command-line.md › JSON documents)."""

    def test_timesheet_keys(self) -> None:
        """Each day holds its keys, the idle gaps of a measured day only, as text keys in
        seconds, and no other key; each entry holds its keys and no other key."""
        document = reports.timesheet_document([_measured(), _declared()], _names())
        self.assertEqual(list(document), ["days"])
        measured, declared = document["days"]
        self.assertEqual(set(measured), {
            "day", "state", "total", "measured_total", "human_time_at_idle_gaps",
            "unknown_invocation_share", "entries"})
        self.assertEqual(set(declared), {
            "day", "state", "total", "measured_total", "unknown_invocation_share",
            "entries"})
        self.assertEqual(measured["day"], "2026-06-15")
        self.assertEqual(declared["day"], "2026-06-16")
        self.assertEqual(measured["state"], "measured_day")
        self.assertEqual(declared["state"], "declared_day")
        self.assertEqual(measured["total"], 7200)
        self.assertEqual(measured["measured_total"], 7000)
        self.assertEqual(measured["human_time_at_idle_gaps"],
                         {"300": 6900, "600": 6600, "900": 6300})
        self.assertEqual(measured["unknown_invocation_share"], 0.25)
        self.assertEqual(declared["unknown_invocation_share"], 0.25)
        self.assertEqual([set(entry) for entry in measured["entries"]], [{
            "project", "work_item", "measured", "with_manual_entries", "declared",
            "inferred_human_share", "inferred_agent_share"}] * 3)
        first = measured["entries"][0]
        self.assertEqual(first["project"], {"id": _ALPHA, "name": "Alpha"})
        self.assertEqual(first["work_item"], {"id": _ITEM, "name": _ITEM_NAME})
        self.assertEqual(first["measured"], 3600)
        self.assertEqual(first["with_manual_entries"], 4000)
        self.assertIsNone(first["declared"])
        self.assertEqual(first["inferred_human_share"], 0.5)
        self.assertEqual(first["inferred_agent_share"], 0.25)
        self.assertEqual(declared["entries"][0]["declared"], 5400)

    def test_unattributed_is_null(self) -> None:
        """The entry of the unattributed time holds no project and no work item; a
        project without a work item holds a null work item."""
        document = reports.timesheet_document([_measured()], _names())
        last = document["days"][0]["entries"][-1]
        self.assertIsNone(last["project"])
        self.assertIsNone(last["work_item"])
        middle = document["days"][0]["entries"][1]
        self.assertEqual(middle["project"], {"id": _ALPHA, "name": "Alpha"})
        self.assertIsNone(middle["work_item"])

    def test_parts_add_up_in_json(self) -> None:
        """In the document as JSON, the measured parts add up to the measured total; the
        parts with manual entries add up to the total of a measured day and the declared
        parts to the total of a declared day (acceptance criterion 4)."""
        document = reports.timesheet_document([_measured(), _declared()], _names())
        written = json.loads(json.dumps(document))
        measured, declared = written["days"]
        self.assertEqual(sum(entry["measured"] for entry in measured["entries"]),
                         measured["measured_total"])
        self.assertEqual(sum(entry["with_manual_entries"] for entry in measured["entries"]),
                         measured["total"])
        self.assertEqual(sum(entry["declared"] for entry in declared["entries"]),
                         declared["total"])

    def test_durations_are_whole_seconds(self) -> None:
        """Every duration of every document is a whole number of seconds: the figures of
        the person, of the projects, and of the work items are rounded to the nearest
        second (decision D12)."""
        documents = [
            reports.timesheet_document([_measured(), _declared()], _names()),
            reports.day_document(_measured(), _names()),
            reports.day_document(_declared(), _names()),
            reports.timesheet_day_document(_measured(), None, _names()),
        ]
        _assert_whole_seconds(self, documents)

    def test_declared_line_without_figures_holds_zero_shares(self) -> None:
        """A declared-only line whose bucket holds no figures of the day reads with the
        shares of zero: the absence of the bucket from the figures is a sound zero
        (metrics.md › Attribution)."""
        figures = _declared()
        line = TimesheetLine((_BETA, None), 0, 0, 1800)
        figures = figures._replace(
            timesheet=figures.timesheet._replace(lines=[*figures.timesheet.lines, line]))
        entry = reports.timesheet_document([figures], _names())["days"][0]["entries"][-1]
        self.assertEqual(entry["project"], {"id": _BETA, "name": "Beta"})
        self.assertEqual(entry["declared"], 1800)
        self.assertEqual(entry["inferred_human_share"], 0.0)
        self.assertEqual(entry["inferred_agent_share"], 0.0)


class DayDocumentTests(unittest.TestCase):
    """The JSON document of `report day` (command-line.md › JSON documents)."""

    def test_day_keys(self) -> None:
        """The document holds its keys and no other key, the idle gaps of a measured day
        only; the person holds its measures; each project and each work item holds its
        measures and its shares, a project also its project and a work item also its
        work item (command-line.md › JSON documents)."""
        document = reports.day_document(_measured(), _names())
        self.assertEqual(set(document), {
            "day", "state", "human_time_at_idle_gaps", "unknown_invocation_share",
            "person", "projects", "work_items"})
        self.assertEqual(document["day"], "2026-06-15")
        self.assertEqual(document["state"], "measured_day")
        self.assertEqual(document["human_time_at_idle_gaps"],
                         {"300": 6900, "600": 6600, "900": 6300})
        self.assertEqual(set(document["person"]),
                         {"human_time", "agent_time", "parallel_ratio", "blocked_time",
                          "activity_classes"})
        measures = {"human_time", "agent_time", "blocked_time", "activity_classes",
                    "inferred_human_share", "inferred_agent_share"}
        self.assertEqual([set(project) for project in document["projects"]],
                         [measures | {"project"}] * 2)
        self.assertEqual(document["person"], {
            "human_time": 7200, "agent_time": 5200, "parallel_ratio": 1.0,
            "blocked_time": 1001,
            "activity_classes": {"person_only": 7200, "supervised": 0,
                                 "unattended": 5201, "blocked": 1000, "idle": 72999}})
        self.assertEqual(document["projects"][0], {
            "project": {"id": _ALPHA, "name": "Alpha"}, "human_time": 7000,
            "agent_time": 5000, "blocked_time": 1001,
            "activity_classes": {"person_only": 7000}, "inferred_human_share": 0.5,
            "inferred_agent_share": 0.25})
        self.assertEqual(document["projects"][1]["project"], None)
        self.assertEqual(document["work_items"], [{
            "work_item": {"id": _ITEM, "name": _ITEM_NAME}, "human_time": 3600,
            "agent_time": 3800, "blocked_time": 0, "activity_classes": {"person_only": 3600},
            "inferred_human_share": 0.5, "inferred_agent_share": 0.25}])
        declared = reports.day_document(_declared(), _names())
        self.assertNotIn("human_time_at_idle_gaps", declared)

    def test_parallel_ratio_of_every_holder(self) -> None:
        """The parallel ratio of the person, of each project, and of each work item, from
        the exact figures in milliseconds: the agent time over the Supervised time plus
        the Unattended time — the person 1 800 000 over 600 000 + 600 000 = 1.5, Alpha
        and its work item 1 200 000 over 800 000 = 1.5, Beta 600 000 over 600 000 = 1.0 —
        the key right after `agent_time`, and no key where the holder has no agent time
        (metrics.md › Agent time; GLOSSARY.md › Parallel ratio)."""
        document = reports.day_document(_parallel_day(), _names())
        self.assertEqual(list(document["person"]),
                         ["human_time", "agent_time", "parallel_ratio", "blocked_time",
                          "activity_classes"])
        self.assertEqual(document["person"]["parallel_ratio"], 1.5)
        measures = ["human_time", "agent_time", "parallel_ratio", "blocked_time",
                    "activity_classes", "inferred_human_share", "inferred_agent_share"]
        self.assertEqual([list(project) for project in document["projects"][:2]],
                         [["project", *measures]] * 2)
        self.assertEqual([project.get("parallel_ratio")
                          for project in document["projects"]], [1.5, 1.0, None])
        self.assertNotIn("parallel_ratio", document["projects"][2])
        self.assertEqual([list(item) for item in document["work_items"]],
                         [["work_item", *measures]])
        self.assertEqual([item["parallel_ratio"] for item in document["work_items"]], [1.5])

    def test_parallel_ratio_from_the_exact_figures(self) -> None:
        """The parallel ratio divides the exact figures in milliseconds, before the
        document rounds anything to whole seconds: an agent time of 1600 ms over an
        unattended union of 400 ms shows as 2 s over 0 s — a division by zero in whole
        seconds — and the ratio is 1600 ÷ 400 = 4.0 (metrics.md › Agent time)."""
        person = _parallel_day().person._replace(
            agent_time=1_600,
            activity_classes={"person_only": 660_000, "supervised": 0, "unattended": 400,
                              "blocked": 0, "idle": 85_139_600})
        figures = _parallel_day()._replace(person=person)
        document = reports.day_document(figures, _names())
        self.assertEqual(document["person"]["agent_time"], 2)
        self.assertEqual(document["person"]["activity_classes"]["unattended"], 0)
        self.assertEqual(document["person"]["parallel_ratio"], 4.0)

    def test_no_agent_time_no_parallel_ratio(self) -> None:
        """A holder whose agent time is zero holds no `parallel_ratio`: the union of the
        agent intervals behind it is zero, the condition of the division itself. A line
        of a declared day whose bucket holds no figures reads the figures of zero, and
        the entries of a timesheet never hold a ratio, which is a figure of the holders
        of `report day` and of the context of a day alone (metrics.md › Agent time)."""
        figures = _parallel_day()
        document = reports.day_document(figures, _names())
        self.assertNotIn("parallel_ratio", document["projects"][2])
        declared = _declared()
        line = TimesheetLine((_BETA, None), 0, 0, 1800)
        declared = declared._replace(
            timesheet=declared.timesheet._replace(lines=[*declared.timesheet.lines, line]))
        sheet = reports.timesheet_day_document(declared, None, _names())
        for entry in sheet["entries"]:
            self.assertNotIn("parallel_ratio", entry)

    def test_human_time_is_the_human_time_with_manual_entries(self) -> None:
        """On figures whose buckets hold manual entries, `human_time` of the person, of
        each project, and of each work item is the measured human time with the manual
        entries, in whole seconds, on a measured day and on a declared day alike — on a
        declared day neither the declared total of the day nor the declared value of a
        bucket; the agent time, the blocked time, the activity classes, and the shares
        stay as the figures hold them, the keys of the document do not change, and a
        bucket without a manual entry keeps its figure (GLOSSARY.md › Measured day;
        metrics.md › Activity classes, › Declared values)."""
        for state in ("measured_day", "declared_day"):
            with self.subTest(state=state):
                document = reports.day_document(_day_with_manual_entries(state), _names())
                self.assertEqual(document["person"], {
                    "human_time": 5520, "agent_time": 1200, "parallel_ratio": 1.0,
                    "blocked_time": 0,
                    "activity_classes": {"person_only": 5520, "supervised": 0,
                                         "unattended": 1200, "blocked": 0, "idle": 79680}})
                self.assertEqual(document["projects"], [
                    {"project": {"id": _ALPHA, "name": "Alpha"}, "human_time": 3660,
                     "agent_time": 1200, "parallel_ratio": 1.0, "blocked_time": 0,
                     "activity_classes": {"person_only": 3660, "unattended": 1200},
                     "inferred_human_share": 0.5, "inferred_agent_share": 0.25},
                    {"project": {"id": _BETA, "name": "Beta"}, "human_time": 60,
                     "agent_time": 0, "blocked_time": 0,
                     "activity_classes": {"person_only": 60},
                     "inferred_human_share": 0.0, "inferred_agent_share": 0.0},
                    {"project": None, "human_time": 1800, "agent_time": 0, "blocked_time": 0,
                     "activity_classes": {"person_only": 1800}, "inferred_human_share": 0.0,
                     "inferred_agent_share": 0.0}])
                self.assertEqual(document["work_items"], [
                    {"work_item": {"id": _ITEM, "name": _ITEM_NAME}, "human_time": 3660,
                     "agent_time": 1200, "parallel_ratio": 1.0, "blocked_time": 0,
                     "activity_classes": {"person_only": 3660, "unattended": 1200},
                     "inferred_human_share": 0.5, "inferred_agent_share": 0.25}])
                self.assertEqual(set(document), {
                    "day", "state", "unknown_invocation_share", "person", "projects",
                    "work_items"} | (set() if state == "declared_day"
                                     else {"human_time_at_idle_gaps"}))

    def test_human_times_of_the_projects_add_up_to_the_person(self) -> None:
        """The human times of the projects of `report day`, the unattributed time among
        them, add up to the human time of the person, which on a measured day is the
        `total` of the timesheet of the day that `report timesheet` shows
        (GLOSSARY.md › Measured day; metrics.md › Declared values)."""
        figures = _day_with_manual_entries("measured_day")
        document = reports.day_document(figures, _names())
        self.assertEqual([row["human_time"] for row in document["projects"]],
                         [3660, 60, 1800])
        self.assertEqual(sum(row["human_time"] for row in document["projects"]), 5520)
        timesheet = reports.timesheet_document([figures], _names())["days"][0]
        self.assertEqual(document["person"]["human_time"], timesheet["total"])

    def test_classes_add_up_in_whole_seconds(self) -> None:
        """On figures whose instants are not at whole seconds, the JSON document divides
        the whole seconds of each of its sums among the classes with the largest-remainder
        method (command-line.md › Reports; metrics.md › Declared values). The human time of
        the person is 1501 s; the exact shares of 400.4 s and 1100.1 s leave 400 s and
        1100 s whole, with remainders 800 400 and 700 100, so the second that remains goes
        to person only: 401 and 1100. The 84 899 s that remain of the day divide among
        800.8 s, 100.9 s, and 83 997.8 s: 800, 100, and 83 997 s whole, and the two seconds
        that remain go to blocked (remainder 76 359 100) and to unattended (67 519 200),
        not to idle (25 920 700): 801, 101, and 83 997. Alpha ties at 600 s each, with a
        remainder of 600 600, and the second that remains goes to the class that comes
        first in the table of the activity classes, person only: 601 and 600. Beta divides
        its 1100 s over one class. The unattended and the blocked of a project or work item
        are rounded each alone: 300.3 s gives 300, 700.7 s gives 701, and 1400.6 s gives
        1401. In every holder the classes person only and supervised add up to its human
        time, and in the person the five classes add up to the 86 400 s of the day. The
        measured day holds its idle gaps as the figures give them (command-line.md ›
        Reports)."""
        document = reports.day_document(_day_of_milliseconds(), _names())
        self.assertEqual(document["human_time_at_idle_gaps"],
                         {"300": 1100, "600": 1000, "900": 900})
        self.assertEqual(document["person"], {
            "human_time": 1501, "agent_time": 2101,
            "parallel_ratio": 2_100_600 / 1_900_900, "blocked_time": 101,
            "activity_classes": {"person_only": 401, "supervised": 1100,
                                 "unattended": 801, "blocked": 101, "idle": 83997}})
        self.assertEqual(document["projects"], [
            {"project": {"id": _ALPHA, "name": "Alpha"}, "human_time": 1201,
             "agent_time": 1501, "parallel_ratio": 1_500_500 / 900_900,
             "blocked_time": 0,
             "activity_classes": {"person_only": 601, "supervised": 600,
                                  "unattended": 300, "blocked": 0},
             "inferred_human_share": 0.5, "inferred_agent_share": 0.25},
            {"project": {"id": _BETA, "name": "Beta"}, "human_time": 1100,
             "agent_time": 701, "parallel_ratio": 1.0, "blocked_time": 1401,
             "activity_classes": {"person_only": 1100, "supervised": 0,
                                  "unattended": 701, "blocked": 1401},
             "inferred_human_share": 0.0, "inferred_agent_share": 0.0}])
        self.assertEqual(document["work_items"], [
            {"work_item": {"id": _ITEM, "name": _ITEM_NAME}, "human_time": 1201,
             "agent_time": 1501, "parallel_ratio": 1_500_500 / 900_900,
             "blocked_time": 0,
             "activity_classes": {"person_only": 601, "supervised": 600,
                                  "unattended": 300, "blocked": 0},
             "inferred_human_share": 0.5, "inferred_agent_share": 0.25}])
        holders = [document["person"], *document["projects"], *document["work_items"]]
        for held in holders:
            classes = held["activity_classes"]
            self.assertEqual(classes["person_only"] + classes["supervised"],
                             held["human_time"], held)
        self.assertEqual(sum(document["person"]["activity_classes"].values()), 86_400)


class TimesheetDayDocumentTests(unittest.TestCase):
    """The JSON document of `timesheet <day>` (command-line.md › JSON documents)."""

    def test_timesheet_day_keys(self) -> None:
        """The document holds its keys and no other key, each entry also its proposed
        value, and the context of the day; without a proposal every proposed value is
        null; a declared day holds no idle gaps (command-line.md › JSON documents)."""
        proposal: dict[Bucket, int] = {(_ALPHA, _ITEM): 4500, (_ALPHA, None): 2700,
                                       UNATTRIBUTED: 0}
        document = reports.timesheet_day_document(_measured(), proposal, _names())
        self.assertEqual(set(document), {
            "day", "state", "total", "measured_total", "human_time_at_idle_gaps",
            "unknown_invocation_share", "entries", "context"})
        self.assertEqual([entry["proposed"] for entry in document["entries"]],
                         [4500, 2700, 0])
        self.assertEqual(document["context"], {"agent_time": 5200, "parallel_ratio": 1.0,
                                               "presence_span": 28000})
        without = reports.timesheet_day_document(_measured(), None, _names())
        self.assertEqual([entry["proposed"] for entry in without["entries"]],
                         [None, None, None])
        declared = reports.timesheet_day_document(_declared(), None, _names())
        self.assertNotIn("human_time_at_idle_gaps", declared)
        self.assertEqual([set(entry) for entry in document["entries"]], [{
            "project", "work_item", "measured", "with_manual_entries", "declared",
            "inferred_human_share", "inferred_agent_share", "proposed"}] * 3)

    def test_parallel_ratio_of_the_context(self) -> None:
        """The context of `timesheet <day>` holds the parallel ratio of the person of the
        day, from the same figures as its agent time: 1 800 000 ms over 600 000 +
        600 000 ms, the key `parallel_ratio` right after `agent_time` and before
        `presence_span`; a day whose person has no agent time holds a context without
        the key (metrics.md › Agent time; command-line.md › JSON documents)."""
        document = reports.timesheet_day_document(_parallel_day(), None, _names())
        self.assertEqual(list(document["context"]),
                         ["agent_time", "parallel_ratio", "presence_span"])
        self.assertEqual(document["context"]["parallel_ratio"], 1.5)
        empty = DayFigures(
            DayTimesheet(_DAY, "measured_day", 0, 0, [], {}, 0.0, 0, None, []),
            _figures(), {}, {})
        without = reports.timesheet_day_document(empty, None, _names())
        self.assertEqual(list(without["context"]), ["agent_time", "presence_span"])


class SessionAndEntryDocumentsTests(unittest.TestCase):
    """The JSON documents of `sessions <day>` and of `entries` (command-line.md › JSON
    documents)."""

    def test_sessions_keys(self) -> None:
        """The document holds the day and the sessions as the command gives them, their
        parts already with the project and work item objects (command-line.md › JSON
        documents)."""
        session = {
            "session_id": "session-1", "tool": "example_tool",
            "start": "2026-06-15T09:00:00.000Z", "end": "2026-06-15T10:00:00.000Z",
            "cwd": "D:\\Work\\Product\\alpha", "branch": "main",
            "parts": [{"project": {"id": _ALPHA, "name": "Alpha"}, "work_item": None,
                       "human_time": 3600, "agent_time": 1200}],
        }
        document = reports.sessions_document(_DAY, [session])
        self.assertEqual(document, {"day": "2026-06-15", "sessions": [session]})

    def test_entries_keys(self) -> None:
        """Each entry of the document holds `event_uid`, `kind`, and `timestamp` first,
        then the other fields of the event in the order of the schema (command-line.md ›
        JSON documents)."""
        one = _event("uid-one", {"day": _DAY.isoformat(), "duration": 3600,
                                 "project": _ALPHA, "note": "Workshop"})
        document = reports.entries_document(_DAY, [one])
        self.assertEqual(list(document), ["day", "entries"])
        self.assertEqual(document["day"], "2026-06-15")
        self.assertEqual(list(document["entries"][0]), [
            "event_uid", "kind", "timestamp", "actor", "day", "duration", "ingested_at",
            "machine", "note", "project", "schema_version", "source", "writer_version"])


_CLASSES = {"person_only": 3200000, "supervised": 4000123, "unattended": 800000,
            "blocked": 300000, "idle": 78099877}
"""The activity classes of the person of the text tests, in milliseconds: person only and
supervised add up to its human time of 7200123 ms, and the five to the 86 400 000 ms of
the day, as the figures of the core hold them (metrics.md › Activity classes)."""

_PROJECT_CLASSES = {"person_only": 3000000, "supervised": 4000123, "unattended": 800000,
                    "blocked": 300000}
"""The activity classes of the project of the text tests: no class idle, and person only
and supervised add up to its human time of 7000123 ms."""


def _expected(name: str) -> str:
    """The expected text of one report of the fixtures, written by hand: its cells from the
    figures of the tests and its grid from the layout of the text output (command-line.md ›
    Output); the tests that read it compare it with what `render` gives."""
    return (Path(__file__).resolve().parent / "fixtures" / "text" / f"{name}.txt"
            ).read_text(encoding="utf-8")


def _report_day() -> DayFigures:
    """The figures of a measured day whose figures hold the activity classes, as the
    figures of the core hold them (metrics.md › Activity classes)."""
    return DayFigures(
        _sheet(_DAY, "measured_day", None, {300: 6900, 600: 6600, 900: 6300}),
        _figures(human=7200123, agent=5200499, blocked=1000500, classes=dict(_CLASSES),
                 inferred_human=0.5, inferred_agent=0.25),
        {_ALPHA: _figures(human=7000123, agent=5000000, blocked=1000500,
                          classes=dict(_PROJECT_CLASSES), inferred_human=0.5,
                          inferred_agent=0.25),
         None: _figures(human=200000)},
        {(_ALPHA, _ITEM): _figures(human=3600123, agent=3800000, inferred_human=0.5,
                                   inferred_agent=0.25),
         (_ALPHA, None): _figures(human=3400000, agent=1200000),
         UNATTRIBUTED: _figures(human=200000)})


def _adding_up() -> DayFigures:
    """The figures of a measured day of the tests with one project, no work item, and no
    unattributed time: the activity classes of the project are those of the person without
    the class idle, a day where the classes of the projects add up to those of the person
    (metrics.md › Activity classes)."""
    person = _figures(human=7200123, agent=5200499, blocked=1000500, classes=dict(_CLASSES),
                      inferred_human=0.5, inferred_agent=0.25)
    project = person._replace(activity_classes={name: value
                                                for name, value in _CLASSES.items()
                                                if name != "idle"})
    sheet = DayTimesheet(_DAY, "measured_day", 7200, 7200,
                         [TimesheetLine((_ALPHA, None), 7200, 7200, None)],
                         {300: 6900, 600: 6600, 900: 6300}, 0.25, 5200, 28000, [])
    return DayFigures(sheet, person, {_ALPHA: project}, {(_ALPHA, None): project})


_NOTE = "activity_classes_do_not_add_up"
"""The key of the note of the text of `report day` on the activity classes
(command-line.md › Reports)."""


class TextOutputTests(unittest.TestCase):
    """The text output of the reports (command-line.md › Output, › Reports; the layout
    is ruled 2026-11-19): the durations as H:MM in whole minutes, one table for each
    section with the columns of the document in order and each column as wide as its
    widest cell, and the names, work items, and notes as the person wrote them."""

    def test_inactive_day_renders(self) -> None:
        """A period holds also a local day with no events and no confirmation: its
        table shows the header and the totals row of zero and the share of the empty
        day, and no idle gaps, for the document holds none (command-line.md ›
        Reports)."""
        figures = DayFigures(
            DayTimesheet(_DAY, "measured_day", 0, 0, [], {}, 0.0, 0, None, []),
            _figures(), {}, {})
        self.assertEqual(text.render(reports.timesheet_document([figures], _names()), "en"),
                         "\n".join([
            "2026-06-15  Measured day",
            "Project  Work item  Measured  With manual entries  Declared  "
            "Inferred human share  Inferred agent share",
            "Total                   0:00                 0:00",
            "",
            "Unknown invocation share  0.00",
        ]))

    def test_format_duration(self) -> None:
        """A duration is H:MM: whole minutes, the seconds left out, the hours beyond 24
        kept (command-line.md › Output)."""
        self.assertEqual((text.format_duration(5459), text.format_duration(91800)),
                         ("1:30", "25:30"))

    def test_timesheet_table_english(self) -> None:
        """`report timesheet` renders one table for each day, with the columns of the
        document in order and the totals row last, then the share of the unknown
        invocation and, on a measured day, the human time at the idle gaps; the
        declared column stays empty on a measured day and the totals row holds the
        total in the column of its kind."""
        document = reports.timesheet_document([_measured(), _declared()], _names())
        self.assertEqual(text.render(document, "en"), _expected("timesheet-en"))

    def test_timesheet_table_italian(self) -> None:
        """In Italian, the titles and the states use the Italian terms of the glossary
        and the labels hold the Italian words of the tables; the states are `giorno
        misurato` and `giorno dichiarato` (command-line.md › Reports)."""
        document = reports.timesheet_document([_measured(), _declared()], _names())
        self.assertEqual(text.render(document, "it"), _expected("timesheet-it"))

    def test_names_and_notes_stay_as_written(self) -> None:
        """Project names, work item names, and notes stay as the person wrote them in
        both languages, and an identifier of the document shows as it is
        (command-line.md › Reports)."""
        sheet = reports.timesheet_document([_declared()], _names())
        for language in ("en", "it"):
            written = text.render(sheet, language)
            self.assertIn("Alpha", written)
            self.assertIn("Feature 142", written)
        event = _event("uid-note", {"day": _DAY.isoformat(), "duration": 3600,
                                    "project": _ALPHA, "note": "Workshop"})
        written = text.render(reports.entries_document(_DAY, [event]), "it")
        self.assertIn("Workshop", written)
        self.assertIn(_ALPHA, written)

    def test_day_report_tables(self) -> None:
        """`report day` renders the day, then one table for the person, for the
        projects, and for the work items, with a column for each activity class that
        the figures of the day hold, then the note on the activity classes, then the
        share of the unknown invocation and the human time at the idle gaps; the person
        holds no shares and a work item holds no project in the document."""
        document = reports.day_document(_report_day(), _names())
        self.assertEqual(text.render(document, "en"), _expected("day-en"))

    def test_day_report_shows_the_parallel_ratio(self) -> None:
        """`report day` shows the parallel ratio in one column right after the agent
        time of the person, of each project, and of each work item, with two decimals —
        the person 1.5 as `1.50`, Alpha and its work item `1.50`, Beta `1.00` — and an
        empty cell for a holder without the key, the unattributed time; the header is
        `Parallel ratio`, `rapporto di parallelismo` in Italian (command-line.md ›
        Reports; metrics.md › Agent time)."""
        document = reports.day_document(_parallel_day(), _names())
        sections = text.render(document, "en").split("\n\n")
        self.assertEqual(sections[1].split("\n"), [
            "Person",
            "Human time  Agent time  Parallel ratio  Blocked time  Person only  Supervised "
            " Unattended  Blocked   Idle",
            "0:11              0:30            1.50          0:00         0:01        0:10       "
            " 0:10     0:00  23:39"])
        self.assertEqual(sections[2].split("\n")[2:], [
            "Alpha               0:01        0:20            1.50          0:00         0:01      "
            "              0:13                                 0.00                  0.00",
            "Beta                0:10        0:10            1.00          0:00         0:10      "
            "              0:10                                 0.00                  0.00",
            "Unattributed        0:00        0:00                          0:00         0:00      "
            "                                                   0.00                  0.00"])
        self.assertEqual(sections[3].split("\n")[2:], [
            "Feature 142        0:01        0:20            1.50          0:00         0:01       "
            "             0:13                                 0.00                  0.00"])
        italian = text.render(document, "it").split("\n\n")
        self.assertEqual(italian[1].split("\n")[1:], [
            "tempo persona  tempo agente  rapporto di parallelismo  tempo bloccato  solo persona "
            " supervisionato  non supervisionato  bloccato  inattività",
            "0:11                   0:30                      1.50            0:00          0:01  "
            "          0:10                0:10      0:00       23:39"])
        for section in italian[1:4]:
            self.assertIn("rapporto di parallelismo", section.split("\n")[1])

    def test_timesheet_day_shows_the_parallel_ratio(self) -> None:
        """`timesheet <day>` shows the parallel ratio of the day as one figure line right
        after its agent time, with two decimals — `Parallel ratio  1.50`, `rapporto di
        parallelismo  1.50` — and no line when the context holds no key, a day whose
        person has no agent time (command-line.md › Reports; metrics.md › Agent time)."""
        document = reports.timesheet_day_document(_parallel_day(), None, _names())
        for language in ("en", "it"):
            with self.subTest(language=language):
                figures = text.render(document, language).split("\n\n")[1].split("\n")
                self.assertEqual(figures, [
                    f"{label('agent_time', language)}  0:30",
                    f"{label('parallel_ratio', language)}  1.50",
                    f"{label('presence_span', language)}  0:10"])
        empty = DayFigures(
            DayTimesheet(_DAY, "measured_day", 0, 0, [], {}, 0.0, 0, None, []),
            _figures(), {}, {})
        for language in ("en", "it"):
            written = text.render(reports.timesheet_day_document(empty, None, _names()),
                                  language)
            self.assertNotIn(label("parallel_ratio", language), written)

    def test_difference_of_the_parallel_ratio_shows_two_decimals(self) -> None:
        """A row of `differences` whose figure is the parallel ratio — a frozen report
        that holds no key against a document of now that holds 1.5 — shows the ratio
        with two decimals and an empty Frozen cell, in both languages
        (command-line.md › Reports, › Frozen reports)."""
        document = {**_day_report(_record()),
                    "differences": [{"day": "2026-06-15", "figure": "parallel_ratio",
                                     "now": 1.5}]}
        self.assertEqual(text.render(document, "en").rsplit("\n\n", 1)[-1]
                         .split("\n"), [
            "Differences",
            "Day         Project  Work item  Figure          Frozen   Now",
            "2026-06-15                      parallel_ratio          1.50"])
        self.assertEqual(text.render(document, "it").rsplit("\n\n", 1)[-1]
                         .split("\n"), [
            "differenze",
            "giorno      progetto  unità di lavoro  figura          congelato  adesso",
            "2026-06-15                             parallel_ratio               1.50"])

    def test_day_report_holds_the_note_after_the_work_items(self) -> None:
        """The text of `report day` holds one sentence that its document does not: the
        activity classes of the projects and of the work items do not always add up to
        those of the person. The sentence is a section of one line after the table of the
        work items, in English and in Italian, on a measured day and on a declared day,
        also on a day where the classes add up, and before the sections against the frozen
        reports (command-line.md › Reports; metrics.md › Activity classes)."""
        for day, figures in (("measured", _measured()), ("declared", _declared()),
                             ("adding up", _adding_up())):
            document = {
                **reports.day_document(figures, _names()),
                "differences": [{"day": figures.timesheet.day.isoformat(),
                                 "figure": "unknown_invocation_share",
                                 "frozen": 0.25, "now": 0.5}],
                "changed": [{"path": "parameters.idle_gap", "frozen": 600, "now": 300}],
            }
            for language in ("en", "it"):
                sentence = note(_NOTE, language)
                self.assertNotIn(sentence, json.dumps(document, ensure_ascii=False))
                with self.subTest(day=day, language=language):
                    sections = text.render(document, language).split("\n\n")
                    self.assertEqual(sections.count(sentence), 1)
                    position = sections.index(sentence)
                    self.assertTrue(sections[position - 1].startswith(
                        label("work_items", language)), sections[position - 1])
                    self.assertTrue(sections[position + 1].startswith(
                        label("unknown_invocation_share", language)))
                    self.assertTrue(sections[-2].startswith(label("differences", language)))
                    self.assertTrue(sections[-1].startswith(label("changed", language)))
                    self.assertLess(position, len(sections) - 2)

    def test_timesheet_day_table_shows_proposal_and_context(self) -> None:
        """`timesheet <day>` renders the day with a proposed column at the end, then
        the context of the day, its agent time and its presence span, then the share
        of the unknown invocation and the human time at the idle gaps."""
        proposal: dict[Bucket, int] = {(_ALPHA, _ITEM): 4500, (_ALPHA, None): 2700,
                                       UNATTRIBUTED: 0}
        document = reports.timesheet_day_document(_measured(), proposal, _names())
        self.assertEqual(text.render(document, "en"), _expected("timesheet_day-en"))

    def test_timesheet_confirm_shows_its_identifier_and_the_entries(self) -> None:
        """The document of `timesheet confirm` — the identifier of the confirmation and
        the entries of the day — renders as the line of the identifier, then the table of
        the entries in the columns of `timesheet <day>`, the proposed value last; no title
        line and no totals row, because the document holds neither the day nor its totals
        (command-line.md › JSON documents)."""
        document = {"event_uid": "uid-one", "entries": [
            {"project": {"id": _ALPHA, "name": "Alpha"},
             "work_item": {"id": _ITEM, "name": _ITEM_NAME}, "measured": 3600,
             "with_manual_entries": 4000, "declared": 5400, "inferred_human_share": 0.5,
             "inferred_agent_share": 0.25, "proposed": 5400},
            {"project": None, "work_item": None, "measured": 0, "with_manual_entries": 200,
             "declared": 0, "inferred_human_share": 0.0, "inferred_agent_share": 0.0,
             "proposed": None}]}
        self.assertEqual(text.render(document, "en"), "\n".join([
            "Event identifier: uid-one",
            "",
            "Project" + " " * 7 + "Work item" + " " * 4 + "Measured  With manual entries"
            "  Declared  Inferred human share  Inferred agent share  Proposed",
            "Alpha" + " " * 9 + _ITEM_NAME + " " * 6 + "1:00" + " " * 17 + "1:06"
            + " " * 6 + "1:30" + " " * 18 + "0.50" + " " * 18 + "0.25" + " " * 6 + "1:30",
            "Unattributed" + " " * 19 + "0:00" + " " * 17 + "0:03" + " " * 6 + "0:00"
            + " " * 18 + "0.00" + " " * 18 + "0.00"]))
        self.assertTrue(text.render(document, "it").startswith(
            "identificativo dell'evento: uid-one\n\nprogetto"))

    def test_sessions_table(self) -> None:
        """`sessions <day>` renders the sessions of the day, one row for each part of
        a session with the session keys repeated on it, and one row for a session
        without parts, its part cells empty; the durations are H:MM and the instants
        stay as the document holds them."""
        sessions = [
            {"session_id": "session-1", "tool": "example_tool",
             "start": "2026-06-15T09:00:00.000Z", "end": "2026-06-15T10:00:00.000Z",
             "cwd": "D:\\Work\\Product\\alpha", "branch": "main",
             "parts": [{"project": {"id": _ALPHA, "name": "Alpha"},
                        "work_item": {"id": _ITEM, "name": _ITEM_NAME},
                        "human_time": 3600, "agent_time": 1200}]},
            {"session_id": "session-2", "tool": "example_tool",
             "start": "2026-06-15T11:00:00.000Z", "end": "2026-06-15T11:30:00.000Z",
             "cwd": "D:\\Work\\Product\\alpha", "branch": "main", "parts": []},
        ]
        self.assertEqual(text.render(reports.sessions_document(_DAY, sessions), "en"),
                         _expected("sessions-en"))

    def test_entries_table(self) -> None:
        """`entries` renders the events of the day, `event_uid`, `kind`, and
        `timestamp` first, then its other fields by name, one column for each field
        that any entry holds, with the duration as H:MM (command-line.md › JSON
        documents)."""
        event = _event("uid-one", {"day": _DAY.isoformat(), "duration": 3600,
                                   "project": _ALPHA, "note": "Workshop"})
        self.assertEqual(text.render(reports.entries_document(_DAY, [event]), "en"),
                         _expected("entries-en"))

    def test_entries_table_shows_the_machine_label(self) -> None:
        """The column Machine of `entries` shows the machine label that the caller gives
        for the machine of an event, and the identifier of a machine that has none, in both
        languages; the header stays the label of `machine`, the document keeps the
        identifier, and without labels the column shows the identifiers (command-line.md ›
        JSON documents)."""
        events = [_event("uid-one", {"project": _ALPHA}),
                  {**_event("uid-two", {"project": _BETA}), "machine": _OTHER_MACHINE}]
        document = reports.entries_document(_DAY, events)
        for language in ("en", "it"):
            rows = support.cells(
                text.render(document, language, machine_labels={_MACHINE: _LABEL}))
            column = rows[1].index(label("machine", language))
            self.assertEqual([row[column] for row in rows[2:]], [_LABEL, _OTHER_MACHINE])
        self.assertEqual([entry["machine"] for entry in document["entries"]],
                         [_MACHINE, _OTHER_MACHINE])
        rows = support.cells(text.render(document, "en"))
        self.assertEqual([row[rows[1].index("Machine")] for row in rows[2:]],
                         [_MACHINE, _OTHER_MACHINE])

    def test_sessions_table_without_a_branch(self) -> None:
        """A session whose document holds no folder and no branch, because its last event
        of the day holds none, leaves their cells empty: an absent field is not written,
        and the table shows no value where the document holds none. The columns after
        the end hold no cell, so no trailing space reaches the line."""
        session = {"session_id": "session-3", "tool": "example_tool",
                   "start": "2026-06-15T09:00:00.000Z", "end": "2026-06-15T10:00:00.000Z",
                   "parts": []}
        self.assertEqual(text.render(reports.sessions_document(_DAY, [session]), "en"),
                         "\n".join([
                             "2026-06-15  Sessions",
                             "Session" + " " * 4 + "Tool" + " " * 10 + "Start" + " " * 21
                             + "End" + " " * 23
                             + "Folder  Branch  Project  Work item  Human time  Agent time",
                             "session-3  example_tool  2026-06-15T09:00:00.000Z  "
                             "2026-06-15T10:00:00.000Z"]))

    def test_frozen_list_table(self) -> None:
        """`frozen list` renders one table under the title of the frozen reports: the
        columns are the keys of its rows, a row without a note leaves the cell empty, and
        the instant of the freeze shows as the document holds it (command-line.md › Frozen
        reports). The widths are the widest cells: the identifier of 36 characters, the
        command `report timesheet`, the day, the note of 18, the machine of 36, the
        instant of 24; with no row every column is as wide as its label."""
        first = "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"
        second = "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"
        document = {"frozen": [
            {"id": first, "report": "report timesheet", "from": "2026-06-15",
             "to": "2026-06-16", "note": "Sent to the office", "machine": _MACHINE,
             "frozen_at": "2026-06-16T12:00:00.000Z"},
            {"id": second, "report": "report day", "from": "2026-06-15",
             "to": "2026-06-15", "machine": _MACHINE,
             "frozen_at": "2026-06-17T09:30:00.000Z"},
        ]}
        self.assertEqual(text.render(document, "en"), "\n".join([
            "Frozen reports",
            "Id" + " " * 36 + "Report" + " " * 12 + "From" + " " * 8 + "To" + " " * 10
            + "Note" + " " * 16 + "Machine" + " " * 31 + "Frozen at",
            f"{first}  report timesheet  2026-06-15  2026-06-16  Sent to the office  "
            f"{_MACHINE}  2026-06-16T12:00:00.000Z",
            f"{second}  report day" + " " * 8 + "2026-06-15  2026-06-15" + " " * 22
            + f"{_MACHINE}  2026-06-17T09:30:00.000Z"]))
        self.assertEqual(text.render({"frozen": []}, "it"),
                         "report congelati\nid  report  dal  al  nota  macchina"
                         "  congelato il")

    def test_frozen_list_table_shows_the_machine_label(self) -> None:
        """The column Machine of `frozen list` shows the `machine_label` of a row that
        holds one, and the identifier of a row that holds none; the header stays the label
        of `machine` (command-line.md › JSON documents). The widths: the identifier of 36,
        the command `report day` of 10, the empty day and note columns as wide as their
        labels, the machine as wide as the identifier of 36, which is wider than the label
        of 15, the instant of 24."""
        first = "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"
        second = "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"
        document = {"frozen": [
            {"id": first, "report": "report day", "machine": _MACHINE,
             "machine_label": _LABEL, "frozen_at": "2026-06-16T12:00:00.000Z"},
            {"id": second, "report": "report day", "machine": _OTHER_MACHINE,
             "frozen_at": "2026-06-17T09:30:00.000Z"},
        ]}
        self.assertEqual(text.render(document, "en"), "\n".join([
            "Frozen reports",
            "Id" + " " * 36 + "Report" + " " * 6 + "From  To  Note  Machine" + " " * 31
            + "Frozen at",
            f"{first}  report day" + " " * 18 + _LABEL + " " * 23
            + "2026-06-16T12:00:00.000Z",
            f"{second}  report day" + " " * 18 + _OTHER_MACHINE
            + "  2026-06-17T09:30:00.000Z"]))

    def test_frozen_show_text(self) -> None:
        """`frozen show` renders a first section of one title line — the label of a frozen
        report, its identifier, and its command — then the sections of the frozen document,
        which are the text of its own command, then the tables of the differences and of the
        changed facts against the report of now (command-line.md › Frozen reports)."""
        frozen_id = "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"
        document = {
            "frozen": {**_timesheet_report(_record()), "frozen_id": frozen_id},
            "differences": [{"day": "2026-06-15", "figure": "total", "frozen": 7200,
                             "now": 7100}],
            "changed": [{"path": "parameters.idle_gap", "frozen": 600, "now": 300}],
        }
        self.assertEqual(text.render(document, "en"), "\n\n".join([
            f"Frozen report  {frozen_id}  report timesheet",
            _expected("timesheet-en"),
            "\n".join(["Differences",
                       "Day" + " " * 9 + "Project  Work item  Figure  Frozen   Now",
                       "2026-06-15" + " " * 22 + "total" + " " * 5 + "2:00" + "  "
                       + "1:58"]),
            "\n".join(["Changed", "Path" + " " * 17 + "Frozen" + " " * 3 + "Now",
                       "parameters.idle_gap" + " " * 4 + "0:10  0:05"])]))
        self.assertTrue(text.render(document, "it").startswith(
            f"report congelato  {frozen_id}  report timesheet\n\n"))
        # a document that holds no identifier, as the file of another version may: the
        # title names the report and its command
        without = {key: value for key, value in document["frozen"].items()
                   if key != "frozen_id"}
        self.assertTrue(text.render({**document, "frozen": without}, "en").startswith(
            "Frozen report  report timesheet\n\n"))

    def test_report_with_an_identifier_ends_with_its_line(self) -> None:
        """A report whose document holds `frozen_id`, as one with `--freeze` does, ends
        with one section of one figure line: the label of a frozen report and the
        identifier, two spaces between (command-line.md › Frozen reports)."""
        frozen_id = "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"
        document = {"command": "report day", "warnings": [], "configuration_errors": [],
                    "record": _record(), **reports.day_document(_report_day(), _names()),
                    "frozen_id": frozen_id}
        self.assertEqual(text.render(document, "en"),
                         _expected("day-en") + "\n\n" + f"Frozen report  {frozen_id}")
        self.assertTrue(text.render(document, "it").endswith(
            f"\n\nreport congelato  {frozen_id}"))
        document.pop("frozen_id")
        self.assertNotIn("Frozen report", text.render(document, "en"))


def _assert_whole_seconds(test: unittest.TestCase, documents: list[dict]) -> None:
    """That every duration of the documents is an `int`, and never a `float` or a text
    (command-line.md › JSON documents): the durations are the values of their keys, the
    keys of the idle gaps name seconds and their values are durations."""
    durations = {"total", "measured_total", "measured", "with_manual_entries", "declared",
                 "proposed", "human_time", "agent_time", "blocked_time"}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in durations and value is not None:
                    test.assertIs(type(value), int, f"{key} holds {value!r}")
                if key == "human_time_at_idle_gaps":
                    for gap, seconds in value.items():
                        test.assertRegex(gap, r"^[0-9]+$")
                        test.assertIs(type(seconds), int)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    for document in documents:
        walk(document)


class FrozenReportTests(unittest.TestCase):
    """The frozen reports and their differences (command-line.md › Frozen reports, › JSON
    documents): the document kept as given with its note and the instant of the freeze,
    the rows of `frozen list`, the latest frozen report of each day, and the figures and
    the record facts that differ between a frozen report and a report of now."""

    def test_freeze_keeps_json_also_for_text_output(self) -> None:
        """`--freeze` keeps exactly the JSON document of the report, the record included,
        also when the output is text: the file holds it as `document`, with `--note` as
        `note` and the instant of the freeze as `frozen_at`; the document gains
        `frozen_id` in the file only, and without a note the file holds no `note`."""
        document = _timesheet_report(_record())
        with support.TemporaryFolder() as store_folder:
            frozen_id = reports.freeze(
                store_folder, _MACHINE, document, "Sent to the office",
                support.utc("2026-06-16T12:00:00"),
                lambda: "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            self.assertEqual(frozen_id, "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            self.assertNotIn("frozen_id", document)
            path = store_folder / "frozen" / _MACHINE / f"{frozen_id}.json"
            written = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(written, {
                "document": {**document, "frozen_id": frozen_id},
                "note": "Sent to the office",
                "frozen_at": "2026-06-16T12:00:00.000Z"})
            self.assertIn("record", written["document"])
            without_note_id = reports.freeze(
                store_folder, _MACHINE, document, None,
                support.utc("2026-06-16T12:00:00"),
                lambda: "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            without_note = json.loads((store_folder / "frozen" / _MACHINE
                                       / f"{without_note_id}.json").read_text(encoding="utf-8"))
            self.assertEqual(list(without_note), ["document", "frozen_at"])

    def test_differences_of_a_changed_rule(self) -> None:
        """An identity rule that the person added after the freeze: `changed` names the
        rule with its value of now and no frozen value, and `differences` holds the
        figures of its day, the human time that moved to the project of the rule."""
        frozen = _timesheet_report(_record())
        current = _timesheet_report(_record(_person_with_beta()),
                                    [_measured_with_beta(), _declared()])
        figure_rows, changed = reports.differences(frozen, current)
        beta = {"id": _BETA, "name": "Beta"}
        self.assertEqual(figure_rows, [
            {"day": "2026-06-15", "project": None, "work_item": None,
             "figure": "with_manual_entries", "frozen": 200, "now": 80},
            {"day": "2026-06-15", "project": beta, "work_item": None,
             "figure": "measured", "now": 0},
            {"day": "2026-06-15", "project": beta, "work_item": None,
             "figure": "with_manual_entries", "now": 120},
            {"day": "2026-06-15", "project": beta, "work_item": None,
             "figure": "inferred_human_share", "now": 0.0},
            {"day": "2026-06-15", "project": beta, "work_item": None,
             "figure": "inferred_agent_share", "now": 0.0},
        ])
        self.assertEqual(changed, [{
            "path": "identity_rules[1]",
            "now": {"project": _BETA, "repository": _BETA,
                    "folder": "D:\\Work\\Product\\beta", "branch": "main",
                    "from": "2026-06-15", "to": "2026-06-16"}}])

    def test_changed_parameters(self) -> None:
        """A report parameter that changed between the two records, the idle gap from ten
        minutes to five: `changed` holds it with its frozen value and its value of now,
        and the figures of the two documents hold no difference."""
        frozen = _timesheet_report(_record(idle_gap=600))
        current = _timesheet_report(_record(idle_gap=300))
        figure_rows, changed = reports.differences(frozen, current)
        self.assertEqual(figure_rows, [])
        self.assertEqual(changed, [
            {"path": "parameters.idle_gap", "frozen": 600, "now": 300}])

    def test_a_frozen_report_without_the_parallel_ratio(self) -> None:
        """A frozen `report day` written before the parallel ratio holds no
        `parallel_ratio` in its holders: `differences` gives each holder that the
        document of now holds the ratio for — here the person, 5 200 499 ms of agent
        time over 5 200 499 ms unattended, 1.0 — one row with `now` alone and no
        `frozen`, after the rows of the figures that the frozen document holds
        (command-line.md › Frozen reports; metrics.md › Agent time)."""
        current = _day_report(_record())
        self.assertEqual(current["person"]["parallel_ratio"], 1.0)
        person = dict(current["person"])
        del person["parallel_ratio"]
        person["human_time"] = 7201
        frozen = {**current, "person": person}
        figure_rows, changed = reports.differences(frozen, current)
        self.assertEqual(figure_rows, [
            {"day": "2026-06-15", "figure": "human_time", "frozen": 7201, "now": 7200},
            {"day": "2026-06-15", "figure": "parallel_ratio", "now": 1.0}])
        self.assertEqual(changed, [])

    def test_frozen_list_keys(self) -> None:
        """`frozen list` shows each frozen report with its identifier, the command and
        the period of its document, its note, its machine, and the instant of its freeze,
        in the order of the files of the store; without a note the row holds no `note`."""
        with support.TemporaryFolder() as store_folder:
            reports.freeze(store_folder, _MACHINE, _timesheet_report(_record()),
                           "Sent to the office", support.utc("2026-06-16T12:00:00"),
                           lambda: "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            reports.freeze(store_folder, _MACHINE, _day_report(_record()), None,
                           support.utc("2026-06-17T09:30:00"),
                           lambda: "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            self.assertEqual(reports.frozen_list(store_folder), ([
                {"id": "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a",
                 "report": "report timesheet", "from": "2026-06-15", "to": "2026-06-16",
                 "note": "Sent to the office", "machine": _MACHINE,
                 "frozen_at": "2026-06-16T12:00:00.000Z"},
                {"id": "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a", "report": "report day",
                 "from": "2026-06-15", "to": "2026-06-15", "machine": _MACHINE,
                 "frozen_at": "2026-06-17T09:30:00.000Z"}], []))

    def test_frozen_list_names_the_machine_label(self) -> None:
        """A row of `frozen list` holds `machine_label`, after `machine`, when the store
        holds a machine label for the machine that wrote the file, and no `machine_label`
        when it holds none, because an absent value is never null (command-line.md › JSON
        documents); its text shows the label of the one machine and the identifier of the
        other, in both languages."""
        with support.TemporaryFolder() as store_folder:
            store.write_label(store_folder, _MACHINE, _LABEL)
            reports.freeze(store_folder, _MACHINE, _day_report(_record()), None,
                           support.utc("2026-06-16T12:00:00"),
                           lambda: "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            reports.freeze(store_folder, _OTHER_MACHINE, _day_report(_record()), None,
                           support.utc("2026-06-17T09:30:00"),
                           lambda: "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            rows, warnings = reports.frozen_list(store_folder)
        self.assertEqual(warnings, [])
        self.assertEqual(rows, [
            {"id": "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a", "report": "report day",
             "from": "2026-06-15", "to": "2026-06-15", "machine": _MACHINE,
             "machine_label": _LABEL, "frozen_at": "2026-06-16T12:00:00.000Z"},
            {"id": "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a", "report": "report day",
             "from": "2026-06-15", "to": "2026-06-15", "machine": _OTHER_MACHINE,
             "frozen_at": "2026-06-17T09:30:00.000Z"}])
        self.assertEqual(list(rows[0]), ["id", "report", "from", "to", "machine",
                                         "machine_label", "frozen_at"])
        for language in ("en", "it"):
            shown = text.render({"frozen": rows}, language)
            first, second = shown.splitlines()[2:]
            self.assertIn(f"  {_LABEL}  ", first)
            self.assertIn(f"  {_OTHER_MACHINE}  ", second)
            self.assertNotIn(_MACHINE, shown)

    def test_frozen_list_reads_each_label_once(self) -> None:
        """`frozen list` reads the store metadata of each machine once, however many of its
        rows name the machine: two frozen reports of one machine whose store metadata is no
        TOML give rows without `machine_label` and one warning `machine_label_unreadable`,
        which names the file; with a label the file is read once too, and both rows hold it
        (command-line.md › JSON documents)."""
        with support.TemporaryFolder() as store_folder:
            for frozen_id in ("1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a",
                              "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"):
                reports.freeze(store_folder, _MACHINE, _day_report(_record()), None,
                               support.utc("2026-06-16T12:00:00"), lambda: frozen_id)
            metadata = store_folder / "machines" / f"{_MACHINE}.toml"
            metadata.parent.mkdir()
            metadata.write_text('label = "Invented laptop\n', encoding="utf-8")
            rows, warnings = reports.frozen_list(store_folder)
            self.assertEqual([row["machine"] for row in rows], [_MACHINE, _MACHINE])
            self.assertTrue(all("machine_label" not in row for row in rows))
            self.assertEqual(warnings, [{"code": "machine_label_unreadable",
                                         "values": {"path": f"machines/{_MACHINE}.toml"}}])
            store.write_label(store_folder, _MACHINE, _LABEL)
            with mock.patch.object(store.files.tomllib, "load",
                                   wraps=store.files.tomllib.load) as load:
                rows, warnings = reports.frozen_list(store_folder)
            self.assertEqual(load.call_count, 1)
            self.assertEqual(([row.get("machine_label") for row in rows], warnings),
                             ([_LABEL, _LABEL], []))

    def test_remove_on_another_machine_names_the_machine_label(self) -> None:
        """The stop error of a removal from another machine names the machine that wrote
        the file: without a machine label in the store, its values hold `id` and `machine`
        and its text names the identifier; with one, its values also hold `machine_label`
        and its text, under the same code, names the label, in both languages
        (command-line.md › Exit codes, › Frozen reports)."""
        with support.TemporaryFolder() as store_folder:
            frozen_id = reports.freeze(store_folder, _MACHINE,
                                       _timesheet_report(_record()), None,
                                       support.utc("2026-06-16T12:00:00"),
                                       lambda: "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            with self.assertRaises(FrozenOtherMachine) as bare:
                reports.remove_frozen_report(store_folder, frozen_id, _OTHER_MACHINE)
            store.write_label(store_folder, _MACHINE, _LABEL)
            with self.assertRaises(FrozenOtherMachine) as labelled:
                reports.remove_frozen_report(store_folder, frozen_id, _OTHER_MACHINE)
        self.assertEqual(bare.exception.values, {"id": frozen_id, "machine": _MACHINE})
        self.assertEqual(labelled.exception.values,
                         {"id": frozen_id, "machine": _MACHINE, "machine_label": _LABEL})
        self.assertEqual((bare.exception.code, labelled.exception.code),
                         ("frozen_other_machine", "frozen_other_machine"))
        cases = {
            bare.exception: (
                f"The frozen report {frozen_id} was written by the machine {_MACHINE};"
                " only that machine removes it.",
                f"Il report congelato {frozen_id} è stato scritto dalla macchina {_MACHINE};"
                " solo quella macchina lo rimuove."),
            labelled.exception: (
                f"The frozen report {frozen_id} was written by the machine {_LABEL};"
                " only that machine removes it.",
                f"Il report congelato {frozen_id} è stato scritto dalla macchina {_LABEL};"
                " solo quella macchina lo rimuove."),
        }
        for error, (english, italian) in cases.items():
            self.assertEqual(message(error.text_key, error.values, "en"), english)
            self.assertEqual(message(error.text_key, error.values, "it"), italian)

    def test_latest_frozen_holds_each_day(self) -> None:
        """Where frozen reports overlap, each day is held by the latest frozen report
        that holds it: the one with the latest `frozen_at`, and, at the same `frozen_at`,
        the one with the latest identifier as text."""
        first = _frozen_timesheet("first-freeze", ["2026-06-15", "2026-06-16"])
        second = _frozen_timesheet("second-freeze",
                                   ["2026-06-15", "2026-06-16", "2026-06-17"])
        third = _frozen_timesheet("third-freeze", ["2026-06-15"])
        latest = reports.latest_frozen_by_day([
            _envelope(first, "2026-06-16T08:00:00.000Z"),
            _envelope(second, "2026-06-16T09:00:00.000Z"),
            _envelope(third, "2026-06-16T09:00:00.000Z"),
        ])
        self.assertEqual(latest, {
            "2026-06-15": third, "2026-06-16": second, "2026-06-17": second})

    def test_remove_stops_for_another_machine_and_an_unknown_identifier(self) -> None:
        """Only the machine that wrote a frozen report removes it: the removal from
        another machine stops and names that machine, an identifier that the store does
        not hold stops with the identifier as its target, and the removal from the machine
        that wrote it deletes the file."""
        with support.TemporaryFolder() as store_folder:
            frozen_id = reports.freeze(store_folder, _MACHINE,
                                       _timesheet_report(_record()), None,
                                       support.utc("2026-06-16T12:00:00"),
                                       lambda: "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            with self.assertRaises(FrozenOtherMachine) as raised:
                reports.remove_frozen_report(store_folder, frozen_id,
                                             "9999b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            self.assertEqual(raised.exception.values,
                             {"id": frozen_id, "machine": _MACHINE})
            with self.assertRaises(TargetNotFound) as missing:
                reports.remove_frozen_report(
                    store_folder, "3333b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a", _MACHINE)
            self.assertEqual(missing.exception.values,
                             {"target": "3333b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"})
            reports.remove_frozen_report(store_folder, frozen_id, _MACHINE)
            self.assertEqual(reports.frozen_list(store_folder), ([], []))

    def test_remove_reads_no_file(self) -> None:
        """The removal finds the file of a frozen report by its name and reads none: a
        file that the ledger cannot read as a frozen report is removed like any other,
        which is the remedy that the stop error names, and the frozen report beside it
        stays (command-line.md › Frozen reports)."""
        with support.TemporaryFolder() as store_folder:
            healthy = reports.freeze(store_folder, _MACHINE, _timesheet_report(_record()),
                                     None, support.utc("2026-06-16T12:00:00"),
                                     lambda: "1111b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a")
            damaged_id = "2222b2c3-9a3d-4f6b-8c5d-2e4a6b8d0f1a"
            damaged = store_folder / "frozen" / _MACHINE / f"{damaged_id}.json"
            damaged.parent.mkdir(parents=True, exist_ok=True)
            damaged.write_bytes(b"not a frozen report")
            self.assertEqual(store.frozen_names(store_folder),
                             [(_MACHINE, healthy), (_MACHINE, damaged_id)])
            with mock.patch.object(Path, "read_text",
                                   side_effect=AssertionError("a file was read")):
                reports.remove_frozen_report(store_folder, damaged_id, _MACHINE)
            self.assertFalse(damaged.exists())
            self.assertEqual([row["id"] for row in reports.frozen_list(store_folder)[0]],
                             [healthy])

    def test_report_days(self) -> None:
        """The local days that a report document covers: the days of `report timesheet` in
        the order of the document, the one day of `report day`, and none for a document of
        another shape."""
        self.assertEqual(reports.report_days(_timesheet_report(_record())),
                         [_DAY, _NEXT])
        self.assertEqual(reports.report_days(_day_report(_record())), [_DAY])
        self.assertEqual(reports.report_days({"command": "report week", "record": {}}), [])
