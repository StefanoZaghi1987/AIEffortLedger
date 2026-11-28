"""The commands of the ledger: the context of one run, `main`, the arguments and the help
of the commands, the requirement of a set-up ledger, and the guards of every action that
writes (command-line.md, architecture.md › Modules)."""

import importlib
import os
import shutil
import subprocess
import sys
import uuid
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from platform import system as running_system
from typing import NamedTuple

from .. import days
from ..adapters import ADAPTERS, Adapter
from ..configuration import (
    ConfigurationUnreadable,
    MachineConfiguration,
    PersonConfiguration,
    SetupRequired,
    WrongValue,
    read_machine_configuration,
    read_person_configuration,
    refresh_machine,
    write_machine_configuration,
)
from ..events import writer_version
from ..ingestion import (
    STORES_FOLDER,
    DevelopmentVersion,
    IngestionResult,
    is_development,
)
from ..ingestion.run import DEVELOPMENT_VARIABLE
from ..language import LANGUAGES, label, question
from ..platform import (
    SchedulerEntry,
    default_store_folder,
    installation_identifier,
    machine_folder,
    registry_time_zone_name,
    store_identifier,
    system_time_zone,
)
from ..setup import SetupContext
from .arguments import PROGRAM, WrongUse, build_arguments, check_values, given_options
from .output import INCOMPLETE_CODES, Outcome, emit, json_document, stopped

__all__ = [
    "INCOMPLETE_CODES",
    "ACTIONS",
    "Context",
    "Outcome",
    "WrongUse",
    "ask_by_key",
    "build_arguments",
    "emit",
    "json_document",
    "main",
    "stopped",
]


class Context(NamedTuple):
    """What one run of the command reads from the machine it runs on and from the process
    that started it: the system and its environment, the home of the person, the instant of
    the run, the maker of machine identifiers, the call of a scheduler program, the
    absolute path of the installed command, the installation identifier, the questions to
    the person when the standard input is a terminal, the adapters of the agent tools, the
    time zone of the operating system, the version of the ledger, and the user identifier
    where the system has one.

    `cli` builds the `SetupContext` of setup from it, and passes `version` to
    `run_ingestion` and to `ledger_event`, because every event names the version that wrote
    it (architecture.md › Runtime).
    """

    system: str
    environ: Mapping[str, str]
    home: Path
    now: datetime
    new_uid: Callable[[], str]
    run: Callable[[list[str]], subprocess.CompletedProcess]
    executable: Path
    installation: str | None
    ask: Callable[[str], str] | None
    adapters: Sequence[Adapter]
    time_zone: Callable[[], str | None]
    version: str
    uid: int | None

    def setup_context(self, language: str) -> SetupContext:
        """The context that `run_setup` reads, built from this run: its questions are
        asked by key in the language of the output (`ask_by_key`)."""
        return SetupContext(
            system=self.system,
            environ=self.environ,
            home=self.home,
            now=self.now,
            executable=self.executable,
            run=self.run,
            installation=self.installation,
            ask=ask_by_key(self.ask, language),
            adapters=self.adapters,
            time_zone=self.time_zone,
            new_uid=self.new_uid,
            version=self.version,
            uid=self.uid,
        )

    def require_setup(
        self, store_option: Path | None,
    ) -> tuple[MachineConfiguration, PersonConfiguration, Path]:
        """The two configurations and the store folder of the command, which stops with
        `SetupRequired` when either configuration is missing (command-line.md › Setup).

        The store folder is the folder of `--store`, else the folder that the machine
        configuration records — resolved, so a command reads the store that setup wrote,
        whatever working directory the command runs in — else the default store folder.
        """
        folder = Path(machine_folder(self.system, self.environ, self.home))
        machine = read_machine_configuration(folder)
        if machine is None:
            raise SetupRequired()
        if store_option is not None:
            store = store_option
        elif machine.store:
            store = Path(machine.store).resolve()
        else:
            store = Path(default_store_folder(self.system, self.environ, self.home))
        return machine, read_person_configuration(store), store

    def before_write(self) -> None:
        """The guards of every action that writes (architecture.md › Runtime): a version
        with a development mark writes only when the environment lets it, and the machine
        identifier is made again when the installation identifier changed, as the first
        step of setup does."""
        if is_development(self.version) and self.environ.get(DEVELOPMENT_VARIABLE) != "1":
            raise DevelopmentVersion()
        folder = Path(machine_folder(self.system, self.environ, self.home))
        machine, changed = refresh_machine(
            read_machine_configuration(folder), self.installation, self.new_uid)
        if changed:
            folder.mkdir(parents=True, exist_ok=True)
            write_machine_configuration(folder, machine)


