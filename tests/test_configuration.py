"""Tests of the configuration module: durations, patterns, the machine configuration, the
person configuration with its dated facts, its rules, and its report parameters, and the
writes of both configuration files."""

import unittest
from datetime import date, datetime, time, timezone
from pathlib import Path
from unittest import mock

import support
from ai_effort_ledger import configuration, events
from ai_effort_ledger.configuration import values, writes
from ai_effort_ledger.platform import salted_hash
from ai_effort_ledger.store import files as store_files

_PARAMETERS = ("idle_gap", "minimum_attention", "stale_limit", "headless_prompts",
               "timesheet_granularity", "language")

# The person configuration of the tests, written by hand with invented values; the days
# and the instants are neutral examples.
_TOML_VALUES = """\
[[time_zone]]
zone = "Europe/Rome"
from = 2026-12-01T00:00:00Z

[[day_start]]
hour = 04:00:00
from = 2026-12-01
"""

# The same dated values, written as the basic strings that the command line appends (D5).
_STRING_VALUES = """\
[[time_zone]]
zone = "Europe/Rome"
from = "2026-12-01T00:00:00Z"

[[day_start]]
hour = "04:00"
from = "2026-12-01"
"""

_MINIMAL = """\
[[time_zone]]
zone = "Europe/Rome"
from = 1970-01-01T00:00:00Z
"""

_REPORT_TABLE = """\
[report]
idle_gap = "5min"
"""

_OPTION_TABLE = """\
[report]
idle_gap = "5min"
language = "it"
"""

_LATER_PHASES = """\
[[label_key]]
key = "tickets"

[[cost_source]]
name = "team"

type = "subscription"

[[price]]
provider = "example-provider"
model = "example-model"
currency = "EUR"

[[model_provider]]
model = "example-model"
provider = "example-provider"
from = 2026-01-01

[report]
first_day_of_week = "mon"
"""

_REMOVED_PHASE = """\
[[time_zone]]
zone = "Europe/Rome"
from = 1970-01-01T00:00:00Z

[[hourly_rate]]
amount = 40
currency = "EUR"
from = 2026-01-01
"""

_TOML_FAULT = """\
[[time_zone]]
zone = "Europe/Rome"
from = 2026-12-01T00:00:00Z extra
"""

_WRONG_ZONE = """\
[[time_zone]]
zone = "Europe/Nowhere"
from = 2026-12-01T00:00:00Z
"""

_DAY_STARTS = """\
# The day start hours of the test, invented.

preferred_remotes = ["origin", "upstream"]
[[day_start]]
hour = "04:00"
from = "2026-01-01"

# The person changed the hour.
[[day_start]]
hour = "08:30"
from = "2026-06-01"
"""

_RULES = """\
[[project]]
id = "example-product"
name = "Example Product"

[[work_item]]
project = "example-product"
id = "T-14"
name = "Example work item"

[[identity_rule]]
project = "example-product"
repository = "example/example-product"
branch = "release-*"
from = 2026-01-01
to = 2026-12-31

[[category_rule]]
tool = "mcp__*"
category = "web"
"""

_MACHINE_TOML = """\
machine = "0123456789abcdef"
installation = "5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f"
salt = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
store = 'D:\\Work\\Store'

[native_logs]
claude_code = ['D:\\Work\\Logs\\Claude Code']
"""

# The person configuration that an append starts from, with a comment and a blank line
# that the append has to keep.
_APPEND_START = """\
# The person configuration of the test, invented.

preferred_remotes = ["origin"]

[[day_start]]
hour = "04:00"
from = "2026-01-01"
"""

# The file that setup creates with the zone of the operating system, and without one.
_CREATED = """\
[[time_zone]]
zone = "Europe/Rome"
from = 1970-01-01T00:00:00Z

[[day_start]]
hour = 00:00:00
from = 1970-01-01
"""

_CREATED_DAY_ONLY = """\
[[day_start]]
hour = 00:00:00
from = 1970-01-01
"""


def _person(folder: Path, text: str) -> configuration.PersonConfiguration:
    """Write the person configuration text into the store folder and read it back."""
    (folder / "configuration.toml").write_text(text, encoding="utf-8")
    return configuration.read_person_configuration(folder)


