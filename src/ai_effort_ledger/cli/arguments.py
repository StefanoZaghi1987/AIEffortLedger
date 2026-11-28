"""The arguments of the commands: the parser of the command line, the stop errors of a wrong
use, the check of the values that hold a format after the parse, and the help in the language
of the output (command-line.md › Form, › Commands, › Exit codes, › Setup)."""

import argparse
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime, time
from functools import partial
from pathlib import Path
from typing import NoReturn

from ..configuration import (
    ENTRY_KEYS,
    WrongValue,
    is_day,
    is_hour,
    is_local_instant,
    is_offset_instant,
    parse_duration,
)
from ..events import version_key
from ..language import LANGUAGES, help_text
from .output import COMPLETED, WRONG_USE

PROGRAM = "ai-effort-ledger"
"""The name of the command, as the console script of the package installs it; the usage
lines and the stop errors of a wrong use name it."""

HELP_WIDTH = 96
"""The width of the help, the main help and the help of a command alike, fixed so that the
help reads the same on every terminal: the library wraps the texts of the options under
it, and `_HelpFormatter` lays out the usage of a command under it (command-line.md ›
Commands)."""

HELP_POSITION = 44
"""The last column at which the text of an option starts, fixed with the width: the
library starts a text two columns after the longest invocation of its parser, indent
included, and at this column at most."""

DAY_WORDS = frozenset({"today", "yesterday"})
"""The day values that name a day of the run, which the action of the command resolves
against the local days of the person (command-line.md › Form)."""

TIMESHEET_ACTIONS = frozenset({"confirm", "retract"})
"""The subcommands of `timesheet`, which come before its day (command-line.md ›
Commands)."""

_ENTRY_NAMES = tuple(name.replace("_", "-") for name in ENTRY_KEYS)
"""The names of the entries of `config add` on the command line: the name of its table
with each underscore as a hyphen (command-line.md › Configuration entries)."""


_PLACEHOLDERS: dict[str, str] = {
    "command": "<command>", "subcommand": "<subcommand>", "folder": "<folder>",
    "text": "<text>", "name": "<name>", "day": "<day>",
    "instant": "<instant>", "hour": "<HH:MM>", "zone": "<IANA time zone>",
    "identifier": "<identifier>", "id": "<id>", "project": "<project>",
    "work_item": "<work item>", "repository": "<repository>", "branch": "<branch>",
    "tool": "<agent tool>", "category": "<tool category>", "session": "<id>",
    "duration": "<duration>", "value": "<value of a timesheet entry>", "key": "<key>",
    "version": "<version>", "source": "<source>", "entry": "<entry>", "event": "<event_uid>",
}
"""The placeholder of the value of each metavar in English, as command-line.md writes it,
by the key of the metavar: a stop error of a wrong use names a positional, and an option
whose value is missing, by it, because the metavars of the help are translated."""

_TIMESHEET_ALTERNATIVES = "<day> | confirm | retract"
"""The arguments of `timesheet` of which the command needs one, as a usage joins them."""

_CONFIRM_OPTIONS = (("total", "--total"), ("set", "--set"), ("note", "--note"))
"""The options that `timesheet confirm <day>` alone takes, by their value names, in the
order of the usage (command-line.md › Commands)."""

_REPORT_PARAMETERS = (
    ("idle_gap", "--idle-gap"), ("minimum_attention", "--minimum-attention"),
    ("stale_limit", "--stale-limit"), ("headless_prompts", "--headless-prompts"),
    ("timesheet_granularity", "--timesheet-granularity"))
"""The report parameters as options, by their value names, in the order of the usage: the
options of the commands that compute figures (command-line.md › Form)."""

_FROZEN_REPORTS = frozenset({"report timesheet", "report day"})
"""The commands whose `--note` is the note of the frozen report that `--freeze` keeps
(command-line.md › Commands, › Frozen reports)."""


class WrongUse(Exception):
    """A stop error of a command line that the command cannot read, with exit code 2
    (command-line.md › Exit codes): each cause has its own code and values, which a
    subclass gives. `action_name` is the command of the JSON envelope: the command words
    that the person typed, or the name of the program when the line holds none."""

    def __init__(self, code: str, values: dict[str, object], action_name: str) -> None:
        self.code = code
        self.values = values
        self.action_name = action_name
        self.exit_code = WRONG_USE
        super().__init__(f"{code}: {values}")


class NoAction(WrongUse):
    """The stop error of a command line that gives no command."""

    def __init__(self) -> None:
        super().__init__("no_command", {}, PROGRAM)


class MissingArgument(WrongUse):
    """The stop error of a command that needs arguments the line does not give: the
    command words and every argument that is missing, in the order of the usage of the
    command."""

    def __init__(self, action_name: str, arguments: Sequence[str]) -> None:
        super().__init__("missing_argument",
                         {"command": action_name, "arguments": [*arguments]}, action_name)


class UnknownArgument(WrongUse):
    """The stop error of a command that does not know arguments of the line: the command
    words and every such argument as the person typed it, in the order of the line; an
    option that the parser reads for another form of the command, such as `--total` of
    `timesheet confirm` in `timesheet <day>`, by its name, in the order of the usage."""

    def __init__(self, action_name: str, arguments: Sequence[str]) -> None:
        super().__init__("unknown_argument",
                         {"command": action_name, "arguments": [*arguments]}, action_name)


class ConflictingArguments(WrongUse):
    """The stop error of arguments that the command does not take together: the command
    words and every argument of the conflict."""

    def __init__(self, action_name: str, arguments: Sequence[str]) -> None:
        super().__init__("conflicting_arguments",
                         {"command": action_name, "arguments": [*arguments]}, action_name)


def read_day(text: str) -> str | date:
    """The shape of a day value of the command line, checked (command-line.md › Form):
    `today`, `yesterday`, or a date `YYYY-MM-DD` of a day that exists. The words of the
    day of the run stay text, because the day they name is a local day of the person,
    which the command resolves when it reads the configuration at run time."""
    if text in DAY_WORDS:
        return text
    if is_day(text):
        return date.fromisoformat(text)
    raise ValueError(f"{text!r} is not a day")


