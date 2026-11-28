"""Tests of the attribution: the matching of the identity rules and of the category
rules, the names of the projects, the buckets of the events with the overrides of the
annotations, and the split rule with the figures of the buckets (configuration.md ›
Matching, metrics.md › Attribution, ADR 0009, ADR 0019, ADR 0021)."""

import unittest
from collections.abc import Sequence
from datetime import date, time
from typing import Any

import support
from ai_effort_ledger import events
from ai_effort_ledger.attribution import annotations, names, rules, split
from ai_effort_ledger.configuration import (
    CategoryRule,
    DayStartEntry,
    IdentityRule,
    PersonConfiguration,
    ProjectName,
    TimeZoneEntry,
    WorkItemName,
)
from ai_effort_ledger.metrics import (
    AgentPart,
    HumanInterval,
    Metrics,
    MetricsParameters,
    Span,
    compute_metrics,
    intersect,
    total,
    union,
)

_DAY = date(2026, 6, 15)
_MACHINE = "3f0d5a1e-8c2b-4d6e-9f0a-1b2c3d4e5f60"
_TOOL = "example_tool"
_SESSION = "session-1"
_REPO = "example.org/team/app"
_SESSION_OF = {"tool": _TOOL, "session_id": _SESSION}


def _person(
    projects: list[ProjectName] | None = None,
    identity_rules: list[IdentityRule] | None = None,
    category_rules: list[CategoryRule] | None = None,
    work_items: list[WorkItemName] | None = None,
) -> PersonConfiguration:
    """A person configuration with the invented entries given and no other fact."""
    return PersonConfiguration(
        time_zones=[TimeZoneEntry("Etc/UTC", support.utc("1970-01-01T00:00"), 2)],
        day_starts=[DayStartEntry(time(0, 0), date(1970, 1, 1), 3)],
        projects=list(projects or []),
        work_items=list(work_items or []),
        identity_rules=list(identity_rules or []),
        category_rules=list(category_rules or []),
        preferred_remotes=["origin"],
        settle_time=14400,
        report={},
    )


def _event(timestamp: str, event_uid: str, **overrides: Any) -> events.Event:
    """A complete invented event of a session, with the identity fields the overrides
    give; the local days of the tests make its instant fall on `_DAY`."""
    event: events.Event = {
        "schema_version": events.SCHEMA_VERSION,
        "source": "example_tool",
        "native_id": "native-" + event_uid,
        "event_uid": event_uid,
        "timestamp": timestamp,
        "writer_version": "0.1.0",
        "actor": "agent",
        "kind": "tool_call",
        "machine": _MACHINE,
        "tool": _TOOL,
        "session_id": _SESSION,
    }
    event.update(overrides)
    return event


def _note(timestamp: str, event_uid: str, **overrides: Any) -> events.Event:
    """A complete invented annotation that a command writes: of a session when it names
    one through `annotates`, of an interval when it holds `start` and `end`."""
    event: events.Event = {
        "schema_version": events.SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": event_uid,
        "timestamp": timestamp,
        "writer_version": "0.1.0",
        "actor": "human",
        "kind": "annotation",
        "machine": _MACHINE,
    }
    event.update(overrides)
    return event


def _rule(
    project: str = "example-product",
    repository: str | None = None,
    folder: str | None = None,
    branch: str | None = None,
    first: date | None = None,
    last: date | None = None,
    line: int = 1,
) -> IdentityRule:
    """One identity rule of the person configuration, with invented values."""
    return IdentityRule(project, repository, folder, branch, first, last, line)


def _tool(tool: str, category: str, line: int) -> CategoryRule:
    """One category rule of the person configuration, with invented values."""
    return CategoryRule(tool, category, line)


_PARAMETERS = MetricsParameters(idle_gap=600, minimum_attention=60, stale_limit=14400,
                                headless_prompts=False)
"""The report parameters of the split tests, at the defaults of the ledger."""

_ALPHA = "example.org/team/alpha"
_BETA = "example.org/team/beta"


def _at(clock: str) -> str:
    """The instant of the day of the tests at the `HH:MM` clock time."""
    return f"2026-06-15T{clock}:00.000Z"


def _ms(clock: str) -> int:
    """The instant of the day of the tests as milliseconds since the epoch."""
    return round(support.utc(_at(clock)).timestamp() * 1000)


def _window(first: str, last: str) -> list[Span]:
    """The window of a report as the span from the first to the last instant."""
    return [(round(support.utc(first).timestamp() * 1000),
             round(support.utc(last).timestamp() * 1000))]


_WHOLE_DAY = _window("2026-06-15T00:00", "2026-06-16T00:00")
"""The window of the whole day of the tests."""


def _signal(timestamp: str, event_uid_value: str, **overrides: Any) -> events.Event:
    """A prompt of the person, the human signal of the split tests."""
    return _event(timestamp, event_uid_value, kind="prompt", actor="human", **overrides)


def _manual_entry(
    start: str,
    end: str,
    event_uid_value: str,
    timestamp: str | None = None,
    mode: str = "overlapping",
    **overrides: Any,
) -> events.Event:
    """A manual entry that a command writes: the interval the person declares, with its
    mode and its fields; the timestamp is the instant of the writing, the start by
    default."""
    made: events.Event = {
        "schema_version": events.SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": event_uid_value,
        "timestamp": timestamp or start,
        "writer_version": "0.1.0",
        "actor": "human",
        "kind": "manual_entry",
        "machine": _MACHINE,
        "start": start,
        "end": end,
        "manual_mode": mode,
    }
    made.update(overrides)
    return made


def _turn(
    session: str, prompt: str, output: str, repository: str, **fields: Any,
) -> list[events.Event]:
    """A prompt of the person and the output that ends the turn of the agent of one
    session: the two events of a turn of the agent-time tests, in the project that their
    repository identity gives."""
    return [
        _signal(prompt, f"uid-{session}-prompt", session_id=session, repo_hint=repository,
                **fields),
        _event(output, f"uid-{session}-output", kind="agent_output", actor="system",
               session_id=session, repo_hint=repository, **fields),
    ]


def _delegating_agent(result: str, output: str) -> list[events.Event]:
    """The events of the main agent of the session of the tests: a prompt at 10:00, a call
    of a tool of the category `delegate` at 10:01, its result, and the output that ends
    the turn."""
    return [
        _signal(_at("10:00"), "uid-prompt", repo_hint=_REPO),
        _event(_at("10:01"), "uid-call", kind="tool_call", tool_name="Agent",
               tool_category="delegate", call_id="call-1", repo_hint=_REPO),
        _event(result, "uid-result", kind="tool_result", actor="system", call_id="call-1",
               repo_hint=_REPO),
        _event(output, "uid-output", kind="agent_output", actor="system", repo_hint=_REPO),
    ]


def _subagent(woken: str, done: str, mode: str) -> list[events.Event]:
    """The two events of the subagent `agent-1` of the session of the tests: the input of
    its parent that wakes it and the output that ends its turn, in the mode given."""
    fields: dict[str, Any] = {"agent_id": "agent-1", "parent_agent_id": _SESSION,
                              "subagent_mode": mode, "repo_hint": _REPO}
    return [
        _event(woken, "uid-subagent-input", kind="notification", actor="system",
               input_origin="parent", **fields),
        _event(done, "uid-subagent-output", kind="agent_output", actor="system", **fields),
    ]


def _confirmation(entries: list[dict[str, Any]]) -> events.Event:
    """A timesheet confirmation that a command writes, with the entries of one day."""
    return {
        "schema_version": events.SCHEMA_VERSION,
        "source": "ledger",
        "event_uid": "confirmation-uid",
        "timestamp": _at("18:00"),
        "writer_version": "0.1.0",
        "actor": "human",
        "kind": "timesheet_confirmation",
        "machine": _MACHINE,
        "day": _DAY.isoformat(),
        "entries": entries,
    }


class PatternTests(unittest.TestCase):
    """The narrower-pattern test of configuration.md › Matching."""

    def test_pattern_narrower(self) -> None:
        """A pattern whose every match the other pattern also matches is narrower: the
        branch of one contract is narrower than any branch, an exact name is narrower
        than a pattern that holds it, and a pattern of every branch is not narrower."""
        self.assertTrue(rules.pattern_narrower("feat/*", "*"))
        self.assertTrue(rules.pattern_narrower("feat/a", "feat/*"))
        self.assertFalse(rules.pattern_narrower("*", "feat/*"))


class FolderTests(unittest.TestCase):
    """The matching of the folder of a rule with the folder of an event."""

    def test_folder_matches_inside_and_separators(self) -> None:
        """A Windows folder of the rule matches the folder itself and every folder inside
        it, with `/` and `\\` as the same separator and without regard to case."""
        self.assertTrue(rules.folder_matches(r"D:\Work", "d:/work/app"))
        self.assertTrue(rules.folder_matches(r"D:\Work", "d:/work"))
        self.assertFalse(rules.folder_matches(r"D:\Work", r"D:\Workbase\app"))
        self.assertFalse(rules.folder_matches(r"D:\Work\app", r"D:\Work"))

    def test_unix_folder_matches_with_case(self) -> None:
        """A folder of the rule that is no Windows path compares with regard to case, and
        name by name, so a longer name is no folder inside."""
        self.assertFalse(rules.folder_matches("/home/a/App", "/home/a/app"))
        self.assertFalse(rules.folder_matches("/home/a/App", "/home/a/AppBase"))
        self.assertTrue(rules.folder_matches("/home/a/App", "/home/a/App/build"))

    def test_foreign_folder_compares_as_text(self) -> None:
        """The folder of the event is a path of another operating system, such as a folder
        inside a virtual machine: the two paths compare as text, the case decided by the
        folder of the rule, and the ledger never asks whether the folder exists."""
        self.assertTrue(rules.folder_matches("/vm/work/app", r"\vm\work\app\src"))
        self.assertFalse(rules.folder_matches("/vm/work/app", r"\vm\work\App\src"))
        self.assertTrue(rules.folder_matches(r"D:\Work\Product", "d:/work/PRODUCT/branch"))