def ask_by_key(ask: Callable[[str], str] | None, language: str) -> Callable[..., str] | None:
    """The questions of a command in the language of the output (command-line.md › Output):
    a function that takes the key of a question of `language` and its values, and asks its
    text through `ask`, the question of the running context, which takes the text; None
    when the context asks nothing, because the standard input is not a terminal. Every
    question of a command reaches the person through it."""
    if ask is None:
        return None

    def asked(key: str, **values: object) -> str:
        """Ask the question of the key with its values, in the language."""
        return ask(question(key, language).format(**values))

    return asked


ACTIONS: dict[str, tuple[str, str]] = {
    "setup": ("ai_effort_ledger.cli.setup_actions", "setup"),
    "schedule show": ("ai_effort_ledger.cli.setup_actions", "schedule_show"),
    "schedule create": ("ai_effort_ledger.cli.setup_actions", "schedule_create"),
    "schedule remove": ("ai_effort_ledger.cli.setup_actions", "schedule_remove"),
    "ingest": ("ai_effort_ledger.cli.store_actions", "ingest"),
    "machine label": ("ai_effort_ledger.cli.store_actions", "machine_label"),
    "config show": ("ai_effort_ledger.cli.store_actions", "config_show"),
    "config add": ("ai_effort_ledger.cli.store_actions", "config_add"),
    "index rebuild": ("ai_effort_ledger.cli.store_actions", "index_rebuild"),
    "version": ("ai_effort_ledger.cli.store_actions", "version"),
    "annotate": ("ai_effort_ledger.cli.entry_actions", "annotate"),
    "entry add": ("ai_effort_ledger.cli.entry_actions", "entry_add"),
    "entries": ("ai_effort_ledger.cli.entry_actions", "entries"),
    "retract": ("ai_effort_ledger.cli.entry_actions", "retract"),
    "timesheet confirm": ("ai_effort_ledger.cli.entry_actions", "timesheet_confirm"),
    "timesheet retract": ("ai_effort_ledger.cli.entry_actions", "timesheet_retract"),
    "purge": ("ai_effort_ledger.cli.entry_actions", "purge"),
    "timesheet": ("ai_effort_ledger.cli.report_actions", "timesheet"),
    "report timesheet": ("ai_effort_ledger.cli.report_actions", "report_timesheet"),
    "report day": ("ai_effort_ledger.cli.report_actions", "report_day"),
    "sessions": ("ai_effort_ledger.cli.report_actions", "sessions"),
    "frozen list": ("ai_effort_ledger.cli.report_actions", "frozen_list"),
    "frozen show": ("ai_effort_ledger.cli.report_actions", "frozen_show"),
    "frozen remove": ("ai_effort_ledger.cli.report_actions", "frozen_remove"),
}
"""The actions of the commands, each as the module and the function that hold it: `main`
imports the module of an action at its first call, so no action module is imported while
the package loads and no import is circular (architecture.md › Modules). Every command of
command-line.md › Commands has its action."""


def machine_data_folder(context: Context) -> Path:
    """The machine-local data folder of the machine that the context runs on
    (architecture.md › Files of a machine)."""
    return Path(machine_folder(context.system, context.environ, context.home))


def resolved_store(context: Context, store_option: Path | None) -> Path:
    """The store folder that a command resolves before it reads or writes anything: the
    folder of `--store`, else the folder the machine configuration records — resolved, so
    a recording of an earlier setup is read where it was written, whatever working
    directory the command runs in — else the default folder; the resolution that the
    second step of setup reads and `require_setup` returns (command-line.md › Setup)."""
    if store_option is not None:
        return store_option
    machine = read_machine_configuration(machine_data_folder(context))
    if machine is not None and machine.store:
        return Path(machine.store).resolve()
    return Path(default_store_folder(context.system, context.environ, context.home))


def machine_configuration(context: Context) -> MachineConfiguration:
    """The machine configuration of the machine that the context runs on, read again: the
    guard of an action that writes may have made the machine identifier again just before
    (command-line.md › Setup)."""
    found = read_machine_configuration(machine_data_folder(context))
    if found is None:
        raise SetupRequired()  # unreachable after `require_setup` passed
    return found


def inside_folder(context: Context, store: Path) -> Path:
    """The folder that one store holds in the machine-local data folder, where its lock,
    its index, and its record of the sources live (architecture.md › Files of a machine)."""
    return (machine_data_folder(context) / STORES_FOLDER
            / store_identifier(store, context.system))


