# Phase 1 Implementation Plan — the daily timesheet of one person

Status: draft, in review by the owner (2026-11-19). In the release commit of Task 66 this line becomes
`Status: completed`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or executing-plans to
> implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Each task has a Backlog.md task
> with the same number, which is created from this plan after the owner's review and before Task 1, outside the
> plan; change its status only with the `backlog` command.

**Goal:** Build the core of the ledger, the package `ai-effort-ledger`, so that one person gets the daily timesheet of
their work with Claude Code and Claude Desktop, as `product.md` › Phase 1 scopes it, with its 10 acceptance criteria
met.

**Architecture:** One Python package with the 17 modules of `architecture.md` › Modules, built in the build order of
that section, each module tested before the next one uses it. Adapters turn native logs into complete events, which
ingestion appends to single-writer segments of the store; reports select events through the local index and compute
`selection` → `metrics` → `attribution` → `declared` → `reports`, with `cli` as the only module that writes to the
terminal.

**Tech Stack:** Python 3.11+ (standard library: `tomllib`, `zoneinfo`, `sqlite3`, `zlib`, `json`, `argparse`,
`unittest`), `tzdata` at run time, `flit_core` to build, `uv` for the local virtual environment, GitHub Actions.

**Spec:** `docs/spec/` (all eight files), `GLOSSARY.md`, `docs/adr/0001`–`0024`. The plan argues from them; when the
plan and a spec disagree, the spec wins and the divergence is flagged (CLAUDE.md › Documents).

## Global Constraints

- Python `>=3.11`. Run time: the standard library and `tzdata` only. Build: `requires = ["flit_core >=4.2,<5"]`,
  `build-backend = "flit_core.buildapi"`. Any other dependency, also for development: ask the owner first.
- Package `ai-effort-ledger`, import name `ai_effort_ledger`, one command `ai-effort-ledger`; static version in
  `[project]` of `pyproject.toml`; `0.1.0.dev0` until the first release (decision D1).
- A version with a development mark writes to a store only when `AI_EFFORT_LEDGER_DEVELOPMENT` is `1`; otherwise every
  command that writes stops with exit code 1. `tests/support.py` sets the variable.
- Time zones only from `tzdata`: `zoneinfo.reset_tzpath(to=[])`; every report records the `tzdata` version.
- No network. No program runs inside a folder taken from a source (ADR 0004). The only programs the ledger runs: the
  schedulers in `setup` and `schedule`, and `ioreg` on macOS.
- No field holds text of prompts, responses, tool input, or code, or paths of files in tool input (ADR 0003, ADR 0012).
  Fixtures are written by hand with invented text; never copy text out of a native log, also not into a test.
- Instants: RFC 3339 text in UTC with `Z` and milliseconds (`2026-11-19T08:30:00.125Z`). Durations: whole seconds.
  An absent field is not written, never written as `null`.
- Module dependencies as `architecture.md` › Modules: a module imports only the modules above it in that table (its
  dependencies and theirs), never a module that depends on it; `reports` imports neither `metrics` nor `attribution`.
  Every module other than `cli` returns warnings and configuration errors as values: `{"code": str, "values": dict}`.
  A configuration error leaves the figures of a report computable; a stop error stops the command
  (`configuration.md` › Format).
- Exit codes: 0 completed, 1 stopped with an error, 2 wrong use, 3 completed with incomplete figures
  (`command-line.md` › Exit codes). Any event of a newer schema version gives `newer_schema_version` and exit
  code 3 (ADR 0023 › Consequences; `event-schema.md` › Encoding).
- Lock: 10 minutes. Local index: SQLite in WAL mode, busy timeout 30 seconds.
- PEP 8, lines at most 99 columns, type hints on public functions, English docstrings, names from `GLOSSARY.md`;
  `tests/style.py` names the words of `architecture.md` › Tests (ruled 2026-11-19).
- Tests: `unittest`, temporary folders only, never the native logs, the store, or the configuration of the machine.
  Full run: `python -I -m unittest discover -s tests`, in `.venv` with `uv pip install -e .`.
- Every `cwd` that a test or the benchmark ingests, or reads settings files for, is a folder below its temporary
  folder: `support.write_session` takes it, and `support.copy_fixture` sets it in the copy of a fixture; a fixed path
  such as `D:\Work\Product` can exist on the machine that runs the tests, with a repository and settings
  files that no test reads.
- The report tests compare an output with its expected file through `support.normalize` (Task 54): it replaces with
  fixed marks the absolute paths inside the temporary folders of the test, the number of bytes read and the chained
  hash of each segment of the report record, and every `tzdata` version, so one committed expected file fits every
  run and every operating system; the chained hash itself has its tests in Task 25.
- Every test method, `setUp`, and `tearDown` is written with `-> None` (CLAUDE.md › Core: public functions have
  type hints); the test stubs of this plan leave it out to stay short (ruled 2026-11-19).
- A function that builds a path for a `system` builds it as `PureWindowsPath` for `"Windows"` and `PurePosixPath`
  otherwise; only the running system turns it into `Path`, resolves it, or checks that it exists. The tests of
  every `system` therefore run on the three runners (Tasks 6, 17, 24); a test that needs a folder of another system
  to exist runs only there (`skipUnless`).
- Markdown prose at most 120 columns. One local commit per task; a push only when the owner asks; never commit
  `.claude/` (see Execution).

## Decisions this plan takes

Each one is a choice that the specs leave open. The walkthrough of 2026-11-19 confirmed or changed each one
before any code. A decision that fixes bytes on disk (D2, D3, D4, D11, D13) becomes a sentence of its spec
before the task that writes those bytes, and an ADR when it is hard to reverse, surprising, and a real
trade-off (ruled 2026-11-19). No row holds D8: that decision is a sentence of Global
Constraints (ADR 0023 › Consequences); the table does not repeat it.

| Id | Decision | Why |
|---|---|---|
| D1 | Version `0.1.0.dev0`; the first release is `0.1.0` | A first release below 1.0 says that the command-line contract is new (ruled 2026-11-19) |
| D2 | An event in memory is a JSON-shaped `dict[str, Any]`; `encode_event` writes `sort_keys=True`, separators `(",", ":")`, `ensure_ascii=False` | The schema is open: a reader keeps fields it does not know only as data; sorted keys make two stores byte-comparable; sentence of `event-schema.md` › Encoding (ruled 2026-11-19) |
| D3 | The event identifier of a record without an identifier is `<kind>:<timestamp>:<position>`, the timestamp as stored text, the position counted from 0 | Stored keys never change (ADR 0023): this format is fixed from the first event; sentence of `event-schema.md` › Keys and invariants (ruled 2026-11-19) |
| D4 | The chained hash chains raw SHA-256 digests over the bytes of each line including its `\n`; the report record shows it as hexadecimal | The line as written is what a file-sync service copies; sentence of `architecture.md` › Local index (ruled 2026-11-19) |
| D5 | The person configuration accepts a dated value as a TOML value (`2026-12-01T00:00:00Z`, `04:00:00`) or as a basic string; `config add` writes basic strings | `configuration.md` › Writes asks for basic strings, and its examples use TOML values; sentence of `configuration.md` › Format (ruled 2026-11-19) |
| D6 | The retention period of `claude-code` is the shortest `cleanupPeriodDays` in effect among the managed and user settings files and the shared and local project settings files of each `cwd` of a session the ingestion reads, stored or held back | Claude Code deletes native logs after a session starts in any folder; a warning too early is harmless, one too late is not; sentence of `claude-code-adapter.md` › Retention (ruled 2026-11-19; held-back sessions ruled 2026-11-20) |
| D7 | A fork is found in the local index by native identifier | Every copied record that gives an event keeps its native identifier; sentence of `claude-code-adapter.md` › Forks, edited to match (ruled 2026-11-19) |
| D9 | The workflow installs with `python -m pip install -e .` | Only actions that GitHub publishes are allowed; `uv` needs a third-party action (ruled 2026-11-19) |
| D10 | A stop error is an exception with `code`, `values`, and `exit_code`; `language` holds its texts | Modules without dependencies cannot share a base class (ruled 2026-11-19) |
| D11 | `salt` is 32 random hexadecimal characters; `installation` is `sha256(salt + identifier)` in hexadecimal | `ingestion.md` › Store asks for a salted hash; sentence of `ingestion.md` › Store (ruled 2026-11-19) |
| D12 | Figures are computed in milliseconds; parts that add up to a total become whole seconds by the largest-remainder method on the whole seconds of the total | Acceptance criterion 4 needs parts that add up in JSON, which holds whole seconds; ties follow `bucket_order` (`metrics.md` › Declared values); the proposal and `declared_value_below_measured` use the shown whole seconds (ruled 2026-11-19) |
| D13 | A frozen report file also holds `frozen_at`, the instant of the freeze; the latest frozen report of a day is the one with the latest `frozen_at`, then the identifier | `command-line.md` › Frozen reports compares each day with the latest frozen report; the tie needs an instant and an identifier; sentences of `command-line.md` › Frozen reports, › JSON documents (ruled 2026-11-19) |
| D14 | Before it appends, a machine cuts a last line without `\n` from its own segment, under the lock | A torn append would join the next event into one broken line; sentence of `ingestion.md` › Store (ruled 2026-11-19) |

## Gates

A gate needs the owner. The task that holds it stops at the gate until the owner answers.

| Gate | Task | What the owner gives |
|---|---|---|
| G1 | Task 2 | Ruled 2026-11-19: words of glossary terms pass (`architecture.md` › Tests) |
| G2 | Task 16 | A run of the survey script on a copy of the native logs, and the rulings that its findings need |
| G3 | Task 43 | The ruling on the CLDR release of the Windows time-zone table, after a dated research note |
| G4 | Task 20 | Ruled 2026-11-19: an empty text has no lines (`event-schema.md` › Keys and invariants) |
| G5 | Task 66 | A run of the benchmark on a laptop, before the first release |
| G6 | Task 3, and the last task of each milestone | Whether to push the branch now, so that the workflow runs the tests on Windows, Linux, and macOS (ruled 2026-11-19) |
| G7 | Task 55 | Approval of the first expected text file of each report, before the other files copy its layout (ruled 2026-11-19) |

## Review Focus

Inputs that the specs imply and that no acceptance criterion names. Each line has its test in the task named.

1. A native log whose last line is half-written because Claude Code is writing it: no `invalid_record` warning; the
   line is not read until the settle time, and the other records are read as usual (`claude-code-adapter.md` ›
   Native logs; Task 17, `test_partial_last_line_is_not_read_without_warning`; Task 22,
   `test_unread_last_line_holds_the_session_back`).
2. Folders with spaces and non-ASCII letters, such as `D:\Work\Città Example`, in the store folder, in `cwd`, and in
   TOML values (Task 13, `test_append_keeps_non_ascii_and_backslashes`; Task 29, `test_cwd_with_non_ascii_letters`
   and `test_store_folder_with_non_ascii_letters`).
3. Records of one file out of time order: metrics sort by `timestamp`, never by line (Task 33,
   `test_records_out_of_order_give_same_agent_time`).
4. A folder of native logs that the machine configuration lists and that no longer exists: the ingestion completes
   with zero new events for it (Task 29, `test_missing_native_log_folder`).
5. A line of a native log that is not valid UTF-8: one `invalid_record` warning, no stop (Task 17,
   `test_invalid_utf8_line_is_invalid_record`).

## File structure

```text
pyproject.toml
.github/workflows/tests.yml
src/ai_effort_ledger/
  __init__.py
  events.py                      fields, encoding, validation, keys, merge rule, versions
  platform/   __init__.py folders.py identity.py lock.py scheduler.py zones.py windows_zones.py
  repository/ __init__.py discovery.py objects.py
  language.py                    English and Italian texts by code
  configuration/ __init__.py values.py machine.py person.py writes.py
  store/      __init__.py segments.py purges.py files.py
  adapters/   __init__.py
    claude_code/ __init__.py discovery.py reading.py tables.py mapping.py size.py subagents.py
                 completeness.py forks.py retention.py
  index.py
  days.py
  ingestion/  __init__.py state.py run.py
  selection.py
  metrics/    __init__.py spans.py human.py agent.py classes.py
  attribution/ __init__.py rules.py names.py annotations.py split.py
  declared.py
  setup.py
  reports/    __init__.py record.py documents.py text.py frozen.py
  cli/        __init__.py arguments.py output.py setup_actions.py store_actions.py entry_actions.py
              report_actions.py figures.py
tests/
  support.py                     environment, temporary folders, instants, builders of invented records
  style.py                       the static check (not a test module), with test_style.py
  benchmark.py                   the benchmark (not a test module)
  fixtures/claude_code/          one hand-written native log for each row of the adapter's tables
  fixtures/expected/             expected text and JSON output, English and Italian
  test_<module>.py               unit tests, test_package.py and test_adapter_claude_code.py among them;
                                 test_scenarios.py, test_store_machines.py, test_order.py,
                                 test_privacy.py, test_reports_output.py
```

One file has one responsibility. A subpackage exists where a module of `architecture.md` has more than one
responsibility; its `__init__.py` holds the public names that other modules use, and nothing else imports from its
inner files. The tree shows the package and its tests; the tasks also write repository files that no module
builds — the survey script and the research notes of Tasks 16 and 43, `README.md` and `CLAUDE.md` in Task 65,
the benchmark note of Task 66.

## Execution

- Mode (ruled 2026-11-19): subagent-driven. For each task a fresh writer agent and a fresh reviewer agent; the
  reviewer compares the task with the spec sections of its Backlog task before the next task starts; one review of
  the whole branch at the end.
- A task that adds no interface of the package has no Interfaces block, and its steps differ from the five-step
  shape on purpose: the workflow, the survey, the scenarios, the report tests, the suites, and the end of the
  phase.
- Each task: write the failing tests, run them and see them fail, write the code, run the task's tests, then the
  full suite, then `python -I tests/style.py`, set the Backlog task to Done with the `backlog` command, then the
  checkpoint.
- Checkpoint (ruled 2026-11-19): one local commit on `feat-phase-1-core` with the code, the tests, and the Backlog
  task file of the task; the message starts with `Task <n>:`. A push only when the owner asks.
- Gate G6 (ruled 2026-11-19): after Task 3 and after the last task of each milestone, ask the owner whether to
  push the branch; on yes, push and check that the six jobs of the workflow pass before the next task.
- Run one test file: `python -I -m unittest discover -s tests -p "test_events.py"`; one test: add `-k <name>`.
- A divergence between a spec and the code is flagged, not resolved: one dated line in `~/.claude/escalations.md` and
  an item in the `To be confirmed` section of the spec; the task stops at that point until the owner rules.

---

## Milestone 0 — Foundation

### Task 1: Package skeleton and test support

**Spec:** `architecture.md` › Runtime, › Project structure, › Tests.

**Files:**
- Create: `pyproject.toml`, `src/ai_effort_ledger/__init__.py`, `tests/support.py`, `tests/test_package.py`

**Interfaces:**
- Produces: `tests/support.py`: `utc(text: str) -> datetime` (`"2026-11-10T09:00"` or with seconds and
  milliseconds, read as UTC); `TemporaryFolder` (context manager, yields `Path`); at import it sets
  `os.environ["AI_EFFORT_LEDGER_DEVELOPMENT"] = "1"`.

- [ ] **Step 1: Write the failing tests** in `tests/test_package.py`:

```python
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
```

- [ ] **Step 2: Run and see it fail**: `python -I -m unittest discover -s tests -p "test_package.py"` → error,
  package not found.
- [ ] **Step 3: Write `pyproject.toml`** with `[build-system]` as in Global Constraints, `[project]` with `name`,
  `version = "0.1.0.dev0"`, `description`, `readme = "README.md"`, `requires-python = ">=3.11"`,
  `dependencies = ["tzdata"]`, and `[project.scripts] ai-effort-ledger = "ai_effort_ledger.cli:main"`; a package
  docstring in `__init__.py`; then `uv venv` and `uv pip install -e .`.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 2: Static check `tests/style.py` (gate G1)

**Spec:** `architecture.md` › Tests; `lint-tool-2026-11.md` › Recommendation; `GLOSSARY.md`.

**Gate G1, ruled 2026-11-19** (`architecture.md` › Tests): a word that the glossary marks _Avoid_ is named unless a
glossary term or the title of the glossary holds it; an _Avoid_ entry of more than one word is named only as that
sequence of words; the text in parentheses of an entry is not part of it; the check names only identifiers that the
code defines (functions, classes, parameters, assigned names, attributes assigned on `self`, import aliases), not names
it uses from other code.

**Files:**
- Create: `tests/style.py`, `tests/test_style.py`

**Interfaces:**
- Produces: `split_identifier(name: str) -> list[str]` (lower-case words of `snake_case` and `CamelCase`);
  `named_words(glossary: str) -> tuple[frozenset[str], frozenset[tuple[str, ...]]]` (single words, sequences);
  `check_file(path: Path, words: frozenset[str], sequences: frozenset[tuple[str, ...]]) -> list[str]` (findings as
  `path:line: text`); `main(argv: list[str] | None = None) -> int` (0 without findings, 1 with findings). Reads
  `GLOSSARY.md` beside `tests/`, checks `src/` and `tests/`, skips `__pycache__`.

- [ ] **Step 1: Write the failing tests** with a glossary text and Python files written into a temporary folder:

```python
def test_split_identifier(self):
    self.assertEqual(style.split_identifier("parseHTTPRecord_line"), ["parse", "http", "record", "line"])

def test_named_word_in_a_def_name(self):            # "def run_job(): ..." -> one finding naming "job"
def test_word_of_a_glossary_term_is_allowed(self):  # "decision_request = 1" -> no finding
def test_sequence_is_named_only_as_sequence(self):  # "effective_hours" named; "hours" alone named; "effective" not
def test_parenthesis_is_not_part_of_the_entry(self):  # "_Avoid_: task (as the generic term)" names "task"
def test_used_names_are_not_named(self):            # "sqlite3.connect(p, timeout=30)" -> no finding
def test_alias_of_an_imported_module_is_named(self):  # "import json as parser" -> one finding
def test_substring_is_not_a_word(self):             # "async_reader", "importlib" -> no finding for sync/import
def test_public_def_without_hints(self):            # "def f(a): ..." -> finding; "def _f(a)" -> none;
                                                    # "def m(self): ..." -> none
def test_overload_is_exempt(self):          # a def with @typing.overload and only "..." as its body -> none
def test_line_longer_than_99_columns(self):         # 100 characters -> finding with its line number
def test_syntax_fault_is_a_finding(self):
def test_main_returns_1_with_findings_and_0_without(self):
```

- [ ] **Step 2: Run and see it fail**: `python -I -m unittest discover -s tests -p "test_style.py"`.
- [ ] **Step 3: Write `tests/style.py`** with `ast` and `tokenize.open()` (encoding cookies and BOMs), counting
  columns as characters of the line without its line break. A function is public when its name does not start with
  `_`; the parameters `self` and `cls`, a vararg, a kwarg, and a nested function need no annotation.
- [ ] **Step 4: Run and see it pass**; then `python -I tests/style.py` on the tree → exit 0.
- [ ] **Step 5: Checkpoint.**

### Task 3: GitHub Actions workflow

**Spec:** `architecture.md` › Tests; acceptance criterion 8.

**Files:**
- Create: `.github/workflows/tests.yml`

- [ ] **Step 1: Find the commit hashes** of the newest release tags of `actions/checkout` and `actions/setup-python`:
  `gh api repos/actions/checkout/releases/latest --jq .tag_name`, then
  `gh api repos/actions/checkout/commits/<tag> --jq .sha` (the same for `setup-python`).
- [ ] **Step 2: Write the workflow**: on `push` and `pull_request`; matrix `os: [windows-latest, ubuntu-latest,
  macos-latest]`, `python-version: ["3.11", "3.x"]`; steps: checkout at its hash, setup-python at its hash,
  `python -m pip install -e .`, `python -I -m unittest discover -s tests`, `python -I tests/style.py` (D9). The job
  sets no secret and has `permissions: contents: read`.
- [ ] **Step 3: Check the pins**: `grep -cE "uses: [a-z/-]+@[0-9a-f]{40}$" .github/workflows/tests.yml` → `2`, and
  `grep -c "uses:"` → `2`.
- [ ] **Step 4: Gate G6, then verify on GitHub** after the owner allows a push: `gh run list --workflow tests.yml
  --limit 1` shows six jobs passing. On no, the next task starts; acceptance criterion 8 stays unmet until a
  later push.
- [ ] **Step 5: Checkpoint.**

## Milestone 1 — Modules without dependencies: `events`, `platform`, `repository`, `language`

### Task 4: `events` — values, encoding, and reading of newer schema versions

**Spec:** `event-schema.md` › Fields, › Encoding; `architecture.md` › Runtime (versions); ADR 0023.

