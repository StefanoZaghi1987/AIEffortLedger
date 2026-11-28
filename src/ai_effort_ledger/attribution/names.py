"""The names of the projects: the default name of a repository identity, the names that
the person configuration gives, and the project identifiers of the declared events that
nothing resolves (metrics.md › Attribution, ADR 0019).

Reports group by project identifier and show the name. By default the name of a project
whose identifier is a repository identity comes from the identity: the last part of its
path, or the first 12 characters of a root-commit hash. An identifier that is no
repository identity is its own name, and an entry of the person configuration gives any
identifier another name. Two default names that are the same show more parts of their
path, so that a configuration without names never has the conflict; a name that the
person configuration gives to two project identifiers is a configuration error.
"""

from collections.abc import Iterable

from ..configuration import PersonConfiguration

_ROOT_COMMIT = "root-commit:"
"""The prefix of the repository identity of a repository without remotes
(event-schema.md › Encoding)."""

_NAME_CHARACTERS = 12
"""The characters of the hash of a root commit that its default name shows."""


def default_name(repository: str) -> str:
    """The name that reports show for a project whose identifier is the repository
    identity `repository`: the last part of its path, or the first 12 characters of a
    root-commit hash (metrics.md › Attribution, ADR 0019)."""
    if repository.startswith(_ROOT_COMMIT):
        return repository[len(_ROOT_COMMIT):len(_ROOT_COMMIT) + _NAME_CHARACTERS]
    return repository.rpartition("/")[2]


def project_names(
    identifiers: Iterable[str],
    repository_hints: Iterable[str],
    person: PersonConfiguration,
) -> tuple[dict[str, str], list[dict]]:
    """The name of each project identifier, and the configuration errors, as values for
    the report (metrics.md › Attribution, ADR 0019).

    An entry of the person configuration gives its name to its identifier. Otherwise an
    identifier that a repository identity of `repository_hints` gives takes the default
    name of the identity, and the identities whose default names are the same show more
    parts of their path until the names differ. An identifier that is no repository
    identity is its own name. A name that the person configuration gives to two project
    identifiers is a `project_name_conflict` error that names both.
    """
    given = {entry.id: entry.name for entry in person.projects}
    names = {identifier: given.get(identifier, identifier) for identifier in identifiers}
    hints = set(repository_hints)
    defaulted = {identifier: default_name(identifier) for identifier in names
                 if identifier not in given and identifier in hints}
    _widen(defaulted)
    names.update(defaulted)
    return names, _conflicts(person)


def declared_project_unknown(
    identifiers: Iterable[str],
    person: PersonConfiguration,
    repository_hints: Iterable[str],
) -> list[dict]:
    """One `declared_project_unknown` warning for each project identifier of a declared
    event that no identity rule, no `[[project]]` entry of the person configuration,
    and no repository identity of `repository_hints` gives (metrics.md › Attribution,
    ADR 0019)."""
    hints = set(repository_hints)
    named = {entry.id for entry in person.projects}
    ruled = {rule.project for rule in person.identity_rules}
    warnings: list[dict] = []
    seen: set[str] = set()
    for identifier in identifiers:
        if identifier in seen:
            continue
        seen.add(identifier)
        if identifier not in hints and identifier not in named and identifier not in ruled:
            warnings.append({"code": "declared_project_unknown",
                             "values": {"project": identifier}})
    return warnings


def _widen(defaulted: dict[str, str]) -> None:
    """Give the identities whose default names are the same a name of one more part of
    their path, until the names of every two of them differ (ADR 0019).

    A name that the whole path cannot make different, such as the shared start of two
    root-commit hashes, stays as it is: only a name of the person configuration can
    conflict.
    """
    depth = dict.fromkeys(defaulted, 1)
    while True:
        seen: dict[str, str] = {}
        shared: set[str] = set()
        for identifier, name in defaulted.items():
            other = seen.get(name)
            if other is not None:
                shared.update((identifier, other))
            seen[name] = identifier
        widened = False
        for identifier in shared:
            parts = identifier.count("/") + 1
            if depth[identifier] < parts:
                depth[identifier] += 1
                defaulted[identifier] = _suffix(identifier, depth[identifier])
                widened = True
        if not shared or not widened:
            return


def _suffix(repository: str, depth: int) -> str:
    """The last `depth` parts of the path of the repository identity."""
    return "/".join(repository.split("/")[-depth:])


def _conflicts(person: PersonConfiguration) -> list[dict]:
    """A `project_name_conflict` error for each name that the person configuration gives
    to more than one project identifier, with the first two of them (ADR 0019)."""
    named: dict[str, list[str]] = {}
    for entry in person.projects:
        held = named.setdefault(entry.name, [])
        if entry.id not in held:
            held.append(entry.id)
    return [{"code": "project_name_conflict", "values": {"first": held[0], "second": held[1]}}
            for held in named.values() if len(held) > 1]
