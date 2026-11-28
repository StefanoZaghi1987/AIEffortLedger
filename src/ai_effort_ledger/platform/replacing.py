"""The replace of one file by another in one operation of the file system, with the wait
of the lock while another process holds the replaced file open (architecture.md ›
Concurrency)."""

import os
import time
from pathlib import Path

from .lock import LockUnavailable

_RETRY_SECONDS = 0.5


def replace_file(new_path: Path, path: Path, limit_seconds: float = 600.0) -> None:
    """Put the new file in the place of the other, trying again every half second while the
    operating system refuses the replace, as it does while another process holds the other
    file open.

    When the limit passes, the new file is removed again and the replace stops with
    `LockUnavailable`, leaving the other file as it was.
    """
    deadline = time.monotonic() + limit_seconds
    while True:
        try:
            os.replace(new_path, path)
            return
        except PermissionError:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                try:
                    new_path.unlink()
                except OSError:
                    pass
                raise LockUnavailable(path) from None
            time.sleep(min(_RETRY_SECONDS, remaining))
