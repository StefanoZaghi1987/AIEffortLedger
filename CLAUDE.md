# AI Effort Ledger — working rules

## Language and terms

- Code, identifiers, comments, and documentation are in English; reports and skills support English and Italian.
- Use the terms of [GLOSSARY.md](GLOSSARY.md) exactly, and their Italian equivalents in Italian text. Never use a term
  listed under _Avoid_. A new concept gets a glossary entry before it appears in a spec.

## Documents

- `docs/spec/` describes the system as it is: present tense, no revision notes. When a rule changes, edit the sentence.
- Open points live in the `## To be confirmed` section of the spec they concern. They close by deletion when the owner
  rules: the ruling becomes a sentence in the body or an ADR.
- `docs/adr/`: one decision per file; only for decisions that are hard to reverse, surprising, and a real trade-off.
  Once an ADR is on `master`, only its status line changes, except the removal of private data (see Privacy), which
  never changes the decision. On a feature branch, an ADR that is not yet on `master` is edited directly.
- `docs/research/`: dated, point-in-time notes; ratios only, except the run times and the processor of the benchmark
  ([architecture.md](docs/spec/architecture.md) › Tests), which measures invented data.
- A divergence between documentation and code is flagged, not resolved silently: one dated line in
  `~/.claude/escalations.md` and an item in the `To be confirmed` section of the spec.

## Privacy

- The repository is public. No tracked file holds personal absolute values, real folder names, or internal project
  names; examples use neutral names such as `D:\Work\Product`.
- Never copy prompt, response, tool input, or code text out of transcripts, also not into tests or fixtures.
- Personal measurements go only to `prototype/out/`, which git ignores.
- Never run git inside a folder taken from a transcript; read the `.git` files instead (ADR 0004).

## Core

- `src/ai_effort_ledger/` is the product. Its modules, their dependencies, and their build order follow
  [docs/spec/architecture.md](docs/spec/architecture.md); a module never imports a module that depends on it.
- Tests: `python -I -m unittest discover -s tests`, in a virtual environment with the package installed in editable mode
  (`uv pip install -e .`). Write the failing test first. Fixtures are written by hand with invented text (see Privacy).
- Only the standard library and `tzdata` at run time, and `flit_core` to build
  ([build-tool-2026-11.md](docs/research/build-tool-2026-11.md)). Ask the owner before any other dependency, also one
  for development only.
- Names in code use the glossary terms (`human_time`, `timesheet_confirmation`, `event_key`), never a term under
  _Avoid_. Public functions have type hints. Python code follows PEP 8, with lines wrapped at 99 columns; docstrings
  are in English.
- Tests never read the native logs, the store, or the configuration of the machine: they use temporary folders.

## Prototype

- `prototype/` is throw-away: it answers questions for the spec and is not the core.
- Run Python with `-I`. Tests: `python -I -m unittest discover -s prototype/tests`.
- Measure: `python -I prototype/measure.py`; validate on a copy of the transcripts:
  `python -I prototype/validate.py --snapshot <folder with cc/ and desktop/<n>/>`.