**Files:**
- Create: `src/ai_effort_ledger/events.py`, `tests/test_events.py`

**Interfaces:**
- Produces: `SCHEMA_VERSION = 1`; `Event = dict[str, Any]`; `KINDS: frozenset[str]` (the 17 kinds);
  `FIELDS: frozenset[str]` (every field of › Fields); `FIXED_VALUES: dict[str, frozenset[str]]` for `kind`, `actor`,
  `invocation`, `subagent_mode`, `tool_category`, `input_origin`, `decision_type`, `manual_mode`, `size_basis`,
  `repo_basis`, `purge_reason`; `format_instant(instant: datetime) -> str`; `parse_instant(text: str) -> datetime`
  (aware UTC, truncated to milliseconds; accepts an offset or `Z`); `version_key(text: str) -> tuple` (raises
  `ValueError` for a wrong version); `writer_version() -> str` (`importlib.metadata.version("ai-effort-ledger")`);
  `encode_event(event: Event) -> bytes` (D2; one line ending in `b"\n"`; `ValueError` for a `None` value);
  `Decoded(state: str, event: Event | None, newer: bool)` with `state` in `"event"`, `"left_out"`, `"broken"`;
  `decode_line(data: bytes) -> Decoded`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_instant_reads_back_equal(self):
    self.assertEqual(events.format_instant(support.utc("2026-11-19T08:30:00.125")),
                     "2026-11-19T08:30:00.125Z")
    self.assertEqual(events.parse_instant("2026-11-19T09:30:00.125+01:00"),
                     support.utc("2026-11-19T08:30:00.125"))

def test_version_order(self):
    k = events.version_key
    self.assertLess(k("1.9.0"), k("1.10.0"))
    self.assertLess(k("1.3.0.dev0"), k("1.3.0"))
    self.assertLess(k("1.3.0.dev0"), k("1.3.0.dev1"))
    with self.assertRaises(ValueError):
        k("v1.3")

def test_encode_is_one_sorted_line(self):     # keys sorted, no spaces, ends with b"\n", UTF-8 letters kept
def test_encode_refuses_null(self):           # {"model": None} -> ValueError
def test_decode_event(self):                  # a valid schema 1 line -> state "event", newer False
def test_decode_not_json_is_broken(self):
def test_decode_missing_required_field_is_broken(self):    # schema 1 without "machine"
def test_decode_unknown_kind_of_schema_1_is_broken(self):
def test_newer_unknown_kind_is_left_out(self):             # schema 2, kind "future" -> "left_out", newer True
def test_newer_unknown_fixed_value_is_left_out(self):      # schema 2, tool_category "paint"
def test_newer_unknown_field_is_dropped(self):             # schema 2, field "x" -> "event", no "x", newer True
def test_open_sets_pass_through(self):        # tokens {"reasoning_output": 5}, requests, price_factors kept
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `events.py`** with the names above. Required fields: `schema_version`, `source`, `event_uid`,
  `timestamp`, `ingested_at`, `writer_version`, `actor`, `kind`, `machine`.
- [ ] **Step 4: Run and see it pass**, then the full suite and `python -I tests/style.py`.
- [ ] **Step 5: Checkpoint.**

### Task 5: `events` — keys, key order, merge rule, events that a command writes

**Spec:** `event-schema.md` › Keys and invariants, › Encoding (event keys).

**Files:**
- Modify: `src/ai_effort_ledger/events.py`, `tests/test_events.py`

**Interfaces:**
- Produces: `EventKey` (frozen dataclass: `source: str`, `native_id: str | None = None`, `session_id: str | None =
  None`, `event_uid: str | None = None`; `to_json() -> dict[str, str]`; `from_json(value: Mapping[str, str]) ->
  EventKey`); `random_uid() -> str` (a random UUID 4 as text);
  `event_key(event: Event) -> EventKey`; `event_order(event: Event) -> tuple` (by `source`, `session_id`,
  `event_uid`; an absent part before every text); `winning_copy(a: tuple[Event, str], b: tuple[Event, str]) ->
  tuple[Event, str]` (pairs of event and segment name); `ledger_event(kind: str, actor: str, machine: str,
  timestamp: datetime, fields: Mapping[str, Any], new_uid: Callable[[], str] = random_uid, version: str | None =
  None) -> Event` (source `ledger`, `event_uid` from `new_uid`, a random UUID 4 by default, `writer_version` from
  `version`, `writer_version()` when it is `None`, no `ingested_at`: the store sets it).

- [ ] **Step 1: Write the failing tests**:

```python
def test_key_with_native_identifier(self):       # -> EventKey("claude-code-jsonl", native_id="m1")
def test_key_without_native_identifier(self):    # -> source, session_id, event_uid
def test_key_of_a_ledger_event(self):            # -> EventKey("ledger", event_uid=<uuid>)
def test_key_json_forms(self):
    self.assertEqual(events.EventKey("ledger", None, None, "u").to_json(),
                     {"source": "ledger", "event_uid": "u"})
def test_key_from_json_reads_back_equal(self):   # the three forms
def test_absent_part_sorts_first(self):          # session_id None before "a"
def test_earliest_ingested_at_wins(self):
def test_equal_instants_resolve_by_segment_name(self):
    # same ingested_at: copy in "segments/a/2026-11.jsonl" wins over "segments/b/2026-11.jsonl"
def test_ledger_event_fields(self):              # schema_version 1, actor, kind, UUID 4, no ingested_at
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Add the names above to `events.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 6: `platform` — folders, store identifier, installation identifier

**Spec:** `architecture.md` › Files of a machine; `ingestion.md` › Store.

**Files:**
- Create: `src/ai_effort_ledger/platform/__init__.py`, `folders.py`, `identity.py`; `tests/test_platform.py`

**Interfaces:**
- Produces: `machine_folder(system: str, environ: Mapping[str, str], home: Path) -> PurePath`;
  `default_store_folder(system: str, environ: Mapping[str, str], home: Path) -> PurePath` (built as Global
  Constraints say; the caller on the running system turns it into `Path`);
  `store_identifier(store_folder: Path, system: str) -> str` (16 lower-case hexadecimal characters of SHA-256 of
  the resolved absolute path; on Windows the path text in lower case first); `installation_identifier(system: str)
  -> str | None`; `parse_ioreg(text: str) -> str | None`; `new_salt() -> str` and `salted_hash(identifier: str,
  salt: str) -> str` (D11). `system` is the value of `platform.system()`: `"Windows"`, `"Linux"`, `"Darwin"`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_folders_windows(self):     # LOCALAPPDATA=C:\L -> C:\L\ai-effort-ledger\machine and ...\store
def test_folders_linux_defaults(self):   # no XDG_* -> ~/.local/state/ai-effort-ledger/machine,
                                         #               ~/.local/share/ai-effort-ledger/store
def test_folders_linux_xdg(self):        # XDG_STATE_HOME, XDG_DATA_HOME set
def test_folders_macos(self):            # ~/Library/Application Support/ai-effort-ledger/{machine,store}
def test_store_identifier_windows_ignores_case(self):
    self.assertEqual(platform.store_identifier(Path(r"D:\Work\Store"), "Windows"),
                     platform.store_identifier(Path(r"d:\work\store"), "Windows"))
def test_store_identifier_is_16_hex(self):
def test_parse_ioreg(self):         # invented output with "IOPlatformUUID" = "0000-TEST" -> "0000-TEST"
def test_salted_hash_depends_on_salt(self):
def test_new_salt_is_32_hex(self):
def test_salted_hash_is_the_spec_digest(self):   # sha256 of the UTF-8 bytes of the salt then the identifier,
                                                 # as lower-case hexadecimal (ingestion.md › Store)
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the functions.** `installation_identifier`: `winreg` `MachineGuid` of
  `HKLM\SOFTWARE\Microsoft\Cryptography`; `/etc/machine-id`; `ioreg -rd1 -c IOPlatformExpertDevice`; `None` when
  the operating system gives none.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 7: `platform` — the lock

**Spec:** `architecture.md` › Concurrency.

**Files:**
- Create: `src/ai_effort_ledger/platform/lock.py`; Modify: `__init__.py`, `tests/test_platform.py`

**Interfaces:**
- Produces: `StoreLock(path: Path, limit_seconds: float = 600.0)`, a context manager that counts nested takes in
  one process: when the process already holds the lock of the same resolved path, it adds 1 to a counter and asks
  the operating system nothing, and the outermost exit releases the lock (ruled 2026-11-20), so `cli` and
  `run_ingestion` or `append_entry` can both take it; `LockUnavailable` (stop error: `code = "lock_unavailable"`,
  `values = {"path": str}`, `exit_code = 1`).

- [ ] **Step 1: Write the failing tests** (a second process holds the lock through `subprocess` and
  `sys.executable`; the holder keeps the lock past the limit, and the tests poll with a deadline, never a fixed
  sleep):

```python
def test_second_holder_waits_then_stops(self):   # limit 1 s while another process holds it -> LockUnavailable
def test_lock_free_after_holder_exits(self):
def test_lock_free_after_holder_is_killed(self): # the operating system releases it
def test_nested_take_in_one_process_does_not_wait(self):   # inner take of the same path: no wait; free only
                                                           # after the outer exit (a second process checks)
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `StoreLock`**: `msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)` on Windows, `fcntl.flock(fd,
  LOCK_EX | LOCK_NB)` elsewhere, a new try every 0.5 s until the limit; a counter for each resolved path in the
  process.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 8: `platform` — scheduler entries

**Spec:** `ingestion.md` › Frequency; `command-line.md` › Commands (`schedule`), › JSON documents
(`scheduler_failed`).

**Files:**
- Create: `src/ai_effort_ledger/platform/scheduler.py`; Modify: `__init__.py`, `tests/test_platform.py`

**Interfaces:**
- Produces: `ENTRY_NAME = "ai-effort-ledger-ingest"`; `SchedulerEntry(name: str, arguments: list[str], time: str)`;
  `scheduler_kind(system: str, which: Callable[[str], str | None]) -> str` (`"windows"`, `"launchd"`, `"systemd"`,
  `"cron"`); `entry_definition(kind: str, executable: Path, store_folder: Path, time: str) -> dict[str, str]`
  (file name → text: Task Scheduler XML, launchd plist, systemd `.service` and `.timer`; for `"cron"` one line);
  `show_entry(kind, run) -> SchedulerEntry | None`; `create_entry(kind, executable, store_folder, time, run, home,
  environ, uid) -> SchedulerEntry`; `remove_entry(kind, run, home, environ, uid) -> bool`. `run: Callable[[list[str]],
  subprocess.CompletedProcess]` is the only path to a real scheduler; `uid: int | None` is the number of `gui/<uid>`
  for `launchctl`, which the caller gives, because `os.getuid()` does not exist on Windows; `environ` gives
  `XDG_CONFIG_HOME`; `SchedulerFailed` (stop error `scheduler_failed`, values `program`, the scheduler program, and
  `exit_code`; exit 1): `create_entry` and `remove_entry` raise it when `run` gives a non-zero result (ruled
  2026-11-20).

- [ ] **Step 1: Write the failing tests** (a fake `run` records each argument list; no test touches a scheduler):

```python
def test_windows_definition(self):   # XML holds <StartWhenAvailable>true</StartWhenAvailable>,
                                     # <Hidden>true</Hidden>, a daily trigger at 12:00, the command and
                                     # "ingest --store <store>"; <Hidden> hides the task in the Task
                                     # Scheduler window only, not a console window
def test_launchd_definition(self):   # Label ai-effort-ledger-ingest, StartCalendarInterval Hour 12 Minute 0
def test_systemd_definition(self):   # OnCalendar=*-*-* 12:00:00 and Persistent=true
def test_cron_is_one_line_to_show(self):   # "0 12 * * * <exe> ingest --store <store>"
def test_definitions_keep_special_characters(self):   # store "C:\Users\Jane Doe\Città 100%": the XML quotes
                                                       # and escapes the arguments, the systemd line quotes
                                                       # and doubles "%", the cron line quotes and escapes
                                                       # "%", the plist holds each argument as its own string
def test_create_replaces_existing_entry(self):    # Windows: schtasks /Create ... /F
def test_remove_without_entry_returns_false(self):
def test_cron_create_changes_nothing(self):   # create_entry("cron", ...) calls no run and writes no file
def test_launchd_create_uses_given_uid(self):   # uid 501 -> "launchctl bootstrap gui/501 <plist>"
def test_systemd_folder_follows_xdg_config_home(self):   # XDG_CONFIG_HOME=X -> X/systemd/user/<name>.timer
def test_time_must_be_hh_mm(self):   # "25:00" -> ValueError
def test_scheduler_kind(self):        # Windows -> "windows"; macOS -> "launchd"; Linux with systemctl
                                      # -> "systemd"; Linux without -> "cron"
def test_show_entry_reads_the_entry(self):   # /Query /XML -> the entry with its arguments and time
def test_show_entry_of_cron_is_none(self):   # the table of cron is shared: the ledger holds no entry there
def test_failed_scheduler_program_raises(self):   # run gives code 1 -> SchedulerFailed("schtasks", 1)
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the functions**: Windows `schtasks /Query /TN <name> /XML`, `/Create /TN <name> /XML <file>
  /F`, `/Delete /TN <name> /F`; macOS `~/Library/LaunchAgents/<name>.plist` with `launchctl bootstrap gui/<uid>` and
  `bootout`; Linux `$XDG_CONFIG_HOME/systemd/user/<name>.{service,timer}`, `~/.config` when the variable is not
  set, with `systemctl --user daemon-reload` and `enable --now` / `disable --now`.
- [ ] **Step 4: Run and see it pass**, then the full suite. Task 44 checks on the owner's Windows machine whether a
  console window shows when the entry starts; if it shows, flag the divergence with "without a visible window where
  the scheduler allows it" (`ingestion.md` › Frequency).
- [ ] **Step 5: Checkpoint.**

### Task 9: `repository` — `.git`, remotes, and repository identity

**Spec:** `ingestion.md` › Repository identity; ADR 0004, ADR 0018.

**Files:**
- Create: `src/ai_effort_ledger/repository/__init__.py`, `discovery.py`; `tests/test_repository.py`

**Interfaces:**
- Produces: `RepositoryIdentity(hint: str, basis: str)` (`basis` `"observed"` or `"inferred"`);
  `normalize_remote(url: str) -> str | None` (`None` for a local folder or `file://`);
  `find_git(folder: Path, home: Path) -> tuple[Path, Path] | None` (git folder, common git directory);
  `resolve_folder(cwd: str, system: str, home: Path, preferred_remotes: Sequence[str], root_commits:
  RootCommits) -> tuple[RepositoryIdentity | None, list[dict]]`; `RootCommits` (the content of `repositories.json`:
  `load(path: Path)`, `save(path: Path)`, `get(common_dir: str) -> str | None`, `put(common_dir: str, commit: str)`).

- [ ] **Step 1: Write the failing tests** (repositories built by hand in temporary folders):

```python
def test_normalize_remote(self):
    n = repository.normalize_remote
    self.assertEqual(n("https://user:secret@Example.org:8443/Team/App.git/"), "example.org/team/app")  # "/" first
    self.assertEqual(n("https://example.org/team/App/"), "example.org/team/app")
    self.assertEqual(n("git@example.org:Team/App.git"), "example.org/team/app")
    self.assertEqual(n("ssh://git@example.org:22/team/app"), "example.org/team/app")
    self.assertIsNone(n("file:///srv/app"))
    self.assertIsNone(n(r"C:\repos\app"))
    self.assertIsNone(n("/srv/git/app"))
def test_preferred_remote_wins(self):          # ["upstream", "origin"] with both -> upstream
def test_first_remote_by_name_otherwise(self):
def test_local_remote_is_skipped(self):        # next remote
def test_worktree_file_and_commondir(self):    # ".git" file "gitdir: ..." -> common dir through commondir
def test_search_stops_at_home(self):           # repository at home -> no identity for a folder inside it
def test_search_stops_at_the_drive_root(self):  # home at the root of the drive of the temporary folder:
                                                # a folder below it with no repository -> no identity
                                                # (ingestion.md › Repository identity)
def test_missing_folder_is_inferred(self):     # cwd gone -> nearest existing parent, basis "inferred"
def test_foreign_path_is_not_resolved(self):   # "/home/vm/app" with system "Windows" -> None, no warning
def test_config_include_is_not_read(self):     # [include] path=... gives no remote
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `discovery.py`**: read `config` with a small reader of `[remote "<name>"]` sections and their
  `url`; never run git. The search also stops at the root of a drive.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 10: `repository` — the root commit from the object store

**Spec:** `ingestion.md` › Repository identity (root commit, pack files, shallow clone).

**Files:**
- Create: `src/ai_effort_ledger/repository/objects.py`; Modify: `discovery.py`, `tests/test_repository.py`,
  `tests/support.py`
  (builders `write_loose_object` and `write_pack` with whole objects, `OFS_DELTA`, and `REF_DELTA`)

**Interfaces:**
- Produces: `root_commit(common_dir: Path) -> str | None` (`None` for a shallow clone); `resolve_folder` of Task 9
  uses it, keeps it in `RootCommits`, and returns the warning `{"code": "shallow_clone", "values": {"folder": ...}}`
  for a shallow clone.

- [ ] **Step 1: Write the failing tests**:

```python
def test_root_commit_from_loose_objects(self):  # HEAD -> refs/heads/main -> 3 commits -> first commit
def test_head_through_packed_refs(self):
def test_root_commit_in_pack(self):             # whole commit objects in a version 2 pack and index
def test_ofs_delta_commit(self):
def test_ref_delta_commit(self):
def test_first_parent_is_followed(self):        # a merge commit: the second parent is ignored
def test_shallow_clone_gives_warning(self):     # "shallow" file -> None and code "shallow_clone"
def test_identity_from_root_commit(self):       # no remote, or only local remotes -> hint "root-commit:<hash>"
def test_root_commit_is_kept(self):             # a second resolve reads no object (RootCommits holds it)
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `objects.py`** with `zlib`: loose objects, pack index version 2, object types 1 (commit),
  6 (`OFS_DELTA`), 7 (`REF_DELTA`), and delta application (copy and insert instructions). The reader covers the
  `files` reference backend and object names of 20 bytes (SHA-1); a repository outside that scope leaves no
  root-commit identity and the ledger warns, as for a shallow clone (ruled 2026-11-20).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 11: `language` — texts by code

**Spec:** `command-line.md` › JSON documents (codes), › Reports (Italian); `GLOSSARY.md` (`_Italian_` lines).

**Files:**
- Create: `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Produces: `LANGUAGES = ("en", "it")`; `WARNING_CODES: frozenset[str]` (the 23 warning codes of the table);
  `CONFIGURATION_ERROR_CODES = frozenset({"identity_rule_conflict", "category_rule_conflict",
  "project_name_conflict"})`; `STOP_CODES: frozenset[str]` (the codes of stop errors, D10, with `lock_unavailable`
  of Task 7 and `scheduler_failed` of Task 8, which is also a warning code with the same texts; each later task
  that adds a stop error adds its code and texts here); `message(code: str, values: Mapping[str, object], language:
  str) -> str`; `label(key: str, language: str) -> str` (titles, states, column names).

- [ ] **Step 1: Write the failing tests**:

```python
def test_every_code_has_both_texts(self):
def test_both_texts_name_the_same_values(self):       # same {placeholders} in "en" and "it"
def test_codes_are_the_table_of_the_spec(self):   # the 23 warning codes and the 3 configuration-error
                                                  # codes, exactly
def test_italian_states_use_glossary_terms(self):     # label("measured_day", "it") is the _Italian_ of
                                                       # "Measured day" in GLOSSARY.md
def test_values_are_not_translated(self):             # message keeps a project name as given
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the texts**: short sentences; the Italian text uses the `_Italian_` term of each glossary term.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.** Gate G6: ask the owner whether to push the branch.

## Milestone 2 — `configuration`, `store`, `adapters`

### Task 12: `configuration` — reading the machine and person configuration

**Spec:** `configuration.md` › Layers, › Order, › Format, › Matching (patterns); `architecture.md` › Files of a
machine; ADR 0017.

