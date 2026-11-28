"""Tests of the repository module: remotes, `.git` discovery, the root commit, and identity.

The repositories of the tests are built by hand in temporary folders, with invented config
text and invented git objects; no test runs git (ADR 0004).
"""

import platform
import shutil
import unittest
from pathlib import Path

import support

from ai_effort_ledger import repository
from ai_effort_ledger.repository import discovery, objects

SYSTEM = platform.system()
TREE = support.TREE

CONFIG_ORIGIN = """\
[core]
    repositoryformatversion = 0
[remote "origin"]
    url = https://Example.org/Team/App.git
    fetch = +refs/heads/*:refs/remotes/origin/*
"""

CONFIG_ORIGIN_AND_UPSTREAM = """\
[remote "origin"]
    url = https://Example.org/Team/Mirror.git
[remote "upstream"]
    url = ssh://git@example.org:22/team/App.git
"""

CONFIG_LOCAL_ORIGIN = """\
[remote "origin"]
    url = file:///srv/git/app
[remote "mirror"]
    url = git@example.org:Team/App.git
"""

CONFIG_SUBMODULE = """\
[submodule "tools/lib"]
    path = tools/lib
    url = https://Example.org/Team/Lib.git
"""

CONFIG_SUBMODULE_BEFORE_ORIGIN = """\
[submodule "origin"]
    url = https://Example.org/Team/Lib.git
[remote "origin"]
    url = https://Example.org/Team/App.git
"""

CONFIG_NO_REMOTE = """\
[core]
    repositoryformatversion = 0
"""

CONFIG_ZZ_THEN_AA = """\
[remote "zz"]
    url = https://zz.example.org/Team/Late.git
[remote "aa"]
    url = https://aa.example.org/Team/First.git
"""

CONFIG_CASE_NAMES = """\
[remote "ab"]
    url = https://lower.example.org/Team/Lower.git
[remote "AA"]
    url = https://upper.example.org/Team/Upper.git
[remote "aB"]
    url = https://mixed.example.org/Team/Mixed.git
"""

CONFIG_CASE_TWO_NAMES = """\
[remote "aB"]
    url = https://mixed.example.org/Team/Mixed.git
[remote "ab"]
    url = https://lower.example.org/Team/Lower.git
"""

CONFIG_CASE_FOLDED_NAMES = """\
[remote "aa"]
    url = https://lower.example.org/Team/Lower.git
[remote "AB"]
    url = https://upper.example.org/Team/Upper.git
"""


CONFIG_ONLY_LOCAL_ORIGIN = """\
[remote "origin"]
    url = file:///srv/git/app
"""

CONFIG_INLINE_COMMENTS = """\
[remote "origin"]
    url = https://Example.org/Team/App.git   # the remote of the team
[remote "mirror"]
    url = git@example.org:Team/Mirror.git;a second copy
[remote "quoted"]
    url = "https://example.org/team/a#b;c.git" ; quoted characters stay
[remote "escaped"]
    url = https://example.org/team/\\"d\\"\\\\e.git
"""

CONFIG_CONTINUED = """\
[remote "origin"]
    url = https://example.org/\\
Team/App.git # the line goes on
    fetch = +refs/heads/*:refs/remotes/origin/*
"""

CONFIG_OPEN_QUOTE = """\
[remote "open"]
    url = "https://example.org/team/open.git
[remote "origin"]
    url = https://example.org/team/app.git
"""

CONFIG_UNKNOWN_ESCAPE = """\
[remote "origin"]
    url = https://example.org/team/\\app.git
"""

CONFIG_COMMENTED_HEADERS = """\
[core]
    repositoryformatversion = 0
[remote "origin"] # my remote of the team
    url = https://Example.org/Team/App.git
[remote "mir[r]or"]; the second copy
    url = git@example.org:Team/Mirror.git
"""



def write_repository(folder: Path, config_text: str) -> Path:
    """Write a hand-made repository into the folder: a `.git` folder with the config text."""
    git_folder = folder / ".git"
    git_folder.mkdir(parents=True)
    (git_folder / "config").write_text(config_text, encoding="utf-8")
    return git_folder


