"""The writes of the person configuration: the entry that the command line appends at the
end of the file, and the file that setup creates (configuration.md › Writes)."""

from collections.abc import Callable, Mapping
from pathlib import Path
from zoneinfo import ZoneInfo

from ..platform import StoreLock
from .forms import is_day, is_hour, is_offset_instant
from .person import PERSON_FILE, read_person_configuration

ENTRY_KEYS: dict[str, tuple[str, ...]] = {
    "time_zone": ("zone", "from"),
    "day_start": ("hour", "from"),
    "project": ("id", "name"),
    "work_item": ("project", "id", "name"),
    "identity_rule": ("project", "repository", "folder", "branch", "from", "to"),
    "category_rule": ("tool", "category"),
}
"""The keys of each entry of the person configuration, in the order of the file."""

TOOL_CATEGORIES: frozenset[str] = frozenset(
    {"edit", "execute", "read", "search", "web", "delegate", "decide", "other"})
"""The tool categories of the event schema, copied from `events.FIXED_VALUES`, because
`configuration` does not depend on `events`; the test that imports both modules keeps the
copy equal to the original."""

_START_INSTANT = "1970-01-01T00:00:00Z"
_START_DAY = "1970-01-01"

_ESCAPES = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\t": "\\t", "\n": "\\n",
            "\f": "\\f", "\r": "\\r"}


class WrongValue(Exception):
    """The stop error of a value of an entry that no format of the command line holds.

    A stop error carries a code, values, and an exit code; the output language holds the
    text.
    """

    def __init__(self, key: str, value: str) -> None:
        self.code = "wrong_value"
        self.values = {"key": key, "value": value}
        self.exit_code = 2
        super().__init__(f"{key}: {value}")


def basic_string(value: str) -> str:
    """The value as one TOML basic string: between double quotes, with double quotes,
    backslashes, and control characters escaped, so a value can never add, change, or
    remove an entry (configuration.md › Writes)."""
    out = ['"']
    for character in value:
        if character in _ESCAPES:
            out.append(_ESCAPES[character])
        elif ord(character) < 0x20 or ord(character) == 0x7F:
            out.append(f"\\u{ord(character):04x}")
        else:
            out.append(character)
    out.append('"')
    return "".join(out)


def append_entry(
    store_folder: Path,
    lock_path: Path,
    entry: str,
    values: Mapping[str, str],
) -> dict[str, str]:
    """Append one entry at the end of the person configuration of the store folder, and
    return the values of the entry as written (configuration.md › Writes).

    Every value is checked before the file changes; a value of no format stops with
    WrongValue. The lock of the store is held while the file is appended and read again;
    when the read of the whole file fails, the earlier bytes go back and the error of the
    read stops the command. The command line normalizes the values it holds before it
    calls this, so a value arrives in its final form.
    """
    keys = ENTRY_KEYS.get(entry)
    if keys is None:
        raise WrongValue("entry", entry)
    for key in values:
        if key not in keys:
            raise WrongValue(key, values[key])
        _check(entry, key, values[key])
    text = _entry_text(entry, values)
    path = store_folder / PERSON_FILE
    with StoreLock(lock_path):
        earlier = path.read_bytes()
        with path.open("ab") as appended:
            if earlier and not earlier.endswith(b"\n"):
                appended.write(b"\n")
            appended.write(text.encode("utf-8"))
        try:
            read_person_configuration(store_folder)
        except Exception:
            path.write_bytes(earlier)
            raise
    return {key: values[key] for key in keys if key in values}


def create_person_configuration(store_folder: Path, zone: str | None) -> list[dict[str, str]]:
    """Create the person configuration of a store folder that holds none, and return its
    entries for setup to show them (configuration.md › Writes).

    The file holds one `[[time_zone]]` entry with the zone of the operating system, when
    the zone is given, and one `[[day_start]]` entry with 00:00, both valid from the start
    of 1970, so that native logs older than the first run have local days. A zone that
    `tzdata` does not hold raises WrongValue. A store folder that holds a person
    configuration already raises FileExistsError.
    """
    path = store_folder / PERSON_FILE
    if path.exists():
        raise FileExistsError(str(path))
    entries: list[dict[str, str]] = []
    blocks = []
    if zone is not None:
        if not _is_zone(zone):
            raise WrongValue("zone", zone)
        entries.append({"zone": zone, "from": _START_INSTANT})
        blocks.append(f"[[time_zone]]\nzone = {basic_string(zone)}\nfrom = {_START_INSTANT}\n")
    entries.append({"hour": "00:00", "from": _START_DAY})
    blocks.append(f"[[day_start]]\nhour = 00:00:00\nfrom = {_START_DAY}\n")
    path.write_text("\n".join(blocks), encoding="utf-8")
    return entries


def _check(entry: str, key: str, value: str) -> None:
    """Check one value of an entry against the format of its key (configuration.md ›
    Writes); a value of no format raises WrongValue with the key and the value."""
    if not _CHECKS[entry][key](value):
        raise WrongValue(key, value)


def _is_zone(value: str) -> bool:
    """Whether `tzdata` holds the time zone."""
    try:
        ZoneInfo(value)
    except (KeyError, ValueError):
        return False
    return True


def _is_category(value: str) -> bool:
    """Whether the value is a tool category of the event schema."""
    return value in TOOL_CATEGORIES


def _is_text(value: str) -> bool:
    """Whether the value is a non-empty text, which the reader of an entry accepts."""
    return bool(value)


_CHECKS: dict[str, dict[str, Callable[[str], bool]]] = {
    "time_zone": {"zone": _is_zone, "from": is_offset_instant},
    "day_start": {"hour": is_hour, "from": is_day},
    "project": {"id": _is_text, "name": _is_text},
    "work_item": {"project": _is_text, "id": _is_text, "name": _is_text},
    "identity_rule": {
        "project": _is_text,
        "repository": _is_text,
        "folder": _is_text,
        "branch": _is_text,
        "from": is_day,
        "to": is_day,
    },
    "category_rule": {"tool": _is_text, "category": _is_category},
}
"""The check of each key of each entry; a key of the values that no entry holds checks
nothing and raises WrongValue."""


def _entry_text(entry: str, values: Mapping[str, str]) -> str:
    """The text of the entry: its `[[entry]]` header and, one per line, each key of the
    entry that the values hold, as a basic string (configuration.md › Writes)."""
    lines = [f"[[{entry}]]"]
    lines.extend(
        f"{key} = {basic_string(values[key])}" for key in ENTRY_KEYS[entry] if key in values)
    return "\n".join(lines) + "\n"
