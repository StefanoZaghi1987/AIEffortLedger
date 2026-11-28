"""The static check of the package and its tests: Avoid words, type hints, the line limit, and
the table of Modules.

It reads the words that GLOSSARY.md, beside tests/, marks _Avoid_ (gate G1) and checks every file
of `src/` and of `tests/`: an identifier that the code defines never holds an Avoid word, a public
function annotates its parameters, a line holds at most 99 columns, and the file parses. It also
reads the table of Modules and the line of the build order from docs/spec/architecture.md, collects
every import statement of the package from every file under `src/ai_effort_ledger/` — a module
that a string loads at run time is not a statement — and names an import that the row of its module
does not list, a dependency of a row that no file of the module imports, a dependency or an import
that stands below its module in the line of the build order, and a cycle of the import graph.
Run it with `python -I tests/style.py`; it exits 0 without findings and 1 with findings.
"""

import argparse
import ast
import re
import sys
import tokenize
from pathlib import Path

LINE_LIMIT = 99
PACKAGE = "ai_effort_ledger"

WORD = re.compile(r"[A-Za-z0-9]+")
PARTS = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|[0-9]+")
TERM = re.compile(r"^\*\*(.+?)\*\*:")


def split_identifier(name: str) -> list[str]:
    """Split a name into its lower-case words, at underscores and at case transitions."""
    parts = []
    for chunk in name.split("_"):
        parts.extend(part.lower() for part in PARTS.findall(chunk))
    return parts


def named_words(glossary: str) -> tuple[frozenset[str], frozenset[tuple[str, ...]]]:
    """Read the glossary: the Avoid single words and the Avoid sequences of more than one word.

    A word that the title of the glossary or a glossary term holds is not named, because an Avoid
    word is wrong only for its own term. The text in parentheses of an entry is not part of it.
    """
    held = set()
    for line in glossary.splitlines():
        if line.startswith("# "):
            held.update(word.lower() for word in WORD.findall(line))
        found = TERM.match(line)
        if found:
            held.update(word.lower() for word in WORD.findall(found.group(1)))
    words = set()
    sequences = set()
    for line in glossary.splitlines():
        if not line.startswith("_Avoid_"):
            continue
        plain = re.sub(r"\([^)]*\)", " ", line.split(":", 1)[1])
        for entry in plain.split(","):
            entry_words = tuple(word.lower() for word in WORD.findall(entry))
            if len(entry_words) == 1:
                words.add(entry_words[0])
            elif entry_words:
                sequences.add(entry_words)
    return frozenset(words - held), frozenset(sequences)