def search_home(folder: Path) -> Path:
    """A home folder for the search: above the folder, below the root of its drive."""
    home = folder
    while home.parent.parent != home.parent:
        home = home.parent
    return home


def resolve(
    folder: Path, preferred: list[str]
) -> tuple[repository.RepositoryIdentity | None, list[dict]]:
    """Resolve a folder of the running system, with a home above it."""
    return repository.resolve_folder(
        str(folder), SYSTEM, search_home(folder), preferred, repository.RootCommits())


def build_chain(messages: list[str]) -> tuple[list[bytes], list[str]]:
    """The contents of a chain of commits, each the child of the one before it, and their
    names in the same order."""
    contents: list[bytes] = []
    names: list[str] = []
    for message in messages:
        content = support.commit_object(TREE, names[-1:], message)
        contents.append(content)
        names.append(support.object_name("commit", content))
    return contents, names


def write_chain(git_folder: Path, contents: list[bytes]) -> None:
    """Write the contents of a chain as loose commit objects."""
    for content in contents:
        support.write_loose_object(git_folder, "commit", content)


def point_head(git_folder: Path, name: str) -> None:
    """Point `HEAD` at `refs/heads/main`, a loose reference that holds the named commit."""
    support.write_loose_ref(git_folder, "refs/heads/main", name)
    support.write_head(git_folder, "refs/heads/main")


def shallow_warning(folder: Path) -> list[dict]:
    """The warning of a repository whose root commit the reader cannot reach."""
    return [{"code": "shallow_clone", "values": {"folder": str(folder)}}]


class TestNormalizeRemote(unittest.TestCase):
    """The URL steps of ingestion.md › Repository identity."""

    def test_normalize_remote(self) -> None:
        n = repository.normalize_remote
        self.assertEqual(
            n("https://user:secret@Example.org:8443/Team/App.git/"),
            "example.org/team/app")  # "/" first
        self.assertEqual(n("https://example.org/team/App/"), "example.org/team/app")
        self.assertEqual(n("git@example.org:Team/App.git"), "example.org/team/app")
        self.assertEqual(n("ssh://git@example.org:22/team/app"), "example.org/team/app")
        self.assertIsNone(n("file:///srv/app"))
        self.assertIsNone(n(r"C:\repos\app"))
        self.assertIsNone(n("/srv/git/app"))


