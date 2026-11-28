"""The output of the commands: the outcome of an action, its warnings and configuration
errors as lines of the standard error, the JSON envelope of the standard output, and the
exit codes (command-line.md › Output, › Exit codes, › JSON documents)."""

import json
from typing import IO, NamedTuple

from ..language import message

COMPLETED = 0
"""The exit code of a command that completed (command-line.md › Exit codes)."""

STOPPED = 1
"""The exit code of a command that stopped with an error and wrote no partial line."""

WRONG_USE = 2
"""The exit code of a wrong use: no command, an argument missing, an argument not known,
arguments that do not go together, a value in a wrong format, or an event of a kind that
the command cannot act on."""

INCOMPLETE = 3
"""The exit code of a command that completed, but some figures are not complete."""

INCOMPLETE_CODES = frozenset(
    {"lost_events", "broken_line", "newer_schema_version", "held_back_events",
     "native_log_gone"})
"""The warning codes whose figures are not complete; one of them, or a configuration
error, gives the exit code 3 (command-line.md › Exit codes)."""


class Outcome(NamedTuple):
    """What one action gave: the document that the JSON documents of command-line.md hold,
    the warnings and the configuration errors as values with `code` and `values`, and
    whether the figures of the action are incomplete.

    The outcome of an action that a stop error stopped comes from `stopped`: its document
    holds the stop error under the key `error`, and `emit` writes the `error` envelope
    instead of the document. No document of a command holds an `error`
    key, so the key marks a stopped action. An action that writes the warning and
    configuration-error lines itself, because the person must read them before it asks a
    question, sets `lines_written`: `emit` then gives the streams none of them again,
    while the lists stay in the outcome for the envelope of `--json`.
    """

    document: dict
    warnings: list[dict]
    configuration_errors: list[dict]
    incomplete: bool
    lines_written: bool = False


def stopped(
    error: Exception,
    warnings: list[dict] | None = None,
    configuration_errors: list[dict] | None = None,
) -> Outcome:
    """The outcome of an action that the stop error stopped before it wrote anything:
    `emit` writes the `error` envelope with the code, the values, and the text of the error
    in the output language, instead of the document, and gives the exit code of the error."""
    return Outcome(
        {"error": error}, list(warnings or []), list(configuration_errors or []), False)


def json_document(outcome: Outcome, action_name: str, language: str) -> dict:
    """The JSON document of the command named `action_name` from the outcome of its action
    (command-line.md › JSON documents): the keys of the document of the outcome, then
    `command`, `warnings`, and `configuration_errors`, each warning and each configuration
    error with `code`, `values`, and `message`, its text in the language. This is the one
    composition of the document of a command: `emit` writes it with `--json`, and a report
    with `--freeze` keeps it as a frozen report (command-line.md › Frozen reports)."""
    return {
        **outcome.document,
        "command": action_name,
        "warnings": [_with_text(entry, language) for entry in outcome.warnings],
        "configuration_errors": [
            _with_text(entry, language) for entry in outcome.configuration_errors],
    }


