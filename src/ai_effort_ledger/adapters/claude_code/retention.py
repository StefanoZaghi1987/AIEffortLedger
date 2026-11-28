"""The retention settings of the agent tools of the adapter: the `cleanupPeriodDays` in
effect for Claude Code and the desktop rule for Claude Desktop, read from the settings files
of Claude Code (claude-code-adapter.md › Retention,
docs/research/claude-code-settings-2026-11.md)."""

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from platform import system as running_system
from typing import NamedTuple

_CLEANUP = "cleanupPeriodDays"
_DESKTOP = "desktopSessionCleanupPeriodDays"
_DEFAULT_DAYS = 30


class Retention(NamedTuple):
    """The retention setting of one agent tool and its period in days; a period of None is no
    age limit (claude-code-adapter.md › Retention)."""

    setting: str
    days: int | None


def managed_settings_path(system: str) -> PurePath:
    """The managed settings file of the given operating system, as a pure path of that system
    (docs/research/claude-code-settings-2026-11.md › The settings files)."""
    if system == "Windows":
        return PureWindowsPath(r"C:\Program Files\ClaudeCode\managed-settings.json")
    if system == "Darwin":
        return PurePosixPath("/Library/Application Support/ClaudeCode/managed-settings.json")
    return PurePosixPath("/etc/claude-code/managed-settings.json")


def retention(
    tool: str,
    environ: Mapping[str, str],
    home: Path,
    system: str,
    native_logs: Mapping[str, Sequence[str]],
    project_folders: Iterable[str],
    managed_file: Path | None = None,
) -> Retention:
    """The retention setting of the agent tool: for `claude-code`, the shortest
    `cleanupPeriodDays` in effect among the managed and person settings files and the shared
    and local project settings files of the folders that the sessions of the machine name as
    `cwd`, with the default of 30 days when none sets it; for `claude-desktop`, the managed
    `cleanupPeriodDays` alone when the managed settings set it, otherwise no age limit while
    `desktopSessionCleanupPeriodDays` is 0 or absent and, when it is set, the longer of the
    desktop setting and the `claude-code` value of the same call.

    The environment and the home folder take no part, although the signature holds them: the
    person settings file is the one beside each recorded `projects/` folder of the machine
    configuration, because a scheduled ingestion does not get the environment variables of
    the person. The managed file is the given one, or the managed settings file of the given
    system when only the running system is named.
    """
    managed = _managed_values(managed_file, system)
    managed_cleanup = _whole(managed, _CLEANUP, 1)
    person = _person_files(native_logs)
    person_cleanup = _shortest_days(person, _CLEANUP, 1)
    person_desktop = _shortest_days(person, _DESKTOP, 0)
    folders = [
        _in_effect(
            managed_cleanup,
            _whole(_read(_project_file(text, "settings.local.json")), _CLEANUP, 1),
            _whole(_read(_project_file(text, "settings.json")), _CLEANUP, 1),
            person_cleanup)
        for text in project_folders
    ]
    # No session names a folder: the managed and person files alone give the value.
    if folders:
        days = min(folders)
    else:
        days = _in_effect(managed_cleanup, None, None, person_cleanup)
    if tool == "claude-desktop":
        if managed_cleanup is not None:
            return Retention(_CLEANUP, managed_cleanup)
        desktop = _whole(managed, _DESKTOP, 0)
        if desktop is None:
            desktop = person_desktop
        if not desktop:
            return Retention(_DESKTOP, None)
        return Retention(_DESKTOP, max(desktop, days))
    return Retention(_CLEANUP, days)


def _managed_values(managed_file: Path | None, system: str) -> dict[str, object] | None:
    """The values of the managed settings file: the given one, or the one of the given system
    when it is the running system and holds the file. No other managed source is read."""
    if managed_file is not None:
        return _read(managed_file)
    if system != running_system():
        return None
    return _read(Path(managed_settings_path(system)))


def _person_files(
    native_logs: Mapping[str, Sequence[str]],
) -> list[dict[str, object]]:
    """The values of the person settings files: one beside each recorded `projects/` folder
    of Claude Code."""
    files = []
    for text in native_logs.get("claude-code", ()):
        values = _read(Path(text).parent / "settings.json")
        if values is not None:
            files.append(values)
    return files


def _project_file(folder_text: str, name: str) -> Path:
    """One settings file of the `.claude` folder of a folder that a session names as `cwd`."""
    return Path(folder_text) / ".claude" / name


def _read(path: Path) -> dict[str, object] | None:
    """The values of one settings file: a JSON object, or None when the file is missing, not
    readable, or holds no object."""
    try:
        values = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return values if isinstance(values, dict) else None


def _whole(values: Mapping[str, object] | None, key: str, minimum: int) -> int | None:
    """The whole number that the key holds in the settings file, from the minimum up: a value
    below the minimum fails validation in Claude Code, so none is in effect."""
    value = values.get(key) if values is not None else None
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return None
    return value


def _shortest_days(
    files: Iterable[Mapping[str, object]], key: str, minimum: int
) -> int | None:
    """The shortest value that the key holds in the given settings files, since each file
    applies and the shortest period warns first."""
    held = [day for file_values in files
            if (day := _whole(file_values, key, minimum)) is not None]
    return min(held) if held else None


def _in_effect(
    managed: int | None, local: int | None, shared: int | None, person: int | None
) -> int:
    """The value that the precedence of Claude Code gives one folder: managed, local project,
    shared project, person, then the default."""
    for value in (managed, local, shared, person):
        if value is not None:
            return value
    return _DEFAULT_DAYS