class TestRemotes(unittest.TestCase):
    """The remote that gives the identity: the preferred names, then the alphabetical order
    of the names."""

    def test_preferred_remote_wins(self) -> None:
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_ORIGIN_AND_UPSTREAM)
            identity, warnings = resolve(folder, ["upstream", "origin"])
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/app", "observed"))
        self.assertEqual(warnings, [])

    def test_first_remote_by_name_otherwise(self) -> None:
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_ORIGIN_AND_UPSTREAM)
            identity, warnings = resolve(folder, ["gitlab"])
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/mirror", "observed"))
        self.assertEqual(warnings, [])

    def test_first_remote_in_the_alphabetical_order_of_the_names(self) -> None:
        """Without a preferred name, the remote that gives the identity is the first in the
        alphabetical order of the names, as text — not the first that the file holds
        (ingestion.md › Repository identity)."""
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_ZZ_THEN_AA)
            identity, warnings = resolve(folder, ["gitlab"])
        self.assertEqual(
            identity, repository.RepositoryIdentity("aa.example.org/team/first", "observed"))
        self.assertEqual(warnings, [])

    def test_the_order_of_the_names_is_the_order_of_their_code_points(self) -> None:
        """The alphabetical order of the names is the order of the names as text, whatever
        the file holds and whatever machine reads it: the order of the code points, so a
        name in upper case comes before one in lower case, and at equal first letters `B`
        comes before `b` — `[AA, ab, aB]` resolves to `AA`, and `[aB, ab]` to `aB`
        (ingestion.md › Repository identity: "the alphabetical order of the names, as
        text")."""
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_CASE_NAMES)
            identity, warnings = resolve(folder, ["gitlab"])
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_CASE_TWO_NAMES)
            other, other_warnings = resolve(folder, ["gitlab"])
        self.assertEqual(
            identity, repository.RepositoryIdentity("upper.example.org/team/upper", "observed"))
        self.assertEqual(warnings, [])
        self.assertEqual(
            other, repository.RepositoryIdentity("mixed.example.org/team/mixed", "observed"))
        self.assertEqual(other_warnings, [])

    def test_names_that_fold_together_resolve_by_their_code_points(self) -> None:
        """Two names that fold to one text but differ in code points — `[aa, AB]` — resolve to
        `AB`'s remote, the code point of `A` coming before `a`; a comparison of the folded
        names would pick `aa` (ingestion.md › Repository identity: "the alphabetical order
        of the names, as text")."""
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_CASE_FOLDED_NAMES)
            identity, warnings = resolve(folder, ["gitlab"])
        self.assertEqual(
            identity, repository.RepositoryIdentity("upper.example.org/team/upper", "observed"))
        self.assertEqual(warnings, [])

    def test_local_remote_is_skipped(self) -> None:
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_LOCAL_ORIGIN)
            identity, warnings = resolve(folder, ["origin"])
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/app", "observed"))
        self.assertEqual(warnings, [])

    def test_submodule_section_is_not_read(self) -> None:
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_SUBMODULE)
            remotes = discovery._read_remotes(git_folder)
            identity, warnings = resolve(folder, ["origin"])
        self.assertEqual(remotes, [])
        self.assertIsNone(identity)
        self.assertEqual(warnings, shallow_warning(folder))

    def test_submodule_does_not_hijack_the_remote(self) -> None:
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_SUBMODULE_BEFORE_ORIGIN)
            identity, warnings = resolve(folder, ["origin"])
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/app", "observed"))
        self.assertEqual(warnings, [])

    def test_inline_comment_is_no_part_of_the_url(self) -> None:
        """A value is read the git way: an unquoted `#` or `;` starts a comment, the spaces
        before it go, the characters between double quotes stay, and a backslash escapes
        a double quote and a backslash."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_INLINE_COMMENTS)
            remotes = discovery._read_remotes(git_folder)
            identity, warnings = resolve(folder, ["origin"])
        self.assertEqual(remotes, [
            ("origin", "https://Example.org/Team/App.git"),
            ("mirror", "git@example.org:Team/Mirror.git"),
            ("quoted", "https://example.org/team/a#b;c.git"),
            ("escaped", 'https://example.org/team/"d"\\e.git'),
        ])
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/app", "observed"))
        self.assertEqual(warnings, [])

    def test_comment_after_a_section_header_is_no_part_of_it(self) -> None:
        """A header line ends at its closing `]`, which a quoted name of a section may
        hold: what follows the closing bracket is a comment, which git reads as such, so
        `[remote "origin"] # my remote` names the remote and the reader takes its url
        (`ingestion.md` › Repository identity)."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_COMMENTED_HEADERS)
            remotes = discovery._read_remotes(git_folder)
            identity, warnings = resolve(folder, ["origin"])
        self.assertEqual(remotes, [
            ("origin", "https://Example.org/Team/App.git"),
            ("mir[r]or", "git@example.org:Team/Mirror.git"),
        ])
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/app", "observed"))
        self.assertEqual(warnings, [])

    def test_backslash_at_the_end_of_a_line_continues_the_value(self) -> None:
        """A backslash at the end of a line continues the value on the next line, without
        the line break, and the comment of the next line goes."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_CONTINUED)
            remotes = discovery._read_remotes(git_folder)
            identity, warnings = resolve(folder, ["origin"])
        self.assertEqual(remotes, [("origin", "https://example.org/Team/App.git")])
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/app", "observed"))
        self.assertEqual(warnings, [])

    def test_config_that_git_refuses_gives_no_remote(self) -> None:
        """A value that git refuses, a double quote that the line does not close or an
        escape that git does not know, makes the whole config one that git cannot read,
        so it gives no remote, as a config that cannot be read."""
        for config in (CONFIG_OPEN_QUOTE, CONFIG_UNKNOWN_ESCAPE):
            with self.subTest(config=config), support.TemporaryFolder() as folder:
                git_folder = write_repository(folder, config)
                self.assertEqual(discovery._read_remotes(git_folder), [])


class TestDiscovery(unittest.TestCase):
    """The search for `.git`: the pointer file, `commondir`, and the stop rules."""

    def test_git_folder_returns_itself(self) -> None:
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_ORIGIN)
            found = repository.find_git(folder, search_home(folder))
        self.assertEqual(found, (git_folder, git_folder))

    def test_worktree_file_and_commondir(self) -> None:
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_ORIGIN)
            worktree_git = git_folder / "worktrees" / "first"
            worktree_git.mkdir(parents=True)
            (worktree_git / "commondir").write_text("../..\n", encoding="utf-8")
            worktree = folder / "first-worktree"
            worktree.mkdir()
            (worktree / ".git").write_text(f"gitdir: {worktree_git}\n", encoding="utf-8")
            found = repository.find_git(worktree, search_home(folder))
            identity, warnings = repository.resolve_folder(
                str(worktree), SYSTEM, search_home(folder), ["origin"], repository.RootCommits())
        self.assertEqual(found, (worktree_git, git_folder))
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/app", "observed"))
        self.assertEqual(warnings, [])

    def test_search_stops_at_home(self) -> None:
        with support.TemporaryFolder() as folder:
            home = folder / "home"
            home.mkdir()
            write_repository(home, CONFIG_ORIGIN)
            deep = home / "project" / "deep"
            deep.mkdir(parents=True)
            identity, warnings = repository.resolve_folder(
                str(deep), SYSTEM, home, ["origin"], repository.RootCommits())
        self.assertIsNone(identity)
        self.assertEqual(warnings, [])

    def test_search_stops_at_the_drive_root(self) -> None:
        with support.TemporaryFolder() as folder:
            root = Path(folder.anchor)
            guard = folder.parent
            while True:
                if (guard / ".git").exists():
                    self.skipTest(f"the real ancestor {guard} holds a .git")
                if guard == root:
                    break
                guard = guard.parent
            below = folder / "deep"
            below.mkdir()
            identity, warnings = repository.resolve_folder(
                str(below), SYSTEM, root, ["origin"], repository.RootCommits())
        self.assertIsNone(identity)
        self.assertEqual(warnings, [])


class TestResolve(unittest.TestCase):
    """resolve_folder: the missing folder, the foreign path, and the config it ignores."""

    def test_missing_folder_is_inferred(self) -> None:
        with support.TemporaryFolder() as folder:
            write_repository(folder, CONFIG_ORIGIN)
            gone = folder / "removed" / "sub"
            identity, warnings = resolve(gone, ["origin"])
        self.assertEqual(
            identity, repository.RepositoryIdentity("example.org/team/app", "inferred"))
        self.assertEqual(warnings, [])

    def test_foreign_path_is_not_resolved(self) -> None:
        identity, warnings = repository.resolve_folder(
            "/home/vm/app", "Windows", Path("C:/Users/Person"), ["origin"],
            repository.RootCommits())
        self.assertIsNone(identity)
        self.assertEqual(warnings, [])

    def test_config_include_is_not_read(self) -> None:
        with support.TemporaryFolder() as folder:
            git_folder = folder / ".git"
            git_folder.mkdir()
            included = folder / "other.config"
            included.write_text(CONFIG_ORIGIN, encoding="utf-8")
            (git_folder / "config").write_text(f"[include]\n    path = {included}\n",
                                               encoding="utf-8")
            identity, warnings = resolve(folder, ["origin"])
        self.assertIsNone(identity)
        self.assertEqual(warnings, shallow_warning(folder))


class TestRootCommits(unittest.TestCase):
    """The store of the root commits, over `repositories.json` of the machine."""

    def test_root_commits_are_kept(self) -> None:
        with support.TemporaryFolder() as folder:
            path = folder / "machine" / "repositories.json"
            common = str(folder / "repo" / ".git")
            store = repository.RootCommits()
            self.assertIsNone(store.get(common))
            store.put(common, "0f1e2d3c" * 5)
            self.assertEqual(store.get(common), "0f1e2d3c" * 5)
            store.save(path)
            again = repository.RootCommits()
            again.load(path)
            self.assertEqual(again.get(common), "0f1e2d3c" * 5)
            fresh = repository.RootCommits()
            fresh.load(folder / "absent.json")
            self.assertIsNone(fresh.get(common))


class TestRootCommit(unittest.TestCase):
    """The walk of objects.root_commit from `HEAD` to the first commit with no parent."""

    def test_root_commit_from_loose_objects(self) -> None:
        """`HEAD` through a loose reference to three loose commits: the first commit."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_NO_REMOTE)
            contents, names = build_chain(["first", "second", "third"])
            write_chain(git_folder, contents)
            point_head(git_folder, names[2])
            found = objects.root_commit(git_folder, git_folder)
        self.assertEqual(found, names[0])

    def test_head_through_packed_refs(self) -> None:
        """`refs/heads/main` is only in `packed-refs`: the walk still finds the first commit."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_NO_REMOTE)
            contents, names = build_chain(["first", "second", "third"])
            write_chain(git_folder, contents)
            support.write_packed_refs(git_folder, [("refs/heads/main", names[2])])
            support.write_head(git_folder, "refs/heads/main")
            found = objects.root_commit(git_folder, git_folder)
        self.assertEqual(found, names[0])

    def test_root_commit_in_pack(self) -> None:
        """Three whole commits in one pack with its index: the walk reads them from the pack."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_NO_REMOTE)
            contents, names = build_chain(["first", "second", "third"])
            support.write_pack(
                git_folder, [support.Whole("commit", content) for content in contents])
            point_head(git_folder, names[2])
            found = objects.root_commit(git_folder, git_folder)
        self.assertEqual(found, names[0])

    def test_ofs_delta_commit(self) -> None:
        """The second and third commits of a pack are deltas against the objects before them."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_NO_REMOTE)
            contents, names = build_chain(["first", "second", "third"])
            support.write_pack(git_folder, [
                support.Whole("commit", contents[0]),
                support.OfsDelta(0, support.delta_from(contents[0], contents[1]),
                                 "commit", contents[1]),
                support.OfsDelta(1, support.delta_from(contents[1], contents[2]),
                                 "commit", contents[2]),
            ])
            point_head(git_folder, names[2])
            found = objects.root_commit(git_folder, git_folder)
        self.assertEqual(found, names[0])

    def test_ref_delta_commit(self) -> None:
        """The second commit of a pack is a `REF_DELTA` that names its base object."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_NO_REMOTE)
            contents, names = build_chain(["first", "second"])
            support.write_pack(git_folder, [
                support.Whole("commit", contents[0]),
                support.RefDelta(names[0], support.delta_from(contents[0], contents[1]),
                                 "commit", contents[1]),
            ])
            point_head(git_folder, names[1])
            found = objects.root_commit(git_folder, git_folder)
        self.assertEqual(found, names[0])

    def test_first_parent_is_followed(self) -> None:
        """A merge commit: the walk follows the first parent; the second parent names an
        object that is not in the store, so following it would end the walk with None."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_NO_REMOTE)
            contents, names = build_chain(["first", "second"])
            write_chain(git_folder, contents)
            merge = support.commit_object(TREE, [names[1], TREE], "merge")
            merge_name = support.write_loose_object(git_folder, "commit", merge)
            point_head(git_folder, merge_name)
            found = objects.root_commit(git_folder, git_folder)
        self.assertEqual(found, names[0])


class TestResolveRootCommit(unittest.TestCase):
    """resolve_folder without a usable remote: the identity, the warning, and the store."""

    def test_worktree_head_when_the_main_head_is_unborn(self) -> None:
        """The root commit walk starts at the `HEAD` of the git folder itself — the
        worktree's, when the folder is that of a worktree — while the references and the
        objects are the common git directory's: a linked worktree whose main `HEAD` names
        a branch that no reference holds resolves the root commit that its own `HEAD`
        reaches, where the common `HEAD` reaches none, and no `shallow_clone` warning
        lies about a clone the repository does not have (ingestion.md › Repository
        identity). The repository is the one `git init -b main` and `git worktree add`
        leave, with the first commit made in the worktree alone."""
        with support.TemporaryFolder() as folder:
            common = folder / "main" / ".git"
            common.mkdir(parents=True)
            (common / "config").write_text(CONFIG_NO_REMOTE, encoding="utf-8")
            worktree_git = common / "worktrees" / "first"
            worktree_git.mkdir(parents=True)
            (worktree_git / "commondir").write_text("../..\n", encoding="utf-8")
            contents, names = build_chain(["first", "second"])
            write_chain(common, contents)
            support.write_loose_ref(common, "refs/heads/topic", names[1])
            support.write_head(common, "refs/heads/main")  # unborn: no reference holds it
            support.write_head(worktree_git, "refs/heads/topic")
            worktree = folder / "first-worktree"
            worktree.mkdir()
            (worktree / ".git").write_text(f"gitdir: {worktree_git}\n", encoding="utf-8")
            identity, warnings = repository.resolve_folder(
                str(worktree), SYSTEM, search_home(folder), ["origin"],
                repository.RootCommits())
            self.assertEqual(identity, repository.RepositoryIdentity(
                "root-commit:" + names[0], "observed"))
            self.assertEqual(warnings, [])
            from_common = objects.root_commit(common, common)
            from_worktree = objects.root_commit(worktree_git, common)
        self.assertIsNone(from_common)
        self.assertEqual(from_worktree, names[0])

    def test_shallow_clone_gives_warning(self) -> None:
        """A `shallow` file: no root commit, and the warning `shallow_clone` with the folder."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_NO_REMOTE)
            contents, names = build_chain(["first", "second"])
            write_chain(git_folder, contents)
            point_head(git_folder, names[1])
            (git_folder / "shallow").write_text(f"{names[1]}\n", encoding="utf-8")
            direct = objects.root_commit(git_folder, git_folder)
            identity, warnings = resolve(folder, ["origin"])
        self.assertIsNone(direct)
        self.assertIsNone(identity)
        self.assertEqual(warnings, shallow_warning(folder))

    def test_identity_from_root_commit(self) -> None:
        """No remote, or only local remotes: the identity is `root-commit:` with the hash."""
        with support.TemporaryFolder() as plain, support.TemporaryFolder() as local:
            contents, names = build_chain(["first", "second"])
            git_folder = write_repository(plain, CONFIG_NO_REMOTE)
            write_chain(git_folder, contents)
            point_head(git_folder, names[1])
            without_remote = resolve(plain, ["origin"])
            git_folder = write_repository(local, CONFIG_ONLY_LOCAL_ORIGIN)
            write_chain(git_folder, contents)
            point_head(git_folder, names[1])
            with_local_remote = resolve(local, ["origin"])
        expected = repository.RepositoryIdentity("root-commit:" + names[0], "observed")
        self.assertEqual(without_remote, (expected, []))
        self.assertEqual(with_local_remote, (expected, []))

    def test_root_commit_is_kept(self) -> None:
        """A second resolve reads no object, because the store holds the root commit; a
        resolve with a fresh store meets the missing objects with the warning."""
        with support.TemporaryFolder() as folder:
            git_folder = write_repository(folder, CONFIG_NO_REMOTE)
            contents, names = build_chain(["first", "second"])
            write_chain(git_folder, contents)
            point_head(git_folder, names[1])
            kept = repository.RootCommits()
            first = repository.resolve_folder(
                str(folder), SYSTEM, search_home(folder), ["origin"], kept)
            shutil.rmtree(git_folder / "objects")
            second = repository.resolve_folder(
                str(folder), SYSTEM, search_home(folder), ["origin"], kept)
            fresh = repository.resolve_folder(
                str(folder), SYSTEM, search_home(folder), ["origin"], repository.RootCommits())
        expected = (repository.RepositoryIdentity("root-commit:" + names[0], "observed"), [])
        self.assertEqual(first, expected)
        self.assertEqual(second, expected)
        self.assertEqual(fresh, (None, shallow_warning(folder)))


if __name__ == "__main__":
    unittest.main()