def read_instant(text: str) -> datetime:
    """The shape of an instant value of the command line, checked (command-line.md ›
    Form): a local time `YYYY-MM-DDTHH:MM`, which the command resolves against the
    time-zone history of the person at run time, or an RFC 3339 instant with an offset
    or `Z`. A text of no other form, a day without a time included, is a wrong value."""
    if is_local_instant(text) or is_offset_instant(text):
        return datetime.fromisoformat(text)
    raise ValueError(f"{text!r} is not an instant")


def read_instant_or_day(text: str) -> datetime | date | str:
    """The shape of a value that an entry of `config add` reads as an instant or as a day
    (command-line.md › Configuration entries): the `from` of a time-zone entry is an
    instant, the `from` of a day-start entry and the ends of an identity rule are local
    days. `today` and `yesterday` stay text, because the day they name is a local day of
    the person, which the action of the command resolves at run time."""
    if text in DAY_WORDS:
        return text
    if is_local_instant(text) or is_offset_instant(text):
        return datetime.fromisoformat(text)
    if is_day(text):
        return date.fromisoformat(text)
    raise ValueError(f"{text!r} is neither an instant nor a day")


def read_duration(text: str) -> int:
    """The whole seconds of a duration value of the command line (command-line.md › Form):
    `1h30min`, or `H:MM` such as `1:30`."""
    return parse_duration(text, clock=True)


def read_hour(text: str) -> time:
    """The shape of an hour of the day, `HH:MM` with two digits each, such as `12:00`
    (command-line.md › Commands)."""
    if is_hour(text):
        return time.fromisoformat(text)
    raise ValueError(f"{text!r} is not an hour")


def read_native_logs(text: str) -> tuple[str, str]:
    """The shape of a value of `--native-logs`: `<agent tool>=<folder>`, both not empty
    (command-line.md › Setup)."""
    tool, mark, folder = text.partition("=")
    if not mark or not tool or not folder:
        raise ValueError(text)
    return tool, folder


def read_version(text: str) -> tuple:
    """The shape of a writer version, read as its order key (command-line.md › Form)."""
    return version_key(text)


def read_frozen_id(text: str) -> str:
    """The shape of the identifier of a frozen report (command-line.md › Frozen reports):
    one name of a file below the frozen folder of a machine, as the store itself keeps it
    — text with no `/` and no `\\`, and neither empty nor `.` nor `..`, the names no file
    of a folder has — because the command joins the identifier into the path of that file
    below the store folder."""
    if text and text not in (".", "..") and "/" not in text and "\\" not in text:
        return text
    raise ValueError(text)


def given_options(words: Sequence[str]) -> tuple[str | None, bool]:
    """The language that the words of the command line give `--language`, and whether one
    of them gives `--json`, read before the parse builds its parser (`main`): each word
    resolves through the prefix rule of the parser that reads it — the matching of
    `_option_of`, which takes an abbreviation that one option alone holds — so the
    language of the help and of the faults, and the JSON envelope of a fault, read the
    line as the parse reads it. The last `--language` whose value a language of the output
    holds wins, and a value that no language holds leaves the one before it; the words
    after `--` are text, and the word that follows an option is that option's value."""
    reader = build_arguments()
    language: str | None = None
    as_json = False
    plain = False
    index = 0
    while index < len(words):
        word = words[index]
        index += 1
        if plain:
            continue
        if word == "--":
            plain = True
            continue
        subcommands = _subcommands(reader)
        if subcommands is not None and word in subcommands.choices:
            reader = subcommands.choices[word]
            continue
        action, value = _option_of(reader, word)
        if action is None or (action.nargs == 0 and value is not None):
            continue
        if action.nargs == 0:
            if "--json" in action.option_strings:
                as_json = True
            continue
        if value is None and index < len(words) and words[index] != "--" \
                and not _is_option(reader, words[index]):
            value, index = words[index], index + 1
        if "--language" in action.option_strings and value in LANGUAGES:
            language = value
    return language, as_json


def check_values(options: argparse.Namespace) -> None:
    """The command line after the parse: the words of `timesheet`, whose subcommand and
    whose day may come as one word, the options that only one form of a command takes,
    and the values of the options that hold a format, which the parse left as text and
    which stay text. A value that no format holds stops with `WrongValue`, which names the
    option, or the placeholder of the positional, and the value; a missing word of the
    timesheet stops with `MissingArgument`, a word too many with `UnknownArgument`, and so
    does an option of another form of `timesheet`; `--note` of a report without `--freeze`
    stops with `MissingArgument`, which names `--freeze` (command-line.md › Commands, ›
    Exit codes)."""
    if options.action == "timesheet":
        _timesheet(options)
    if (options.action in _FROZEN_REPORTS and hasattr(options, "note")
            and not getattr(options, "freeze", False)):
        raise MissingArgument(options.action, ["--freeze"])
    for dest, (option, reader) in getattr(options, "readers", {}).items():
        value = getattr(options, dest, None)
        if value is None:
            continue
        for one in value if isinstance(value, list) else (value,):
            try:
                reader(one)
            except ValueError:
                raise WrongValue(option, one) from None


def _timesheet(options: argparse.Namespace) -> None:
    """The action and the day of `timesheet`: `timesheet <day>` gives no subcommand, so
    its first word is the day; `timesheet confirm <day>` and `timesheet retract <day>`
    give the subcommand before the day. A day that the command does not read, or a
    subcommand without the day after it, stops the command. `--total`, `--set`, and
    `--note` belong to `timesheet confirm` alone, and `timesheet retract`, which computes
    no figures, takes no report parameter either: such an option stops the other form
    with `UnknownArgument` (command-line.md › Commands)."""
    words = [word for word in (getattr(options, "subcommand", None),
                               getattr(options, "day", None)) if word is not None]
    if not words:
        raise MissingArgument(options.action, [_TIMESHEET_ALTERNATIVES])
    held = _timesheet_held(words)
    if words[0] in TIMESHEET_ACTIONS:
        options.action = f"timesheet {words[0]}"
        if len(words) < held:
            raise MissingArgument(options.action, [_PLACEHOLDERS["day"]])
        if words[0] == "retract":
            _refuse_options(options, (*_CONFIRM_OPTIONS, *_REPORT_PARAMETERS))
        return
    if len(words) > held:
        raise UnknownArgument(options.action, words[held:])
    _refuse_options(options, _CONFIRM_OPTIONS)
    options.day = words[0]  # the day form: the first word was the day, as the person typed it


