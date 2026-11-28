"""The time zone of the operating system and the conversion of the Windows time-zone names.

Linux and macOS give an IANA time zone: the `TZ` variable of the environment wins over the
target of the localtime link when `tzdata` holds the zone that it names; a POSIX TZ string
or a path names no zone and gives None, as an unknown Windows name does. Windows gives a
Windows time-zone name, which the injected `read_registry` reads and the table of
`windows_zones` converts; an unknown name gives None, never a guess (configuration.md ›
Writes).
"""

import os
from collections.abc import Callable, Mapping
from pathlib import Path
from zoneinfo import ZoneInfo

from .windows_zones import WINDOWS_ZONES

TIME_ZONE_KEY = r"SYSTEM\CurrentControlSet\Control\TimeZoneInformation"
TIME_ZONE_VALUE = "TimeZoneKeyName"
ZONEINFO_FOLDER = "zoneinfo"


def windows_zone_to_iana(name: str) -> str | None:
    """The IANA time zone of the Windows name in the table, or None when it holds none."""
    return WINDOWS_ZONES.get(name)


def zone_of_localtime_target(target: str) -> str | None:
    """The IANA time zone in the target of a localtime link, or None when it holds none.

    The zone is the path below the `zoneinfo` folder of the target, as in
    `/usr/share/zoneinfo/Europe/Rome`; a target without that folder gives None, because the
    ledger never guesses a time zone.
    """
    parts = target.replace("\\", "/").split("/")
    if ZONEINFO_FOLDER not in parts:
        return None
    zone = "/".join(parts[parts.index(ZONEINFO_FOLDER) + 1:])
    return zone or None


def _holds_zone(name: str) -> bool:
    """Whether `tzdata` holds the time zone of the name (configuration.md › Writes)."""
    try:
        ZoneInfo(name)
    except (KeyError, ValueError):
        return False
    return True


def system_time_zone(
    system: str,
    environ: Mapping[str, str],
    localtime: Path,
    read_registry: Callable[[], str | None],
) -> str | None:
    """The IANA time zone of the operating system, or None when the system gives none.

    On Windows the name of the registry converts with the table. On Linux and macOS the `TZ`
    variable of the environment, with or without the leading colon, wins over the target of
    the localtime link when `tzdata` holds the zone it names; a POSIX TZ string or a path
    names no zone and gives None, and the link is not consulted beside it, so that setup
    writes no `[[time_zone]]` entry, as for an unknown Windows name (configuration.md ›
    Writes). A link whose target names no `zoneinfo` folder gives None.
    """
    if system == "Windows":
        name = read_registry()
        return windows_zone_to_iana(name) if name is not None else None
    zone = environ.get("TZ", "").removeprefix(":")
    if zone:
        return zone if _holds_zone(zone) else None
    try:
        target = os.readlink(localtime)
    except OSError:
        return None
    return zone_of_localtime_target(target)


def registry_time_zone_name() -> str | None:
    """The TimeZoneKeyName value of the registry of Windows, or None when it gives none."""
    try:
        import winreg
    except ImportError:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, TIME_ZONE_KEY) as key:
            value, _ = winreg.QueryValueEx(key, TIME_ZONE_VALUE)
    except OSError:
        return None
    return value if isinstance(value, str) and value else None