class IdentityRuleTests(unittest.TestCase):
    """The project that the identity rules give to the observations of an event."""

    def test_date_range_both_ends_included(self) -> None:
        """A rule with the range from 2026-03-01 to 2026-06-30 matches the first day and
        the last day of the range, and no day before it or after it."""
        span = [_rule(first=date(2026, 3, 1), last=date(2026, 6, 30), line=4)]
        self.assertEqual(rules.project_of(None, None, None, date(2026, 3, 1), span),
                         ("example-product", None))
        self.assertEqual(rules.project_of(None, None, None, date(2026, 6, 30), span),
                         ("example-product", None))
        self.assertIsNone(rules.project_of(None, None, None, date(2026, 2, 28), span)[0])
        self.assertIsNone(rules.project_of(None, None, None, date(2026, 7, 1), span)[0])

    def test_most_specific_rule_wins(self) -> None:
        """A matching rule with one more condition wins, and a matching rule with one
        narrower value wins over the rules that hold the same conditions."""
        wide = _rule(folder=r"D:\Work", line=2)
        deep = _rule(folder=r"D:\Work\app", branch="release-*", project="app-release",
                     line=3)
        star = _rule(folder=r"D:\Work", branch="*", project="any-branch", line=4)
        narrow = _rule(folder=r"D:\Work", branch="release-*", project="app-branch", line=5)
        self.assertEqual(rules.project_of(None, r"D:\Work\app", "release-5", _DAY,
                                          [wide, deep]), ("app-release", None))
        self.assertEqual(rules.project_of(None, r"D:\Work\app", "release-5", _DAY,
                                          [star, narrow]), ("app-branch", None))

    def test_equal_specificity_is_configuration_error(self) -> None:
        """Two matching rules of which neither is more specific apply none: the event has
        no project and the error names the two rules with their lines."""
        left = _rule(folder=r"D:\Work", branch="release-*", project="left", line=2)
        right = _rule(folder=r"D:\Work\app", branch="*", project="right", line=3)
        project, error = rules.project_of(None, r"D:\Work\app", "release-5", _DAY,
                                          [left, right])
        self.assertIsNone(project)
        self.assertEqual(error["code"], "identity_rule_conflict")
        self.assertEqual(error["values"],
                         {"first": "line 2 (left)", "second": "line 3 (right)"})

    def test_duplicate_pattern_is_configuration_error(self) -> None:
        """Two identity rules of the same conditions are a conflict, as two category
        rules of the same tool name are: neither is more specific, so neither applies
        and the event stays unattributed."""
        same = [_rule(folder=r"D:\Work", line=2), _rule(folder=r"D:\Work", line=3)]
        project, error = rules.project_of(None, r"D:\Work\app", None, _DAY, same)
        self.assertIsNone(project)
        self.assertEqual(error["code"], "identity_rule_conflict")
        self.assertEqual(error["values"],
                         {"first": "line 2 (example-product)",
                          "second": "line 3 (example-product)"})

    def test_default_rule_only_without_matching_rule(self) -> None:
        """Without a matching rule the project is the repository identity itself, and an
        event without a repository identity stays unattributed."""
        configured = [_rule(repository="example.org/team/other", project="other", line=2)]
        self.assertEqual(rules.project_of("example.org/team/app", None, None, _DAY,
                                          configured), ("example.org/team/app", None))
        self.assertEqual(rules.project_of("example.org/team/app", None, None, _DAY, []),
                         ("example.org/team/app", None))
        self.assertEqual(rules.project_of(None, None, None, _DAY, configured),
                         (None, None))


class CategoryRuleTests(unittest.TestCase):
    """The category that the category rules give to the name of a tool."""

    def test_category_rule_replaces_stored_category(self) -> None:
        """The category of the matching rule replaces the category that the adapter
        stored, and a tool name that no rule matches keeps the stored one."""
        configured = [_tool("mcp__*", "web", 2)]
        self.assertEqual(rules.category_of("mcp__search", "other", configured),
                         ("web", None))
        self.assertEqual(rules.category_of("Read", "read", configured), ("read", None))

    def test_category_conflict_keeps_stored_category(self) -> None:
        """Two matching rules of which neither is narrower leave the tool in the category
        that the adapter stored, and the error names the two rules."""
        both = [_tool("mcp__*", "web", 2), _tool("*search*", "search", 3)]
        category, error = rules.category_of("mcp__search", "other", both)
        self.assertEqual(category, "other")
        self.assertEqual(error["code"], "category_rule_conflict")
        self.assertEqual(error["values"],
                         {"first": "line 2 (web)", "second": "line 3 (search)"})
        same = [_tool("Spawn", "delegate", 2), _tool("Spawn", "other", 3)]
        category, error = rules.category_of("Spawn", "edit", same)
        self.assertEqual((category, error["code"]), ("edit", "category_rule_conflict"))

    def test_effective_category_of_a_tool_call(self) -> None:
        """The callable that the parameters hold gives the category of the rules to a tool
        call whose name a rule matches, the stored category to the other tool calls, and
        the stored category to an event of another kind."""
        effective = rules.effective_category([_tool("Spawn", "delegate", 5)])
        spawn = {"kind": "tool_call", "tool_name": "Spawn", "tool_category": "other"}
        self.assertEqual(effective(spawn), "delegate")
        read = {"kind": "tool_call", "tool_name": "Read", "tool_category": "read"}
        self.assertEqual(effective(read), "read")
        self.assertEqual(effective({"kind": "agent_output"}), "other")


class NameTests(unittest.TestCase):
    """The names of the projects and the unknown projects of the declared events
    (metrics.md › Attribution, ADR 0019)."""

    def test_default_names(self) -> None:
        """The default name of a repository identity is the last part of its path, and
        of a root commit the first 12 characters of the hash."""
        hints = ["example.org/team/app",
                 "root-commit:0123456789abcdef0123456789abcdef01234567"]
        given, errors = names.project_names(hints, hints, _person())
        self.assertEqual(given, {"example.org/team/app": "app",
                                 "root-commit:0123456789abcdef0123456789abcdef01234567":
                                 "0123456789ab"})
        self.assertEqual(errors, [])

    def test_declared_identifier_is_its_own_name(self) -> None:
        """A project identifier that no repository identity of the events gives is its
        own name; with the identity among the events it takes the default name."""
        given, _ = names.project_names(["acme/alpha"], [], _person())
        self.assertEqual(given, {"acme/alpha": "acme/alpha"})
        given, _ = names.project_names(["acme/alpha"], ["acme/alpha"], _person())
        self.assertEqual(given, {"acme/alpha": "alpha"})

    def test_equal_default_names_take_more_path(self) -> None:
        """Two identities whose last path part is the same show one more part of their
        path, so that the names differ, and no error rises."""
        hints = ["example.org/a/x/app", "example.org/b/y/app"]
        given, errors = names.project_names(hints, hints, _person())
        self.assertEqual(given, {"example.org/a/x/app": "x/app",
                                 "example.org/b/y/app": "y/app"})
        self.assertEqual(errors, [])

    def test_name_given_to_two_projects_is_error(self) -> None:
        """A name that the person configuration gives to two project identifiers is a
        configuration error that names both, and both identifiers keep the name."""
        person = _person(projects=[ProjectName("example.org/team/app", "Invented App"),
                                   ProjectName("acme/other", "Invented App")])
        hints = ["example.org/team/app", "acme/other"]
        given, errors = names.project_names(hints, hints, person)
        self.assertEqual(errors, [{"code": "project_name_conflict",
                                   "values": {"first": "example.org/team/app",
                                              "second": "acme/other"}}])
        self.assertEqual(given, {"example.org/team/app": "Invented App",
                                 "acme/other": "Invented App"})

    def test_declared_project_unknown_warns(self) -> None:
        """A project identifier of a declared event that no identity rule, no entry of
        the person configuration, and no repository identity gives warns once, and the
        buckets of the annotations warn the same way."""
        person = _person(projects=[ProjectName("named-project", "Named")],
                         identity_rules=[
                             _rule(repository="example.org/team/app",
                                   project="ruled-project")])
        warnings = names.declared_project_unknown(
            ["ruled-project", "named-project", "example.org/team/app", "acme/unknown",
             "acme/unknown"],
            person, ["example.org/team/app"])
        self.assertEqual(warnings, [{"code": "declared_project_unknown",
                                     "values": {"project": "acme/unknown"}}])
        event = _event("2026-06-15T10:00:00.000Z", "uid-one", repo_hint=_REPO)
        note = _note("2026-06-15T12:00:00.000Z", "note-uid", project="acme/unknown",
                     annotates=_SESSION_OF)
        buckets, errors = annotations.event_buckets([event], [note], person,
                                                    support.scenario_days())
        self.assertEqual(buckets[events.event_key(event)], ("acme/unknown", None))
        self.assertEqual(errors, [{"code": "declared_project_unknown",
                                   "values": {"project": "acme/unknown"}}])


