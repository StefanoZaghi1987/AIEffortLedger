"""Report tests: the fixture stores that the outputs of the commands are compared on,
the marks that make one expected file fit every run and every operating system, and the
text and JSON output of the commands, in English and in Italian, against their expected
files (architecture.md › Tests › Report tests, command-line.md › Form, › Reports, ›
Frozen reports, Global Constraints)."""

import contextlib
import io
import json
import subprocess
import tomllib
import unittest
from collections.abc import Callable, Sequence
from datetime import timedelta
from pathlib import Path
from unittest import mock

import support
from ai_effort_ledger import days, declared, reports
from ai_effort_ledger.cli import ACTIONS, Context
from ai_effort_ledger.cli import _ask as ask_at_terminal
from ai_effort_ledger.configuration import read_person_configuration
from ai_effort_ledger.configuration.person import PERSON_FILE
from ai_effort_ledger.events import format_instant
from ai_effort_ledger.language import LANGUAGES, message, question
from ai_effort_ledger.platform import ENTRY_NAME
from ai_effort_ledger.store import machine_labels

EXPECTED = Path(__file__).resolve().parent / "fixtures" / "expected"
"""The expected files of the commands that the output tests cover, by language
(architecture.md › Tests › Report tests): under the folder of the language, `en` or `it`,
for each command, `<command>_<name>.txt` holds the text of the standard output and
`<command>_<name>.json` the document of `--json`; the words of a command are joined by a
dash, as in `report-timesheet`, and the name after the underscore names the fixture store
that a report reads, or the scenario of a command that builds its own world. The help has
no JSON document, so `help_main.txt` and `help_<command>.txt` alone hold the help of
`--help` and of one command. The English file and the Italian file of one name are twins:
the same cells, with the labels, the states, the messages, and the language of the record
in the language of the folder, except the one row that the language of the record adds to
the changed facts of a twin against a frozen report (command-line.md › Reports), and the
parameter `language` of `config show`, whose value and layer the `--language` of the
Italian run gives (configuration.md › Order)."""

SESSION_EVENTS = "session"
"""The count of the events of the sessions that each store holds in its selection."""

MANUAL_ENTRIES = "manual_entry"
ANNOTATIONS = "annotation"
CONFIRMATIONS = "timesheet_confirmation"
RETRACTIONS = "retraction"

STORE_EVENTS = {
    "measured_day": {SESSION_EVENTS: 2, MANUAL_ENTRIES: 0, ANNOTATIONS: 0,
                     CONFIRMATIONS: 0, RETRACTIONS: 0},
    "declared_day": {SESSION_EVENTS: 2, MANUAL_ENTRIES: 0, ANNOTATIONS: 0,
                     CONFIRMATIONS: 1, RETRACTIONS: 0},
    "manual_entries": {SESSION_EVENTS: 2, MANUAL_ENTRIES: 2, ANNOTATIONS: 0,
                       CONFIRMATIONS: 0, RETRACTIONS: 0},
    "annotations": {SESSION_EVENTS: 3, MANUAL_ENTRIES: 0, ANNOTATIONS: 2,
                    CONFIRMATIONS: 0, RETRACTIONS: 0},
    "retraction": {SESSION_EVENTS: 2, MANUAL_ENTRIES: 0, ANNOTATIONS: 0,
                   CONFIRMATIONS: 0, RETRACTIONS: 1},
    "frozen_period": {SESSION_EVENTS: 4, MANUAL_ENTRIES: 0, ANNOTATIONS: 0,
                      CONFIRMATIONS: 0, RETRACTIONS: 0},
    "frozen_day": {SESSION_EVENTS: 3, MANUAL_ENTRIES: 1, ANNOTATIONS: 2,
                   CONFIRMATIONS: 0, RETRACTIONS: 0},
    "parallel_agents": {SESSION_EVENTS: 4, MANUAL_ENTRIES: 0, ANNOTATIONS: 0,
                        CONFIRMATIONS: 0, RETRACTIONS: 0},
}
"""The events that each fixture store holds, the counts that pin its scenario: the
events of the sessions, then the declared events by kind; the retraction store counts no
manual entry, because its retraction cancels the one that it wrote."""

STORE_STATES = {
    "measured_day": (declared.MEASURED_DAY,),
    "declared_day": (declared.DECLARED_DAY,),
    "manual_entries": (declared.MEASURED_DAY,),
    "annotations": (declared.MEASURED_DAY,),
    "retraction": (declared.MEASURED_DAY,),
    "frozen_period": (declared.MEASURED_DAY, declared.MEASURED_DAY),
    "frozen_day": (declared.MEASURED_DAY,),
    "parallel_agents": (declared.MEASURED_DAY,),
}
"""The state of each day of each store: only the declared day holds a confirmation that
no retraction cancels; every other day is measured."""


HELP_COMMANDS: dict[str, tuple[str, ...]] = {
    "main": (),
    "setup": ("setup",),
    "schedule-show": ("schedule", "show"),
    "schedule-create": ("schedule", "create"),
    "schedule-remove": ("schedule", "remove"),
    "ingest": ("ingest",),
    "machine-label": ("machine", "label"),
    "config-show": ("config", "show"),
    "config-add": ("config", "add"),
    "sessions": ("sessions",),
    "annotate": ("annotate",),
    "entry-add": ("entry", "add"),
    "timesheet": ("timesheet",),
    "entries": ("entries",),
    "retract": ("retract",),
    "purge": ("purge",),
    "report-timesheet": ("report", "timesheet"),
    "report-day": ("report", "day"),
    "frozen-list": ("frozen", "list"),
    "frozen-show": ("frozen", "show"),
    "frozen-remove": ("frozen", "remove"),
    "index-rebuild": ("index", "rebuild"),
    "version": ("version",),
}
"""The words before `--help` of each help that has an expected file, `help_<name>.txt`, by
its name: the main command, and each of the 22 parsers of a command of command-line.md ›
Commands. `timesheet` is one parser for `timesheet <day>`, `timesheet confirm`, and
`timesheet retract`, whose word the command reads after the parse; the parser of a group,
such as `schedule`, runs no command, and its words show in the listing of `--help`."""


def _expected(name: str, kind: str, language: str) -> str:
    """The expected output of one report in the language, as its file of the expected
    folder of that language holds it: written by hand from the definition of the fixture
    store and the layout of the text (command-line.md › Output), with the marks of
    `normalize` where the output holds a value that differs at each run."""
    return (EXPECTED / language / f"{name}.{kind}").read_text(encoding="utf-8")


def _no_name_of_the_world(case: unittest.TestCase, home: Path, masked: str) -> None:
    """The guard of every compared output: no line of it holds the name of the temporary
    folder of its world, in no language and no mode. That folder is the home itself, or the
    folder below which a fixture store builds its home. `normalize` masks a path only where
    it begins at the root of the world, so a path that the context computes from a system
    other than the running one keeps the random name of the temporary folder in its text
    and no expected file can hold it; the message shows the line that holds the name."""
    name = next(one.name for one in (home, *home.parents)
                if one.name.startswith(support.TEMPORARY_PREFIX))
    for line in masked.split("\n"):
        if name in line:
            case.fail(f"the name of the temporary folder of the world, {name},"
                      f" is in the output: {line}")


def _assert_pair(
    case: unittest.TestCase, name: str,
    words: Sequence[str] | Callable[[Path], Sequence[str]],
    world: Callable[[], tuple[Context, Path]], *, fresh: bool = False,
    by_cells: bool = False,
    after: Callable[[Context, Path, str, str], None] | None = None,
    kinds: Sequence[str] = ("txt", "json"),
) -> dict[str, str]:
    """The comparison rule of the output tests, the one place that runs a command and
    compares its output with its expected files. In each language, `world` gives a context
    and a home, and the words, or the words that `words` gives for the home when it is a
    function, for a command that names a folder of its world, run on them in text and with
    `--json`, with the home as the working folder: each run ends with the exit code 0, and
    its output, through `normalize` with the home as the root, holds no name of the
    temporary folder of its world (`_no_name_of_the_world`) and equals the expected file of
    `name` in the language, the text cell by cell (`support.cells`) when `by_cells` is
    true, for a table that holds an absolute path. The two modes run on one world, or,
    when `fresh` is true, each on a world of its own, for a command that changes what its
    own output shows. The standard error of the text run, normalized with its home, equals
    that of the JSON run. Returns that standard error by language. When `after` is given,
    each run calls it, after its comparison and inside its subtest, with the context and
    the home of the run's world, the mode (`txt` or `json`), and the standard output as the
    command wrote it, so that a test checks the state that the run left. `kinds` gives the
    modes that the command has: the help has no JSON document (command-line.md › JSON
    documents), so its pair runs the text alone, and no standard error of another mode is
    compared."""
    errors: dict[str, str] = {}
    for chosen in LANGUAGES:
        spoken = () if chosen == "en" else ("--language", chosen)
        held: dict[str, str] = {}
        for kind in kinds:
            with case.subTest(language=chosen, kind=kind):
                if kind == "txt" or fresh:
                    context, home = world()
                extra = ("--json",) if kind == "json" else ()
                said = words(home) if callable(words) else words
                with contextlib.chdir(home):
                    code, shown, error = support.run_main(context, *said, *spoken, *extra)
                held[kind] = support.normalize(error, [home])
                case.assertEqual(code, 0, error)
                masked = support.normalize(shown, [home])
                _no_name_of_the_world(case, home, masked)
                expected = support.normalize(_expected(name, kind, chosen), [home])
                if by_cells and kind == "txt":
                    masked, expected = support.cells(masked), support.cells(expected)
                case.assertEqual(masked, expected)
                if after is not None:
                    after(context, home, kind, shown)
        if "json" in held:
            with case.subTest(language=chosen, stream="standard error"):
                case.assertEqual(held["json"], held["txt"])
        errors[chosen] = held["txt"]
    return errors


