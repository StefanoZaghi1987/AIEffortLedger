"""Throw-away survey of the structure of the native logs of Claude Code.

Answers the open points of docs/spec/claude-code-adapter.md (interruptions, subagent links
without `agentId`, nested subagents, the input keys of `MultiEdit` and `NotebookEdit`) with
counts over a copy of the native logs. Writes counts, key paths, and JSON value types to
prototype/out/ only, and never a value of a free-text field: of the values of the records,
only `version`, `type`, `toolDenialKind`, and the names of the delegation tools are written,
and the identifiers of the sessions and subagents of the file names. A key made of letters,
digits, and `_`, starting with a letter or `_`, is written as it is; every other key is
written as `<key>`, because such a key is data, such as a file path.

Usage: python -I prototype/survey.py --snapshot DIR   (DIR holds cc/ and desktop/<n>/ copies)
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import re
from pathlib import Path

INTERRUPTION_PREFIX = "[Request interrupted by user"
DELEGATE_TOOLS = ("Agent", "Task")
INPUT_KEY_TOOLS = ("MultiEdit", "NotebookEdit")
KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
PARENT_HINT = re.compile(r"parent|sidechain", re.IGNORECASE)
ABSENT = object()
Counter = collections.Counter


def safe_key(key: str) -> str:
    """The written form of one key of a record: itself when an identifier, else `<key>`."""
    return key if KEY_RE.fullmatch(key) else "<key>"


def json_type(value: object) -> str:
    """The JSON type of one value, as the survey writes it."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    if isinstance(value, (int, float)):
        return "number"
    return "other"


def walk(value: object, path: str, sink: Counter) -> None:
    """Count the JSON type of every value of a record, at the path of keys that leads to it."""
    if path:
        sink[(path, json_type(value))] += 1
    if isinstance(value, dict):
        for key, item in value.items():
            step = safe_key(str(key))
            walk(item, f"{path}.{step}" if path else step, sink)
    elif isinstance(value, list):
        for item in value:
            walk(item, f"{path}[]", sink)


def collect_values(value: object, key: str, sink: Counter) -> None:
    """Count the values of every occurrence of one key name; a non-string counts as its type."""
    if isinstance(value, dict):
        for name, item in value.items():
            if name == key:
                sink[item if isinstance(item, str) else json_type(item)] += 1
            collect_values(item, key, sink)
    elif isinstance(value, list):
        for item in value:
            collect_values(item, key, sink)


