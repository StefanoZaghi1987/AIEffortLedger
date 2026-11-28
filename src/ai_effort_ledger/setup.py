"""The setup steps and the scheduled ingestion: the seven steps with which the ledger starts
on a machine (command-line.md › Setup) — the machine configuration with the folders of
native logs, the store folder, the person configuration when the store folder has none, the
machine label, the retention with its advice, the scheduled ingestion with the consent of
the person, and the first ingestion. Setup can run again at any time: it changes only what
its options or answers change."""

import shutil
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import NamedTuple

from .adapters import Adapter, Retention
from .configuration import (
    MachineConfiguration,
    PersonConfiguration,
    SetupRequired,
    WrongValue,
    create_person_configuration,
    read_machine_configuration,
    read_person_configuration,
    refresh_machine,
    write_machine_configuration,
)
from .configuration.machine import MACHINE_FILE
from .ingestion import IngestionResult, is_development, run_ingestion
from .platform import (
    ENTRY_NAME,
    SchedulerEntry,
    SchedulerFailed,
    carries_word,
    create_entry,
    default_store_folder,
    entry_time,
    machine_folder,
    scheduler_kind,
    show_entry,
)
from .store import write_label

YES_ANSWERS = frozenset({"y", "yes", "s", "si", "sì"})
"""The answers that mean consent, in the two languages of the output; the setup and the
purge ask the same person with it."""

_LINGER_ADVICE = "loginctl enable-linger"
"""The command the advice of a scheduled ingestion names on Linux, because a systemd user
timer runs only while the person is logged in (ingestion.md › Frequency)."""


@dataclass(frozen=True)
class SetupOptions:
    """The options of `setup`: the store folder of `--store`, the machine label of `--label`,
    the folders of `--native-logs <agent tool>=<folder>`, whether the scheduled ingestion is
    asked for (`--schedule yes` or `no`), and the time of the daily ingestion.

    `schedule` is None when the option is absent: only then the consent of the person is
    asked, and only when standard input is a terminal.
    """

    store: Path | None = None
    label: str | None = None
    native_logs: list[tuple[str, str]] = field(default_factory=list)
    schedule: bool | None = None
    time: str = "12:00"


class SetupContext(NamedTuple):
    """What the setup needs from the machine it runs on and from the command that calls it.

    `ask` asks the person the question of a key of the questions of the ledger with its
    values, such as `ask("setup_schedule", time="12:00")`, and gives the answer; the command
    that owns the terminal renders the question in the language of the output. It is None
    when standard input is not a terminal; `time_zone` gives the IANA time zone
    of the operating system, or None when the ledger can hold none; `new_uid` gives
    `refresh_machine` its new machine identifier; `version` goes to the development check of
    the scheduler entry and to `run_ingestion`; `uid` goes to `create_entry` of the
    scheduler; `run` is the only path to a real scheduler program (platform.scheduler).
    """

    system: str
    environ: Mapping[str, str]
    home: Path
    now: datetime
    executable: Path
    run: Callable[[list[str]], subprocess.CompletedProcess]
    installation: str | None
    ask: Callable[..., str] | None
    adapters: Sequence[Adapter]
    time_zone: Callable[[], str | None]
    new_uid: Callable[[], str]
    version: str
    uid: int | None


class SetupResult(NamedTuple):
    """What one setup wrote and showed: the machine identifier, the store folder, whether
    the person configuration was created and with which entries, the retention of each agent
    tool with its advice, the entry of the scheduled ingestion as the scheduler holds it or
    as it would hold it, the result of the first ingestion, and the warnings of the setup
    steps themselves.

    `entries` and `retention` feed the text output only: the JSON document of setup holds
    `machine`, `store`, `configuration_created`, `schedule`, and `ingest`
    (command-line.md › JSON documents).
    """

    machine: str
    store: Path
    configuration_created: bool
    entries: list[dict[str, str]]
    retention: list[dict[str, object]]
    schedule: SchedulerEntry | None
    ingest: IngestionResult
    warnings: list[dict[str, object]]


