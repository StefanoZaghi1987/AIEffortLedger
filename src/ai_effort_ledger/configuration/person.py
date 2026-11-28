"""The person configuration: the file `configuration.toml` of the store folder, with its
dated facts, its rules, and its single values as values (configuration.md › Format, ADR
0017). A dated value is either a TOML value of its type or the basic string that the
command line appends, so the reader accepts both as the same entry."""

from collections.abc import Mapping
from dataclasses import fields
from datetime import date, datetime, time
from pathlib import Path
from typing import NamedTuple
from zoneinfo import ZoneInfo

from ..language import LANGUAGES
from .forms import is_day, is_hour, is_offset_instant
from .values import (
    ConfigurationUnreadable,
    ReportParameters,
    SetupRequired,
    _fault,
    _header_lines,
    _key_line,
    _load,
    parse_duration,
)

PERSON_FILE = "configuration.toml"

DEFAULT_SETTLE_TIME = 14400
"""The settle time of a person who names none: 4 hours (GLOSSARY › Settle time)."""

_LATER_PHASE = frozenset({"label_key", "cost_source", "price", "model_provider"})
"""The entries that the Format section of configuration.md names for a later phase:
valid in any version of the ledger, with no effect before their phase."""

_NAMED_KEYS = frozenset({
    "time_zone", "day_start", "project", "work_item", "identity_rule", "category_rule",
    "preferred_remotes", "settle_time", "report"}) | _LATER_PHASE
"""The entries and the single keys of the person configuration that the Format section
names; the reader accepts no other key of the file (configuration.md › Format)."""

_NAMED_REPORT_KEYS = frozenset({
    "idle_gap", "minimum_attention", "stale_limit", "headless_prompts",
    "timesheet_granularity", "language", "first_day_of_week"})
"""The keys of the `[report]` table that the Format section names; `first_day_of_week`
is the one key of the table of a later phase."""

_ENTRY_KEYS = {
    "time_zone": frozenset({"zone", "from"}),
    "day_start": frozenset({"hour", "from"}),
    "project": frozenset({"id", "name"}),
    "work_item": frozenset({"project", "id", "name"}),
    "identity_rule": frozenset({"repository", "folder", "branch", "from", "to", "project"}),
    "category_rule": frozenset({"tool", "category"}),
}
"""The keys that the Keys column of the Format section names for each entry the reader
reads, by the name of the entry: the reader of an entry accepts no other key of it. The
entries of a later phase have no reader yet, so no keys of theirs are checked
(configuration.md › Format)."""

# The keys of the `[report]` table whose value is a duration.
_DURATION_KEYS = ("idle_gap", "minimum_attention", "stale_limit", "timesheet_granularity")


class TimeZoneEntry(NamedTuple):
    """One time zone of the time-zone history, valid from an instant.

    `start` is the `from` key of the entry (`from` is a Python keyword); it is an aware
    instant, from a TOML instant or from an RFC 3339 basic string.
    """

    zone: str
    start: datetime
    line: int


class DayStartEntry(NamedTuple):
    """One day start hour, valid from a local date.

    `start` is the `from` key of the entry (`from` is a Python keyword).
    """

    hour: time
    start: date
    line: int


class ProjectName(NamedTuple):
    """The name that reports show for a project identifier (ADR 0019)."""

    id: str
    name: str


class WorkItemName(NamedTuple):
    """The name that reports show for a work item identifier of a project (ADR 0019)."""

    project: str
    id: str
    name: str


class IdentityRule(NamedTuple):
    """A rule that resolves events to a project from their repository identity, folder,
    branch, and date.

    `first` and `last` are the `from` and `to` keys of the entry (`from` is a Python
    keyword); both ends of the range of local days are included. The rule matches an
    event when all its conditions match, and at least one condition is present.
    """

    project: str
    repository: str | None
    folder: str | None
    branch: str | None
    first: date | None
    last: date | None
    line: int


class CategoryRule(NamedTuple):
    """A rule that gives a tool category to the tool names it matches, at report time."""

    tool: str
    category: str
    line: int


