"""Shared support for the tests: the environment, temporary folders, and instants."""

import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

os.environ["AI_EFFORT_LEDGER_DEVELOPMENT"] = "1"


def utc(text: str) -> datetime:
    """Read an instant as UTC: `YYYY-MM-DDTHH:MM`, with optional seconds and milliseconds."""
    return datetime.fromisoformat(text).replace(tzinfo=timezone.utc)


class TemporaryFolder:
    """A temporary folder that is removed at the end; it yields its path."""

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix="ai_effort_ledger_"))
        return self.path

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