class FixtureStoreTests(support.FixtureStores):
    """The eight fixture stores build, hold the events of their scenario, and give the
    states of their days; the frozen period holds one frozen report and a later rule
    change, the frozen day a frozen report at another minimum attention and a manual
    entry after the freeze, and the parallel agents a person whose agent time is longer
    than the clock time in which its agents work; `normalize` masks what differs at each
    run and on another operating system."""

    def test_normalize_masks_per_run_values(self) -> None:
        """`normalize` replaces with fixed marks the paths below the roots, as a table
        prints them and as JSON escapes them, the bytes read and the chained hash of
        each segment of the report record, and every tzdata version, and folds the line
        ends; the name of a segment, which no run and no system changes, stays."""
        home = self._homes["measured_day"]
        version = days.tzdata_version()
        held = support.store_figures(
            self._contexts["measured_day"], support.fixture_store_folder(home),
            *support.FIXTURE_PERIODS["measured_day"]).selection.segments[0]
        cwd = home / support.FIXTURE_WORK_FOLDER / "alpha"
        text = "\n".join([
            f"session-alpha  claude-code  {cwd}  2:00\r",
            json.dumps({"cwd": str(cwd), "new_events": 3}),
            json.dumps({"record": {"segments": [
                {"segment": held.segment, "size": held.size,
                 "chained_hash": held.chained_hash}], "tzdata": version}}),
            f"tzdata: {version}",
        ])
        normalized = support.normalize(text, [home])
        self.assertEqual(normalized, "\n".join([
            "session-alpha  claude-code  <root>/work/alpha  2:00",
            '{"cwd": "<root>/work/alpha", "new_events": 3}',
            '{"record": {"segments": [{"segment": "segments/machine-one/2026-11.jsonl",'
            ' "size": <bytes>, "chained_hash": <hash>}], "tzdata": <tzdata>}}',
            "tzdata: <tzdata>",
        ]))
        self.assertEqual(support.normalize(normalized, [home]), normalized)

    def test_cells_of_a_table_that_holds_a_path(self) -> None:
        """`cells` gives the cells of each line of a text, the parts that two or more spaces
        separate: the column of a table that holds an absolute path is as wide as the path
        of the machine, and `normalize` masks the path only after the layout is made, so
        the text of such a table compares cell by cell — a header padded for a path of
        another length gives the cells of the expected file, and a cell that differs from
        the expected one makes the comparison fail."""
        home = self._homes["measured_day"]
        cwd = str(home / support.FIXTURE_WORK_FOLDER / "alpha")
        width = len(cwd)
        # the expected file is padded for a path one column longer than the one of the
        # machine, so that the two headers differ whatever the machine
        expected = "\n".join([
            "Session  " + "Folder".ljust(width + 1) + "  Branch",
            "session  <root>/work/alpha" + " " * 2 + "main",
        ]) + "\n"
        output = support.normalize("\n".join([
            "Session  " + "Folder".ljust(width) + "  Branch",
            "session  " + cwd + " " * 2 + "main",
        ]) + "\n", [home])
        self.assertNotEqual(output, expected)
        self.assertEqual(support.cells(output), [
            ["Session", "Folder", "Branch"],
            ["session", "<root>/work/alpha", "main"],
            []])
        self.assertEqual(support.cells(output), support.cells(expected))
        other = expected.replace("main", "feat")
        self.assertNotEqual(support.cells(output), support.cells(other))
        self.assertEqual(support.cells("A  B  \n\n  C\n"), [["A", "B"], [], ["C"], []])

    def test_each_fixture_store_builds(self) -> None:
        """Every name of the fixture stores gives a store that `figures_of_days` reads:
        the selection holds the events of its sessions and the declared events of its
        scenario, and no store holds a configuration error."""
        for name in support.FIXTURE_NAMES:
            with self.subTest(store=name):
                figures = support.store_figures(
                    self._contexts[name], support.fixture_store_folder(self._homes[name]),
                    *support.FIXTURE_PERIODS[name])
                selection = figures.selection
                held = {SESSION_EVENTS: len(selection.session_events),
                        MANUAL_ENTRIES: len(selection.manual_entries),
                        ANNOTATIONS: len(selection.annotations),
                        CONFIRMATIONS: len(selection.confirmations),
                        RETRACTIONS: len(selection.retractions)}
                self.assertEqual(held, STORE_EVENTS[name])
                self.assertEqual(figures.attribution.configuration_errors, [])

    def test_states_of_the_fixture_days(self) -> None:
        """measured_day "measured", declared_day "declared": every store holds the days
        of its period, in the order of the days, with the state of its scenario."""
        for name in support.FIXTURE_NAMES:
            with self.subTest(store=name):
                figures = support.store_figures(
                    self._contexts[name], support.fixture_store_folder(self._homes[name]),
                    *support.FIXTURE_PERIODS[name])
                first, last = support.FIXTURE_PERIODS[name]
                span = (last - first).days + 1
                self.assertEqual([one.timesheet.day for one in figures.days],
                                 [first + timedelta(days=one) for one in range(span)])
                self.assertEqual([one.timesheet.state for one in figures.days],
                                 list(STORE_STATES[name]))

    def test_agents_in_parallel_work_longer_than_the_clock(self) -> None:
        """The store of the parallel agents: the agent time of the person is the sum
        over its two agents, 1 200 000 + 600 000 = 1 800 000 ms, over the union of the
        agent intervals behind it — the Supervised time plus the Unattended time of the
        person, 600 000 + 600 000 = 1 200 000 ms — so the agent time is longer than the
        clock time in which the agents work and the parallel ratio is 1.5 (metrics.md ›
        Agent time, › Quantities)."""
        figures = support.store_figures(
            self._contexts["parallel_agents"],
            support.fixture_store_folder(self._homes["parallel_agents"]),
            *support.FIXTURE_PERIODS["parallel_agents"])
        person = figures.days[0].person
        self.assertEqual(person.agent_time, 1_800_000)
        self.assertEqual(person.activity_classes["supervised"]
                         + person.activity_classes["unattended"], 1_200_000)

    def test_frozen_period_has_a_later_rule_change(self) -> None:
        """One frozen report, of `report timesheet` over its two days, with the note and
        the instant of the freeze; the record of the frozen report holds no rule for
        `beta`, and the person configuration of the store holds it now, so a report of
        now resolves the second day to `beta`, where the frozen one resolved it to the
        repository identity itself."""
        home = self._homes["frozen_period"]
        store = support.fixture_store_folder(home)
        rows, warnings = reports.frozen_list(store)
        self.assertEqual((len(rows), warnings), (1, []))
        row = rows[0]
        self.assertEqual(row["id"], support.build_uid(1))
        self.assertEqual(row["machine"], support.FIXTURE_MACHINE)
        self.assertEqual(row["report"], "report timesheet")
        self.assertEqual(row["from"], support.FIXTURE_DAY_ONE.isoformat())
        self.assertEqual(row["to"], support.FIXTURE_DAY_TWO.isoformat())
        self.assertEqual(row["note"], support.FIXTURE_NOTES["frozen"])
        self.assertEqual(row["frozen_at"], format_instant(support.FIXTURE_NOW))
        envelope = json.loads((store / "frozen" / support.FIXTURE_MACHINE
                               / f"{row['id']}.json").read_text(encoding="utf-8"))
        document = envelope["document"]
        self.assertEqual([rule["project"]
                          for rule in document["record"]["identity_rules"]], ["alpha"])
        self.assertEqual(document["days"][1]["entries"][0]["project"],
                         {"id": "example.com/acme/beta", "name": "beta"})
        person = read_person_configuration(store)
        self.assertEqual([rule.project for rule in person.identity_rules],
                         ["alpha", "beta"])
        figures = support.store_figures(
            self._contexts["frozen_period"], store, *support.FIXTURE_PERIODS["frozen_period"])
        self.assertEqual(figures.days[1].timesheet.lines[0].bucket, ("beta", None))

    def test_frozen_day_holds_a_frozen_report_and_a_later_entry(self) -> None:
        """One frozen report, of `report day` of the day, kept at a minimum attention of
        two minutes and with no note; after the freeze the store holds one manual entry of
        an hour on the work item `story-1`, so the figures of now differ from the frozen
        ones (the scenario of the expected pair `report-day_frozen_day`)."""
        home = self._homes["frozen_day"]
        store = support.fixture_store_folder(home)
        rows, _ = reports.frozen_list(store)
        self.assertEqual(rows, [{
            "id": support.build_uid(3), "report": "report day",
            "from": support.FIXTURE_DAY_ONE.isoformat(), "to": support.FIXTURE_DAY_ONE.isoformat(),
            "machine": support.FIXTURE_MACHINE,
            "frozen_at": format_instant(support.FIXTURE_NOW)}])
        envelope = json.loads((store / "frozen" / support.FIXTURE_MACHINE
                               / f"{support.build_uid(3)}.json").read_text(encoding="utf-8"))
        self.assertEqual(list(envelope), ["document", "frozen_at"])
        frozen = envelope["document"]
        self.assertEqual(list(frozen), ["day", "state", "unknown_invocation_share",
                                        "human_time_at_idle_gaps", "person", "projects",
                                        "work_items", "record", "command", "warnings",
                                        "configuration_errors", "frozen_id"])
        self.assertEqual(frozen["record"]["parameters"]["minimum_attention"], 120)
        self.assertEqual(frozen["person"]["activity_classes"]["idle"], 84960)
        figures = support.store_figures(
            self._contexts["frozen_day"], store, *support.FIXTURE_PERIODS["frozen_day"])
        self.assertEqual([one.bucket for one in figures.days[0].timesheet.lines],
                         [("alpha", "story-1"), ("beta", "story-2")])
        self.assertEqual(figures.days[0].person.activity_classes["idle"], 81480 * 1000)


