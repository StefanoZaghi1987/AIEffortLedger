"""The actions that read or write the store: `ingest`, `machine label`, `config show`,
`config add`, `index rebuild`, and `version` (command-line.md › Commands, › Setup, ›
Configuration entries, › JSON documents). Every action that writes calls `before_write`
first; the lock of the machine and the store is taken by the ingestion, by the append of
an entry, and by the action of the label of the machine itself."""

import argparse
import json
import tomllib
from dataclasses import fields
from datetime import date, datetime, timezone
from pathlib import Path

from .. import days
from ..attribution import project_names
from ..configuration import (
    ENTRY_KEYS,
    PersonConfiguration,
    ReportParameters,
    WrongValue,
    append_entry,
    is_offset_instant,
    resolve_parameters,
)
from ..configuration.person import PERSON_FILE
from ..events import format_instant
from ..index import LocalIndex
from ..ingestion.run import INDEX_FILE, LOCK_FILE, run_ingestion
from ..language import label
from ..platform import StoreLock
from ..reports import format_duration
from ..repository import normalize_remote
from ..store import write_label
from . import (
    Context,
    entry_text,
    inside_folder,
    machine_configuration,
    machine_data_folder,
    sources_document,
    sources_text,
)
from .arguments import ConflictingArguments, MissingArgument
from .figures import report_options
from .output import Outcome


