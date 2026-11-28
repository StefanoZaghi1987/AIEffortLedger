"""The values of the configuration: durations, patterns, the report parameters with the
defaults of the ledger, and the reading of the configuration files (configuration.md ›
Format)."""

import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

_DURATION = re.compile(r"(?:(\d+)h)?(?:(\d+)min)?(?:(\d+)s)?")
_CLOCK = re.compile(r"(\d+):(\d\d)")
_AT_LINE = re.compile(r"at line (\d+)")
_HEADER = re.compile(r"[ \t]*\[\[?[ \t]*([^\]]*?)[ \t]*\]\]?")
_MULTILINE_BASIC = '"""'
_MULTILINE_LITERAL = "'''"


class ConfigurationUnreadable(Exception):
    """The stop error of a configuration file that the ledger cannot read.

    A stop error carries a code, values, and an exit code; the output language holds the
    text. The ledger never uses part of a file (configuration.md › Format).
    """

    def __init__(self, path: Path, line: int) -> None:
        self.code = "configuration_unreadable"
        self.values = {"path": str(path), "line": line}
        self.exit_code = 1
        super().__init__(f"{path}: line {line}")


class SetupRequired(Exception):
    """The stop error of a store folder that holds no person configuration."""

    def __init__(self) -> None:
        self.code = "setup_required"
        self.values: dict[str, object] = {}
        self.exit_code = 1
        super().__init__("setup_required")


def parse_duration(text: str, clock: bool = False) -> int:
    """The whole seconds of a duration: whole numbers with the units `h`, `min`, and `s`,
    such as `"4h"`, `"10min"`, or `"1h30min"` (configuration.md › Format).

    With `clock`, the form `H:MM` of a command-line value is read too (`"1:30"` is 5400).
    Any other text raises ValueError.
    """
    found = _DURATION.fullmatch(text)
    if found and any(found.groups()):
        hour, minute, second = (int(part) if part else 0 for part in found.groups())
        return hour * 3600 + minute * 60 + second
    if clock:
        clocked = _CLOCK.fullmatch(text)
        if clocked and int(clocked.group(2)) < 60:
            return int(clocked.group(1)) * 3600 + int(clocked.group(2)) * 60
    raise ValueError(f"{text!r} is not a duration")


def pattern_matches(pattern: str, text: str) -> bool:
    """Whether the pattern matches the whole text, `*` standing for any text, with regard
    to case (configuration.md › Matching)."""
    parts = pattern.split("*")
    expression = ".*".join(re.escape(part) for part in parts)
    return re.fullmatch(expression, text) is not None


@dataclass(frozen=True)
class ReportParameters:
    """The report parameters of one report, with the defaults of the ledger.

    The person configuration gives the default of each, and an option of the command can
    change one for one command (configuration.md › Order).
    """

    idle_gap: int = 600
    minimum_attention: int = 60
    stale_limit: int = 14400
    headless_prompts: bool = False
    timesheet_granularity: int = 900
    language: str = "en"


def _load(path: Path) -> tuple[dict[str, object], str]:
    """The tables of a configuration file and its text, for the lines of its keys.

    A file that tomllib cannot read raises ConfigurationUnreadable with the line of the
    fault; a file that cannot be read at all raises it with line 1; a missing file raises
    FileNotFoundError, which each reader turns into its own value.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise
    except (OSError, UnicodeDecodeError):
        raise ConfigurationUnreadable(path, 1) from None
    try:
        data: dict[str, object] = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise ConfigurationUnreadable(path, _fault_line(error)) from None
    return data, text


def _fault_line(error: tomllib.TOMLDecodeError) -> int:
    """The line of the fault: the `lineno` attribute of the error from Python 3.14, before
    that the number after `at line` in its message, 1 when the message names no line,
    because the parenthetical of the message ends with the column."""
    lineno = getattr(error, "lineno", None)
    if isinstance(lineno, int):
        return lineno
    found = _AT_LINE.search(str(error))
    return int(found.group(1)) if found else 1


def _key_line(text: str, key: str) -> int:
    """The first line of the text that assigns the key, or 1 when no line does."""
    expression = re.compile(rf"[ \t]*{re.escape(key)}[ \t]*=")
    for number, line in enumerate(text.splitlines(), start=1):
        if expression.match(line):
            return number
    return 1


def _header_lines(text: str, name: str) -> list[int]:
    """The lines of the headers of the name, in the order of the file: the `[[name]]`
    headers of a list of tables and the `[name]` header of one table.

    tomllib gives no line of an entry, so the reader finds the lines that start, after
    spaces, with `[[<name>]]` or `[<name>]`, and gives the n-th entry of a list the line of
    the n-th header. A header that a string holds names no entry: the scan follows the strings of
    TOML — a basic one from `"`, a literal one from `'`, each also in its multi-line form
    of three quotes, with a backslash escaping the character after it in a basic one, the
    newline of a line-ending backslash included, which still counts its line — and a
    comment from `#` to the end of its line, so a line that begins inside one of them
    names no header. tomllib has accepted the text already, so no string of it spans a
    line that a single-quote or a comment ends.
    """
    lines: list[int] = []
    inside = ""
    at_line_start = True
    number = 1
    position = 0
    while position < len(text):
        character = text[position]
        if character == "\n":
            number += 1
            at_line_start = True
            position += 1
            if inside in ('"', "'"):
                inside = ""
            continue
        if inside in ('"', "'", _MULTILINE_BASIC, _MULTILINE_LITERAL):
            if inside in ('"', _MULTILINE_BASIC) and character == "\\":
                if text.startswith("\n", position + 1):
                    number += 1
                    at_line_start = True
                position += 2
                continue
            if text.startswith(inside, position):
                position += len(inside)
                inside = ""
            else:
                position += 1
            continue
        if at_line_start and character not in " \t":
            at_line_start = False
            found = _HEADER.match(text, position)
            if found and found.group(1) == name:
                lines.append(number)
        if character == "#":
            end = text.find("\n", position)
            position = len(text) if end < 0 else end
            continue
        for delimiter in (_MULTILINE_BASIC, _MULTILINE_LITERAL):
            if text.startswith(delimiter, position):
                inside = delimiter
                position += 3
                break
        else:
            inside = '"' if character == '"' else "'" if character == "'" else ""
            position += 1
    return lines


def _fault(path: Path, text: str, key: str) -> ConfigurationUnreadable:
    """The unreadable error that names the line of the key."""
    return ConfigurationUnreadable(path, _key_line(text, key))
