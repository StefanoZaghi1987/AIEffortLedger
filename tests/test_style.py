"""Tests of the static check: the rules of gate G1, applied to files of a temporary tree."""

import contextlib
import io
import unittest
from pathlib import Path

import support
import style

GLOSSARY = """\
# Ledger words

**Decision request**:
A point at which a test decides.
_Avoid_: job, timeout
"""


def architecture_document(rows: str, order: str) -> str:
    """An invented architecture.md: a table of Modules and a line of build order below it."""
    return ("# Architecture\n\n## Modules\n\n| Module | Responsibility | Depends on |\n"
            "|---|---|---|\n" + rows + "\nBuild order: " + order + ".\n")


def package_file(root: Path, relative: str, source: str) -> Path:
    """Write one invented file under src/ai_effort_ledger/ and return its path."""
    path = root / "src" / "ai_effort_ledger" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return path


def write_tree(root: Path, document: str, files: dict[str, str]) -> None:
    """Write an invented tree: GLOSSARY.md, docs/spec/architecture.md, and package files."""
    (root / "GLOSSARY.md").write_text(GLOSSARY, encoding="utf-8")
    spec = root / "docs" / "spec"
    spec.mkdir(parents=True, exist_ok=True)
    (spec / "architecture.md").write_text(document, encoding="utf-8")
    for relative, source in files.items():
        package_file(root, relative, source)