def ingest(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `ingest`: one ingestion of every adapter into the store, with the
    number of new events of each folder of native logs (command-line.md › Commands). The
    warnings of the reading, among them `lost_events`, go to the outcome, so an ingestion
    that finds lost events completes with the exit code 3."""
    _, person, store = context.require_setup(options.store)
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    result = run_ingestion(machine, machine_data_folder(context), store, person,
                           context.adapters, context.now, context.home, context.system,
                           context.environ, context.version)
    document = sources_document(result)
    if not options.json:
        shown = sources_text(document, options.language)
        if shown:
            print(shown)
    return Outcome(document, result.warnings, [], False)


def machine_label(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `machine label`: the label of the machine written in its store
    metadata, under the lock of the machine and the store (command-line.md › Commands). A
    label that is blank after `strip()` would show no name where an output names the
    machine, so it stops with a wrong value of `<text>` before anything is read or
    written."""
    if not options.text.strip():
        raise WrongValue("<text>", options.text)
    _, _, store = context.require_setup(options.store)
    context.before_write()
    machine = machine_configuration(context)  # the guard may have made the machine again
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        write_label(store, machine.machine, options.text)
    document = {"machine": machine.machine, "label": options.text}
    if not options.json:
        print(f"{label('machine', options.language)}: {document['machine']}\n"
              f"{label('label', options.language)}: {document['label']}")
    return Outcome(document, [], [], False)


def config_show(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `config show`: the value of each parameter and dated fact with the
    layer that gives it, and every configuration error that the person configuration
    gives alone; a rule conflict needs an event that the two rules match, so the reports
    show it. No event is read, so the command computes no figures and completes with the
    exit code 0 also when it shows configuration errors (command-line.md › Commands)."""
    _, person, store = context.require_setup(options.store)
    parameters, layers = resolve_parameters(report_options(options), person)
    document = {
        "parameters": _parameters(parameters, layers, person, store),
        "entries": _entries(person),
    }
    errors = project_names((), (), person)[1]
    options.configuration_errors_are_incomplete = False
    if not options.json:
        print(_show_text(document, options.language))
    return Outcome(document, [], errors, False)


def config_add(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `config add`: one entry appended at the end of the person
    configuration, with its values in their final form (command-line.md › Configuration
    entries). The append of `configuration` takes the lock of the machine and the store
    while it appends and reads the file again. A value of no format stops with a wrong
    value that names the option the person typed, such as `--category`, not the key of
    the entry (command-line.md › Configuration entries)."""
    _, person, store = context.require_setup(options.store)
    entry = options.entry.replace("-", "_")
    values = _values(entry, options, context, person)
    context.before_write()
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    try:
        written = append_entry(store, inside / LOCK_FILE, entry, values)
    except WrongValue as wrong:
        key = wrong.values["key"]
        if key not in _OPTION_KEYS:
            raise
        raise WrongValue(_flag(key), wrong.values["value"]) from None
    document = {"entry": entry, **written}
    if not options.json:
        print(entry_text(entry, written))
    return Outcome(document, [], [], False)


def index_rebuild(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `index rebuild`: the local index built again from the segments, with
    the numbers that it holds, its segments and all its lines (command-line.md ›
    Commands, › JSON documents)."""
    _, _, store = context.require_setup(options.store)
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    index = LocalIndex(inside / INDEX_FILE)
    try:
        index.rebuild(store)
        segments, lines = index.counts()
    finally:
        index.close()
    document = {"segments": segments, "events": lines}
    if not options.json:
        print(f"{label('segments', options.language)}: {segments}\n"
              f"{label('events', options.language)}: {lines}")
    return Outcome(document, [], [], False)


def version(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `version`: the version of the ledger and of `tzdata`. It reads no
    store, so it completes before any setup (command-line.md › Commands)."""
    document = {"ledger": context.version, "tzdata": days.tzdata_version()}
    if not options.json:
        print(f"{label('ledger', options.language)}: {document['ledger']}\n"
              f"{label('tzdata', options.language)}: {document['tzdata']}")
    return Outcome(document, [], [], False)


_OPTION_KEYS = ("zone", "from", "hour", "id", "name", "project", "work_item", "repository",
                "folder", "branch", "to", "tool", "category")
"""The keys of the entries of the person configuration, each also an option of `config
add` with its underscores as hyphens (command-line.md › Configuration entries)."""

_REQUIRED: dict[str, tuple[str, ...]] = {
    "time_zone": ("zone", "from"),
    "day_start": ("hour", "from"),
    "project": ("id", "name"),
    "work_item": ("project", "id", "name"),
    "identity_rule": ("project",),
    "category_rule": ("tool", "category"),
}
"""The keys that each entry of `config add` needs; an identity rule also needs at least
one of its conditions, which `_values` checks (command-line.md › Configuration entries)."""

_CONDITIONS = ("repository", "folder", "branch", "from", "to")
"""The keys that an identity rule matches, at least one of them (configuration.md ›
Format)."""


def _values(
    entry: str,
    options: argparse.Namespace,
    context: Context,
    person: PersonConfiguration,
) -> dict[str, str]:
    """The values of one entry of `config add`, as the file will hold them: the URL of
    `--repository` becomes its repository identity first (configuration.md › Matching),
    and a day value becomes the local day of the person, an instant value the instant
    itself (command-line.md › Form). Options that the entry does not read stop with
    `ConflictingArguments`, which names the entry and each of them; keys that the entry
    needs and the command line does not give stop with `MissingArgument`, which names
    each of them, the conditions of an identity rule as one argument."""
    unread = [_flag(key) for key in _OPTION_KEYS
              if getattr(options, key, None) is not None and key not in ENTRY_KEYS[entry]]
    if unread:
        raise ConflictingArguments(options.action, [options.entry, *unread])
    values = {key: value for key in ENTRY_KEYS[entry]
              if (value := getattr(options, key, None)) is not None}
    missing = [_flag(key) for key in _REQUIRED[entry] if key not in values]
    if missing:
        raise MissingArgument(options.action, missing)
    if entry == "identity_rule" and not any(key in values for key in _CONDITIONS):
        raise MissingArgument(options.action, [" | ".join(map(_flag, _CONDITIONS))])
    if "repository" in values:
        identity = normalize_remote(values["repository"])
        if identity is None:
            raise WrongValue("--repository", values["repository"])
        values["repository"] = identity
    for key in ("from", "to"):
        if key in values:
            values[key] = _dated(entry, key, values[key], context, person)
    return values


def _flag(key: str) -> str:
    """The option of `config add` that gives the key of an entry."""
    return f"--{key.replace('_', '-')}"


def _dated(
    entry: str,
    key: str,
    value: str,
    context: Context,
    person: PersonConfiguration,
) -> str:
    """The dated value of an entry as the file holds it: the `from` of a time-zone entry
    is an RFC 3339 instant, with an offset or `Z` alone — a local time is a wrong use —
    kept as the instant of the value, RFC 3339 in UTC; the `from` of a day-start entry
    and the ends of an identity rule are local days, `YYYY-MM-DD`. `today` and
    `yesterday` name the local day of the run, through the time-zone history and the day
    start hours of the person (command-line.md › Form)."""
    local = days.LocalDays(person.time_zones, person.day_starts)
    if entry == "time_zone":
        if not is_offset_instant(value):
            raise WrongValue(f"--{key}", value)
        return format_instant(local.local_instant(value))
    try:
        return local.parse_day(value, context.now).isoformat()
    except ValueError:
        raise WrongValue(f"--{key}", value) from None


def _parameters(
    values: ReportParameters,
    layers: dict[str, str],
    person: PersonConfiguration,
    store: Path,
) -> list[dict]:
    """The parameters of the document: the report parameters with the layer that gives
    each one, then the two single values of Phase 1, whose layer is the person's when
    the file holds the key and the default's when it does not (configuration.md ›
    Format)."""
    held = [{"name": field.name, "value": getattr(values, field.name),
             "layer": layers[field.name]} for field in fields(values)]
    single = tomllib.loads((store / PERSON_FILE).read_text(encoding="utf-8"))
    held.append({"name": "settle_time", "value": person.settle_time,
                 "layer": "person" if "settle_time" in single else "default"})
    held.append({"name": "preferred_remotes", "value": person.preferred_remotes,
                 "layer": "person" if "preferred_remotes" in single else "default"})
    return held


def _entries(person: PersonConfiguration) -> list[dict]:
    """The entries of the document: every entry of the person configuration with its
    keys, the instants in UTC and the days and hours as the command line shows them
    (command-line.md › JSON documents, configuration.md › Format)."""
    held = []
    for entry in person.time_zones:
        held.append({"entry": "time_zone", "zone": entry.zone,
                     "from": format_instant(entry.start), "layer": "person"})
    for entry in person.day_starts:
        held.append({"entry": "day_start", "hour": f"{entry.hour:%H:%M}",
                     "from": entry.start.isoformat(), "layer": "person"})
    for entry in person.projects:
        held.append({"entry": "project", "id": entry.id, "name": entry.name,
                     "layer": "person"})
    for entry in person.work_items:
        held.append({"entry": "work_item", "project": entry.project, "id": entry.id,
                     "name": entry.name, "layer": "person"})
    for entry in person.identity_rules:
        one: dict = {"entry": "identity_rule", "project": entry.project}
        for key, value in (("repository", entry.repository), ("folder", entry.folder),
                           ("branch", entry.branch), ("from", entry.first),
                           ("to", entry.last)):
            if value is not None:
                one[key] = value.isoformat() if isinstance(value, date) else value
        one["layer"] = "person"
        held.append(one)
    for entry in person.category_rules:
        held.append({"entry": "category_rule", "tool": entry.tool,
                     "category": entry.category, "layer": "person"})
    return held


_DURATION_PARAMETERS = frozenset({"idle_gap", "minimum_attention", "stale_limit",
                                  "timesheet_granularity", "settle_time"})
"""The parameters of `config show` whose value is a duration in whole seconds
(configuration.md › Format)."""


def _show_text(document: dict, language: str) -> str:
    """The text of the document of `config show`: one line for each parameter and for
    each entry, its value or keys, then the layer that gives it in the language. A
    duration shows as `H:MM` (command-line.md › Output), and the `from` of a time-zone
    entry as setup shows the entries that it creates (`_shown_instant`); the document
    keeps the seconds, the names of the layers, and the instants in UTC with
    milliseconds."""
    lines = [label("parameters", language)]
    for parameter in document["parameters"]:
        value = parameter["value"]
        if parameter["name"] in _DURATION_PARAMETERS:
            shown = format_duration(value)
        elif isinstance(value, str):
            shown = value
        else:
            shown = json.dumps(value, ensure_ascii=False)
        lines.append(f"{parameter['name']} {shown} {_layer(parameter['layer'], language)}")
    lines.append(label("entries", language))
    for entry in document["entries"]:
        name = entry["entry"]
        keys = {key: shown for key, shown in entry.items() if key not in ("entry", "layer")}
        if name == "time_zone":
            keys["from"] = _shown_instant(keys["from"])
        lines.append(f"{entry_text(name, keys)} {_layer(entry['layer'], language)}")
    return "\n".join(lines)


def _layer(layer: str, language: str) -> str:
    """The word of a layer of configuration.md › Order in the language: `option`,
    `person`, or `default`."""
    return label(f"layer_{layer}", language)


def _shown_instant(text: str) -> str:
    """An instant of the document as the text shows it, in the form of the entries that
    setup creates (configuration.md › Format): RFC 3339 in UTC with `Z`, whole seconds,
    and the milliseconds only when they are not zero, so that the text never shows less
    than the value."""
    moment = datetime.fromisoformat(text).astimezone(timezone.utc)
    milliseconds = moment.microsecond // 1000
    fraction = f".{milliseconds:03d}" if milliseconds else ""
    return f"{moment:%Y-%m-%dT%H:%M:%S}{fraction}Z"