class BucketTests(unittest.TestCase):
    """The buckets of the events: the identity of the previous event of a session and
    the overrides of the annotations of a session or of an interval (metrics.md ›
    Attribution)."""

    def test_event_takes_folder_of_previous_event(self) -> None:
        """An event without its own folder, branch, or repository identity takes those
        of the previous event of its session, whatever their order in the report, and
        the identity rules resolve its project from them."""
        person = _person(identity_rules=[_rule(folder=r"D:\Work\Product",
                                               project="folder-project")])
        first = _event("2026-06-15T10:00:00.000Z", "uid-first",
                       cwd=r"D:\Work\Product\app", branch="main")
        second = _event("2026-06-15T10:01:00.000Z", "uid-second")
        buckets, errors = annotations.event_buckets([second, first], [], person,
                                                    support.scenario_days())
        self.assertEqual(buckets[events.event_key(first)], ("folder-project", None))
        self.assertEqual(buckets[events.event_key(second)], ("folder-project", None))
        self.assertEqual(errors, [])

    def test_session_annotation_overrides(self) -> None:
        """An annotation of a session gives every event of the session the project it
        names, also an event whose derived project is none."""
        person = _person(identity_rules=[_rule(repository=_REPO,
                                               project="acme/declared")])
        event = _event("2026-06-15T10:00:00.000Z", "uid-one")
        note = _note("2026-06-15T12:00:00.000Z", "note-uid", project="acme/declared",
                     annotates=_SESSION_OF)
        buckets, errors = annotations.event_buckets([event], [note], person,
                                                    support.scenario_days())
        self.assertEqual(buckets[events.event_key(event)], ("acme/declared", None))
        self.assertEqual(errors, [])

    def test_work_item_without_project_keeps_project(self) -> None:
        """An annotation that gives a work item and no project keeps the project that
        attribution gives to the event."""
        event = _event("2026-06-15T10:00:00.000Z", "uid-one", repo_hint=_REPO)
        note = _note("2026-06-15T12:00:00.000Z", "note-uid", work_item="invented-7",
                     annotates=_SESSION_OF)
        buckets, errors = annotations.event_buckets([event], [note], _person(),
                                                    support.scenario_days())
        self.assertEqual(buckets[events.event_key(event)], (_REPO, "invented-7"))
        self.assertEqual(errors, [])

    def test_project_without_work_item_removes_work_item(self) -> None:
        """A later annotation that gives a project and no work item removes the work
        item of the earlier annotations, which belongs to the earlier project, and a
        still later work item applies to the project that the earlier annotation gave."""
        event = _event("2026-06-15T10:00:00.000Z", "uid-one", repo_hint=_REPO)
        first = _note("2026-06-15T11:00:00.000Z", "note-first", work_item="invented-7",
                      annotates=_SESSION_OF)
        second = _note("2026-06-15T12:00:00.000Z", "note-second", project="acme/other",
                       annotates=_SESSION_OF)
        third = _note("2026-06-15T13:00:00.000Z", "note-third", work_item="invented-8",
                      annotates=_SESSION_OF)
        buckets, _ = annotations.event_buckets([event], [third, second, first], _person(),
                                               support.scenario_days())
        self.assertEqual(buckets[events.event_key(event)], ("acme/other", "invented-8"))

    def test_work_item_on_unattributed_event_warns(self) -> None:
        """A work item that an annotation gives to an event without a project does not
        apply: the event stays unattributed and the warning names the annotation, by its
        `event_uid`, and its work item (metrics.md › Attribution)."""
        event = _event("2026-06-15T10:00:00.000Z", "uid-one")
        note = _note("2026-06-15T12:00:00.000Z", "note-uid", work_item="invented-7",
                     annotates=_SESSION_OF)
        buckets, errors = annotations.event_buckets([event], [note], _person(),
                                                    support.scenario_days())
        self.assertEqual(buckets[events.event_key(event)], (None, None))
        self.assertEqual(errors, [{"code": "work_item_without_project",
                                   "values": {"work_item": "invented-7",
                                              "event_uid": "note-uid"}}])

    def test_overlapping_annotations_apply_in_timestamp_order(self) -> None:
        """Overlapping annotations of an interval apply in the order of their timestamp,
        equal instants by event key, and an interval holds the events whose timestamp is
        inside it, with the start included and the end excluded."""
        inside = _event("2026-06-15T10:30:00.000Z", "uid-inside", repo_hint=_REPO)
        early_only = _event("2026-06-15T10:10:00.000Z", "uid-early", repo_hint=_REPO)
        after = _event("2026-06-15T11:00:00.000Z", "uid-after", repo_hint=_REPO)
        early = _note("2026-06-15T09:00:00.000Z", "note-early", project="acme/early",
                      start="2026-06-15T10:00:00.000Z", end="2026-06-15T11:00:00.000Z")
        late = _note("2026-06-15T09:30:00.000Z", "note-late", project="acme/late",
                     start="2026-06-15T10:15:00.000Z", end="2026-06-15T11:00:00.000Z")
        tie_a = _note("2026-06-15T09:40:00.000Z", "note-tie-a", project="acme/tied-a",
                      start="2026-06-15T10:30:00.000Z", end="2026-06-15T10:31:00.000Z")
        tie_b = _note("2026-06-15T09:40:00.000Z", "note-tie-b", project="acme/tied-b",
                      start="2026-06-15T10:30:00.000Z", end="2026-06-15T10:31:00.000Z")
        buckets, errors = annotations.event_buckets(
            [after, inside, early_only], [tie_b, late, tie_a, early], _person(),
            support.scenario_days())
        self.assertEqual(buckets[events.event_key(inside)], ("acme/tied-b", None))
        self.assertEqual(buckets[events.event_key(early_only)], ("acme/early", None))
        self.assertEqual(buckets[events.event_key(after)], (_REPO, None))
        self.assertEqual(sorted(error["values"]["project"] for error in errors),
                         ["acme/early", "acme/late", "acme/tied-a", "acme/tied-b"])

    def test_conflict_error_carries_one_matching_event(self) -> None:
        """Two identity rules that both match an event give the completed conflict: the
        error names the rules and carries one event that they match, as its event key
        (configuration.md › Matching: the report shows the configuration error with the
        rules and one event that they match)."""
        left = _rule(folder=r"D:\Work", branch="release-*", project="left", line=2)
        right = _rule(folder=r"D:\Work\app", branch="*", project="right", line=3)
        event = _event("2026-06-15T10:00:00.000Z", "uid-one",
                       cwd=r"D:\Work\app\src", branch="release-5")
        buckets, errors = annotations.event_buckets([event], [],
                                                    _person(identity_rules=[left, right]),
                                                    support.scenario_days())
        self.assertEqual(buckets[events.event_key(event)], (None, None))
        self.assertEqual(errors, [{"code": "identity_rule_conflict",
                                   "values": {"first": "line 2 (left)",
                                              "second": "line 3 (right)",
                                              "event": events.event_key(event).to_json()}}])


class SplitTests(unittest.TestCase):
    """The split rule: every instant of the measured human time to one human signal
    (metrics.md › Attribution, ADR 0021)."""

    def test_split_rule_earliest_end_wins(self) -> None:
        """An instant that more than one interval contains belongs to the interval that
        ends first, and intervals that end at the same instant resolve by the event key
        of their signal: the larger key wins, as every rule that applies over another."""
        alpha = _signal(_at("10:00"), "uid-alpha")
        beta = _signal(_at("10:02"), "uid-beta", session_id="session-2")
        tie_a = _signal(_at("10:06"), "uid-tie-a")
        tie_b = _signal(_at("10:08"), "uid-tie-b")
        intervals = [
            HumanInterval(_ms("10:00"), _ms("10:04"), alpha, "signal_gap"),
            HumanInterval(_ms("10:02"), _ms("10:06"), beta, "minimum_attention"),
            HumanInterval(_ms("10:08"), _ms("10:10"), tie_b, "signal_gap"),
            HumanInterval(_ms("10:06"), _ms("10:10"), tie_a, "signal_gap"),
        ]
        self.assertEqual(split.split_human(intervals), [
            ((_ms("10:00"), _ms("10:04")), alpha),
            ((_ms("10:04"), _ms("10:06")), beta),
            ((_ms("10:06"), _ms("10:08")), tie_a),
            ((_ms("10:08"), _ms("10:10")), tie_b),
        ])