class ReportOutputTests(support.FixtureStores):
    """The output of the commands that read the store on the fixture stores, in English
    and in Italian, against the expected files (architecture.md › Tests › Report tests;
    command-line.md › Form, › Output, › Reports, › Frozen reports, › JSON documents):
    `report timesheet`, `report day`, `timesheet <day>`, `sessions <day>`, `entries
    <day>`, `frozen list`, and `frozen show` in text and in JSON, each output compared
    with its expected file through `support.normalize`. A pair runs in both languages:
    the Italian run adds `--language it` to the words of the command, which stay the
    same otherwise, and reads the twin of the folder `it`. The text of `sessions`
    compares cell by cell, because its column of the folders is as wide as the absolute
    path of the machine. Every shape that the commands show is in at least one expected
    file: a measured day, a declared day, manual entries — also in `report day`, where
    an overlapping entry moves the measured minute of a project to another, in its human
    time and in its classes —, work items, a report with its differences against a frozen
    report — of its own command, with the leaf rows of a composite figure, and of another
    command —, the sentence on the activity classes that the text of `report day` holds,
    the sessions of a day, the declared events, a frozen report with its differences, and
    a report with `--freeze`, on a store that each language and each mode builds for
    itself because the freeze changes it. The fixture stores that the pairs only read are
    built once for both languages.
    The warnings and configuration errors of a report go to the standard error, never into
    the expected file of the standard output."""

    def _assert_output(
        self, name: str, store: str, *words: str, by_cells: bool = False
    ) -> dict[str, str]:
        """The command on the fixture store, compared with its expected files by
        `_assert_pair` on the context and the home that the store holds; the test gets the
        lines on the standard error by language."""
        return _assert_pair(
            self, name, words, lambda: (self._contexts[store], self._homes[store]),
            by_cells=by_cells)

    def test_report_timesheet_of_a_measured_day(self) -> None:
        """`report timesheet` of a period of one measured day: the state of the day, its
        total and its measured total, one entry for the project of its human time with
        no declared value, the share of the unknown invocation, and the human time at the
        idle gaps (command-line.md › Reports, › JSON documents)."""
        self._assert_output("report-timesheet_measured_day", "measured_day",
                            "report", "timesheet", "--from",
                            support.FIXTURE_DAY_ONE.isoformat(), "--to",
                            support.FIXTURE_DAY_ONE.isoformat())

    def test_report_timesheet_of_a_declared_day(self) -> None:
        """`report timesheet` of a declared day: the declared value in its column, the
        total of the declared entries under it, and no human time at the idle gaps
        (command-line.md › Reports; metrics.md › Declared values)."""
        self._assert_output("report-timesheet_declared_day", "declared_day",
                            "report", "timesheet", "--from",
                            support.FIXTURE_DAY_THREE.isoformat(), "--to",
                            support.FIXTURE_DAY_THREE.isoformat())

    def test_report_timesheet_with_manual_entries(self) -> None:
        """`report timesheet` of a day with a manual entry of each mode: the entry in
        mode `overlapping` takes the measured human time of the other project into its
        project, so that the two columns of a line can differ, and the day keeps the
        measured total beside its total; the warning about the overlap goes to the
        standard error in both modes, in the language of the output (metrics.md ›
        Declared values, command-line.md › Output)."""
        errors = self._assert_output("report-timesheet_manual_entries", "manual_entries",
                                     "report", "timesheet", "--from",
                                     support.FIXTURE_DAY_ONE.isoformat(), "--to",
                                     support.FIXTURE_DAY_ONE.isoformat())
        uid = support.build_uid(1)
        self.assertEqual(errors, {
            "en": f"warning: The manual entry {uid} overlaps measured human time.\n",
            "it": f"warning: La registrazione manuale {uid} si sovrappone al tempo persona"
                  " misurato.\n",
        })

    def test_report_timesheet_with_work_items(self) -> None:
        """`report timesheet` of a day whose time two annotations give to work items: one
        line for each project and work item, with the name of the work item
        (command-line.md › Reports)."""
        self._assert_output("report-timesheet_annotations", "annotations",
                            "report", "timesheet", "--from",
                            support.FIXTURE_DAY_ONE.isoformat(), "--to",
                            support.FIXTURE_DAY_ONE.isoformat())

    def test_report_timesheet_of_a_frozen_period_shows_the_differences(self) -> None:
        """`report timesheet` of the period that a frozen report holds: one group of
        sections for each day of the period, then the figures that differ from the frozen
        report, the identity rule that changed between the two report records and, in
        Italian, the row of the language of the record, `en` against `it`
        (command-line.md › Reports, › Frozen reports, › JSON documents)."""
        self._assert_output("report-timesheet_frozen_period", "frozen_period",
                            "report", "timesheet", "--from",
                            support.FIXTURE_DAY_ONE.isoformat(), "--to",
                            support.FIXTURE_DAY_TWO.isoformat())

    def test_report_day_of_a_measured_day(self) -> None:
        """`report day` of a measured day: the human time, the agent time, the blocked
        time, and the activity classes of the person, of each project, and of each work
        item of the day — the work items table with its header alone when the day holds
        none —, then the sentence that the activity classes of the projects and of the
        work items do not always add up to those of the person, then the share of the
        unknown invocation and the human time at the idle gaps (command-line.md › Reports,
        › JSON documents)."""
        self._assert_output("report-day_measured_day", "measured_day",
                            "report", "day", support.FIXTURE_DAY_ONE.isoformat())

    def test_report_day_with_manual_entries(self) -> None:
        """`report day` of the day of `manual_entries`, which holds one manual entry of
        `beta` in mode `overlapping` over the measured minute of `alpha` and one in mode
        `additional`: the human time of the person is the human time of the day with
        manual entries, 2400 seconds, and so is the human time of each project — the
        overlapping entry takes the measured minute of Alpha to Beta, so Alpha shows a
        human time of 0:00. The activity classes of each project come from that human
        time, as the classes of the person do, so Alpha shows no class person only beside
        its human time of 0:00 and Beta a class person only of 0:40 beside its human time
        of 0:40; the 0:05 of agent time stay Alpha's, unattended (GLOSSARY.md › Measured
        day; metrics.md › Activity classes, › Declared values). The warning about the
        overlap goes to the standard error in both languages (command-line.md › Output)."""
        errors = self._assert_output("report-day_manual_entries", "manual_entries",
                                     "report", "day", support.FIXTURE_DAY_ONE.isoformat())
        uid = support.build_uid(1)
        self.assertEqual(errors, {
            "en": f"warning: The manual entry {uid} overlaps measured human time.\n",
            "it": f"warning: La registrazione manuale {uid} si sovrappone al tempo persona"
                  " misurato.\n",
        })

    def test_report_day_with_work_items(self) -> None:
        """`report day` of a day with two projects and two work items: one row for each
        project and one for each work item, with the activity classes that each one
        holds; a bucket holds no class idle (metrics.md › Activity classes)."""
        self._assert_output("report-day_annotations", "annotations",
                            "report", "day", support.FIXTURE_DAY_ONE.isoformat())

    def test_report_day_of_a_declared_day(self) -> None:
        """`report day` of a declared day holds no human time at the idle gaps; its
        figures are the measured ones, the evidence of the declared day (command-line.md
        › JSON documents; metrics.md › Declared values)."""
        self._assert_output("report-day_declared_day", "declared_day",
                            "report", "day", support.FIXTURE_DAY_THREE.isoformat())

    def test_report_day_of_a_frozen_period_shows_the_differences(self) -> None:
        """`report day` of a day that a frozen report of `report timesheet` holds: the two
        documents hold under the same name only the share of the unknown invocation and
        the human time at the idle gaps, which are equal, so the table of the differences
        holds its header alone; the identity rule that changed is the one row of `changed`
        in English, and in Italian `changed` holds also the row of the language of the
        record, `en` against `it` (command-line.md › Reports, › Frozen reports)."""
        self._assert_output("report-day_frozen_period", "frozen_period",
                            "report", "day", support.FIXTURE_DAY_TWO.isoformat())

    def test_report_day_of_a_frozen_day_shows_the_leaf_rows(self) -> None:
        """`report day` against a frozen `report day` of its own day, computed at another
        minimum attention and before a manual entry of an hour on the work item `story-1`:
        the human time of the person, of Alpha, and of Story One of now holds the manual
        entry, and every figure of the person, of each project, and of each work item
        that differs gives its row, a composite figure gives one row for each scalar leaf
        that differs — the human time at each idle gap, the class person only, the class
        idle —, each leaf as a duration in H:MM, and the report parameter that changed is
        a row of `changed`, which in Italian holds also the row of the language of the
        record, `en` against `it` (command-line.md › Reports, › Frozen reports, › Output)."""
        self._assert_output("report-day_frozen_day", "frozen_day",
                            "report", "day", support.FIXTURE_DAY_ONE.isoformat())

    def test_report_day_of_agents_in_parallel(self) -> None:
        """`report day` of the day of the parallel agents: the agent time of the person
        is 1800 seconds over a union of 1200, so its parallel ratio is 1.50 beside its
        agent time of 0:30, and each project holds 1200 over 1200 and 600 over 600,
        ratio 1.00; the human time of the person is 660 seconds — Alpha the 60 seconds
        of the minimum attention before its prompt, Beta the 600 seconds of the signal
        gap that belongs to the later prompt — the person is supervised 600 seconds and
        unattended 600, and the classes of the projects do not add up to those of the
        person (metrics.md › Agent time; command-line.md › Reports)."""
        self._assert_output("report-day_parallel_agents", "parallel_agents",
                            "report", "day", support.FIXTURE_DAY_ONE.isoformat())

    def test_timesheet_of_agents_in_parallel(self) -> None:
        """`timesheet <day>` of the day of the parallel agents: the context holds the
        agent time of the day, 1800 seconds as 0:30, its parallel ratio 1.50 beside it,
        and the presence span of 600 seconds as 0:10; the entries hold Alpha 60 seconds
        and Beta 600, each proposed 900 at the granularity, and the total is 660
        (command-line.md › Commands, › Reports)."""
        self._assert_output("timesheet_parallel_agents", "parallel_agents",
                            "timesheet", support.FIXTURE_DAY_ONE.isoformat())

    def test_report_day_shows_the_human_time_with_manual_entries(self) -> None:
        """`report day` of the day of `frozen_day`, which holds a manual entry of an hour
        on the work item `story-1`: the human time of the person, of each project, and of
        each work item is the measured human time with manual entries — Alpha 3660 + Beta
        60 = 3720 seconds, the person as much, which is the total of the timesheet of the
        day —, and the activity classes of Alpha and of Story One come from that human
        time: their class person only holds the measured minute and the hour of the entry,
        3660 seconds (GLOSSARY.md › Measured day; metrics.md › Activity classes, ›
        Declared values)."""
        context = self._contexts["frozen_day"]
        one = support.FIXTURE_DAY_ONE.isoformat()
        code, shown, error = support.run_main(context, "report", "day", one, "--json")
        self.assertEqual(code, 0, error)
        document = json.loads(shown)
        self.assertEqual(document["person"]["human_time"], 3720)
        self.assertEqual([(row["project"]["id"], row["human_time"])
                          for row in document["projects"]], [("alpha", 3660), ("beta", 60)])
        self.assertEqual([(row["work_item"]["id"], row["human_time"])
                          for row in document["work_items"]],
                         [("story-1", 3660), ("story-2", 60)])
        self.assertEqual([row["activity_classes"]["person_only"]
                          for row in document["projects"]], [3660, 60])
        code, shown, error = support.run_main(
            context, "report", "timesheet", "--from", one, "--to", one, "--json")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(shown)["days"][0]["total"], 3720)

    def test_report_day_classes_add_up_to_the_human_time_of_every_holder(self) -> None:
        """For every holder of every fixture store — the person, each project, each work
        item — and on every day of the period of the store, the JSON document of `report
        day` gives `person_only + supervised == human_time`: the activity classes of every
        holder come from its measured human time with manual entries, in whole seconds as
        in milliseconds (metrics.md › Activity classes; command-line.md › Reports). For the
        person the five classes add up to the length of its day, 86 400 seconds on every
        fixture day, which lies in `Etc/UTC` with the day start at 00:00 (metrics.md › Days
        and weeks)."""
        for name in support.FIXTURE_NAMES:
            first, last = support.FIXTURE_PERIODS[name]
            for offset in range((last - first).days + 1):
                day = (first + timedelta(days=offset)).isoformat()
                code, shown, error = support.run_main(
                    self._contexts[name], "report", "day", day, "--json")
                self.assertEqual(code, 0, f"{name} {day}: {error}")
                document = json.loads(shown)
                with self.subTest(store=name, day=day):
                    holders = [document["person"], *document["projects"],
                               *document["work_items"]]
                    for held in holders:
                        classes = held["activity_classes"]
                        self.assertEqual(
                            classes["person_only"] + classes["supervised"],
                            held["human_time"], held)
                    self.assertEqual(
                        sum(document["person"]["activity_classes"].values()), 86_400)

    def test_report_day_with_freeze_ends_with_its_identifier(self) -> None:
        """`report day --freeze` on a store that holds no frozen report: the text is the
        report of the day, then the line of the identifier of the frozen report; the JSON
        output is the document of the file that the command keeps, with the instant of the
        freeze and no note (command-line.md › Frozen reports). The freeze changes the
        store, so each language and each mode runs on a store of its own."""
        one = support.FIXTURE_DAY_ONE.isoformat()
        identifier = support.FIXTURE_FIRST_UID

        def world() -> tuple[Context, Path]:
            folder = support.TemporaryFolder()
            home = folder.__enter__()
            self.addCleanup(folder.__exit__, None, None, None)
            return support.fixture_store("measured_day", home), home

        def kept(_: Context, home: Path, kind: str, shown: str) -> None:
            path = (support.fixture_store_folder(home) / "frozen"
                    / support.FIXTURE_MACHINE / f"{identifier}.json")
            envelope = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(list(envelope), ["document", "frozen_at"])
            self.assertEqual(envelope["frozen_at"], "2026-11-24T12:00:00.000Z")
            self.assertEqual(envelope["document"]["frozen_id"], identifier)
            if kind == "json":
                self.assertEqual(json.loads(shown), envelope["document"])

        errors = _assert_pair(self, "report-day-freeze_measured_day",
                              ("report", "day", one, "--freeze"), world, fresh=True,
                              after=kept)
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_sessions_of_a_day_with_work_items(self) -> None:
        """`sessions <day>` of a day with two sessions: each with its identifier, its agent
        tool, the instant of its first and of its last event of the day, its folder, and
        one line for each project and work item of the session with the human time and the
        agent time of the day; no record of the fixtures holds a branch, so the document
        holds none and the cell stays empty (command-line.md › Commands, › JSON documents).
        The column of the folders is as wide as the absolute path of the store, which differs
        from one machine to the next, so the text compares cell by cell."""
        self._assert_output("sessions_annotations", "annotations",
                            "sessions", support.FIXTURE_DAY_ONE.isoformat(), by_cells=True)

    def test_entries_of_two_annotations(self) -> None:
        """`entries <day>` of the day of the instants of the declared events: the session
        annotation and the interval annotation, each with `event_uid`, `kind`, and
        `timestamp` first and its other fields by name; a field that one entry does not
        hold leaves the cell empty, and the session that an annotation names shows as its
        JSON text in one cell; the store holds the machine label `FIXTURE_LABEL`, which the
        column Machine of the text shows, while the document keeps the identifier
        (command-line.md › Commands, › JSON documents)."""
        self._assert_output("entries_annotations", "annotations", "entries",
                            support.FIXTURE_NOW.date().isoformat())

    def test_entries_of_a_declared_day(self) -> None:
        """`entries <day>` of a declared day: the timesheet confirmation of the day, whose
        entries show as one cell of JSON; the store holds no machine label, so the column
        Machine of the text shows the identifier (command-line.md › Commands, › JSON
        documents)."""
        self._assert_output("entries_declared_day", "declared_day", "entries",
                            support.FIXTURE_DAY_THREE.isoformat())

    def test_frozen_list_of_the_frozen_period(self) -> None:
        """`frozen list`: one row for the frozen report of the store, with its identifier,
        its command, the first and the last day of its period, its note, its machine with
        the machine label `FIXTURE_LABEL` that the store holds for it, and the instant of
        the freeze; the column Machine of the text shows the label (command-line.md ›
        Frozen reports, › JSON documents)."""
        self._assert_output("frozen-list_frozen_period", "frozen_period", "frozen", "list")

    def test_frozen_show_of_the_frozen_period(self) -> None:
        """`frozen show <id>`: the frozen report under a title line that names it and its
        command, then the figures that differ from the report of now over its days, the
        identity rule that changed between the two report records and, in Italian, the
        row of the language of the record, `en` against `it` (command-line.md ›
        Frozen reports, › JSON documents)."""
        self._assert_output("frozen-show_frozen_period", "frozen_period",
                            "frozen", "show", support.build_uid(1))

    def test_entries_lists_the_manual_entries_and_the_retraction(self) -> None:
        """The manual entries and the retraction show no shape that the expected files of
        `entries` do not hold, so a behaviour covers each: the two manual entries of a
        store are listed with their mode, their interval, their project, and their note,
        in both modes; the retraction of a manual entry is listed beside the entry that it
        cancels, and its cell holds the key of the entry as its JSON text (command-line.md
        › Commands)."""
        moment = support.FIXTURE_NOW.date().isoformat()
        context = self._contexts["manual_entries"]
        code, shown, error = support.run_main(context, "entries", moment, "--json")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(shown)["entries"], [
            {"event_uid": support.build_uid(1), "kind": "manual_entry",
             "timestamp": "2026-11-24T12:00:00.000Z", "actor": "human",
             "end": "2026-11-20T09:10:00.000Z", "ingested_at": "2026-11-24T12:00:00.000Z",
             "machine": support.FIXTURE_MACHINE, "note": support.FIXTURE_NOTES["overlapping"],
             "project": "beta", "schema_version": 1, "source": "ledger",
             "start": "2026-11-20T08:50:00.000Z", "manual_mode": "overlapping",
             "writer_version": "0.1.0"},
            {"event_uid": support.build_uid(2), "kind": "manual_entry",
             "timestamp": "2026-11-24T12:00:00.000Z", "actor": "human",
             "end": "2026-11-20T09:50:00.000Z", "ingested_at": "2026-11-24T12:00:00.000Z",
             "machine": support.FIXTURE_MACHINE, "note": support.FIXTURE_NOTES["additional"],
             "project": "beta", "schema_version": 1, "source": "ledger",
             "start": "2026-11-20T09:30:00.000Z", "manual_mode": "additional",
             "writer_version": "0.1.0"}])
        code, shown, error = support.run_main(context, "entries", moment)
        self.assertEqual(code, 0, error)
        self.assertEqual(shown.split("\n\n")[0].splitlines()[0], f"{moment}  Events")
        for text in ("Mode", "overlapping", "additional", "beta",
                     support.FIXTURE_NOTES["overlapping"], support.FIXTURE_NOTES["additional"]):
            self.assertIn(text, shown)
        context = self._contexts["retraction"]
        code, shown, error = support.run_main(context, "entries", moment, "--json")
        self.assertEqual(code, 0, error)
        entries = json.loads(shown)["entries"]
        self.assertEqual([entry["kind"] for entry in entries], ["manual_entry", "retraction"])
        self.assertEqual(entries[1]["retracts"],
                         {"source": "ledger", "event_uid": support.build_uid(1)})
        code, shown, error = support.run_main(context, "entries", moment)
        self.assertEqual(code, 0, error)
        self.assertIn('{"event_uid": "' + support.build_uid(1) + '", "source": "ledger"}',
                      shown)
        self.assertIn(support.FIXTURE_NOTES["retracted"], shown)

    def test_timesheet_of_a_measured_day_shows_the_proposal(self) -> None:
        """`timesheet <day>` of a measured day: the entries of the day with the proposed
        value of each one, rounded up to the timesheet granularity, the agent time and
        the presence span of the day as context, the share of the unknown invocation, and
        the human time at the idle gaps; no differences (command-line.md › Commands, ›
        Timesheet, › JSON documents)."""
        self._assert_output("timesheet_measured_day", "measured_day",
                            "timesheet", support.FIXTURE_DAY_ONE.isoformat())

    def test_timesheet_of_a_declared_day_shows_the_entries(self) -> None:
        """`timesheet <day>` of a declared day: the timesheet entries of the day with the
        measured values next to them, and the proposed value equal to the declared one
        (command-line.md › Commands, › Timesheet)."""
        self._assert_output("timesheet_declared_day", "declared_day",
                            "timesheet", support.FIXTURE_DAY_THREE.isoformat())

    def test_timesheet_with_work_items(self) -> None:
        """`timesheet <day>` of a day with work items: the name of each work item beside
        its project, and the proposal of each one (command-line.md › Reports)."""
        self._assert_output("timesheet_annotations", "annotations",
                            "timesheet", support.FIXTURE_DAY_ONE.isoformat())