class TestStyle(unittest.TestCase):
    """The static check applies the rules of gate G1 to invented glossaries and files."""

    def findings(self, glossary: str, source: str) -> list[str]:
        """Check one invented file against the named words of an invented glossary."""
        with support.TemporaryFolder() as folder:
            path = folder / "source.py"
            path.write_text(source, encoding="utf-8")
            words, sequences = style.named_words(glossary)
            return style.check_file(path, words, sequences)

    def test_split_identifier(self) -> None:
        self.assertEqual(
            style.split_identifier("parseHTTPRecord_line"),
            ["parse", "http", "record", "line"])

    def test_named_word_in_a_def_name(self) -> None:
        findings = self.findings(GLOSSARY, "def run_job():\n    return 1\n")
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].endswith(
            "'run_job' holds 'job', a word the glossary marks Avoid"))

    def test_word_of_a_glossary_term_is_allowed(self) -> None:
        self.assertEqual(self.findings(GLOSSARY, "decision_request = 1\n"), [])

    def test_sequence_is_named_only_as_sequence(self) -> None:
        glossary = "# Words\n\n_Avoid_: effective hours, hours\n"
        source = "effective_hours = 1\nhours = 2\neffective = 3\n"
        findings = self.findings(glossary, source)
        self.assertEqual(len(findings), 2)
        self.assertTrue(findings[0].endswith(
            "'effective_hours' holds 'effective hours', a sequence the glossary marks Avoid"))
        self.assertTrue(findings[1].endswith(
            "'hours' holds 'hours', a word the glossary marks Avoid"))

    def test_parenthesis_is_not_part_of_the_entry(self) -> None:
        glossary = "# Words\n\n_Avoid_: task (as the generic term)\n"
        glossary += "_Avoid_: chat, conversation (the history, not the talk)\n"
        source = "task = 1\nchat = 2\nconversation = 3\n"
        findings = self.findings(glossary, source)
        self.assertEqual(len(findings), 3)
        self.assertTrue(findings[0].endswith(
            "'task' holds 'task', a word the glossary marks Avoid"))
        self.assertTrue(findings[1].endswith(
            "'chat' holds 'chat', a word the glossary marks Avoid"))
        self.assertTrue(findings[2].endswith(
            "'conversation' holds 'conversation', a word the glossary marks Avoid"))

    def test_used_names_are_not_named(self) -> None:
        source = "import sqlite3\n\nsqlite3.connect(p, timeout=30)\n"
        self.assertEqual(self.findings(GLOSSARY, source), [])

    def test_alias_of_an_imported_module_is_named(self) -> None:
        glossary = "# Words\n\n_Avoid_: parser\n"
        findings = self.findings(glossary, "import json as parser\n")
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].endswith(
            "'parser' holds 'parser', a word the glossary marks Avoid"))

    def test_substring_is_not_a_word(self) -> None:
        glossary = "# Words\n\n_Avoid_: sync, import\n"
        source = "async_reader = 1\nimportlib_reader = 2\nimport importlib\n"
        self.assertEqual(self.findings(glossary, source), [])

    def test_public_def_without_hints(self) -> None:
        source = "def f(a):\n    return a\n\ndef _f(a):\n    return a\n"
        source += "def m(self):\n    return self\n"
        source += "def v(*args):\n    return args\n\ndef k(**kwargs):\n    return kwargs\n"
        findings = self.findings(GLOSSARY, source)
        self.assertEqual(len(findings), 1)
        self.assertTrue(findings[0].endswith("'f' has no annotation for the parameter 'a'"))
        self.assertIn(":1: ", findings[0])

    def test_overload_is_exempt(self) -> None:
        source = "import typing\n\n\n@typing.overload\ndef f(a):\n    ...\n"
        self.assertEqual(self.findings(GLOSSARY, source), [])

    def test_line_longer_than_99_columns(self) -> None:
        long_line = 'value = "' + "a" * 90 + '"\n'
        findings = self.findings(GLOSSARY, long_line)
        self.assertEqual(len(findings), 1)
        self.assertIn(":1: ", findings[0])
        self.assertIn("the line holds 100 columns, over 99", findings[0])

    def test_syntax_fault_is_a_finding(self) -> None:
        findings = self.findings(GLOSSARY, "def broken(:\n    return 1\n")
        self.assertEqual(len(findings), 1)
        self.assertIn(":1: ", findings[0])
        self.assertIn("syntax fault", findings[0])

    def run_main(self, root: str) -> tuple[int, str]:
        """Run the check on a tree: its exit code and its printed findings, captured."""
        sink = io.StringIO()
        with contextlib.redirect_stdout(sink):
            code = style.main([root])
        return code, sink.getvalue()

    def test_main_returns_1_with_findings_and_0_without(self) -> None:
        with support.TemporaryFolder() as root:
            (root / "GLOSSARY.md").write_text(GLOSSARY, encoding="utf-8")
            spec = root / "docs" / "spec"
            spec.mkdir(parents=True)
            (spec / "architecture.md").write_text(
                architecture_document("| `events` | the schema | — |", "`events`"),
                encoding="utf-8")
            (root / "src").mkdir()
            (root / "tests").mkdir()
            (root / "src" / "good.py").write_text("value = 1\n", encoding="utf-8")
            (root / "tests" / "good_test.py").write_text(
                "def good() -> int:\n    return 1\n", encoding="utf-8")
            code, printed = self.run_main(str(root))
            self.assertEqual((code, printed), (0, ""))
            cache = root / "src" / "__pycache__"
            cache.mkdir()
            (cache / "cached.py").write_text("job = 1\n", encoding="utf-8")
            code, printed = self.run_main(str(root))
            self.assertEqual((code, printed), (0, ""))
            (root / "src" / "bad.py").write_text("job = 1\n", encoding="utf-8")
            code, printed = self.run_main(str(root))
            self.assertEqual(code, 1)
            self.assertIn("'job'", printed)
            (root / "src" / "bad.py").unlink()
            (root / "tests" / "bad_test.py").write_text("job = 1\n", encoding="utf-8")
            code, printed = self.run_main(str(root))
            self.assertEqual(code, 1)
            self.assertIn("'job'", printed)

    def test_the_readers_of_the_document(self) -> None:
        document = (
            "# Architecture\n\n## Modules\n\n| Module | Responsibility | Depends on |\n"
            "|---|---|---|\n| `events` | the schema | — |\n"
            "| `store` | the segments | `events`, `platform` |\n"
            "| `cli` | the terminal | all |\n\n"
            "Build order: `events`, `platform`,\n`store` → `cli`. A module never imports a\n"
            "module that depends on it.\n")
        lines_at, listed = style.module_rows(document)
        self.assertEqual(lines_at, {"events": 7, "store": 8, "cli": 9})
        self.assertEqual(listed, {
            "events": frozenset(),
            "store": frozenset({"events", "platform"}),
            "cli": None})
        self.assertEqual(style.build_order(document), [["events", "platform", "store"], ["cli"]])

    def test_a_decoy_table_under_a_later_heading_is_not_read(self) -> None:
        document = (
            "# Architecture\n\n## Modules\n\n| Module | Responsibility | Depends on |\n"
            "|---|---|---|\n| `events` | the schema | — |\n"
            "| `store` | the segments | `events`, `platform` |\n\n"
            "Build order: `events` → `store`.\n\n"
            "## Layout\n\n| Module | Folder | Reads |\n|---|---|---|\n"
            "| `store` | `store` | `events`, `days` |\n")
        files = {
            "__init__.py": "value = 1\n",
            "events/__init__.py": "value = 1\n",
            "store/__init__.py": "from ..events import Event\n",
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            spec = root / "docs" / "spec" / "architecture.md"
            self.assertEqual((code, printed), (
                1, f"{spec}:8: the row of 'store' lists 'platform', which no file of the "
                   f"module imports\n"))

    def test_a_build_order_line_outside_the_section_is_not_the_line(self) -> None:
        document = (
            "# Architecture\n\n## Modules\n\n| Module | Responsibility | Depends on |\n"
            "|---|---|---|\n| `events` | the schema | — |\n"
            "| `store` | the segments | `events` |\n\n"
            "Build order: `events` → `store`.\n\n"
            "## Reading the document\n\nBuild order: `store` → `events`.\n")
        files = {
            "__init__.py": "value = 1\n",
            "events/__init__.py": "value = 1\n",
            "days.py": "value = 1\n",
            "store/__init__.py": "from ..events import Event\nfrom ..days import Day\n",
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            path = root / "src" / "ai_effort_ledger" / "store" / "__init__.py"
            self.assertEqual((code, printed), (
                1, f"{path}:2: an import of 'days' that the row of 'store' does not list\n"))

    def test_the_forms_of_the_pass_on_a_clean_tree(self) -> None:
        document = architecture_document(
            "| `events` | the schema | — |\n"
            "| `platform` | the machine | — |\n"
            "| `store` | the segments | — |\n"
            "| `days` | the local days | `events` |\n"
            "| `reports` | the outputs | `days`, `store` |\n"
            "| `adapters` | the adapters | `events` |\n"
            "| `cli` | the terminal | all |",
            "`events`, `platform` → `store`, `days` → `adapters`, `reports` → `cli`")
        files = {
            "__init__.py": '"""An invented package."""\n',
            "events/__init__.py": "Event = 1\n",
            "platform/__init__.py": "value = 1\n",
            "store/__init__.py": "value = 1\n",
            "store/files.py": "value = 1\n",
            "days.py": "from ai_effort_ledger.events import Event\n",
            "reports/__init__.py": (
                "from ..days import EventKey\n"
                "from .. import days\n"
                "from ..store.files import write\n"),
            "adapters/__init__.py": "value = 1\n",
            "adapters/claude_code/__init__.py": "from . import mapping\n",
            "adapters/claude_code/completeness.py": "from ...events import Event\n",
            "cli/__init__.py": "from ..adapters import Adapter\nfrom .. import days, reports\n",
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            self.assertEqual((code, printed), (0, ""))
            base = root / "src" / "ai_effort_ledger"
            completeness = base / "adapters" / "claude_code" / "completeness.py"
            terminal = base / "cli" / "__init__.py"
            outputs = base / "reports" / "__init__.py"
            self.assertEqual(style.package_imports(base), {
                "adapters": {"events": [(completeness, 1)]},
                "cli": {"adapters": [(terminal, 1)], "days": [(terminal, 2)],
                        "reports": [(terminal, 2)]},
                "days": {"events": [(base / "days.py", 1)]},
                "reports": {"days": [(outputs, 1), (outputs, 2)], "store": [(outputs, 3)]},
            })

    def test_a_class_and_a_submodule_that_share_a_name(self) -> None:
        document = architecture_document(
            "| `events` | the schema | — |\n"
            "| `retention` | the setting | — |\n"
            "| `reports` | the outputs | `retention` |",
            "`events` → `retention` → `reports`")
        files = {
            "__init__.py": "value = 1\n",
            "events/__init__.py": "value = 1\n",
            "retention.py": "value = 1\n",
            "reports/__init__.py": "from .. import Retention\nfrom .. import retention\n",
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            path = root / "src" / "ai_effort_ledger" / "reports" / "__init__.py"
            self.assertEqual((code, printed), (
                1, f"{path}:1: an import of 'ai_effort_ledger' that the row of 'reports' does "
                   f"not list\n"))

    def test_a_module_the_row_does_not_list(self) -> None:
        document = architecture_document(
            "| `events` | the schema | — |\n"
            "| `days` | the local days | — |",
            "`events` → `days`")
        files = {
            "__init__.py": "value = 1\n",
            "events/__init__.py": "value = 1\n",
            "days.py": (
                "def take(value: int) -> int:\n"
                "    from .events import Event\n"
                "    return value\n"),
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            path = root / "src" / "ai_effort_ledger" / "days.py"
            self.assertEqual((code, printed), (
                1, f"{path}:2: an import of 'events' that the row of 'days' does not list\n"))

    def test_a_dependency_no_file_imports(self) -> None:
        document = architecture_document(
            "| `events` | the schema | — |\n"
            "| `platform` | the machine | — |\n"
            "| `store` | the segments | `events`, `platform` |",
            "`events`, `platform` → `store`")
        files = {
            "__init__.py": "value = 1\n",
            "events/__init__.py": "value = 1\n",
            "platform/__init__.py": "value = 1\n",
            "store/__init__.py": "from ..events import Event\n",
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            spec = root / "docs" / "spec" / "architecture.md"
            self.assertEqual((code, printed), (
                1, f"{spec}:9: the row of 'store' lists 'platform', which no file of the "
                   f"module imports\n"))

    def test_a_dependency_below_in_the_build_order(self) -> None:
        document = architecture_document(
            "| `events` | the schema | — |\n"
            "| `days` | the local days | `configuration` |\n"
            "| `configuration` | the reads | — |",
            "`events` → `days` → `configuration`")
        files = {
            "__init__.py": "value = 1\n",
            "events/__init__.py": "value = 1\n",
            "days.py": "from .configuration import read\n",
            "configuration/__init__.py": "value = 1\n",
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            spec = root / "docs" / "spec" / "architecture.md"
            path = root / "src" / "ai_effort_ledger" / "days.py"
            self.assertEqual((code, printed), (
                1,
                f"{spec}:8: the row of 'days' lists 'configuration', which stands below it in "
                f"the build order\n"
                f"{path}:1: an import of 'configuration' that stands below 'days' in the build "
                f"order\n"))

    def test_a_cycle_of_two_modules(self) -> None:
        document = architecture_document(
            "| `events` | the schema | — |\n"
            "| `days` | the local days | `metrics` |\n"
            "| `metrics` | the figures | `days` |",
            "`events` → `days`, `metrics`")
        files = {
            "__init__.py": "value = 1\n",
            "events/__init__.py": "value = 1\n",
            "days.py": "from .metrics import Metrics\n",
            "metrics/__init__.py": "from ..days import EventKey\n",
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            path = root / "src" / "ai_effort_ledger" / "metrics" / "__init__.py"
            self.assertEqual((code, printed), (
                1, f"{path}:1: a cycle of the import graph: 'days' -> 'metrics' -> 'days'\n"))

    def test_a_module_imported_in_the_package_root(self) -> None:
        document = architecture_document(
            "| `events` | the schema | — |",
            "`events`")
        files = {
            "__init__.py": "from .events import Event\n",
            "events/__init__.py": "value = 1\n",
        }
        with support.TemporaryFolder() as root:
            write_tree(root, document, files)
            code, printed = self.run_main(str(root))
            path = root / "src" / "ai_effort_ledger" / "__init__.py"
            self.assertEqual((code, printed), (
                1, f"{path}:1: an import of 'events' that the row of 'ai_effort_ledger' does "
                   f"not list\n"))

    def test_a_tree_without_the_architecture_document(self) -> None:
        with support.TemporaryFolder() as root:
            (root / "GLOSSARY.md").write_text(GLOSSARY, encoding="utf-8")
            package_file(root, "__init__.py", "value = 1\n")
            with self.assertRaises(FileNotFoundError):
                style.main([str(root)])

    def test_a_tree_without_a_table(self) -> None:
        with support.TemporaryFolder() as root:
            write_tree(root, "# Architecture\n\nWords without a table.\n", {
                "__init__.py": "value = 1\n",
                "events/__init__.py": "value = 1\n",
                "days.py": "from .events import Event\n",
            })
            code, printed = self.run_main(str(root))
            path = root / "src" / "ai_effort_ledger" / "days.py"
            self.assertEqual((code, printed), (
                1, f"{path}:1: an import of 'events' that the row of 'days' does not list\n"))
