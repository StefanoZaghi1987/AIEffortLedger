"""Tests of the package skeleton: version, console script, and run-time dependencies."""

import importlib.metadata
import tomllib
import unittest
from pathlib import Path


class TestPackage(unittest.TestCase):
    """The installed package metadata agrees with pyproject.toml."""

    def test_version_matches_pyproject(self):
        root = Path(__file__).resolve().parents[1]
        with open(root / "pyproject.toml", "rb") as stream:
            declared = tomllib.load(stream)["project"]["version"]
        self.assertEqual(importlib.metadata.version("ai-effort-ledger"), declared)

    def test_console_script_runs_main(self):
        names = {e.name for e in importlib.metadata.entry_points(group="console_scripts")}
        self.assertIn("ai-effort-ledger", names)

    def test_only_tzdata_at_run_time(self):
        self.assertEqual(importlib.metadata.requires("ai-effort-ledger"), ["tzdata"])
