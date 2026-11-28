"""The entry of the scheduled ingestion in the scheduler of the operating system.

The entry is one task of the scheduler, named once, so that the ledger changes nothing that
another program owns. The `run` callable, given by the caller, is the only path to a real
scheduler program; every other step happens in files the caller names with `home` and
`environ`, and the entry of launchd and of systemd is read back from those files. Cron keeps
no entry, because its table of the person is one shared file: there the definition is the
single line to add.
"""

import os
import plistlib
import re
import subprocess
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree
from xml.parsers.expat import ExpatError
from xml.sax.saxutils import escape

ENTRY_NAME = "ai-effort-ledger-ingest"

_TIME = re.compile(r"([01][0-9]|2[0-3]):([0-5][0-9])")
_START_BOUNDARY = re.compile(r"^\d{4}-\d{2}-\d{2}T(\d{2}:\d{2}):\d{2}$")
_ON_CALENDAR = re.compile(r"\*-\*-\* ([01][0-9]|2[0-3]):([0-5][0-9]):00")
_SYSTEMD_BARE = re.compile(r'[^"\\\s]+')

# The escapes systemd reads inside a quoted word of an ExecStart (systemd.service(5) ›
# Command lines); every other backslash sequence is a form the writer never writes.
_SYSTEMD_ESCAPES = {"\\": "\\", '"': '"', "t": "\t", "n": "\n", "r": "\r"}

_REFUSED_CHARACTERS = frozenset(
    character for character in map(chr, range(0x20)) if character not in "\t\n\r")
"""The characters below the space that the entry refuses for every kind, on three
truths: exact for the XML kinds — an XML text of 1.0 admits a tab, a newline and a
carriage return alone of the control characters; documented for systemd — control
characters are not allowed (systemd.service(5) › Command lines); conservative for
cron — the shell would carry them inside the single quotes, and that the carriers
of the crontab hold such bytes is unverified, so the refusal keeps them out of the
table."""

# The elements of the Task Scheduler XML that hold the command, its words, and the time.
_ENTRY_ELEMENTS = ("Command", "Arguments", "StartBoundary")


class SchedulerFailed(Exception):
    """The stop error of a scheduler program that ends with a non-zero code.

    A stop error carries a code, values, and an exit code; the output language holds the text.
    """

    def __init__(self, program: str, exit_code: int) -> None:
        self.code = "scheduler_failed"
        self.values = {"program": program, "exit_code": exit_code}
        self.exit_code = 1
        super().__init__(f"{program} ended with exit code {exit_code}")


@dataclass
class SchedulerEntry:
    """The entry of the scheduled ingestion as the scheduler holds it."""

    name: str
    arguments: list[str]
    time: str


def scheduler_kind(system: str, which: Callable[[str], str | None]) -> str:
    """The kind of scheduler of the system: windows, launchd, systemd, or cron.

    The `which` callable asks the system for the folder of a program, as `shutil.which` does:
    Linux with `systemctl` takes systemd, without it only cron remains.
    """
    if system == "Windows":
        return "windows"
    if system == "Darwin":
        return "launchd"
    if system == "Linux" and which("systemctl"):
        return "systemd"
    return "cron"


def carries_word(kind: str, word: str) -> bool:
    """Whether the entry of the scheduler kind can carry the word unchanged.

    The Task Scheduler and launchd hold the entry in XML, systemd in a line of a unit
    file, cron in one line of the shared table: a control character below the space is
    refused for every kind — exact for the XML kinds, documented for systemd,
    conservative for cron (`_REFUSED_CHARACTERS` says what holds) — and neither would a
    surrogate come back, which no file of UTF-8 holds; cron refuses a newline and a
    carriage return besides, which break its one line, and a `%`, which its families
    read oppositely (`_cron_word` names the reason); `schedule create` refuses such a
    word (command-line.md › Commands).
    """
    refused = _REFUSED_CHARACTERS | {"\n", "\r", "%"} if kind == "cron" else _REFUSED_CHARACTERS
    return not any(character in refused or 0xD800 <= ord(character) <= 0xDFFF
                   for character in word)


