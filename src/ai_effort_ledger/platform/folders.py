"""The folders of the operating system: the machine-local data folder and the store folder."""

from collections.abc import Mapping
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath

LEDGER_FOLDER = "ai-effort-ledger"


def machine_folder(system: str, environ: Mapping[str, str], home: Path) -> PurePath:
    """The machine-local data folder of the given system, as a pure path, never resolved."""
    return _base_folder(system, environ, home, "machine", "XDG_STATE_HOME", ".local", "state")


def default_store_folder(system: str, environ: Mapping[str, str], home: Path) -> PurePath:
    """The default store folder of the given system, as a pure path, never resolved."""
    return _base_folder(system, environ, home, "store", "XDG_DATA_HOME", ".local", "share")


def _base_folder(
    system: str,
    environ: Mapping[str, str],
    home: Path,
    leaf: str,
    variable: str,
    *default_parts: str,
) -> PurePath:
    """The folder of the ledger under the local data folder of the system, as a pure path.

    The pure path is of the given system: PureWindowsPath on Windows, PurePosixPath otherwise.
    On Linux the variable names the XDG folder that holds the leaf, and the parts after the
    home folder are its value when the variable is not set. When LOCALAPPDATA is not set on
    Windows, the folder goes under AppData\\Local of the home folder. The home folder enters
    the POSIX paths as its POSIX string, so the pure path is built from POSIX parts alone,
    whatever the flavour of the running system.
    """
    if system == "Windows":
        local = environ.get("LOCALAPPDATA") or str(PureWindowsPath(home, "AppData", "Local"))
        return PureWindowsPath(local, LEDGER_FOLDER, leaf)
    if system == "Darwin":
        return PurePosixPath(
            home.as_posix(), "Library", "Application Support", LEDGER_FOLDER, leaf)
    base = environ.get(variable) or str(PurePosixPath(home.as_posix(), *default_parts))
    return PurePosixPath(base, LEDGER_FOLDER, leaf)