def _refuse_options(options: argparse.Namespace, refused: Sequence[tuple[str, str]]) -> None:
    """Stop the command with `UnknownArgument` when the line gives any of the refused
    options, each by its name, in the order of the usage; an option that the line does
    not give holds no value, because its default is left out of the values."""
    given = [flag for dest, flag in refused if hasattr(options, dest)]
    if given:
        raise UnknownArgument(options.action, given)


def _timesheet_held(words: Sequence[str]) -> int:
    """The number of positional words that `timesheet` reads: a subcommand and its day,
    or the day of the day form alone."""
    return 2 if words and words[0] in TIMESHEET_ACTIONS else 1


_UNRECOGNIZED = "unrecognized arguments: "
"""The start of the text of argparse for words that no parser read, the same on Python
3.11, 3.12, and 3.13; `_fault_of` reads it only when the words show no fault."""


class _Refused(Exception):
    """A fault that argparse found in a command line, with the text of argparse; the parser
    of the whole line turns it into the stop error of its cause (`_fault_of`)."""

    def __init__(self, text: str) -> None:
        self.text = text
        super().__init__(text)


class _Line:
    """The words of a command line as the parsers of the commands read them: the command
    words that the parsers know, the positional words of the last command, the words that
    no parser knows with their places, the first fault in the order of the words, and the
    arguments that the last command needs and the line does not give.

    Each parser reads the words up to the word of its subcommand, which gives the rest of
    the line to the parser of the subcommand; an option takes the next word as its value
    unless that word is an option or `--`; a word that starts with a hyphen and that no
    option holds takes no value; an option may be shortened to a start that one option
    alone holds; after `--` every word is positional. These are the rules of argparse.
    """

    def __init__(self, reader: argparse.ArgumentParser, words: Sequence[str]) -> None:
        self.words = list(words)
        self.path: list[str] = []
        self.positionals: list[str] = []
        self.unknown: list[tuple[int, str]] = []
        self.fault: Callable[[str], Exception] | None = None
        self.missing: list[str] = []
        self._read(reader)

    def action_name(self) -> str:
        """The command words that the person typed, wherever they stand among the options,
        with the subcommand of `timesheet`, which the parser reads as a positional word;
        the name of the program when the line holds no command word."""
        path = list(self.path)
        if path == ["timesheet"] and self.positionals[:1] \
                and self.positionals[0] in TIMESHEET_ACTIONS:
            path.append(self.positionals[0])
        return " ".join(path) or PROGRAM

    def _first(self, fault: Callable[[str], Exception]) -> None:
        """Keep the fault unless an earlier word gave one."""
        if self.fault is None:
            self.fault = fault

    def _read(self, top: argparse.ArgumentParser) -> None:
        """Read the words from the parser of the whole line down to the parser of the last
        command word."""
        reader, index, plain = top, 0, False
        while True:
            subcommands = _subcommands(reader)
            slots = [action for action in reader._actions
                     if not action.option_strings and action is not subcommands]
            seen: list[argparse.Action] = []
            positionals: list[tuple[int, str]] = []
            deeper = None
            while index < len(self.words) and deeper is None:
                at, word = index, self.words[index]
                index += 1
                if not plain and word == "--":
                    plain = True
                elif not plain and _is_option(reader, word):
                    index = self._option(reader, at, seen)
                elif subcommands is None:
                    positionals.append((at, word))
                    self._choice(slots, len(positionals) - 1, word)
                elif word in subcommands.choices:
                    deeper = subcommands.choices[word]
                    self.path.append(word)
                else:  # the place of the subcommand holds a word that no command holds
                    self.unknown.append((at, word))
                    return
            if deeper is not None:
                reader = deeper
                continue
            self.positionals = [word for _, word in positionals]
            held = (_timesheet_held(self.positionals) if self.path == ["timesheet"]
                    else len(slots))
            self.unknown.extend(positionals[held:])
            self.missing = _missing(reader, seen, len(positionals), slots, subcommands)
            return

    def _option(self, reader: argparse.ArgumentParser, at: int,
                seen: list[argparse.Action]) -> int:
        """Read the option at the place `at`, with its value, and give the place of the
        next word."""
        word, index = self.words[at], at + 1
        action, value = _option_of(reader, word)
        if action is None or (action.nargs == 0 and value is not None):
            self.unknown.append((at, word))
            return index
        flag = _flag(action)
        if action.nargs != 0 and value is None:
            if index < len(self.words) and self.words[index] != "--" \
                    and not _is_option(reader, self.words[index]):
                value, index = self.words[index], index + 1
            else:
                needed = f"{flag} {_placeholder(action)}"
                self._first(lambda action_name: MissingArgument(action_name, [needed]))
        if value is not None and action.choices is not None and value not in action.choices:
            self._first(partial(_wrong_value, flag, value))
        together = _together(reader, action, seen)
        if together:
            self._first(lambda action_name: ConflictingArguments(action_name, together))
        seen.append(action)
        return index

    def _choice(self, slots: Sequence[argparse.Action], slot: int, word: str) -> None:
        """Check the positional word of the slot against the choices of the slot."""
        if slot < len(slots) and slots[slot].choices is not None \
                and word not in slots[slot].choices:
            self._first(partial(_wrong_value, _placeholder(slots[slot]), word))


