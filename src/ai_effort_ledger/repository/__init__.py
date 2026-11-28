"""The repository identity of a folder, read from the files of git, without running git."""

from .discovery import (
    INFERRED,
    OBSERVED,
    RepositoryIdentity,
    RootCommits,
    find_git,
    normalize_remote,
    resolve_folder,
)
from .objects import root_commit

__all__ = [
    "INFERRED",
    "OBSERVED",
    "RepositoryIdentity",
    "RootCommits",
    "find_git",
    "normalize_remote",
    "resolve_folder",
    "root_commit",
]