**Files:**
- Create: `src/ai_effort_ledger/configuration/__init__.py`, `values.py`, `machine.py`, `person.py`;
  `tests/test_configuration.py`; Modify: `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Produces: `parse_duration(text: str, clock: bool = False) -> int` (`"1h30min"` → 5400; with `clock`, also `H:MM`);
  `pattern_matches(pattern: str, text: str) -> bool` (`*` stands for any text, with regard to case);
  `MachineConfiguration(machine: str, installation: str | None, salt: str | None, store: str | None, native_logs:
  dict[str, list[str]])`; `read_machine_configuration(folder: Path) -> MachineConfiguration | None`;
  `TimeZoneEntry(zone: str, start: datetime, line: int)`; `DayStartEntry(hour: time, start: date, line: int)`;
  `ProjectName(id: str, name: str)`; `WorkItemName(project: str, id: str, name: str)`; `IdentityRule(project: str,
  repository: str | None, folder: str | None, branch: str | None, first: date | None, last: date | None, line: int)`;
  (`start` is the `from` key, `first` and `last` the `from` and `to` of an identity rule, because `from` is a
  Python keyword);
  `CategoryRule(tool: str, category: str, line: int)`; `PersonConfiguration(time_zones, day_starts, projects,
  work_items, identity_rules, category_rules, preferred_remotes: list[str], settle_time: int, report: dict[str,
  object])`; `read_person_configuration(store_folder: Path) -> PersonConfiguration`; `ReportParameters` (frozen:
  `idle_gap=600`, `minimum_attention=60`, `stale_limit=14400`, `headless_prompts=False`,
  `timesheet_granularity=900`, `language="en"`); `resolve_parameters(options: Mapping[str, object], person:
  PersonConfiguration) -> tuple[ReportParameters, dict[str, str]]` (name → layer `"option"`, `"person"`,
  `"default"`); `ConfigurationUnreadable` (stop error `configuration_unreadable`, values `path` and `line`, exit 1);
  `SetupRequired` (stop error `setup_required`, exit 1).

- [ ] **Step 1: Write the failing tests**:

```python
def test_duration_formats(self):
    p = configuration.parse_duration
    self.assertEqual((p("4h"), p("10min"), p("1h30min"), p("90s")), (14400, 600, 5400, 90))
    self.assertEqual(p("1:30", clock=True), 5400)
    with self.assertRaises(ValueError):
        p("4 hours")
def test_dated_values_as_toml_values_or_strings(self):   # D5: both forms give the same entries
def test_defaults(self):          # preferred_remotes ["origin"], settle_time 14400, ReportParameters()
def test_report_table_overrides_defaults(self):          # [report] idle_gap = "5min"
def test_option_overrides_person(self):                  # layers "option", "person", "default"
def test_later_phase_keys_are_accepted(self):            # [[label_key]], [[hourly_rate]], pseudonym
def test_unreadable_file_names_the_line(self):           # ConfigurationUnreadable with line 3
def test_entry_line_is_its_header_line(self):            # [[day_start]] at lines 4 and 9 -> line 4, line 9
def test_valid_toml_with_wrong_value_is_unreadable_with_line(self):   # zone "Europe/Nowhere"
def test_machine_configuration_reads_back_equal(self):       # native_logs with Windows paths
def test_pattern_matches(self):   # "mcp__*" matches "mcp__a__b"; "Edit" does not match "edit"
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the reader** with `tomllib`; a file that `tomllib` cannot read raises
  `ConfigurationUnreadable` with the line of the fault: the `lineno` attribute of `TOMLDecodeError` from
  Python 3.14, before that the
  number of `at line` in its message — `re.search(r"at line (\d+)", text)`, 1 when the pattern is absent,
  because the parenthetical of the message ends with the column (the workflow runs this test on 3.11);
  the ledger never uses part of a file. `tomllib` gives no line of an entry: the reader finds the lines that start,
  after spaces, with `[[<name>]]`, and gives the n-th entry of a list the line of the n-th such header; an array
  written inline gives each of its entries the line of its key.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 13: `configuration` — writes

**Spec:** `configuration.md` › Writes; `command-line.md` › Configuration entries; `ingestion.md` › Store
(installation identifier).

**Files:**
- Create: `src/ai_effort_ledger/configuration/writes.py`; Modify: `__init__.py`, `machine.py`,
  `tests/test_configuration.py`, `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Consumes: `StoreLock` (Task 7); `new_salt`, `salted_hash` (Task 6).
- Produces: `ENTRY_KEYS: dict[str, tuple[str, ...]]` (`"time_zone": ("zone", "from")`, `"day_start": ("hour",
  "from")`, `"project": ("id", "name")`, `"work_item": ("project", "id", "name")`, `"identity_rule": ("project",
  "repository", "folder", "branch", "from", "to")`, `"category_rule": ("tool", "category")`);
  `basic_string(value: str) -> str`; `append_entry(store_folder: Path, lock_path: Path, entry: str, values:
  Mapping[str, str]) -> dict[str, str]`; `WrongValue` (stop error `wrong_value`, values `key` and `value`, exit 2);
  `create_person_configuration(store_folder: Path, zone: str | None) -> list[dict[str, str]]`;
  `write_machine_configuration(folder: Path, value: MachineConfiguration) -> None`;
  `refresh_machine(value: MachineConfiguration | None, installation: str | None, new_id: Callable[[], str]) ->
  tuple[MachineConfiguration, bool]` (a machine identifier from `new_id`, with a new salt, when there is none or when
  the salted hash differs; `True` when changed; `setup` and `cli` pass their `new_uid`, so that a test knows the
  identifier).

- [ ] **Step 1: Write the failing tests**:

```python
def test_append_writes_basic_strings_at_end(self):   # comments and layout of the file stay byte for byte
def test_value_cannot_add_an_entry(self):            # name 'a"\n[[project]]\nid = "x' -> one entry, exact text
def test_append_keeps_non_ascii_and_backslashes(self):   # folder r"D:\Work\Città Example" reads back equal
def test_wrong_values_stop_with_exit_2(self):        # zone "Mars/Base", hour "25:00", category "cooking",
                                                     # time-zone "from" "2026-12-01" (needs RFC 3339 instant)
def test_failed_read_restores_content(self):         # a reader that fails after the append -> old bytes back
def test_create_person_configuration(self):
    # zone "Europe/Rome" -> [[time_zone]] from 1970-01-01T00:00:00Z and [[day_start]] 00:00 from 1970-01-01
def test_create_without_zone_writes_no_time_zone(self):
def test_machine_configuration_written_whole(self):
def test_new_machine_identifier_when_installation_changes(self):
def test_no_check_when_system_gives_no_identifier(self):   # installation None -> machine kept
def test_category_constant_equals_events(self):   # the copied constant equals
                                                  # events.FIXED_VALUES["tool_category"]; the test imports
                                                  # both modules, the package does not
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `writes.py`**: validate each value first (a time zone opens with `zoneinfo.ZoneInfo`, `HH:MM`,
  a tool category of `FIXED_VALUES` — copied as a constant, because `configuration` does not depend on `events`, a
  duration, an RFC 3339 instant, or a day `YYYY-MM-DD`); take the lock; append; read the whole file again; on a
  failed read write the old bytes back and raise. The command line normalizes `--repository`, and turns `today` and
  `yesterday` into a day `YYYY-MM-DD` with `LocalDays.parse_day` (Task 27), before it calls `append_entry` (`cli`
  depends on `repository` and `days`).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 14: `store` — segments, store metadata, frozen report files

**Spec:** `ingestion.md` › Store; `architecture.md` › Concurrency; `event-schema.md` › Encoding.

**Files:**
- Create: `src/ai_effort_ledger/store/__init__.py`, `segments.py`, `files.py`; `tests/test_store.py`; Modify:
  `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Consumes: `encode_event`, `decode_line`, `format_instant` (Task 4).
- Produces: `SegmentLine(segment: str, number: int, offset: int, data: bytes)` (`segment` is the path text
  `segments/<machine>/<YYYY-MM>.jsonl`, `number` from 1); `segment_names(store_folder: Path) -> list[str]` (sorted as
  text); `read_lines(store_folder: Path, segment: str, offset: int = 0, first_number: int = 1) ->
  Iterator[SegmentLine]` (`first_number` is the number of the line at `offset`, so that a read that resumes an
  earlier read gives the numbers of the segment; a last line without
  `\n` is not given); `append_events(store_folder: Path, machine: str, events: Sequence[Event], now: datetime) ->
  list[SegmentLine]` (sets `ingested_at` to `now`; segment of the UTC month of `now`; one `write` and one `flush`
  for each line, `architecture.md` › Concurrency, then one `os.fsync` for the whole batch); `read_label`,
  `write_label(store_folder, machine, label)`;
  `write_frozen(store_folder, machine, frozen_id, document)`, `list_frozen(store_folder) -> list[tuple[str, str,
  dict]]`, `remove_frozen(store_folder, machine, frozen_id, own_machine)`; `FrozenOtherMachine` (stop error
  `frozen_other_machine`, values `id`, `machine`, exit 1); `TargetNotFound` (stop error `target_not_found`, values
  `target`, exit 1).

- [ ] **Step 1: Write the failing tests**:

```python
def test_append_sets_ingested_at_and_month(self):   # now 2026-11-30T23:30Z -> segments/<m>/2026-11.jsonl
def test_each_line_ends_with_line_break(self):
def test_half_written_last_line_is_ignored(self):   # no line, no warning
def test_append_cuts_own_torn_last_line(self):      # D14: segment ends without \n -> cut, then append
def test_broken_line_keeps_its_number(self):        # decode_line(...).state == "broken" at number 2
def test_segment_names_sort_as_text(self):
def test_label_with_quotes_reads_back_equal(self):   # quotes, backslashes, a control character
def test_frozen_files(self):                        # frozen/<m>/<id>.json written, listed, removed
def test_frozen_remove_on_other_machine_stops(self):
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `segments.py` and `files.py`.** `append_events` cuts a last line without `\n` of the own
  segment before it writes (D14). `write_label` writes the label as a TOML basic string, with the escapes of
  `configuration.md` › Writes (double quotes, backslashes, control characters) in `files.py`, because `store`
  depends only on `events` and `platform` (`architecture.md` › Modules).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 15: `store` — purges

**Spec:** `event-schema.md` › Keys and invariants (purges); `ingestion.md` › Store; ADR 0008, ADR 0015.

**Files:**
- Create: `src/ai_effort_ledger/store/purges.py`; Modify: `__init__.py`, `tests/test_store.py`

**Interfaces:**
- Consumes: `EventKey`, `event_key`, `version_key` (Tasks 4, 5); `LockUnavailable` (Task 7).
- Produces: `PurgeSet.from_events(purges: Iterable[Event]) -> PurgeSet`; `PurgeSet.blocks(event: Event) -> bool` (a
  copy passes only when every purge that lists its key has a `corrected_version` and the copy's `writer_version` is
  that version or newer); `PurgeSet.sessions_to_read(own_version: str, applied: set[str]) -> list[tuple[str, str]]`;
  `rewrite_segment(store_folder: Path, segment: str, keep: Callable[[SegmentLine], bool], limit_seconds: float =
  600.0) -> int` (lines removed; a new file in the same folder, then `os.replace`; a `PermissionError` retries every
  0.5 s until the limit, then `LockUnavailable`).

- [ ] **Step 1: Write the failing tests**:

```python
def test_purge_without_corrected_version_blocks_for_good(self):
def test_corrected_version_lets_newer_copies_pass(self):
    # corrected "0.2.0": writer "0.1.0" blocked, "0.2.0" passes, "0.2.0.dev0" blocked, "0.3.0" passes
def test_two_purges_of_one_key(self):        # one without corrected version -> blocked at any version
def test_sessions_to_read(self):             # purge with corrected "0.2.0", own version "0.2.0" -> its sessions
def test_older_version_leaves_the_purge(self):   # own version "0.1.0" -> no session
def test_rewrite_removes_lines_in_one_step(self):
def test_rewrite_retries_while_file_is_open(self):   # Windows only (skipUnless)
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `purges.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 16: Survey of native logs (gate G2)

**Spec:** `claude-code-adapter.md` › To be confirmed (interruptions; subagent link without `agentId` and nested
subagents; input keys of `MultiEdit` and `NotebookEdit`); `ingestion.md` › To be confirmed (orchestrated sessions);
CLAUDE.md › Privacy.

**Files:**
- Create: `prototype/survey.py` (throw-away, not part of the package); `docs/research/native-log-survey-2026-11.md`;
  `tests/fixtures/claude_code/` (Step 4, one fixture by hand for each new record form)
- Modify: `docs/spec/claude-code-adapter.md`, `docs/spec/ingestion.md` (Step 3, the sentence of each ruling)

The script reads a copy of the native logs (`--snapshot <folder>`, the layout of `prototype/validate.py`) and writes to
`prototype/out/` only: counts of record types by `version`; key paths with the JSON type of their value; for user
records, whether the text starts with `[Request interrupted by user` (a count, never the text); the values of
`toolDenialKind`; for the tool results of `Agent` and `Task`, the JSON type of `toolUseResult` and whether it holds
`agentId`; subagent files whose records name a subagent as parent; the key names of the input of `MultiEdit` and
`NotebookEdit`. It prints no value of a free-text field. A key made of letters, digits, and `_`, starting with a
letter or `_`, is written as it is; every other key is written as `<key>`, because such a key is data, such as a
file path.

- [ ] **Step 1: Write the script** and run it on an invented folder made by hand: the output holds no text of the
  invented records (a marker word in the input never appears in `prototype/out/`, also not when it is a key).
- [ ] **Step 2: Gate G2.** Ask the owner to make the copy of the native logs and to run
  `python -I prototype/survey.py --snapshot <folder>`, or to allow the run.
- [ ] **Step 3: Write the research note** with ratios only, and give the findings to the owner in a ruling panel
  for each `To be confirmed` item that a finding closes; before each panel, explain the item in plain English with
  a table of its cases × options. Each ruling becomes a sentence of the spec, and the item is
  deleted. An item that the survey cannot close comes to the owner with two choices: rule it now, or give it
  the trigger "with a real sample", without a phase.
- [ ] **Step 4: Write a fixture** in `tests/fixtures/claude_code/` for each new record form that the rulings add, by
  hand, with invented text; Tasks 18–22 test it.
- [ ] **Step 5: Checkpoint.**

### Task 17: `adapters` — interface, folders of native logs, reading of files

**Spec:** `claude-code-adapter.md` › Native logs, › Session fields (entrypoint); `ingestion.md` › Adapters;
`architecture.md` › Modules (`adapters`).

**Files:**
- Create: `src/ai_effort_ledger/adapters/__init__.py`, `claude_code/__init__.py`, `discovery.py`, `reading.py`,
  `tables.py`; `tests/test_adapter_claude_code.py`; `tests/fixtures/claude_code/` (one fixture for each row of
  the tables; Task 16 may have written some);
  Modify: `tests/support.py` (builders of invented records: `prompt_record`, `output_record`, `tool_use`,
  `tool_result_record`, `queue_record`, `write_session(folder, session_id, records, subagents, cwd)`,
  `copy_fixture(name, folder, cwd)`)

**Interfaces:**
- Produces in `adapters`: `SessionFiles(tool: str, session_id: str, folder: Path, main: Path | None, subagents:
  dict[str, Path])`; `ReadContext(machine: str, now: datetime, settle_time: int, native_id_owner: Callable[[str, str],
  tuple[str, str] | None])`; `ReadResult(events: list[Event], held_back: set[tuple[str, str]], warnings: list[dict],
  unknown_tools: set[str])`; `Retention(setting: str, days: int | None)` (`None` is no age limit);
  `Adapter` (protocol: `source: str`, `tools: tuple[str, ...]`, `default_folders(environ, home, system) -> dict[str,
  list[PurePath]]`, `retention(tool, environ, home, system, native_logs: Mapping[str, Sequence[str]], project_folders:
  Iterable[str]) -> Retention`, `sessions(tool, folder) -> list[SessionFiles]`, `read_sessions(sessions, context) ->
  ReadResult`); `ADAPTERS: tuple[Adapter, ...]`.
  The adapter leaves `ingested_at`, `writer_version`, `repo_hint`, and `repo_basis` to ingestion.
- Produces in `claude_code`: `SOURCE = "claude-code-jsonl"`; `ENTRYPOINTS: dict[str, str]`; `read_file(path: Path,
  settled: bool) -> tuple[list[tuple[int, dict]], bool, list[dict]]` (records with their line number, whether a last
  line without `\n` stayed unread, warnings; with `settled` true, that line is read like any other line);
  `ClaudeCodeAdapter` with `source`, `tools`, `default_folders`, `sessions`, and `read_sessions`, which in this task
  reads the files of each session with `read_file` (`settled` when no file of the session changed for
  `context.settle_time`) and gives their warnings and no event; Task 18 adds `map_session` to `read_sessions`,
  Task 21 adds `deduplicate` before it and `link_subagents` after it, Task 22 adds `complete_events`, Task 23 adds
  `assign_forks`, and Task 24 adds `retention` and `managed_file`; `ADAPTERS = (ClaudeCodeAdapter(),)`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_default_folders(self):
    # CLAUDE_CONFIG_DIR=X -> {"claude-code": [X/projects]}; else <home>/.claude/projects;
    # Linux: no folder for "claude-desktop"; Windows: <APPDATA>/Claude/local-agent-mode-sessions for
    # "claude-desktop"; the candidates as pure
    # paths, built also when they do not exist; the search of the sessions skips a folder that is not there
def test_sessions_of_a_folder(self):        # <f>/<sid>.jsonl and <f>/<sid>/subagents/agent-<a>.jsonl
def test_desktop_folders_are_searched(self):   # every .claude/projects/ below the recorded folder
def test_desktop_folder_on_macos(self):
def test_invalid_json_line_warns(self):     # code "invalid_record", values file and line, no event
def test_invalid_utf8_line_is_invalid_record(self):      # Review Focus 5
def test_partial_last_line_is_not_read_without_warning(self):  # Review Focus 1; settled False
def test_unknown_record_type_warns_once_per_type_and_version(self):
def test_read_sessions_gives_warnings_of_files(self):   # an invalid line -> invalid_record, no event
def test_entrypoints(self):
    # cli, local-agent -> interactive; sdk-cli, sdk-ts, sdk-py -> headless;
    # "x-new" -> unknown with "unknown_entrypoint"; no entrypoint -> unknown, no warning
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the files.** `read_file` reads bytes line by line and decodes each line on its own.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 18: `adapters` — records of the agent to events

**Spec:** `claude-code-adapter.md` › Records and events (the rows of `assistant`, tool use, and tool results), ›
Tokens, › Requests and price factors, › Tool categories; `event-schema.md` › Keys and invariants (one response on
several lines, the
identifier of an event from a record without an identifier); ADR 0024.

**Files:**
- Create: `src/ai_effort_ledger/adapters/claude_code/mapping.py`; Modify: `tables.py`, `__init__.py`,
  `tests/test_adapter_claude_code.py`;
  `tests/fixtures/claude_code/` (one file for each row of this task)

**Interfaces:**
- Consumes: `read_file`, `ENTRYPOINTS` (Task 17); `parse_instant`, `format_instant` (Task 4).
- Produces: `map_session(records: Sequence[SessionRecord], tool: str, machine: str) -> tuple[list[Event],
  list[dict]]` (every event gets `tool`, and the `invocation` of the `entrypoint` of its own record, because a
  resumed session can change it: `event-schema.md` › Fields) where `SessionRecord(agent: str, file_order: int,
  line: int, record: dict)` (the rows of the agent;
  Task 19 adds the others); `event_identifiers(records: Sequence[SessionRecord]) -> dict[tuple[int, int], str]` (D3,
  `event-schema.md` › Keys and invariants); `TOOL_CATEGORIES: dict[str, str]` in `tables.py` (the table of › Tool
  categories, 26 names; an unknown name gives `other` and goes to `ReadResult.unknown_tools`), which `tool_call`
  needs; `read_sessions` turns the records of each session into `SessionRecord`s and calls `map_session`.

- [ ] **Step 1: Write the failing tests**, one for each row, from its fixture:

