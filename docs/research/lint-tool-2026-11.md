# Static checks for the Python code — research of November 2026

Point-in-time research that compares the static checks (lint tools) available for the core package: `ruff`, `pyflakes`,
`pycodestyle`, `flake8`, `pylint`, `mypy`, the `compileall` command of Python, and a checker script written with the
standard library. Facts are the state on 2026-11-19 and change with tool releases; the workflow file and the scripts of
the repository are the current truth, this file is not updated.

Package metadata comes from the PyPI JSON API (`https://pypi.org/pypi/<name>/json`); capabilities come from the official
documentation of each tool. The feasibility of the standard-library checker was verified with a working prototype of
137 lines (`argparse`, `ast`, `tokenize`, `pathlib`), written and run outside the repository with `python -I` on
CPython 3.13.

The constraints are those of the core: Python 3.11 or later, only the standard library and `tzdata` at run time, a
supply chain kept small (every package, also one for development only, needs the consent of the owner), tests with
`python -I`, a workflow on Windows, Linux, and macOS, and three style rules of CLAUDE.md that no general tool knows:
identifiers never hold a word that the glossary marks _Avoid_, public functions have type hints, and lines wrap at 99
columns.

## ruff

- Latest version 0.17.5, uploaded 2026-11-12; MIT; maintained by Astral
  ([PyPI JSON](https://pypi.org/pypi/ruff/json)). Not pure Python: the Windows wheel is 9.8 MiB and holds one compiled
  Rust program; 18 platform wheels per release. No dependencies: an install downloads one package.
- Cadence: 432 releases since 2022, 49 in the twelve months to 2026-11-19 — one every five to seven days, with
  behaviour changes inside minor bumps ([changelog](https://github.com/astral-sh/ruff/blob/main/CHANGELOG.md)).
- Line length: rule E501 `line-too-long`, limit set with `line-length`
  ([rule page](https://docs.astral.sh/ruff/rules/line-too-long/)); it is **not** on by default — the defaults enable
  `F`, `E`, `B`, `UP`, `RUF` and omit stylistic rules that overlap with the formatter
  ([rules](https://docs.astral.sh/ruff/rules/)) — so it needs an explicit opt-in.
- Syntax faults: yes, as `invalid-syntax` diagnostics ([linter](https://docs.astral.sh/ruff/linter/)).
- Missing type hints: ANN201 `missing-return-type-public-function`, opt-in
  ([rule page](https://docs.astral.sh/ruff/rules/missing-return-type-public-function/)).
- Words in names: no. TID251 `banned-api` bans imports and member access, not identifier definitions
  ([rule page](https://docs.astral.sh/ruff/rules/banned-api/)); no naming rule takes a custom ban list; and there is no
  plugin api: "Ruff does not yet support third-party plugins" ([FAQ](https://docs.astral.sh/ruff/faq/),
  [issue 283](https://github.com/astral-sh/ruff/issues/283)).

## pyflakes

- Latest version 4.1.0, uploaded 2026-10-28; MIT; PyCQA; pure Python, 65 KiB, no dependencies
  ([PyPI JSON](https://pypi.org/pypi/pyflakes/json)).
- Checks unused imports and variables, undefined names; "it will never complain about style" by design
  ([README](https://github.com/PyCQA/pyflakes)). No line length, no naming, no type hints, no configuration.

## pycodestyle

- Latest version 2.15.0, uploaded 2026-09-22; MIT; PyCQA; pure Python, 31 KiB, no dependencies
  ([PyPI JSON](https://pypi.org/pypi/pycodestyle/json)).
- Checks the style conventions of PEP 8: indentation, whitespace, line length (E501, default 79), statements; E901
  reports syntax faults. Naming is out of scope by design
  ([introduction](https://pycodestyle.readthedocs.io/en/latest/intro.html)).

## flake8

- Latest version 7.5.0, uploaded 2026-10-28; MIT; PyCQA; pure Python, 56 KiB
  ([PyPI JSON](https://pypi.org/pypi/flake8/json)). Depends on `mccabe`, `pycodestyle`, and `pyflakes` with pinned
  ranges: an install downloads four packages.
- Plugins install with pip and register themselves
  ([using plugins](https://flake8.pycqa.org/en/latest/user/using-plugins.html)). No established plugin bans arbitrary
  identifiers in names: `flake8-tidy-imports` bans imports, `pep8-naming` enforces conventions without a ban list;
  a ban list needs a purpose-built plugin (web search over plugin lists, 2026-11-19; weaker evidence than the rest of
  this file).

## pylint

- Latest version 4.1.4, uploaded 2026-11-14; **GPL-2.0-or-later**; pylint-dev; pure Python, 0.56 MiB
  ([PyPI JSON](https://pypi.org/pypi/pylint/json)). Dependencies on Python 3.11 and Windows: `astroid`, `colorama`,
  `dill`, `isort`, `mccabe`, `platformdirs`, `tomlkit` — eight packages.
- Words in names: yes, off the shelf. `disallowed-name` (C0104) with `bad-names` and `bad-names-rgxs`
  ([message page](https://pylint.readthedocs.io/en/latest/user_guide/messages/convention/disallowed-name.html)).
  Line too long: C0301. Syntax faults: E0001. Missing type hints: no such message exists in the complete index.
- Configuration is the largest of the set: hundreds of messages, each to tune
  ([development guide](https://pylint.readthedocs.io/en/latest/development_guide/index.html) for custom checkers).

## mypy

- Latest version 2.4.1, uploaded 2026-10-28; MIT; hosted under the Python organization
  ([PyPI JSON](https://pypi.org/pypi/mypy/json)). Compiled wheels of about 10.8 MiB per platform (pure-Python fallback
  2.8 MiB); six packages on Python 3.11.
- Static type checks only ([getting started](https://mypy.readthedocs.io/en/stable/getting_started.html)); the presence
  of type hints is enforced through strictness flags such as `disallow_untyped_defs`
  ([existing code](https://mypy.readthedocs.io/en/stable/existing_code.html)). No style, no naming.

## compileall and a checker of the standard library

- `compileall` compiles the source tree with the built-in `compile()` and catches syntax faults only
  ([documentation](https://docs.python.org/3/library/compileall.html)); it is a subset of what `ast.parse` gives a
  script.
- A checker script with `argparse`, `ast`, `tokenize`, and `pathlib` was verified in a prototype of 137 lines. In one
  pass it reported: a line over the limit, banned words in four identifiers (an import alias, a class, two functions),
  a public function and a public method without return annotations, and a syntax fault with its line number.
- Pitfalls found or documented: read files with `tokenize.open()` for encoding cookies and BOMs
  ([tokenize](https://docs.python.org/3/library/tokenize.html)); match banned words as whole words after splitting
  `snake_case` on `_` and case transitions — a plain substring test fires on `sync` in `async` and on `import` in
  `importlib`; the interpreter that runs the checker must parse the grammar of the code
  ([ast](https://docs.python.org/3/library/ast.html)); annotation checks need exemptions (`@overload`, stub files,
  properties); the column count must state its rule for tabs; file discovery must exclude caches.

## Words in names, across tools

| Tool | Bans words in identifier names |
|---|---|
| pylint | ✓ `bad-names`, `bad-names-rgxs` |
| ruff | ✗ imports and member access only; no plugin api |
| flake8 | ✗ needs a purpose-built plugin |
| mypy | ✗ types only |
| standard-library checker | ✓ a plain word list, read as data |

## Comparison

| Option | Packages downloaded | Pure Python | Line length | Syntax faults | Words in names | Missing type hints |
|---|---|---|---|---|---|---|
| ruff 0.17.5 | 1 (9.8 MiB) | ✗ | ✓ opt-in | ✓ | ✗ | ✓ opt-in (ANN201) |
| pyflakes 4.1.0 | 1 (65 KiB) | ✓ | ✗ | ✓ | ✗ | ✗ |
| pycodestyle 2.15.0 | 1 (31 KiB) | ✓ | ✓ | ✓ | ✗ | ✗ |
| flake8 7.5.0 | 4 | ✓ | ✓ | ✓ | ✗ | ✗ (plugin) |
| pylint 4.1.4 | 8 (Windows) | ✓ | ✓ | ✓ | ✓ | ✗ |
| mypy 2.4.1 | 6 (10.8 MiB) | ✗ | ✗ | parse faults | ✗ | ✓ (strictness) |
| `compileall` | 0 | — | ✗ | ✓ | ✗ | ✗ |
| own checker script | 0 | ✓ | ✓ | ✓ | ✓ | ✓ |

## Recommendation

- **Best: a checker script of the standard library**, `tests/style.py` beside `tests/benchmark.py`. It is the only
  option that checks all three style rules of CLAUDE.md — the _Avoid_ words in identifiers, type hints on public
  functions, the line limit — with no package outside the standard library. The prototype shows a size of about 150
  lines. It reads the _Avoid_ words from GLOSSARY.md, so the ban list never drifts from the glossary; the workflow runs
  it after the tests. The cost is ownership: exemptions, grammar changes of Python, and the word-splitting rule.
- **Cleanest: no checker.** Nothing to own, no tool version to track; review holds every rule. The faults of the
  example stay until a person sees them.
- **Most general: `ruff`.** The largest rule set in one package, the default of the industry; it covers everything
  except the naming rule of this project, which stays with review for as long as ruff has no plugin api (0.17.5).