def entry_definition(kind: str, executable: Path, store_folder: Path, time: str) -> dict[str, str]:
    """The text of the entry for each file of its kind, as a file name and its text.

    Windows gives the Task Scheduler XML, launchd the plist, systemd the `.service` and the
    `.timer`; cron gives the single line of the shared table of the person.
    """
    hour, minute = _split_time(time)
    if kind == "windows":
        return {f"{ENTRY_NAME}.xml": _windows_xml(executable, store_folder, hour, minute)}
    if kind == "launchd":
        return {f"{ENTRY_NAME}.plist": _launchd_xml(executable, store_folder, hour, minute)}
    if kind == "systemd":
        return {
            f"{ENTRY_NAME}.service": _systemd_service(executable, store_folder),
            f"{ENTRY_NAME}.timer": _systemd_timer(hour, minute),
        }
    if kind == "cron":
        return {f"{ENTRY_NAME}.cron": _cron_line(executable, store_folder, hour, minute)}
    raise ValueError(f"unknown scheduler kind: {kind!r}")


def show_entry(
    kind: str,
    run: Callable[[list[str]], subprocess.CompletedProcess],
    home: Path,
    environ: Mapping[str, str],
) -> SchedulerEntry | None:
    """The entry as the scheduler holds it, or None when the scheduler holds none.

    The Task Scheduler is asked through the `run` callable; launchd and systemd hold the entry
    in the files that a create writes in the folders that `home` and `environ` name, which are
    read without a program; cron holds no entry of the ledger. A query that fails, and a file
    that is absent, cannot be read, or holds no complete entry of the ledger, is no entry, not
    a stop.
    """
    if kind == "launchd":
        return _launchd_entry(home)
    if kind == "systemd":
        return _systemd_entry(home, environ)
    if kind != "windows":
        return None
    asked = run(["schtasks", "/Query", "/TN", ENTRY_NAME, "/XML"])
    if asked.returncode != 0:
        return None
    return _windows_entry(str(asked.stdout))


def create_entry(
    kind: str,
    executable: Path,
    store_folder: Path,
    time: str,
    run: Callable[[list[str]], subprocess.CompletedProcess],
    home: Path,
    environ: Mapping[str, str],
    uid: int | None,
) -> SchedulerEntry:
    """Create the entry, or replace the one of the ledger that already exists.

    Cron writes nothing and calls no program, because its table of the person is one shared
    file that only the person edits; the definition is the line to show. When the scheduler
    program ends with a non-zero code, the call stops with `SchedulerFailed` (ruled
    2026-11-20).
    """
    entry = SchedulerEntry(
        ENTRY_NAME, [str(executable), "ingest", "--store", str(store_folder)], entry_time(time))
    if kind == "windows":
        _windows_create(executable, store_folder, time, run)
    elif kind == "launchd":
        _launchd_create(home, run, uid, executable, store_folder, time)
    elif kind == "systemd":
        _systemd_create(home, environ, run, executable, store_folder, time)
    elif kind != "cron":
        raise ValueError(f"unknown scheduler kind: {kind!r}")
    return entry


def remove_entry(
    kind: str,
    run: Callable[[list[str]], subprocess.CompletedProcess],
    home: Path,
    environ: Mapping[str, str],
    uid: int | None,
) -> bool:
    """Remove the entry, and give False when the scheduler holds none, without stopping.

    Cron never holds an entry of the ledger, so it always gives False. When the scheduler
    program ends with a non-zero code on an entry that exists, the call stops with
    `SchedulerFailed` (ruled 2026-11-20).
    """
    if kind == "windows":
        return _windows_remove(run)
    if kind == "launchd":
        return _launchd_remove(home, run, uid)
    if kind == "systemd":
        return _systemd_remove(home, environ, run)
    if kind != "cron":
        raise ValueError(f"unknown scheduler kind: {kind!r}")
    return False


def _split_time(time: str) -> tuple[int, int]:
    """Read the time as `HH:MM`, two digits for each, in the local time of the operating
    system, hour then minute — the form of `--time <HH:MM>` of the command line
    (command-line.md › Commands), which the readers of the command line have checked
    already."""
    found = _TIME.fullmatch(time)
    if not found:
        raise ValueError(f"the time must be HH:MM, not {time!r}")
    return int(found.group(1)), int(found.group(2))