class TestConfiguration(unittest.TestCase):
    """The reading of the configuration files follows the specification."""

    def test_duration_formats(self) -> None:
        p = configuration.parse_duration
        self.assertEqual((p("4h"), p("10min"), p("1h30min"), p("90s")), (14400, 600, 5400, 90))
        self.assertEqual(p("1:30", clock=True), 5400)
        with self.assertRaises(ValueError):
            p("4 hours")
        with self.assertRaises(ValueError):
            p("1:30")
        with self.assertRaises(ValueError):
            p("1:60", clock=True)

    def test_dated_values_as_toml_values_or_strings(self) -> None:
        # D5: both forms give the same entries.
        with support.TemporaryFolder() as folder:
            values = _person(folder, _TOML_VALUES)
            strings = _person(folder, _STRING_VALUES)
        expected_zone = configuration.TimeZoneEntry(
            "Europe/Rome", datetime(2026, 12, 1, tzinfo=timezone.utc), 1)
        expected_day = configuration.DayStartEntry(time(4, 0), date(2026, 12, 1), 5)
        self.assertEqual(values.time_zones, [expected_zone])
        self.assertEqual(values.day_starts, [expected_day])
        self.assertEqual(strings.time_zones, values.time_zones)
        self.assertEqual(strings.day_starts, values.day_starts)

    def test_the_definitions_of_the_forms(self) -> None:
        """The one definition of each form of a dated value, public in `configuration`,
        says of every text of the shared table whether it is a day, a local instant, an
        RFC 3339 instant with an offset or `Z`, or an hour (command-line.md › Form); every
        reader of a person's text reads its verdict, so what a version of `fromisoformat`
        would accept is not a form."""
        for one in support.FORM_TEXTS:
            with self.subTest(text=one.text):
                self.assertEqual(configuration.is_day(one.text), one.day)
                self.assertEqual(configuration.is_local_instant(one.text),
                                 one.local_instant)
                self.assertEqual(configuration.is_offset_instant(one.text),
                                 one.offset_instant)
                self.assertEqual(configuration.is_hour(one.text), one.hour)

    def test_dated_basic_strings_read_the_forms_alone(self) -> None:
        """A dated value of the person configuration written as a basic string reads the
        form of its kind alone (command-line.md › Form): a text of no form makes the file
        unreadable with the line of its entry, the hour included; the words of the day of
        the run never name a day in the file."""
        cases = (
            (f'[[time_zone]]\nzone = "Europe/Rome"\nfrom = {{value}}\n', "offset_instant"),
            ("[[day_start]]\nhour = 04:00:00\nfrom = {value}\n", "day"),
            ('[[day_start]]\nhour = {value}\nfrom = 2026-12-01\n', "hour"),
        )
        for one in support.FORM_TEXTS:
            for entry_text, kind in cases:
                with self.subTest(text=one.text, entry=entry_text.splitlines()[0]):
                    takes = getattr(one, kind)
                    with support.TemporaryFolder() as folder:
                        path = folder / "configuration.toml"
                        path.write_text(_MINIMAL + "\n" + entry_text.format(
                            value=writes.basic_string(one.text)), encoding="utf-8")
                        if takes:
                            configuration.read_person_configuration(folder)
                        else:
                            with self.assertRaises(
                                configuration.ConfigurationUnreadable
                            ) as stopped:
                                configuration.read_person_configuration(folder)
                            self.assertEqual(stopped.exception.values,
                                             {"path": str(path), "line": 5})

    def test_append_checks_read_the_forms_alone(self) -> None:
        """The checks before an append read the same definitions: a dated value of no
        form stops the append with `wrong_value`, the key, the value, and the file
        unchanged; a value of a form is written and the file reads back."""
        cases = (
            ("time_zone", {"zone": "Europe/Rome"}, "from", "offset_instant"),
            ("day_start", {"hour": "04:00"}, "from", "day"),
            ("day_start", {"from": "2026-12-01"}, "hour", "hour"),
        )
        for one in support.FORM_TEXTS:
            for entry, held, key, kind in cases:
                values = {**held, key: one.text}
                with self.subTest(text=one.text, entry=entry, key=key):
                    with support.TemporaryFolder() as folder:
                        path = folder / "configuration.toml"
                        path.write_text(_MINIMAL, encoding="utf-8")
                        before = path.read_bytes()
                        if getattr(one, kind):
                            configuration.append_entry(folder, folder / "lock", entry,
                                                       values)
                            self.assertNotEqual(path.read_bytes(), before)
                        else:
                            with self.assertRaises(configuration.WrongValue) as stopped:
                                configuration.append_entry(folder, folder / "lock",
                                                           entry, values)
                            self.assertEqual(path.read_bytes(), before)
                            self.assertEqual(stopped.exception.values,
                                             {"key": key, "value": one.text})

    def test_defaults(self) -> None:
        # preferred_remotes ["origin"], settle_time 14400, ReportParameters().
        with support.TemporaryFolder() as folder:
            person = _person(folder, _MINIMAL)
        self.assertEqual(person.preferred_remotes, ["origin"])
        self.assertEqual(person.settle_time, 14400)
        defaults = configuration.ReportParameters()
        self.assertEqual(
            (defaults.idle_gap, defaults.minimum_attention, defaults.stale_limit,
             defaults.headless_prompts, defaults.timesheet_granularity, defaults.language),
            (600, 60, 14400, False, 900, "en"))
        parameters, layers = configuration.resolve_parameters({}, person)
        self.assertEqual(parameters, configuration.ReportParameters())
        self.assertEqual(layers, {name: "default" for name in _PARAMETERS})

    def test_report_table_overrides_defaults(self) -> None:
        # [report] idle_gap = "5min"
        with support.TemporaryFolder() as folder:
            person = _person(folder, _REPORT_TABLE)
        self.assertEqual(person.report, {"idle_gap": "5min"})
        parameters, layers = configuration.resolve_parameters({}, person)
        self.assertEqual(parameters.idle_gap, 300)
        self.assertEqual(layers["idle_gap"], "person")
        self.assertEqual(layers["stale_limit"], "default")

    def test_option_overrides_person(self) -> None:
        # layers "option", "person", "default"
        with support.TemporaryFolder() as folder:
            person = _person(folder, _OPTION_TABLE)
        options: dict[str, object] = {"idle_gap": 120, "headless_prompts": True}
        parameters, layers = configuration.resolve_parameters(options, person)
        self.assertEqual(
            (parameters.idle_gap, parameters.headless_prompts, parameters.language),
            (120, True, "it"))
        self.assertEqual(layers, {
            "idle_gap": "option",
            "minimum_attention": "default",
            "stale_limit": "default",
            "headless_prompts": "option",
            "timesheet_granularity": "default",
            "language": "person",
        })

    def test_later_phase_keys_are_accepted(self) -> None:
        # [[label_key]], [[cost_source]], [[price]], [[model_provider]], first_day_of_week
        with support.TemporaryFolder() as folder:
            person = _person(folder, _LATER_PHASES)
        self.assertEqual(person.time_zones, [])
        self.assertEqual(person.day_starts, [])
        self.assertEqual(person.projects, [])
        self.assertEqual(person.work_items, [])
        self.assertEqual(person.identity_rules, [])
        self.assertEqual(person.category_rules, [])
        self.assertEqual(person.report, {"first_day_of_week": "mon"})

    def test_a_top_level_first_day_of_week_is_unreadable(self) -> None:
        """`first_day_of_week` is a key of the `[report]` table (configuration.md ›
        Format): written at the top level of the file it names no key that the section
        gives that level, so the reader stops at the line of the key."""
        text = 'first_day_of_week = "mon"\n\n' + _MINIMAL
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 1})

    def test_removed_phase_key_is_unreadable_with_line(self) -> None:
        # [[hourly_rate]] -> ConfigurationUnreadable with line 5
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(_REMOVED_PHASE, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 5})

    def test_a_single_value_behind_another_key_is_unreadable_at_its_key_line(self) -> None:
        """A single value that the Format section does not name stops the reader at the
        line of its own assignment: no header names the key, so `_refuse_unnamed` takes
        the line that `_key_line` finds (configuration.md › Format)."""
        text = 'preferred_remotes = ["origin"]\nnonsense = true\n\n' + _MINIMAL
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 2})

    def test_a_mistyped_single_table_header_names_its_line(self) -> None:
        """A single-table header that the Format section does not name, such as a
        `[reportx]` written for `[report]`, matches no assignment line: the reader stops
        at the line of the header, wherever in the file the header sits
        (configuration.md › Format)."""
        text = "\n".join([
            "[[time_zone]]",
            'zone = "Europe/Rome"',
            "from = 1970-01-01T00:00:00Z",
            "",
            "[[day_start]]",
            "hour = 04:00:00",
            "from = 2026-12-01",
            "",
            "# The single values and the tables of the report follow.",
            "",
            'preferred_remotes = ["origin"]',
            "[reportx]",
        ]) + "\n"
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 12})

    def test_unreadable_file_names_the_line(self) -> None:
        # ConfigurationUnreadable with line 3
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(_TOML_FAULT, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.code, "configuration_unreadable")
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 3})
        self.assertEqual(stopped.exception.exit_code, 1)

    def test_entry_line_is_its_header_line(self) -> None:
        # [[day_start]] at lines 4 and 9 -> line 4, line 9
        with support.TemporaryFolder() as folder:
            person = _person(folder, _DAY_STARTS)
        self.assertEqual([entry.line for entry in person.day_starts], [4, 9])
        self.assertEqual(
            [entry.hour for entry in person.day_starts], [time(4, 0), time(8, 30)])
        self.assertEqual(
            [entry.start for entry in person.day_starts], [date(2026, 1, 1), date(2026, 6, 1)])
        self.assertEqual(person.preferred_remotes, ["origin", "upstream"])

    def test_valid_toml_with_wrong_value_is_unreadable_with_line(self) -> None:
        # zone "Europe/Nowhere"
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(_WRONG_ZONE, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 1})

    def test_language_outside_the_languages_is_unreadable_with_line(self) -> None:
        text = _MINIMAL + '\n[report]\nlanguage = "fr"\n'  # the key is on line 6
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
            self.assertEqual(stopped.exception.values, {"path": str(path), "line": 6})
            for language in ("en", "it"):
                path.write_text(text.replace('"fr"', f'"{language}"'), encoding="utf-8")
                person = configuration.read_person_configuration(folder)
                self.assertEqual(person.report["language"], language)

    def test_a_report_key_the_format_does_not_name_is_unreadable_at_the_key_line(self) -> None:
        """A key of the `[report]` table that the Format section does not name stops the
        reader at the line of the key (configuration.md › Format)."""
        text = _MINIMAL + '\n[report]\nidle_gap = "5min"\nnonsense = true\n'
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 7})

    def test_missing_person_configuration_stops_with_setup_required(self) -> None:
        with support.TemporaryFolder() as folder:
            with self.assertRaises(configuration.SetupRequired) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.code, "setup_required")
        self.assertEqual(stopped.exception.values, {})
        self.assertEqual(stopped.exception.exit_code, 1)

    def test_rules_and_names_read_with_lines(self) -> None:
        with support.TemporaryFolder() as folder:
            person = _person(folder, _RULES)
        self.assertEqual(
            person.projects,
            [configuration.ProjectName("example-product", "Example Product")])
        self.assertEqual(
            person.work_items,
            [configuration.WorkItemName("example-product", "T-14", "Example work item")])
        self.assertEqual(
            person.identity_rules,
            [configuration.IdentityRule(
                project="example-product", repository="example/example-product", folder=None,
                branch="release-*", first=date(2026, 1, 1), last=date(2026, 12, 31), line=10)])
        self.assertEqual(
            person.category_rules,
            [configuration.CategoryRule("mcp__*", "web", 17)])

    def test_identity_rule_needs_a_condition(self) -> None:
        text = '[[identity_rule]]\nproject = "example-product"\n'
        with support.TemporaryFolder() as folder:
            (folder / "configuration.toml").write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable):
                configuration.read_person_configuration(folder)

    def test_an_entry_key_the_format_does_not_name_is_unreadable_at_the_entry_line(self) -> None:
        """The Keys column of the Format table names the keys of an identity rule, and a
        key it does not name, such as a `brnach` written for `branch`, is a condition
        that the reader would drop in silence; the reader stops at the line of the
        entry's header, the line it can name (configuration.md › Format)."""
        text = (
            "[[identity_rule]]\n"
            'project = "example-product"\n'
            'repository = "example/example-product"\n'
            'brnach = "release-*"\n'
        )
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 1})

    def test_no_entry_reader_accepts_a_key_the_format_does_not_name(self) -> None:
        """Every reader of an entry refuses a key that the Keys column of the Format
        table does not name for it, at the line of the entry's header
        (configuration.md › Format)."""
        cases = (
            ("time_zone",
             '[[time_zone]]\n'
             'zone = "Europe/Rome"\n'
             "from = 2026-12-01T00:00:00Z\n"
             'extra = "x"\n'),
            ("day_start",
             "[[day_start]]\n"
             "hour = 04:00:00\n"
             "from = 2026-12-01\n"
             'extra = "x"\n'),
            ("project",
             "[[project]]\n"
             'id = "example-product"\n'
             'name = "Example Product"\n'
             'extra = "x"\n'),
            ("work_item",
             "[[work_item]]\n"
             'project = "example-product"\n'
             'id = "T-14"\n'
             'name = "Example work item"\n'
             'extra = "x"\n'),
            ("identity_rule",
             "[[identity_rule]]\n"
             'project = "example-product"\n'
             'repository = "example/example-product"\n'
             'extra = "x"\n'),
            ("category_rule",
             "[[category_rule]]\n"
             'tool = "mcp__*"\n'
             'category = "web"\n'
             'extra = "x"\n'),
        )
        for name, entry_text in cases:
            with self.subTest(entry=name), support.TemporaryFolder() as folder:
                path = folder / "configuration.toml"
                path.write_text(entry_text, encoding="utf-8")
                with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                    configuration.read_person_configuration(folder)
                self.assertEqual(stopped.exception.values,
                                 {"path": str(path), "line": 1})

    def test_machine_configuration_reads_back_equal(self) -> None:
        # native_logs with Windows paths
        with support.TemporaryFolder() as folder:
            self.assertIsNone(configuration.read_machine_configuration(folder))
            (folder / "machine.toml").write_text(_MACHINE_TOML, encoding="utf-8")
            value = configuration.read_machine_configuration(folder)
        self.assertEqual(value, configuration.MachineConfiguration(
            machine="0123456789abcdef",
            installation="5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f",
            salt="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            store=r"D:\Work\Store",
            native_logs={"claude_code": [r"D:\Work\Logs\Claude Code"]}))

    def test_pattern_matches(self) -> None:
        # "mcp__*" matches "mcp__a__b"; "Edit" does not match "edit"
        matches = configuration.pattern_matches
        self.assertTrue(matches("mcp__*", "mcp__a__b"))
        self.assertFalse(matches("Edit", "edit"))
        self.assertTrue(matches("release-*", "release-1"))
        self.assertFalse(matches("release-*", "pre-release-1"))
        self.assertTrue(matches("*edit*", "built an editor"))
        self.assertTrue(matches("a*b*c", "a one b two c"))

    def test_a_duration_is_a_text_alone(self) -> None:
        """A duration is a text of whole numbers with the units `h`, `min`, and `s`
        (configuration.md › Format): a whole number names no duration, so `settle_time`
        and a duration key of the `[report]` table written as an integer make the file
        unreadable at the line of the key, while the text reads back whole seconds."""
        cases = (
            ("settle_time = 14400\n\n", 1),
            ("[report]\nidle_gap = 300\n\n", 2),
        )
        for added, line in cases:
            with self.subTest(text=added.splitlines()[0]):
                with support.TemporaryFolder() as folder:
                    path = folder / "configuration.toml"
                    path.write_text(added + _MINIMAL, encoding="utf-8")
                    with self.assertRaises(
                        configuration.ConfigurationUnreadable
                    ) as stopped:
                        configuration.read_person_configuration(folder)
                    self.assertEqual(stopped.exception.values,
                                     {"path": str(path), "line": line})
        with support.TemporaryFolder() as folder:
            person = _person(folder, 'settle_time = "4h"\n\n' + _MINIMAL)
        self.assertEqual(person.settle_time, 14400)

    def test_a_header_inside_a_text_value_names_no_entry(self) -> None:
        """A `[[name]]` header that a multi-line string value holds names no entry, so
        the entry after it keeps the line of its own header (configuration.md › Format)."""
        text = (
            "[[project]]\n"
            'id = "example-product"\n'
            'name = """\n'
            "[[day_start]]\n"
            '"""\n'
            "\n"
            "[[day_start]]\n"
            "hour = 04:00:00\n"
            "from = 2026-12-01\n"
        )
        with support.TemporaryFolder() as folder:
            person = _person(folder, text)
        self.assertEqual(person.projects, [configuration.ProjectName(
            "example-product", "[[day_start]]\n")])
        self.assertEqual([entry.line for entry in person.day_starts], [7])

    def test_an_indented_header_names_its_entry(self) -> None:
        """A header written behind spaces on its line names its entry as a header at the
        start of the line does."""
        text = ('preferred_remotes = ["origin"]\n'
                "  [[day_start]]\n"
                "hour = 04:00:00\n"
                "from = 2026-12-01\n")
        with support.TemporaryFolder() as folder:
            person = _person(folder, text)
        self.assertEqual([entry.line for entry in person.day_starts], [2])

    def test_an_unreadable_entry_behind_a_text_value_names_its_line(self) -> None:
        """A value that the reader cannot accept behind a multi-line string value stops
        the reader at the line of its entry, not at a line that the string holds."""
        text = (
            "[[project]]\n"
            'id = "alpha"\n'
            'name = """a note of the person\n'
            "[[time_zone]]\n"
            '"""\n'
            "\n"
            "[[time_zone]]\n"
            'zone = "Europe/Nowhere"\n'
            "from = 2026-12-01T00:00:00Z\n"
        )
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 7})

    def test_a_line_ending_backslash_still_counts_its_line(self) -> None:
        """A backslash at the end of a line in a multi-line basic string is valid TOML and
        the newline after it is a line of the file, so a header behind it keeps its line.
        The reader gets the text from `read_text`, which turns a CRLF into a newline, so
        no CRLF reaches the scan."""
        text = 'note = """first \\\nsecond"""\n[[project]]\nname = "a"\n'
        self.assertEqual(values._header_lines(text, "project"), [3])

    def test_a_comment_runs_to_the_end_of_its_line(self) -> None:
        """Triple quotes inside a comment open no string, so both entries behind it keep
        their lines, and an unreadable second entry names its own line."""
        text = (
            "[[time_zone]]\n"
            'zone = "Europe/Rome"\n'
            "from = 2026-12-01T00:00:00Z\n"
            "# a note with ''' and \"\"\" in it\n"
            "[[time_zone]]\n"
            'zone = "Europe/Paris"\n'
            "from = 2027-01-01T00:00:00Z\n"
        )
        with support.TemporaryFolder() as folder:
            person = _person(folder, text)
            self.assertEqual([entry.line for entry in person.time_zones], [1, 5])
            path = folder / "configuration.toml"
            path.write_text(text.replace("Paris", "Nowhere"), encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values["line"], 5)

    def test_no_entry_is_dropped_when_a_header_is_not_found(self) -> None:
        """A quoted header is valid TOML that the scan does not find: every entry that
        tomllib read is still returned, an entry that the scan did not place with the
        line of the first header the scan found."""
        text = (
            "[[day_start]]\n"
            "hour = 04:00:00\n"
            "from = 2026-12-01\n"
            '[["day_start"]]\n'
            "hour = 05:00:00\n"
            "from = 2027-01-01\n"
        )
        with support.TemporaryFolder() as folder:
            person = _person(folder, text)
        self.assertEqual([entry.line for entry in person.day_starts], [1, 1])

    def test_the_machine_refuses_an_empty_text(self) -> None:
        """An empty installation, salt, or store is an unreadable machine configuration:
        an empty text is a value that no key holds, and every reader would silently read
        it as absent."""
        for key in ("installation", "salt", "store"):
            with self.subTest(key=key), support.TemporaryFolder() as folder:
                path = folder / "machine.toml"
                text = f'machine = "0123456789abcdef"\n{key} = ""\n'
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                    configuration.read_machine_configuration(folder)
                self.assertEqual(stopped.exception.values, {"path": str(path), "line": 2})

    def test_an_empty_condition_is_unreadable(self) -> None:
        """A condition of an identity rule that the key is present for holds a text, and
        an empty text is a value the reader cannot accept as any empty value, not a rule
        that matches no event in silence."""
        text = '[[identity_rule]]\nproject = "example-product"\nbranch = ""\n'
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(configuration.ConfigurationUnreadable) as stopped:
                configuration.read_person_configuration(folder)
        self.assertEqual(stopped.exception.values, {"path": str(path), "line": 1})


