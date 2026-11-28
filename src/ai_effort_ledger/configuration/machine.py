"""The machine configuration: the file `machine.toml` of the machine-local data folder
(architecture.md › Files of a machine). Setup writes it as a whole, because its keys and
the types of their values are fixed, so the reader checks each one."""

import re
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple

from ..platform import new_salt, salted_hash
from .values import _fault, _load
from .writes import basic_string

MACHINE_FILE = "machine.toml"

_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")


class MachineConfiguration(NamedTuple):
    """The settings of one machine: its identifier, the check of its installation, the
    location of the store, and the folders of the native logs of each agent tool."""

    machine: str
    installation: str | None
    salt: str | None
    store: str | None
    native_logs: dict[str, list[str]]


def read_machine_configuration(folder: Path) -> MachineConfiguration | None:
    """The machine configuration of the machine-local data folder, or None when the file
    is missing and the machine is not set up yet.

    A file that the ledger cannot read raises ConfigurationUnreadable; the ledger never
    uses part of a file (configuration.md › Format).
    """
    path = folder / MACHINE_FILE
    try:
        data, text = _load(path)
    except FileNotFoundError:
        return None
    machine = data.get("machine")
    if not isinstance(machine, str) or not machine:
        raise _fault(path, text, "machine")
    return MachineConfiguration(
        machine=machine,
        installation=_text(data, "installation", path, text),
        salt=_text(data, "salt", path, text),
        store=_text(data, "store", path, text),
        native_logs=_native_logs(data, path, text),
    )


def _text(data: dict[str, object], key: str, path: Path, text: str) -> str | None:
    """The text that the key holds, or None when the key is absent; an empty text or
    another value is a fault that names the line of the key."""
    value = data.get(key)
    if value is None or (isinstance(value, str) and value):
        return value
    raise _fault(path, text, key)


def _native_logs(data: dict[str, object], path: Path, text: str) -> dict[str, list[str]]:
    """The folders of the native logs of each agent tool, each value a list of texts."""
    table = data.get("native_logs", {})
    if not isinstance(table, dict):
        raise _fault(path, text, "native_logs")
    folders: dict[str, list[str]] = {}
    for tool, value in table.items():
        if not isinstance(value, list) or not all(isinstance(one, str) for one in value):
            raise _fault(path, text, str(tool))
        folders[str(tool)] = list(value)
    return folders


def write_machine_configuration(folder: Path, value: MachineConfiguration) -> None:
    """Write the machine configuration of the machine-local data folder as a whole, also
    when only one key changes, because its keys and the types of their values are fixed,
    so writing it needs no general TOML writer (configuration.md › Writes)."""
    (folder / MACHINE_FILE).write_text(_machine_text(value), encoding="utf-8")


def refresh_machine(
    value: MachineConfiguration | None,
    installation: str | None,
    new_id: Callable[[], str],
) -> tuple[MachineConfiguration, bool]:
    """The machine configuration that setup writes, and whether the machine identifier
    changed (command-line.md › Setup, ingestion.md › Store).

    A folder that holds no machine configuration yet gets a machine identifier from
    `new_id`. The machine identifier is made again, with a new salt, when the salted hash
    of the installation identifier differs from the one the configuration keeps. An
    installation identifier that the operating system gives no check, and the machine is
    kept as it is; a hash that the configuration does not keep yet is recorded with a new
    salt, and the machine is kept too, because no recorded hash has changed.
    """
    if value is None:
        value = MachineConfiguration(machine=new_id(), installation=None, salt=None,
                                     store=None, native_logs={})
        return _with_hash(value, installation), True
    if installation is None:
        return value, False
    if value.installation is None or value.salt is None:
        return _with_hash(value, installation), False
    if salted_hash(installation, value.salt) != value.installation:
        changed = value._replace(machine=new_id())
        return _with_hash(changed, installation), True
    return value, False


def _with_hash(value: MachineConfiguration, installation: str | None) -> MachineConfiguration:
    """The machine configuration with the salted hash of the installation identifier under
    a new salt, or without the two keys when the operating system gives no identifier."""
    if installation is None:
        return value._replace(installation=None, salt=None)
    salt = new_salt()
    return value._replace(installation=salted_hash(installation, salt), salt=salt)


def _machine_text(value: MachineConfiguration) -> str:
    """The text of the machine configuration: one line for each key that the value holds,
    then the table of the folders of the native logs of each agent tool."""
    lines = [f"machine = {basic_string(value.machine)}"]
    for key in ("installation", "salt", "store"):
        held = getattr(value, key)
        if held is not None:
            lines.append(f"{key} = {basic_string(held)}")
    lines.append("")
    lines.append("[native_logs]")
    for tool, folders in value.native_logs.items():
        held = ", ".join(basic_string(folder) for folder in folders)
        lines.append(f"{_bare_key(tool)} = [{held}]")
    return "\n".join(lines) + "\n"


def _bare_key(name: str) -> str:
    """The name of a tool as a TOML key: itself when a bare key can hold it, else a basic
    string."""
    return name if _BARE_KEY.fullmatch(name) else basic_string(name)
