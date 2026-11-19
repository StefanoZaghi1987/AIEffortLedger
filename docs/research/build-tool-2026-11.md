# Build tools for the Python package — research of November 2026

Point-in-time research that compares four PEP 517 build backends for the core package: `setuptools`, `hatchling`,
`uv_build`, and `flit_core`. Facts are the state on 2026-11-19 and change with tool releases; the `pyproject.toml` of
the package is the current truth, this file is not updated.

The constraints are those of the core: a pure-Python package in a `src/` layout, one console command in
`[project.scripts]`, the runtime dependency `tzdata` only, Python 3.11 or later on Windows, Linux, and macOS, installs
from a git tag with `uv tool install` or `pipx install`, editable installs with `uv pip install -e .`, tests with
`python -I`, a static PEP 440 version, possible data files inside the package, and a small build-time supply chain.

Package metadata comes from the PyPI JSON API (`https://pypi.org/pypi/<name>/json`). Wheel contents were checked by
listing the files of the published wheels, without running them.

## setuptools

- Latest version: 84.2.1, uploaded 2026-10-20. First upload to PyPI: 0.6b1 in 2006
  ([PyPI JSON](https://pypi.org/pypi/setuptools/json)). Maintained by the PyPA
  ([source](https://github.com/pypa/setuptools)). License `MIT`. Requires Python 3.10 or later.
- Build-time downloads: one package. `requires_dist` holds only extras (`test`, `doc`, `core`, `check`, `cover`,
  `enabler`, `type`), so an installer fetches no other package
  ([PyPI JSON](https://pypi.org/pypi/setuptools/json)). The hooks `get_requires_for_build_wheel` and
  `get_requires_for_build_editable` add nothing for a project without `setup_requires`
  ([build_meta.py](https://github.com/pypa/setuptools/blob/v84.2.1/setuptools/build_meta.py#L330)).
- Pure Python, but large: the wheel is 876 KB and vendors 11 libraries under `setuptools/_vendor` (`autocommand`,
  `backports.tarfile`, `importlib_metadata`, `jaraco.context`, `jaraco.functools`, `jaraco.text`, `more_itertools`,
  `packaging`, `platformdirs`, `tomli`, `wheel`, `zipp`), observed in the published wheel.
- Versioning: a new major version is frequent. There were 15 major versions from 70.0.0 (2024-05-21) to 84.0.0
  (2026-08-08) ([PyPI JSON](https://pypi.org/pypi/setuptools/json)). Recent removals: `easy_install` and the old
  `setup.py develop` path (v80), `--dry-run` (v81), `pkg_resources` (v82), Python 3.9 (v83)
  ([history](https://setuptools.pypa.io/en/stable/history.html)).
- PEP 639: `license = "MIT"` and `project.license-files` since v77. The same release deprecated `project.license` as a
  TOML table, `tool.setuptools.license-files`, and license classifiers
  ([history](https://setuptools.pypa.io/en/stable/history.html)). The warning for the TOML table has the due date
  2027-02-18 ([source](https://github.com/pypa/setuptools/blob/v84.2.1/setuptools/config/_apply_pyprojecttoml.py#L212)).
  The PyPA guide gives `setuptools >= 77.0.3` as the minimum for PEP 639
  ([packaging guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/#choosing-a-build-backend)).
- `src/` layout: found by automatic discovery when no package option is set
  ([package discovery](https://setuptools.pypa.io/en/latest/userguide/package_discovery.html#src-layout)).
- `[project.scripts]` and PEP 621 metadata in `pyproject.toml` only: supported
  ([pyproject configuration](https://setuptools.pypa.io/en/latest/userguide/pyproject_config.html)). Static and dynamic
  version are both supported.
- Editable install (PEP 660): setuptools "offers no guarantee of which technique will be used"
  ([development mode](https://setuptools.pypa.io/en/latest/userguide/development_mode.html)). In v84.2.1 a `src/`
  layout with automatic discovery gets a static `.pth` file that adds `src` to `sys.path`; other layouts get a `.pth`
  file that imports a `MetaPathFinder`; the `strict` mode uses a link tree
  ([editable_wheel.py](https://github.com/pypa/setuptools/blob/v84.2.1/setuptools/command/editable_wheel.py#L366)).
- Data files: files inside the package are not included by default. They must be listed in `package-data`, in
  `MANIFEST.in`, or found by a VCS plugin such as `setuptools-scm`
  ([data files](https://setuptools.pypa.io/en/latest/userguide/datafiles.html)).
- sdist contents: a fixed default list (package modules, `tests/test*.py`, readme, license files, `pyproject.toml`,
  `setup.py`, `setup.cfg`, `MANIFEST.in`), controlled with `MANIFEST.in`
  ([controlling files](https://setuptools.pypa.io/en/latest/userguide/miscellaneous.html)).
- Reproducible builds: wheel timestamps come from `SOURCE_DATE_EPOCH` through the vendored `wheel` module
  ([wheelfile.py](https://github.com/pypa/setuptools/blob/v84.2.1/setuptools/_vendor/wheel/wheelfile.py#L53)).
  I found no `SOURCE_DATE_EPOCH` handling for the sdist in the setuptools code of v84.2.1.
- Pitfalls: setuptools writes `build`, `dist`, and `*.egg-info` folders into the source tree, and a stale cache
  can change the result
  ([cache](https://setuptools.pypa.io/en/latest/userguide/miscellaneous.html#caching-and-troubleshooting)).
  A data file that is not declared is silently left out of the wheel.

## hatchling

- Latest version: 1.33.0, uploaded 2026-10-28; first upload to PyPI in January 2022; 1.0.0 on 2022-05-18
  ([PyPI JSON](https://pypi.org/pypi/hatchling/json)). Maintained in the PyPA `hatch` repository
  ([source](https://github.com/pypa/hatch/tree/master/backend)). License `MIT`. Requires Python 3.10 or later.
- Build-time downloads: six packages for a wheel. `requires_dist` is `packaging>=24.2`, `pathspec>=0.10.1`,
  `pluggy>=1.0.0`, `tomlkit>=0.11.1`, `trove-classifiers`, and `tomli` only below Python 3.11
  ([PyPI JSON](https://pypi.org/pypi/hatchling/json)). None of these five has a runtime dependency
  ([packaging](https://pypi.org/pypi/packaging/json), [pathspec](https://pypi.org/pypi/pathspec/json),
  [pluggy](https://pypi.org/pypi/pluggy/json), [tomlkit](https://pypi.org/pypi/tomlkit/json),
  [trove-classifiers](https://pypi.org/pypi/trove-classifiers/json)). `tomlkit` became a dependency in 1.32.0
  ([history](https://hatch.pypa.io/latest/history/hatchling/)). An editable build adds a seventh package,
  `editables~=0.3`, which `get_requires_for_build_editable` always returns
  ([build.py](https://github.com/pypa/hatch/blob/hatchling-v1.33.0/backend/src/hatchling/build.py#L61),
  [constants.py](https://github.com/pypa/hatch/blob/hatchling-v1.33.0/backend/src/hatchling/builders/constants.py#L45)).
  All are pure Python; the six wheels for a normal build are about 360 KB together.
- Versioning: Semantic Versioning, stated at the top of the
  [history](https://hatch.pypa.io/latest/history/hatchling/); still at 1.x four years after 1.0.0. The PyPA guide gives
  `hatchling >= 1.26` as the minimum for PEP 639 and uses Hatchling as its default backend
  ([packaging guide](https://packaging.python.org/en/latest/tutorials/packaging-projects/#choosing-a-build-backend)).
- `src/` layout: found by a heuristic that checks `<NAME>/__init__.py`, then `src/<NAME>/__init__.py`
  ([wheel builder](https://hatch.pypa.io/latest/plugins/builder/wheel/#default-file-selection)).
- `[project.scripts]`, PEP 621, PEP 639 (`license = "MIT"`, `license-files`), static or dynamic version: supported
  ([metadata](https://hatch.pypa.io/latest/config/metadata/)). Since 1.32.3 the version string is written to the core
  metadata exactly as typed in `pyproject.toml` ([history](https://hatch.pypa.io/latest/history/hatchling/)), so the
  version should be typed in normalized PEP 440 form (for example `0.2.0.dev1`).
- Editable install: by default a `.pth` file with the source directory (`src`). With `dev-mode-exact = true` it uses
  an import hook from the `editables` library, which adds an `import` line to the `.pth` file and a runtime dependency
  on `editables` ([build configuration](https://hatch.pypa.io/latest/config/build/#dev-mode),
  [wheel.py](https://github.com/pypa/hatch/blob/hatchling-v1.33.0/backend/src/hatchling/builders/wheel.py#L549),
  [editables](https://github.com/pfmoore/editables/blob/0.6/src/editables/__init__.py)).
- Data files: every file in the package folder is included unless the VCS ignores it.
- sdist contents: by default every file that the VCS does not ignore; `include`, `exclude`, `only-include`, and
  `artifacts` change the selection
  ([sdist builder](https://hatch.pypa.io/latest/plugins/builder/sdist/#default-file-selection),
  [build configuration](https://hatch.pypa.io/latest/config/build/#vcs)).
- Reproducible builds: on by default. Timestamps come from `SOURCE_DATE_EPOCH`, or from a fixed default value
  ([build configuration](https://hatch.pypa.io/latest/config/build/#reproducible-builds),
  [utils.py](https://github.com/pypa/hatch/blob/hatchling-v1.33.0/backend/src/hatchling/builders/utils.py#L94)).
- Pitfalls: hatchling reads `.gitignore`, not the git index. A file that is not committed but not ignored goes into a
  local sdist or wheel; a file that is ignored (for example a generated data table) is left out unless it is listed
  in `artifacts` ([build configuration](https://hatch.pypa.io/latest/config/build/#artifacts)).

## uv_build

- Latest version: 0.13.9, uploaded 2026-11-17; first upload to PyPI in February 2025; 175 releases since then
  ([PyPI JSON](https://pypi.org/pypi/uv-build/json)). Maintained by Astral in the uv repository
  ([source](https://github.com/astral-sh/uv)). Astral announced on 2026-03-19 that it joins OpenAI and that OpenAI "will
  continue supporting our open source tools" ([Astral blog](https://astral.sh/blog/openai)). License
  `MIT OR Apache-2.0`.
- Build-time downloads: one package with no dependencies (`requires_dist` is empty)
  ([PyPI JSON](https://pypi.org/pypi/uv-build/json)). It is not pure Python: each wheel is platform-specific and holds a
  compiled Rust executable (`uv-build.exe` is 2.5 MB in the 1.2 MB `win_amd64` wheel) and a CycloneDX SBOM, observed in
  the published wheel. Wheels exist for Windows, macOS, and many Linux targets.
- With uv as the installer, nothing is downloaded: the `uv` executable contains a copy of the backend and uses it when
  its version satisfies the `uv_build` requirement
  ([build backend](https://docs.astral.sh/uv/concepts/build-backend/#bundled-build-backend)).
  This "fast path" applies to source builds during installs, also editable ones
  ([source/mod.rs](https://github.com/astral-sh/uv/blob/0.13.9/crates/uv-distribution/src/source/mod.rs#L2952),
  [uv-dispatch](https://github.com/astral-sh/uv/blob/0.13.9/crates/uv-dispatch/src/lib.rs#L665)); `uv build
  --force-pep517` disables it ([CLI reference](https://docs.astral.sh/uv/reference/cli/#uv-build--force-pep517)).
  pip and other frontends always download `uv_build`.
- Versioning: not at 1.0. uv bumps the minor version for breaking changes
  ([versioning policy](https://docs.astral.sh/uv/reference/policies/versioning/)), and the documentation asks for an
  upper bound, `requires = ["uv_build>=0.13.9,<0.14"]`
  ([build backend](https://docs.astral.sh/uv/concepts/build-backend/#using-the-uv-build-backend)). Building an sdist
  without an upper bound prints a warning
  ([metadata.rs](https://github.com/astral-sh/uv/blob/0.13.9/crates/uv-build-backend/src/metadata.rs#L1293)).
  New minor versions came in 2025-07 (0.8), 2025-10 (0.9), 2026-02 (0.10), 2026-03 (0.11), 2026-07 (0.12), and 2026-10
  (0.13). The release notes of 0.9, 0.10, 0.12, and 0.13 state no breaking change to the `uv_build` configuration but
  ask to raise the bound; 0.13 changed the bytes and hashes of sdists made by `uv_build`
  ([changelog](https://github.com/astral-sh/uv/blob/0.13.9/CHANGELOG.md#0130)). The backend was declared stable in
  0.7.19 (2025-07-02) ([changelog 0.7.x](https://github.com/astral-sh/uv/blob/0.13.9/changelogs/0.7.x.md#0719)) and is
  the default of `uv init` ([project configuration](https://docs.astral.sh/uv/concepts/projects/config/#build-systems)).
- `src/` layout: the default. The module is `src/<name>/__init__.py`, with the project name lowercased and `-` and `.`
  replaced by `_` (so `ai-effort-ledger` gives `ai_effort_ledger`); `module-name` and `module-root` change it
  ([build backend](https://docs.astral.sh/uv/concepts/build-backend/#modules)).
- Only pure Python code; for build scripts or a more flexible layout the uv documentation points to hatchling
  ([build backend](https://docs.astral.sh/uv/concepts/build-backend/#choosing-a-build-backend)).
- `[project.scripts]`, PEP 621, PEP 639: supported; the backend checks that `license` is a valid SPDX expression
  ([metadata.rs](https://github.com/astral-sh/uv/blob/0.13.9/crates/uv-build-backend/src/metadata.rs)). Dynamic
  metadata, including a dynamic version, is rejected ("Dynamic metadata is not supported",
  [metadata.rs](https://github.com/astral-sh/uv/blob/0.13.9/crates/uv-build-backend/src/metadata.rs#L73)).
- Editable install: a static `.pth` file that holds the module root (`src`)
  ([wheel.rs](https://github.com/astral-sh/uv/blob/0.13.9/crates/uv-build-backend/src/wheel.rs#L285)).
- Data files: everything under the module folder goes into the wheel, except `__pycache__`, `*.pyc`, `*.pyo`, and
  `wheel-exclude`; other data goes in `data` folders
  ([build backend](https://docs.astral.sh/uv/concepts/build-backend/#file-inclusion-and-exclusion)).
- sdist contents: minimal by default (`pyproject.toml` rewritten plus the original, the module, readme, license files,
  `data` folders), extended with `source-include` and reduced with `source-exclude`
  ([build backend](https://docs.astral.sh/uv/concepts/build-backend/#file-inclusion-and-exclusion)).
- Reproducible builds: the backend tests check that sdist and wheel are "byte-by-byte identical independent of the
  build path or platform"
  ([lib.rs](https://github.com/astral-sh/uv/blob/0.13.9/crates/uv-build-backend/src/lib.rs#L735)).
  I found no `SOURCE_DATE_EPOCH` handling in the backend source; it does not need one.
- Pitfalls: the upper bound must be raised at each uv minor release, about every three months. The module name must
  match the normalized project name or be configured. Only one top-level module.

## flit_core

- Latest version: 4.2.0, uploaded 2026-10-27; first upload to PyPI in 2019 (2.0rc1); 3.0.0 on 2020-09-06; 4.0.1 on
  2026-08-04 ([PyPI JSON](https://pypi.org/pypi/flit-core/json)). Maintained by the PyPA
  ([source](https://github.com/pypa/flit)). License `BSD-3-Clause`.
- Build-time downloads: one package with no dependencies (`requires_dist` is empty)
  ([PyPI JSON](https://pypi.org/pypi/flit-core/json)). Pure Python, 48 KB wheel, 22 files; it vendors only `tomli`, used
  when the standard `tomllib` is missing (Python below 3.11), observed in the published wheel.
- Versioning: major versions are rare (3.0 in 2020, 4.0 in 2026). The documentation asks all packages to specify
  `<5` ([build system section](https://flit.pypa.io/en/stable/pyproject_toml.html#build-system-section)). 4.0 removed
  `[tool.flit.metadata]`, the `--setup-py` option, Python 3.6 and 3.7, and VCS-based sdists in `flit build`; projects
  that already use `[project]` only change the bound ([history](https://flit.pypa.io/en/stable/history.html)).
- `src/` layout: automatic. The import name is the project name with `-` replaced by `_`, found in the project folder
  or in `src/` ([module section](https://flit.pypa.io/en/stable/pyproject_toml.html#module-section)).
- `[project.scripts]`, PEP 621: supported. PEP 639 (`license = "MIT"`, `license-files`) since 3.11
  ([build system section](https://flit.pypa.io/en/stable/pyproject_toml.html#build-system-section)).
- Version and description: static in `[project]`, or dynamic from `__version__` and the module docstring. Only when a
  field is listed in `dynamic` does flit need the docstring or `__version__`; if it cannot parse them, it imports the
  module and asks for the runtime dependencies at build time
  ([buildapi.py](https://github.com/pypa/flit/blob/4.2.0/flit_core/flit_core/buildapi.py#L20),
  [common.py](https://github.com/pypa/flit/blob/4.2.0/flit_core/flit_core/common.py#L230)). A static version avoids
  all of this.
- Editable install (PEP 660 since 3.4, [history](https://flit.pypa.io/en/stable/history.html)): a static `.pth` file
  with the source folder ([wheel.py](https://github.com/pypa/flit/blob/4.2.0/flit_core/flit_core/wheel.py#L177)).
- Data files: the wheel contains every file of the package folder except `__pycache__` and `*.pyc`
  ([sdist section](https://flit.pypa.io/en/stable/pyproject_toml.html#sdist-section)).
- sdist contents: minimal by default (package, `pyproject.toml`, readme, license files, external data folder);
  `[tool.flit.sdist]` `include` and `exclude` extend it
  ([sdist section](https://flit.pypa.io/en/stable/pyproject_toml.html#sdist-section)).
- Reproducible builds: wheels are reproducible, but zip timestamps come from the file modification times unless
  `SOURCE_DATE_EPOCH` is set ([reproducible builds](https://flit.pypa.io/en/stable/reproducible.html)). The sdist uses
  `SOURCE_DATE_EPOCH` and a fixed gzip timestamp
  ([sdist.py](https://github.com/pypa/flit/blob/4.2.0/flit_core/flit_core/sdist.py#L226)).
- Pitfalls: any stray file inside the package folder is shipped. No build hooks and no compiled code.

## Installs from a git URL

- pip needs the `git` executable and builds the checkout "locally in a temp dir"
  ([VCS support](https://pip.pypa.io/en/stable/topics/vcs-support/)). It creates an isolated build environment and
  installs `build-system.requires` plus the packages that `get_requires_for_build_*` returns
  ([build system interface](https://pip.pypa.io/en/stable/reference/build-system/)).
- uv uses PEP 517 build isolation by default
  ([pip compatibility](https://docs.astral.sh/uv/pip/compatibility/#pep-517-build-isolation)),
  except for `uv_build` in a compatible version, which it runs from its own executable (see above).
- pipx makes one virtual environment per application and uses uv when uv is available, pip otherwise
  ([how pipx works](https://pipx.pypa.io/stable/explanation/how-pipx-works.html)).
- What a clean machine downloads to build the package, with these facts:
  - setuptools: `setuptools` (1 package, 876 KB).
  - hatchling: `hatchling`, `packaging`, `pathspec`, `pluggy`, `tomlkit`, `trove-classifiers` (6 packages, about
    360 KB); `editables` in addition for an editable install.
  - uv_build: nothing with uv in a compatible version; otherwise `uv_build` (1 platform wheel, about 1.2 MB).
  - flit_core: `flit_core` (1 package, 48 KB).

## Editable installs under `python -I`

- `-I` implies `-E`, `-P`, and `-s`: it ignores `PYTHON*` variables, does not prepend the script folder, and skips the
  user site-packages ([command line](https://docs.python.org/3/using/cmdline.html#cmdoption-I)). It does not imply
  `-S`, so the `site` module still runs and processes `.pth` files in the site-packages of the virtual environment
  ([site](https://docs.python.org/3/library/site.html)).
- All four backends make a `.pth` file in site-packages for this layout, so an editable install works under
  `python -I`.
- Python 3.15 deprecates `import` lines in `.pth` files; Python 3.18 and 3.19 will ignore them silently, in favor of
  `.start` files from PEP 829 ([site](https://docs.python.org/3/library/site.html)). Path-only `.pth` files are not
  affected. This touches the setuptools `MetaPathFinder` mode (other layouts) and the hatchling `dev-mode-exact` mode,
  not the default modes that apply here.

## No `[build-system]` table

- PEP 518: tools "should not require the existence of the `[build-system]` table"; when it is missing, they use the
  default `requires = ["setuptools"]` ([PEP 518](https://peps.python.org/pep-0518/)). PEP 517: when `build-backend` is
  missing, tools revert to the legacy behaviour, directly or through `setuptools.build_meta:__legacy__`
  ([PEP 517](https://peps.python.org/pep-0517/)).
- pip 26.3: without a `build-system` table it assumes `requires = ["setuptools>=40.8.0"]` and
  `build-backend = "setuptools.build_meta:__legacy__"`
  ([build system interface](https://pip.pypa.io/en/stable/reference/build-system/#fallback-behaviour),
  [pyproject.py](https://github.com/pypa/pip/blob/26.3/src/pip/_internal/pyproject.py#L69)). Without `setup.py`, the
  legacy backend runs a default `from setuptools import setup; setup()`
  ([build_meta.py](https://github.com/pypa/setuptools/blob/v84.2.1/setuptools/build_meta.py#L132)), so setuptools reads
  `[project]` from `pyproject.toml`.
- uv: `uv pip install` and dependencies also fall back to `setuptools.build_meta:__legacy__`. In a uv project without a
  build system, uv does not build or install the project itself, only its dependencies
  ([project configuration](https://docs.astral.sh/uv/concepts/projects/config/#build-systems)).
- Result: the build then uses whatever setuptools version is newest, with no upper bound, and `uv sync` does not
  install the console command. An explicit table is safer.

## Comparison

| Case | setuptools | hatchling | uv_build | flit_core |
| --- | --- | --- | --- | --- |
| Packages downloaded to build a wheel | 1 (876 KB, 11 vendored libraries) | 6 (about 360 KB) | 0 with uv; 1 (1.2 MB) otherwise | 1 (48 KB) |
| Packages downloaded for an editable install | 1 | 7 (+ `editables`) | 0 with uv; 1 otherwise | 1 |
| Pure Python backend | ✓ | ✓ | ✗ (Rust executable) | ✓ |
| Maintainer | PyPA | PyPA | Astral (joining OpenAI) | PyPA |
| Version 1.0 or later | ✓ (84.x, major about every 2 months) | ✓ (1.x since 2022) | ✗ (0.13, minor = breaking) | ✓ (4.x; majors 2020, 2026) |
| Upper bound in `requires` | not asked | not asked | required, raise each minor | `<5` asked |
| `src/` layout found without configuration | ✓ | ✓ | ✓ (default) | ✓ |
| `[project.scripts]` | ✓ | ✓ | ✓ | ✓ |
| PEP 621 only, no `setup.py` | ✓ | ✓ | ✓ | ✓ |
| PEP 639 `license = "MIT"`, `license-files` | ✓ (≥ 77) | ✓ (≥ 1.26) | ✓ | ✓ (≥ 3.11) |
| PEP 660 mechanism here | static `.pth` (no guarantee) | static `.pth` | static `.pth` | static `.pth` |
| Editable install under `python -I` in a venv | ✓ | ✓ | ✓ | ✓ |
| Data file inside the package, no configuration | ✗ (`package-data` or `MANIFEST.in`) | ✓ (unless git-ignored) | ✓ | ✓ |
| Reproducible without `SOURCE_DATE_EPOCH` | ✗ | ✓ | ✓ | ✗ (wheel) |
| Default sdist | fixed list + `MANIFEST.in` | all files not git-ignored | minimal | minimal |
| Static version with `.devN` | ✓ | ✓ (type it normalized) | ✓ | ✓ |
| Dynamic version | ✓ | ✓ | ✗ | ✓ (`__version__`) |
| Compiled extensions, build hooks | ✓ | ✓ (hooks, plugins) | ✗ | ✗ |

## Recommendation

- **Best: `flit_core`.** One pure-Python package of 48 KB with no dependencies, maintained by the PyPA, with a major
  version every few years; it covers every constraint here without configuration (`requires = ["flit_core >=4.2,<5"]`).
- **Cleanest: `uv_build`.** Zero configuration for this exact layout, static metadata only, byte-reproducible output,
  and no download at all when uv builds; the cost is a compiled single-vendor backend at 0.x whose upper bound must be
  raised about every three months.
- **Most general: `setuptools`.** It is the backend that PEP 518, pip, and uv fall back to, and it supports every
  layout, dynamic metadata, and compiled extensions; the cost is the largest backend, a new major version about every
  two months, and explicit declaration of data files.