```python
def test_response_on_three_lines_is_one_agent_output(self):
    # tokens: largest value of each category; timestamp of the last line; native_id message.id
def test_cache_write_5m_without_cache_creation(self):    # cache_creation_input_tokens 100, no
                                                         # cache_creation object -> cache_write_5m 100
def test_absent_token_key_is_absent(self):
def test_requests_and_price_factors(self):  # web_search 2 kept, web_fetch 0 not written; speed of last line
def test_model_starting_with_angle_bracket_gives_no_event(self):
def test_tool_use_gives_tool_call(self):    # native_id "tool_call:<id>", call_id
def test_categories(self):                  # each row of the table; "mcp__x__y" -> "other"
def test_server_and_mcp_tool_use(self):
def test_tool_result_row(self):
def test_position_counts_across_files(self):    # main file first, then subagents by name, then lines
def test_event_identifier_text(self):       # "queued_message:2026-11-19T08:30:00.125Z:0", then ":1"
def test_invocation_of_each_record(self):   # resumed session: entrypoint cli, then sdk-cli -> interactive,
                                            # then headless
def test_tool_of_the_session_files(self):   # tool "claude-desktop" on every event
def test_read_sessions_maps_each_session(self):   # two sessions -> the events of both, each with its session_id
def test_no_text_in_agent_events(self):     # the marker word of each fixture of this task is in no event
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `mapping.py`.** The adapter reads text only for the tests of the table and drops it.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 19: `adapters` — records of the person and the system to events

**Spec:** `claude-code-adapter.md` › Records and events (the rows of prompts, permissions, questions, queued messages,
and notifications; the record types without an event); `event-schema.md` › Keys and invariants (prompts);
`product.md` › Phase 1 (the adapter writes no session title and no provider hint).

**Files:**
- Modify: `src/ai_effort_ledger/adapters/claude_code/mapping.py`, `tests/test_adapter_claude_code.py`;
  `tests/fixtures/claude_code/` (one file for each row of this task, one for the record types that give no event,
  one for a version without `origin`)

**Interfaces:**
- Consumes: `map_session`, `event_identifiers` (Task 18).
- Produces: the other rows of `map_session`.

- [ ] **Step 1: Write the failing tests**, one for each row, from its fixture:

```python
def test_question_and_approval_requests(self):  # decision_request at tool call, decision actor human at result
def test_permission_of_the_person(self):    # user_temporary -> decision_request + decision
def test_permission_of_a_rule_gives_no_event(self):          # source "config"
def test_unknown_permission_source_warns(self):
def test_permission_with_two_tool_results_warns(self):       # "multi_tool_result_permission"
def test_prompt_of_interactive_session(self):
def test_prompt_of_headless_session_is_scripted_notification(self):
def test_interruption_gives_no_prompt(self):
def test_notification_coordinator_peer(self):
def test_unknown_origin_kind_warns(self):
def test_queued_message(self):              # event_uid "queued_message:<timestamp>:0" (D3)
def test_queue_content_starting_with_angle_bracket_gives_no_event(self):
def test_is_meta_gives_no_event(self):
def test_unknown_structure_of_known_type_is_unknown_record_type(self):
def test_record_types_without_event(self):  # the 19 types of the list: no event, no warning
def test_prompt_without_origin(self):       # tags <task-notification -> notification; others no event
def test_session_title_and_provider_hint_are_not_written(self):   # product.md › Phase 1
def test_no_text_in_person_events(self):    # the marker word of every fixture is in no event
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Extend `mapping.py`.** The adapter reads text only for the tests of the table and drops it.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 20: `adapters` — size counters (gate G4)

**Spec:** `claude-code-adapter.md` › Tool categories, › Size counters; `event-schema.md` › Keys and invariants (size
counters); ADR 0012, ADR 0016.

**Gate G4, ruled 2026-11-19** (`event-schema.md` › Keys and invariants): an empty text has no lines.

**Files:**
- Create: `src/ai_effort_ledger/adapters/claude_code/size.py`; Modify: `mapping.py`,
  `tests/test_adapter_claude_code.py`

**Interfaces:**
- Consumes: `TOOL_CATEGORIES` (Task 18).
- Produces: `count_lines(text: str) -> int`;
  `file_extension(path: str) -> str | None`; `size_counters(tool_name: str, tool_input: dict, result_record: dict |
  None, is_error: bool) -> dict[str, object]` (`lines_added`, `lines_removed`, `file_ext`, `size_basis`; empty dict
  for no counters).

- [ ] **Step 1: Write the failing tests**:

```python
def test_count_lines(self):
    self.assertEqual((size.count_lines("a\nb"), size.count_lines("a\nb\n")), (2, 2))
    self.assertEqual(size.count_lines(""), 0)
def test_insertion_counts_no_removed_line(self):     # Edit with empty old_string -> lines_removed 0
def test_patch_counts(self):                # structuredPatch hunks: "+" and "-" lines, size_basis "patch"
def test_patch_without_hunks_falls_back_to_input(self):
def test_edit_input(self):                  # new_string / old_string, size_basis "input"
def test_multiedit_sums_items(self):
def test_write_create_has_zero_removed(self):    # toolUseResult type "create"
def test_write_update_without_patch_has_removed_absent(self):
def test_notebookedit(self):                # new_source; removed absent; notebook_path
def test_error_result_has_no_counters(self):
def test_call_without_result_has_no_counters(self):
def test_file_extension(self):
    e = size.file_extension
    self.assertEqual((e("a.PY"), e("a.tar.gz"), e(".bashrc"), e("Makefile")), ("py", "gz", None, None))
def test_no_path_in_events(self):           # file_path of the fixture is in no event
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `size.py`** and call it from `mapping.py` when the tool result is known.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 21: `adapters` — subagents, copies of one record

**Spec:** `claude-code-adapter.md` › Session fields; `event-schema.md` › Keys and invariants (identity, copies).

**Files:**
- Create: `src/ai_effort_ledger/adapters/claude_code/subagents.py`; Modify: `mapping.py`, `__init__.py`,
  `tests/test_adapter_claude_code.py`

**Interfaces:**
- Produces: `link_subagents(events: list[Event], records: Sequence[SessionRecord]) -> None` (sets `parent_agent_id`
  and `subagent_mode`); `deduplicate(records: Sequence[SessionRecord]) -> tuple[list[SessionRecord], list[dict]]`
  (the copy in the file of the agent that the record names; `record_copies_differ` when copies differ in another
  field; its values name the fields only, never their content); `read_sessions` calls `deduplicate` before
  `map_session` and `link_subagents` after it.

- [ ] **Step 1: Write the failing tests**:

```python
def test_main_agent_id_is_session(self):
def test_subagent_id_from_file_name(self):
def test_link_from_agent_result(self):      # toolUseResult.agentId -> parent_agent_id = agent of the call
def test_background_mode(self):             # isAsync true, or input run_in_background true -> "background"
def test_parent_input_is_notification(self):    # input_origin "parent"
def test_copy_in_two_files_gives_one_event(self):
def test_differing_copies_warn(self):
def test_copies_differ_names_fields_only(self):  # the invented marker word is in no warning value
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `subagents.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 22: `adapters` — complete events and held-back events

**Spec:** `ingestion.md` › Adapters; `claude-code-adapter.md` › Complete events; ADR 0020.

**Files:**
- Create: `src/ai_effort_ledger/adapters/claude_code/completeness.py`; Modify: `__init__.py`,
  `tests/test_adapter_claude_code.py`

**Interfaces:**
- Produces: `complete_events(events: list[Event], records: Sequence[SessionRecord], settled: bool) -> tuple[list[Event],
  bool]` (complete events, whether any event is held back); `settled` is true when no file of the session changed for
  the settle time (`now - newest mtime >= settle_time`). `read_sessions` passes the same `settled` to `read_file`; a
  session whose last line stayed unread counts as held back (`ReadResult.held_back`), so that the next ingestion reads
  it again although its files did not change (`claude-code-adapter.md` › Native logs).

- [ ] **Step 1: Write the failing tests**:

```python
def test_last_response_is_held_back(self):      # no later record of the same agent
def test_response_complete_after_later_record(self):
def test_tool_call_waits_for_its_result(self):
def test_provider_tool_complete_with_response(self):
def test_subagent_waits_for_its_link(self):     # no Agent result yet -> all events of the subagent held back
def test_settled_session_is_complete(self):     # call without result stored without counters;
                                                # subagent without link has no subagent_mode
def test_same_store_at_any_hour(self):          # read at t1 then at t2 > t1 -> union of stored events equal
def test_unread_last_line_holds_the_session_back(self):   # Review Focus 1: not settled -> held back;
                                                          # settled -> read, its event stored
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `completeness.py`** and use it in `read_sessions`.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 23: `adapters` — forked sessions

**Spec:** `claude-code-adapter.md` › Forks; `event-schema.md` › Keys and invariants (forks); D7.

**Files:**
- Create: `src/ai_effort_ledger/adapters/claude_code/forks.py`; Modify: `__init__.py`,
  `tests/test_adapter_claude_code.py`

**Interfaces:**
- Produces: `assign_forks(sessions: dict[tuple[str, str], list[Event]], native_id_owner) -> list[dict]` (moves shared
  events to the original, sets `forked_from = {"session_id": ..., "instant": ...}` on the events of the fork, returns
  warnings `fork_original_unknown`); `read_sessions` calls it with `context.native_id_owner` on the sessions that
  it read.

- [ ] **Step 1: Write the failing tests**:

```python
def test_original_holds_own_records_in_shared_range(self):
def test_fork_instant_is_last_shared_record(self):
def test_both_or_neither_sort_by_identifier_and_warn(self):
def test_fork_read_alone_uses_the_index(self):   # native_id_owner names the original
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `forks.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 24: `adapters` — retention settings

**Spec:** `claude-code-adapter.md` › Retention; `ingestion.md` › Frequency; D6.

**Files:**
- Create: `src/ai_effort_ledger/adapters/claude_code/retention.py`; Modify: `__init__.py`,
  `tests/test_adapter_claude_code.py`, `tests/support.py`

**Interfaces:**
- Produces: `retention(tool: str, environ, home, system, native_logs: Mapping[str, Sequence[str]], project_folders:
  Iterable[str], managed_file: Path | None = None) -> Retention` (`native_logs`: `MachineConfiguration.native_logs`;
  the user `settings.json` is the one beside each recorded `projects/` folder of `claude-code`, with no user settings
  file when none is recorded; `project_folders`:
  the `cwd` texts that `LocalIndex.session_folders()` of Task 26 gives to the callers in `ingestion` and `setup`
  (Tasks 29 and 44), plus the `cwd` of every session the running ingestion read, also one it holds back
  (ruled 2026-11-20);
  `claude-code`: the shortest `cleanupPeriodDays` in effect, D6, default 30; `claude-desktop`: managed
  `cleanupPeriodDays` alone when managed settings set it, also when `desktopSessionCleanupPeriodDays` is 0 or
  absent; otherwise `None` while `desktopSessionCleanupPeriodDays` is 0 or absent, and, when it is set, the longer
  of the desktop setting and the `claude-code` value of the same call, which is the `cleanupPeriodDays` that pairs
  with it, because the managed file cannot join the pair (ruled 2026-11-20)); `managed_settings_path(system: str)
  -> PurePath` (the paths of Step 1), used when
  `managed_file` is `None`; `ClaudeCodeAdapter(managed_file: Path | None = None)` passes
  it on, `ADAPTERS` holds `ClaudeCodeAdapter()`, and `support.adapters_for_tests(home: Path)` gives one whose
  managed file is in the temporary home, for every test that ingests or builds a `Context` (Task 29, Task 44,
  and Tasks 48–63).

- [ ] **Step 1: The paths** (the facts and sources live in
  [claude-code-settings-2026-11.md](../research/claude-code-settings-2026-11.md)): user `settings.json` in the
  folder that holds the recorded `projects/` folder of Claude Code
  (`claude-code-adapter.md` › Retention; not `CLAUDE_CONFIG_DIR` at run time); shared project
  `<folder>/.claude/settings.json`; local project `<folder>/.claude/settings.local.json`;
  managed `C:\Program Files\ClaudeCode\managed-settings.json`, `/Library/Application
  Support/ClaudeCode/managed-settings.json`, `/etc/claude-code/managed-settings.json`. Precedence (spec order): managed,
  local project, shared project, user. `desktopSessionCleanupPeriodDays` is read from the user and managed files
  only. A folder that no longer exists is skipped; no other managed source (registry, profile, server,
  drop-in files beside the managed file) is read.
- [ ] **Step 2: Write the failing tests** with settings files in a temporary home:

```python
def test_default_claude_code(self):        # Retention("cleanupPeriodDays", 30)
def test_setting_of_the_person(self):      # 60 -> 60
def test_desktop_has_no_age_limit_by_default(self):
def test_desktop_longer_of_two(self):      # desktop 90, cleanup 30 -> 90
def test_desktop_cleanup_longer(self):    # desktop 7, cleanup 30 -> 30 (the example of the documentation)
def test_managed_cleanup_applies_alone(self):    # managed_file in the temporary folder
def test_managed_cleanup_without_desktop_setting(self):   # claude-desktop, no desktop setting, managed 14
                                                          # -> Retention("cleanupPeriodDays", 14)
def test_managed_settings_path(self):            # the three paths of Step 1 by system; no file is read
def test_shorter_local_project_value_wins(self):     # user 30, <folder>/.claude/settings.local.json 7 -> 7
def test_precedence_inside_one_folder(self):         # local 60 over shared 7 in the same folder -> 60
def test_missing_project_folder_is_skipped(self):
def test_person_settings_follow_recorded_folder(self):  # native_logs X/projects, CLAUDE_CONFIG_DIR=Y
                                                        # -> X/settings.json, never Y/settings.json
```

- [ ] **Step 3: Run and see it fail**, then write `retention.py`.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.** Gate G6: ask the owner whether to push the branch.

## Milestone 3 — `index`, `days`

### Task 25: `index` — update, chained hash, broken lines, the winning copy

**Spec:** `architecture.md` › Local index, › Report record; `event-schema.md` › Keys and invariants (merge rule);
`ingestion.md` › Store (every read ignores the copies that a purge blocks); D4.

**Files:**
- Create: `src/ai_effort_ledger/index.py`, `tests/test_index.py`; Modify: `src/ai_effort_ledger/language.py`,
  `tests/test_language.py`

**Interfaces:**
- Consumes: `segment_names`, `read_lines`, `SegmentLine` (Task 14); `PurgeSet` (Task 15); `decode_line`,
  `event_key`, `winning_copy` (Tasks 4, 5).
- Produces: `INDEX_FORMAT = 1`; `SegmentState(segment: str, size: int, chained_hash: str)`; `BrokenLine(segment: str,
  number: int)`; `LocalIndex(path: Path, limit_seconds: float = 30.0)` (opens SQLite in WAL mode with
  that busy timeout) with: `update(store_folder:
  Path) -> IndexUpdate(lines_read: int, broken: list[BrokenLine], newer: bool)`; `rebuild(store_folder: Path) ->
  None`; `segment_states() -> list[SegmentState]`; `broken_lines() -> list[BrokenLine]` and `has_newer() -> bool`
  (every broken line and every line of a newer schema version that the index holds, also those of an earlier update;
  `IndexUpdate` names only the lines of one update); `has_key(key: EventKey, purges: PurgeSet) -> bool` (False when
  every copy of the key is blocked); `counts() -> tuple[int, int]`; `IndexBusy` (stop error `index_busy`, exit 1);
  the private `_winning(rows, purges)` that every query of Task 26 uses: the winning copy among the copies that the
  purges do not block.

- [ ] **Step 1: Write the failing tests**:

```python
def test_update_reads_only_new_bytes(self):     # lines_read == number of appended lines
def test_numbers_continue_after_an_offset(self):   # a second update from the stored offset gives the next
                                                    # numbers; the number of a broken line counts from 1
def test_moved_last_line_reads_segment_again(self):   # after rewrite_segment
def test_removed_segment_removes_its_events(self):
def test_other_format_rebuilds(self):           # stored format 0 -> rebuilt
def test_two_updates_add_each_line_once(self):  # two connections, same segment
def test_chained_hash(self):
    # h0 = sha256(b"").digest(); h1 = sha256(h0 + line1).digest(); segment_states shows h_n.hex()
def test_wal_mode(self):                         # PRAGMA journal_mode == "wal"
def test_newer_schema_is_flagged(self):
def test_broken_and_newer_lines_stay_after_update(self):   # a second update reads no byte: broken_lines()
                                                           # and has_newer() still give them
def test_has_key_ignores_blocked_copy(self):    # only a blocked copy -> False
def test_index_busy_past_the_limit(self):   # a second connection holds an exclusive write transaction
                                            # past the limit (0.5 s in the test) -> IndexBusy
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `index.py`**: tables `meta(format)`, `segments(name, size, last_offset, last_hash, chained)`,
  `lines(segment, offset, number, state, newer, key, source, tool, session_id, kind, timestamp, ingested_at, day,
  start, end, cwd, event)` (`state` as `Decoded.state`: broken and left-out lines stay as rows) with
  primary key `(segment, offset)` and `INSERT OR IGNORE`; one transaction for each segment, opened with
  `BEGIN IMMEDIATE` before it reads the state of the segment, so that a later commit never writes an older size or
  chained hash. The `update` of a segment with stored lines resumes with `first_number` as their last number + 1,
  so that a `broken_line` names the line of the segment (`ingestion.md` › Store).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 26: `index` — the queries

**Spec:** `architecture.md` › Local index; `command-line.md` › Commands (`annotate`, `retract`, `entries`), › Purge;
`ingestion.md` › Store.

**Files:**
- Modify: `src/ai_effort_ledger/index.py`, `tests/test_index.py`

**Interfaces:**
- Consumes: `LocalIndex`, `_winning` (Task 25).
- Produces: on `LocalIndex` these queries; each one except `purge_events` takes the keyword-only parameter
  `purges: PurgeSet`, because every read ignores the copies that a purge blocks (`ingestion.md` › Store), and gives
  one copy for each key through `_winning`: `sessions_between(start: datetime, end: datetime, *, purges: PurgeSet)
  -> set[tuple[str, str]]` (`tool`, `session_id`); `session_events(sessions: Iterable[tuple[str, str]], *, purges:
  PurgeSet) -> list[Event]`; `confirmations_of(days: Iterable[str], *, purges: PurgeSet) -> list[Event]`;
  `intervals_between(start: datetime, end: datetime, *, purges: PurgeSet) -> list[Event]` (manual entries and
  interval annotations); `bookkeeping(*, purges: PurgeSet) -> list[Event]` (retractions, purges, session
  annotations); `native_id_owner(source: str, native_id: str, *, purges: PurgeSet) -> tuple[str, str] | None`
  (ingestion gives `functools.partial(index.native_id_owner, purges=purges)` to `ReadContext`);
  `session_folders(*, purges: PurgeSet) -> set[str]` (the `cwd` values of the stored events, D6);
  `ledger_events_between(parts: Sequence[tuple[datetime, datetime]], *, purges: PurgeSet) -> list[Event]` (events
  of the source `ledger` whose `timestamp` is in one of the parts, for `entries <day>`);
  `tools_of_session(session_id: str, *, purges: PurgeSet) -> set[str]`
  (`annotate --session` without `--tool`); `keys_written_below(version: str, source: str | None = None, *, purges:
  PurgeSet) -> list[EventKey]` (`purge --writer-version-below`); `sessions_of_keys(keys: Iterable[EventKey], *,
  purges: PurgeSet) -> set[tuple[str, str]]` (the sessions that a purge with a corrected version names);
  `ledger_event_by_uid(event_uid: str, *, purges: PurgeSet) -> Event | None` (`retract`, `timesheet retract`);
  `purge_events() -> list[Event]` (every purge, one copy for each key, without a `PurgeSet`:
  `PurgeSet.from_events(index.purge_events())` builds the `PurgeSet` of the other queries).

- [ ] **Step 1: Write the failing tests**:

```python
def test_query_gives_winning_copy(self):        # two machines hold one key: earliest ingested_at
def test_blocked_copy_never_wins(self):         # earlier copy blocked -> the later unblocked copy is given
def test_sessions_between_and_session_events(self):  # two sessions in the range, one outside; the events
                                                     # of the inside ones only
def test_session_folders(self):                 # two sessions, two cwd values -> both
def test_tools_of_session(self):                # one id in two agent tools -> both
def test_keys_written_below(self):              # writer 0.1.0 and 0.1.1, below 0.1.1 -> the first only
def test_sessions_of_keys(self):
def test_ledger_event_by_uid(self):             # unknown event_uid -> None
def test_ledger_events_between(self):           # by timestamp, not by start and end; two parts of one day
def test_purge_events_need_no_purge_set(self):  # a purge that lists a key -> purge_events() gives it
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the queries.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 27: `days` — local days

**Spec:** `metrics.md` › Days and weeks; `configuration.md` › Format (dated facts); `command-line.md` › Form (day and
instant values); ADR 0022.

**Files:**
- Create: `src/ai_effort_ledger/days.py`, `tests/test_days.py`; Modify: `tests/support.py` (calls
  `days.use_tzdata_only()` at import), `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Consumes: `TimeZoneEntry`, `DayStartEntry`, `PersonConfiguration` (Task 12).
- Produces: `use_tzdata_only() -> None` (`zoneinfo.reset_tzpath(to=[])`, then
  `zoneinfo.ZoneInfo.clear_cache()`); `tzdata_version() -> str`; `LocalDays(time_zones: Sequence[TimeZoneEntry],
  day_starts: Sequence[DayStartEntry])` (raises `DatedFactConflict`) with `local_day(instant: datetime) -> date`
  (raises `NoLocalDay`), `day_parts(day: date) -> list[tuple[datetime, datetime]]` (UTC, start included, end
  excluded; two parts when a journey to the west crosses the start of the day), `local_instant(text: str) ->
  datetime`, `parse_day(text: str, now: datetime) -> date`; `NoLocalDay` (stop error `no_local_day`, values
  `instant`, exit 1); `DatedFactConflict` (stop error `dated_fact_conflict`, values `first`, `second`, exit 1);
  `NoTimeZone` (stop error `time_zone_missing`, exit 1: `LocalDays` raises it when the time-zone history is empty).

- [ ] **Step 1: Write the failing tests** (time zone `Europe/Rome` from `1970-01-01T00:00:00Z`, day start 00:00):

```python
def test_local_day(self):              # 2026-11-10T23:30Z -> 2026-11-11
def test_day_start_hour(self):         # day start 04:00: local 02:00 of 11-11 -> 2026-11-10
def test_daylight_saving_days(self):   # 2026-03-29 lasts 23 h, 2026-10-25 lasts 25 h
def test_change_of_day_start(self):    # 00:00 -> 04:00 from 2026-12-01: 2026-11-30 lasts 28 h
def test_journey_east(self):           # Asia/Tokyo from 2026-12-01T00:00Z: 2026-12-01 starts at 2026-11-30T23:00Z
                                       # and lasts 16 h
