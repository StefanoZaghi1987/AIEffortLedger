"""The repository identity of a folder, read from the files of git, without running git.

The search finds `.git`, a folder or a pointer file of a worktree, follows `commondir` to the
common git directory, and reads the remote URL from its `config`, without `include` files and
without `insteadOf` rewrites; when no usable remote exists, it reads the root commit from the
object store (ingestion.md › Repository identity, ADR 0004).
"""

import json
import os
import re
from collections.abc import Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import NamedTuple

from .objects import root_commit

SYSTEM_PATHS = {"Windows": PureWindowsPath, "Linux": PurePosixPath, "Darwin": PurePosixPath}

OBSERVED = "observed"
INFERRED = "inferred"

SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*://")
DRIVE = re.compile(r"^[A-Za-z]:")
PORT = re.compile(r":[0-9]+$")


class RepositoryIdentity(NamedTuple):
    """The repository identity of a folder and whether it was observed or inferred."""

    hint: str
    basis: str


class RootCommits:
    """The root commit of each repository already read, by the path of its common git
    directory, kept in `repositories.json` of the machine-local data folder."""

    def __init__(self) -> None:
        self._commits: dict[str, str] = {}

    def load(self, path: Path) -> None:
        """Read the file into the store; a missing or unreadable file leaves it empty."""
        try:
            read: object = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            read = {}
        if isinstance(read, dict):
            self._commits = {str(key): str(value) for key, value in read.items()}
        else:
            self._commits = {}

    def save(self, path: Path) -> None:
        """Write the store to the file, creating the parent folder when it is missing."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self._commits, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")

    def get(self, common_dir: str) -> str | None:
        """The root commit of the repository with this common git directory, or None."""
        return self._commits.get(common_dir)

    def put(self, common_dir: str, commit: str) -> None:
        """Remember the root commit of the repository with this common git directory."""
        self._commits[common_dir] = commit


def normalize_remote(url: str) -> str | None:
    """The repository identity of a remote URL, or None for a local folder or `file://`.

    The steps of ingestion.md › Repository identity: a URL with a scheme loses the scheme, the
    user information with any password or token, and the port; an address without a scheme,
    `user@host:path`, loses the user and becomes `host/path`; a final `/` and then a final
    `.git` go; all is written in lower case. No credential survives.
    """
    if SCHEME.match(url):
        return _with_scheme(url)
    if DRIVE.match(url) or url.startswith("/"):
        return None
    colon = url.find(":")
    if colon <= 0:
        return None
    host = url[:colon]
    at = host.rfind("@")
    if at >= 0:
        host = host[at + 1:]
    if not host:
        return None
    return _identity_text(host + "/" + url[colon + 1:])


def _with_scheme(url: str) -> str | None:
    """Normalize a URL that has a scheme; `file://` and a drive letter name a folder of the
    machine, and its path names folders of the machine too, so neither becomes an identity."""
    scheme, _, rest = url.partition("://")
    if scheme.lower() == "file":
        return None
    authority, _, path = rest.partition("/")
    at = authority.rfind("@")
    if at >= 0:
        authority = authority[at + 1:]
    authority = PORT.sub("", authority)
    if not authority:
        return None
    return _identity_text(authority + "/" + path)


def _identity_text(identity: str) -> str:
    """Remove a final `/`, then a final `.git`, and write all in lower case."""
    if identity.endswith("/"):
        identity = identity[:-1]
    if identity.endswith(".git"):
        identity = identity[:-4]
    return identity.lower()


def find_git(folder: Path, home: Path) -> tuple[Path, Path] | None:
    """Find `.git` walking up from the folder; the pair of the git folder and the common git
    directory, or None.

    The search never reaches the home folder of the person or the root of a drive, so a
    repository there gives no identity to the folders inside it (ingestion.md › Repository
    identity). A worktree reaches its repository through the `gitdir` pointer file and
    `commondir`.
    """
    candidate = folder
    while candidate != home and candidate.parent != candidate:
        dot_git = candidate / ".git"
        if dot_git.is_dir():
            return dot_git, _common_directory(dot_git)
        if dot_git.is_file():
            return _from_pointer_file(dot_git, candidate)
        candidate = candidate.parent
    return None


def _from_pointer_file(dot_git: Path, folder: Path) -> tuple[Path, Path] | None:
    """Read a `.git` file that points to the git folder of a worktree, `gitdir: <path>`."""
    text = dot_git.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("gitdir:"):
            continue
        pointed = line.partition(":")[2].strip()
        if not pointed:
            return None
        git_folder = _joined(folder, pointed)
        return git_folder, _common_directory(git_folder)
    return None


def _common_directory(git_folder: Path) -> Path:
    """Follow the `commondir` file of the git folder to the common git directory."""
    commondir = git_folder / "commondir"
    if commondir.is_file():
        text = commondir.read_text(encoding="utf-8", errors="replace").strip()
        if text:
            return _joined(git_folder, text)
    return _joined(git_folder, ".")


def _joined(base: Path, text: str) -> Path:
    """The path of the text, relative to the base when it is not absolute, normalized."""
    path = Path(text)
    if not path.is_absolute():
        path = base / path
    return Path(os.path.normpath(str(path)))


def _read_remotes(common_dir: Path) -> list[tuple[str, str]]:
    """The `[remote "<name>"]` sections of a `config` with their first `url`, in file order.

    The reader is small and line-based: a full-line comment goes, a section header ends at
    its closing `]` and what follows it is a comment, each value is read the git way
    (`_config_value`), and nothing of `include` files is read and no `insteadOf` rewrite is
    applied. A config that cannot be read, or that holds a value that git refuses, gives no
    remote.
    """
    try:
        text = (common_dir / "config").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.splitlines()
    remotes: list[tuple[str, str]] = []
    section: str | None = None
    seen: set[str] = set()
    position = 0
    while position < len(lines):
        line = lines[position]
        position += 1
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith(";"):
            continue
        if stripped.startswith("["):
            header = _section_header(stripped)
            if header is not None:
                section = _remote_name(header)
                continue
        name, equals, rest = line.partition("=")
        if not equals:
            continue
        value, position = _config_value(rest, lines, position)
        if value is None:
            return []
        if section is not None and section not in seen and name.strip().lower() == "url":
            seen.add(section)
            remotes.append((section, value))
    return remotes


_ESCAPES = {"n": "\n", "t": "\t", "b": "\b", '"': '"', "\\": "\\"}
"""The escapes that git reads in a value of a `config`, each with its character."""

_SPACES = " \t\v\f\r"
"""The characters that git reads as spaces in a value of a `config`."""


def _config_value(text: str, lines: Sequence[str], position: int) -> tuple[str | None, int]:
    """The value of a variable of a `config` that starts in the text, read the git way, and
    the position of the line after it in the lines; None when git refuses the value.

    An unquoted `#` or `;` starts a comment to the end of the line; the spaces before the
    value and after it go, and the spaces inside it stay; double quotes go and keep the
    characters between them; a backslash escapes `"`, `\\`, `n`, `t`, and `b`, and a
    backslash at the end of a line continues the value on the next line, without the line
    break. Git refuses any other escape and a double quote that the line does not close.
    """
    value: list[str] = []
    trim: int | None = None
    quoted = False
    index = 0
    while index < len(text):
        char = text[index]
        index += 1
        if char in _SPACES and not quoted:
            if trim is None:
                trim = len(value)
            if value:
                value.append(char)
            continue
        if char in "#;" and not quoted:
            break
        trim = None
        if char == "\\":
            if index == len(text):
                if position < len(lines):
                    text, index, position = lines[position], 0, position + 1
                continue
            escaped = _ESCAPES.get(text[index])
            index += 1
            if escaped is None:
                return None, position
            value.append(escaped)
            continue
        if char == '"':
            quoted = not quoted
            continue
        value.append(char)
    if quoted:
        return None, position
    return "".join(value if trim is None else value[:trim]), position


def _section_header(line: str) -> str | None:
    """The header that a section line holds, up to its closing `]`, or None when the line
    closes no header: what follows the closing bracket is a comment, which git reads as
    such, and a bracket inside the quoted name of a section is not the closing one."""
    quoted = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
        elif char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == "]" and not quoted:
            return line[:index + 1]
    return None


def _remote_name(line: str) -> str | None:
    """The name of a `[remote "<name>"]` line; a header of any other section gives None.

    Git writes other quoted sections beside the remotes, `[submodule "<path>"]` with its
    `url` among them; taking their name would take the identity of another repository.
    """
    first = line.find('"')
    if first < 0 or line[1:first].strip().lower() != "remote":
        return None
    last = line.rfind('"')
    if last > first:
        return line[first + 1:last]
    return None


def _remote_identity(
    remotes: list[tuple[str, str]],
    preferred_remotes: Sequence[str],
) -> str | None:
    """The identity of the remote the person prefers, otherwise of the first remote in the
    alphabetical order of the names, as text; a remote that is a local folder or a `file://`
    URL is not used."""
    usable = [(name, url) for name, url in remotes if normalize_remote(url) is not None]
    for preferred in preferred_remotes:
        for name, url in usable:
            if name == preferred:
                return normalize_remote(url)
    if usable:
        first = min(usable, key=lambda remote: remote[0])
        return normalize_remote(first[1])
    return None


def resolve_folder(
    cwd: str,
    system: str,
    home: Path,
    preferred_remotes: Sequence[str],
    root_commits: RootCommits,
) -> tuple[RepositoryIdentity | None, list[dict]]:
    """Resolve the repository identity of a `cwd`, with the warnings of the resolution.

    A `cwd` that is not an absolute path of the named system is not resolved, without a
    warning (ingestion.md › Repository identity). A folder that no longer exists resolves
    through its nearest existing parent folder, and the identity is inferred, not observed
    (ADR 0018). Without a usable remote the root commit decides: the reader follows the
    `HEAD` of the git folder — of the worktree, when the folder is one — through the
    reference files and `packed-refs` of the common git directory to the first commit with
    no parent, and the identity is `root-commit:` with its hash. A shallow clone and a
    history the reader cannot reach give no identity and the warning `shallow_clone`. The
    root commit of each repository is kept in `root_commits`, so its objects are read once.
    """
    path_class = SYSTEM_PATHS.get(system)
    if path_class is None or not path_class(cwd).is_absolute():
        return None, []
    probe = Path(cwd)
    basis = OBSERVED
    while not probe.is_dir():
        if probe.parent == probe:
            return None, []
        probe = probe.parent
        basis = INFERRED
    found = find_git(probe, home)
    if found is None:
        return None, []
    identity = _remote_identity(_read_remotes(found[1]), preferred_remotes)
    if identity is None:
        common = str(found[1])
        commit = root_commits.get(common)
        if commit is None:
            commit = root_commit(found[0], found[1])
            if commit is None:
                return None, [{"code": "shallow_clone", "values": {"folder": cwd}}]
            root_commits.put(common, commit)
        identity = "root-commit:" + commit
    return RepositoryIdentity(identity, basis), []