def _fault_of(reader: argparse.ArgumentParser, words: Sequence[str], text: str) -> Exception:
    """The stop error of a command line that argparse refused, derived from its words and
    from the parsers of the commands, not from the parser that raised (`_Line`). A word
    that no parser knows comes first; then the first fault in the order of the words: an
    option without its value, a value out of the choices of its option or positional, or
    two options of one group; then the arguments that the command needs, and no command
    at all. Where the words show no fault, as for a line that Python 3.11 refuses and
    later versions read, the words that the text of argparse names are not known; where
    the text names no word either, a branch that no refusal of today reaches, the
    arguments the command does not know are the words that start with `--`, else the
    first word after the last command word."""
    line = _Line(reader, words)
    action_name = line.action_name()
    if line.unknown:
        return UnknownArgument(action_name, [word for _, word in sorted(line.unknown)])
    if line.fault is not None:
        return line.fault(action_name)
    if line.missing:
        return MissingArgument(action_name, line.missing) if line.path else NoAction()
    if text.startswith(_UNRECOGNIZED):
        return UnknownArgument(action_name, text[len(_UNRECOGNIZED):].split(" "))
    long_options = [word for word in words if word.startswith("--") and word not in line.path]
    if long_options:
        return UnknownArgument(action_name, long_options)
    place = -1
    if line.path:
        for at, word in enumerate(words):
            if word == line.path[-1]:
                place = at
    return UnknownArgument(action_name, words[place + 1:place + 2])


def _wrong_value(key: str, value: str, action_name: str) -> WrongValue:
    """The wrong value of the key in the command line of the command words given."""
    fault = WrongValue(key, value)
    fault.action_name = action_name
    return fault


def _subcommands(reader: argparse.ArgumentParser) -> argparse.Action | None:
    """The action of the subcommands of the parser, or None when it has none."""
    return next((action for action in reader._actions
                 if isinstance(action, argparse._SubParsersAction)), None)


def _is_option(reader: argparse.ArgumentParser, word: str) -> bool:
    """Whether the parser reads the word as an option, known or not, as argparse does: a
    word that starts with a hyphen, but not `-` alone, a negative number, or a word with a
    space that no option holds."""
    if not word.startswith("-") or word == "-":
        return False
    if _option_of(reader, word)[0] is not None:
        return True
    if word[1:].replace(".", "", 1).isdigit():
        return False
    return " " not in word


def _option_of(
    reader: argparse.ArgumentParser, word: str,
) -> tuple[argparse.Action | None, str | None]:
    """The option of the parser that the word names, by one of its strings or by a start
    that one option alone holds, and the value that the word gives after `=`; no option
    when none or more than one holds the word."""
    held = reader._option_string_actions
    if word in held:
        return held[word], None
    name, mark, value = word.partition("=")
    if mark and name in held:
        return held[name], value
    if name.startswith("--"):
        starting = {id(action): action for string, action in held.items()
                    if string.startswith(name)}
        if len(starting) == 1:
            return next(iter(starting.values())), value if mark else None
    return None, None


def _flag(action: argparse.Action) -> str:
    """The option string by which a stop error names the option."""
    return action.option_strings[-1]


def _placeholder(action: argparse.Action) -> str:
    """The placeholder of the value of an option, or of a positional, in English, as
    command-line.md writes it: the placeholder of its metavar, else its choices joined by
    `|`."""
    placeholder = getattr(action.metavar, "placeholder", None)
    if placeholder is not None:
        return placeholder
    if action.choices is not None:
        return "|".join(action.choices)
    return f"<{action.dest}>"


def _together(
    reader: argparse.ArgumentParser, action: argparse.Action, seen: Sequence[argparse.Action],
) -> list[str]:
    """The options of a mutually exclusive group of the action that the line gives with
    it, in the order of the group, when the line gives more than one; else none."""
    for group in reader._mutually_exclusive_groups:
        members = group._group_actions
        if action in members:
            given = [member for member in members if member is action or member in seen]
            if len(given) > 1:
                return [_flag(member) for member in given]
    return []


def _missing(
    reader: argparse.ArgumentParser, seen: Sequence[argparse.Action], given: int,
    slots: Sequence[argparse.Action], subcommands: argparse.Action | None,
) -> list[str]:
    """The arguments that the parser needs and the line does not give, in the order of its
    usage: the required options, a required group of options as one argument at the place
    of its first member, the required positionals, and the subcommands as one argument."""
    groups = {}
    for group in reader._mutually_exclusive_groups:
        members = group._group_actions
        if group.required and not any(member in seen for member in members):
            groups[id(members[0])] = " | ".join(_flag(member) for member in members)
    missing = []
    for action in reader._actions:
        if id(action) in groups:
            missing.append(groups[id(action)])
        elif action.option_strings and action.required and action not in seen:
            missing.append(_flag(action))
    missing.extend(_placeholder(action) for slot, action in enumerate(slots)
                   if action.required and slot >= given)
    if subcommands is not None:
        missing.append(" | ".join(subcommands.choices))
    return missing


def _part_of(
    formatter: argparse.HelpFormatter, action: argparse.Action, grouped: bool,
) -> str:
    """The part of one action in the usage, with the argument that its metavar and its
    `nargs` give; `grouped` leaves out the brackets of an action of a mutually exclusive
    group, which brings its own."""
    if not action.option_strings:
        part = formatter._format_args(action, action.dest)
        if grouped and part.startswith("[") and part.endswith("]"):
            part = part[1:-1]
        return part
    if action.nargs == 0:
        part = action.option_strings[0]
    else:
        argument = formatter._format_args(action, action.dest.upper())
        part = f"{action.option_strings[0]} {argument}"
    return part if grouped or action.required else f"[{part}]"