def run_setup(options: SetupOptions, context: SetupContext) -> SetupResult:
    """Run the seven steps of setup in their order (command-line.md › Setup), and give what
    they wrote and showed.

    Everything the steps read of the machine comes in through the context: the folders, the
    installation identifier, the time zone, the scheduler call, and the questions. Setup
    writes the machine configuration as a whole and creates the person configuration only
    when the store folder has none; the first ingestion takes the lock of the machine and
    the store itself.
    """
    machine_path = Path(machine_folder(context.system, context.environ, context.home))
    machine_path.mkdir(parents=True, exist_ok=True)
    earlier = read_machine_configuration(machine_path)
    machine, _ = refresh_machine(earlier, context.installation, context.new_uid)      # step 1
    machine = _with_native_logs(machine, options, context)
    store_path, machine = _store_folder(options, earlier, machine, context)           # step 2
    write_machine_configuration(machine_path, machine)
    store_path.mkdir(parents=True, exist_ok=True)
    entries, created, person = _person_configuration(store_path, context)             # step 3
    _write_label(options, store_path, machine.machine, context)                       # step 4
    retention = _retention_shown(machine, context)                                    # step 5
    schedule, warnings = _scheduled_ingestion(options, store_path, context)           # step 6
    ingest = run_ingestion(machine, machine_path, store_path, person, context.adapters,  # step 7
                           context.now, context.home, context.system, context.environ,
                           context.version)
    return SetupResult(machine.machine, store_path, created, entries, retention, schedule,
                       ingest, warnings)


def _with_native_logs(
    machine: MachineConfiguration,
    options: SetupOptions,
    context: SetupContext,
) -> MachineConfiguration:
    """The machine configuration with the folders of native logs of step 1: a folder already
    recorded stays, also one the person added; the folders that each agent tool uses on the
    machine join when they exist, read again from the environment at this setup, and so does
    every folder of `--native-logs` (command-line.md › Setup, claude-code-adapter.md ›
    Native logs)."""
    folders: dict[str, list[str]] = {tool: list(held)
                                     for tool, held in machine.native_logs.items()}
    for adapter in context.adapters:
        defaults = adapter.default_folders(context.environ, context.home, context.system)
        for tool, paths in defaults.items():
            for path in paths:
                if Path(str(path)).exists():
                    _add_folder(folders, tool, str(path))
    for tool, folder in options.native_logs:
        _add_folder(folders, tool, folder)
    return machine._replace(native_logs=folders)


def _add_folder(folders: dict[str, list[str]], tool: str, folder: str) -> None:
    """Add one folder of native logs to the folders of its agent tool, once; the recorded
    order stays."""
    held = folders.setdefault(tool, [])
    if folder not in held:
        held.append(folder)


def _store_folder(
    options: SetupOptions,
    earlier: MachineConfiguration | None,
    machine: MachineConfiguration,
    context: SetupContext,
) -> tuple[Path, MachineConfiguration]:
    """The store folder of step 2: the folder of `--store`, else the folder the machine
    configuration records, else the default folder. A word of the person or a recording of
    an earlier setup is resolved to its absolute path — the shape the machine
    configuration records, so that every command and every run of the scheduled ingestion
    reads the store where setup wrote it, whatever working directory they run in
    (architecture.md › Files of a machine, command-line.md › Setup); the default folder is
    absolute by its construction in the environment. The default folder is recorded as no
    key, because the configuration holds the store folder only when it is not the
    default."""
    default = Path(default_store_folder(context.system, context.environ, context.home))
    recorded = earlier.store if earlier is not None else None
    chosen = options.store or (Path(recorded) if recorded else default)
    if chosen is not default:
        chosen = chosen.resolve()
    return chosen, machine._replace(store=str(chosen) if chosen != default else None)