def entry_time(time: str) -> str:
    """The time of the entry as `HH:MM` with two digits for each of the hour and the
    minute."""
    hour, minute = _split_time(time)
    return f"{hour:02d}:{minute:02d}"


def _windows_xml(executable: Path, store_folder: Path, hour: int, minute: int) -> str:
    """The Task Scheduler XML of the entry: daily, hidden, and started again when missed.

    `Hidden` takes the task out of the list of the Task Scheduler window only; it keeps no
    console window of the ingestion away. The `Arguments` hold each word quoted as the C
    runtime of the program reads it (`list2cmdline` writes those rules), so a store folder
    that ends with a backslash keeps it when the Task Scheduler runs the entry.
    """
    program = escape(str(executable))
    arguments = escape(
        subprocess.list2cmdline(["ingest", "--store", str(store_folder)]))
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>The daily ingestion of the AI Effort Ledger.</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>2000-01-01T{hour:02d}:{minute:02d}:00</StartBoundary>
      <Enabled>true</Enabled>
      <ScheduleByDay>
        <DaysInterval>1</DaysInterval>
      </ScheduleByDay>
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>true</Hidden>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>{program}</Command>
      <Arguments>{arguments}</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def _launchd_xml(executable: Path, store_folder: Path, hour: int, minute: int) -> str:
    """The plist of the launchd agent of the entry: each argument as its own string.

    `StartCalendarInterval` starts an agent whose moment passed while the computer slept when
    the computer wakes, so no other key is needed for a missed start.
    """
    words = [str(executable), "ingest", "--store", str(store_folder)]
    strings = "\n".join(f"      <string>{escape(word)}</string>" for word in words)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>{ENTRY_NAME}</string>
    <key>ProgramArguments</key>
    <array>
{strings}
    </array>
    <key>StartCalendarInterval</key>
    <dict>
      <key>Hour</key>
      <integer>{hour}</integer>
      <key>Minute</key>
      <integer>{minute}</integer>
    </dict>
  </dict>