def _parameters(definition: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    """Every parameter of the definition: positional, keyword-only, then vararg and kwarg."""
    arguments = definition.args
    optional = [arguments.vararg, arguments.kwarg]
    return arguments.posonlyargs + arguments.args + arguments.kwonlyargs + [
        entry for entry in optional if entry]


def _annotated(definition: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.arg]:
    """The parameters a definition must annotate: not `self` and `cls`, a vararg, or a kwarg."""
    needed = definition.args.posonlyargs + definition.args.args + definition.args.kwonlyargs
    return [entry for entry in needed if entry.arg not in ("self", "cls")]


def _overload_stub(definition: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """A def that `typing.overload` decorates and whose body holds only `...` is a stub."""
    decorated = any(
        (isinstance(entry, ast.Name) and entry.id == "overload")
        or (isinstance(entry, ast.Attribute) and entry.attr == "overload")
        for entry in definition.decorator_list)
    if not decorated or len(definition.body) != 1:
        return False
    only = definition.body[0]
    return (isinstance(only, ast.Expr) and isinstance(only.value, ast.Constant)
            and only.value.value is Ellipsis)


def _defined(tree: ast.AST) -> tuple[list[tuple[int, str]], list[tuple[int, str, str]]]:
    """Collect the identifiers the code defines and the parameters that lack an annotation.

    Returns the (line, identifier) pairs and the (line, function, parameter) triples. The
    identifiers are the names of functions, classes, parameters, assigned names, attributes that
    `self` receives, and import aliases; not the names the code uses from other code. A nested
    function, an overload stub, and the parameters `self`, `cls`, a vararg, and a kwarg need no
    annotation.
    """
    identifiers = []
    missing = []

    def walk(node: ast.AST, inside_a_def: bool) -> None:
        for child in ast.iter_child_nodes(node):
            deeper = inside_a_def
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                identifiers.append((child.lineno, child.name))
                for parameter in _parameters(child):
                    identifiers.append((child.lineno, parameter.arg))
                public = not child.name.startswith("_")
                if not inside_a_def and public and not _overload_stub(child):
                    for parameter in _annotated(child):
                        if parameter.annotation is None:
                            missing.append((child.lineno, child.name, parameter.arg))
                deeper = True
            elif isinstance(child, ast.ClassDef):
                identifiers.append((child.lineno, child.name))
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Store):
                identifiers.append((child.lineno, child.id))
            elif isinstance(child, ast.Attribute) and isinstance(child.ctx, ast.Store):
                if isinstance(child.value, ast.Name) and child.value.id == "self":
                    identifiers.append((child.lineno, child.attr))
            elif isinstance(child, (ast.Import, ast.ImportFrom)):
                for alias in child.names:
                    if alias.asname:
                        identifiers.append((child.lineno, alias.asname))
            elif isinstance(child, ast.ExceptHandler) and child.name:
                identifiers.append((child.lineno, child.name))
            walk(child, deeper)

    walk(tree, False)
    return identifiers, missing


def _avoid_hits(
    identifier: str,
    words: frozenset[str],
    sequences: frozenset[tuple[str, ...]],
) -> list[tuple[bool, str]]:
    """The Avoid texts the identifier holds; a sequence is matched first and consumes its words."""
    hits = []
    parts = split_identifier(identifier)
    index = 0
    while index < len(parts):
        span = 0
        for size in range(len(parts) - index, 1, -1):
            if tuple(parts[index:index + size]) in sequences:
                span = size
                break
        if span:
            hits.append((True, " ".join(parts[index:index + span])))
            index += span
        elif parts[index] in words:
            hits.append((False, parts[index]))
            index += 1
        else:
            index += 1
    return hits


def check_file(
    path: Path,
    words: frozenset[str],
    sequences: frozenset[tuple[str, ...]],
) -> list[str]:
    """Check one file and return its findings, each as `path:line: text`, in the order of lines."""
    marked = []
    with tokenize.open(path) as source:
        text = source.read()
    for number, line in enumerate(text.splitlines(), start=1):
        if len(line) > LINE_LIMIT:
            marked.append((number, f"the line holds {len(line)} columns, over {LINE_LIMIT}"))
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as fault:
        marked.append((fault.lineno or 1, f"syntax fault: {fault.msg}"))
    else:
        identifiers, missing = _defined(tree)
        for number, name, parameter in missing:
            marked.append((number, f"'{name}' has no annotation for the parameter '{parameter}'"))
        for number, identifier in sorted(set(identifiers)):
            for is_sequence, held in _avoid_hits(identifier, words, sequences):
                kind = "sequence" if is_sequence else "word"
                marked.append(
                    (number, f"'{identifier}' holds '{held}', a {kind} the glossary marks Avoid"))
    return [f"{path}:{number}: {finding}" for number, finding in sorted(marked)]


def _section_lines(text: str) -> list[tuple[int, str]]:
    """The numbered lines of the section of Modules: from the heading `## Modules` to the next
    heading of the same or a higher level; a deeper heading does not end the section."""
    held: list[tuple[int, str]] = []
    inside = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "## Modules":
            inside = True
        elif inside and (line.startswith("# ") or line.startswith("## ")):
            break
        if inside:
            held.append((number, line))
    return held


def module_rows(text: str) -> tuple[dict[str, int], dict[str, frozenset[str] | None]]:
    """Read the table of Modules of the architecture document: the rows between the heading
    `## Modules` and the next heading of the same or a higher level; a three-cell row of another
    part of the document is not a row of the table.

    Returns the line of each row and the set of modules that its cell names: the cell `all` is
    read as every module (None), the cell `—` as none.
    """
    lines_at: dict[str, int] = {}
    listed: dict[str, frozenset[str] | None] = {}
    for number, line in _section_lines(text):
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 3:
            continue
        name = cells[0].strip("`")
        held = None if cells[2].strip("`") == "all" else frozenset(
            piece.strip().strip("`") for piece in cells[2].split(",")) - {"—"}
        lines_at[name] = number
        listed[name] = held
    return lines_at, listed


def build_order(text: str) -> list[list[str]]:
    """Read the line of the build order from the section of Modules: the groups of modules, in
    the order of the line; a line of build order outside the section is not the line."""
    groups: list[list[str]] = []
    lines = [line for _, line in _section_lines(text)]
    for index, line in enumerate(lines):
        if not line.startswith("Build order:"):
            continue
        sentence = line[len("Build order:"):]
        while "." not in sentence and index + 1 < len(lines):
            index += 1
            sentence += " " + lines[index].strip()
        groups = [
            re.findall(r"`([^`]+)`", group)
            for group in sentence.split(".", 1)[0].split("→")]
    return groups


def _modules_of(
    node: ast.AST,
    inside: tuple[str, ...],
    files: set[str],
    folders: set[str],
) -> list[str]:
    """The rows that one import statement of the package loads.

    A statement maps to the first module after the package of the module it loads; a statement
    from the package root maps a name that the package holds as a file `<name>.py` or a folder
    `<name>/` with an `__init__.py`, matched case-exactly, to that module, and any other name to
    the package root. A statement of another package loads no row.
    """
    if isinstance(node, ast.ImportFrom):
        if node.level:
            if node.level - 1 > len(inside):
                return []
            origin = inside[: len(inside) - (node.level - 1)]
            walked = origin + tuple(node.module.split(".")) if node.module else origin
        elif node.module == PACKAGE:
            walked = ()
        elif node.module and node.module.startswith(PACKAGE + "."):
            walked = tuple(node.module.split(".")[1:])
        else:
            return []
    elif isinstance(node, ast.Import):
        return [pieces[1] if len(pieces) > 1 else PACKAGE
                for pieces in (alias.name.split(".") for alias in node.names)
                if pieces[0] == PACKAGE]
    else:
        return []
    if walked:
        return [walked[0]]
    return [alias.name if f"{alias.name}.py" in files or alias.name in folders else PACKAGE
            for alias in node.names]


def package_imports(base: Path) -> dict[str, dict[str, list[tuple[Path, int]]]]:
    """Collect the imports between the rows of the table from every file of the package.

    Returns, for each row, the rows its files hold statements of and the place of every
    statement. A statement is collected wherever it sits in the file; a statement inside one
    module is left out. The package root is a row of its own.
    """
    edges: dict[str, dict[str, list[tuple[Path, int]]]] = {}
    if not base.is_dir():
        return edges
    entries = {entry.name for entry in base.iterdir()}
    folders = {name for name in entries if (base / name / "__init__.py").is_file()}
    for path in sorted(base.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        parts = path.relative_to(base).parts
        own = PACKAGE if parts == ("__init__.py",) else (
            parts[0] if len(parts) > 1 else path.stem)
        with tokenize.open(path) as source:
            text = source.read()
        try:
            tree = ast.parse(text, filename=str(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            for reached in _modules_of(node, parts[:-1], entries, folders):
                if reached == own:
                    continue
                edges.setdefault(own, {}).setdefault(reached, []).append((path, node.lineno))
    return edges


def _cycles(edges: dict[str, dict[str, list[tuple[Path, int]]]]) -> list[tuple[str, int, str]]:
    """The cycles of the import graph, decided on the statements alone, each named once."""
    found: list[tuple[str, int, str]] = []
    state: dict[str, int] = {}
    stack: list[str] = []

    def walk(own: str) -> None:
        state[own] = 1
        stack.append(own)
        for reached in sorted(edges.get(own, {})):
            if state.get(reached) == 1:
                ring = stack[stack.index(reached):] + [reached]
                path, number = edges[own][reached][0]
                found.append(
                    (str(path), number,
                     "a cycle of the import graph: " + " -> ".join(f"'{row}'" for row in ring)))
            elif state.get(reached, 0) == 0:
                walk(reached)
        stack.pop()
        state[own] = 2

    for own in sorted(edges):
        if state.get(own, 0) == 0:
            walk(own)
    return found


def module_findings(
    base: Path,
    document: Path,
    lines_at: dict[str, int],
    listed: dict[str, frozenset[str] | None],
    order: list[list[str]],
) -> list[str]:
    """Compare the imports of the package with the table and the line of the build order.

    A row that the table does not hold names no module, so every statement of its files is named;
    a row that the line of the build order does not place takes no part in the comparison of
    order.
    """
    edges = package_imports(base)
    places = {name: place for place, group in enumerate(order) for name in group}
    marked: list[tuple[str, int, str]] = []
    for own in sorted(edges):
        named = listed.get(own, frozenset())
        for reached in sorted(edges[own]):
            for path, number in edges[own][reached]:
                if named is not None and reached not in named:
                    marked.append(
                        (str(path), number,
                         f"an import of '{reached}' that the row of '{own}' does not list"))
                if own in places and reached in places and places[reached] > places[own]:
                    marked.append(
                        (str(path), number,
                         f"an import of '{reached}' that stands below '{own}' in the build order"))
    for own in sorted(lines_at):
        if listed[own] is None:
            continue
        for held in sorted(listed[own]):
            if held not in edges.get(own, {}):
                marked.append(
                    (str(document), lines_at[own],
                     f"the row of '{own}' lists '{held}', which no file of the module imports"))
            if own in places and held in places and places[held] > places[own]:
                marked.append(
                    (str(document), lines_at[own],
                     f"the row of '{own}' lists '{held}', which stands below it "
                     f"in the build order"))
    marked.extend(_cycles(edges))
    return [f"{path}:{number}: {finding}" for path, number, finding in sorted(marked)]


def main(argv: list[str] | None = None) -> int:
    """Check the tree: it reads GLOSSARY.md and docs/spec/architecture.md beside tests/, checks
    `src/` and `tests/`, skips `__pycache__`, prints one finding per line, and returns 0 without
    findings, 1 with findings."""
    options = argparse.ArgumentParser(description="The static check of the AI Effort Ledger tree.")
    options.add_argument(
        "root", nargs="?", type=Path, default=None, help="the folder that holds src/ and tests/")
    root = options.parse_args(argv).root or Path(__file__).resolve().parents[1]
    words, sequences = named_words((root / "GLOSSARY.md").read_text(encoding="utf-8"))
    document = root / "docs" / "spec" / "architecture.md"
    architecture = document.read_text(encoding="utf-8")
    lines_at, listed = module_rows(architecture)
    order = build_order(architecture)
    findings = []
    for folder in ("src", "tests"):
        base = root / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            findings.extend(check_file(path, words, sequences))
    findings.extend(
        module_findings(root / "src" / PACKAGE, document, lines_at, listed, order))
    for finding in findings:
        print(finding)
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
