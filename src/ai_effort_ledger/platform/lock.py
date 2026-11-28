"""The lock of a store: an operating-system lock on its lock file, counted per process."""

import os
import time
from pathlib import Path
from platform import system as running_system
from types import TracebackType

_WINDOWS = running_system() == "Windows"

if _WINDOWS:
    import msvcrt
else:
    import fcntl

_RETRY_SECONDS = 0.5

# The nested takes of one process: the resolved path of each held lock and its take count.
_COUNTS: dict[str, int] = {}


class LockUnavailable(Exception):
    """The stop error of a lock that stays held past the limit.

    A stop error carries a code, values, and an exit code; the output language holds the text.
    """

    def __init__(self, path: Path) -> None:
        self.code = "lock_unavailable"
        self.values = {"path": str(path)}
        self.exit_code = 1
        super().__init__(str(path))


class StoreLock:
    """The lock of the file at the path, taken with a limit and counted per process.

    The operating system releases the lock when the process ends, so a lock never stays
    after a crash (architecture.md › Concurrency). Nested takes of the same resolved path
    in one process add 1 to a counter and ask the operating system nothing (ruled
    2026-11-20): the outermost take locks the file, the outermost exit releases it, so
    callers that nest can both take the lock.
    """

    def __init__(self, path: Path, limit_seconds: float = 600.0) -> None:
        self.path = path
        self.limit_seconds = limit_seconds
        self._key: str | None = None
        self._descriptor: int | None = None

    def __enter__(self) -> "StoreLock":
        key = str(self.path.resolve())
        if _COUNTS.get(key, 0):
            _COUNTS[key] += 1
        else:
            descriptor = _open_descriptor(self.path)
            _take(descriptor, self.limit_seconds, self.path)
            self._descriptor = descriptor
            _COUNTS[key] = 1
        self._key = key
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._key is None:
            return
        count = _COUNTS[self._key] - 1
        if count:
            _COUNTS[self._key] = count
        else:
            del _COUNTS[self._key]
            _release(self._descriptor)
        self._key = None
        self._descriptor = None


def _open_descriptor(path: Path) -> int:
    """Open the file of the path for reading and writing, creating it when it is missing."""
    return os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOINHERIT", 0))


def _take(descriptor: int, limit_seconds: float, path: Path) -> None:
    """Take the lock of the open file, trying again every half second until the limit.

    When the limit passes, the file closes again and the take stops with `LockUnavailable`.
    """
    deadline = time.monotonic() + limit_seconds
    while True:
        try:
            _try_take(descriptor)
            return
        except OSError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                os.close(descriptor)
                raise LockUnavailable(path) from None
            time.sleep(min(_RETRY_SECONDS, remaining))


def _try_take(descriptor: int) -> None:
    """Ask the operating system once for the exclusive lock; OSError is its refusal."""
    os.lseek(descriptor, 0, os.SEEK_SET)
    if _WINDOWS:
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
    else:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _release(descriptor: int | None) -> None:
    """Release the lock of the open file and close it."""
    if descriptor is not None:
        if _WINDOWS:
            os.lseek(descriptor, 0, os.SEEK_SET)
            msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        os.close(descriptor)
