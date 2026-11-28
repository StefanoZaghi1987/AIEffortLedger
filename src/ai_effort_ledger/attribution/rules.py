"""The matching of the identity rules and of the category rules: the narrower-pattern
test, the folders, the project of an event, and the category of a tool call
(configuration.md › Matching, metrics.md › Attribution, ADR 0009).

The most specific matching rule wins; two matching rules of which neither is more
specific apply none, never a silent choice: the event keeps the repository identity or
the stored category, and the error with the two rules goes to the report, which
`event_buckets` completes with one event that they match.
"""

import re
from collections.abc import Callable, Sequence
from datetime import date
from typing import TypeVar

from ..configuration import CategoryRule, IdentityRule, pattern_matches
from ..events import Event

_SENTINELS = tuple(chr(code) for code in range(32))
"""The characters that replace a `*` of a pattern in the narrower-pattern test; every
control character appears in no realistic pattern, so only a `*` can match one."""

_FOLDER_SEPARATOR = re.compile(r"[\\/]")
_DRIVE = re.compile(r"[A-Za-z]:")

_Rule = TypeVar("_Rule", IdentityRule, CategoryRule)


def pattern_narrower(p: str, q: str) -> bool:
    """Whether the pattern `p` matches a part of what the pattern `q` matches
    (configuration.md › Matching): `q` matches the text of `p` in which each `*` is a
    character that only a `*` of `q` matches — a control character that `q` holds nowhere,
    so no literal of `q` can match it.

    An exact name is a pattern without `*`; a pattern is narrower than an equal pattern,
    and the strict narrowness of two rules comes from comparing both ways.
    """
    for sentinel in _SENTINELS:
        if sentinel not in q:
            return pattern_matches(q, p.replace("*", sentinel))
    return False


def folder_matches(rule_folder: str, folder: str) -> bool:
    """Whether the folder is the folder of the rule or a folder inside it
    (configuration.md › Matching).

    The two paths compare as text, folder name by folder name, and the ledger never asks
    whether a folder exists on the machine. `/` and `\\` are the same separator, and the
    comparison has no regard to case when the folder of the rule is a Windows path — a
    drive letter or a UNC path — and regard to case otherwise.
    """
    rule_parts = _folder_parts(rule_folder)
    parts = _folder_parts(folder)
    if _is_windows(rule_folder):
        rule_parts = [part.lower() for part in rule_parts]
        parts = [part.lower() for part in parts]
    return len(parts) >= len(rule_parts) and parts[:len(rule_parts)] == rule_parts


def more_specific(x: IdentityRule, y: IdentityRule) -> bool:
    """Whether the identity rule `x` is more specific than the identity rule `y`
    (configuration.md › Matching): `x` has every condition of `y` with the same or a
    narrower value, and at least one more condition or one narrower value."""
    holds = (_holds_repository(x, y), _holds_folder(x, y), _holds_branch(x, y),
             _holds_days(x, y))
    if not all(holds):
        return False
    extra = ((x.repository is not None and y.repository is None)
             or (x.folder is not None and y.folder is None)
             or (x.branch is not None and y.branch is None)
             or (_has_days(x) and not _has_days(y)))
    narrower = (_folder_narrower(x, y) or _branch_narrower(x, y) or _days_narrower(x, y))
    return extra or narrower


def project_of(
    repository: str | None,
    folder: str | None,
    branch: str | None,
    day: date,
    rules: Sequence[IdentityRule],
) -> tuple[str | None, dict | None]:
    """The project that the identity rules give to an event observed with a repository
    identity, a folder, a branch, and a local day (configuration.md › Matching,
    metrics.md › Attribution, ADR 0009).

    The most specific matching rule wins. Two matching rules of which neither is more
    specific give `None` and an `identity_rule_conflict` error whose values name the two
    rules, which `event_buckets` completes with one event that they match. Without a
    matching rule the project is the repository identity itself, the default rule; an
    event without a repository identity stays unattributed.
    """
    matching = [rule for rule in rules if _rule_matches(rule, repository, folder, branch, day)]
    if not matching:
        return repository, None
    winner = _standout(matching, more_specific)
    if winner is not None:
        return winner.project, None
    first, second = _conflict_pair(matching, more_specific)
    return None, {
        "code": "identity_rule_conflict",
        "values": {"first": _identity_text(first), "second": _identity_text(second)},
    }


def category_of(
    tool_name: str,
    stored: str,
    rules: Sequence[CategoryRule],
) -> tuple[str, dict | None]:
    """The category of a tool call: the category that the most specific matching category
    rule gives, or the category that the adapter stored when no rule matches
    (configuration.md › Matching, metrics.md › Attribution).

    Two matching rules of which neither is narrower give the stored category and a
    `category_rule_conflict` error whose values name the two rules, for `attribute` of the
    report to show.
    """
    matching = [rule for rule in rules if pattern_matches(rule.tool, tool_name)]
    if not matching:
        return stored, None
    winner = _standout(matching, _tool_narrower)
    if winner is not None:
        return winner.category, None
    first, second = _conflict_pair(matching, _tool_narrower)
    return stored, {
        "code": "category_rule_conflict",
        "values": {"first": _category_text(first), "second": _category_text(second)},
    }


