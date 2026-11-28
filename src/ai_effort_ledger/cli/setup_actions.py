"""The actions of `setup` and of the three `schedule` commands: the seven steps of the
setup through the setup module, under the lock of the machine and the store, and the
entry of the scheduled ingestion in the scheduler of the operating system
(command-line.md › Setup, › Commands, › Exit codes)."""

import argparse
import shutil
from pathlib import Path
from typing import Any

from ..configuration import WrongValue
from ..configuration.person import PERSON_FILE
from ..ingestion import is_development
from ..ingestion.run import LOCK_FILE, DevelopmentVersion
from ..language import label, note
from ..platform import (
    StoreLock,
    carries_word,
    create_entry,
    remove_entry,
    scheduler_kind,
    show_entry,
)
from ..setup import SetupOptions, SetupResult, run_setup
from ..store import machine_labels
from . import (
    Context,
    entry_text,
    inside_folder,
    resolved_store,
    schedule_document,
    schedule_text,
    sources_document,
    sources_text,
)
from .arguments import read_native_logs
from .output import Outcome


def setup(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `setup` (command-line.md › Setup): the seven steps through
    `run_setup`, with the guards of `before_write` before them and the lock of the
    machine and the store around them; the first ingestion takes the lock again as a
    nested take of the same process (platform.lock › StoreLock). The machine label is read
    once, after the steps, for the document and its text."""
    store = resolved_store(context, options.store)
    context.before_write()
    inside = inside_folder(context, store)
    inside.mkdir(parents=True, exist_ok=True)
    with StoreLock(inside / LOCK_FILE):
        result = run_setup(_options(options), context.setup_context(options.language))
    labels, label_warnings = machine_labels(result.store, [result.machine])
    document: dict[str, Any] = {"machine": result.machine}
    if result.machine in labels:
        document["machine_label"] = labels[result.machine]
    document.update({
        "store": str(result.store),
        "configuration_created": result.configuration_created,
        "schedule": schedule_document(result.schedule),
        "ingest": sources_document(result.ingest),
    })
    warnings = [*result.warnings, *result.ingest.warnings, *label_warnings]
    if not options.json:
        print(_text_of(result, document, options.language))
    return Outcome(document, warnings, [], False)


def schedule_show(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `schedule show`: the entry as the scheduler of the operating system
    holds it, or no entry (command-line.md › Commands)."""
    context.require_setup(options.store)
    entry = show_entry(scheduler_kind(context.system, shutil.which), context.run,
                       context.home, context.environ)
    document = {"schedule": schedule_document(entry)}
    if not options.json:
        print(schedule_text(entry, options.language))
    return Outcome(document, [], [], False)


def schedule_create(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `schedule create`: the entry created, or the one of the ledger that
    exists replaced. A version with a development mark stops, because the scheduler does
    not pass the variable that lets such a version write, and a store folder with a word
    the scheduler cannot carry — the folder of `--store`, or the one the machine
    configuration records — stops with the code of a wrong value, before anything is
    written (command-line.md › Commands)."""
    if is_development(context.version):
        raise DevelopmentVersion()
    kind = scheduler_kind(context.system, shutil.which)
    store = resolved_store(context, options.store)
    if not carries_word(kind, str(store)):
        raise WrongValue("--store", str(store))
    _, _, store = context.require_setup(options.store)
    entry = create_entry(kind, context.executable,
                         store, options.time, context.run, context.home, context.environ,
                         context.uid)
    document = {"schedule": schedule_document(entry)}
    if not options.json:
        print(schedule_text(entry, options.language))
    return Outcome(document, [], [], False)


def schedule_remove(context: Context, options: argparse.Namespace) -> Outcome:
    """The action of `schedule remove`: the entry removed from the scheduler of the
    operating system; a scheduler that holds none completes with the warning
    `no_schedule_entry` (command-line.md › Commands)."""
    context.require_setup(options.store)
    removed = remove_entry(scheduler_kind(context.system, shutil.which), context.run,
                           context.home, context.environ, context.uid)
    warnings = [] if removed else [{"code": "no_schedule_entry", "values": {}}]
    document = {"schedule": None}
    if not options.json:
        print(schedule_text(None, options.language))
    return Outcome(document, warnings, [], False)


def _options(options: argparse.Namespace) -> SetupOptions:
    """The options of `run_setup` from the words of the command line: the folders of
    `--native-logs` read as `tool=folder`, and `--schedule yes|no` as the consent it
    gives; `check_values` has stopped a value of another shape before any action runs."""
    native = [read_native_logs(value) for value in getattr(options, "native_logs", [])]
    asked = getattr(options, "schedule", None)
    return SetupOptions(
        store=options.store,
        label=getattr(options, "label", None),
        native_logs=native,
        schedule=None if asked is None else asked == "yes",
        time=options.time,
    )


def _text_of(result: SetupResult, document: dict, language: str) -> str:
    """The text of the setup, from its document: the machine, with its machine label beside
    it when the document holds one, as `machine label` shows them, the store folder, whether
    the person configuration was created, its file and its entries when it was, the
    retention with its advice, the entry of the scheduled ingestion, and the sources of the
    first ingestion."""
    word = label("yes", language) if document["configuration_created"] \
        else label("no", language)
    lines = [f"{label('machine', language)}: {document['machine']}"]
    if "machine_label" in document:
        lines.append(f"{label('label', language)}: {document['machine_label']}")
    lines += [
        f"{label('store_folder', language)}: {document['store']}",
        f"{label('created', language)}: {word}",
    ]
    if result.configuration_created:
        file = Path(document["store"]) / PERSON_FILE
        lines.append(f"{label('person_configuration', language)}: {file}")
        lines.append(label("entries", language))
        lines.extend(_created_entries(result))
    lines.extend(_retention_lines(result, language))
    lines.append(schedule_text(result.schedule, language))
    sources = sources_text(document["ingest"], language)
    if sources:
        lines.append(label("ingestion", language))
        lines.append(sources)
    return "\n".join(lines)


def _created_entries(result: SetupResult) -> list[str]:
    """The lines of the entries of the person configuration that setup created: the name
    of each entry is the table that its keys belong to (configuration.md › Writes)."""
    return [entry_text("time_zone" if "zone" in values else "day_start", values)
            for values in result.entries]


def _retention_lines(result: SetupResult, language: str) -> list[str]:
    """The lines of step 5 (command-line.md › Setup; ingestion.md › Frequency): the
    retention period of each agent tool beside its setting, followed by the command of
    the `linger` key when the setup gives one, which it does on Linux; then what the
    period means, and the advice of a longer retention period with its cost."""
    lines = [label("retention", language)]
    for shown in result.retention:
        period = label("none", language) if shown["days"] is None else shown["days"]
        line = f"{shown['tool']} {shown['setting']} {period}"
        if shown["linger"]:
            line = f"{line} {shown['linger']}"
        lines.append(line)
    lines.append(note("retention_meaning", language))
    lines.append(note("retention_advice", language))
    return lines
