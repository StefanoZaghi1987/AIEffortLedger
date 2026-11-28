"""The adapter of the native logs of Claude Code and of Claude Desktop: the folders that its
agent tools use, the sessions of a folder of native logs, the reading of their files, and the
retention that its settings files give (claude-code-adapter.md)."""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePath

from . import discovery, mapping, reading, retention
from .completeness import complete_events
from .discovery import SessionFiles
from .forks import assign_forks
from .mapping import SessionRecord, event_identifiers, map_session
from .reading import ReadContext, ReadResult, read_file
from .retention import Retention, managed_settings_path
from .subagents import deduplicate, link_subagents
from .tables import ENTRYPOINTS, SOURCE, TOOLS, TOOL_CATEGORIES, invocation_of

__all__ = [
    "ClaudeCodeAdapter",
    "ENTRYPOINTS",
    "SOURCE",
    "TOOL_CATEGORIES",
    "Retention",
    "SessionRecord",
    "assign_forks",
    "complete_events",
    "deduplicate",
    "event_identifiers",
    "invocation_of",
    "link_subagents",
    "managed_settings_path",
    "map_session",
    "read_file",
    "retention",
]


class ClaudeCodeAdapter:
    """The adapter of the native logs of Claude Code and of Claude Desktop: the folders of
    native logs that its agent tools use, the sessions of a folder, the reading of the files
    of a session, and the retention that its settings files give."""

    source = SOURCE
    tools = TOOLS

    def __init__(self, managed_file: Path | None = None) -> None:
        """The adapter, with the managed settings file that the retention reads, or the
        managed settings file of the system when none is given."""
        self.managed_file = managed_file

    def default_folders(
        self, environ: Mapping[str, str], home: Path, system: str
    ) -> dict[str, list[PurePath]]:
        """The folders of native logs that each agent tool uses by default on the system."""
        return discovery.default_folders(environ, home, system)

    def retention(
        self,
        tool: str,
        environ: Mapping[str, str],
        home: Path,
        system: str,
        native_logs: Mapping[str, Sequence[str]],
        project_folders: Iterable[str],
    ) -> Retention:
        """The retention setting of the agent tool, and the period that a folder follows."""
        return retention.retention(
            tool, environ, home, system, native_logs, project_folders, self.managed_file)

    def sessions(self, tool: str, folder: Path) -> list[SessionFiles]:
        """The sessions that a folder of native logs holds."""
        return discovery.sessions(tool, folder)

    def read_sessions(
        self, sessions: Sequence[SessionFiles], context: ReadContext
    ) -> ReadResult:
        """The events of the sessions, what stays held back, and the warnings."""
        return reading.read_sessions(sessions, context)