def _person_configuration(
    store_path: Path, context: SetupContext
) -> tuple[list[dict[str, str]], bool, PersonConfiguration]:
    """The person configuration of step 3: when the store folder has none, create it with
    one `[[time_zone]]` entry that holds the time zone of the operating system and one
    `[[day_start]]` entry with 00:00, and give its entries for setup to show them; a store
    folder that holds one stays as it is (configuration.md › Writes)."""
    try:
        return [], False, read_person_configuration(store_path)
    except SetupRequired:
        entries = create_person_configuration(store_path, context.time_zone())
        return entries, True, read_person_configuration(store_path)


def _write_label(
    options: SetupOptions, store_path: Path, machine: str, context: SetupContext
) -> None:
    """The machine label of step 4: the value of `--label`, or the answer of the person,
    written in the store metadata. When standard input is not a terminal and `--label` is
    absent or blank after `strip()`, setup writes no label (command-line.md › Setup)."""
    label = options.label if options.label and options.label.strip() else None
    if label is None and context.ask is not None:
        answer = context.ask("setup_label")
        label = answer.strip() or None
    if label is not None:
        write_label(store_path, machine, label)


def _retention_shown(
    machine: MachineConfiguration, context: SetupContext
) -> list[dict[str, object]]:
    """The retention of step 5: the setting and the period of each agent tool, and on Linux
    the command of the advice of the scheduled ingestion, `loginctl enable-linger`
    (ingestion.md › Frequency). The JSON document of setup holds none of it; the text
    output shows each line with what the period means and the advice of a longer period
    with its cost, from the notes of the language module."""
    linger = _LINGER_ADVICE if context.system == "Linux" else None
    shown = []
    for adapter in context.adapters:
        for tool in adapter.tools:
            held: Retention = adapter.retention(
                tool, context.environ, context.home, context.system, machine.native_logs, ())
            shown.append({"tool": tool, "setting": held.setting, "days": held.days,
                          "linger": linger})
    return shown


def _scheduled_ingestion(
    options: SetupOptions, store_path: Path, context: SetupContext
) -> tuple[SchedulerEntry | None, list[dict[str, object]]]:
    """The scheduled ingestion of step 6: the entry is shown, and created only with
    `--schedule yes` or the consent of the person. A version with a development mark shows
    the entry and never creates it, because the scheduler does not pass the variable that
    lets such a version write. A store folder with a word the scheduler cannot carry stops
    setup with the wrong value that names the folder and the machine configuration file to
    fix, before the entry is created (command-line.md › Setup). When the scheduler ends
    with an error, the warning `scheduler_failed` is given and setup goes on with the next
    step."""
    kind = scheduler_kind(context.system, shutil.which)
    intended = SchedulerEntry(
        ENTRY_NAME, [str(context.executable), "ingest", "--store", str(store_path)],
        entry_time(options.time))
    existing = show_entry(kind, context.run, context.home, context.environ)
    if is_development(context.version) or not _consents(options, context):
        return existing or intended, []
    if not carries_word(kind, str(store_path)):
        machine_file = Path(
            machine_folder(context.system, context.environ, context.home)) / MACHINE_FILE
        raise WrongValue(str(machine_file), str(store_path))
    try:
        return create_entry(kind, context.executable, store_path, options.time, context.run,
                            context.home, context.environ, context.uid), []
    except SchedulerFailed as failed:
        return existing, [{"code": failed.code, "values": failed.values}]


def _consents(options: SetupOptions, context: SetupContext) -> bool:
    """Whether the scheduled ingestion is asked for: with `--schedule yes` it is, with
    `--schedule no` and without a terminal it is not, and without `--schedule` the person
    decides, whose answer counts as consent in the two languages of the output."""
    if options.schedule is not None:
        return options.schedule
    if context.ask is None:
        return False
    return context.ask("setup_schedule", time=options.time).strip().lower() in YES_ANSWERS