def emit(
    outcome: Outcome,
    action_name: str,
    as_json: bool,
    language: str,
    stdout: IO[str],
    stderr: IO[str],
    configuration_errors_are_incomplete: bool = True,
    held_back_is_incomplete: bool = True,
) -> int:
    """Write the outcome of the action named `action_name` and give its exit code.

    The warnings and the configuration errors go to the standard error, one on each line,
    each warning starting `warning:` and each configuration error starting `error:`, with
    the text of its code in the language — unless the action wrote those lines itself and
    set `lines_written`, for the person to read them before it asked its question; then
    each line reaches the standard error exactly once. With `as_json`, the standard
    output holds the JSON document of the command, as `json_document` composes it; an
    action that stopped holds `error` with the same keys instead of the keys of its
    document, and the one line of the error goes to the standard error in both modes,
    because the standard error holds warnings and errors without regard to the mode.
    Without `as_json`, the action writes its own text, and `emit` writes only
    the lines of the standard error; an action that stopped writes one line that starts
    `error:`. The exit code is the exit code of the stop error, then 3 when the figures are
    incomplete — a configuration error, or a warning of `INCOMPLETE_CODES` — and 0
    otherwise; `configuration_errors_are_incomplete` false keeps the configuration errors
    from the exit code 3 (`config show` computes no figures), and `held_back_is_incomplete`
    false keeps the warning `held_back_events` from it (`timesheet confirm`, whose entries are
    the declaration of the person).
    """
    error = _stop_error(outcome)
    if not outcome.lines_written:
        write_lines(outcome.warnings, outcome.configuration_errors, language, stderr)
    if error is not None:
        envelope = {
            **json_document(outcome._replace(document={}), action_name, language),
            "error": _with_text(error, language),
        }
        if as_json:
            stdout.write(json.dumps(envelope, ensure_ascii=False) + "\n")
        stderr.write(f"error: {envelope['error']['message']}\n")
        return int(getattr(error, "exit_code", STOPPED))
    if as_json:
        document = json_document(outcome, action_name, language)
        stdout.write(json.dumps(document, ensure_ascii=False) + "\n")
    if _is_incomplete(outcome, configuration_errors_are_incomplete, held_back_is_incomplete):
        return INCOMPLETE
    return COMPLETED


def _stop_error(outcome: Outcome) -> Exception | None:
    """The stop error of an outcome that `stopped` gave, or None: it sits in the document
    under the key `error`."""
    error = outcome.document.get("error")
    return error if isinstance(error, Exception) else None


def write_lines(
    warnings: list[dict],
    configuration_errors: list[dict],
    language: str,
    stderr: IO[str],
) -> None:
    """One line for each warning and each configuration error, on the stream: each
    warning starting `warning:` and each configuration error starting `error:`, with the
    text of its code in the language (command-line.md › Output). `emit` writes the lines
    of an outcome with it, and an action that asks a question writes them itself before
    the question, so that the person answers on what they see."""
    for warning in warnings:
        stderr.write(f"warning: {_text(warning, language)}\n")
    for configuration_error in configuration_errors:
        stderr.write(f"error: {_text(configuration_error, language)}\n")


def _with_text(entry: dict | Exception, language: str) -> dict:
    """The code, the values, and the text of a warning, of a configuration error, or of a
    stop error, as the JSON documents hold each one."""
    code, values = _code_and_values(entry)
    return {"code": code, "values": values,
            "message": message(_text_key(entry), values, language)}


def _text(entry: dict | Exception, language: str) -> str:
    """The text of a warning, of a configuration error, or of a stop error."""
    _, values = _code_and_values(entry)
    return message(_text_key(entry), values, language)


def _text_key(entry: dict | Exception) -> str:
    """The key of the text that a warning, a configuration error, or a stop error is
    written with: its code, or the variant of its code (`language.TEXT_VARIANTS`) that a
    stop error carries as `text_key`."""
    code, _ = _code_and_values(entry)
    return getattr(entry, "text_key", code) if isinstance(entry, Exception) else code


def _code_and_values(entry: dict | Exception) -> tuple[str, dict]:
    """The code and the values of a warning, of a configuration error, or of a stop error:
    the keys of a value, the attributes of an error."""
    if isinstance(entry, Exception):
        return entry.code, entry.values
    return entry["code"], entry["values"]


def _is_incomplete(
    outcome: Outcome,
    configuration_errors_are_incomplete: bool,
    held_back_is_incomplete: bool,
) -> bool:
    """Whether the figures of the action are incomplete: the flag of the outcome, a
    configuration error, or a warning of `INCOMPLETE_CODES`."""
    if configuration_errors_are_incomplete and outcome.configuration_errors:
        return True
    for warning in outcome.warnings:
        if warning["code"] not in INCOMPLETE_CODES:
            continue
        if warning["code"] == "held_back_events" and not held_back_is_incomplete:
            continue
        return True
    return outcome.incomplete
