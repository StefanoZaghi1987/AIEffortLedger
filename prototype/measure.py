"""Throw-away measurement of human time and agent time on real Claude Code transcripts.

Answers the open points of docs/spec/metrics.md and docs/spec/event-schema.md with numbers. Reads transcripts only,
never writes outside prototype/out/, and never copies prompt, response, or code text.

Usage: python -I prototype/measure.py [--root DIR ...] [--out DIR] [--days N]
"""
from __future__ import annotations

import argparse
import bisect
import collections
import datetime as dt
import glob
import json
import os
import re
import sys
from pathlib import Path

GAPS_MIN = (5, 10, 15, 30)
REFERENCE_GAP_MIN = 10
MIN_ATTENTION_S = 60
# A turn interval that stays open longer than this without any agent event is a crash or an interrupt, not work.
STALE_OPEN_S = 4 * 3600
DECISION_TOOLS = {"AskUserQuestion", "ExitPlanMode"}
AGENT_TOOLS = {"Agent", "Task"}
NON_HUMAN_TAGS = {"task-notification", "local-command-stdout", "local-command-caveat", "system-reminder"}
PROGRAMMATIC_ENTRYPOINTS = {"sdk-cli", "sdk-ts", "sdk-py"}


def default_roots() -> list[Path]:
    home = Path.home()
    roots = [home / ".claude" / "projects"]
    for base in (os.environ.get("APPDATA"), home / "Library" / "Application Support", home / ".config"):
        if base:
            roots += [Path(p) for p in glob.glob(str(Path(base) / "Claude" / "local-agent-mode-sessions" / "**" / ".claude" / "projects"), recursive=True)]
    return [r for r in roots if r.is_dir()]


