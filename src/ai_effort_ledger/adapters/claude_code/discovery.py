"""The folders of native logs of the adapter and the sessions of one folder: the folders that
its agent tools use by default on each operating system, and the files of each session that a
folder holds (claude-code-adapter.md › Native logs)."""

from collections.abc import Mapping
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from typing import NamedTuple

from .tables import DESKTOP


class SessionFiles(NamedTuple):
    """The files of one session: its agent tool and identifier, the folder of native logs that
    holds them, the file of the main agent when it exists, and the file of each subagent by
    the identifier in its name."""

    tool: str
    session_id: str
    folder: Path
    main: Path | None
    subagents: dict[str, Path]


def default_folders(
    environ: Mapping[str, str], home: Path, system: str
) -> dict[str, list[PurePath]]:
    """The folders of native logs that each agent tool of the adapter uses by default on the
    given system, as pure paths of that system, built also when they do not exist.

    Claude Code reads `projects/` of its configuration folder: the folder that the environment
    variable `CLAUDE_CONFIG_DIR` gives, otherwise `.claude` in the home folder of the person.
    Claude Desktop records its sessions below `Claude/local-agent-mode-sessions` of the
    application data folder of the operating system, and has no folder on Linux. The home
    folder enters the POSIX paths as its POSIX string, so the pure paths are built from POSIX
    parts alone, whatever the flavour of the running system.
    """
    if system == "Windows":
        config = environ.get("CLAUDE_CONFIG_DIR")
        base = PureWindowsPath(config) if config else PureWindowsPath(home, ".claude")
        app_data = environ.get("APPDATA") or str(PureWindowsPath(home, "AppData", "Roaming"))
        return {
            "claude-code": [base / "projects"],
            "claude-desktop": [PureWindowsPath(
                app_data, "Claude", "local-agent-mode-sessions")],
        }
    config = environ.get("CLAUDE_CONFIG_DIR")
    code = (PurePosixPath(config, "projects") if config
            else PurePosixPath(home.as_posix(), ".claude", "projects"))
    folders: dict[str, list[PurePath]] = {"claude-code": [code]}
    if system == "Darwin":
        folders["claude-desktop"] = [PurePosixPath(
            home.as_posix(), "Library", "Application Support", "Claude",
            "local-agent-mode-sessions")]
    else:
        folders["claude-desktop"] = []
    return folders


def sessions(tool: str, folder: Path) -> list[SessionFiles]:
    """The sessions that a folder of native logs holds, in the order of their identifiers: a
    `<session>.jsonl` file is the file of the main agent of a session, and
    `<session>/subagents/agent-<agent>.jsonl` the file of one subagent.

    For Claude Desktop the given folder is the recorded folder, and every `.claude/projects`
    folder below it is searched. A folder that is not there holds no session.
    """
    if tool != DESKTOP:
        return _sessions_in(tool, folder)
    if not folder.is_dir():
        return []
    found: list[SessionFiles] = []
    for projects in sorted(folder.glob("**/.claude/projects")):
        if projects.is_dir():
            found.extend(_sessions_in(tool, projects))
    return sorted(found, key=lambda session: (session.session_id, str(session.folder)))


def _sessions_in(tool: str, folder: Path) -> list[SessionFiles]:
    """The sessions of one folder of native logs, in the order of their identifiers. The
    agent tool can delete a folder while the walk holds it: the folder of native logs
    that is gone after the walk's own check holds no session, a session whose subagent
    folder is gone holds its main file and no subagent, the walk raises nothing, and
    what the rest of the folder holds is still found."""
    try:
        if not folder.is_dir():
            return []
        mains = {path.stem: path for path in folder.glob("*.jsonl")}
        entries = sorted(folder.iterdir())
    except OSError:
        return []
    agents: dict[str, dict[str, Path]] = {}
    for entry in entries:
        if entry.is_dir():
            try:
                files = _subagents(entry)
            except OSError:
                continue
            if files:
                agents[entry.name] = files
    return [
        SessionFiles(tool, name, folder, mains.get(name), agents.get(name, {}))
        for name in sorted(set(mains) | set(agents))
    ]


def _subagents(session_folder: Path) -> dict[str, Path]:
    """The file of each subagent of a session, by the identifier in its file name."""
    files = session_folder / "subagents"
    if not files.is_dir():
        return {}
    return {path.stem[len("agent-"):]: path for path in sorted(files.glob("agent-*.jsonl"))}