INVENTED_KEY = '{"source": "invented-source", "native_id": "invented-record"}'
"""The event key, as its JSON object, of a source that no folder of native logs of the
machine configuration feeds (command-line.md › Purge)."""

ANNOTATION_NOTE = "Invented note of the annotation of the output tests."
"""The note of the annotation that the pair `annotate_measured_day` writes."""


def _lines(kind: str, code: str, values: dict[str, object]) -> dict[str, str]:
    """The line of the standard error of one warning or error, by language, as the
    commands write it: the kind, `warning` or `error`, then the text of its code in the
    language."""
    return {chosen: f"{kind}: {message(code, values, chosen)}\n" for chosen in LANGUAGES}


def _ledger_events(home: Path) -> list[dict]:
    """The events of the source `ledger` that the segments of the fixture store of the home
    hold, in the order of the segments and of their lines."""
    return [event for event, _ in support.stored_events(support.fixture_store_folder(home))
            if event["source"] == "ledger"]


def _written(home: Path) -> dict:
    """The one event that the command of an output test wrote into the fixture store of the
    home: the event whose identifier is the first of the counting maker of the context."""
    [event] = [one for one in _ledger_events(home)
               if one["event_uid"] == support.FIXTURE_FIRST_UID]
    return event


class WriteOutputTests(support.FixtureStores):
    """The output of the commands that write to the store — `annotate`, `entry add`,
    `timesheet confirm`, `timesheet retract`, `retract`, `purge`, `frozen remove`, and
    `report timesheet --freeze` — in English and in Italian, against their expected files
    (architecture.md › Tests › Report tests; command-line.md › Commands, › Timesheet, ›
    Purge, › Frozen reports, › JSON documents), compared by `_assert_pair`. A command that
    writes changes what its next run shows, so each language and each mode runs on a
    fixture store of its own, built afresh: the identifier of the event that the command
    writes, or of its frozen report, is the first that the counting maker of the context
    gives, `support.FIXTURE_FIRST_UID`, unless the world wrote before it. The two pairs of
    `purge` that write nothing run on the store of the class, which they leave as it is.
    Each test also reads the state that its run left in the store."""

    STORES = ("manual_entries",)

    def _fresh(self, name: str) -> Callable[[], tuple[Context, Path]]:
        """A world of its own for each run: the fixture store `name`, built afresh in a
        temporary home that the test removes at its end."""
        def world() -> tuple[Context, Path]:
            folder = support.TemporaryFolder()
            home = folder.__enter__()
            self.addCleanup(folder.__exit__, None, None, None)
            return support.fixture_store(name, home), home
        return world

    def _class_store(self) -> tuple[Context, Path]:
        """The context and the home of the store of the class."""
        return self._contexts["manual_entries"], self._homes["manual_entries"]

    def _assert_one_event(self, name: str, words: Sequence[str], store: str,
                          fields: dict[str, object]) -> None:
        """A command that writes one event shows its identifier, and the store holds that
        event with the fields given; nothing reaches the standard error."""
        def stored(_: Context, home: Path, *__: object) -> None:
            event = _written(home)
            self.assertEqual({key: event.get(key) for key in fields}, fields)

        errors = _assert_pair(self, name, words, self._fresh(store), fresh=True,
                              after=stored)
        self.assertEqual(errors, {"en": "", "it": ""})

    def _assert_confirmation(self, name: str, store: str, day: str,
                             fields: dict[str, object]) -> dict[str, str]:
        """`timesheet confirm <day>` on a fixture store of its own: its output against the
        expected files of `name`, the confirmation with the fields given in the store, and
        the `entries` of its JSON document equal to those of `timesheet <day>` after it, as
        command-line.md › JSON documents says. Returns the standard error by language."""
        def confirmed(context: Context, home: Path, kind: str, shown: str) -> None:
            event = _written(home)
            self.assertEqual({key: event.get(key) for key in fields}, fields)
            if kind == "json":
                code, now, error = support.run_main(context, "timesheet", day, "--json")
                self.assertEqual(code, 0, error)
                self.assertEqual(json.loads(shown)["entries"], json.loads(now)["entries"])

        return _assert_pair(self, name, ("timesheet", "confirm", day), self._fresh(store),
                            fresh=True, after=confirmed)

    def test_annotate_writes_an_annotation_of_a_session(self) -> None:
        """`annotate --session` with a project and a note: the line of the identifier of
        the annotation, and the document that holds it (command-line.md › Commands, ›
        JSON documents); the store holds the annotation of the session of the agent tool
        that holds it."""
        self._assert_one_event(
            "annotate_measured_day",
            ("annotate", "--session", "session-alpha", "--project", "beta", "--note",
             ANNOTATION_NOTE), "measured_day",
            {"kind": "annotation", "annotates": {"tool": "claude-code",
                                                 "session_id": "session-alpha"},
             "project": "beta", "note": ANNOTATION_NOTE})

    def test_entry_add_writes_a_manual_entry(self) -> None:
        """`entry add` of an hour of the day that the session does not cover, in mode
        `additional`: the line of the identifier of the manual entry (command-line.md ›
        Commands); the store holds the entry with its interval in UTC and milliseconds."""
        self._assert_one_event(
            "entry-add_measured_day",
            ("entry", "add", "--from", "2026-11-20T10:00", "--to", "2026-11-20T11:00",
             "--mode", "additional", "--project", "alpha"), "measured_day",
            {"kind": "manual_entry", "start": "2026-11-20T10:00:00.000Z",
             "end": "2026-11-20T11:00:00.000Z", "manual_mode": "additional",
             "project": "alpha"})

    def test_timesheet_confirm_of_a_measured_day(self) -> None:
        """`timesheet confirm` of a measured day confirms its proposal: the line of the
        identifier of the confirmation, then the entries of the day as `timesheet <day>`
        shows them once the day is declared — the declared value of Alpha, 900 seconds,
        and the same proposed value (command-line.md › Timesheet, › JSON documents)."""
        errors = self._assert_confirmation(
            "timesheet-confirm_measured_day", "measured_day",
            support.FIXTURE_DAY_ONE.isoformat(),
            {"kind": "timesheet_confirmation", "day": "2026-11-20",
             "entries": [{"project": "alpha", "duration": 900}], "replaces": None})
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_timesheet_confirm_of_a_day_with_manual_entries(self) -> None:
        """`timesheet confirm` of the day of `manual_entries` confirms the one entry of its
        proposal, Beta at 2700 seconds; the entries of the day hold also Alpha, which the
        confirmation does not hold, with its measured minute, a declared value of zero, and
        no proposed value. The warnings of the day — the manual entry that overlaps
        measured human time, and the declared value of Alpha below its measured human time
        — reach the standard error before the text, in the language of the output
        (command-line.md › Timesheet, › Reports, › Output)."""
        errors = self._assert_confirmation(
            "timesheet-confirm_manual_entries", "manual_entries",
            support.FIXTURE_DAY_ONE.isoformat(),
            {"kind": "timesheet_confirmation",
             "entries": [{"project": "beta", "duration": 2700}], "replaces": None})
        overlap = _lines("warning", "manual_entry_overlap",
                         {"event_uid": support.build_uid(1)})
        below = _lines("warning", "declared_value_below_measured", {"project": "alpha"})
        self.assertEqual(errors, {chosen: overlap[chosen] + below[chosen]
                                  for chosen in LANGUAGES})

    def test_timesheet_confirm_of_a_declared_day(self) -> None:
        """`timesheet confirm` of the declared day confirms its entries again: the new
        confirmation names the one of the build in `replaces`. The build confirmed the day
        an hour before the fixed now of the fixture context, so the new confirmation is the
        latest (metrics.md › Declared values): the entries of the day are its own, equal to
        those of the build, and no warning reaches the standard error (command-line.md ›
        Timesheet)."""
        errors = self._assert_confirmation(
            "timesheet-confirm_declared_day", "declared_day",
            support.FIXTURE_DAY_THREE.isoformat(),
            {"kind": "timesheet_confirmation",
             "entries": [{"project": "alpha", "duration": 900}],
             "replaces": {"source": "ledger", "event_uid": support.build_uid(1)}})
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_timesheet_retract_of_a_declared_day(self) -> None:
        """`timesheet retract` of the declared day retracts its one confirmation: the line
        of the identifier of the retraction (command-line.md › Commands, › Timesheet)."""
        self._assert_one_event(
            "timesheet-retract_declared_day",
            ("timesheet", "retract", support.FIXTURE_DAY_THREE.isoformat()), "declared_day",
            {"kind": "retraction",
             "retracts": {"source": "ledger", "event_uid": support.build_uid(1)}})

    def test_retract_of_an_annotation(self) -> None:
        """`retract` of the session annotation of `annotations` by its identifier: the line
        of the identifier of the retraction (command-line.md › Commands)."""
        self._assert_one_event(
            "retract_annotations", ("retract", support.build_uid(1)), "annotations",
            {"kind": "retraction",
             "retracts": {"source": "ledger", "event_uid": support.build_uid(1)}})

    def _assert_purge(self, name: str, words: Sequence[str],
                      world: Callable[[], tuple[Context, Path]], *, fresh: bool,
                      purged: list[list[dict]]) -> dict[str, str]:
        """`purge` on the worlds given: its output against the expected files of `name`,
        and the store after the run, whose purges hold the keys of `purged`, one list for
        each purge in the order of the store, while no event of the source `ledger` that a
        purge names is left in the segments. Returns the standard error by language."""
        def left(_: Context, home: Path, *__: object) -> None:
            held = _ledger_events(home)
            purges = [event["purged_keys"] for event in held if event["kind"] == "purge"]
            self.assertEqual(purges, purged)
            gone = {key["event_uid"] for keys in purges for key in keys
                    if key["source"] == "ledger"}
            self.assertEqual([event for event in held if event["event_uid"] in gone], [])

        return _assert_pair(self, name, words, world, fresh=fresh, after=left)

    def test_purge_by_key_writes_the_purge(self) -> None:
        """`purge --key … --yes` of a manual entry of the store, by its identifier alone,
        and of a key of a source that no folder of native logs feeds, as its JSON object:
        the keys in the order typed, the second also in `keys_without_source`, the line of
        the purge written, and the warning of the source that no longer exists on the
        standard error (command-line.md › Purge, › JSON documents); the manual entry leaves
        the segments of the machine."""
        words = ("purge", "--key", support.build_uid(1), "--key", INVENTED_KEY,
                 "--reason", "content", "--yes")
        keys = [{"source": "ledger", "event_uid": support.build_uid(1)},
                {"source": "invented-source", "native_id": "invented-record"}]
        errors = self._assert_purge("purge_written", words, self._fresh("manual_entries"),
                                    fresh=True, purged=[keys])
        self.assertEqual(errors, _lines("warning", "purged_key_source_gone",
                                        {"source": "invented-source"}))

    def test_purge_without_yes_and_without_a_terminal_writes_nothing(self) -> None:
        """The same `purge` without `--yes`, and with no terminal on the standard input:
        nobody is asked, the keys and the line of the purge not written, and the warning
        on the standard error; the store does not change (command-line.md › Output, ›
        Purge)."""
        words = ("purge", "--key", support.build_uid(1), "--key", INVENTED_KEY,
                 "--reason", "content")
        errors = self._assert_purge("purge_not_written", words, self._class_store,
                                    fresh=False, purged=[])
        self.assertEqual(errors, _lines("warning", "purged_key_source_gone",
                                        {"source": "invented-source"}))

    def test_purge_with_the_consent_of_the_person(self) -> None:
        """The same `purge` without `--yes`, at a terminal whose person answers `yes`: the
        question of the running context goes to the standard error after the warning, in
        the language of the output, and the standard output holds the keys and the line of
        the purge written, or the JSON document alone (command-line.md › Output, ›
        Purge)."""
        fixture = self._fresh("manual_entries")

        def at_a_terminal() -> tuple[Context, Path]:
            context, home = fixture()
            answered = mock.patch("sys.stdin", io.StringIO("yes\n"))
            answered.start()
            self.addCleanup(answered.stop)
            return context._replace(ask=ask_at_terminal), home

        words = ("purge", "--key", support.build_uid(1), "--key", INVENTED_KEY,
                 "--reason", "content")
        keys = [{"source": "ledger", "event_uid": support.build_uid(1)},
                {"source": "invented-source", "native_id": "invented-record"}]
        errors = self._assert_purge("purge_consent", words, at_a_terminal, fresh=True,
                                    purged=[keys])
        gone = _lines("warning", "purged_key_source_gone", {"source": "invented-source"})
        self.assertEqual(errors, {chosen: gone[chosen] + question("purge_consent", chosen)
                                  for chosen in LANGUAGES})

    def test_purge_by_writer_version_holds_no_key_of_a_purge(self) -> None:
        """`purge --writer-version-below` a version above the one that wrote every event of
        a store that holds one purge already — of an annotation, written by key before the
        run: the keys of the two events of the session and of the two manual entries, in
        the order of their timestamps, and no key of the purge or of the annotation that
        it removed (command-line.md › Purge); the purge with a corrected version is
        written, and no warning."""
        fixture = self._fresh("manual_entries")

        def with_a_purge() -> tuple[Context, Path]:
            context, home = fixture()
            for words in (("annotate", "--from", "2026-11-20T12:00", "--to",
                           "2026-11-20T13:00", "--project", "alpha"),
                          ("purge", "--key", support.FIXTURE_FIRST_UID, "--reason",
                           "content", "--yes")):
                code, _, error = support.run_main(context, *words)
                self.assertEqual((code, error), (0, ""))
            return context, home

        keys = [{"source": "claude-code-jsonl",
                 "native_id": "7f1c0000-0000-4000-8000-000000000001"},
                {"source": "claude-code-jsonl",
                 "native_id": "response-2026-11-20T09:00"},
                {"source": "ledger", "event_uid": support.build_uid(1)},
                {"source": "ledger", "event_uid": support.build_uid(2)}]
        errors = self._assert_purge(
            "purge_writer-version",
            ("purge", "--writer-version-below", "0.2.0", "--reason", "correction",
             "--corrected-version", "0.3.0", "--yes"), with_a_purge, fresh=True,
            purged=[[{"source": "ledger", "event_uid": support.FIXTURE_FIRST_UID}], keys])
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_purge_by_writer_version_that_selects_no_key(self) -> None:
        """`purge --writer-version-below` a version under the one that wrote every event of
        the store: the selection holds no key, so nothing is written and nobody is asked;
        the command completes with the warning `no_key_selected` (command-line.md ›
        Purge)."""
        errors = self._assert_purge(
            "purge_no-key-selected",
            ("purge", "--writer-version-below", "0.0.1", "--reason", "forget", "--yes"),
            self._class_store, fresh=False, purged=[])
        self.assertEqual(errors, _lines("warning", "no_key_selected", {}))

    def test_frozen_remove_of_the_frozen_report(self) -> None:
        """`frozen remove` of the frozen report of `frozen_period`: the line of its
        identifier (command-line.md › Frozen reports, › JSON documents); its file leaves
        the store."""
        identifier = support.build_uid(1)

        def removed(_: Context, home: Path, *__: object) -> None:
            self.assertFalse((support.fixture_store_folder(home) / "frozen"
                              / support.FIXTURE_MACHINE / f"{identifier}.json").exists())

        errors = _assert_pair(self, "frozen-remove_frozen_period",
                              ("frozen", "remove", identifier), self._fresh("frozen_period"),
                              fresh=True, after=removed)
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_report_timesheet_with_freeze_ends_with_its_identifier(self) -> None:
        """`report timesheet --freeze` of the one day of `measured_day`: the report of the
        period, then the line of the identifier of the frozen report; the JSON output is
        the document of the file that the command keeps, with the instant of the freeze and
        no note (command-line.md › Frozen reports)."""
        one = support.FIXTURE_DAY_ONE.isoformat()
        identifier = support.FIXTURE_FIRST_UID

        def kept(_: Context, home: Path, kind: str, shown: str) -> None:
            path = (support.fixture_store_folder(home) / "frozen"
                    / support.FIXTURE_MACHINE / f"{identifier}.json")
            envelope = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(list(envelope), ["document", "frozen_at"])
            self.assertEqual(envelope["frozen_at"], "2026-11-24T12:00:00.000Z")
            self.assertEqual(envelope["document"]["frozen_id"], identifier)
            if kind == "json":
                self.assertEqual(json.loads(shown), envelope["document"])

        errors = _assert_pair(self, "report-timesheet-freeze_measured_day",
                              ("report", "timesheet", "--from", one, "--to", one,
                               "--freeze"), self._fresh("measured_day"), fresh=True,
                              after=kept)
        self.assertEqual(errors, {"en": "", "it": ""})