def effective_category(rules: Sequence[CategoryRule]) -> Callable[[Event], str]:
    """The category of a tool call after the category rules, as `MetricsParameters.category`
    holds it (configuration.md › Order; `cli` builds the parameters, because `configuration`
    and `attribution` are not below `metrics`, architecture.md › Modules).

    The callable gives `category_of` of a `tool_call` and the stored category of any other
    event, and leaves the `category_rule_conflict` to `attribute`, which reports it.
    """

    def category(event: Event) -> str:
        stored = event.get("tool_category", "other")
        if event.get("kind") != "tool_call":
            return stored
        effective, _error = category_of(event.get("tool_name", ""), stored, rules)
        return effective

    return category


def _rule_matches(
    rule: IdentityRule,
    repository: str | None,
    folder: str | None,
    branch: str | None,
    day: date,
) -> bool:
    """Whether the rule matches an event observed with a repository identity, a folder, a
    branch, and a local day: every condition the rule holds matches, and a repository in
    a rule is a repository identity that matches only itself (configuration.md ›
    Matching)."""
    if rule.repository is not None and rule.repository != repository:
        return False
    if rule.folder is not None and (folder is None or not folder_matches(rule.folder, folder)):
        return False
    if rule.branch is not None and (branch is None or not pattern_matches(rule.branch, branch)):
        return False
    if rule.first is not None and day < rule.first:
        return False
    if rule.last is not None and day > rule.last:
        return False
    return True


def _folder_parts(path: str) -> list[str]:
    """The folder names of a path, with `/` and `\\` as the same separator."""
    return [part for part in _FOLDER_SEPARATOR.split(path) if part]


def _is_windows(path: str) -> bool:
    """Whether the path is a Windows path: a drive letter or a UNC path
    (configuration.md › Matching)."""
    return bool(_DRIVE.match(path)) or path.startswith("\\\\") or path.startswith("//")


def _holds_repository(x: IdentityRule, y: IdentityRule) -> bool:
    """Whether `x` holds the repository condition of `y`, with the same identity."""
    return y.repository is None or x.repository == y.repository


def _holds_folder(x: IdentityRule, y: IdentityRule) -> bool:
    """Whether `x` holds the folder condition of `y`, with the same or a folder inside it."""
    return y.folder is None or (x.folder is not None and folder_matches(y.folder, x.folder))


def _holds_branch(x: IdentityRule, y: IdentityRule) -> bool:
    """Whether `x` holds the branch condition of `y`, with the same or a narrower pattern."""
    return y.branch is None or (x.branch is not None and pattern_narrower(x.branch, y.branch))


def _has_days(rule: IdentityRule) -> bool:
    """Whether the rule holds a condition on the range of local days."""
    return rule.first is not None or rule.last is not None


def _holds_days(x: IdentityRule, y: IdentityRule) -> bool:
    """Whether `x` holds the range of local days of `y`, with the same or a range inside
    it, both ends included."""
    if y.first is not None and (x.first is None or x.first < y.first):
        return False
    return not (y.last is not None and (x.last is None or x.last > y.last))


def _folder_narrower(x: IdentityRule, y: IdentityRule) -> bool:
    """Whether the folder of `x` is inside the folder of `y`, and not the other way."""
    return bool(x.folder is not None and y.folder is not None
                and folder_matches(y.folder, x.folder)
                and not folder_matches(x.folder, y.folder))


def _branch_narrower(x: IdentityRule, y: IdentityRule) -> bool:
    """Whether the pattern of the branch of `x` matches a part of what the pattern of `y`
    matches, and not the other way."""
    return bool(x.branch is not None and y.branch is not None
                and pattern_narrower(x.branch, y.branch)
                and not pattern_narrower(y.branch, x.branch))


def _days_narrower(x: IdentityRule, y: IdentityRule) -> bool:
    """Whether the range of local days of `x` is inside the range of `y`, and not the
    other way, both ends included."""
    return bool(_has_days(x) and _has_days(y)
                and _holds_days(x, y) and not _holds_days(y, x))


def _tool_narrower(x: CategoryRule, y: CategoryRule) -> bool:
    """Whether the pattern of the tool names of `x` matches a part of what the pattern of
    `y` matches, and not the other way: two rules of the same pattern conflict."""
    return pattern_narrower(x.tool, y.tool) and not pattern_narrower(y.tool, x.tool)


def _standout(
    matching: Sequence[_Rule],
    beats: Callable[[_Rule, _Rule], bool],
) -> _Rule | None:
    """The matching rule that beats every other matching rule, or None: more specific for
    the identity rules, narrower for the category rules."""
    for candidate in matching:
        if all(beats(candidate, other) for other in matching if other is not candidate):
            return candidate
    return None


def _conflict_pair(
    matching: Sequence[_Rule],
    beats: Callable[[_Rule, _Rule], bool],
) -> tuple[_Rule, _Rule]:
    """The first pair of matching rules, in the order of the configuration, of which
    neither beats the other. One exists whenever no rule beats every other: two rules
    that a third beats or that beat no rule stand in such a pair."""
    for index, first in enumerate(matching):
        for second in matching[index + 1:]:
            if not beats(first, second) and not beats(second, first):
                return first, second
    return matching[0], matching[1]


def _identity_text(rule: IdentityRule) -> str:
    """The identity rule as the text of an error value: the line of its entry and the
    project it gives."""
    return f"line {rule.line} ({rule.project})"


def _category_text(rule: CategoryRule) -> str:
    """The category rule as the text of an error value: the line of its entry and the
    category it gives."""
    return f"line {rule.line} ({rule.category})"
