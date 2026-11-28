"""The files of the store beside the segments: the store metadata of a machine and its frozen
reports.

The store metadata, `machines/<machine>.toml`, holds one key, `label`, which the machine alone
writes (`ingestion.md` › Store). A frozen report is kept as given in `frozen/<machine>/<id>.json`,
and only the machine that wrote it removes it (`architecture.md` › Report record). The label is
written as a TOML basic string with the escapes of `configuration.md` › Writes, because `store`
depends only on `events` and `platform` (`architecture.md` › Modules).
"""

import json
import math
import tomllib
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ..events import parse_instant


class FrozenOtherMachine(Exception):
    """The stop error of a frozen report that another machine wrote.

    A stop error carries a code, values, and an exit code; the output language holds the text.
    The values hold `machine_label` too when the store holds a machine label for the machine
    that wrote the file, and the error is then written with `text_key`, the variant of the
    text of its code that names the label instead of the identifier (command-line.md › Exit
    codes).
    """

    def __init__(self, frozen_id: str, machine: str, machine_label: str | None = None) -> None:
        self.code = "frozen_other_machine"
        self.values = {"id": frozen_id, "machine": machine}
        self.text_key = self.code
        if machine_label is not None:
            self.values["machine_label"] = machine_label
            self.text_key = "frozen_other_machine_with_label"
        self.exit_code = 1
        super().__init__(f"{frozen_id} was written by the machine {machine}")


class TargetNotFound(Exception):
    """The stop error of a target that the store does not hold.

    A stop error carries a code, values, and an exit code; the output language holds the text.
    """

    def __init__(self, target: str) -> None:
        self.code = "target_not_found"
        self.values = {"target": target}
        self.exit_code = 1
        super().__init__(target)


class FrozenReportUnreadable(Exception):
    """The stop error of a file of a frozen report that the ledger cannot read as one.

    A stop error carries a code, values, and an exit code; the output language holds the text.
    The values hold `path`, the file as the store names it.
    """

    def __init__(self, path: str) -> None:
        self.code = "frozen_report_unreadable"
        self.values = {"path": path}
        self.exit_code = 1
        super().__init__(path)


def _basic_string(value: str) -> str:
    """The value as one TOML basic string, with double quotes, backslashes, and control
    characters escaped (`configuration.md` › Writes)."""
    named = {"\b": r"\b", "\t": r"\t", "\n": r"\n", "\f": r"\f", "\r": r"\r"}
    escaped = ['"']
    for character in value:
        if character == '"':
            escaped.append('\\"')
        elif character == "\\":
            escaped.append("\\\\")
        elif character in named:
            escaped.append(named[character])
        elif character < " " or character == "\x7f":
            escaped.append(f"\\u{ord(character):04x}")
        else:
            escaped.append(character)
    escaped.append('"')
    return "".join(escaped)


def frozen_name(machine: str, frozen_id: str) -> str:
    """The path text of the file of one frozen report, as the store names it in every
    message: `frozen/<machine>/<id>.json`, below the store folder."""
    return f"frozen/{machine}/{frozen_id}.json"


def _metadata_name(machine: str) -> str:
    """The path text of the store metadata of one machine, as the store names it in every
    message: `machines/<machine>.toml`, below the store folder."""
    return f"machines/{machine}.toml"


def machine_labels(
    store_folder: Path, machines: Iterable[str],
) -> tuple[dict[str, str], list[dict]]:
    """The machine labels of the machines that one command names, each store metadata read
    once however often the command names its machine: the machine label of each machine
    whose store metadata holds one, and the warnings (command-line.md › JSON documents).
    No store metadata, store metadata without `label`, and a label that is blank after
    `strip()` give no label and no warning. Store metadata that the operating system
    refuses, whose text the parser of TOML cannot read — also for its depth —, or whose
    `label` is not text gives no label and the warning `machine_label_unreadable`, which
    names the file as the store holds it: the label is only shown, and a file-sync service
    can hand over the file of another machine while that machine writes it, so the command
    goes on with the identifier."""
    labels: dict[str, str] = {}
    warnings: list[dict] = []
    for machine in dict.fromkeys(machines):
        name = _metadata_name(machine)
        try:
            with open(store_folder / name, "rb") as metadata_file:
                label = tomllib.load(metadata_file).get("label", "")
        except FileNotFoundError:
            label = ""
        except (OSError, ValueError, RecursionError):
            label = None  # no TOML value is None, so None stands for the file not read
        if not isinstance(label, str):
            warnings.append({"code": "machine_label_unreadable", "values": {"path": name}})
        elif label.strip():
            labels[machine] = label
    return labels, warnings


def write_label(store_folder: Path, machine: str, label: str) -> None:
    """Write the machine label of the machine in its store metadata, as the whole file."""
    path = store_folder / _metadata_name(machine)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"label = {_basic_string(label)}\n", encoding="utf-8")