class AttributionTests(unittest.TestCase):
    """The figures of the buckets and the warnings of the report: the split rule over
    the measured human time, the manual entries over it, the agent time by its events,
    and the blocked time by its request (metrics.md › Attribution, › Declared values)."""

    def figures_of(
        self,
        session_events: list[events.Event],
        manual_entries: list[events.Event] | None = None,
        person: PersonConfiguration | None = None,
    ) -> tuple[dict[annotations.Bucket, split.BucketFigures], split.Attribution]:
        """The figures of the buckets over the whole day of the tests, with the report
        that holds them."""
        entries = list(manual_entries or [])
        metrics = compute_metrics(session_events, entries, _PARAMETERS)
        report = split.attribute(session_events, [], entries, metrics,
                                 person or _person(), support.scenario_days())
        return report.figures(_window("2026-06-15T00:00", "2026-06-16T00:00")), report

    def sessions_of(
        self, session_events: list[events.Event],
    ) -> tuple[Metrics, split.Attribution]:
        """The metrics and the attribution of the sessions of the tests, with no manual
        entry and no annotation."""
        metrics = compute_metrics(session_events, [], _PARAMETERS)
        report = split.attribute(session_events, [], [], metrics, _person(),
                                 support.scenario_days())
        return metrics, report

    def test_agent_time_divides_at_events(self) -> None:
        """The agent time of a turn whose events resolve to more than one project
        divides at its events: each part between two consecutive events takes the
        attribution of the event that ends it (metrics.md › Attribution)."""
        prompt = _signal(_at("10:00"), "uid-prompt")
        call = _event(_at("10:01"), "uid-call", repo_hint=_ALPHA)
        result = _event(_at("10:02"), "uid-result", kind="tool_result", actor="system",
                        repo_hint=_BETA)
        output = _event(_at("10:03"), "uid-output", kind="agent_output", repo_hint=_BETA)
        figures, _ = self.figures_of([prompt, call, result, output])
        self.assertEqual(figures[(_ALPHA, None)].agent_time, 60_000)
        self.assertEqual(figures[(_BETA, None)].agent_time, 120_000)
        self.assertEqual(figures[(_ALPHA, None)].human_time, 0)

    def test_blocked_time_follows_its_request(self) -> None:
        """The blocked time takes the attribution of its decision request: a request of
        another project than the agent output that follows keeps the blocked time in its
        own project (metrics.md › Attribution, › Blocked time)."""
        prompt = _signal(_at("10:00"), "uid-prompt", repo_hint=_ALPHA)
        request = _event(_at("10:01"), "uid-request", kind="decision_request",
                         decision_type="permission", call_id="request-1", repo_hint=_BETA)
        decision = _event(_at("10:02"), "uid-decision", kind="decision", actor="human",
                          call_id="request-1", repo_hint=_BETA)
        output = _event(_at("10:03"), "uid-output", kind="agent_output", repo_hint=_ALPHA)
        figures, _ = self.figures_of([prompt, request, decision, output])
        self.assertEqual(figures[(_BETA, None)].blocked_time, 60_000)
        self.assertEqual(figures[(_BETA, None)].agent_time, 60_000)
        self.assertEqual(figures[(_ALPHA, None)].agent_time, 60_000)
        self.assertEqual(figures[(_BETA, None)].human_time, 120_000)

    def test_overlapping_manual_entry_takes_interval(self) -> None:
        """An entry of mode `overlapping` merges with the measured human time by union
        and its attribution applies to the whole interval, and where it overlaps the
        measured human time of another project the report warns about the change
        (metrics.md › Declared values)."""
        person = _person(projects=[ProjectName("acme/delta", "Invented Delta")])
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        second = _signal(_at("10:04"), "uid-second", repo_hint=_ALPHA)
        entry = _manual_entry(_at("10:02"), _at("10:06"), "entry-uid", project="acme/delta")
        figures, report = self.figures_of([first, second], [entry], person)
        self.assertEqual(figures[(_ALPHA, None)].human_time, 300_000)
        self.assertEqual(figures[(_ALPHA, None)].with_manual, 180_000)
        self.assertEqual(figures[("acme/delta", None)].with_manual, 240_000)
        self.assertEqual(report.warnings,
                         [{"code": "manual_entry_overlap",
                           "values": {"event_uid": "entry-uid"}}])

    def test_latest_overlapping_entry_wins(self) -> None:
        """Where manual entries of mode `overlapping` overlap each other, the one with
        the latest timestamp applies, and equal instants resolve by the event key, the
        larger one (metrics.md › Attribution)."""
        person = _person(projects=[ProjectName("acme/bravo", "Bravo"),
                                   ProjectName("acme/charlie", "Charlie"),
                                   ProjectName("acme/zulu", "Zulu"),
                                   ProjectName("acme/alfa", "Alfa")])
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        second = _signal(_at("10:04"), "uid-second", repo_hint=_ALPHA)
        earlier = _manual_entry(_at("10:02"), _at("10:08"), "entry-earlier",
                                timestamp=_at("11:00"), project="acme/bravo")
        later = _manual_entry(_at("10:04"), _at("10:10"), "entry-later",
                              timestamp=_at("12:00"), project="acme/charlie")
        tie_zulu = _manual_entry(_at("10:10"), _at("10:14"), "entry-tie-zulu",
                                 timestamp=_at("13:00"), project="acme/zulu")
        tie_alfa = _manual_entry(_at("10:12"), _at("10:16"), "entry-tie-alfa",
                                 timestamp=_at("13:00"), project="acme/alfa")
        entries = [tie_alfa, tie_zulu, later, earlier]
        figures, report = self.figures_of([first, second], entries, person)
        self.assertEqual(figures[(_ALPHA, None)].with_manual, 180_000)
        self.assertEqual(figures[("acme/bravo", None)].with_manual, 120_000)
        self.assertEqual(figures[("acme/charlie", None)].with_manual, 360_000)
        self.assertEqual(figures[("acme/zulu", None)].with_manual, 240_000)
        self.assertEqual(figures[("acme/alfa", None)].with_manual, 120_000)
        self.assertEqual(report.warnings,
                         [{"code": "manual_entry_overlap",
                           "values": {"event_uid": "entry-earlier"}}])

    def test_parts_add_up_to_human_time(self) -> None:
        """The measured human time of the projects, the work items, and the unattributed
        time adds up to the measured human time of the day, the measured part of
        acceptance criterion 4 (product.md › Phase 1)."""
        alpha_first = _signal(_at("10:00"), "uid-a1", session_id="session-1",
                              repo_hint=_ALPHA)
        alpha_second = _signal(_at("10:03"), "uid-a2", session_id="session-1")
        beta_first = _signal(_at("10:06"), "uid-b1", session_id="session-2",
                             repo_hint=_BETA)
        beta_second = _signal(_at("10:09"), "uid-b2", session_id="session-2")
        stray = _signal(_at("10:12"), "uid-none", session_id="session-3")
        events_of = [beta_second, stray, beta_first, alpha_second, alpha_first]
        figures, _ = self.figures_of(events_of)
        self.assertEqual(sum(item.human_time for item in figures.values()), 780_000)
        self.assertEqual(figures[(_ALPHA, None)].human_time, 240_000)
        self.assertEqual(figures[(_BETA, None)].human_time, 360_000)
        self.assertEqual(figures[(None, None)].human_time, 180_000)

    def test_with_manual_parts_add_up(self) -> None:
        """On a measured day the values with manual entries add up to the total human
        time of the day, the part with manual entries of acceptance criterion 4
        (product.md › Phase 1): an entry over the measured time of two projects, and an
        additional entry outside it."""
        person = _person(projects=[ProjectName("acme/mike", "Mike"),
                                   ProjectName("acme/november", "November")])
        alpha_first = _signal(_at("10:00"), "uid-a1", session_id="session-1",
                              repo_hint=_ALPHA)
        alpha_second = _signal(_at("10:03"), "uid-a2", session_id="session-1")
        beta_first = _signal(_at("10:06"), "uid-b1", session_id="session-2",
                             repo_hint=_BETA)
        beta_second = _signal(_at("10:09"), "uid-b2", session_id="session-2")
        stray = _signal(_at("10:12"), "uid-none", session_id="session-3")
        over = _manual_entry(_at("10:01"), _at("10:05"), "entry-over", project="acme/mike")
        apart = _manual_entry(_at("10:20"), _at("10:30"), "entry-apart",
                              mode="additional", project="acme/november")
        events_of = [beta_second, stray, beta_first, alpha_second, alpha_first]
        figures, report = self.figures_of(events_of, [apart, over], person)
        self.assertEqual(sum(item.with_manual for item in figures.values()), 1_380_000)
        self.assertEqual(figures[(_ALPHA, None)].with_manual, 120_000)
        self.assertEqual(figures[("acme/mike", None)].with_manual, 240_000)
        self.assertEqual(figures[(_BETA, None)].with_manual, 240_000)
        self.assertEqual(figures[(None, None)].with_manual, 180_000)
        self.assertEqual(figures[("acme/november", None)].with_manual, 600_000)
        self.assertEqual(report.warnings,
                         [{"code": "manual_entry_overlap",
                           "values": {"event_uid": "entry-over"}}])

    def test_manual_entry_of_unknown_project_warns(self) -> None:
        """The project identifier of a manual entry that no identity rule, no entry of
        the person configuration, and no repository identity gives warns, and stays its
        own name (metrics.md › Attribution, ADR 0019)."""
        signal = _signal(_at("10:00"), "uid-only", repo_hint=_ALPHA)
        entry = _manual_entry(_at("10:05"), _at("10:06"), "entry-uid",
                              mode="additional", project="acme/mystery")
        figures, report = self.figures_of([signal], [entry])
        self.assertEqual(report.warnings,
                         [{"code": "declared_project_unknown",
                           "values": {"project": "acme/mystery"}}])
        self.assertEqual(report.names,
                         {_ALPHA: "alpha", "acme/mystery": "acme/mystery"})
        self.assertEqual(figures[("acme/mystery", None)].with_manual, 60_000)

    def test_project_only_in_a_confirmation_has_a_name(self) -> None:
        """The projects and the work items of the timesheet confirmations get names too,
        so that a project that only a confirmation names has one: from the person
        configuration when it names them, their identifiers otherwise (metrics.md ›
        Declared values)."""
        confirmation = _confirmation([{"project": "acme/solo", "work_item": "item-9",
                                       "duration": 900}])
        named = _person(projects=[ProjectName("acme/solo", "Declared Project")],
                        work_items=[WorkItemName("acme/solo", "item-9", "Invented Item")])
        report = split.attribute([], [], [], Metrics([], [], [], [], []), named,
                                 support.scenario_days(), [confirmation])
        self.assertEqual(report.names, {"acme/solo": "Declared Project"})
        self.assertEqual(report.work_item_names,
                         {("acme/solo", "item-9"): "Invented Item"})
        plain = split.attribute([], [], [], Metrics([], [], [], [], []), _person(),
                                support.scenario_days(), [confirmation])
        self.assertEqual(plain.names, {"acme/solo": "acme/solo"})
        self.assertEqual(plain.work_item_names, {("acme/solo", "item-9"): "item-9"})

    def test_hints_and_work_item_names_read_from_the_attribution(self) -> None:
        """An attribution gives the repository identities that the events of its sessions
        hint at, and the name of any work item by the rule that names its own: the name of
        the person configuration for the pair of the project and the identifier, else the
        identifier (metrics.md › Attribution, ADR 0019)."""
        hinted = _signal(_at("10:00"), "uid-hinted", repo_hint=_ALPHA)
        unhinted = _signal(_at("10:05"), "uid-unhinted")
        named = _person(work_items=[WorkItemName("acme/solo", "item-9", "Invented Item")])
        metrics = compute_metrics([hinted, unhinted], [], _PARAMETERS)
        report = split.attribute([hinted, unhinted], [], [], metrics, named,
                                 support.scenario_days())
        self.assertEqual(report.repository_hints, frozenset({_ALPHA}))
        self.assertEqual(report.work_item_name("acme/solo", "item-9"), "Invented Item")
        self.assertEqual(report.work_item_name("acme/solo", "item-10"), "item-10")
        self.assertEqual(report.work_item_name("acme/other", "item-9"), "item-9")

    def test_inferred_shares(self) -> None:
        """The shares of a bucket that rest on an inferred repository identity: 4 of 10
        minutes of human time from a signal whose identity is inferred give 0.4, and the
        agent time the same way, by the event that ends each part (metrics.md ›
        Attribution, ADR 0018)."""
        observed = _signal(_at("10:00"), "uid-observed", repo_hint=_REPO,
                           repo_basis="observed")
        inferred = _signal(_at("10:06"), "uid-inferred", repo_hint=_REPO,
                           repo_basis="inferred")
        call = _event(_at("10:04"), "uid-call", kind="agent_output", actor="system",
                      repo_hint=_REPO, repo_basis="observed")
        result = _event(_at("10:08"), "uid-result", kind="agent_output", actor="system",
                        repo_hint=_REPO, repo_basis="inferred")
        metrics = Metrics(
            [HumanInterval(_ms("10:00"), _ms("10:06"), observed, "signal_gap"),
             HumanInterval(_ms("10:06"), _ms("10:10"), inferred, "signal_gap")],
            [],
            [AgentPart(_ms("10:00"), _ms("10:06"), (_TOOL, _SESSION, "main"), call),
             AgentPart(_ms("10:06"), _ms("10:10"), (_TOOL, _SESSION, "main"), result)],
            [], [])
        events_of = [observed, inferred, call, result]
        report = split.attribute(events_of, [], [], metrics, _person(),
                                 support.scenario_days())
        window = _window("2026-06-15T00:00", "2026-06-16T00:00")
        figures = report.figures(window)[(_REPO, None)]
        self.assertEqual(figures.human_time, 600_000)
        self.assertAlmostEqual(figures.inferred_human_share, 0.4)
        self.assertEqual(figures.agent_time, 600_000)
        self.assertAlmostEqual(figures.inferred_agent_share, 0.4)
        projects = report.project_figures(window)
        self.assertEqual(set(projects), {_REPO})
        self.assertAlmostEqual(projects[_REPO].inferred_human_share, 0.4)
        self.assertAlmostEqual(projects[_REPO].inferred_agent_share, 0.4)

    def test_inferred_shares_follow_the_carried_identity(self) -> None:
        """An event without its own repository identity takes the identity of the previous
        event of its session with its basis: the prompt of 10:08 and the output of 10:10
        take the inferred identity of the prompt of 10:06. The human time is 6 minutes
        from the observed prompt of 10:00, 2 from the inferred prompt of 10:06, and 2 from
        the prompt of 10:08, so 4 of 10 minutes rest on the inferred identity, 0.4; the
        agent time is 4 minutes to the observed output of 10:04 and 6 to the output of
        10:10, so 6 of 10, 0.6 — in the bucket, in the project, and in the person
        (metrics.md › Attribution, ADR 0018)."""
        observed = _signal(_at("10:00"), "uid-observed", repo_hint=_REPO,
                           repo_basis="observed")
        output = _event(_at("10:04"), "uid-output", kind="agent_output", actor="system",
                        repo_hint=_REPO, repo_basis="observed")
        inferred = _signal(_at("10:06"), "uid-inferred", repo_hint=_REPO,
                           repo_basis="inferred")
        carried = _signal(_at("10:08"), "uid-carried")
        last = _event(_at("10:10"), "uid-last", kind="agent_output", actor="system")
        agent = (_TOOL, _SESSION, _SESSION)
        metrics = Metrics(
            [HumanInterval(_ms("10:00"), _ms("10:06"), observed, "signal_gap"),
             HumanInterval(_ms("10:06"), _ms("10:08"), inferred, "signal_gap"),
             HumanInterval(_ms("10:08"), _ms("10:10"), carried, "signal_gap")],
            [],
            [AgentPart(_ms("10:00"), _ms("10:04"), agent, output),
             AgentPart(_ms("10:04"), _ms("10:10"), agent, last)],
            [], [])
        report = split.attribute([last, carried, inferred, output, observed], [], [],
                                 metrics, _person(), support.scenario_days())
        for held in (report.figures(_WHOLE_DAY)[(_REPO, None)],
                     report.project_figures(_WHOLE_DAY)[_REPO],
                     report.person_figures(_WHOLE_DAY)):
            self.assertEqual((held.human_time, held.agent_time), (600_000, 600_000))
            self.assertAlmostEqual(held.inferred_human_share, 0.4)
            self.assertAlmostEqual(held.inferred_agent_share, 0.6)

    def test_project_classes_have_no_idle(self) -> None:
        """The activity classes of a bucket come from its human, agent, and blocked time
        and hold no class idle: the rest of the window, which the class idle holds for
        the person, is no part of them (metrics.md › Activity classes). The person is
        present 09:59-10:01 and the agent works 10:01-10:02, so the second prompt closed
        the turn of the first."""
        first = _signal(_at("10:00"), "uid-first", repo_hint=_REPO)
        second = _signal(_at("10:01"), "uid-second")
        output = _event(_at("10:02"), "uid-output", kind="agent_output", actor="system",
                        repo_hint=_REPO)
        figures, _ = self.figures_of([output, second, first])
        held = figures[(_REPO, None)]
        self.assertNotIn("idle", held.activity_classes)
        self.assertEqual(held.activity_classes, {"person_only": 120_000,
                                                 "supervised": 0,
                                                 "unattended": 60_000, "blocked": 0})
        self.assertEqual(held.human_time, 120_000)
        self.assertEqual(held.agent_time, 60_000)
        self.assertEqual(held.inferred_human_share, 0.0)
        self.assertEqual(held.inferred_agent_share, 0.0)

    def test_project_figures_are_unions(self) -> None:
        """The human time, the blocked time, and the activity classes of a project come from
        the unions of the spans of its buckets, and its agent time is the sum over the agents
        of those spans: two work items of one project whose blocked time overlaps make the
        project count the shared instants once, where the figures of the work items each hold
        their own, and its activity classes are no sum of theirs (metrics.md › Attribution, ›
        Activity classes)."""
        request_one = _event(_at("10:01"), "uid-request-1", kind="decision_request",
                             decision_type="permission", call_id="request-1",
                             repo_hint=_REPO)
        decision_one = _event(_at("10:04"), "uid-decision-1", kind="decision",
                              actor="human", call_id="request-1", repo_hint=_REPO)
        request_two = _event(_at("10:03"), "uid-request-2", kind="decision_request",
                             decision_type="permission", call_id="request-2",
                             session_id="session-2", repo_hint=_REPO)
        decision_two = _event(_at("10:06"), "uid-decision-2", kind="decision",
                              actor="human", call_id="request-2", session_id="session-2",
                              repo_hint=_REPO)
        first = _signal(_at("10:00"), "uid-first", repo_hint=_REPO)
        second = _signal(_at("10:02"), "uid-second", session_id="session-2",
                         repo_hint=_REPO)
        note_one = _note("2026-06-15T09:00:00.000Z", "note-one",
                         annotates={"tool": _TOOL, "session_id": _SESSION},
                         work_item="invented-1")
        note_two = _note("2026-06-15T09:00:00.000Z", "note-two",
                         annotates={"tool": _TOOL, "session_id": "session-2"},
                         work_item="invented-2")
        events_of = [first, request_one, decision_one, second, request_two, decision_two]
        metrics = compute_metrics(events_of, [], _PARAMETERS)
        report = split.attribute(events_of, [note_one, note_two], [], metrics,
                                 _person(), support.scenario_days())
        window = _window("2026-06-15T00:00", "2026-06-16T00:00")
        figures = report.figures(window)
        self.assertEqual(figures[(_REPO, "invented-1")].blocked_time, 180_000)
        self.assertEqual(figures[(_REPO, "invented-2")].blocked_time, 180_000)
        projects = report.project_figures(window)
        self.assertEqual(projects[_REPO].blocked_time, 300_000)
        self.assertEqual(projects[_REPO].human_time, 420_000)
        self.assertEqual(projects[_REPO].agent_time, 120_000)
        self.assertEqual(projects[_REPO].activity_classes,
                         {"person_only": 300_000, "supervised": 120_000,
                          "unattended": 0, "blocked": 0})

    def test_holder_classes_rest_on_its_human_time_with_manual_entries(self) -> None:
        """The activity classes of a project come from its measured human time with manual
        entries, beside the agent time and the blocked time attributed to it, as the
        classes of the person do (metrics.md › Activity classes, › Declared values), so
        for every holder the class person only and the class supervised add up to its
        human time with manual entries. Alpha is present 09:59-10:00 and 10:19-10:25, and
        its agent works 10:00-10:05, 10:20-10:22, and 10:25-10:26. An entry in mode
        `overlapping` on Delta, 09:30-10:10, takes the first minute of Alpha: the classes
        of Delta cover its whole interval, 40 min of person only and no agent time, and
        Alpha keeps 6 min of presence — 2 min supervised and 4 min person only — beside
        its 6 min of unattended agent time, which stay its own. An entry in mode
        `additional` on Echo, 11:00-11:30, meets no measured human time and gives Echo 30
        min of person only. The person counts the union: 76 min present, 7 min supervised
        — among them the 5 min of the turn of Alpha inside the entry on Delta —, 69 min of
        person only, 1 min unattended, and 81 780 s idle, the day without its 76 min of
        presence and its 1 min of agent time alone."""
        delta, echo = "acme/delta", "acme/echo"
        person = _person(projects=[ProjectName(delta, "Invented Delta"),
                                   ProjectName(echo, "Invented Echo")])
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        output = _event(_at("10:05"), "uid-output", kind="agent_output", actor="system",
                        repo_hint=_ALPHA)
        second = _signal(_at("10:20"), "uid-second", repo_hint=_ALPHA)
        answer = _event(_at("10:22"), "uid-answer", kind="agent_output", actor="system",
                        repo_hint=_ALPHA)
        third = _signal(_at("10:25"), "uid-third", repo_hint=_ALPHA)
        last = _event(_at("10:26"), "uid-last", kind="agent_output", actor="system",
                      repo_hint=_ALPHA)
        over = _manual_entry(_at("09:30"), _at("10:10"), "entry-over", project=delta)
        apart = _manual_entry(_at("11:00"), _at("11:30"), "entry-apart", mode="additional",
                              project=echo)
        figures, report = self.figures_of([first, output, second, answer, third, last],
                                          [apart, over], person)
        self.assertEqual(report.warnings,
                         [{"code": "manual_entry_overlap",
                           "values": {"event_uid": "entry-over"}}])
        alpha = figures[(_ALPHA, None)]
        self.assertEqual((alpha.human_time, alpha.with_manual, alpha.agent_time),
                         (420_000, 360_000, 480_000))
        self.assertEqual(alpha.activity_classes,
                         {"person_only": 240_000, "supervised": 120_000,
                          "unattended": 360_000, "blocked": 0})
        self.assertEqual(figures[(delta, None)].activity_classes,
                         {"person_only": 2_400_000, "supervised": 0,
                          "unattended": 0, "blocked": 0})
        self.assertEqual(figures[(delta, None)].with_manual, 2_400_000)
        self.assertEqual(figures[(echo, None)].activity_classes,
                         {"person_only": 1_800_000, "supervised": 0,
                          "unattended": 0, "blocked": 0})
        projects = report.project_figures(_WHOLE_DAY)
        self.assertEqual({name: held.activity_classes for name, held in projects.items()},
                         {_ALPHA: alpha.activity_classes,
                          delta: figures[(delta, None)].activity_classes,
                          echo: figures[(echo, None)].activity_classes})
        for held in (*figures.values(), *projects.values()):
            classes = held.activity_classes
            self.assertEqual(classes["person_only"] + classes["supervised"],
                             held.with_manual)
        whole = report.person_figures(_WHOLE_DAY)
        self.assertEqual(whole.with_manual, 4_560_000)
        self.assertEqual(whole.activity_classes,
                         {"person_only": 4_140_000, "supervised": 420_000,
                          "unattended": 60_000, "blocked": 0, "idle": 81_780_000})

    def test_session_parts(self) -> None:
        """The parts of each session: the human time that the split rule gives to the
        signals of the session and the agent time of its agents, per bucket of the
        session, inside the window (metrics.md › Attribution, command-line.md ›
        Commands)."""
        prompt_one = _signal(_at("10:00"), "uid-p1", repo_hint=_ALPHA)
        output_one = _event(_at("10:02"), "uid-o1", kind="agent_output", actor="system",
                            repo_hint=_ALPHA)
        prompt_two = _signal(_at("10:04"), "uid-p2")
        output_two = _event(_at("10:06"), "uid-o2", kind="agent_output", actor="system",
                            repo_hint=_BETA)
        prompt_three = _signal(_at("10:08"), "uid-p3")
        later = _signal(_at("11:00"), "uid-later", session_id="session-2",
                        repo_hint=_ALPHA)
        events_of = [later, prompt_three, output_two, prompt_two, output_one, prompt_one]
        _, report = self.sessions_of(events_of)
        window = _window("2026-06-15T00:00", "2026-06-16T00:00")
        self.assertEqual(report.session_parts(window), {
            (_TOOL, "session-1"): {(_ALPHA, None): (300_000, 120_000),
                                   (_BETA, None): (240_000, 120_000)},
            (_TOOL, "session-2"): {(_ALPHA, None): (60_000, 0)},
        })

    def test_session_parts_add_up_to_session_figures(self) -> None:
        """The parts of the sessions add up to the figures of the buckets: over every
        bucket, the human time and the agent time of its session parts are the figures of
        the bucket, and the parts of a session add up to the human time that the split
        rule gives to its signals and to the agent time of its agents (metrics.md ›
        Attribution, acceptance criterion 4)."""
        prompt_one = _signal(_at("10:00"), "uid-p1", repo_hint=_ALPHA)
        output_one = _event(_at("10:02"), "uid-o1", kind="agent_output", actor="system",
                            repo_hint=_ALPHA)
        prompt_two = _signal(_at("10:04"), "uid-p2")
        output_two = _event(_at("10:06"), "uid-o2", kind="agent_output", actor="system",
                            repo_hint=_BETA)
        prompt_three = _signal(_at("10:08"), "uid-p3")
        later = _signal(_at("11:00"), "uid-later", session_id="session-2",
                        repo_hint=_ALPHA)
        events_of = [later, prompt_three, output_two, prompt_two, output_one, prompt_one]
        metrics, report = self.sessions_of(events_of)
        window = _window("2026-06-15T00:00", "2026-06-16T00:00")
        figures = report.figures(window)
        parts = report.session_parts(window)
        for bucket, held in figures.items():
            human = sum(values.get(bucket, (0, 0))[0] for values in parts.values())
            agent = sum(values.get(bucket, (0, 0))[1] for values in parts.values())
            self.assertEqual(human, held.human_time, str(bucket))
            self.assertEqual(agent, held.agent_time, str(bucket))
        split_of = {}
        for span, signal in split.split_human(metrics.human):
            session = (signal["tool"], signal["session_id"])
            length = total(intersect([span], window))
            split_of[session] = split_of.get(session, 0) + length
        self.assertEqual({session: sum(part[0] for part in held.values())
                          for session, held in parts.items()},
                         {session: split_of.get(session, 0) for session in parts})
        agents = {}
        for part in metrics.agent:
            session = (part.agent[0], part.agent[1])
            length = total(intersect([(part.start, part.end)], window))
            agents[session] = agents.get(session, 0) + length
        self.assertEqual({session: sum(part[1] for part in held.values())
                          for session, held in parts.items()},
                         {session: agents.get(session, 0) for session in parts})

    def test_figures_hold_only_buckets_of_the_window(self) -> None:
        """A bucket whose time lies entirely outside the window enters no row of the
        figures and of the project figures, not an all-zero one: the figures of the
        window hold only the buckets that hold time inside it (metrics.md ›
        Attribution)."""
        first = _signal(_at("10:00"), "uid-first", repo_hint=_ALPHA)
        second = _signal(_at("10:04"), "uid-second")
        apart = _signal(_at("11:00"), "uid-apart", session_id="session-2",
                        repo_hint=_BETA)
        _, report = self.sessions_of([apart, second, first])
        window = _window("2026-06-15T10:00", "2026-06-15T10:10")
        self.assertEqual(set(report.figures(window)), {(_ALPHA, None)})
        self.assertEqual(set(report.project_figures(window)), {_ALPHA})

    def test_entry_rank_dominates_timestamp(self) -> None:
        """Where an entry of mode `overlapping` and one of mode `additional` hold the same
        instants that no measured human time covers, the rank decides, not the timestamp:
        the overlapping entry takes them, however later the person wrote the additional
        entry (metrics.md › Attribution)."""
        person = _person(projects=[ProjectName("acme/older", "Invented Older"),
                                   ProjectName("acme/newer", "Invented Newer")])
        signal = _signal(_at("10:00"), "uid-only", repo_hint=_REPO)
        older = _manual_entry(_at("10:05"), _at("10:15"), "entry-older",
                              timestamp=_at("09:00"), project="acme/older")
        newer = _manual_entry(_at("10:10"), _at("10:20"), "entry-newer",
                              timestamp=_at("15:00"), mode="additional",
                              project="acme/newer")
        figures, report = self.figures_of([signal], [older, newer], person)
        self.assertEqual(figures[("acme/older", None)].with_manual, 600_000)
        self.assertEqual(figures[("acme/newer", None)].with_manual, 300_000)
        self.assertEqual(figures[(_REPO, None)].with_manual, 60_000)
        self.assertEqual(report.warnings, [])

    def test_window_inside_an_entry_that_holds_another_entry(self) -> None:
        """A window reads the manual entries that can hold an instant of it: the entry
        10:00-11:00 holds the entry 10:10-10:20 and ends after it, so the window
        10:30-10:40, inside the first entry and after the second, takes the project of
        the first entry, and the entries before the window and after it hold none of it.
        The activity classes of a bucket come from the measured human time with manual
        entries, which the held entry gives in full here, so the class Person only takes
        the whole window (metrics.md › Activity classes)."""
        person = _person(projects=[ProjectName("acme/mike", "Mike"),
                                   ProjectName("acme/november", "November"),
                                   ProjectName("acme/oscar", "Oscar"),
                                   ProjectName("acme/papa", "Papa")])
        held = _manual_entry(_at("10:00"), _at("11:00"), "entry-held",
                             timestamp=_at("11:30"), project="acme/mike")
        inside = _manual_entry(_at("10:10"), _at("10:20"), "entry-inside",
                               timestamp=_at("12:00"), project="acme/november")
        before = _manual_entry(_at("09:00"), _at("09:30"), "entry-before",
                               project="acme/oscar")
        after = _manual_entry(_at("11:30"), _at("12:00"), "entry-after",
                              project="acme/papa")
        entries = [after, inside, before, held]
        metrics = compute_metrics([], entries, _PARAMETERS)
        report = split.attribute([], [], entries, metrics, person,
                                 support.scenario_days())
        window = _window("2026-06-15T10:30", "2026-06-15T10:40")
        expected = split.BucketFigures(
            0, 600_000, 0, 0,
            {"person_only": 600_000, "supervised": 0, "unattended": 0, "blocked": 0},
            0.0, 0.0)
        self.assertEqual(report.figures(window), {("acme/mike", None): expected})
        self.assertEqual(report.project_figures(window), {"acme/mike": expected})
        self.assertEqual(report.person_figures(window).with_manual, 600_000)

    def test_window_inside_a_wait_that_holds_another_wait(self) -> None:
        """A window reads the blocked time that can hold an instant of it: the wait from
        the request at 10:00 of session-1 to its decision at 11:00 holds the wait
        10:10-10:20 of session-2 and ends after it, so the window 10:30-10:40, inside
        the first wait and after the second, holds 10 minutes of blocked time, and the
        waits before the window and after it hold none of it (metrics.md › Blocked time,
        › Days and weeks)."""
        events_of = [
            _event(_at("10:00"), "uid-request-1", kind="decision_request",
                   session_id="s-1", decision_type="permission", call_id="call-1",
                   repo_hint=_ALPHA),
            _event(_at("11:00"), "uid-decision-1", kind="decision", actor="human",
                   session_id="s-1", call_id="call-1", repo_hint=_ALPHA),
            _event(_at("10:10"), "uid-request-2", kind="decision_request",
                   session_id="s-2", decision_type="permission", call_id="call-2",
                   repo_hint=_BETA),
            _event(_at("10:20"), "uid-decision-2", kind="decision", actor="human",
                   session_id="s-2", call_id="call-2", repo_hint=_BETA),
            _event(_at("09:00"), "uid-request-3", kind="decision_request",
                   session_id="s-3", decision_type="permission", call_id="call-3",
                   repo_hint=_BETA),
            _event(_at("09:05"), "uid-decision-3", kind="decision", actor="human",
                   session_id="s-3", call_id="call-3", repo_hint=_BETA),
            _event(_at("11:30"), "uid-request-4", kind="decision_request",
                   session_id="s-4", decision_type="permission", call_id="call-4",
                   repo_hint=_ALPHA),
            _event(_at("11:40"), "uid-decision-4", kind="decision", actor="human",
                   session_id="s-4", call_id="call-4", repo_hint=_ALPHA),
        ]
        _, report = self.sessions_of(events_of)
        window = _window("2026-06-15T10:30", "2026-06-15T10:40")
        self.assertEqual(report.figures(window),
                         {(_ALPHA, None): split.BucketFigures(
                             0, 0, 0, 600_000,
                             {"person_only": 0, "supervised": 0, "unattended": 0,
                              "blocked": 600_000}, 0.0, 0.0)})
        self.assertEqual(report.person_figures(window).blocked_time, 600_000)

    def test_category_rule_conflict_reported(self) -> None:
        """Two matching category rules of which neither is narrower keep the stored
        category and give one `category_rule_conflict` error, once for the pair,
        however many tool calls they both match, and the error carries one event that
        they match, the first tool call in the order of the timestamp, as its event key
        (configuration.md › Matching: the report shows the configuration error with the
        rules and one event that they match)."""
        person = _person(category_rules=[_tool("mcp__*", "web", 2),
                                         _tool("*search*", "search", 3)])
        first = _event(_at("10:00"), "uid-call-a", tool_name="mcp__search",
                       tool_category="other", repo_hint=_ALPHA)
        second = _event(_at("10:01"), "uid-call-b", tool_name="mcp__search",
                        tool_category="other", repo_hint=_ALPHA)
        events_of = [second, first]
        metrics = compute_metrics(events_of, [], _PARAMETERS)
        report = split.attribute(events_of, [], [], metrics, person,
                                 support.scenario_days())
        self.assertEqual(report.configuration_errors,
                         [{"code": "category_rule_conflict",
                           "values": {"first": "line 2 (web)",
                                      "second": "line 3 (search)",
                                      "event": events.event_key(first).to_json()}}])