class PersonConfiguration(NamedTuple):
    """The settings and rules that the person owns: the dated facts of the time zones and
    of the day start hours, the names of projects and work items, the identity rules and
    the category rules, and the single values (configuration.md › Layers)."""

    time_zones: list[TimeZoneEntry]
    day_starts: list[DayStartEntry]
    projects: list[ProjectName]
    work_items: list[WorkItemName]
    identity_rules: list[IdentityRule]
    category_rules: list[CategoryRule]
    preferred_remotes: list[str]
    settle_time: int
    report: dict[str, object]


def read_person_configuration(store_folder: Path) -> PersonConfiguration:
    """The person configuration of the store folder (ADR 0017).

    A store folder that holds no person configuration raises SetupRequired: setup creates
    it. A file that the ledger cannot read raises ConfigurationUnreadable with the line
    of the fault or of the entry; the ledger never uses part of a file (configuration.md
    › Format). The reader accepts only what the Format section names: the keys and the
    entries of the file, the keys of the `[report]` table, and the keys that the Keys
    column of the section names for each entry. The keys and entries of a later phase
    are valid and have no effect; any other key stops the reader, a key of the file or
    of the table at the line of the key, a key of an entry at the line of the entry's
    header.
    """
    path = store_folder / PERSON_FILE
    try:
        data, text = _load(path)
    except FileNotFoundError:
        raise SetupRequired() from None
    _refuse_unnamed(data, text, path, _NAMED_KEYS)
    return PersonConfiguration(
        time_zones=[
            _time_zone(entry, path, line)
            for line, entry in _entries(data, text, path, "time_zone")
        ],
        day_starts=[
            _day_start(entry, path, line)
            for line, entry in _entries(data, text, path, "day_start")
        ],
        projects=[
            _project(entry, path, line) for line, entry in _entries(data, text, path, "project")
        ],
        work_items=[
            _work_item(entry, path, line)
            for line, entry in _entries(data, text, path, "work_item")
        ],
        identity_rules=[
            _identity_rule(entry, path, line)
            for line, entry in _entries(data, text, path, "identity_rule")
        ],
        category_rules=[
            _category_rule(entry, path, line)
            for line, entry in _entries(data, text, path, "category_rule")
        ],
        preferred_remotes=_preferred_remotes(data, path, text),
        settle_time=_settle_time(data, path, text),
        report=_report_table(data, path, text),
    )


def _refuse_unnamed(
    data: dict[str, object],
    text: str,
    path: Path,
    named: frozenset[str],
    entry_line: int | None = None,
) -> None:
    """Stop at the first key of the data that the set does not name, with the line the
    reader names for it (configuration.md › Format). The set names the keys of one level
    of the configuration: the keys of the file, the keys of the `[report]` table, or the
    keys of one entry. A key of the file or of the table stops the reader at the line of
    the key: the line of the header that names it, `[[name]]` or `[name]`, or the line of
    the assignment of a single value; a key of an entry stops it at the line of the entry
    that `entry_line` holds, the header line the reader already holds, since the reader
    tracks no line of a key inside an entry."""
    for key in data:
        if key not in named:
            if entry_line is not None:
                raise ConfigurationUnreadable(path, entry_line)
            headers = _header_lines(text, key)
            raise ConfigurationUnreadable(
                path, headers[0] if headers else _key_line(text, key))


def resolve_parameters(
    options: Mapping[str, object],
    person: PersonConfiguration,
) -> tuple[ReportParameters, dict[str, str]]:
    """The report parameters from the first layer that gives one (configuration.md ›
    Order), with the layer of each: an option of the command, then the person
    configuration, then the defaults of the ledger.

    The keys are the report parameter names, the keys of the `[report]` table; an option
    whose value is None gives no value. A duration is whole seconds or a duration text;
    the reader has checked the values of the person configuration, and the text of an
    option that is not a duration raises ValueError.
    """
    defaults = ReportParameters()
    values: dict[str, object] = {}
    layers: dict[str, str] = {}
    for field in fields(ReportParameters):
        name = field.name
        if options.get(name) is not None:
            raw, layer = options[name], "option"
        elif name in person.report:
            raw, layer = person.report[name], "person"
        else:
            raw, layer = getattr(defaults, name), "default"
        if name in _DURATION_KEYS and isinstance(raw, str):
            raw = parse_duration(raw)
        values[name] = raw
        layers[name] = layer
    return ReportParameters(**values), layers


