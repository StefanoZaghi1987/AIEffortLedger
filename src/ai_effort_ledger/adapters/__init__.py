"""The adapters of the ledger: one subpackage for each source format. Each adapter declares
the folders of native logs of its agent tools and their retention setting, finds the sessions
of a folder, and reads their files into complete events (ingestion.md › Adapters,
architecture.md › Modules)."""

from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePath
from typing import Protocol

from .claude_code import (
    ENTRYPOINTS,
    SOURCE,
    TOOL_CATEGORIES,
    ClaudeCodeAdapter,
    ReadContext,
    ReadResult,
    Retention,
    SessionFiles,
    SessionRecord,
    complete_events,
    deduplicate,
    event_identifiers,
    link_subagents,
    map_session,
    read_file,
)

__all__ = [
    "ADAPTERS",
    "Adapter",
    "ClaudeCodeAdapter",
    "complete_events",
    "ENTRYPOINTS",
    "ReadContext",
    "ReadResult",
    "Retention",
    "SOURCE",
    "SessionFiles",
    "SessionRecord",
    "TOOL_CATEGORIES",
    "deduplicate",
    "event_identifiers",
    "link_subagents",
    "map_session",
    "read_file",
]


class Adapter(Protocol):
    """What one adapter gives to the setup and to the ingestion: its source, its agent tools,
    the default folders of native logs, the retention setting of each agent tool, the sessions
    of a folder, and the reading of the files of sessions. The adapter leaves `ingested_at`,
    `writer_version`, `repo_hint`, and `repo_basis` to the ingestion (ingestion.md ›
    Adapters)."""

    source: str
    tools: tuple[str, ...]

    def default_folders(
        self, environ: Mapping[str, str], home: Path, system: str
    ) -> dict[str, list[PurePath]]:
        """The folders of native logs that each agent tool uses by default on the system."""
        ...

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
        ...

    def sessions(self, tool: str, folder: Path) -> list[SessionFiles]:
        """The sessions that a folder of native logs holds."""
        ...

    def read_sessions(
        self, sessions: Sequence[SessionFiles], context: ReadContext
    ) -> ReadResult:
        """The complete events of the sessions, what stays held back, and the warnings."""
        ...


ADAPTERS: tuple[Adapter, ...] = (ClaudeCodeAdapter(),)
"""Every adapter of the ledger, one for each source format."""