def schedule_document(entry: SchedulerEntry | None) -> dict | None:
    """The `schedule` key of the JSON documents of the schedule commands and of setup: the
    name, the command, and the time of the entry, or None when the scheduler holds none
    (command-line.md › JSON documents)."""
    if entry is None:
        return None
    return {"name": entry.name, "command": " ".join(entry.arguments), "time": entry.time}


def schedule_text(entry: SchedulerEntry | None, language: str) -> str:
    """The text of the `schedule` document: the entry of the scheduled ingestion, or the
    line that names none."""
    if entry is None:
        return f"{label('scheduled_ingestion', language)}: {label('none', language)}"
    return "\n".join([
        f"{label('scheduled_ingestion', language)}:",
        f"{label('name', language)}: {entry.name}",
        f"{label('command', language)}: {' '.join(entry.arguments)}",
        f"{label('hour', language)}: {entry.time}",
    ])


def sources_document(result: IngestionResult) -> dict:
    """The document of `ingest`, and the `ingest` key of the document of setup: one source
    for each folder of native logs, in the order of the scan: per adapter, per agent tool
    of the adapter, per folder that the machine configuration records for that tool
    (command-line.md › JSON documents)."""
    return {"sources": [{"source": one.source, "folder": one.folder,
                         "new_events": one.new_events,
                         "sessions_held_back": one.sessions_held_back}
                        for one in result.sources]}


def sources_text(document: dict, language: str) -> str:
    """The text of the sources document: one block of lines for each folder of native
    logs, an empty line between the blocks."""
    blocks = []
    for source in document["sources"]:
        blocks.append("\n".join([
            f"{label('source', language)}: {source['source']}",
            f"{label('folder', language)}: {source['folder']}",
            f"{label('new_events', language)}: {source['new_events']}",
            f"{label('sessions_held_back', language)}: {source['sessions_held_back']}",
        ]))
    return "\n\n".join(blocks)


def entry_text(entry: str, values: Mapping[str, str]) -> str:
    """One line of the text of `config show` and of `config add`, and of the entries that
    setup shows: the entry and its keys as the file holds them."""
    return " ".join([entry, *(f"{key}={values[key]}" for key in values)])


LOCALTIME = Path("/etc/localtime")
"""The link of the local time of the operating system, whose target `system_time_zone`
reads where the system has one."""


def main(argv: list[str] | None = None, context: Context | None = None) -> int:
    """The command `ai-effort-ledger` (command-line.md › Form): the two streams of the
    process carry UTF-8 from the first word on (`_utf8_streams`), the time zones come only
    from `tzdata` (architecture.md › Runtime), a fault of the command line stops with the
    exit code 2, the action of the command comes from the table of `cli`, and a stop error
    of the action gives the exit code of its kind.

    The parse, its help, and the faults of the values read the command line in the
    language of `--language` alone, read before the parse through the prefix rule of the
    parsers themselves (`given_options`), because no store is read for them. After them
    the language of the output takes the layers of configuration.md › Order: `--language`,
    else `[report] language` of the person configuration, else `en`; a ledger that gives
    no person configuration to read leaves the language of the words, and the action stops
    with its own stop error in it. `version` reads no configuration.
    """
    _utf8_streams()
    days.use_tzdata_only()
    words = list(sys.argv[1:] if argv is None else argv)
    language_word, as_json = given_options(words)
    output_language = language_word or "en"
    try:
        options = build_arguments(output_language).parse_args(words)
    except SystemExit as asked_help:  # the help of a command completes with exit code 0
        return asked_help.code if isinstance(asked_help.code, int) else 0
    except Exception as fault:  # the faults of argparse: a wrong use or a wrong value
        if not hasattr(fault, "exit_code"):
            raise
        return emit(stopped(fault), getattr(fault, "action_name", PROGRAM),
                    as_json, output_language, sys.stdout, sys.stderr)
    options.store = getattr(options, "store", None)
    options.json = getattr(options, "json", False)
    given_language = hasattr(options, "language")
    options.language = getattr(options, "language", output_language)
    options.language_given = given_language
    try:
        check_values(options)
    except (WrongValue, WrongUse) as fault:
        return emit(stopped(fault), options.action, options.json, output_language,
                    sys.stdout, sys.stderr)
    found = ACTIONS[options.action]
    action = getattr(importlib.import_module(found[0]), found[1])
    if context is None:
        context = _running_context()
    if not given_language and options.action != "version":
        options.language = _person_language(context, options.action, options.store,
                                            output_language)
    try:
        outcome = action(context, options)
    except Exception as fault:  # a stop error of the action: the outcome of a stopped run
        if not hasattr(fault, "exit_code"):
            raise
        outcome = stopped(fault)
    # An action whose figures are never incomplete — `config show` — keeps its
    # configuration errors from the exit code 3, and `timesheet confirm` keeps the
    # held-back events of the day from it, because its entries are the declaration of
    # the person (command-line.md › Exit codes).
    return emit(outcome, options.action, options.json, options.language,
                sys.stdout, sys.stderr,
                getattr(options, "configuration_errors_are_incomplete", True),
                getattr(options, "held_back_is_incomplete", True))