def test_journey_west_gives_two_parts(self):
    # America/New_York from 2026-12-01T03:00Z: 2026-11-30 has [11-29T23:00Z, 11-30T23:00Z) and
    # [12-01T03:00Z, 12-01T05:00Z); 2026-12-01 has [11-30T23:00Z, 12-01T03:00Z) and [12-01T05:00Z, 12-02T05:00Z)
def test_instant_before_history_stops(self):     # NoLocalDay names the instant
def test_empty_time_zone_history_stops(self):   # LocalDays([], []) -> NoTimeZone on the first local day
def test_two_entries_with_same_start_stop(self): # DatedFactConflict names both
def test_repeated_local_time_is_first(self):     # "2026-10-25T02:30" -> 2026-10-25T00:30Z
def test_skipped_local_time_is_after_change(self):   # "2026-03-29T02:30" -> 2026-03-29T01:00Z
def test_today_and_yesterday(self):
def test_tzdata_only(self):                      # zoneinfo.TZPATH == () after use_tzdata_only()
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `days.py`.** A local day starts at the first instant whose local date and time reach the day
  start hour of that date; `day_parts` walks the transitions of the time-zone history and of the zone inside the day.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.** Gate G6: ask the owner whether to push the branch.

## Milestone 4 — `ingestion`, `selection`, `metrics`

### Task 28: `ingestion` — record of sources, sessions to read, lost events

**Spec:** `architecture.md` › Data flow (step 4), › Files of a machine (`sources.json`); `ingestion.md` › Frequency,
› Store.

**Files:**
- Create: `src/ai_effort_ledger/ingestion/__init__.py`, `state.py`; `tests/test_ingestion.py`

**Interfaces:**
- Produces: `SourcesState(folders: dict[str, str], files: dict[str, tuple[int, int]], held_back: dict[str,
  list[str]], applied_purges: list[str])` (the key of `held_back` is the agent tool, the values are its session
  identifiers) with `load(path: Path) -> SourcesState` and `save(path: Path)`;
  `sessions_to_read(state: SourcesState, found: Sequence[SessionFiles], purged: Sequence[tuple[str, str]]) ->
  list[SessionFiles]`; `lost_events(state: SourcesState, folder: str, retention: Retention, now: datetime) -> dict |
  None` (warning `lost_events`, values `folder`, `from`, `to`); `held_back_sessions(machine_folder: Path,
  store_folder: Path, system: str) -> set[tuple[str, str]]` (used by `cli`, which passes it to `select`,
  Task 31, for `held_back_events`).

- [ ] **Step 1: Write the failing tests**:

```python
def test_changed_file_selects_its_whole_session(self):   # size or mtime of one subagent file changed
def test_held_back_session_is_read_again(self):
def test_purged_session_is_read_again(self):
def test_unchanged_session_is_not_read(self):
def test_lost_events_after_long_gap(self):     # previous 2026-10-01, now 2026-11-10, retention 30 days
def test_lost_events_at_the_retention_edge(self):  # a gap of exactly 30 days -> no warning; 31 -> warning
def test_no_lost_events_without_age_limit(self):         # Retention(..., None)
def test_no_lost_events_at_first_ingestion(self):
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `state.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 29: `ingestion` — the ingestion

**Spec:** `architecture.md` › Data flow (steps 1–11); `ingestion.md` › Adapters, › Store, › Repository identity;
acceptance criteria 1 and 6.

**Files:**
- Create: `src/ai_effort_ledger/ingestion/run.py`; Modify: `__init__.py`, `tests/test_ingestion.py`,
  `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Consumes: Tasks 7, 9, 10, 12–15, 17–26, 28.
- Produces: `SourceResult(source: str, folder: str, new_events: int, sessions_held_back: int)`;
  `IngestionResult(sources: list[SourceResult], warnings: list[dict])`; `run_ingestion(machine: MachineConfiguration,
  machine_folder: Path, store_folder: Path, person: PersonConfiguration, adapters: Sequence[Adapter], now: datetime,
  home: Path, system: str, environ: Mapping[str, str], version: str | None = None) -> IngestionResult` (retention
  gets `machine.native_logs` and the `cwd` of every session this ingestion read, also one it holds back
  (ruled 2026-11-20); `version`, `writer_version()` when it is `None`, is the `writer_version` of each new
  event, the own version of `PurgeSet.sessions_to_read`, and the version of the development check);
  `DevelopmentVersion` (stop error `development_version`, exit 1), raised before the lock when `version` has a
  development mark and the `environ` parameter, never `os.environ`, does not give `AI_EFFORT_LEDGER_DEVELOPMENT` as
  `1` (a test that passes its own `environ` puts the variable in it); `remove_blocked_copies(store_folder: Path,
  machine: str, purges: PurgeSet) -> None` (step 10: `rewrite_segment` of Task 15 on each segment of the machine
  that holds a copy that `purges` blocks; Task 53 calls it too).

- [ ] **Step 1: Write the failing tests** (native logs written by `support.write_session` in a temporary home):

```python
def test_second_ingestion_adds_nothing(self):       # acceptance criterion 1
def test_events_get_repository_identity(self):      # repo_hint and repo_basis "observed"
def test_cwd_with_non_ascii_letters(self):          # Review Focus 2
def test_store_folder_with_non_ascii_letters(self): # Review Focus 2: store folder "Città Example Store"
def test_missing_native_log_folder(self):           # Review Focus 4: new_events 0, no stop
def test_purged_key_is_not_appended(self):
def test_corrected_version_brings_corrected_events(self):    # acceptance criterion 6
def test_blocked_copies_leave_own_segments(self):   # step 10
def test_unknown_tool_warns_once_unless_category_rule(self): # rule "mcp__*" -> "other" stops the warning
def test_key_already_stored_is_not_appended(self):  # also from another machine's segment
def test_development_version_needs_variable(self):
def test_counts_by_folder(self):                    # SourceResult per folder; sessions_held_back
def test_held_back_session_counts_for_retention(self): # a held-back session's cwd: cleanup 7 wins over user 30
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `run.py`** in the order of the eleven steps; steps 4, 7, and 10 build the `PurgeSet` from
  `purge_events()` (Task 26); repository identity is resolved once for each folder in one ingestion, and
  `repositories.json` keeps root commits.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 30: Speed probe of the ingestion

**Spec:** `architecture.md` › Tests (benchmark); `product.md` › Phase 1, acceptance criterion 10.

**Files:**
- Create: `tests/benchmark.py`

**Interfaces:**
- Consumes: `run_ingestion` (Task 29); `MachineConfiguration`, `PersonConfiguration` (Task 12).
- Produces: `write_native_logs(folder: Path, days: int, sessions: int, lines: int) -> int` (invented native logs with
  the record types of the fixtures; returns the number of lines); `main(argv: list[str] | None = None) -> int` with
  `--days 30 --sessions 10 --lines 1000` (defaults) and `--folder <temporary folder>`; it times the first ingestion
  through `run_ingestion` and prints the seconds and the processor (`platform.processor()` or
  `platform.machine()`); `main` calls `days.use_tzdata_only()` first (Global Constraints: time zones only from
  `tzdata`; the script imports nothing from `tests/support.py`).
  It runs in a temporary folder with its own home, machine folder, and store, an `environ` with
  `AI_EFFORT_LEDGER_DEVELOPMENT=1`, and `ClaudeCodeAdapter(managed_file=<temporary file>)` as its adapter; it never
  reads the native logs, the store, or the configuration of the machine, and it imports nothing from
  `tests/support.py`, because `python -I` leaves the folder of the script off `sys.path`.

- [ ] **Step 1: Write the script** and run it with `--days 1 --sessions 2 --lines 50`: it completes and prints one
  time.
- [ ] **Step 2: Run it with the defaults** on the development machine and give the seconds to the owner. Above 60 s:
  profile with `cProfile`, fix Task 14, 25, or 29, and run again before Task 31; a second run above the target
  stops the task for the owner.
- [ ] **Step 3: Checkpoint.**

### Task 31: `selection` — the events of a report

**Spec:** `architecture.md` › Data flow (report), › Report record; `ingestion.md` › Store (broken lines);
`metrics.md` › Declared values (retractions).

**Files:**
- Create: `src/ai_effort_ledger/selection.py`, `tests/test_selection.py`

**Interfaces:**
- Consumes: `LocalIndex` (Tasks 25, 26); `LocalDays` (Task 27); `PurgeSet` (Task 15); `ReportParameters` (Task 12).
- Produces: `Selection(first: date, last: date, session_events: list[Event], confirmations: list[Event],
  manual_entries: list[Event], annotations: list[Event], retractions: list[Event], cancelled: set[EventKey],
  segments: list[SegmentState], broken: list[BrokenLine], newer: bool, warnings: list[dict])` (`confirmations`
  holds every timesheet confirmation of its days, retracted or not, for the chain of `replaces`); `select(index:
  LocalIndex, store_folder: Path, days: LocalDays, first: date, last: date, parameters: ReportParameters,
  held_back: set[tuple[str, str]]) ->
  Selection`; `cancelled(retractions: Sequence[Event]) -> set[EventKey]` (a retraction that a retraction cancels
  cancels nothing).

- [ ] **Step 1: Write the failing tests**:

```python
def test_whole_session_is_selected(self):   # a session with an event inside: also its event 5 h before the start
def test_margin_around_the_period(self):    # margin = max(stale_limit, idle_gap) = 4 h: a session whose only event
                                            # is 3 h before the start or after the end -> selected; 5 h -> not
def test_confirmations_by_day(self):
def test_intervals_that_intersect(self):    # manual entry crossing the period start
def test_bookkeeping_at_any_instant(self):  # retraction and purge from months before
def test_retraction_of_retraction_brings_back(self):
def test_purged_events_left_out(self):
def test_broken_lines_warn_and_are_recorded(self):    # warning "broken_line", values segment and line
def test_held_back_session_warns(self):     # "held_back_events"
def test_newer_schema_warns(self):          # "newer_schema_version"; newer is True (ADR 0023)
def test_lines_of_an_earlier_update_still_warn(self):   # an ingestion updates the index, then select:
                                                        # broken_line and newer_schema_version again
def test_empty_index_gives_same_selection(self):
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `selection.py`**; it brings the index up to date first and takes no lock; it builds the
  `PurgeSet` from `purge_events()`; `broken` and `newer` come from `broken_lines()` and `has_newer()`, never from the
  `IndexUpdate` alone.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 32: `metrics` — spans and human time

**Spec:** `metrics.md` › Human time, › Uncertainty; ADR 0021.

**Files:**
- Create: `src/ai_effort_ledger/metrics/__init__.py`, `spans.py`, `human.py`; `tests/test_metrics.py`

**Interfaces:**
- Produces: `Span = tuple[int, int]` (milliseconds since the epoch, start included, end excluded); `union(spans:
  Iterable[Span]) -> list[Span]`, `intersect(a, b) -> list[Span]`, `subtract(a, b) -> list[Span]`, `total(spans) ->
  int`; `HumanInterval(start: int, end: int, signal: Event, kind: str)` (`kind` `"signal_gap"`, `"response"`,
  `"minimum_attention"`; a signal gap belongs to its later signal); `MetricsParameters(idle_gap: int,
  minimum_attention: int, stale_limit: int, headless_prompts: bool, category: Callable[[Event], str] =
  stored_category)` (seconds; `category` gives the tool category of a `tool_call` after the category rules, and
  `stored_category(event: Event) -> str` gives its stored `tool_category`; `cli` builds it from `ReportParameters`
  and `effective_category` of Task 36, because `configuration` and `attribution` are not below `metrics`);
  `human_signals(events: Sequence[Event],
  headless_prompts: bool) -> list[Event]`; `human_intervals(events: Sequence[Event], parameters: MetricsParameters)
  -> list[HumanInterval]`; `human_time_at_idle_gaps(events, parameters, window: Sequence[Span]) -> dict[int,
  int]` (idle gaps 300, 600, 900 seconds and the one in use → milliseconds of human time inside `window`);
  `unknown_invocation_share(events, parameters, window: Sequence[Span]) -> float`; `presence_span(events,
  parameters, window: Sequence[Span]) -> int | None` (milliseconds from the first to the last human signal inside
  `window`; `None` without a signal). A window is a sequence of spans, because a local day can have two parts.

- [ ] **Step 1: Write the failing tests**:

```python
def test_span_operations(self):
def test_signal_gap(self):                  # prompts 09:00 and 09:05 -> 6 min: gap 5 to the 09:05 prompt,
                                            # minimum attention 1 to the 09:00 prompt, which ends no interval
def test_gap_longer_than_idle_gap(self):    # 09:00 and 09:11 -> two minimum attentions, 2 min
def test_response_interval(self):           # output 10:30, prompt 10:34 -> 4 min
def test_background_output_starts_no_response(self):
def test_absent_mode_starts_response(self): # no subagent_mode: the output of the subagent starts the interval
def test_decision_request_starts_response(self):
def test_rule_decision_is_no_signal(self):
def test_headless_prompts_parameter(self):  # "yes" -> signals; default "no" -> none
def test_one_stream_across_sessions(self):  # an instant counts once
def test_idle_gaps_5_10_15(self):
def test_unknown_invocation_share(self):    # 1 of 4 signals -> 0.25
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `spans.py` and `human.py`**; events sort by `timestamp`, then `event_order`. A subagent
  whose `subagent_mode` is absent counts as a foreground subagent (ruled 2026-11-20; `metrics.md` › Human time).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 33: `metrics` — turns, agent time, blocked time

**Spec:** `metrics.md` › Agent time (a wait for a subagent is a tool call of the category `delegate` until its tool
result), › Blocked time.

**Files:**
- Create: `src/ai_effort_ledger/metrics/agent.py`; Modify: `__init__.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces: `Turn(agent: tuple[str, str, str], start: int, end: int)` (`tool`, `session_id`, `agent_id`);
  `AgentPart(start: int, end: int, agent: tuple[str, str, str], event: Event)` (the part between two consecutive
  events of a turn, without blocked time and waits for subagents, with the event that ends it);
  `BlockedInterval(start: int, end: int, request: Event)`; `turns(events, stale_limit: int) -> list[Turn]`;
  `agent_parts(events, parameters) -> list[AgentPart]`; `blocked_intervals(events) -> list[BlockedInterval]`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_turn_from_input_to_last_output(self):
def test_tool_execution_is_part_of_turn(self):
def test_interruption_ends_turn(self):
def test_stale_turn_ends_at_last_event(self):   # 08:00, 08:01 call, 13:00 result, 13:01 -> turns 1 + 1 min
def test_blocked_time_is_subtracted(self):
def test_foreground_wait_is_subtracted(self):
def test_background_wait_is_near_zero(self):   # call 12:01:00, result 12:01:02 -> 2 s subtracted
def test_call_without_result_waits_to_next_event(self):   # no tool result: the wait ends at the next event
                                                         # of its agent, an interruption, or the last event
def test_delegate_category_wait_without_tool_names(self):   # parameters.category gives "delegate" for "Spawn"
def test_decision_without_decision_ends_at_next_event(self):
def test_subagent_has_own_turns(self):
def test_records_out_of_order_give_same_agent_time(self):   # Review Focus 3
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `agent.py`.** It finds a wait by the category `delegate` that `parameters.category` gives,
  never by a tool name, and never reads `subagent_mode`; a call without a tool result waits as a decision request
  without a decision (`metrics.md` › Agent time; ruled 2026-11-20).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 34: `metrics` — manual entries and activity classes of the person

**Spec:** `metrics.md` › Declared values (manual entries), › Activity classes.

**Files:**
- Create: `src/ai_effort_ledger/metrics/classes.py`; Modify: `__init__.py`, `tests/test_metrics.py`

**Interfaces:**
- Produces: `ManualPart(start: int, end: int, entry: Event)`; `manual_parts(entries: Sequence[Event], human:
  list[Span]) -> tuple[list[ManualPart], list[dict]]` (`overlapping`: the whole interval; `additional`: the interval
  without measured human time, with a `manual_entry_overlap` warning for each removed overlap); `activity_classes(human:
  list[Span], agent: list[Span], blocked: list[Span], window: Sequence[Span]) -> dict[str, int]` (keys `person_only`,
  `supervised`, `unattended`, `blocked`, `idle`; the values add up to the window); `Metrics(human:
  list[HumanInterval], manual: list[ManualPart], agent: list[AgentPart], blocked: list[BlockedInterval], warnings:
  list[dict])`; `compute_metrics(session_events: Sequence[Event], manual_entries: Sequence[Event], parameters:
  MetricsParameters) -> Metrics`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_overlapping_entry_merges_by_union(self):
def test_additional_entry_counts_outside_measured_time(self):   # and warns
def test_classes_table(self):        # one instant of each row of the table -> the class of that row
def test_present_person_and_blocked_agent_is_person_only(self):
def test_classes_add_up_to_window(self):
def test_day_of_two_parts(self):     # window of two spans: nothing between them is counted
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `classes.py` and `compute_metrics`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 35: Scenarios of the prototype on the core

**Spec:** `architecture.md` › Tests (scenario tests); `validation-2026-11.md`; acceptance criterion 3.

**Files:**
- Create: `tests/test_scenarios.py`; Modify: `tests/support.py` (`scenario(sessions, annotations=(),
  manual_entries=(), subagents=None, time_zones=None, day_starts=None) -> tuple[list[Event], Metrics,
  LocalDays]`: `sessions` is a sequence of the record lists of one or more sessions, each with its own `cwd` and
  repository; the time-zone history and the day-start hours are parameters (one zone from 1970 and day start 00:00
  when absent), so a scenario can change the day start, cross a change of daylight saving, or make a journey; it
  writes the native logs and the events of the source `ledger`, reads them with the adapter as settled sessions,
  computes the metrics with defaults, and gives the events, so that a test can assert which events a scenario
  writes; `test_midnight_split` cuts by `LocalDays.day_parts`; `activity_classes` takes as window the day parts of
  every local day that holds an event of the scenario, so the four classes of the prototype hold, and `idle`, the
  rest of the window, is not compared)

- [ ] **Step 1: Write the scenarios** with the values of `prototype/tests/test_scenarios.py`, in the native record
  forms of the adapter fixtures (a subagent links through `toolUseResult.agentId`). Minimum attention differs
  from the prototype on purpose: the first signal of a chain ends no interval, so it gets minimum attention
  (`metrics.md` › Human time, ADR 0021; ruled 2026-11-20), and a chain of more than one signal adds 1 minute
  to the human time of the prototype (an isolated signal already has its minute there):

```python
def test_example_morning(self):
    # 09:00 prompt, 09:05 queued message, 09:20-10:00 permission of the person, 10:10-10:25 foreground
    # subagent, 10:30 output, 10:34 prompt, 10:35 output
    # human 11 min (the prototype gives 10); agent 50 min; blocked 40 min;
    # classes person_only 6, supervised 5, unattended 45, blocked 39 (minutes)
def test_overnight_notification(self):        # agent 90, human 2, unattended 90
def test_rule_permission(self):               # agent 2, human 1, no decision event
def test_permission_overnight(self):          # blocked 779, agent 2, class blocked 778
def test_question_to_the_person(self):        # blocked 3, agent 2, human 5
def test_background_subagent(self):           # agent 178 s: the 2 s wait is subtracted (prototype: 3 min)
def test_parallel_sessions_one_stream(self):  # human 20
def test_alternating_sessions(self):          # human 19 together; 4 for the sessions one by one
def test_programmatic_session(self):          # human 0, unattended 8
def test_midnight_split(self):                # one hour from 23:30 local -> 30 + 30 min in two local days
def test_stale_turn(self):                    # turns 2 min
def test_prompt_without_origin(self):         # "<command-message>" text is a prompt; "<task-notification>"
                                              # is a notification; isMeta gives no event
def test_human_time_across_a_day_start_change(self):   # day start 04:00 from 2026-12-01: a signal at 01:02
                                                       # local counts for 2026-11-30; human 7 min (6 + 1)