def parse_ts(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


# ---------------------------------------------------------------- intervals (lists of (start, end) in epoch seconds)

def union(iv):
    out = []
    for s, e in sorted(i for i in iv if i[1] > i[0]):
        if out and s <= out[-1][1]:
            out[-1][1] = max(out[-1][1], e)
        else:
            out.append([s, e])
    return [tuple(x) for x in out]


def total(iv) -> float:
    return sum(e - s for s, e in union(iv))


def intersect(a, b):
    a, b, out, i, j = union(a), union(b), [], 0, 0
    while i < len(a) and j < len(b):
        s, e = max(a[i][0], b[j][0]), min(a[i][1], b[j][1])
        if s < e:
            out.append((s, e))
        if a[i][1] < b[j][1]:
            i += 1
        else:
            j += 1
    return out


def subtract(a, b):
    out = []
    b = union(b)
    for s, e in union(a):
        for bs, be in b:
            if be <= s or bs >= e:
                continue
            if bs > s:
                out.append((s, bs))
            s = max(s, be)
            if s >= e:
                break
        if s < e:
            out.append((s, e))
    return out


def by_local_day(iv) -> dict[str, float]:
    days = collections.Counter()
    for s, e in union(iv):
        while s < e:
            local = dt.datetime.fromtimestamp(s).astimezone()
            nxt = (local.replace(hour=0, minute=0, second=0, microsecond=0) + dt.timedelta(days=1)).timestamp()
            cut = min(e, nxt)
            days[local.date().isoformat()] += cut - s
            s = cut
    return days


# ---------------------------------------------------------------- reading one transcript file

def text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(x.get("text", "") for x in content if isinstance(x, dict) and x.get("type") == "text")
    return ""


def is_human_prompt(o: dict) -> bool:
    if o.get("isMeta") or o.get("isSidechain"):
        return False
    origin = (o.get("origin") or {}).get("kind")
    if origin is not None:
        return origin == "human"
    txt = text_of((o.get("message") or {}).get("content")).lstrip()
    if not txt:
        return False
    m = re.match(r"<([a-zA-Z_-]+)", txt)
    return not (m and m.group(1) in NON_HUMAN_TAGS)


class FileResult:
    def __init__(self, path: Path, root: Path):
        self.path, self.root = path, root
        rel = path.relative_to(root).parts
        self.folder = rel[0]
        self.is_subagent = "subagents" in rel
        self.session_id = rel[1] if self.is_subagent else path.stem
        self.agent_id = path.stem if self.is_subagent else self.session_id
        self.human_prompts: list[float] = []
        self.decisions: list[tuple[float, float]] = []       # (decision request, decision of the person)
        self.fg_waits: list[tuple[float, float]] = []        # waits for own foreground subagents
        self.enqueues: list[float] = []
        self.turns: list[tuple[float, float]] = []
        self.prompt_latency: list[tuple[float, float]] = []  # (previous agent event, prompt)
        self.turn_duration_ms = 0
        self.tokens: dict[tuple, dict] = {}                   # (message id, request id) -> model, time, counts
        self.cwds: collections.Counter = collections.Counter()
        self.entrypoints: collections.Counter = collections.Counter()
        self.versions: collections.Counter = collections.Counter()
        self.record_types: dict[str, set] = collections.defaultdict(set)
        self.stale_turns = 0
        self.away = 0
        self.prompt_uuids: set = set()
        self.interactive = True

    def read(self) -> "FileResult":
        rows = []
        with open(self.path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if o.get("timestamp"):
                    rows.append((parse_ts(o["timestamp"]).timestamp(), o))
                v = o.get("version")
                if v:
                    self.versions[v] += 1
                    self.record_types[v].add(o.get("type"))
        rows.sort(key=lambda r: r[0])
        open_since = last_agent = last_event = None
        pending: dict[str, tuple] = {}  # tool use id -> (time, tool name, background)
        orphans: dict[str, tuple] = {}  # calls pending when a turn went stale: matched, but keep no turn open

        def close():
            nonlocal open_since
            if open_since is not None and last_agent is not None and last_agent > open_since:
                self.turns.append((open_since, last_agent))
            open_since = None

        for t, o in rows:
            kind = o.get("type")
            if o.get("cwd"):
                self.cwds[o["cwd"]] += 1
            if o.get("entrypoint"):
                self.entrypoints[o["entrypoint"]] += 1
            if open_since is not None and last_event is not None and t - last_event > STALE_OPEN_S:
                self.stale_turns += 1
                orphans.update(pending)
                pending.clear()
                close()
            if kind == "assistant":
                msg = o.get("message") or {}
                if open_since is None:
                    open_since = t
                last_agent = last_event = t
                for block in msg.get("content") or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        inp = block.get("input") if isinstance(block.get("input"), dict) else {}
                        pending[block.get("id")] = (t, block.get("name"), bool(inp.get("run_in_background")))
                model = msg.get("model")
                if model and not str(model).startswith("<"):
                    u = msg.get("usage") or {}
                    cc = u.get("cache_creation") or {}
                    w1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
                    w5 = cc.get("ephemeral_5m_input_tokens", (u.get("cache_creation_input_tokens", 0) or 0) - w1) or 0
                    counts = dict(input=u.get("input_tokens", 0) or 0, output=u.get("output_tokens", 0) or 0,
                                  cache_write_5m=w5, cache_write_1h=w1, cache_read=u.get("cache_read_input_tokens", 0) or 0)
                    key = (msg.get("id"), o.get("requestId"))
                    rec = self.tokens.setdefault(key, dict(model=model, t=t, counts=dict.fromkeys(counts, 0)))
                    rec["t"] = max(rec["t"], t)
                    for c, n in counts.items():
                        rec["counts"][c] = max(rec["counts"][c], n)
            elif kind == "user":
                content = (o.get("message") or {}).get("content")
                results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"] if isinstance(content, list) else []
                if results:
                    pd = o.get("permissionDecision") or {}
                    for b in results:
                        call = pending.pop(b.get("tool_use_id"), None) or orphans.pop(b.get("tool_use_id"), None)
                        if call is None:
                            continue
                        started, name, background = call
                        if name in DECISION_TOOLS or str(pd.get("source", "")).startswith("user"):
                            self.decisions.append((started, t))
                        elif name in AGENT_TOOLS and not background:
                            self.fg_waits.append((started, t))
                    if open_since is None:
                        open_since = t
                    last_event = t
                elif not self.is_subagent and is_human_prompt(o):
                    if last_agent is not None:
                        self.prompt_latency.append((last_agent, t))
                    pending.clear()
                    close()
                    self.human_prompts.append(t)
                    self.prompt_uuids.add(o.get("uuid"))
                    open_since = last_event = t
                else:
                    if not pending:
                        close()
                    if open_since is None:
                        open_since = t
                    last_event = t
            elif kind == "system" and o.get("subtype") == "turn_duration":
                self.turn_duration_ms += o.get("durationMs") or 0
            elif kind == "system" and o.get("subtype") == "away_summary":
                self.away += 1
            elif kind == "queue-operation" and o.get("operation") == "enqueue":
                c = o.get("content")
                if isinstance(c, str) and c.strip() and not c.lstrip().startswith("<"):
                    self.enqueues.append(t)
        close()
        main_entry = self.entrypoints.most_common(1)
        self.interactive = not (main_entry and main_entry[0][0] in PROGRAMMATIC_ENTRYPOINTS)
        return self


# ---------------------------------------------------------------- repository identity, read from files (no git run)

def find_git_dir(cwd: str) -> Path | None:
    p = Path(cwd)
    for d in [p, *p.parents]:
        g = d / ".git"
        if g.is_dir():
            return g
        if g.is_file():
            m = re.match(r"gitdir:\s*(.+)", g.read_text(encoding="utf-8", errors="replace").strip())
            if m:
                target = Path(m.group(1))
                return target if target.is_absolute() else (d / target).resolve()
    return None


def common_dir(git_dir: Path) -> Path:
    c = git_dir / "commondir"
    if c.is_file():
        target = Path(c.read_text(encoding="utf-8", errors="replace").strip())
        return target if target.is_absolute() else (git_dir / target).resolve()
    return git_dir


def remote_url(common: Path) -> str | None:
    cfg = common / "config"
    if not cfg.is_file():
        return None
    section = None
    for line in cfg.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        m = re.match(r'\[remote\s+"([^"]+)"\]', line)
        if m:
            section = m.group(1)
        elif line.startswith("["):
            section = None
        elif section == "origin" and re.match(r"url\s*=", line):
            return line.split("=", 1)[1].strip()
    return None


def normalize_remote(url: str) -> str:
    url = re.sub(r"^(https?://|ssh://|git@)", "", url.strip()).replace(":", "/")
    url = re.sub(r"^[^@/]+@", "", url)
    return re.sub(r"\.git$", "", url).lower()


def repo_identity(cwd: str) -> str:
    if not os.path.isdir(cwd):
        return "missing-folder"
    g = find_git_dir(cwd)
    if g is None:
        return "no-git"
    remote = remote_url(common_dir(g))
    return "remote:" + normalize_remote(remote) if remote else "no-remote"


# ---------------------------------------------------------------- human time (docs/spec/metrics.md)

def signals(f: FileResult) -> list[float]:
    """Human signals of one file; a session started by a script or the SDK has none."""
    if not f.interactive:
        return []
    return f.human_prompts + [b for _, b in f.decisions] + f.enqueues


def human_time(files, gap_s, signal_gaps: bool = True, responses: bool = True):
    """Human time of a person: signal gaps over one stream of the signals of all files, response intervals inside
    each session, minimum attention for isolated signals."""
    stream = sorted(t for f in files for t in signals(f))
    iv = []
    if signal_gaps:
        iv += [(a, b) for a, b in zip(stream, stream[1:]) if b - a <= gap_s]
    if responses:
        iv += [(a, b) for f in files if f.interactive for a, b in f.prompt_latency + f.decisions if b - a <= gap_s]
    iv = union(iv)
    starts = [s for s, _ in iv]

    def covered(t):
        i = bisect.bisect_right(starts, t) - 1
        return i >= 0 and t <= iv[i][1]

    return union(iv + [(t - MIN_ATTENTION_S, t) for t in stream if not covered(t)])


# ---------------------------------------------------------------- report

def metrics(files: list[FileResult], gap_s: float) -> dict:
    """Agent time, blocked time, human time, and activity classes of a set of transcript files (seconds)."""
    working = {id(f): subtract(f.turns, f.decisions + f.fg_waits) for f in files}
    working_union = union([x for iv in working.values() for x in iv])
    blocked_union = union([x for f in files for x in f.decisions])
    h = human_time(files, gap_s)
    sup = total(intersect(h, working_union))
    return dict(
        working=working,
        working_union=working_union,
        blocked_union=blocked_union,
        human=h,
        agent_time=sum(total(x) for x in working.values()),
        classes=dict(person_only=total(h) - sup, supervised=sup, unattended=total(working_union) - sup,
                     blocked=total(subtract(subtract(blocked_union, working_union), h))),
        union_all=total(h + working_union + blocked_union),
    )


def read_roots(roots: list[Path]) -> list[FileResult]:
    return [FileResult(Path(p), root).read()
            for root in roots for p in sorted(glob.glob(str(root / "**" / "*.jsonl"), recursive=True))]


def hours(seconds: float) -> str:
    return f"{seconds / 3600:.1f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", action="append", type=Path)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "out")
    ap.add_argument("--days", type=int, help="only the last N days")
    a = ap.parse_args()
    roots = a.root or default_roots()
    files = read_roots(roots)
    if a.days:
        cutoff = dt.datetime.now().timestamp() - a.days * 86400
        files = [f for f in files if any(t >= cutoff for t in f.human_prompts + [s for s, _ in f.turns])]
    main_files = [f for f in files if not f.is_subagent]
    sub_files = [f for f in files if f.is_subagent]

    folder_repo: dict[str, str] = {}
    for f in files:
        if f.folder not in folder_repo and f.cwds:
            folder_repo[f.folder] = repo_identity(f.cwds.most_common(1)[0][0])
    repo_folders = collections.defaultdict(set)
    for folder, repo in folder_repo.items():
        repo_folders[repo].add(folder)

    # agent time and blocked time, per agent
    M = metrics(files, REFERENCE_GAP_MIN * 60)
    working, working_union, blocked_union = M["working"], M["working_union"], M["blocked_union"]
    turn_sum = sum(e - s for f in files for s, e in f.turns)
    agent_sum = M["agent_time"]
    main_sum = sum(total(working[id(f)]) for f in main_files)
    blocked = [x for f in files for x in f.decisions]
    fg_wait = sum(total(f.fg_waits) for f in files)
    turn_duration_s = sum(f.turn_duration_ms for f in main_files) / 1000
    files_with_td = [f for f in main_files if f.turn_duration_ms]
    turns_where_td = sum(e - s for f in files_with_td for s, e in f.turns)

    # human time
    human = {}
    for g in GAPS_MIN:
        human[g] = dict(A=total(human_time(files, g * 60, responses=False)),
                        B=total(human_time(files, g * 60, signal_gaps=False)),
                        U=total(human_time(files, g * 60)))
    H, classes, all_union = M["human"], M["classes"], M["union_all"]

    # parallel human time across projects; per-session human time for comparison with the person-level stream
    gap = REFERENCE_GAP_MIN * 60
    repo_files = collections.defaultdict(list)
    for f in files:
        repo_files[folder_repo.get(f.folder, "unknown")].append(f)
    per_repo_h = {repo: human_time(fs, gap) for repo, fs in repo_files.items()}
    sum_per_repo = sum(total(v) for v in per_repo_h.values())
    sessions = collections.defaultdict(list)
    for f in files:
        sessions[(f.root, f.folder, f.session_id)].append(f)
    per_session_h = total(union([x for fs in sessions.values() for x in human_time(fs, gap)]))
    programmatic = [f for f in main_files if not f.interactive]
    all_prompts = sum(len(f.human_prompts) for f in main_files)

    # duplicates from fork or resume
    key_sessions = collections.defaultdict(set)
    for f in main_files:
        for k in f.tokens:
            key_sessions[k].add(f.session_id)
    dup_keys = sum(1 for s in key_sessions.values() if len(s) > 1)

    tok = collections.defaultdict(collections.Counter)
    for f in files:
        for rec in f.tokens.values():
            tok[rec["model"]].update(rec["counts"])

    daily = collections.defaultdict(lambda: collections.defaultdict(lambda: [0.0, 0.0]))
    for repo, iv in per_repo_h.items():
        for d, s in by_local_day(iv).items():
            daily[d][repo][0] += s
    for f in files:
        repo = folder_repo.get(f.folder, "unknown")
        for d, sec in by_local_day(working[id(f)]).items():
            daily[d][repo][1] += sec

    versions = collections.Counter()
    types_by_version = collections.defaultdict(set)
    entry = collections.Counter()
    for f in files:
        versions.update(f.versions)
        entry.update(f.entrypoints)
        for v, ts in f.record_types.items():
            types_by_version[v] |= ts

    n_prompts = sum(len(f.human_prompts) for f in files if f.interactive)
    n_dec = sum(len(f.decisions) for f in files if f.interactive)
    n_enq = sum(len(f.enqueues) for f in files if f.interactive)
    all_t = [s for f in files for s, _ in f.turns]
    first = dt.datetime.fromtimestamp(min(all_t)).date() if all_t else None
    last = dt.datetime.fromtimestamp(max(all_t)).date() if all_t else None
    L = []
    w = L.append
    w(f"# Prototype measurements — {dt.date.today().isoformat()}\n")
    w(f"Roots: {len(roots)}; files: {len(main_files)} sessions, {len(sub_files)} subagents; period {first} → {last}.")
    w(f"Entry points: {dict(entry)}. Away summaries: {sum(f.away for f in files)}. "
      f"Turns closed by the stale limit of {STALE_OPEN_S // 3600} h: {sum(f.stale_turns for f in files)}.\n")
    w("## Human time by idle gap (hours)\n")
    w("| Idle gap (min) | A: signal gaps | B: response intervals | A ∪ B (spec) |\n|---|---|---|---|")
    for g in GAPS_MIN:
        w(f"| {g} | {hours(human[g]['A'])} | {hours(human[g]['B'])} | {hours(human[g]['U'])} |")
    w(f"\nHuman signals: {n_prompts + n_dec + n_enq} (prompts {n_prompts}, decisions of the person {n_dec}, "
      f"queued messages {n_enq}).\n")
    w("## Agent time and blocked time (hours)\n")
    w(f"- Turn durations, sum over agents: {hours(turn_sum)}")
    w(f"- Agent time (spec), sum over agents: {hours(agent_sum)} (main {hours(main_sum)}, subagents {hours(agent_sum - main_sum)})")
    w(f"- Agent time union: {hours(total(working_union))}; parallelism {agent_sum / max(total(working_union), 1):.2f}")
    w(f"- Blocked time: sum {hours(sum(b - a for a, b in blocked))}, union {hours(total(blocked_union))}")
    w(f"- Waiting for own foreground subagents: {hours(fg_wait)}")
    w(f"- Cross-check, sessions with `turn_duration`: tool-reported {hours(turn_duration_s)} vs prototype turns "
      f"{hours(turns_where_td)} on the same {len(files_with_td)} sessions\n")
    w(f"## Activity classes (spec definitions, idle gap {REFERENCE_GAP_MIN} min, hours)\n")
    w("| Person only | Supervised | Unattended | Blocked |\n|---|---|---|---|")
    w(f"| {hours(classes['person_only'])} | {hours(classes['supervised'])} | {hours(classes['unattended'])} | "
      f"{hours(classes['blocked'])} |\n")
    w(f"Check: union of human, agent, and blocked time {hours(all_union)}; sum of classes {hours(sum(classes.values()))}.\n")
    w("## Parallel human time across projects\n")
    w(f"- Sum of per-project human time {hours(sum_per_repo)} vs person-level total {hours(total(H))}: difference "
      f"{hours(sum_per_repo - total(H))} ({(sum_per_repo - total(H)) / max(total(H), 1) * 100:.1f} %); the total "
      f"also holds signal gaps between sessions of different projects, which the split rule divides")
    w(f"- Person-level human time / per-session human time: {total(H) / max(per_session_h, 1):.3f}")
    w(f"- Sessions with a programmatic entry point: {len(programmatic)} of {len(main_files)}; prompts they hold: "
      f"{sum(len(f.human_prompts) for f in programmatic) / max(all_prompts, 1) * 100:.1f} % of all prompts, "
      f"not counted as human signals\n")
    w("## Project identity\n")
    w("| Repository identity | Log folders |\n|---|---|")
    for repo, folders in sorted(repo_folders.items(), key=lambda x: -len(x[1])):
        w(f"| `{repo}` | {len(folders)}: {', '.join(sorted(folders))} |")
    w("\n## Duplicates\n")
    w(f"- Responses present in more than one session: {dup_keys} of {len(key_sessions)}\n")
    w("## Tokens per model (millions)\n")
    w("| Model | Input | Output | Cache write 5m | Cache write 1h | Cache read |\n|---|---|---|---|---|---|")
    for m, c in sorted(tok.items(), key=lambda x: -x[1]["output"]):
        w(f"| `{m}` | " + " | ".join(f"{c[k] / 1e6:.2f}" for k in ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")) + " |")
    w("\n## Record types per version\n")
    for v in sorted(types_by_version):
        w(f"- `{v}` ({versions[v]} lines): {', '.join(sorted(str(t) for t in types_by_version[v]))}")
    w(f"\n## Daily human time / agent time per project (hours, spec definitions, idle gap {REFERENCE_GAP_MIN} min)\n")
    w("| Day | Project | Human | Agent |\n|---|---|---|---|")
    for d in sorted(daily):
        for repo, (h, ag) in sorted(daily[d].items()):
            w(f"| {d} | `{repo}` | {hours(h)} | {hours(ag)} |")

    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f"measurements-{dt.date.today().isoformat()}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    sys.exit(main())