def _utf8_streams() -> None:
    """The two streams of the process carry UTF-8 from the first word of the command on
    (command-line.md › Form): the standard output strictly, because the JSON envelope and
    the text tables are UTF-8 by construction, and the standard error with
    `backslashreplace`, the interpreter's own default for a redirected standard error, so
    a warning degrades and never stops a run. A stream that holds no `reconfigure`, such
    as the string streams of the tests, stays as it is."""
    for stream, errors in ((sys.stdout, "strict"), (sys.stderr, "backslashreplace")):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors=errors)


def _person_language(
    context: Context, action_name: str, store_option: Path | None, default: str,
) -> str:
    """The language of the output when the command line gives no `--language`: the key
    `language` of the `[report]` table of the person configuration, else `default`
    (command-line.md › Form). `setup` reads the person configuration of the store folder
    that it resolves, also on a machine without a machine configuration; every other
    command reads the one that `require_setup` gives. A configuration that is missing or
    cannot be read leaves `default`, and the action raises the stop error itself."""
    try:
        if action_name == "setup":
            person = read_person_configuration(resolved_store(context, store_option))
        else:
            person = context.require_setup(store_option)[1]
    except (SetupRequired, ConfigurationUnreadable):
        return default
    return str(person.report.get("language", default))


def _running_context() -> Context:
    """The context of the running process: the system and its environment, the home of the
    person, the instant of the run, the maker of machine identifiers, the call of a
    scheduler program, the installed command (`_installed_executable`), the installation
    identifier of the system, the questions to the person when the standard input is a
    terminal, the adapters of the agent tools, the time zone of the operating system, the
    version of the ledger, and the user identifier where the system has one."""
    system = running_system()
    environ = os.environ
    return Context(
        system=system,
        environ=environ,
        home=Path.home(),
        now=datetime.now(timezone.utc),
        new_uid=lambda: str(uuid.uuid4()),
        run=_run_program,
        executable=_installed_executable(shutil.which, sys.argv[0]),
        installation=installation_identifier(system),
        ask=_ask if sys.stdin.isatty() else None,
        adapters=ADAPTERS,
        time_zone=lambda: system_time_zone(system, environ, LOCALTIME,
                                           registry_time_zone_name),
        version=writer_version(),
        uid=_uid_of_process(),
    )


def _installed_executable(which: Callable[[str], str | None], started: str) -> Path:
    """The absolute path of the installed command that the entry of the scheduled
    ingestion carries (ingestion.md › Frequency): the command that `which` finds on the
    PATH of the machine, else the path that started the process, resolved, when
    `sys.argv[0]` is a path, else the bare name of the program."""
    found = which(PROGRAM)
    if found is not None:
        return Path(found)
    given = Path(started)
    if given.is_file():
        return given.resolve()
    return Path(PROGRAM)


def _run_program(words: list[str]) -> subprocess.CompletedProcess:
    """A program of the operating system with its output captured: the schedulers are the
    only programs the ledger runs (architecture.md › Runtime). A byte that the code page
    of the machine holds not degrades, so one byte of an answer cannot turn a live entry
    of a scheduler into none."""
    return subprocess.run(words, capture_output=True, text=True, errors="replace",
                          check=False)


def _uid_of_process() -> int | None:
    """The user identifier of the running process, or None where the system has none."""
    finder = getattr(os, "getuid", None)
    return finder() if finder is not None else None


def _ask(text: str) -> str:
    """A question to the person at the terminal: its text goes to the standard error, so
    that the standard output holds the text or the JSON document of the command alone, and
    the answer is one line of the standard input without its end; an end of the input is
    an empty answer, which every command reads as no answer (command-line.md › Output)."""
    sys.stderr.write(text)
    sys.stderr.flush()
    return sys.stdin.readline().removesuffix("\n")