def test_human_time_on_a_daylight_saving_day(self):    # 2026-10-25 in Europe/Rome lasts 25 h; signals at 02:30
                                                       # and 02:36 local give human 7 min (6 + 1) on that day
def test_human_time_across_a_journey(self):            # Europe/Rome, America/New_York from 2026-12-01T03:00Z:
                                                       # 04:00Z is 23:00 of 11-30; human 1 min on 2026-11-30
```

- [ ] **Step 2: Run** (the modules exist): any failure is a defect of the core or of the port; fix the core when the
  spec supports the hand value, and flag when the spec and the hand value disagree. A fix goes into the code of one
  module, with a test in that module's test file; a fix that touches more than one module stops the task for the owner.
- [ ] **Step 3: Run the full suite.**
- [ ] **Step 4: Set the Backlog task to Done.**
- [ ] **Step 5: Checkpoint.** Gate G6: ask the owner whether to push the branch.

## Milestone 5 — `attribution`

### Task 36: `attribution` — identity rules and category rules

**Spec:** `configuration.md` › Matching; `metrics.md` › Attribution; ADR 0009.

**Files:**
- Create: `src/ai_effort_ledger/attribution/__init__.py`, `rules.py`; `tests/test_attribution.py`

**Interfaces:**
- Consumes: `IdentityRule`, `CategoryRule`, `pattern_matches` (Task 12).
- Produces: `pattern_narrower(p: str, q: str) -> bool`; `folder_matches(rule_folder: str, folder: str) -> bool`;
  `more_specific(x: IdentityRule, y: IdentityRule) -> bool`; `project_of(repository: str | None, folder: str | None,
  branch: str | None, day: date, rules: Sequence[IdentityRule]) -> tuple[str | None, dict | None]` (the project, or
  `None` and an `identity_rule_conflict` error with the rules, which `event_buckets` of Task 37 completes with one
  event that they match (`configuration.md` › Matching); without a matching rule, the repository identity
  itself); `category_of(tool_name: str, stored: str, rules: Sequence[CategoryRule]) -> tuple[str, dict | None]`;
  `effective_category(rules: Sequence[CategoryRule]) -> Callable[[Event], str]` (`category_of` of a `tool_call`,
  for `MetricsParameters.category` of Task 32; `attribute` of Task 38 reports a `category_rule_conflict`).

- [ ] **Step 1: Write the failing tests**:

```python
def test_pattern_narrower(self):
    self.assertTrue(rules.pattern_narrower("feat/*", "*"))
    self.assertTrue(rules.pattern_narrower("feat/a", "feat/*"))
    self.assertFalse(rules.pattern_narrower("*", "feat/*"))
def test_folder_matches_inside_and_separators(self):   # r"D:\Work" matches "d:/work/app"
def test_unix_folder_matches_with_case(self):          # "/home/a/App" does not match "/home/a/app"
def test_foreign_folder_compares_as_text(self):        # a virtual-machine path in an event
def test_date_range_both_ends_included(self):
def test_most_specific_rule_wins(self):
def test_equal_specificity_is_configuration_error(self):   # unattributed + identity_rule_conflict with one event
def test_default_rule_only_without_matching_rule(self):
def test_category_rule_replaces_stored_category(self):
def test_category_conflict_keeps_stored_category(self):    # category_rule_conflict
def test_effective_category_of_a_tool_call(self):   # rule "Spawn" -> delegate: a tool_call "Spawn" -> "delegate"
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `rules.py`** with the narrower-pattern test of `configuration.md` › Matching: P is narrower than
  Q when Q matches P with each `*` of P replaced by a character that only a `*` of Q matches.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 37: `attribution` — project names and annotations

**Spec:** `metrics.md` › Attribution (projects, work items, annotations); ADR 0018, ADR 0019.

**Files:**
- Create: `src/ai_effort_ledger/attribution/names.py`, `annotations.py`; Modify: `__init__.py`,
  `tests/test_attribution.py`

**Interfaces:**
- Consumes: the rules of Task 36; `LocalDays` (Task 27); the event lists of a `Selection` (Task 31) as values,
  because `selection` is not below `attribution`.
- Produces: `Bucket = tuple[str | None, str | None]` (project identifier, work item identifier; `(None, None)` is the
  unattributed time); `default_name(repository: str) -> str` (the last part of the path of a repository identity,
  or the first 12 characters of a root-commit hash); `project_names(identifiers: Iterable[str],
  repository_hints: Iterable[str], person: PersonConfiguration) -> tuple[dict[str, str], list[dict]]` (a default
  name only for an identifier that a repository identity of `repository_hints` gives; an identifier that is not a
  repository identity is its own name, `metrics.md` › Attribution); `event_buckets(session_events: Sequence[Event],
  annotations: Sequence[Event], person: PersonConfiguration, days: LocalDays) -> tuple[dict[EventKey, Bucket],
  list[dict]]` (the bucket of each event, and the warnings); `declared_project_unknown(identifiers: Iterable[str],
  person: PersonConfiguration, repository_hints: Iterable[str]) -> list[dict]` (one `declared_project_unknown`
  warning for each project identifier of a declared event that no identity rule, no `[[project]]` entry, and no
  repository identity among `repository_hints` gives; `event_buckets` calls it for the annotations, `attribute` of
  Task 38 for the manual entries, and `day_figures` of Task 40 for the latest confirmation).

- [ ] **Step 1: Write the failing tests**:

```python
def test_default_names(self):        # "example.org/team/app" -> "app"; "root-commit:<40 hex>" -> first 12
def test_declared_identifier_is_its_own_name(self):   # "acme/alpha", no repository hint ->
                                                      # "acme/alpha"; with the hint -> "alpha"
def test_equal_default_names_take_more_path(self):   # "a/x/app", "b/y/app" -> "x/app", "y/app"
def test_name_given_to_two_projects_is_error(self):  # project_name_conflict, both identifiers
def test_event_takes_folder_of_previous_event(self):
def test_session_annotation_overrides(self):
def test_work_item_without_project_keeps_project(self):
def test_project_without_work_item_removes_work_item(self):
def test_work_item_on_unattributed_event_warns(self):    # work_item_without_project
def test_overlapping_annotations_apply_in_timestamp_order(self):
def test_declared_project_unknown_warns(self):
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `names.py` and `annotations.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 38: `attribution` — the split rule, manual entries, time by bucket

**Spec:** `metrics.md` › Attribution (split rule), › Declared values (manual entries); ADR 0021; acceptance
criterion 4.

**Files:**
- Create: `src/ai_effort_ledger/attribution/split.py`; Modify: `__init__.py`, `tests/test_attribution.py`

**Interfaces:**
- Consumes: `Metrics`, `Span`, spans functions (Tasks 32–34); `event_buckets`, `project_names` (Task 37).
- Produces: `split_human(intervals: Sequence[HumanInterval]) -> list[tuple[Span, Event]]`; `BucketFigures(human_time:
  int, with_manual: int, agent_time: int, blocked_time: int, activity_classes: dict[str, int], inferred_human_share:
  float, inferred_agent_share: float)` (milliseconds; this task fills `human_time`, `with_manual`, `agent_time`, and
  `blocked_time`, Task 39 the activity classes and the inferred shares); `Attribution` with `figures(window:
  Sequence[Span]) -> dict[Bucket, BucketFigures]`, `names: dict[str, str]`, `work_item_names: dict[tuple[str, str],
  str]`, `configuration_errors: list[dict]`, `warnings: list[dict]`; `attribute(session_events: Sequence[Event],
  annotations: Sequence[Event], manual_entries: Sequence[Event], metrics: Metrics, person: PersonConfiguration, days:
  LocalDays, confirmations: Sequence[Event] = ()) -> Attribution` (the projects and work items of `confirmations`
  get names too, so that a project that only a timesheet confirmation names has one).

- [ ] **Step 1: Write the failing tests**:

```python
def test_split_rule_earliest_end_wins(self):
def test_agent_time_divides_at_events(self):
def test_blocked_time_follows_its_request(self):
def test_overlapping_manual_entry_takes_interval(self):  # and warns manual_entry_overlap
def test_latest_overlapping_entry_wins(self):
def test_parts_add_up_to_human_time(self):           # acceptance criterion 4, measured part
def test_with_manual_parts_add_up(self):             # acceptance criterion 4, part with manual entries
def test_manual_entry_of_unknown_project_warns(self):   # declared_project_unknown
def test_project_only_in_a_confirmation_has_a_name(self):
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `split.py` and `attribute`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 39: `attribution` — activity classes of projects, inferred shares, project figures, parts of each session

**Spec:** `metrics.md` › Activity classes, › Attribution (inferred repository identity); `command-line.md` ›
Commands (`sessions <day>`), › JSON documents (`report day`); ADR 0018.

**Files:**
- Modify: `src/ai_effort_ledger/attribution/split.py`, `__init__.py`, `tests/test_attribution.py`,
  `tests/test_scenarios.py`

**Interfaces:**
- Consumes: `split_human`, `BucketFigures`, `Attribution`, `attribute` (Task 38); `activity_classes` (Task 34).
- Produces: the `activity_classes`, `inferred_human_share`, and `inferred_agent_share` of each `BucketFigures`; on
  `Attribution`: `project_figures(window: Sequence[Span]) -> dict[str | None, BucketFigures]` (for `report day`: each
  project from the unions of the spans of its buckets, so its blocked time and activity classes are never sums of
  work-item figures; `None` is the unattributed time) and `session_parts(window: Sequence[Span]) -> dict[tuple[str,
  str], dict[Bucket, tuple[int, int]]]` (human time and agent time for each bucket of each session, for
  `sessions <day>`).

- [ ] **Step 1: Write the failing tests**:

```python
def test_inferred_shares(self):                      # 4 of 10 min human time on repo_basis "inferred"
                                                     # -> 0.4; agent time the same way
def test_project_classes_have_no_idle(self):
def test_project_figures_are_unions(self):          # two work items of project A with overlapping blocked
                                                     # time -> A counts that blocked time once
def test_session_parts(self):                        # session S: project A 40 min, project B 20 min
def test_session_parts_add_up_to_session_figures(self):
```

- [ ] **Step 2: Add scenarios** to `tests/test_scenarios.py`: two parallel sessions of two projects (split rule),
  overlapping annotations, a manual entry of each mode, work across the start or the end of a report period; the test
  computes the project figures with `attribute` (Task 38) from the events that `scenario` gives; Task 40 adds
  the day-level assertions of these scenarios with `day_figures`.
- [ ] **Step 3: Run and see it fail**, then write the classes, the shares, `project_figures`, and `session_parts`.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.** Gate G6: ask the owner whether to push the branch.

## Milestone 6 — `declared`, `setup`

### Task 40: `declared` — timesheet confirmations and declared days

**Spec:** `metrics.md` › Declared values; ADR 0011, ADR 0014; acceptance criteria 4 and 5.

**Files:**
- Create: `src/ai_effort_ledger/declared.py`, `tests/test_declared.py`; Modify: `tests/test_scenarios.py`

**Interfaces:**
- Consumes: `Attribution`, `BucketFigures` (Tasks 38, 39); `Bucket`, `declared_project_unknown` (Task 37); `Metrics`,
  `MetricsParameters`
  (Tasks 32–34); `LocalDays` (Task 27); the confirmations and the cancelled keys of a `Selection` (Task 31) as
  values.
- Produces: `Declaration(latest: Event | None, warnings: list[dict])`; `latest_confirmation(confirmations:
  Sequence[Event], cancelled: set[EventKey]) -> Declaration`; `TimesheetLine(bucket: Bucket, measured: int,
  with_manual: int, declared: int | None)` (seconds); `DayTimesheet(day: date, state: str, total: int,
  measured_total: int, lines:
  list[TimesheetLine], human_time_at_idle_gaps: dict[int, int] | None, unknown_invocation_share: float, agent_time: int,
  presence_span: int | None, warnings: list[dict])`; `DayFigures(timesheet: DayTimesheet, person: BucketFigures,
  projects: dict[str | None, BucketFigures], buckets: dict[Bucket, BucketFigures])` (what `reports` reads, so that
  it never imports `attribution`; `projects` from `Attribution.project_figures`);
  `day_figures(day: date, attribution: Attribution, metrics: Metrics, session_events: Sequence[Event],
  confirmations: Sequence[Event], cancelled: set[EventKey], days: LocalDays, parameters: MetricsParameters) ->
  DayFigures` (`session_events` give the human time at each idle gap, the presence span, and the repository hints
  of `declared_project_unknown` for the projects of the latest confirmation, Task 37);
  `bucket_order(bucket: Bucket, measured: Mapping[Bucket, int]) -> tuple` (larger measured human time first, then
  the project and work item identifiers as text, the unattributed time last; `metrics.md` › Declared values);
  `whole_seconds(parts: Mapping[Bucket, int], measured: Mapping[Bucket, int]) -> dict[Bucket, int]` (D12; ties by
  `bucket_order`); `Bucket` and `BucketFigures`, re-exported from `attribution`, so that `reports` takes them from
  `declared`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_latest_by_timestamp_then_key(self):
def test_retracting_latest_brings_back_earlier(self):
def test_all_retracted_is_measured_day(self):
def test_confirmation_not_seen(self):          # acceptance criterion 5: two machines, no replaces -> warning
def test_chain_through_retracted_confirmation(self):    # not a warning
def test_confirmation_before_replaced(self):
def test_declared_total_is_sum_of_entries(self):         # acceptance criterion 4, declared part
def test_declared_below_measured_warns_per_project(self):    # also a project without entry
def test_no_warning_when_declared_equals_shown_measured(self):   # measured 900.4 s shows 900; declared 900
def test_entry_without_work_item_stays_in_project(self):
def test_confirmation_of_unknown_project_warns(self):    # declared_project_unknown
def test_measured_day_total_is_union_with_manual(self):
def test_day_of_two_parts(self):              # a journey to the west: the day is the sum of its two parts
def test_presence_span_of_the_day(self):
def test_whole_seconds_add_up(self):           # 3 parts of 1500 ms, 1500 ms, 1000 ms -> 2, 1, 1 seconds
                                               # (the tie goes by `bucket_order`)
```

Add to `tests/test_scenarios.py` the day-level assertions of the scenarios of Task 39, with `day_figures`.

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `declared.py`** (confirmations part).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 41: `declared` — timesheet proposal

**Spec:** `metrics.md` › Declared values (proposal); `command-line.md` › Timesheet.

**Files:**
- Modify: `src/ai_effort_ledger/declared.py`, `tests/test_declared.py`, `tests/test_scenarios.py`,
  `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Produces: `proposal(with_manual: Mapping[Bucket, int], granularity: int, total: int | None = None, given:
  Mapping[Bucket, int] | None = None) -> dict[Bucket, int]` (seconds; `with_manual` holds the whole seconds that
  the report shows, D12;
  ties by `bucket_order` of Task 40; without `total`, each entry is its value rounded up to the granularity
  (`metrics.md` › Declared values); `SetAboveTotal` (stop error `set_above_total`, exit
  1).

The division of a total, when the shares alone do not determine it, returns only the entries that it divides, also
the unattributed rest; the caller merges the entries of `given` into it:

```python
if measured_sum == 0:                      # no measured time among the other entries
    return {UNATTRIBUTED: remaining_total}    # the caller adds a given value of the same entry
units, rest = divmod(remaining_total, granularity)
quotients = {b: divmod(units * value, measured_sum) for b, value in shares.items()}
result = {b: q for b, (q, _) in quotients.items()}
order = sorted(shares, key=lambda b: (-quotients[b][1], bucket_order(b, shares)))   # whole numbers only
for b in order[: units - sum(result.values())]:
    result[b] += 1
result = {b: n * granularity for b, n in result.items()}
result[order[0]] += rest
```

- [ ] **Step 1: Write the failing tests**:

```python
def test_rounds_up_to_granularity(self):      # 50 min, 15 min granularity -> 60 min
def test_zero_entries_are_left_out(self):
def test_total_divides_by_shares(self):       # total 8 h over 3 h / 1 h measured -> 6 h / 2 h
def test_shares_include_manual_entries(self):  # A 30 min measured, B a 60 min manual entry, total 3 h -> 1 h / 2 h
def test_rest_below_one_unit_to_largest_remainder(self):   # total 8:05 -> 5 min to the first of the order
def test_equal_remainders_follow_bucket_order(self):   # total 30 min over A 15 min / B 45 min: equal
                                                       # remainders, B (larger measured) takes the unit;
                                                       # 1h15 over 50 % / 50 %: the identifier decides
def test_given_entries_and_total(self):       # --set A=2h --total 8h -> rest divides among others
def test_rest_without_other_entry_is_unattributed(self):   # total 3 h -> unattributed 3 h; a given
                                                           # unattributed 1 h takes the rest -> 3 h
def test_total_on_a_day_without_measured_time_is_unattributed(self):
def test_given_project_and_total_without_measured_time(self):   # --set A=1h --total 3h -> A 1h, unattributed 2h
def test_set_above_total_stops(self):
def test_total_below_measured_is_allowed(self):   # warning on the declared day, not here
```

- [ ] **Step 2: Add the scenarios** "timesheet proposal" and "division of a given total" to
  `tests/test_scenarios.py`; the test computes the proposal from the `with_manual` figures of `attribute` (Task 38)
  for the events that `scenario` gives.
- [ ] **Step 3: Run and see it fail**, then write `proposal`.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 42: Speed probe of the timesheet figures

**Spec:** `architecture.md` › Tests (benchmark); `product.md` › Phase 1, acceptance criterion 10.

**Files:**
- Modify: `tests/benchmark.py`

**Interfaces:**
- Consumes: `select` (Task 31); the metrics of Tasks 32–34; `Attribution` (Tasks 38, 39); `day_figures`,
  `proposal` (Tasks 40, 41).
- Produces: a second time: the figures of each day of one month, from `selection` to `day_figures` and `proposal`,
  without `reports` and `cli`.

- [ ] **Step 1: Extend the script** and run it with `--days 1 --sessions 2 --lines 50`: it prints two times.
- [ ] **Step 2: Run it with the defaults** on the development machine: the probe measures the pipeline alone, as
  an early warning; the target of criterion 10 is measured only through `cli.main` (Task 64, gate G5). Above 5 s:
  profile with `cProfile`, fix, and run again before Task 43; a second run above it stops the task for the owner.
- [ ] **Step 3: Checkpoint.**

### Task 43: `platform` — time zone of the operating system (gate G3)

**Spec:** `configuration.md` › Writes (Windows names), › To be confirmed (CLDR release).

**Gate G3.** First a research note `docs/research/windows-zones-2026-11.md` from primary sources (the CLDR release
notes and `common/supplemental/windowsZones.xml` of the release), with Best / Cleanest / Most general; then a ruling
panel on the release and on how an update of the table reaches a release, after a plain-English explanation with a
table of cases × options. The ruling becomes a sentence of
`configuration.md`, and the `To be confirmed` item is deleted.

**Files:**
- Create: `src/ai_effort_ledger/platform/zones.py`, `windows_zones.py` (data: the territory `001` rows of the ruled
  release, which its module docstring names); Modify: `__init__.py`, `tests/test_platform.py`

**Interfaces:**
- Produces: `WINDOWS_ZONES: dict[str, str]`; `windows_zone_to_iana(name: str) -> str | None`;
  `system_time_zone(system: str, environ: Mapping[str, str], localtime: Path, read_registry: Callable[[], str |
  None]) -> str | None`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_windows_name_converts(self):    # "W. Europe Standard Time" -> "Europe/Berlin"
def test_unknown_windows_name(self):     # -> None, never a guess
def test_linux_localtime_link(self):     # link to .../zoneinfo/Europe/Rome -> "Europe/Rome"
def test_tz_variable_wins(self):         # TZ=":Europe/Rome" -> "Europe/Rome"
def test_every_value_is_in_tzdata(self): # each value of WINDOWS_ZONES opens with zoneinfo after reset_tzpath
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the table and the functions**; Windows reads `TimeZoneKeyName` of
  `HKLM\SYSTEM\CurrentControlSet\Control\TimeZoneInformation` with `winreg`.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 44: `setup` — setup steps and the scheduled ingestion

**Spec:** `command-line.md` › Setup, › Commands (`schedule`); `ingestion.md` › Frequency; `configuration.md` ›
Writes (first person configuration).

**Files:**
- Create: `src/ai_effort_ledger/setup.py`, `tests/test_setup.py`

**Interfaces:**
- Consumes: Tasks 6–8, 12, 13, 17, 24, 26, 29, 43.
- Produces: `SetupContext(system: str, environ: Mapping[str, str], home: Path, now: datetime, executable: Path, run:
  Callable, installation: str | None, ask: Callable[[str], str] | None, adapters: Sequence[Adapter], time_zone:
  Callable[[], str | None], new_uid: Callable[[], str], version: str, uid: int | None)` (`ask` is `None` when
  standard input is not a terminal; `time_zone` gives the IANA time zone of the operating system or `None`; `new_uid`
  gives `refresh_machine` its new machine identifier; `version` goes to the development check of the scheduler entry
  and to `run_ingestion`; `uid` goes to `create_entry` and `remove_entry` of Task 8; tests pass
  `support.adapters_for_tests(home)` and a fixed `time_zone`);
  `SetupOptions(store: Path | None, label: str | None, native_logs: list[tuple[str, str]], schedule: bool | None,
  time: str)`; `SetupResult(machine: str, store: Path, configuration_created: bool, entries:
  list[dict], retention: list[dict], schedule: SchedulerEntry | None, ingest:
  IngestionResult)` (`entries` and `retention` feed the text output only; the JSON document holds the keys of
  `command-line.md` › JSON documents);
  `run_setup(options: SetupOptions, context: SetupContext) -> SetupResult`.

- [ ] **Step 1: Write the failing tests** (temporary home; fake `run`; no real scheduler):

```python
def test_first_setup_creates_all(self):       # machine.toml, configuration.toml, label, first ingestion
def test_first_setup_stores_every_complete_event(self):   # criterion 1: store keys == events of all fixtures
def test_second_setup_changes_only_options(self):
def test_recorded_folder_stays(self):         # a folder the person added is kept
def test_claude_config_dir_is_recorded(self):
def test_store_option_is_written(self):
def test_no_label_without_terminal(self):
def test_schedule_only_with_consent(self):    # schedule None and no terminal -> shown, not created;
                                              # version "0.1.0" and --schedule yes -> created