def _usage_parts(
    formatter: argparse.HelpFormatter, actions: Sequence[argparse.Action],
    groups: Sequence[argparse._MutuallyExclusiveGroup],
) -> list[str]:
    """The parts of a usage: first the options of the parser, each in the order of the
    parser, then its positionals (command-line.md › Commands). An option that is not
    required is one part in brackets, with its first option string and its argument; a
    required option is the same without brackets; a positional is its argument. The
    members of a mutually exclusive group take no brackets of their own: the first opens
    the group, `(` when it is required and `[` otherwise, every member but the last ends
    with ` |`, and the last closes it, so that the group breaks after a `|` and nowhere
    else."""
    order = ([action for action in actions if action.option_strings]
             + [action for action in actions if not action.option_strings])
    shown = [action for action in order if action.help is not argparse.SUPPRESS]
    runs: dict[int, tuple[int, bool]] = {}
    for group in groups:
        members = [i for i, action in enumerate(shown) if action in group._group_actions]
        if members and members == list(range(members[0], members[-1] + 1)):
            runs[members[0]] = (members[-1] + 1, group.required)
    before: dict[int, str] = {}
    after: dict[int, str] = {}
    for start, (end, required) in runs.items():
        before[start] = "(" if required else "["
        after[end - 1] = ")" if required else "]"
        for i in range(start, end - 1):
            after[i] = " |"
    parts = []
    for index, action in enumerate(shown):
        grouped = any(start <= index < end for start, (end, _) in runs.items())
        parts.append(before.get(index, "") + _part_of(formatter, action, grouped)
                     + after.get(index, ""))
    return parts


class _HelpFormatter(argparse.HelpFormatter):
    """The formatter of the help: its width and the last column of the text of an option
    are fixed, so the help reads the same on every terminal, and its usage lines start
    with the word `usage` of the output language.

    The usage of a parser that gives none is laid out by the ledger (`_rows`), not by the
    library, because the line breaks of the library follow the version of its interpreter:
    through Python 3.12 it keeps a mutually exclusive group whole and may part an option
    from its argument, and 3.13 breaks the group after each `|`."""

    def __init__(self, prog: str, output_language: str = "en") -> None:
        super().__init__(prog, max_help_position=HELP_POSITION, width=HELP_WIDTH)
        self.output_language = output_language

    def _format_usage(self, usage, actions, groups, prefix) -> str:
        """The usage that the parser gives, as the main parser does (command-line.md ›
        Form); without one, the parts of the parser in rows, by the rule of the ledger."""
        if prefix is None:
            prefix = help_text("usage", self.output_language) + ": "
        if usage is not None:
            return f"{prefix}{usage % dict(prog=self._prog)}\n\n"
        return self._rows(prefix, _usage_parts(self, actions, groups)) + "\n\n"

    def _rows(self, prefix: str, parts: Sequence[str]) -> str:
        """The parts of a usage in rows of at most `HELP_WIDTH` columns: the first row
        follows the name of the program, and each next row starts under the first part. A
        part joins a row while the row fits; a part that does not fit starts the next row,
        so that a row breaks between two parts and never inside one, and a part longer
        than the width stands alone on its row, whole."""
        under = " " * (len(prefix) + len(self._prog) + 1)
        rows = [prefix + self._prog]
        for part in parts:
            if len(rows[-1]) + 1 + len(part) <= HELP_WIDTH:
                rows[-1] += " " + part
            else:
                rows.append(under + part)
        return "\n".join(rows)


class _HelpAction(argparse.Action):
    """The action of `-h` and `--help`: it writes the help of the parser and stops the run
    with the exit code of a command that completed, before any store is read
    (command-line.md › Commands, › Setup)."""

    def __init__(
        self, option_strings, dest, default=False, required=False, help=None,
    ) -> None:
        super().__init__(option_strings=option_strings, dest=dest, nargs=0,
                         default=default, required=required, help=help)

    def __call__(self, reader, namespace, values, start=None) -> NoReturn:
        reader.print_help()
        raise SystemExit(COMPLETED)


class _Reader(argparse.ArgumentParser):
    """The parser of a command: on a fault of the command line, the parse raises the stop
    error of its cause, which the words of the whole line give (`_fault_of`), instead of
    writing the text of argparse, so a wrong use writes one line `error:` in the output
    language and no usage line (command-line.md › Output, › Exit codes)."""

    def __init__(
        self, *args, action_name: str | None = None, output_language: str = "en", **kwargs,
    ) -> None:
        self.action_name = action_name
        self.output_language = output_language
        kwargs.setdefault(
            "formatter_class", partial(_HelpFormatter, output_language=output_language))
        super().__init__(*args, **kwargs)

    def format_help(self) -> str:
        """The help of the parser, whose words for its groups come from the language."""
        for group in self._action_groups:
            if group.title == "positional arguments":
                group.title = help_text("arguments", self.output_language)
            elif group.title == "options":
                group.title = help_text("options", self.output_language)
        return super().format_help()

    def parse_args(
        self, args: Sequence[str] | None = None, namespace: argparse.Namespace | None = None,
    ) -> argparse.Namespace:
        """The values of the command line; a fault of the line raises its stop error. The
        parsers of the subcommands read their words through `parse_known_args`, so the
        parser of the whole line gives the stop error."""
        words = list(sys.argv[1:] if args is None else args)
        try:
            return super().parse_args(words, namespace)
        except _Refused as refused:
            raise _fault_of(self, words, refused.text) from None

    def error(self, text: str) -> NoReturn:
        raise _Refused(text)


class _Metavar(str):
    """The placeholder of an option or of a positional in the help, in the language of the
    output, which also carries its placeholder in English as command-line.md writes it."""

    placeholder: str

    def __new__(cls, text: str, placeholder: str) -> "_Metavar":
        made = super().__new__(cls, text)
        made.placeholder = placeholder
        return made


def _metavar(key: str, language: str, placeholder: str | None = None) -> _Metavar:
    """The placeholder of an option in the help, in the language, as its upper-case word,
    with its placeholder in English: the one of the key, unless one is given."""
    return _Metavar(help_text(f"metavar_{key}", language).upper(),
                    placeholder or _PLACEHOLDERS[key])


def _own_help(reader: argparse.ArgumentParser, language: str) -> None:
    """The own `-h` of a parser, whose word of help comes from the language."""
    reader.add_argument(
        "-h", "--help", action=_HelpAction, default=argparse.SUPPRESS,
        help=help_text("help", language))