def write_frozen(
    store_folder: Path,
    machine: str,
    frozen_id: str,
    document: dict[str, Any],
) -> None:
    """Keep the document as a frozen report of the machine, with the identifier as its name."""
    path = store_folder / frozen_name(machine, frozen_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(document, indent=2, ensure_ascii=False)
    path.write_text(text + "\n", encoding="utf-8")


def _frozen_paths(store_folder: Path) -> list[Path]:
    """The files of the frozen reports of the store, in the order of their paths as text."""
    frozen = store_folder / "frozen"
    if not frozen.is_dir():
        return []
    return sorted(frozen.glob("*/*.json"),
                  key=lambda path: path.relative_to(store_folder).as_posix())


def frozen_names(store_folder: Path) -> list[tuple[str, str]]:
    """The machine and the identifier of each frozen report of the store, from the names of
    its files alone, in the order of their paths as text; no file is read, so a file that the
    ledger cannot read as a frozen report is named like any other."""
    return [(path.parent.name, path.stem) for path in _frozen_paths(store_folder)]


def list_frozen(store_folder: Path) -> list[tuple[str, str, dict[str, Any]]]:
    """The frozen reports of the store as machine, identifier, and envelope, in the order of
    their paths as text, the identifier being the name of the file. This is the reader of
    the file: it reads the envelope, the identifier, and the two keys of the document that
    every consumer reads, and a file that it cannot read as the envelope of a frozen report
    stops with `FrozenReportUnreadable` (command-line.md › Frozen reports). The commands
    read the frozen reports through `reports.read_frozen`, which reads the documents
    too."""
    return [(path.parent.name, path.stem, _read_frozen(path, store_folder))
            for path in _frozen_paths(store_folder)]


def _read_frozen(path: Path, store_folder: Path) -> dict[str, Any]:
    """The envelope of one file of a frozen report, as the store keeps it: a JSON object
    whose numbers are all finite, holding a `document` object whose `command` is text and
    whose `record` is an object, an instant as `frozen_at`, and, when it holds `note`, a
    text: the `--note` of the freeze. A `frozen_id` that the document holds is the
    identifier of the file name, the one that `frozen show` and `frozen remove` take; a
    document that holds none is no fault. These are the checks of the envelope and of the
    identifier, with the two keys of the document that every consumer reads whatever its
    command; the other keys of the document are read by `reports`, which knows the
    documents of the report commands. A file that the operating system refuses, whose text
    the parser of JSON cannot read — also for its depth —, or that holds no such envelope
    stops with `FrozenReportUnreadable`, which names the file as the store holds it."""
    name = path.relative_to(store_folder).as_posix()
    try:
        envelope: Any = json.loads(path.read_text(encoding="utf-8"),
                                   parse_float=_finite, parse_constant=_finite)
    except (OSError, ValueError, RecursionError):
        raise FrozenReportUnreadable(name) from None
    document = envelope.get("document") if isinstance(envelope, dict) else None
    if (not isinstance(document, dict)
            or not isinstance(document.get("command"), str)
            or not isinstance(document.get("record"), dict)
            or document.get("frozen_id", path.stem) != path.stem
            or not isinstance(envelope.get("note", ""), str)
            or not _is_instant(envelope.get("frozen_at"))):
        raise FrozenReportUnreadable(name)
    return envelope


def _finite(text: str) -> float:
    """The number of a JSON text that the parser hands over: one with a fraction or an
    exponent, or `NaN`, `Infinity`, or `-Infinity`. A number that is not finite raises
    `ValueError`, because the ledger writes a document back only as strict JSON."""
    number = float(text)
    if not math.isfinite(number):
        raise ValueError(f"{text} is no finite number")
    return number


def _is_instant(value: Any) -> bool:
    """Whether a value is the text of an instant, as the schema stores one."""
    if not isinstance(value, str):
        return False
    try:
        parse_instant(value)
    except ValueError:
        return False
    return True


def remove_frozen(store_folder: Path, machine: str, frozen_id: str, own_machine: str) -> None:
    """Remove the frozen report of the machine; another machine stops, because each file of the
    store has one writer (`architecture.md` › Report record), with the machine label of the
    machine that wrote the file when the store holds one. Store metadata that the ledger
    cannot read gives the identifier and no warning, because a stop error carries no warnings
    to the output."""
    if machine != own_machine:
        labels, _ = machine_labels(store_folder, [machine])
        raise FrozenOtherMachine(frozen_id, machine, labels.get(machine))
    path = store_folder / frozen_name(machine, frozen_id)
    if not path.is_file():
        raise TargetNotFound(frozen_name(machine, frozen_id))
    path.unlink()