def _write_settled_session(logs: Path, home: Path) -> None:
    """The one session of the machine scenarios: an invented prompt in the folder of native
    logs, with its working folder below the home, settled so that an ingestion reads it."""
    support.write_session(
        logs, "session-one",
        [support.prompt_record("Invented prompt of the machine tests.",
                               "2026-11-20T09:15:00.000Z",
                               "3f1c0000-0000-4000-8000-0000000000b1")],
        {}, home / support.FIXTURE_WORK_FOLDER)
    support.settle([logs])


class FakeScheduler:
    """A fake of the Task Scheduler that holds at most one entry, the XML document of the
    last create, which a create hands over as a temporary file that the fake reads during
    the call (platform.scheduler › _windows_create): a query for the entry of the ledger
    is answered with that document and the exit code 0 when an entry is held, and with
    the exit code 1 when none is; a delete drops the entry. Any other call fails the test,
    so no scenario reaches the scheduler of the machine that runs the tests."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.document: str | None = None

    def __call__(self, words: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(list(words))
        if (words[:2] == ["schtasks", "/Query"] and words[2:4] == ["/TN", ENTRY_NAME]
                and words[4:] in ([], ["/XML"])):
            held = self.document is not None
            stdout = self.document if held and words[4:] == ["/XML"] else ""
            return subprocess.CompletedProcess(words, 0 if held else 1, stdout, "")
        if (words[:5] == ["schtasks", "/Create", "/TN", ENTRY_NAME, "/XML"]
                and words[6:] == ["/F"]):
            self.document = Path(words[5]).read_text(encoding="utf-8")
            return subprocess.CompletedProcess(words, 0, "", "")
        if words == ["schtasks", "/Delete", "/TN", ENTRY_NAME, "/F"]:
            self.document = None
            return subprocess.CompletedProcess(words, 0, "", "")
        raise AssertionError(f"the fake of the Task Scheduler received {words}")


class MachineOutputTests(unittest.TestCase):
    """The output, on one machine that the scenario builds in its temporary home, of the
    commands that prepare the ledger and that fill it — `setup`, `schedule show`,
    `schedule create`, `schedule remove`, `ingest`, and `machine label` — in English and
    in Italian, against their expected files (command-line.md › Setup, › Commands, ›
    JSON documents; architecture.md › Tests › Report tests), compared by `_assert_pair`.
    Each scenario builds the world of its own. A scenario runs one world for each mode
    where the first run changes what the second would show: `setup_first`, because the
    second `setup` creates nothing; `schedule-remove_entry`, because the first run removes
    the entry that the second would remove; `ingest_new_events`, because the first
    `ingest` takes the events that the second would not find. The others run one world for
    both modes, `schedule-create_time` too, because a create replaces the entry and gives
    the same output twice. The scenarios of `setup` and of `schedule` give their context
    the system `Windows` fixed, so that every runner takes the scheduler that the fake
    plays, the Task Scheduler, where a Linux runner without `systemctl` would take cron,
    which holds no entry, and the retention lines of `setup` name no `loginctl
    enable-linger`, which they name on Linux. They run every command with the home of the
    world as the working folder, because the machine-local data folder of a `Windows`
    context is a pure path of Windows whose text the command turns into a path of the
    working folder. No output of such a scenario holds a path that the context
    computes from a system other than the running one: the `setup` of the scenario gives
    its store folder with `--store`, and its folder of native logs with `--native-logs`,
    as the executable is given below the home; no default folder of an agent tool exists
    in the home. The machine configuration and the person configuration are written by
    the `setup` of the scenario, never by hand. The warnings of a command go to the
    standard error, never into the expected file of the standard output."""

    def _machine_world(self) -> tuple[Context, Path]:
        """An empty home below a temporary folder, with one settled session of an invented
        prompt in its folder of native logs, and the context of the scenarios on it: the
        system `Windows` fixed, the environment of a world, the instant, the maker of
        identifiers, the installation identifier, the time zone, and the version fixed as
        the fixture context gives them, the fake of the Task Scheduler as the only call of
        a scheduler program, and no question. The installed command of the context is a
        path below the home, so that the command of the entry shows below the root of its
        world on every runner; the file itself need not exist."""
        scheduler = FakeScheduler()
        folder = support.TemporaryFolder()
        home = folder.__enter__()
        self.addCleanup(folder.__exit__, None, None, None)
        logs = home / support.FIXTURE_LOGS_FOLDER
        logs.mkdir()
        _write_settled_session(logs, home)
        context = Context(
            system="Windows",
            environ=support.world_environ(home),
            home=home,
            now=support.FIXTURE_NOW,
            new_uid=support.fixture_uids(),
            run=scheduler,
            executable=home / "tools" / "ai-effort-ledger",
            installation=support.FIXTURE_INSTALLATION,
            ask=None,
            adapters=[support.adapters_for_tests(home)],
            time_zone=lambda: support.FIXTURE_ZONE,
            version=support.FIXTURE_VERSION,
            uid=501,
        )
        return context, home

    def _world_after_setup(self, entry: bool = False) -> tuple[Context, Path]:
        """The world of `_machine_world` after the `setup` of the scenarios has run; with
        `entry` true, a `schedule create` has run after it, and the fake scheduler holds
        the entry that the create handed it."""
        context, home = self._machine_world()
        self._run(context, home, *self._setup_words(home))
        if entry:
            self._run(context, home, "schedule", "create")
        return context, home

    def _store_world(self, session: bool = True) -> tuple[Context, Path]:
        """A machine set up below a temporary home by `support.world`, with, when `session`
        is true, one settled session of an invented prompt in its folder of native logs."""
        folder = support.TemporaryFolder()
        home = folder.__enter__()
        self.addCleanup(folder.__exit__, None, None, None)
        fixture = support.world(home, support.FIXTURE_MACHINE)
        if session:
            _write_settled_session(fixture.logs[0], home)
        return fixture.context, home

    def _setup_words(self, home: Path) -> tuple[str, ...]:
        """The words of the `setup` of a scenario: the store folder and the folder of native
        logs of the world, given with `--store` and `--native-logs`. The store folder is
        given because the default folder of a `Windows` context is a pure path of Windows
        that prints another text on a runner that is not Windows, and `setup` records a
        store that is not the default in the machine configuration, so the later commands
        find it with no option; no default folder of an agent tool exists in the home of
        the world, so the logs are given too (command-line.md › Setup)."""
        return ("setup", "--store", str(home / support.FIXTURE_STORE_FOLDER),
                "--native-logs", f"claude-code={home / support.FIXTURE_LOGS_FOLDER}")

    def _run(self, context: Context, home: Path, *words: str) -> None:
        """One command that builds the world, with the home of the world as the working
        folder: a command that stops, or that writes a line of warning or error, fails the
        test, so a world rests on no step that its scenario did not mean."""
        with contextlib.chdir(home):
            code, _, error = support.run_main(context, *words)
        self.assertEqual(code, 0, error)
        self.assertEqual(error, "")

    def test_setup_first_shows_the_created_configuration(self) -> None:
        """`setup` on a home that holds nothing of the ledger: the machine identifier that
        the guard of the command made, the store folder it was given, the person configuration
        it created with the file that names it and with its entries, the retention of the
        two agent tools, the entry the scheduled ingestion would hold — the command
        creates none, because nobody gave it `--schedule yes` and it asks no question —,
        and the one source of the first ingestion with its new event (command-line.md ›
        Setup, › JSON documents)."""
        _assert_pair(self, "setup_first", self._setup_words, self._machine_world, fresh=True)

    def test_setup_second_shows_what_it_changed(self) -> None:
        """`setup` again on the machine that `setup_first` left: nothing created, the
        entry the scheduled ingestion would hold unchanged, and no new event in the folder
        of native logs that the first ingestion emptied (command-line.md › Setup)."""
        _assert_pair(self, "setup_second", self._setup_words, self._world_after_setup)

    def test_schedule_show_names_no_entry(self) -> None:
        """`schedule show` on a set-up machine whose scheduler holds no entry of the
        ledger: the line that names none (command-line.md › Commands, › JSON documents)."""
        _assert_pair(self, "schedule-show_no_entry", ("schedule", "show"),
                     self._world_after_setup)

    def test_schedule_show_shows_the_entry_the_fake_holds(self) -> None:
        """`schedule show` after a `schedule create`: the entry as the fake of the Task
        Scheduler holds it, read back from the XML of the create (command-line.md ›
        Commands)."""
        _assert_pair(self, "schedule-show_entry", ("schedule", "show"),
                     lambda: self._world_after_setup(entry=True))

    def test_schedule_create_shows_the_entry_at_its_time(self) -> None:
        """`schedule create --time 06:30`: the entry at the time of the option, created in
        the fake of the Task Scheduler; a create replaces an entry that the scheduler
        holds already (command-line.md › Commands)."""
        _assert_pair(self, "schedule-create_time", ("schedule", "create", "--time", "06:30"),
                     self._world_after_setup)

    def test_schedule_remove_removes_the_entry(self) -> None:
        """`schedule remove` on a machine whose scheduler holds the entry: the line that
        names none, and the entry dropped from the fake of the Task Scheduler. The remove
        changes what its own next run would warn, so each mode runs on a world of its own
        (command-line.md › Commands)."""
        def dropped(context: Context, *_: object) -> None:
            self.assertIsNone(context.run.document)

        _assert_pair(self, "schedule-remove_entry", ("schedule", "remove"),
                     lambda: self._world_after_setup(entry=True), fresh=True, after=dropped)

    def test_schedule_remove_without_entry_warns(self) -> None:
        """`schedule remove` on a set-up machine whose scheduler holds no entry of the
        ledger: it completes and warns `no_schedule_entry`, on the standard error in both
        modes and, with `--json`, also in the warnings of the document (command-line.md ›
        Commands, › Output, › Exit codes)."""
        errors = _assert_pair(self, "schedule-remove_no_entry", ("schedule", "remove"),
                              self._world_after_setup)
        self.assertEqual(errors, {
            "en": "warning: The ledger has no scheduled ingestion to remove.\n",
            "it": "warning: Il ledger non ha nessuna acquisizione pianificata da"
                  " rimuovere.\n",
        })

    def test_ingest_counts_the_new_events_of_a_folder(self) -> None:
        """`ingest` on a set-up machine whose folder of native logs holds one settled
        session: the source of the folder, the folder as the machine configuration records
        it, and the number of its new events and of the sessions still held back
        (command-line.md › Commands, › JSON documents)."""
        _assert_pair(self, "ingest_new_events", ("ingest",), self._store_world, fresh=True)

    def test_ingest_again_counts_no_new_events(self) -> None:
        """`ingest` again on the machine of `ingest_new_events`: the same source with no
        new event, because the first ingestion recorded its own instant for the folder
        (ingestion.md › Frequency)."""
        def world() -> tuple[Context, Path]:
            context, home = self._store_world()
            self._run(context, home, "ingest")
            return context, home
        _assert_pair(self, "ingest_no_new_events", ("ingest",), world)

    def test_machine_label_shows_the_machine_and_its_label(self) -> None:
        """`machine label <text>`: the machine identifier and the label, and the label
        written in the store metadata of the machine (command-line.md › Commands, › JSON
        documents; architecture.md › Files of a machine). The same label each time, so
        both modes run on one world."""
        def written(_: Context, home: Path, *__: object) -> None:
            self.assertEqual(
                machine_labels(support.fixture_store_folder(home), [support.FIXTURE_MACHINE]),
                ({support.FIXTURE_MACHINE: "Invented label of the machine."}, []))

        _assert_pair(self, "machine-label_label",
                     ("machine", "label", "Invented label of the machine."),
                     lambda: self._store_world(session=False), after=written)


class StoreOutputTests(support.FixtureStores):
    """The output of `config show`, `config add`, `index rebuild`, `version`, and the help,
    in English and in Italian, against their expected files (command-line.md › Commands, ›
    Configuration entries, › JSON documents, › Exit codes; architecture.md › Tests › Report
    tests), compared by `_assert_pair`. `config show`, `index rebuild`, and `version` run
    on a fixture store, which they do not change, and `config show` of a configuration error
    on a world of its own; `config add` writes the person configuration, so each of its
    runs has a world of its own, and its Italian twin holds the English cells, because it
    prints no label. The help completes before any store is read, so it runs on the context
    of a fixture store; it has no JSON document, so its pairs compare the text alone."""

    STORES = ("annotations", "frozen_day")

    def _fixture(self, name: str) -> Callable[[], tuple[Context, Path]]:
        """The context and the home of the fixture store `name` of the class."""
        return lambda: (self._contexts[name], self._homes[name])

    def _world(self, *entries: Sequence[str]) -> tuple[Context, Path]:
        """A machine set up below a temporary home by `support.world`, whose person
        configuration then takes each entry of `entries`, the words after `config add`,
        through the command; a command that stops or writes a line of warning or error
        fails the test."""
        folder = support.TemporaryFolder()
        home = folder.__enter__()
        self.addCleanup(folder.__exit__, None, None, None)
        fixture = support.world(home, support.FIXTURE_MACHINE)
        for words in entries:
            code, _, error = support.run_main(fixture.context, "config", "add", *words)
            self.assertEqual((code, error), (0, ""))
        return fixture.context, home

    def _assert_config_add(self, name: str, entry: str, values: dict[str, str],
                           *words: str) -> None:
        """`config add <words>` on a world of its own for each run: its output against the
        expected files of `name`, and, after each run, the entry `entry` with `values` as
        the last one of its kind that the person configuration holds; no line on the
        standard error."""
        def appended(_: Context, home: Path, *__: object) -> None:
            text = (support.fixture_store_folder(home) / PERSON_FILE).read_text(
                encoding="utf-8")
            self.assertEqual(tomllib.loads(text)[entry][-1], values)

        errors = _assert_pair(self, name, ("config", "add", *words), self._world,
                              fresh=True, after=appended)
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_config_show_of_a_fixture_store(self) -> None:
        """`config show` on the store `annotations`: each report parameter and single
        value at its default, then the time zone and the day start that the creation
        wrote, the two projects, the two work items, and the two identity rules, each with
        the layer `person`. The English run gives no `--language`, so the language shows
        the layer `default`; the Italian run gives `--language it`, so it shows `it` and
        the layer `option` (configuration.md › Order)."""
        errors = _assert_pair(self, "config-show_annotations", ("config", "show"),
                              self._fixture("annotations"))
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_config_show_of_a_name_conflict(self) -> None:
        """`config show` on a person configuration that gives one name to two project
        identifiers: the two projects, and the configuration error on the standard error
        in the language of the run, and in the document; `config show` computes no
        figures, so it completes with the exit code 0 (command-line.md › Exit codes)."""
        shared = ("--name", "Shared Name")
        errors = _assert_pair(
            self, "config-show_name_conflict", ("config", "show"),
            lambda: self._world(("project", "--id", "alpha", *shared),
                                ("project", "--id", "beta", *shared)))
        self.assertEqual(errors, {
            "en": "error: The person configuration gives one name to two project"
                  " identifiers: alpha and beta.\n",
            "it": "error: La configurazione personale dà uno stesso nome a due"
                  " identificativi di progetto: alpha e beta.\n",
        })

    def test_config_add_of_a_time_zone(self) -> None:
        """`config add time-zone` with an RFC 3339 instant, always the form of its
        `--from` (command-line.md › Form): the instant of the entry in UTC with
        milliseconds (command-line.md › Configuration entries)."""
        self._assert_config_add(
            "config-add_time_zone", "time_zone",
            {"zone": "Europe/Rome", "from": "2026-12-01T09:00:00.000Z"},
            "time-zone", "--zone", "Europe/Rome", "--from", "2026-12-01T09:00:00Z")

    def test_config_add_of_a_day_start(self) -> None:
        """`config add day-start --from today`: the hour as `HH:MM`, and the local day of
        the instant of the context as the day of the entry (command-line.md › Form)."""
        self._assert_config_add(
            "config-add_day_start", "day_start", {"hour": "04:00", "from": "2026-11-24"},
            "day-start", "--hour", "04:00", "--from", "today")

    def test_config_add_of_an_identity_rule(self) -> None:
        """`config add identity-rule` with a remote URL: the repository identity of the
        URL, without the scheme, the port, and `.git`, in lower case (configuration.md ›
        Matching; ingestion.md › Repository identity)."""
        self._assert_config_add(
            "config-add_identity_rule", "identity_rule",
            {"project": "alpha", "repository": "example.org/team/invented"},
            "identity-rule", "--project", "alpha", "--repository",
            "https://Example.org:8443/Team/Invented.git")

    def test_index_rebuild_counts_the_segments_and_the_lines(self) -> None:
        """`index rebuild` on the store `frozen_day`: its one segment, and its six lines —
        the three events of the sessions, the two annotations, and the manual entry. The
        rebuild changes no segment, and no result depends on the index (architecture.md ›
        Local index)."""
        errors = _assert_pair(self, "index-rebuild_frozen_day", ("index", "rebuild"),
                              self._fixture("frozen_day"))
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_version_shows_the_version_of_the_context(self) -> None:
        """`version`: the version of the ledger that the context gives, the fixed
        `FIXTURE_VERSION`, and the version of `tzdata`, which `normalize` masks
        (command-line.md › Commands, › JSON documents)."""
        errors = _assert_pair(self, "version_fixture", ("version",),
                              self._fixture("annotations"))
        self.assertEqual(errors, {"en": "", "it": ""})

    def test_help_of_each_action_and_of_the_main_help(self) -> None:
        """`--help` and `<command> --help` of each command: the help at the fixed width,
        with the words of the language of `--language`, completed with the exit code 0
        and nothing on the standard error (command-line.md › Commands)."""
        for name, words in HELP_COMMANDS.items():
            with self.subTest(help=name):
                errors = _assert_pair(self, f"help_{name}", (*words, "--help"),
                                      self._fixture("annotations"), kinds=("txt",))
                self.assertEqual(errors, {"en": "", "it": ""})

    def test_each_action_has_the_words_of_a_help_file(self) -> None:
        """Every action of `ACTIONS` has the words of a pair of `HELP_COMMANDS` as the
        first words of its own, so that a command that gets a parser and an action
        without its help file fails here. The empty words of `main` match every action
        and are left out."""
        prefixes = [words for words in HELP_COMMANDS.values() if words]
        for action in ACTIONS:
            with self.subTest(action=action):
                self.assertTrue(
                    any(tuple(action.split())[:len(words)] == words for words in prefixes),
                    f"no help file holds the help of the action {action}")
