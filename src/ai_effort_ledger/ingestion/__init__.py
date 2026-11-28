"""The ingestion of all adapters into the store: what one machine remembers of its sources,
the sessions that an ingestion reads, the warning for the events that the retention of an
agent tool can have deleted, and the ingestion itself, from the lock to the copies that a
purge blocks (architecture.md › Modules, › Data flow, ingestion.md › Frequency)."""

from .run import (
    DevelopmentVersion,
    IngestionResult,
    SourceResult,
    is_development,
    remove_blocked_copies,
    run_ingestion,
)
from .state import (
    SOURCES_FILE,
    STORES_FOLDER,
    SourcesState,
    file_stamp,
    held_back_sessions,
    lost_events,
    sessions_to_read,
    sources_path,
)

__all__ = [
    "SOURCES_FILE",
    "STORES_FOLDER",
    "DevelopmentVersion",
    "IngestionResult",
    "SourceResult",
    "SourcesState",
    "file_stamp",
    "held_back_sessions",
    "is_development",
    "lost_events",
    "remove_blocked_copies",
    "run_ingestion",
    "sessions_to_read",
    "sources_path",
]