</plist>
"""


def _systemd_service(executable: Path, store_folder: Path) -> str:
    """The text of the `.service` of the entry, with each word quoted as systemd needs."""
    words = [str(executable), "ingest", "--store", str(store_folder)]
    start = " ".join(_systemd_word(word) for word in words)
    return (
        "[Unit]\n"
        "Description=The daily ingestion of the AI Effort Ledger.\n"
        "\n"
        "[Service]\n"
        "Type=oneshot\n"
        f"ExecStart={start}\n"
    )


def _systemd_timer(hour: int, minute: int) -> str:
    """The text of the `.timer` of the entry: daily at the moment, kept for a missed start."""
    return (
        "[Unit]\n"
        "Description=The daily ingestion of the AI Effort Ledger.\n"
        "\n"
        "[Timer]\n"
        f"OnCalendar=*-*-* {hour:02d}:{minute:02d}:00\n"
        "Persistent=true\n"
        "\n"
        "[Install]\n"
        "WantedBy=timers.target\n"
    )


def _systemd_word(word: str) -> str:
    """One word of an ExecStart, quoted and escaped as systemd reads it.

    A word that holds any whitespace, a double quote or a backslash stands between double
    quotes; inside them the backslash and the double quote are escaped and a tab, a
    newline and a carriage return are the C escapes systemd reads. A `%` is doubled,
    because systemd reads it as the start of a specifier, and a `$` is doubled, because
    systemd reads `$NAME` and `${NAME}` as variables and `$$` as one `$`
    (systemd.service(5) › Command lines).
    """
    escaped = (word.replace("\\", "\\\\").replace('"', '\\"')
               .replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r"))
    doubled = escaped.replace("%", "%%").replace("$", "$$")
    if any(character.isspace() for character in doubled) or '"' in doubled or "\\" in doubled:
        return f'"{doubled}"'
    return doubled


def _cron_line(executable: Path, store_folder: Path, hour: int, minute: int) -> str:
    """The single line of the shared table of cron: minute then hour, then the command
    words, each written so that the shell cron starts reads it as one word."""
    words = [_cron_executable(str(executable)), "ingest", "--store",
             _cron_word(str(store_folder))]
    return f"{minute} {hour} * * * " + " ".join(words)


def _cron_word(word: str) -> str:
    """One word of the line of cron: single quotes, which the shell reads as itself.

    Cron hands the line to a shell, which reads an unquoted word as its own pieces and
    its escapes, so the word stands between single quotes. A `%` stays inside the
    single quotes, unescaped: the families of cron read the two possible escapes of
    `%` oppositely — cronie strips the backslash of `\\%` itself before the shell runs
    (`do_command.c`), busybox crond processes no percent — so no written form carries
    the word on both families, and `schedule create` refuses it (command-line.md ›
    Commands).
    """
    pieces = ["'"]
    for character in word:
        if character == "'":
            pieces.append("'\\''")
        else:
            pieces.append(character)
    pieces.append("'")
    return "".join(pieces)


def _cron_executable(word: str) -> str:
    """The executable word of the line of cron: every `%` of the install folder as `\\%`,
    between the single quotes of a word.

    The install folder is no value of the command, so no guard refuses it; cronie strips
    the backslash of `\\%` itself before the shell runs the line (`do_command.c`), so the
    program path reaches the shell as the folder is (ruled 2026-11-27). The store word
    keeps its refusal, because no written form carries a percent on both families of cron
    (`_cron_word`).
    """
    return _cron_word(word.replace("%", "\\%"))


def _windows_entry(text: str) -> SchedulerEntry | None:
    """The entry that the answer of the Task Scheduler holds, or None when it holds
    none; an answer that holds no XML, or a text no UTF-8 file can hold, is no entry."""
    try:
        root = ElementTree.fromstring(text)
    except (ElementTree.ParseError, ValueError):
        return None
    values: dict[str, str] = {}
    for element in root.iter():
        name = element.tag.rsplit("}", 1)[-1]
        if name in _ENTRY_ELEMENTS and name not in values:
            values[name] = element.text or ""
    program = values.get("Command")
    boundary = values.get("StartBoundary")
    found = _START_BOUNDARY.match(boundary) if boundary else None
    if not program or not found:
        return None
    words = _windows_words(values.get("Arguments") or "")
    return SchedulerEntry(ENTRY_NAME, [program, *words], found.group(1))


def _windows_words(text: str) -> list[str]:
    """The words of `Arguments` as the C runtime reads them: a space or a tab between two
    words, a word between double quotes, a backslash before a quote and a run of
    backslashes before a closing quote doubled (`CommandLineToArgvW`; `list2cmdline`
    writes the same rules). Every text splits, so an answer never stops the read."""
    words: list[str] = []
    word: list[str] = []
    backslashes = 0
    quoted = False
    has_word = False
    for character in text:
        if character == "\\":
            backslashes += 1
            continue
        if character == '"':
            word.append("\\" * (backslashes // 2))
            if backslashes % 2:
                word.append('"')
            else:
                quoted = not quoted
            backslashes = 0
            has_word = True
            continue
        if backslashes:
            word.append("\\" * backslashes)
            backslashes = 0
        if not quoted and character in (" ", "\t"):
            if word or has_word:
                words.append("".join(word))
                word = []
                has_word = False
            continue
        word.append(character)
        has_word = True
    if backslashes:
        word.append("\\" * backslashes)
    if word or has_word:
        words.append("".join(word))
    return words


def _launchd_entry(home: Path) -> SchedulerEntry | None:
    """The entry that the plist of the launchd agent holds, or None when it holds none.

    The plist is the one `_launchd_create` writes: `Label` is the name of the entry,
    `ProgramArguments` its words, and `StartCalendarInterval` its hour and minute.
    """
    # plistlib reports a damaged file through the error of the step that meets it: the
    # parser of XML, a value, the stack of a key outside a dict, a date that is no date,
    # an encoding of the declaration that Python does not know, or nesting deeper than
    # the stack of a binary plist.
    try:
        document = plistlib.loads(_launchd_plist(home).read_bytes())
    except (OSError, ValueError, ExpatError, IndexError, AttributeError,
            LookupError, RecursionError):
        return None
    if not isinstance(document, dict) or document.get("Label") != ENTRY_NAME:
        return None
    words = document.get("ProgramArguments")
    interval = document.get("StartCalendarInterval")
    if (not isinstance(words, list) or not words
            or not all(isinstance(word, str) for word in words)
            or not isinstance(interval, dict)):
        return None
    hour, minute = interval.get("Hour"), interval.get("Minute")
    if not _is_whole(hour, 23) or not _is_whole(minute, 59):
        return None
    return SchedulerEntry(ENTRY_NAME, list(words), f"{hour:02d}:{minute:02d}")


def _is_whole(value: object, highest: int) -> bool:
    """Whether the value of a plist is a whole number from 0 to the highest; a plist boolean
    is no number."""
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= highest


def _systemd_entry(home: Path, environ: Mapping[str, str]) -> SchedulerEntry | None:
    """The entry that the `.timer` and the `.service` of systemd hold, or None when they hold
    none.

    The time is the `OnCalendar` of the timer, in the one form `_systemd_timer` writes; the
    words are the `ExecStart` of the service, read as `_systemd_word` writes them.
    """
    folder = _systemd_folder(home, environ)
    try:
        timer = (folder / f"{ENTRY_NAME}.timer").read_text(encoding="utf-8")
        service = (folder / f"{ENTRY_NAME}.service").read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    calendar = _unit_value(timer, "OnCalendar")
    found = _ON_CALENDAR.fullmatch(calendar) if calendar is not None else None
    start = _unit_value(service, "ExecStart")
    words = _systemd_words(start) if start is not None else None
    if not found or not words:
        return None
    return SchedulerEntry(ENTRY_NAME, words, f"{found.group(1)}:{found.group(2)}")


def _unit_value(text: str, key: str) -> str | None:
    """The value of the first line `key=value` of a unit file, or None without one."""
    for line in text.splitlines():
        name, sign, value = line.partition("=")
        if sign and name == key:
            return value
    return None


def _systemd_words(line: str) -> list[str] | None:
    """The words of an `ExecStart`, the inverse of `_systemd_word`: one space between two
    words, a word between double quotes with its escapes undone, and a doubled `%` and
    `$` one character. None when the line holds no such words, such as a quote that is
    never closed, a backslash escape systemd does not read, or a word glued to a
    quoted one."""
    words: list[str] = []
    position = 0
    while position < len(line):
        if words:
            if line[position] != " ":
                return None
            position += 1
            if position == len(line):
                return None  # a line that ends with the space of a separator holds no word
        word: list[str] = []
        if line[position] == '"':
            position += 1
            while position < len(line) and line[position] != '"':
                character = line[position]
                if character == "\\":
                    if position + 1 >= len(line):
                        return None  # a backslash at the end escapes nothing
                    escape = _SYSTEMD_ESCAPES.get(line[position + 1])
                    if escape is None:
                        return None
                    word.append(escape)
                    position += 2
                    continue
                word.append(character)
                position += 1
            if position >= len(line):
                return None  # a quote that is never closed
            position += 1
        else:
            found = _SYSTEMD_BARE.match(line, position)
            if not found:
                return None
            word = list(found.group())
            position = found.end()
        if position < len(line) and line[position] == '"':
            return None  # a word glued to a quoted word
        words.append("".join(word).replace("%%", "%").replace("$$", "$"))
    return words


def _checked(
    run: Callable[[list[str]], subprocess.CompletedProcess],
    words: list[str],
) -> subprocess.CompletedProcess:
    """Call the scheduler program once and stop with `SchedulerFailed` on a non-zero code."""
    done = run(words)
    if done.returncode != 0:
        raise SchedulerFailed(words[0], done.returncode)
    return done


def _write_temporary(text: str) -> Path:
    """Write the text to a file of the temporary folder of the system and give its path."""
    descriptor, name = tempfile.mkstemp(prefix=f"{ENTRY_NAME}-", suffix=".xml")
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as document:
        document.write(text)
    return Path(name)


def _windows_create(
    executable: Path,
    store_folder: Path,
    time: str,
    run: Callable[[list[str]], subprocess.CompletedProcess],
) -> None:
    """Write the XML to a temporary file and give it to schtasks, which replaces with `/F`."""
    document = entry_definition("windows", executable, store_folder, time)
    path = _write_temporary(document[f"{ENTRY_NAME}.xml"])
    try:
        _checked(run, ["schtasks", "/Create", "/TN", ENTRY_NAME, "/XML", str(path), "/F"])
    finally:
        path.unlink(missing_ok=True)


def _launchd_create(
    home: Path,
    run: Callable[[list[str]], subprocess.CompletedProcess],
    uid: int | None,
    executable: Path,
    store_folder: Path,
    time: str,
) -> None:
    """Write the plist to LaunchAgents of the person and load it with launchctl.

    The bootout before the bootstrap takes an entry of the ledger that the domain already
    holds out of it, so the bootstrap replaces it; a bootout that ends with a non-zero code
    only says that the entry was not loaded, which a create tolerates. A bootstrap that ends
    with a non-zero code leaves no plist on disk.
    """
    domain = f"gui/{_uid_number(uid)}"
    path = _launchd_plist(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    document = entry_definition("launchd", executable, store_folder, time)
    path.write_text(document[f"{ENTRY_NAME}.plist"], encoding="utf-8")
    run(["launchctl", "bootout", f"{domain}/{ENTRY_NAME}"])
    try:
        _checked(run, ["launchctl", "bootstrap", domain, str(path)])
    except SchedulerFailed:
        path.unlink(missing_ok=True)
        raise


def _systemd_create(
    home: Path,
    environ: Mapping[str, str],
    run: Callable[[list[str]], subprocess.CompletedProcess],
    executable: Path,
    store_folder: Path,
    time: str,
) -> None:
    """Write the `.service` and the `.timer` to the user folder of systemd and start the timer.

    A call that ends with a non-zero code leaves no file on disk, as a failed bootstrap
    of launchd leaves no plist, so the scheduler runs no entry that `schedule show` reads.
    """
    folder = _systemd_folder(home, environ)
    folder.mkdir(parents=True, exist_ok=True)
    files = entry_definition("systemd", executable, store_folder, time)
    for name, text in files.items():
        (folder / name).write_text(text, encoding="utf-8")
    try:
        _checked(run, ["systemctl", "--user", "daemon-reload"])
        _checked(run, ["systemctl", "--user", "enable", "--now", f"{ENTRY_NAME}.timer"])
    except SchedulerFailed:
        for name in files:
            (folder / name).unlink(missing_ok=True)
        raise


def _windows_remove(run: Callable[[list[str]], subprocess.CompletedProcess]) -> bool:
    """Delete the entry of the Task Scheduler, or give False when the query finds none."""
    asked = run(["schtasks", "/Query", "/TN", ENTRY_NAME])
    if asked.returncode != 0:
        return False
    _checked(run, ["schtasks", "/Delete", "/TN", ENTRY_NAME, "/F"])
    return True


def _launchd_remove(
    home: Path,
    run: Callable[[list[str]], subprocess.CompletedProcess],
    uid: int | None,
) -> bool:
    """Unload the launchd agent of the entry and remove its plist, or give False without one."""
    path = _launchd_plist(home)
    if not path.exists():
        return False
    _checked(run, ["launchctl", "bootout", f"gui/{_uid_number(uid)}/{ENTRY_NAME}"])
    path.unlink()
    return True


def _systemd_remove(
    home: Path,
    environ: Mapping[str, str],
    run: Callable[[list[str]], subprocess.CompletedProcess],
) -> bool:
    """Stop the timer of the entry and remove its files, or give False without a timer."""
    folder = _systemd_folder(home, environ)
    timer = folder / f"{ENTRY_NAME}.timer"
    if not timer.exists():
        return False
    _checked(run, ["systemctl", "--user", "disable", "--now", f"{ENTRY_NAME}.timer"])
    _checked(run, ["systemctl", "--user", "daemon-reload"])
    timer.unlink(missing_ok=True)
    (folder / f"{ENTRY_NAME}.service").unlink(missing_ok=True)
    return True


def _uid_number(uid: int | None) -> int:
    """The number of `gui/<uid>` for launchctl, which the caller gives."""
    if uid is None:
        raise ValueError("launchd needs the number of gui/<uid>, and the caller gives none")
    return uid


def _launchd_plist(home: Path) -> Path:
    """The plist of the launchd agent of the entry, in LaunchAgents of the person."""
    return home / "Library" / "LaunchAgents" / f"{ENTRY_NAME}.plist"


def _systemd_folder(home: Path, environ: Mapping[str, str]) -> Path:
    """The user folder of systemd: under `$XDG_CONFIG_HOME`, or under `.config` of the home."""
    base = environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(base) / "systemd" / "user"