class AgentTimeTests(unittest.TestCase):
    """The agent time of a holder is the sum over the agents that work in it: an instant
    counts once for each agent, and the parts of one agent count once. The human time, the
    blocked time, and the activity classes stay clock time (metrics.md › Agent time, ›
    Activity classes, ADR 0001)."""

    def _attributed(
        self,
        session_events: list[events.Event],
        notes: Sequence[events.Event] = (),
    ) -> split.Attribution:
        """The attribution of the events of the tests, with the annotations given and no
        manual entry."""
        metrics = compute_metrics(session_events, [], _PARAMETERS)
        return split.attribute(session_events, list(notes), [], metrics, _person(),
                               support.scenario_days())

    def test_two_sessions_of_two_projects(self) -> None:
        """Two sessions of two projects, whose turns 10:00-10:10 and 10:05-10:15 share 5
        minutes: the person holds 10 + 10 = 20 minutes of agent time, where the union of
        the turns is 15, and each project its 10. The activity classes of the person are
        clock time: the person is present 09:59-10:05 (the minimum attention before the
        first prompt and the signal gap to the second), so 1 minute is person only, 5
        supervised, and 10 unattended: the shared instants count once. The sessions give 10
        minutes each, and they add up to the person (metrics.md › Agent time)."""
        events_of = [*_turn("session-1", _at("10:00"), _at("10:10"), _ALPHA),
                     *_turn("session-2", _at("10:05"), _at("10:15"), _BETA)]
        report = self._attributed(events_of)
        person = report.person_figures(_WHOLE_DAY)
        self.assertEqual(person.agent_time, 1_200_000)
        self.assertEqual(person.activity_classes,
                         {"person_only": 60_000, "supervised": 300_000,
                          "unattended": 600_000, "blocked": 0, "idle": 85_440_000})
        figures = report.figures(_WHOLE_DAY)
        self.assertEqual({bucket: held.agent_time for bucket, held in figures.items()},
                         {(_ALPHA, None): 600_000, (_BETA, None): 600_000})
        parts = report.session_parts(_WHOLE_DAY)
        self.assertEqual(parts, {(_TOOL, "session-1"): {(_ALPHA, None): (60_000, 600_000)},
                                 (_TOOL, "session-2"): {(_BETA, None): (300_000, 600_000)}})
        self.assertEqual(sum(times[1] for held in parts.values() for times in held.values()),
                         person.agent_time)

    def test_two_sessions_of_one_project(self) -> None:
        """Two sessions of one project with the same turns: the bucket and the project hold
        10 + 10 = 20 minutes of agent time, where the union is 15, and the classes of the
        project count the shared instants once: the person is present 09:59-10:05, so 1
        minute is person only, 5 supervised, and 10 unattended (metrics.md › Agent time, ›
        Activity classes)."""
        events_of = [*_turn("session-1", _at("10:00"), _at("10:10"), _ALPHA),
                     *_turn("session-2", _at("10:05"), _at("10:15"), _ALPHA)]
        report = self._attributed(events_of)
        self.assertEqual(report.figures(_WHOLE_DAY)[(_ALPHA, None)].agent_time, 1_200_000)
        project = report.project_figures(_WHOLE_DAY)[_ALPHA]
        self.assertEqual(project.agent_time, 1_200_000)
        self.assertEqual(project.activity_classes,
                         {"person_only": 60_000, "supervised": 300_000,
                          "unattended": 600_000, "blocked": 0})

    def test_background_subagent_works_beside_its_agent(self) -> None:
        """A background subagent returns its result at once, 2 s after the call, and works
        from 10:01 to 10:06 while the main agent goes on working to 10:10: the main agent
        holds 60 + 538 = 598 s and the subagent 300 s, so the part of the session holds 898
        s of agent time, where the union is 600, and the person as much. The classes of the
        person are clock time: the person is present 09:59-10:00 only, so 600 s are
        unattended and none supervised (metrics.md › Agent time)."""
        events_of = [*_delegating_agent("2026-06-15T10:01:02.000Z", _at("10:10")),
                     *_subagent(_at("10:01"), _at("10:06"), "background")]
        report = self._attributed(events_of)
        person = report.person_figures(_WHOLE_DAY)
        self.assertEqual(person.agent_time, 898_000)
        self.assertEqual(person.activity_classes,
                         {"person_only": 60_000, "supervised": 0, "unattended": 600_000,
                          "blocked": 0, "idle": 85_740_000})
        self.assertEqual(report.session_parts(_WHOLE_DAY),
                         {(_TOOL, _SESSION): {(_REPO, None): (60_000, 898_000)}})

    def test_foreground_subagent_adds_no_parallel_time(self) -> None:
        """A foreground subagent changes nothing: the main agent waits for it from the
        call of 10:01 to the result of 10:06, and that wait is no agent time, so the parts
        of the two agents never overlap and the sum equals the union. The main agent holds
        60 + 60 s, the subagent 300 s, and the session, as the union of its parts, 420 s
        (metrics.md › Agent time)."""
        events_of = [*_delegating_agent(_at("10:06"), _at("10:07")),
                     *_subagent(_at("10:01"), _at("10:06"), "foreground")]
        report = self._attributed(events_of)
        metrics = compute_metrics(events_of, [], _PARAMETERS)
        merged = total(union([(part.start, part.end) for part in metrics.agent]))
        self.assertEqual(report.person_figures(_WHOLE_DAY).agent_time, merged)
        self.assertEqual(report.session_parts(_WHOLE_DAY),
                         {(_TOOL, _SESSION): {(_REPO, None): (60_000, 420_000)}})

    def test_work_items_of_one_project(self) -> None:
        """Two work items of one project whose agent parts overlap: each part lies in the
        bucket of its work item, so the project holds the sum of its work items, 10 + 10 =
        20 minutes of agent time, where the union is 15 (metrics.md › Agent time, ›
        Attribution)."""
        events_of = [*_turn("session-1", _at("10:00"), _at("10:10"), _REPO),
                     *_turn("session-2", _at("10:05"), _at("10:15"), _REPO)]
        notes = [_note("2026-06-15T09:00:00.000Z", "note-one",
                       annotates={"tool": _TOOL, "session_id": "session-1"},
                       work_item="invented-1"),
                 _note("2026-06-15T09:00:00.000Z", "note-two",
                       annotates={"tool": _TOOL, "session_id": "session-2"},
                       work_item="invented-2")]
        report = self._attributed(events_of, notes)
        figures = report.figures(_WHOLE_DAY)
        self.assertEqual({bucket: held.agent_time for bucket, held in figures.items()},
                         {(_REPO, "invented-1"): 600_000, (_REPO, "invented-2"): 600_000})
        project = report.project_figures(_WHOLE_DAY)[_REPO]
        self.assertEqual(project.agent_time, 1_200_000)
        self.assertEqual(sum(held.agent_time for held in figures.values()),
                         project.agent_time)

    def test_two_copies_of_one_part_count_once(self) -> None:
        """Two overlapping parts of one agent, as two copies of one record give, 10:00-10:10
        and 10:05-10:15: they count once, 15 minutes, in the person, in the project, and in
        the part of the session (metrics.md › Agent time)."""
        signal = _signal(_at("10:00"), "uid-prompt", repo_hint=_REPO)
        call = _event(_at("10:10"), "uid-call", kind="agent_output", actor="system",
                      repo_hint=_REPO)
        copy = _event(_at("10:15"), "uid-copy", kind="agent_output", actor="system",
                      repo_hint=_REPO)
        agent = (_TOOL, _SESSION, _SESSION)
        metrics = Metrics(
            [HumanInterval(_ms("09:59"), _ms("10:00"), signal, "minimum_attention")], [],
            [AgentPart(_ms("10:00"), _ms("10:10"), agent, call),
             AgentPart(_ms("10:05"), _ms("10:15"), agent, copy)], [], [])
        report = split.attribute([signal, call, copy], [], [], metrics, _person(),
                                 support.scenario_days())
        self.assertEqual(report.person_figures(_WHOLE_DAY).agent_time, 900_000)
        self.assertEqual(report.project_figures(_WHOLE_DAY)[_REPO].agent_time, 900_000)
        self.assertEqual(report.session_parts(_WHOLE_DAY),
                         {(_TOOL, _SESSION): {(_REPO, None): (60_000, 900_000)}})

    def test_inferred_agent_share_of_the_sum(self) -> None:
        """Of two overlapping parts, the turn 10:00-10:10 rests on an inferred repository
        identity and the turn 10:05-10:15 on an observed one: the inferred part holds 10 of
        the 20 minutes of the sum, so the share is 0.5 in the bucket, in the project, and
        in the person; over the union of 15 minutes it would be 2/3 (metrics.md ›
        Attribution, ADR 0018)."""
        events_of = [*_turn("session-1", _at("10:00"), _at("10:10"), _REPO,
                            repo_basis="inferred"),
                     *_turn("session-2", _at("10:05"), _at("10:15"), _REPO,
                            repo_basis="observed")]
        report = self._attributed(events_of)
        for held in (report.figures(_WHOLE_DAY)[(_REPO, None)],
                     report.project_figures(_WHOLE_DAY)[_REPO],
                     report.person_figures(_WHOLE_DAY)):
            self.assertEqual(held.agent_time, 1_200_000)
            self.assertAlmostEqual(held.inferred_agent_share, 0.5)

    def test_inferred_agent_share_sums_over_the_inferred_agents(self) -> None:
        """The numerator of the share is a sum over the agents too: of three turns of one
        project, the turns 10:00-10:10 and 10:05-10:15, which overlap, both rest on an
        inferred repository identity and the turn 10:20-10:30 on an observed one, so the
        share is (10 + 10) / (10 + 10 + 10) = 2/3 in the bucket, in the project, and in the
        person. Over a numerator that is the union of the inferred turns it would be
        15 / 30 = 1/2, and over a denominator that is the union of every turn 20 / 25 = 4/5
        (metrics.md › Attribution, ADR 0018)."""
        events_of = [*_turn("session-1", _at("10:00"), _at("10:10"), _REPO,
                            repo_basis="inferred"),
                     *_turn("session-2", _at("10:05"), _at("10:15"), _REPO,
                            repo_basis="inferred"),
                     *_turn("session-3", _at("10:20"), _at("10:30"), _REPO,
                            repo_basis="observed")]
        report = self._attributed(events_of)
        for held in (report.figures(_WHOLE_DAY)[(_REPO, None)],
                     report.project_figures(_WHOLE_DAY)[_REPO],
                     report.person_figures(_WHOLE_DAY)):
            self.assertEqual(held.agent_time, 1_800_000)
            self.assertAlmostEqual(held.inferred_agent_share, 2 / 3)

    def test_window_of_two_spans(self) -> None:
        """A window of two spans, as a journey cuts a day: only the agent time inside the
        two spans counts. The turns 10:00-10:30 and 10:10-10:40 inside the spans 10:00-10:15
        and 10:25-10:45 give 15 + 5 minutes and 5 + 15 minutes, 40 minutes for the person,
        where the union of the turns gives 30 (metrics.md › Agent time, › Days and
        weeks)."""
        events_of = [*_turn("session-1", _at("10:00"), _at("10:30"), _ALPHA),
                     *_turn("session-2", _at("10:10"), _at("10:40"), _BETA)]
        report = self._attributed(events_of)
        window = [(_ms("10:00"), _ms("10:15")), (_ms("10:25"), _ms("10:45"))]
        self.assertEqual(report.person_figures(window).agent_time, 2_400_000)
        self.assertEqual({bucket: held.agent_time
                          for bucket, held in report.figures(window).items()},
                         {(_ALPHA, None): 1_200_000, (_BETA, None): 1_200_000})
        self.assertEqual(report.session_parts(window),
                         {(_TOOL, "session-1"): {(_ALPHA, None): (0, 1_200_000)},
                          (_TOOL, "session-2"): {(_BETA, None): (600_000, 1_200_000)}})

    def test_part_across_the_end_of_the_day(self) -> None:
        """A part that crosses the end of the day divides at the boundary, and each day
        follows the rule: the turns 23:30-00:30 and 23:45-00:45 give the first day 30 + 15
        = 45 minutes of agent time, where the union gives 30, and the second day 30 + 45 =
        75 minutes, where the union gives 45; the two days add up to the two turns of one
        hour each (metrics.md › Days and weeks, › Agent time)."""
        events_of = [*_turn("session-1", _at("23:30"), "2026-06-16T00:30:00.000Z", _ALPHA),
                     *_turn("session-2", _at("23:45"), "2026-06-16T00:45:00.000Z", _BETA)]
        report = self._attributed(events_of)
        first = report.person_figures(_WHOLE_DAY).agent_time
        second = report.person_figures(_window("2026-06-16T00:00",
                                               "2026-06-17T00:00")).agent_time
        self.assertEqual((first, second), (2_700_000, 4_500_000))
        self.assertEqual(first + second, 7_200_000)

    def test_window_inside_a_turn_that_holds_another_turn(self) -> None:
        """A window reads the agent time that can hold an instant of it: the turn
        10:00-11:00 of session-1 holds the turn 10:10-10:20 of session-2 and ends after
        it, so the window 10:30-10:40, inside the first turn and after the second, holds
        10 minutes of agent time, and the turns before the window and after it hold none
        of it (metrics.md › Agent time, › Days and weeks)."""
        events_of = [*_turn("session-1", _at("10:00"), _at("11:00"), _ALPHA),
                     *_turn("session-2", _at("10:10"), _at("10:20"), _BETA),
                     *_turn("session-3", _at("09:00"), _at("09:15"), _BETA),
                     *_turn("session-4", _at("11:30"), _at("12:00"), _ALPHA)]
        report = self._attributed(events_of)
        window = _window("2026-06-15T10:30", "2026-06-15T10:40")
        self.assertEqual(report.figures(window),
                         {(_ALPHA, None): split.BucketFigures(
                             0, 0, 600_000, 0,
                             {"person_only": 0, "supervised": 0, "unattended": 600_000,
                              "blocked": 0}, 0.0, 0.0)})
        self.assertEqual(report.person_figures(window).agent_time, 600_000)
        self.assertEqual(report.project_figures(window)[_ALPHA].agent_time, 600_000)


if __name__ == "__main__":
    unittest.main()