def _global_options(reader: argparse.ArgumentParser, language: str) -> None:
    """The three options of every command (command-line.md › Form): the store folder of
    this command, the JSON document, and the language of the output. A default that the
    parser leaves out of the values, so that a value before the command stays."""
    reader.add_argument(
        "--store", type=Path, default=argparse.SUPPRESS, metavar=_metavar("folder", language),
        help=help_text("help_option_store", language))
    reader.add_argument(
        "--json", action="store_true", default=argparse.SUPPRESS,
        help=help_text("help_option_json", language))
    reader.add_argument(
        "--language", choices=LANGUAGES, default=argparse.SUPPRESS,
        help=help_text("help_option_language", language))


def _report_parameters(
    reader: argparse.ArgumentParser,
    language: str,
    values: dict[str, tuple[str, Callable[[str], object]]],
) -> None:
    """The report parameters as options of a command that computes figures
    (command-line.md › Form): each read as text and checked after the parse, the four
    durations in the forms of a duration, which their placeholder names."""
    reader.add_argument(
        "--idle-gap", default=argparse.SUPPRESS, metavar=_metavar("duration", language),
        help=help_text("help_option_idle_gap", language))
    values["idle_gap"] = ("--idle-gap", read_duration)
    reader.add_argument(
        "--minimum-attention", default=argparse.SUPPRESS,
        metavar=_metavar("duration", language),
        help=help_text("help_option_minimum_attention", language))
    values["minimum_attention"] = ("--minimum-attention", read_duration)
    reader.add_argument(
        "--stale-limit", default=argparse.SUPPRESS, metavar=_metavar("duration", language),
        help=help_text("help_option_stale_limit", language))
    values["stale_limit"] = ("--stale-limit", read_duration)
    reader.add_argument(
        "--headless-prompts", choices=("yes", "no"), default=argparse.SUPPRESS,
        help=help_text("help_option_headless_prompts", language))
    reader.add_argument(
        "--timesheet-granularity", default=argparse.SUPPRESS,
        metavar=_metavar("duration", language),
        help=help_text("help_option_timesheet_granularity", language))
    values["timesheet_granularity"] = ("--timesheet-granularity", read_duration)