def text_of(content: object) -> str:
    """The text of the content of a message: the content itself, or its `text` blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        blocks = [b for b in content if isinstance(b, dict) and b.get("type") == "text"]
        return "".join(str(b.get("text", "")) for b in blocks)
    return ""


def display_of(path: Path, rel: tuple[str, ...]) -> str:
    """The name of one file of the snapshot, without the name of its launch folder."""
    if "subagents" in rel:
        i = rel.index("subagents")
        return f"{rel[i - 1]}/subagents/{path.stem}"
    return path.stem


def survey_file(path: Path, root: Path, label: str) -> dict:
    """Collect the counts of the survey for one file of native logs."""
    rel = path.relative_to(root).parts
    is_subagent = "subagents" in rel
    own_ids = {path.stem, path.stem.removeprefix("agent-")}
    result = dict(
        label=label, display=display_of(path, rel), is_subagent=is_subagent,
        records=0, invalid=0, version_type=Counter(), paths=Counter(),
        user_total=0, user_text=0, user_interrupted=0, denials=Counter(),
        tool_names={}, delegate=Counter(), unpaired=0, input_keys=Counter(),
        input_other=Counter(), other_agent=0, other_ids=set(),
    )
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                record = json.loads(line)
            except ValueError:
                result["invalid"] += 1
                continue
            if not isinstance(record, dict):
                result["invalid"] += 1
                continue
            result["records"] += 1
            kind = str(record.get("type"))
            raw_version = record.get("version")
            version = str(raw_version) if raw_version is not None else "(no version)"
            result["version_type"][(version, kind)] += 1
            walk(record, kind, result["paths"])
            collect_values(record, "toolDenialKind", result["denials"])
            message = record.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            blocks = (
                [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
            )
            if kind == "user":
                text = text_of(content)
                result["user_total"] += 1
                result["user_text"] += bool(text.strip())
                result["user_interrupted"] += text.lstrip().startswith(INTERRUPTION_PREFIX)
            for block in blocks:
                if block.get("type") == "tool_use":
                    name = str(block.get("name"))
                    result["tool_names"][block.get("id")] = name
                    if name in INPUT_KEY_TOOLS:
                        inp = block.get("input", ABSENT)
                        if isinstance(inp, dict):
                            for key in inp:
                                result["input_keys"][f"{name}:{safe_key(str(key))}"] += 1
                        else:
                            shape = "absent" if inp is ABSENT else json_type(inp)
                            result["input_other"][f"{name}:{shape}"] += 1
                elif block.get("type") == "tool_result":
                    name = result["tool_names"].get(block.get("tool_use_id"))
                    if name is None:
                        result["unpaired"] += 1
                    elif name in DELEGATE_TOOLS:
                        tur = record.get("toolUseResult", ABSENT)
                        shape = "absent" if tur is ABSENT else json_type(tur)
                        holds = isinstance(tur, dict) and "agentId" in tur
                        key = (name, shape, holds if shape == "object" else None)
                        result["delegate"][key] += 1
            if is_subagent:
                agent_id = record.get("agentId")
                if isinstance(agent_id, str) and agent_id not in own_ids:
                    result["other_agent"] += 1
                    result["other_ids"].add(agent_id)
    parent = {(p, t): n for (p, t), n in result["paths"].items()
              if any(PARENT_HINT.search(c) for c in p.split("."))}
    result["parent_paths"] = Counter(parent)
    return result


def roots_of(snapshot: Path) -> list[tuple[str, Path]]:
    """The roots of a snapshot with labels: `cc/` and each `desktop/<n>/` folder that exists."""
    roots = [("cc", snapshot / "cc")]
    roots += [(f"desktop/{p.name}", p) for p in sorted((snapshot / "desktop").glob("*"))]
    return [(label, p) for label, p in roots if p.is_dir()]


def delegate_lines(delegate: Counter) -> list[str]:
    """Per delegation tool: the types of `toolUseResult` and how many objects hold `agentId`."""
    per: dict[str, dict[str, list[int]]] = {
        t: collections.defaultdict(lambda: [0, 0]) for t in DELEGATE_TOOLS
    }
    for (tool, kind, holds), n in delegate.items():
        cell = per[tool][kind]
        cell[0] += n
        cell[1] += n if holds else 0
    out = []
    for tool in DELEGATE_TOOLS:
        body = ", ".join(
            f"{kind}: {n}" + (f" (holds `agentId`: {c})" if kind == "object" else "")
            for kind, (n, c) in sorted(per[tool].items())
        )
        out.append(f"- `{tool}`: {body or 'no results'}")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "out")
    a = ap.parse_args()
    roots = roots_of(a.snapshot)
    results = [
        survey_file(Path(p), root, label)
        for label, root in roots
        for p in sorted(glob.glob(str(root / "**" / "*.jsonl"), recursive=True))
    ]
    version_type: Counter = sum((r["version_type"] for r in results), Counter())
    paths: dict[str, Counter] = collections.defaultdict(Counter)
    for r in results:
        for key, n in r["paths"].items():
            paths[key[0].split(".")[0]][key] += n
    delegate: Counter = sum((r["delegate"] for r in results), Counter())
    denials: Counter = sum((r["denials"] for r in results), Counter())
    input_keys: Counter = sum((r["input_keys"] for r in results), Counter())
    input_other: Counter = sum((r["input_other"] for r in results), Counter())
    files_by_root = Counter(r["label"] for r in results)
    n_records = sum(r["records"] for r in results)
    n_invalid = sum(r["invalid"] for r in results)
    roots_line = ", ".join(f"{label}: {n} files" for label, n in sorted(files_by_root.items()))
    L = [
        f"# Native log survey — {dt.date.today().isoformat()}\n",
        f"Snapshot roots: {roots_line or 'none'}; {len(results)} files, {n_records} records, "
        f"{n_invalid} lines not valid JSON.\n",
    ]
    w = L.append

    w("## Record types by version\n")
    for (version, kind), n in sorted(version_type.items()):
        w(f"- `{version}` `{kind}`: {n}")
    w("")

    w("## Key paths and the JSON type of their values\n")
    for kind in sorted(paths):
        w(f"- `{kind}`")
        for (p, t), n in sorted(paths[kind].items()):
            w(f"  - `{p}`: {t} ({n})")
    w("")

    w("## Interruptions\n")
    w(
        f"- user records: {sum(r['user_total'] for r in results)}; with a text: "
        f"{sum(r['user_text'] for r in results)}; text starting with the interruption prefix: "
        f"{sum(r['user_interrupted'] for r in results)}\n"
    )

    w("## Values of `toolDenialKind`\n")
    for value, n in sorted(denials.items()):
        w(f"- `{value}`: {n}")
    if not denials:
        w("- none")
    w("")

    unpaired = sum(r["unpaired"] for r in results)
    w("## Tool results of the delegation tools\n")
    w("\n".join(delegate_lines(delegate)))
    w(f"- tool results with no tool call of the same file: {unpaired}\n")

    w("## Input keys of the edit tools without a sample\n")
    for tool in INPUT_KEY_TOOLS:
        keys = {k.split(":", 1)[1]: n for k, n in input_keys.items() if k.startswith(f"{tool}:")}
        others = {
            k.split(":", 1)[1]: n for k, n in input_other.items() if k.startswith(f"{tool}:")
        }
        body = ", ".join(f"`{k}` ({n})" for k, n in sorted(keys.items())) or "no calls"
        if others:
            body += "; input that is not an object: "
            body += ", ".join(f"{t} ({n})" for t, n in sorted(others.items()))
        w(f"- `{tool}`: {body}")
    w("")

    w("## Subagent files and parent links\n")
    subs = [r for r in results if r["is_subagent"]]
    if not subs:
        w("- none")
    for r in subs:
        w(
            f"- `{r['display']}`: {r['records']} records; records whose `agentId` is not an agent "
            f"of the file: {r['other_agent']} (distinct other agents: {len(r['other_ids'])})"
        )
        if r["parent_paths"]:
            for (p, t), n in sorted(r["parent_paths"].items()):
                w(f"  - key of a parent name `{p}`: {t} ({n})")
        else:
            w("  - no key of a parent name")
    w("")

    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f"survey-{dt.date.today().isoformat()}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