class TestConfigurationWrites(unittest.TestCase):
    """The writes of the configuration follow the specification: the entry that the
    command line appends at the end of the person configuration, the file that setup
    creates, and the machine configuration that setup writes as a whole."""

    def test_append_writes_basic_strings_at_end(self) -> None:
        # comments and layout of the file stay byte for byte
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(_APPEND_START, encoding="utf-8")
            values = configuration.append_entry(
                folder, folder / "lock", "project",
                {"id": "example-product", "name": "Example Product"})
            text = path.read_text(encoding="utf-8")
            person = configuration.read_person_configuration(folder)
        self.assertEqual(values, {"id": "example-product", "name": "Example Product"})
        self.assertEqual(text, _APPEND_START + "[[project]]\n"
                         'id = "example-product"\n'
                         'name = "Example Product"\n')
        self.assertEqual(person.projects,
                         [configuration.ProjectName("example-product", "Example Product")])
        self.assertEqual(person.day_starts,
                         [configuration.DayStartEntry(time(4, 0), date(2026, 1, 1), 5)])

    def test_value_cannot_add_an_entry(self) -> None:
        # name 'a"\n[[project]]\nid = "x' -> one entry, exact text
        name = 'a"\n[[project]]\nid = "x'
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text("", encoding="utf-8")
            configuration.append_entry(folder, folder / "lock", "project",
                                       {"id": "example-product", "name": name})
            text = path.read_text(encoding="utf-8")
            person = configuration.read_person_configuration(folder)
        self.assertEqual(text, "[[project]]\n"
                         'id = "example-product"\n'
                         'name = "a\\"\\n[[project]]\\nid = \\"x"\n')
        self.assertEqual(len(person.projects), 1)
        self.assertEqual(person.projects, [configuration.ProjectName("example-product", name)])

    def test_append_keeps_non_ascii_and_backslashes(self) -> None:
        # folder r"D:\Work\Città Example" reads back equal
        folder_name = "D:\\Work\\Città Example"
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text("", encoding="utf-8")
            configuration.append_entry(folder, folder / "lock", "identity_rule",
                                       {"project": "example-product", "folder": folder_name})
            person = configuration.read_person_configuration(folder)
        rule = configuration.IdentityRule(project="example-product", repository=None,
                                          folder=folder_name, branch=None, first=None,
                                          last=None, line=1)
        self.assertEqual(person.identity_rules, [rule])

    def test_wrong_values_stop_with_exit_2(self) -> None:
        # zone "Mars/Base", hour "25:00", category "cooking", time-zone "from"
        # "2026-12-01" (needs an RFC 3339 instant)
        cases = [
            ("time_zone", {"zone": "Mars/Base", "from": "2026-12-01T00:00:00Z"}, "zone"),
            ("day_start", {"hour": "25:00", "from": "2026-12-01"}, "hour"),
            ("category_rule", {"tool": "mcp__*", "category": "cooking"}, "category"),
            ("time_zone", {"zone": "Europe/Rome", "from": "2026-12-01"}, "from"),
        ]
        for entry, values, key in cases:
            with self.subTest(entry=entry, key=key):
                with support.TemporaryFolder() as folder:
                    path = folder / "configuration.toml"
                    path.write_text(_MINIMAL, encoding="utf-8")
                    before = path.read_bytes()
                    with self.assertRaises(configuration.WrongValue) as stopped:
                        configuration.append_entry(folder, folder / "lock", entry, values)
                    self.assertEqual(path.read_bytes(), before)
                self.assertEqual(stopped.exception.code, "wrong_value")
                self.assertEqual(stopped.exception.values, {"key": key, "value": values[key]})
                self.assertEqual(stopped.exception.exit_code, 2)

    def test_failed_read_restores_content(self) -> None:
        # a reader that fails after the append -> old bytes back
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            path.write_text(_MINIMAL, encoding="utf-8")
            before = path.read_bytes()
            with mock.patch.object(configuration.writes, "read_person_configuration",
                                   side_effect=configuration.ConfigurationUnreadable(path, 3)):
                with self.assertRaises(configuration.ConfigurationUnreadable):
                    configuration.append_entry(folder, folder / "lock", "project",
                                               {"id": "example-product",
                                                "name": "Example Product"})
            self.assertEqual(path.read_bytes(), before)

    def test_create_person_configuration(self) -> None:
        # zone "Europe/Rome" -> [[time_zone]] from 1970-01-01T00:00:00Z and [[day_start]]
        # 00:00 from 1970-01-01
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            entries = configuration.create_person_configuration(folder, "Europe/Rome")
            text = path.read_text(encoding="utf-8")
            person = configuration.read_person_configuration(folder)
        self.assertEqual(entries, [
            {"zone": "Europe/Rome", "from": "1970-01-01T00:00:00Z"},
            {"hour": "00:00", "from": "1970-01-01"},
        ])
        self.assertEqual(text, _CREATED)
        self.assertEqual(person.time_zones, [configuration.TimeZoneEntry(
            "Europe/Rome", datetime(1970, 1, 1, tzinfo=timezone.utc), 1)])
        self.assertEqual(person.day_starts,
                         [configuration.DayStartEntry(time(0, 0), date(1970, 1, 1), 5)])

    def test_create_without_zone_writes_no_time_zone(self) -> None:
        with support.TemporaryFolder() as folder:
            path = folder / "configuration.toml"
            entries = configuration.create_person_configuration(folder, None)
            text = path.read_text(encoding="utf-8")
            person = configuration.read_person_configuration(folder)
        self.assertEqual(entries, [{"hour": "00:00", "from": "1970-01-01"}])
        self.assertEqual(text, _CREATED_DAY_ONLY)
        self.assertEqual(person.time_zones, [])
        self.assertEqual(person.day_starts,
                         [configuration.DayStartEntry(time(0, 0), date(1970, 1, 1), 1)])

    def test_machine_configuration_written_whole(self) -> None:
        value = configuration.MachineConfiguration(
            machine="0123456789abcdef",
            installation="5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f5f",
            salt="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            store=r"D:\Work\Store",
            native_logs={"claude_code": [r"D:\Work\Logs\Claude Code"]})
        least = configuration.MachineConfiguration(machine="fedcba9876543210",
                                                   installation=None, salt=None, store=None,
                                                   native_logs={})
        with support.TemporaryFolder() as folder:
            configuration.write_machine_configuration(folder, value)
            self.assertEqual(configuration.read_machine_configuration(folder), value)
            configuration.write_machine_configuration(folder, least)
            self.assertEqual(configuration.read_machine_configuration(folder), least)

    def test_new_machine_identifier_when_installation_changes(self) -> None:
        salt = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        value = configuration.MachineConfiguration(
            machine="0123456789abcdef", installation=salted_hash("guid-one", salt),
            salt=salt, store=None, native_logs={})
        changed, wrote = configuration.refresh_machine(value, "guid-two",
                                                       lambda: "fedcba9876543210")
        self.assertTrue(wrote)
        self.assertEqual(changed.machine, "fedcba9876543210")
        self.assertNotEqual(changed.salt, salt)
        self.assertEqual(changed.installation, salted_hash("guid-two", changed.salt))
        kept, wrote = configuration.refresh_machine(value, "guid-one",
                                                    lambda: "fedcba9876543210")
        self.assertFalse(wrote)
        self.assertEqual(kept, value)
        created, wrote = configuration.refresh_machine(None, "guid-one",
                                                       lambda: "fedcba9876543210")
        self.assertTrue(wrote)
        self.assertEqual(created.machine, "fedcba9876543210")
        self.assertEqual(created.installation, salted_hash("guid-one", created.salt))

    def test_no_check_when_system_gives_no_identifier(self) -> None:
        # installation None -> machine kept
        value = configuration.MachineConfiguration(
            machine="0123456789abcdef",
            installation=salted_hash("guid-one", "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"),
            salt="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            store=r"D:\Work\Store", native_logs={})
        kept, wrote = configuration.refresh_machine(value, None, lambda: "fedcba9876543210")
        self.assertFalse(wrote)
        self.assertEqual(kept, value)

    def test_category_constant_equals_events(self) -> None:
        # the copied constant equals events.FIXED_VALUES["tool_category"]; the test
        # imports both modules, the package does not
        self.assertEqual(writes.TOOL_CATEGORIES, events.FIXED_VALUES["tool_category"])

    def test_store_escaper_equals_the_writes_escaper(self) -> None:
        """The escaper of the store metadata writes the same TOML basic string as the one
        of the writes of the configurations, byte for byte: on the empty text, a double
        quote and a backslash of their own, every control character, DEL, non-ASCII
        letters, and one invented text that holds them together
        (`configuration.md` › Writes; architecture.md › Modules leaves the two escapes no
        shared home, so the test imports both modules — the package does not — and pins
        them together)."""
        controls = "".join(chr(number) for number in range(0x20))
        texts = [
            "",
            'a quote "',
            "a backslash \\",
            'both "\\ of them',
            controls,
            "\x7f",
            "àèìòù Å ç ñ",
            f"a\tb\nc\rd\be\f{controls}x\"y\\z\x7f à",
        ]
        for text in texts:
            with self.subTest(text=repr(text)):
                self.assertEqual(store_files._basic_string(text), writes.basic_string(text))