def build_arguments(output_language: str = "en") -> argparse.ArgumentParser:
    """The parser of the command line in the language of the output (command-line.md ›
    Form, › Commands): the three options of every command, an own `-h` on every parser,
    every command of the spec with the options of its rows, and the report parameters of
    the commands that compute figures."""
    common = _Reader(add_help=False, output_language=output_language)
    _global_options(common, output_language)
    reader = _Reader(
        prog=PROGRAM, output_language=output_language, add_help=False, parents=[common],
        description=help_text("description", output_language),
        usage=f"{PROGRAM} <{_metavar('command', output_language).lower()}> "
              f"[<{_metavar('subcommand', output_language).lower()}>] "
              f"[{help_text('options', output_language)}]")
    _own_help(reader, output_language)
    # Without a metavar the library heads the section with every choice in braces, on one
    # line over the width.
    commands = reader.add_subparsers(
        title=help_text("commands", output_language), dest="action", required=True,
        metavar=f"<{_metavar('command', output_language).lower()}>",
        parser_class=_Reader, prog=PROGRAM)

    def declare(parent, name: str, key: str, path: str) -> argparse.ArgumentParser:
        """One command of the spec, with the three options of every command, an own `-h`,
        and its name as the action that the table of `cli` holds."""
        sub = parent.add_parser(
            name, action_name=path, output_language=output_language, add_help=False,
            parents=[common], help=help_text(key, output_language),
            description=help_text(key, output_language))
        sub.set_defaults(action=path)
        _own_help(sub, output_language)
        return sub

    values: dict[str, tuple[str, Callable[[str], object]]] = {}
    setup = declare(commands, "setup", "help_setup", "setup")
    setup.add_argument("--label", default=argparse.SUPPRESS,
                       metavar=_metavar("text", output_language),
                       help=help_text("help_option_label", output_language))
    setup.add_argument("--schedule", choices=("yes", "no"), default=argparse.SUPPRESS,
                       help=help_text("help_option_schedule", output_language))
    setup.add_argument("--native-logs", action="append", default=argparse.SUPPRESS,
                       metavar=_Metavar(f"{_metavar('tool', output_language)}="
                                        f"{_metavar('folder', output_language)}",
                                        "<agent tool>=<folder>"),
                       help=help_text("help_option_native_logs", output_language))
    setup.add_argument("--time", default="12:00", metavar=_metavar("hour", output_language),
                       help=help_text("help_option_time", output_language))
    values["native_logs"] = ("--native-logs", read_native_logs)
    values["time"] = ("--time", read_hour)
    setup.set_defaults(readers=values)

    schedule = declare(commands, "schedule", "help_schedule", "schedule")
    schedule_words = schedule.add_subparsers(
        title=help_text("commands", output_language), dest="action", required=True,
        parser_class=_Reader, prog=schedule.prog)
    declare(schedule_words, "show", "help_schedule_show", "schedule show")
    values = {}
    create = declare(schedule_words, "create", "help_schedule_create", "schedule create")
    create.add_argument("--time", default="12:00", metavar=_metavar("hour", output_language),
                        help=help_text("help_option_time", output_language))
    values["time"] = ("--time", read_hour)
    create.set_defaults(readers=values)
    declare(schedule_words, "remove", "help_schedule_remove", "schedule remove")

    declare(commands, "ingest", "help_ingest", "ingest")

    machine = declare(commands, "machine", "help_machine", "machine")
    machine_words = machine.add_subparsers(
        title=help_text("commands", output_language), dest="action", required=True,
        parser_class=_Reader, prog=machine.prog)
    machine_label = declare(machine_words, "label", "help_machine_label",
                            "machine label")
    machine_label.add_argument("text", metavar=_metavar("text", output_language))

    config = declare(commands, "config", "help_config", "config")
    config_words = config.add_subparsers(
        title=help_text("commands", output_language), dest="action", required=True,
        parser_class=_Reader, prog=config.prog)
    declare(config_words, "show", "help_config_show", "config show")
    values = {}
    add = declare(config_words, "add", "help_config_add", "config add")
    add.add_argument("entry", choices=_ENTRY_NAMES, metavar=_metavar("entry", output_language))
    add.add_argument("--zone", default=argparse.SUPPRESS,
                     metavar=_metavar("zone", output_language),
                     help=help_text("help_option_zone", output_language))
    add.add_argument("--from", default=argparse.SUPPRESS,
                     metavar=_Metavar(f"{_metavar('instant', output_language)}|"
                                      f"{_metavar('day', output_language)}",
                                      "<instant>|<day>"),
                     help=help_text("help_option_from_entry", output_language))
    values["from"] = ("--from", read_instant_or_day)
    add.add_argument("--hour", default=argparse.SUPPRESS,
                     metavar=_metavar("hour", output_language),
                     help=help_text("help_option_hour", output_language))
    values["hour"] = ("--hour", read_hour)
    add.add_argument("--id", default=argparse.SUPPRESS,
                     metavar=_metavar("identifier", output_language),
                     help=help_text("help_option_id", output_language))
    add.add_argument("--name", default=argparse.SUPPRESS,
                     metavar=_metavar("name", output_language),
                     help=help_text("help_option_name", output_language))
    add.add_argument("--project", default=argparse.SUPPRESS,
                     metavar=_metavar("project", output_language, "<project identifier>"),
                     help=help_text("help_option_project", output_language))
    add.add_argument("--work-item", default=argparse.SUPPRESS,
                     metavar=_metavar("work_item", output_language),
                     help=help_text("help_option_work_item", output_language))
    add.add_argument("--repository", default=argparse.SUPPRESS,
                     metavar=_metavar("repository", output_language),
                     help=help_text("help_option_repository", output_language))
    add.add_argument("--folder", default=argparse.SUPPRESS,
                     metavar=_metavar("folder", output_language),
                     help=help_text("help_option_folder", output_language))
    add.add_argument("--branch", default=argparse.SUPPRESS,
                     metavar=_metavar("branch", output_language),
                     help=help_text("help_option_branch", output_language))
    add.add_argument("--to", default=argparse.SUPPRESS, metavar=_metavar("day", output_language),
                     help=help_text("help_option_to_day", output_language))
    values["to"] = ("--to", read_day)
    add.add_argument("--tool", default=argparse.SUPPRESS,
                     metavar=_metavar("tool", output_language, "<pattern>"),
                     help=help_text("help_option_tool", output_language))
    add.add_argument("--category", default=argparse.SUPPRESS,
                     metavar=_metavar("category", output_language),
                     help=help_text("help_option_category", output_language))
    add.set_defaults(readers=values)

    values = {}
    sessions = declare(commands, "sessions", "help_sessions", "sessions")
    sessions.add_argument("day", metavar=_metavar("day", output_language))
    values["day"] = (_PLACEHOLDERS["day"], read_day)
    _report_parameters(sessions, output_language, values)
    sessions.set_defaults(readers=values)

    values = {}
    annotate = declare(commands, "annotate", "help_annotate", "annotate")
    annotate.add_argument("--tool", default=argparse.SUPPRESS,
                          metavar=_metavar("tool", output_language),
                          help=help_text("help_option_tool", output_language))
    about = annotate.add_mutually_exclusive_group(required=True)
    about.add_argument("--session", default=argparse.SUPPRESS,
                       metavar=_metavar("session", output_language),
                       help=help_text("help_option_session", output_language))
    about.add_argument("--from", default=argparse.SUPPRESS,
                       metavar=_metavar("instant", output_language),
                       help=help_text("help_option_from_instant", output_language))
    values["from"] = ("--from", read_instant)
    # `--to` ends the interval that `--from` begins (command-line.md › Commands), so only
    # `--session` and `--from` exclude each other; the action of the command checks that
    # an interval holds both ends and that a session takes no interval.
    annotate.add_argument("--to", default=argparse.SUPPRESS,
                          metavar=_metavar("instant", output_language),
                          help=help_text("help_option_to_instant", output_language))
    values["to"] = ("--to", read_instant)
    annotate.add_argument("--project", default=argparse.SUPPRESS,
                          metavar=_metavar("project", output_language),
                          help=help_text("help_option_project", output_language))
    annotate.add_argument("--work-item", default=argparse.SUPPRESS,
                          metavar=_metavar("work_item", output_language),
                          help=help_text("help_option_work_item", output_language))
    annotate.add_argument("--note", default=argparse.SUPPRESS,
                          metavar=_metavar("text", output_language),
                          help=help_text("help_option_note", output_language))
    annotate.set_defaults(readers=values)

    entry = declare(commands, "entry", "help_entry", "entry")
    entry_words = entry.add_subparsers(
        title=help_text("commands", output_language), dest="action", required=True,
        parser_class=_Reader, prog=entry.prog)
    values = {}
    add_entry = declare(entry_words, "add", "help_entry_add", "entry add")
    add_entry.add_argument("--from", required=True, default=argparse.SUPPRESS,
                           metavar=_metavar("instant", output_language),
                           help=help_text("help_option_from_instant", output_language))
    values["from"] = ("--from", read_instant)
    add_entry.add_argument("--to", required=True, default=argparse.SUPPRESS,
                           metavar=_metavar("instant", output_language),
                           help=help_text("help_option_to_instant", output_language))
    values["to"] = ("--to", read_instant)
    add_entry.add_argument("--mode", choices=("overlapping", "additional"), required=True,
                           default=argparse.SUPPRESS,
                           help=help_text("help_option_mode", output_language))
    add_entry.add_argument("--project", default=argparse.SUPPRESS,
                           metavar=_metavar("project", output_language),
                           help=help_text("help_option_project", output_language))
    add_entry.add_argument("--work-item", default=argparse.SUPPRESS,
                           metavar=_metavar("work_item", output_language),
                           help=help_text("help_option_work_item", output_language))
    add_entry.add_argument("--note", default=argparse.SUPPRESS,
                           metavar=_metavar("text", output_language),
                           help=help_text("help_option_note", output_language))
    add_entry.set_defaults(readers=values)

    values = {}
    timesheet = declare(commands, "timesheet", "help_timesheet", "timesheet")
    timesheet.add_argument(
        "subcommand", nargs="?", default=argparse.SUPPRESS,
        metavar=_metavar("subcommand", output_language),
        help=help_text("help_timesheet_action", output_language))
    timesheet.add_argument("day", nargs="?", default=argparse.SUPPRESS,
                           metavar=_metavar("day", output_language))
    values["day"] = (_PLACEHOLDERS["day"], read_day)
    timesheet.add_argument("--total", default=argparse.SUPPRESS,
                           metavar=_metavar("duration", output_language),
                           help=help_text("help_option_total", output_language))
    values["total"] = ("--total", read_duration)
    timesheet.add_argument("--set", action="append", default=argparse.SUPPRESS,
                           metavar=_metavar("value", output_language),
                           help=help_text("help_option_set", output_language))
    timesheet.add_argument("--note", default=argparse.SUPPRESS,
                           metavar=_metavar("text", output_language),
                           help=help_text("help_option_note", output_language))
    _report_parameters(timesheet, output_language, values)
    timesheet.set_defaults(readers=values)

    values = {}
    entries = declare(commands, "entries", "help_entries", "entries")
    entries.add_argument("day", metavar=_metavar("day", output_language))
    values["day"] = (_PLACEHOLDERS["day"], read_day)
    entries.set_defaults(readers=values)

    declare(commands, "retract", "help_retract", "retract").add_argument(
        "event_uid", metavar=_metavar("event", output_language))

    values = {}
    purge = declare(commands, "purge", "help_purge", "purge")
    removal = purge.add_mutually_exclusive_group(required=True)
    removal.add_argument("--key", action="append", default=argparse.SUPPRESS,
                         metavar=_metavar("key", output_language),
                         help=help_text("help_option_key", output_language))
    removal.add_argument("--writer-version-below", default=argparse.SUPPRESS,
                         metavar=_metavar("version", output_language),
                         help=help_text("help_option_writer_version_below", output_language))
    values["writer_version_below"] = ("--writer-version-below", read_version)
    purge.add_argument("--source", default=argparse.SUPPRESS,
                       metavar=_metavar("source", output_language),
                       help=help_text("help_option_source", output_language))
    purge.add_argument("--reason", choices=("content", "correction", "forget"), required=True,
                       default=argparse.SUPPRESS,
                       help=help_text("help_option_reason", output_language))
    purge.add_argument("--corrected-version", default=argparse.SUPPRESS,
                       metavar=_metavar("version", output_language),
                       help=help_text("help_option_corrected_version", output_language))
    values["corrected_version"] = ("--corrected-version", read_version)
    purge.add_argument("--yes", action="store_true", default=argparse.SUPPRESS,
                       help=help_text("help_option_yes", output_language))
    purge.set_defaults(readers=values)

    report = declare(commands, "report", "help_report", "report")
    report_words = report.add_subparsers(
        title=help_text("commands", output_language), dest="action", required=True,
        parser_class=_Reader, prog=report.prog)
    values = {}
    report_timesheet = declare(report_words, "timesheet", "help_report_timesheet",
                               "report timesheet")
    report_timesheet.add_argument("--from", required=True, default=argparse.SUPPRESS,
                                  metavar=_metavar("day", output_language),
                                  help=help_text("help_option_from_period", output_language))
    values["from"] = ("--from", read_day)
    report_timesheet.add_argument("--to", required=True, default=argparse.SUPPRESS,
                                  metavar=_metavar("day", output_language),
                                  help=help_text("help_option_to_day", output_language))
    values["to"] = ("--to", read_day)
    report_timesheet.add_argument("--freeze", action="store_true", default=argparse.SUPPRESS,
                                  help=help_text("help_option_freeze", output_language))
    report_timesheet.add_argument("--note", default=argparse.SUPPRESS,
                                  metavar=_metavar("text", output_language),
                                  help=help_text("help_option_note", output_language))
    _report_parameters(report_timesheet, output_language, values)
    report_timesheet.set_defaults(readers=values)

    values = {}
    report_day = declare(report_words, "day", "help_report_day", "report day")
    report_day.add_argument("day", metavar=_metavar("day", output_language))
    values["day"] = (_PLACEHOLDERS["day"], read_day)
    report_day.add_argument("--freeze", action="store_true", default=argparse.SUPPRESS,
                            help=help_text("help_option_freeze", output_language))
    report_day.add_argument("--note", default=argparse.SUPPRESS,
                            metavar=_metavar("text", output_language),
                            help=help_text("help_option_note", output_language))
    _report_parameters(report_day, output_language, values)
    report_day.set_defaults(readers=values)

    frozen = declare(commands, "frozen", "help_frozen", "frozen")
    frozen_words = frozen.add_subparsers(
        title=help_text("commands", output_language), dest="action", required=True,
        parser_class=_Reader, prog=frozen.prog)
    declare(frozen_words, "list", "help_frozen_list", "frozen list")
    declare(frozen_words, "show", "help_frozen_show", "frozen show").add_argument(
        "id", metavar=_metavar("id", output_language))
    values = {}
    removal = declare(frozen_words, "remove", "help_frozen_remove", "frozen remove")
    removal.add_argument("id", metavar=_metavar("id", output_language))
    values["id"] = (_PLACEHOLDERS["id"], read_frozen_id)
    removal.set_defaults(readers=values)

    index = declare(commands, "index", "help_index", "index")
    index_words = index.add_subparsers(
        title=help_text("commands", output_language), dest="action", required=True,
        parser_class=_Reader, prog=index.prog)
    declare(index_words, "rebuild", "help_index_rebuild", "index rebuild")

    declare(commands, "version", "help_version", "version")
    return reader