def test_development_version_never_creates_entry(self):   # 0.1.0.dev0, --schedule yes -> shown, not created
def test_retention_is_shown_with_advice(self):
def test_windows_zone_unknown_writes_no_time_zone(self):   # time_zone gives None -> no [[time_zone]]
def test_failed_scheduler_warns_and_ingests(self):   # run gives code 1 -> warning scheduler_failed, schedule
                                                     # shows no entry, the first ingestion runs, exit 0
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `setup.py`** in the order of the seven steps; the retention advice follows `ingestion.md` ›
  Frequency, and on Linux it names `loginctl enable-linger` (ruled 2026-11-20).
- [ ] **Step 4: Run and see it pass**, then the full suite. On the owner's Windows machine, with the owner's consent:
  write the XML of `entry_definition("windows", ...)`, for a store folder whose path holds `à`, to a temporary file,
  run `schtasks /Create /TN ai-effort-ledger-ingest /XML <file> /F`, check that `schtasks /Query /TN
  ai-effort-ledger-ingest /XML` shows the path unchanged (a changed path is a defect of the encoding of the file,
  fixed in `scheduler.py` with a test), run `schtasks /Run /TN ai-effort-ledger-ingest`, check whether a console
  window shows, then `schtasks /Delete /TN ai-effort-ledger-ingest /F`. A development version never creates the
  entry through the ledger, and its run stops with `development_version`, which does not change the check. When a
  window shows, flag the divergence (Task 8).
- [ ] **Step 5: Checkpoint.** Gate G6: ask the owner whether to push the branch.

## Milestone 7 — `reports`

### Task 45: `reports` — report record and JSON documents

**Spec:** `command-line.md` › JSON documents, › Reports, › Output; `architecture.md` › Report record;
`metrics.md` › Reproducibility, › Uncertainty.

**Files:**
- Create: `src/ai_effort_ledger/reports/__init__.py`, `record.py`, `documents.py`; `tests/test_reports.py`

**Interfaces:**
- Consumes: `DayTimesheet`, `DayFigures`, `Bucket`, `bucket_order` (Task 40, which re-exports `Bucket`);
  `proposal` (Task 41); `Selection` (Task 31); `tzdata_version` (Task 27).
- Produces: `report_record(parameters: ReportParameters, person: PersonConfiguration, selection: Selection,
  configuration_errors: list[dict], ledger: str, tzdata: str) -> dict`; `timesheet_document(days:
  Sequence[DayFigures], names: Names) -> dict` (the inferred shares come from `DayFigures.buckets`);
  `timesheet_day_document(figures: DayFigures, proposal: Mapping[Bucket, int] | None, names: Names) -> dict`
  (`timesheet <day>`, with `context`; each entry also has `proposed`, `command-line.md` › JSON documents;
  `timesheet confirm` adds `event_uid`); `day_document(figures: DayFigures, names: Names) -> dict` (`person`,
  `projects` from `DayFigures.projects`, `work_items` from the buckets of `DayFigures.buckets` with a work item);
  `sessions_document(day: date, sessions: list[dict]) -> dict`; `entries_document(day: date, events: list[Event]) ->
  dict`; `Names(projects: dict[str, str], work_items: dict[tuple[str, str], str])`. Keys exactly as the table of
  › JSON documents; a project or work item is
  `{"id": ..., "name": ...}` or `null`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_record_holds_versions_parameters_rules_facts_segments(self):
def test_timesheet_keys(self):   # days[*]: day, state, total, human_time_at_idle_gaps (measured only; keys
                                 # "300", "600", "900"), unknown_invocation_share, entries[*] with project,
                                 # work_item, measured, with_manual_entries, declared, inferred_*_share
def test_unattributed_is_null(self):
def test_day_keys(self):
def test_timesheet_day_keys(self):   # entries as in report timesheet; context with agent_time and presence_span
def test_parts_add_up_in_json(self):   # measured parts sum to measured_total; with manual entries and
                                        # declared parts sum to total (criterion 4)
def test_durations_are_whole_seconds(self):
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `record.py` and `documents.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 46: `reports` — text output

**Spec:** `command-line.md` › Output, › Reports; the texts of `language` (Task 11).

**Files:**
- Create: `src/ai_effort_ledger/reports/text.py`; Modify: `__init__.py`, `src/ai_effort_ledger/language.py`,
  `tests/test_language.py`, `tests/test_reports.py`

**Interfaces:**
- Produces: `format_duration(seconds: int) -> str` (`H:MM`, whole minutes, seconds left out, hours beyond 24 kept);
  `render(document: dict, language: str) -> str` (one table for each section; columns separated by two spaces, each
  column as wide as its widest cell; the first column left-aligned, numbers right-aligned; titles and states
  from `language.label`). This interface also
  fixes, for each report, its sections and the column keys of each table, in order, as `language.label` keys; the
  command line and its JSON output are a stable contract (`command-line.md` line 4); no spec sentence fixes
  the text layout of a table, so this interface fixes it (ruled 2026-11-19).

- [ ] **Step 1: Write the failing tests**:

```python
def test_format_duration(self):
    self.assertEqual((text.format_duration(5459), text.format_duration(91800)), ("1:30", "25:30"))
def test_timesheet_table_english(self):
def test_timesheet_table_italian(self):    # states "giorno misurato" / "giorno dichiarato" from the glossary
def test_names_and_notes_stay_as_written(self):
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `text.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 47: `reports` — frozen reports and their differences

**Spec:** `command-line.md` › Frozen reports, › JSON documents (`frozen show`); `architecture.md` › Report record.

**Files:**
- Create: `src/ai_effort_ledger/reports/frozen.py`; Modify: `__init__.py`, `tests/test_reports.py`

**Interfaces:**
- Consumes: `write_frozen`, `list_frozen`, `remove_frozen` (Task 14).
- Produces: `freeze(store_folder: Path, machine: str, document: dict, note: str | None, now: datetime, new_uid:
  Callable[[], str]) -> str` (UUID 4 identifier; the file holds `document`, `note`, and `frozen_at`, D13);
  `differences(frozen: dict, current: dict) -> tuple[list[dict], list[dict]]` (`differences` for each day, project,
  and work item whose figures differ, with the frozen value and the value of now; `changed` for parameters, rules,
  and dated facts); `latest_frozen_by_day(frozen:
  Sequence[dict]) -> dict[str, dict]`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_freeze_keeps_json_also_for_text_output(self):
def test_differences_of_a_changed_rule(self):    # an identity rule added after the freeze: `changed` names
                                                  # it, and `differences` holds the figures of its day
def test_changed_parameters(self):               # idle_gap 10min -> 5min
def test_frozen_list_keys(self):
def test_latest_frozen_holds_each_day(self):     # two frozen reports overlap; the later frozen_at wins
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `frozen.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.** Gate G6: ask the owner whether to push the branch.

## Milestone 8 — `cli`

### Task 48: `cli` — output, `Context`, exit codes, guards

**Spec:** `command-line.md` › Output, › Exit codes, › Setup (last paragraph), › JSON documents; `architecture.md` ›
Runtime, › Modules (`cli`).

**Files:**
- Create: `src/ai_effort_ledger/cli/__init__.py`, `output.py`; `tests/test_cli.py`

**Interfaces:**
- Produces: `Outcome(document: dict, warnings: list[dict], configuration_errors: list[dict], incomplete: bool)`;
  `emit(outcome: Outcome, action_name: str, as_json: bool, language: str, stdout, stderr) -> int` (warnings to
  standard error, warnings each line starting `warning:`, configuration errors `error:`; the JSON envelope
  `command`, `warnings`, `configuration_errors`, each with `code`, `values`, `message`, and, when an action stops,
  `error` with the same keys, written instead of the document (ruled 2026-11-20); exit 3 when `incomplete` or a
  configuration error exists);
  `Context(system: str, environ: Mapping[str, str], home: Path, now: datetime, new_uid: Callable[[], str],
  run: Callable, executable: Path, installation: str | None, ask: Callable[[str], str] | None, adapters:
  Sequence[Adapter], time_zone: Callable[[], str | None], version: str, uid: int | None)` (`executable` is the
  absolute path of the installed command, `shutil.which` of `ai-effort-ledger` (`ingestion.md` › Frequency), which
  a test replaces; `time_zone` from `system_time_zone` of Task 43, `version` from `writer_version()`, `uid` from
  `os.getuid()` where
  the system has it; tests pass a fixed `now`, a counting `new_uid`, a fake `run`, a temporary home,
  `support.adapters_for_tests(home)`, a fixed `time_zone`, and `version` `"0.1.0"` where a test creates a scheduler
  entry; `cli` builds `SetupContext` from it and passes `version` to `run_ingestion` and `ledger_event`) with
  `require_setup(store_option: Path | None) -> tuple[MachineConfiguration, PersonConfiguration, Path]` (the store
  folder is `--store`, else `store` of the machine configuration, else `default_store_folder`; `SetupRequired` when
  either configuration is missing) and `before_write()` (development guard with `version`, installation check with
  `refresh_machine` and `new_uid`). Every action that writes — `setup`, `ingest`,
  `machine label`, `config add`, a report with `--freeze`, `frozen remove`, and all actions of Tasks 51–53 — takes
  the lock and calls `before_write()`, and the task that writes the action tests both;
  `emit` has the parameter `configuration_errors_are_incomplete: bool = True`, and `config show` passes `False`
  (exit 0); `emit` also has `held_back_is_incomplete: bool = True`, and `timesheet confirm` passes `False`,
  because its entries are the declaration of the person.
  `INCOMPLETE_CODES = frozenset({"lost_events", "broken_line", "newer_schema_version",
  "held_back_events"})`: a warning with one of these codes, or a configuration error, sets `incomplete`
  (`command-line.md` › Exit codes); `timesheet confirm` does not count `held_back_events`.

- [ ] **Step 1: Write the failing tests** (every test gives a temporary home through the environment):

```python
def test_require_setup_without_configuration_stops(self):   # SetupRequired
def test_store_folder_order(self):         # --store, else store of the machine configuration, else the default
def test_json_envelope(self):              # command, warnings, configuration_errors with code/values/message
def test_warnings_go_to_standard_error(self):
def test_configuration_error_line_starts_error(self):
def test_json_stop_writes_error_envelope(self):  # a stopped action: error with code/values/message, exit 1 or 2
def test_italian_messages(self):
def test_before_write_refused_for_development_version(self):   # version "0.1.0.dev0", the variable unset in
                                                                # Context.environ -> DevelopmentVersion
def test_before_write_after_home_folder_copy(self):   # another installation -> new machine identifier
def test_each_incomplete_code_exits_3(self):     # emit: one case for each code of INCOMPLETE_CODES
def test_other_warnings_keep_exit_0(self):       # declared_value_below_measured, unknown_tool_name
def test_every_stop_error_has_its_texts(self):   # each exception class of the package with a class attribute
                                                 # code: the code is in STOP_CODES, with both texts
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `__init__.py` (the `Context`) and `output.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 49: `cli` — arguments, help, `main`

**Spec:** `command-line.md` › Form, › Output, › Commands, › Exit codes, › Setup (last paragraph); `architecture.md` ›
Runtime.

**Files:**
- Create: `src/ai_effort_ledger/cli/arguments.py`; Modify: `src/ai_effort_ledger/cli/__init__.py`, `tests/test_cli.py`,
  `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Consumes: `Context`, `Outcome`, `emit` (Task 48).
- Produces: `main(argv: list[str] | None = None, context: Context | None = None) -> int` (`None` builds the
  `Context` of the running process; calls `days.use_tzdata_only()`; maps stop errors to their exit code);
  `WrongUse` (stop error `wrong_use`, values `command` and `option`, `option` `None` when the fault names none,
  exit 2): `ArgumentParser.error` raises it, so a fault of `argparse` writes one line `error: <text in the output
  language>` and never the English text of `argparse`; an option whose value has a format (`--time`, `--key`, days,
  instants, versions, durations) is read as text and checked after `argparse`, and a wrong value raises `WrongValue`
  (Task 13) with the option and the value (`command-line.md` › Output, › Exit codes; ruled 2026-11-20);
  `build_arguments() -> argparse.ArgumentParser` (it registers every command of `command-line.md` ›
  Commands, whose actions Tasks 50–56 fill through a table of actions in `cli/__init__.py`; `main` imports the
  module of an action at its first call, so no action module is imported while the package loads and no import is
  circular; its help comes in the language of `--language`, with a help formatter of a fixed width, so an expected
  file of the help (Task 59) does not depend on the width of the terminal, and an own `-h` whose words, `usage` and
  `options` included, come from `language`; global `--store`, `--json`, `--language en|it`; report parameters
  `--idle-gap`, `--minimum-attention`, `--stale-limit`, `--headless-prompts yes|no`, `--timesheet-granularity`).

- [ ] **Step 1: Write the failing tests** (every test gives `--store` and a temporary home through the environment):

```python
def test_unknown_action_exits_2(self):       # one stderr line "error: ..." of wrong_use, no "usage:"
def test_wrong_duration_exits_2(self):      # wrong_value, key "--idle-gap"
def test_wrong_use_in_italian(self):        # --language it: the line of wrong_use is the Italian text
def test_action_before_setup_exits_1_and_asks_for_setup(self):
def test_help_lists_commands(self):        # "--help" and "<command> --help" exit 0 before setup
def test_help_in_italian(self):            # --language it: every word, also usage and options, from language
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `arguments.py`, and `main` in `__init__.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 50: `cli` — setup, schedule, ingest, machine label, config, index, version

**Spec:** `command-line.md` › Commands, › Setup, › Configuration entries, › JSON documents.

**Files:**
- Create: `src/ai_effort_ledger/cli/setup_actions.py`, `store_actions.py`; Modify:
  `src/ai_effort_ledger/cli/__init__.py`, `src/ai_effort_ledger/language.py`, `tests/test_language.py`,
  `tests/test_cli.py`

**Interfaces:**
- Consumes: `Context`, `emit`, `require_setup`, `before_write` (Task 48); `run_setup` (Task 44); `run_ingestion`
  (Task 29); the scheduler entries of Task 8; the configuration of Tasks 12 and 13; the store metadata of Task 14;
  the index of Tasks 25 and 26; `tzdata_version` (Task 27).

- [ ] **Step 1: Write the failing tests**, one for each command, text and JSON:

```python
def test_setup_json(self):        # machine, store, configuration_created, schedule, ingest
def test_schedule_show_create_remove(self):   # version "0.1.0"; remove without entry -> warning
                                              # no_schedule_entry, exit 0
def test_schedule_create_failed_scheduler_exits_1(self):   # fake run gives code 1 -> scheduler_failed
def test_schedule_create_refused_for_development_version(self):   # version "0.1.0.dev0" -> development_version,
                                                                  # exit 1
def test_ingest_counts_and_lost_events_exit_3(self):
def test_schedule_entry_runs_context_executable(self):   # the entry that schedule create writes runs
                                                         # the absolute path of Context.executable
def test_machine_label(self):
def test_config_show_layers_and_errors_exit_0(self):   # project_name_conflict; no event is read
def test_config_add_each_entry(self):         # --repository URL is normalized first; day-start
                                              # --from today -> the local day as YYYY-MM-DD
def test_config_add_wrong_value_exits_2(self):
def test_index_rebuild_counts(self):
def test_version_shows_tzdata(self):
def test_version_works_before_setup(self):
def test_store_actions_take_the_lock(self):   # setup, ingest, machine label, config add: StoreLock.__enter__
                                              # patched records the take; version "0.1.0.dev0" and the
                                              # variable unset -> exit 1
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the two files.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 51: `cli` — annotations, manual entries, retractions

**Spec:** `command-line.md` › Commands (`annotate`, `entry add`, `entries`, `retract`); `event-schema.md` › Fields.

**Files:**
- Create: `src/ai_effort_ledger/cli/entry_actions.py`; Modify: `src/ai_effort_ledger/cli/__init__.py`,
  `tests/test_cli.py`, `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Consumes: `Context`, `emit`, `require_setup` (Task 48); `ledger_events_between`, `confirmations_of`,
  `ledger_event_by_uid`, `tools_of_session` (Task 26); `entries_document` (Task 45); `WrongUse` (Task 49).

- [ ] **Step 1: Write the failing tests**:

```python
def test_annotate_session_and_interval(self):
def test_annotate_unknown_session_exits_1(self):
def test_annotate_ambiguous_session_needs_tool(self):
def test_project_given_as_name(self):
def test_entry_add_unattributed(self):        # --project - or no --project
def test_entries_lists_by_local_day(self):
def test_retract_and_retract_retraction(self):
def test_retract_unknown_event_uid_exits_1(self):   # names the target, exit 1 (`command-line.md` › Commands)
def test_retract_of_a_purge_exits_2(self):    # wrong_kind, nothing written
def test_annotate_without_project_or_work_item_exits_2(self):   # wrong_use
def test_entry_actions_take_the_lock(self):   # annotate, entry add, retract: as in Task 50
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write `entry_actions.py`** (these commands); each that writes takes the lock and calls
  `before_write()`; `entries` reads `ledger_events_between` with the parts of the day (Task 26) and keeps the
  manual entries, annotations, and retractions — a purge is not listed — and reads `confirmations_of`, whose `day`
  is the day, and gives `entries_document` (Task 45). `annotate --session` without `--tool`, when two agent tools
  hold the identifier,
  stops with the stop error `ambiguous_session` (values `session_id`, `tools`, exit 1), with its texts in `language`.
  `retract` of an `event_uid` of a kind other than the four of `command-line.md` › Commands stops with the stop
  error `WrongKind` (code `wrong_kind`, values `command`, `event_uid`, `kind`, exit 2; ruled 2026-11-20), which
  Task 53 also uses; `annotate` without `--project` and `--work-item` raises `WrongUse` (Task 49).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 52: `cli` — the figures of days, and timesheet confirmations

**Spec:** `command-line.md` › Timesheet; `metrics.md` › Declared values; `architecture.md` › Modules; ADR 0014.

**Files:**
- Create: `src/ai_effort_ledger/cli/figures.py`; Modify: `src/ai_effort_ledger/cli/entry_actions.py`,
  `src/ai_effort_ledger/cli/__init__.py`, `tests/test_cli.py`, `src/ai_effort_ledger/language.py`,
  `tests/test_language.py`

**Interfaces:**
- Consumes: Tasks 12, 25–41, 45, 46.
- Produces: `Figures(selection: Selection, attribution: Attribution, days: list[DayFigures])`;
  `figures_of_days(context: Context, store_folder: Path, person: PersonConfiguration, parameters: ReportParameters,
  first: date, last: date) -> Figures` (`store_folder` and `person` from `Context.require_setup`, `parameters` from
  `resolve_parameters` of Task 12 with the report options): it builds `MetricsParameters` from `parameters` and
  `effective_category(person.category_rules)` (Task 36), then runs `select` → `compute_metrics` → `attribute` (with
  `selection.confirmations`, Task 38) → `day_figures` once (`architecture.md` › Modules: `reports` imports neither
  `metrics` nor `attribution`); `timesheet confirm` and every report command use it (ruled 2026-11-19).

- [ ] **Step 1: Write the failing tests**:

```python
def test_figures_of_days_runs_each_stage_once(self):
def test_timesheet_confirm_without_options(self):     # confirms the proposal shown by "timesheet <day>"
def test_timesheet_confirm_set_and_total(self):
def test_timesheet_confirm_future_day_exits_1(self):   # stop error day_after_today (values day), texts in
                                                        # language
def test_confirm_names_latest_in_replaces(self):
def test_confirm_warns_held_back_and_exits_0(self):
def test_confirm_warns_when_replaced_is_later(self):  # clocks differ -> confirmation_before_replaced
def test_timesheet_retract(self):
def test_timesheet_retract_unknown_day_exits_1(self):   # a day without confirmation: names the day, exit 1
def test_timesheet_actions_take_the_lock(self):   # timesheet confirm, timesheet retract: as in Task 50
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Extend `entry_actions.py`.**
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 53: `cli` — purges

**Spec:** `command-line.md` › Purge; `architecture.md` › Data flow (step 10); `event-schema.md` › Keys and
invariants (purges); ADR 0008, ADR 0015.

**Files:**
- Modify: `src/ai_effort_ledger/cli/entry_actions.py`, `src/ai_effort_ledger/cli/__init__.py`,
  `tests/test_cli.py`, `src/ai_effort_ledger/language.py`, `tests/test_language.py`

**Interfaces:**
- Consumes: `keys_written_below`, `sessions_of_keys`, `ledger_event_by_uid` (Task 26); `PurgeSet` (Task 15);
  `remove_blocked_copies` (Task 29); `WrongKind` (Task 51), for a `--key` whose event is a purge (`command-line.md`
  › Purge; ruled 2026-11-20); `WrongUse` (Task 49).

- [ ] **Step 1: Write the failing tests**:

```python
def test_purge_by_key_and_by_writer_version(self):
def test_purge_needs_yes_without_terminal(self):      # written false
def test_purge_forget_with_corrected_version_exits_2(self):   # wrong_use
def test_purge_warns_key_source_gone(self):
def test_purge_with_corrected_version_names_sessions(self):
def test_purge_takes_the_lock(self):          # as in Task 50
def test_purge_of_a_purge_exits_2(self):      # --key of a purge -> wrong_kind, nothing written
def test_purge_removes_own_blocked_copies_at_once(self):   # own segments rewritten before the command ends;
                                                          # the segment of another machine is unchanged
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Extend `entry_actions.py`.** After it writes the purge, under the same lock, the command calls
  `remove_blocked_copies` with the purges of the store and the new one (`command-line.md` › Purge; ruled
  2026-11-20).
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 54: Fixture stores of the report tests

**Spec:** `architecture.md` › Tests (report tests); `command-line.md` › Reports, › Frozen reports; acceptance
criterion 9.

**Files:**
- Create: `tests/test_reports_output.py`; Modify: `tests/support.py`

**Interfaces:**
- Consumes: `Context` (Task 48); `figures_of_days` (Task 52); `freeze` (Task 47); `support.write_session` (Task 17).
- Produces: `support.normalize(text: str, roots: Sequence[Path]) -> str` (Global Constraints: the fixed marks
  that make one committed expected file fit every run and every operating system); `support.fixture_store(name:
  str, home: Path) -> Context` for the names `measured_day`, `declared_day`,
  `manual_entries`, `annotations`, `retraction`, and `frozen_period`: it writes the native logs, the configurations,
  and the events of that store in the temporary `home`, and gives the `Context` of the tests, with a fixed `now`,
  `version` `"0.1.0"`, and a `new_uid` that counts `00000000-0000-4000-8000-000000000001`, `…2`; the machine
  configuration holds a fixed machine identifier and the salted hash of the `installation` of the `Context`, so that
  `before_write()` keeps it; the segment path of a month is the same at each run, the bytes are not: every `cwd` is
  below the temporary folder (Global Constraints), so the number of bytes read and the chained hash of each segment
  of the report record differ at each run, and the comparison of the report tests masks them; `frozen_period` keeps
  a frozen report that `fixture_store` builds through `figures_of_days`
  (Task 52), the documents of Task 45, and `freeze` (Task 47) — the same pipeline that the report actions of
  Task 55 use — and then gets an identity rule.

- [ ] **Step 1: Write the failing tests** in `tests/test_reports_output.py`:

```python
def test_normalize_masks_per_run_values(self):  # the paths under the roots, the bytes read and the chained
                                                 # hashes of the segments, and every tzdata version
def test_each_fixture_store_builds(self):           # every name gives a store that figures_of_days reads
def test_states_of_the_fixture_days(self):          # measured_day "measured", declared_day "declared"
def test_frozen_period_has_a_later_rule_change(self):   # one frozen report; an identity rule after its frozen_at
```

- [ ] **Step 2: Run and see it fail.**
- [ ] **Step 3: Write the fixture stores** in `tests/support.py` (`fixture_store(name, home)`): a measured day; a
  declared day; manual entries of both modes; annotations; a retraction; a frozen period with a later rule change.
- [ ] **Step 4: Run and see it pass**, then the full suite.
- [ ] **Step 5: Checkpoint.**

### Task 55: `cli` — the report of a period, of a day, and the timesheet of a day, in English (gate G7)

**Spec:** `command-line.md` › Reports, › Timesheet, › JSON documents; acceptance criterion 9.

**Files:**
- Create: `src/ai_effort_ledger/cli/report_actions.py`, `tests/fixtures/expected/en/` (one `.txt` and one `.json`
  for each command of this task); Modify: `src/ai_effort_ledger/cli/__init__.py`,
  `src/ai_effort_ledger/language.py`, `tests/test_language.py`, `tests/test_reports_output.py`,
  `tests/test_cli.py`

**Interfaces:**
- Consumes: `figures_of_days` (Task 52); the documents and text of Tasks 45, 46; `differences`, `latest_frozen_by_day`
  (Task 47); the fixture stores of Task 54.

- [ ] **Step 1: Write the failing report tests** for `report timesheet`, `report day`, and `timesheet <day>`: the
  text and the JSON output in English against the expected files; the comparison runs both sides through
  `support.normalize` (Global Constraints), which masks what differs at each run or on another operating system.
- [ ] **Step 2: Write `report_actions.py`** for these commands; a report of a period that a frozen report holds also
  gives `differences` and `changed` (`command-line.md` › Reports, › JSON documents). Write each expected file by hand
  from the specs and the layout of Task 46 before its test passes, never by copying the output.
  When a test fails, recompute the value by hand from the fixture definition and the layout of Task 46: correct
  the expected file where the recomputation shows it wrong, and fix the code only where the spec supports the
  divergence. Gate G7: show the
  owner the first expected text file of each report and wait for the approval before the next file.
- [ ] **Step 3: Run and see it pass**, then the full suite.
- [ ] **Step 4: Checkpoint.**

### Task 56: `cli` — sessions, entries output, and frozen reports, in English

**Spec:** `command-line.md` › Commands (`sessions`, `entries`), › Frozen reports, › JSON documents; acceptance
criterion 9.

**Files:**
- Modify: `src/ai_effort_ledger/cli/report_actions.py`, `src/ai_effort_ledger/cli/__init__.py`,
  `src/ai_effort_ledger/language.py`, `tests/test_language.py`, `tests/test_reports_output.py`,
  `tests/test_cli.py`; `tests/fixtures/expected/en/` (one `.txt` and one `.json` for each command of this task)

**Interfaces:**
- Consumes: `figures_of_days` (Task 52); `Attribution.session_parts` (Task 39); `freeze`, `differences`,
  `latest_frozen_by_day` (Task 47); the fixture stores of Task 54.

- [ ] **Step 1: Write the failing report tests** for `sessions <day>`, `entries` (its output only; Task 51 writes the
  action), `frozen list`, `frozen show`, and `--freeze`, in text and JSON, in English.
- [ ] **Step 2: Write the actions**: `sessions`, `frozen list`, `frozen show`, `frozen remove`, and `--freeze`; a
  report with `--freeze` and `frozen remove` take the lock and call `before_write()` (`architecture.md` ›
  Concurrency), with `test_frozen_actions_take_the_lock` (as in Task 50), `test_frozen_remove_of_unknown_id_exits_1`,
  and `test_frozen_show_of_unknown_id_exits_1` in `tests/test_cli.py`. Write each expected file by hand from the
  specs before its test passes.
- [ ] **Step 3: Run and see it pass**, then the full suite.
- [ ] **Step 4: Checkpoint.**

### Task 57: report tests in Italian

**Spec:** `command-line.md` › Reports (Italian); `GLOSSARY.md` (`_Italian_` lines); acceptance criterion 9.

**Files:**
- Create: `tests/fixtures/expected/it/` (the Italian `.txt` and `.json` of each report command of Tasks 55, 56);
  Modify: `tests/test_reports_output.py`, `src/ai_effort_ledger/language.py` where a text is missing

- [ ] **Step 1: Write the expected files by hand** with the `_Italian_` terms of the glossary.
- [ ] **Step 2: Write the tests** with `--language it`; run and see the missing texts fail.
- [ ] **Step 3: Complete the texts**, run, then the full suite.
- [ ] **Step 4: Checkpoint.**

### Task 58: report tests of `setup`, `schedule`, `ingest`, and `machine label`

**Spec:** `command-line.md` › Commands, › Setup, › JSON documents, › Exit codes; acceptance criterion 9.

**Files:**
- Create: `tests/fixtures/expected/en/` and `it/` files for each command of this task; Modify:
  `tests/test_reports_output.py`

- [ ] **Step 1: Write the expected files by hand** (text and JSON, English and Italian) for `setup`, `schedule
  show|create|remove`, `ingest`, and `machine label`, with the fixed `now`, `new_uid`, and `version` of Task 54 and
  a fake scheduler.
- [ ] **Step 2: Write the tests**; run; fix the code where a test
  fails; the expected file changes only when a computation by hand from the fixture definition and the layout
  of Task 46 shows it wrong, or when a spec sentence supports it.
- [ ] **Step 3: Run the full suite.**
- [ ] **Step 4: Checkpoint.**

### Task 59: report tests of `config`, `index rebuild`, `version`, and help

**Spec:** `command-line.md` › Commands, › Configuration entries, › JSON documents, › Exit codes; acceptance
criterion 9.

**Files:**
- Create: `tests/fixtures/expected/en/` and `it/` files for each command of this task; Modify:
  `tests/test_reports_output.py`

- [ ] **Step 1: Write the expected files by hand** (text and JSON, English and Italian) for `config show`, `config
  add`, `index rebuild`, `version`, and `--help` and `<command> --help` (text only: › JSON documents gives `--help`
  no document), with the fixed `now`, `new_uid`, and `version` of Task 54.
- [ ] **Step 2: Write the tests**; run; fix the code where a test
  fails; the expected file changes only when a computation by hand from the fixture definition and the layout
  of Task 46 shows it wrong, or when a spec sentence supports it.
- [ ] **Step 3: Run the full suite.**
- [ ] **Step 4: Checkpoint.**

### Task 60: report tests of the commands that write events

**Spec:** `command-line.md` › Commands, › Timesheet, › Purge, › JSON documents, › Exit codes; acceptance criterion 9.

**Files:**
- Create: `tests/fixtures/expected/en/` and `it/` files for each command of this task; Modify:
  `tests/test_reports_output.py`

- [ ] **Step 1: Write the expected files by hand** (text and JSON, English and Italian) for `annotate`, `entry add`,
  `timesheet confirm`, `timesheet retract`, `retract`, `purge`, and `frozen remove`, with the fixed `now` and
  `new_uid` of Task 54.
- [ ] **Step 2: Write the tests**; run; fix the code where a test
  fails; the expected file changes only when a computation by hand from the fixture definition and the layout
  of Task 46 shows it wrong, or when a spec sentence supports it.
- [ ] **Step 3: Run the full suite.**
- [ ] **Step 4: Checkpoint.** Gate G6: ask the owner whether to push the branch.

## Milestone 9 — Suites across modules, benchmark, end of the phase, first release

### Task 61: Store tests with two machines

**Spec:** `architecture.md` › Tests (store tests); acceptance criteria 2, 5, 6.

**Files:**
- Create: `tests/test_store_machines.py`; Modify: `tests/support.py` (`copy_segments(source_store, target_store,
  cut_last_line: bool)`: a file-sync service that copies segments, with a delay shown as a half-written last line)

- [ ] **Step 1: Write the tests**:

```python
def test_half_written_last_line_on_other_machine_is_ignored(self):
def test_broken_line_warns_with_segment_and_number(self):      # exit 3, also for a report after an ingest
def test_purge_without_corrected_version_keeps_key_out_on_both(self):
def test_corrected_copy_replaces_blocked_earlier_copy(self):
    # machine A stores E with version "0.1.0" (run_ingestion, Task 29); a purge names 0.1.1; machine B
    # stores the corrected E with version "0.1.1"; both report it
def test_confirmations_of_one_day_from_two_machines(self):     # latest wins, confirmation_not_seen
def test_confirmation_seen_after_copy_has_no_warning(self):
def test_frozen_remove_on_other_machine_exits_1(self):
```

- [ ] **Step 2: Run**; fix where a test fails, flag where the spec is silent. A fix goes into the code of one module,
  with a test in that module's test file; a fix that touches more than one module stops the task for the owner.
- [ ] **Step 3: Run the full suite.**
- [ ] **Step 4: Set the Backlog task to Done.**
- [ ] **Step 5: Checkpoint.**

### Task 62: Order tests

**Spec:** `architecture.md` › Tests (order tests); acceptance criterion 2.

**Files:**
- Create: `tests/test_order.py`

- [ ] **Step 1: Write the tests**:

```python
def test_shuffled_file_order_gives_same_store(self):   # same keys, same fields except ingested_at
def test_segment_order_gives_same_reports(self):       # segments of two machines indexed in both orders
def test_day_equals_day_inside_week(self):
def test_tool_result_after_settle_time(self):          # the store differs only as ingestion.md › Adapters says
def test_fork_read_before_its_original(self):          # the store differs only as ingestion.md › Adapters says
def test_repository_identity_at_first_ingestion(self): # the store differs only as ingestion.md › Adapters says
```

- [ ] **Step 2: Run**; fix or flag. A fix goes into the code of one module, with a test in that module's test file; a
  fix that touches more than one module stops the task for the owner.
- [ ] **Step 3: Run the full suite.**
- [ ] **Step 4: Set the Backlog task to Done.**
- [ ] **Step 5: Checkpoint.**

### Task 63: Privacy test

**Spec:** `architecture.md` › Tests (privacy test); acceptance criterion 7; ADR 0003.

**Files:**
- Create: `tests/test_privacy.py`

- [ ] **Step 1: Write the test**: ingest every fixture of `tests/fixtures/claude_code/`; every line of the store
  holds only fields of `events.FIELDS` with `schema_version` 1; each text field of a fixture (prompts, responses,
  tool input, code, file paths of tool input) holds an invented marker word, and no marker word appears in any
  file of the store folder, read as bytes — the segments, the store metadata, the person configuration, the
  frozen reports — nor in the local index of the machine-local data folder.
- [ ] **Step 2: Run**; a failure is a defect of the adapter.
- [ ] **Step 3: Run the full suite.**
- [ ] **Step 4: Set the Backlog task to Done.**
- [ ] **Step 5: Checkpoint.**

### Task 64: Benchmark through the command line

**Spec:** `architecture.md` › Tests (benchmark); acceptance criterion 10.

**Files:**
- Modify: `tests/benchmark.py`

**Interfaces:**
- Consumes: `write_native_logs`, `main` (Tasks 30, 42); `cli.main` (Task 49), `Context` (Task 48);
  `write_machine_configuration`, `create_person_configuration` (Task 13).
- Produces: both times run through `cli.main(argv, context)`: the first `ingest`, and `report timesheet` of one month.
  The script builds the `Context` itself, never the one of the running process: a temporary home, an `environ` that
  names only temporary folders and `AI_EFFORT_LEDGER_DEVELOPMENT=1`, a fake `run`, a fixed `time_zone`, and
  `ClaudeCodeAdapter(managed_file=<temporary file>)` as its adapter. Before the timed `ingest` it writes the machine
  configuration and the person configuration with the functions of Task 13; as in Task 30, it imports nothing from
  `tests/support.py`.

- [ ] **Step 1: Change the script** and run it with `--days 1 --sessions 2 --lines 50`: it completes and prints two
  times.
- [ ] **Step 2: Run it with the defaults** on the development machine and give the seconds to the owner; the targets
  are less than 60 s for the first ingestion and less than 5 s for the timesheet.
- [ ] **Step 3: If a target fails**, profile with `cProfile`, fix, and run again; a second failure stops the
  task for the owner.
- [ ] **Step 4: Checkpoint.**

### Task 65: End of the phase

**Spec:** `product.md` › Phase 1 (acceptance criteria), › Phases; CLAUDE.md › Documents.

**Files:**
- Modify: `README.md`, `CLAUDE.md`

- [ ] **Step 1: Check each acceptance criterion** against the table below; each has a passing test, except
  criterion 10, which has the dated note of the benchmark (`architecture.md` › Tests).
- [ ] **Step 2: Check the `To be confirmed` sections**: every item marked "before the end of Phase 1" or "in Phase 1"
  is closed by a ruling. The items and the task that closes each: `claude-code-adapter.md` › interruptions, subagent
  link without `agentId` and nested subagents, input keys of `MultiEdit` and `NotebookEdit` (Task 16, gate G2);
  `configuration.md` › CLDR release of the Windows time-zone table (Task 43, gate G3).
- [ ] **Step 3: Update `README.md`**: installation with `uv tool install git+<repository URL>@v<version>` or
  `pipx` (`architecture.md` › Runtime), `setup`, the daily timesheet, `schedule remove`, and how to remove the
  package; update `CLAUDE.md` › Core: `python -I tests/style.py` and `python -I tests/benchmark.py` beside the
  line of the tests.
- [ ] **Step 4: Run the full suite and the static check**, and the workflow on GitHub after a push (gate G6);
  recommend `/effort xhigh` to the owner for the final verification pass, and wait.
- [ ] **Step 5: Set the Backlog task to Done**, then the checkpoint.
- [ ] **Step 6: Merge** the branch into `master` when the owner asks.

### Task 66: First release 0.1.0 (gate G5)

**Spec:** `architecture.md` › Release, › Tests (benchmark); `product.md` › Phase 1 (acceptance criterion 10), › End of
the phase.

**Files:**
- Modify: `pyproject.toml`, this plan, the Backlog task file of the task; Create:
  `docs/research/benchmark-<yyyy>-<mm>.md`

It runs on `master` after the merge.

- [ ] **Step 1: Run the tests**: the full suite, the static check, and the workflow on the merge commit (the
  owner asks for the push of `master`).
- [ ] **Step 2: Gate G5.** Ask the owner to run `python -I tests/benchmark.py` on a laptop; write
  `docs/research/benchmark-<yyyy>-<mm>.md` with the seconds and the processor; the targets are less than 60 s for the
  first ingestion and less than 5 s for the timesheet. A failed target stops the release (Steps 3–6); the owner
  decides between a fix on a branch and a ruling that accepts the seconds of the note.
- [ ] **Step 3: Set `version = "0.1.0"`** in `pyproject.toml`, set the status line of this plan to
  `Status: completed`, and commit them with the note of Step 2.
- [ ] **Step 4: On the owner's word**, tag the commit `v0.1.0` and push the commit and the tag.
- [ ] **Step 5: Set `version = "0.1.1.dev0"`** in `pyproject.toml` (`architecture.md` › Release, step 5) and
  commit; push it only when the owner asks.
- [ ] **Step 6: Install** with the line of `README.md` in a temporary folder and run `ai-effort-ledger version`;
  then set the Backlog task of Task 66 to Done and commit its file on `master` (`Task 66: Done`); push only when
  the owner asks.

## Acceptance criteria and their tasks

Each row names the tasks whose tests assert the criterion; the tasks that only build what the tests check stay
unlisted.

| Criterion | Tasks |
|---|---|
| 1. After `setup`, all native logs in retention are stored; a second `ingest` adds none | 29, 44, 50 |
| 2. Same store at any hour and in any order; same reports from segments in any order | 22, 25, 26, 61, 62 |
| 3. Prototype scenarios give the hand-computed figures | 32–35 |
| 4. Parts add up to the day in the JSON document: measured, with manual entries, declared | 38, 40, 45 |
| 5. A day confirmed on two machines shows the latest confirmation and a warning | 40, 61 |
| 6. Purge with a corrected version gives corrected events; without one keeps keys out | 15, 29, 61 |
| 7. No text of the fixtures in the store | 18–20, 63 |
| 8. Tests pass on Windows, Linux, macOS with Python 3.11 and the newest release | 3, 65 (gate G6 at each milestone) |
| 9. Report tests of every command, text and JSON, English and Italian | 54–60 |
| 10. Benchmark: first ingestion < 1 min, timesheet of a month < 5 s | 30, 42, 64, 66 |