def _entries(
    data: dict[str, object],
    text: str,
    path: Path,
    name: str,
) -> list[tuple[int, dict[str, object]]]:
    """The entries of the `[[name]]` list, each with its line: the line of its header,
    or, when the list is written inline as an array, the line of its key.

    tomllib gives no line of an entry, so the reader finds the headers itself. A value
    that is not a list of tables is a value the reader cannot accept. An entry with a
    key that the Keys column of the Format section does not name for the entry stops the
    reader at the line of the entry. Every entry that tomllib read is returned: the
    entries pair with the headers the scan found, in order, and an entry beyond the last
    header found gets the line of the first header found, or of the key when the scan
    finds no header at all.
    """
    raw = data.get(name)
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise _fault(path, text, name)
    headers = _header_lines(text, name)
    fallback = headers[0] if headers else _key_line(text, name)
    entries: list[tuple[int, dict[str, object]]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise _fault(path, text, name)
        line = headers[index] if index < len(headers) else fallback
        _refuse_unnamed(entry, text, path, _ENTRY_KEYS[name], line)
        entries.append((line, entry))
    return entries


def _time_zone(entry: dict[str, object], path: Path, line: int) -> TimeZoneEntry:
    """One entry of the time-zone history: a zone that `tzdata` holds and an instant."""
    return TimeZoneEntry(_zone(entry, path, line), _instant(entry, path, line), line)


def _zone(entry: dict[str, object], path: Path, line: int) -> str:
    """The IANA name of the time zone, checked against `tzdata`.

    The ledger reads time zones only from `tzdata`, so a zone that it does not hold is a
    value the reader cannot accept, and the file is unreadable with the line of the
    entry (configuration.md › Format).
    """
    value = entry.get("zone")
    if isinstance(value, str) and value:
        try:
            ZoneInfo(value)
        except (KeyError, ValueError):
            raise ConfigurationUnreadable(path, line) from None
        return value
    raise ConfigurationUnreadable(path, line)


def _instant(entry: dict[str, object], path: Path, line: int) -> datetime:
    """The instant that the `from` key holds: a TOML instant with its offset, or a basic
    string in the form of an RFC 3339 instant, with an offset or `Z` alone
    (command-line.md › Form)."""
    value = entry.get("from")
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value
    if isinstance(value, str) and is_offset_instant(value):
        return datetime.fromisoformat(value)
    raise ConfigurationUnreadable(path, line)


def _day_start(entry: dict[str, object], path: Path, line: int) -> DayStartEntry:
    """One entry of the day start hours: an hour and the local date from which it is
    valid."""
    return DayStartEntry(_hour(entry, path, line), _day(entry, "from", path, line), line)


def _hour(entry: dict[str, object], path: Path, line: int) -> time:
    """The hour of the day start: a TOML time, with its seconds, or a basic string of
    the form `HH:MM`, such as `"04:00"` (command-line.md › Form)."""
    value = entry.get("hour")
    if isinstance(value, time):
        return value
    if isinstance(value, str) and is_hour(value):
        return time.fromisoformat(value)
    raise ConfigurationUnreadable(path, line)


def _day(entry: dict[str, object], key: str, path: Path, line: int) -> date:
    """The local day that the key holds: a TOML date, or a `YYYY-MM-DD` basic string."""
    day = _optional_day(entry, key, path, line)
    if day is not None:
        return day
    raise ConfigurationUnreadable(path, line)


def _optional_day(entry: dict[str, object], key: str, path: Path, line: int) -> date | None:
    """The local day that the key holds, or None when the key is absent."""
    value = entry.get(key)
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and is_day(value):
        return date.fromisoformat(value)
    raise ConfigurationUnreadable(path, line)


def _text(entry: dict[str, object], key: str, path: Path, line: int) -> str:
    """The non-empty text that the key of an entry holds."""
    value = entry.get(key)
    if isinstance(value, str) and value:
        return value
    raise ConfigurationUnreadable(path, line)


def _optional_text(entry: dict[str, object], key: str, path: Path, line: int) -> str | None:
    """The non-empty text that the key of an entry holds, or None when the key is absent:
    a text of no characters is a value the reader cannot accept, as the text of `_text`."""
    value = entry.get(key)
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    raise ConfigurationUnreadable(path, line)


def _project(entry: dict[str, object], path: Path, line: int) -> ProjectName:
    """One entry of the names of projects: an identifier and the name reports show."""
    return ProjectName(_text(entry, "id", path, line), _text(entry, "name", path, line))


def _work_item(entry: dict[str, object], path: Path, line: int) -> WorkItemName:
    """One entry of the names of work items: a project, an identifier, and a name."""
    return WorkItemName(
        _text(entry, "project", path, line),
        _text(entry, "id", path, line),
        _text(entry, "name", path, line),
    )


def _identity_rule(entry: dict[str, object], path: Path, line: int) -> IdentityRule:
    """One identity rule, whose conditions it matches, at least one of them."""
    rule = IdentityRule(
        project=_text(entry, "project", path, line),
        repository=_optional_text(entry, "repository", path, line),
        folder=_optional_text(entry, "folder", path, line),
        branch=_optional_text(entry, "branch", path, line),
        first=_optional_day(entry, "from", path, line),
        last=_optional_day(entry, "to", path, line),
        line=line,
    )
    conditions = (rule.repository, rule.folder, rule.branch, rule.first, rule.last)
    if all(condition is None for condition in conditions):
        raise ConfigurationUnreadable(path, line)
    return rule


def _category_rule(entry: dict[str, object], path: Path, line: int) -> CategoryRule:
    """One category rule: a pattern of tool names and the tool category it gives."""
    return CategoryRule(_text(entry, "tool", path, line), _text(entry, "category", path, line),
                        line)


def _preferred_remotes(data: dict[str, object], path: Path, text: str) -> list[str]:
    """The names of the preferred remotes, `["origin"]` when the key is absent."""
    value = data.get("preferred_remotes", ["origin"])
    if isinstance(value, list) and all(isinstance(one, str) for one in value):
        return list(value)
    raise _fault(path, text, "preferred_remotes")


def _settle_time(data: dict[str, object], path: Path, text: str) -> int:
    """The settle time in whole seconds, the default of the ledger when the key is absent."""
    value = data.get("settle_time")
    return DEFAULT_SETTLE_TIME if value is None else _seconds(value, path, text, "settle_time")


def _seconds(value: object, path: Path, text: str, key: str) -> int:
    """The whole seconds of a duration value: its text alone, since a duration is a text
    of whole numbers with the units `h`, `min`, and `s` (configuration.md › Format); any
    other value makes the file unreadable at the line of the key."""
    if isinstance(value, str):
        try:
            return parse_duration(value)
        except ValueError:
            pass
    raise _fault(path, text, key)


def _report_table(data: dict[str, object], path: Path, text: str) -> dict[str, object]:
    """The `[report]` table of the defaults of the report parameters, checked for the
    keys that the Format section names and for the types that the parameters read: a
    duration for each duration, a flag for `headless_prompts`, and one of `LANGUAGES` for
    `language`, as the option `--language` takes. A key or a value outside these forms
    stops the reader at the line of its key."""
    table = data.get("report", {})
    if not isinstance(table, dict):
        raise _fault(path, text, "report")
    _refuse_unnamed(table, text, path, _NAMED_REPORT_KEYS)
    for key in _DURATION_KEYS:
        if key in table:
            _seconds(table[key], path, text, key)
    headless = table.get("headless_prompts")
    if headless is not None and not isinstance(headless, bool):
        raise _fault(path, text, "headless_prompts")
    language = table.get("language")
    if language is not None and language not in LANGUAGES:
        raise _fault(path, text, "language")
    return dict(table)
