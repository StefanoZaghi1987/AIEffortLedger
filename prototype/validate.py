"""Throw-away validation of the prototype measurements on a fixed snapshot of real transcripts.

Checks determinism, the prompt heuristic of old formats, turn detection against Claude Code turn_duration, the
sensitivity to open parameters, token deduplication, and the coverage of human time inside the daily presence span.
Writes absolute values to prototype/out/ only.

Usage: python -I prototype/validate.py --snapshot DIR   (DIR holds cc/ and desktop/<n>/ copies of the transcript roots)
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import glob
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import measure as m  # noqa: E402

GAP = m.REFERENCE_GAP_MIN * 60


def roots_of(snapshot: Path) -> list[Path]:
    return [snapshot / "cc"] + sorted((snapshot / "desktop").glob("*"))


def raw_records(path: str):
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except ValueError:
                continue


def fingerprint(M: dict) -> tuple:
    return (round(M["agent_time"], 3), round(m.total(M["human"]), 3), round(m.total(M["blocked_union"]), 3),
            tuple(round(v, 3) for v in M["classes"].values()))


def pct(x: float) -> str:
    return f"{x * 100:.1f} %"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "out")
    a = ap.parse_args()
    roots = roots_of(a.snapshot)
    files = m.read_roots(roots)
    L = [f"# Validation — {dt.date.today().isoformat()}\n", f"Snapshot: {len(files)} files.\n"]
    w = L.append

    # 1. determinism: same result on a second read and on reversed file order
    base = fingerprint(m.metrics(files, GAP))
    again = fingerprint(m.metrics(m.read_roots(roots), GAP))
    reverse = fingerprint(m.metrics(list(reversed(files)), GAP))
    w("## Determinism\n")
    w(f"- Second read identical: {base == again}; reversed file order identical: {base == reverse}\n")

    # 2. old-format prompt heuristic against the explicit origin field
    tp = fp = fn = tn = 0
    for f in files:
        if f.is_subagent:
            continue
        for o in raw_records(str(f.path)):
            if o.get("type") != "user" or "origin" not in o:
                continue
            content = (o.get("message") or {}).get("content")
            if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                continue
            truth = (o.get("origin") or {}).get("kind") == "human" and not o.get("isMeta") and not o.get("isSidechain")
            guess = m.is_human_prompt({k: v for k, v in o.items() if k != "origin"})
            tp += truth and guess
            fp += guess and not truth
            fn += truth and not guess
            tn += not truth and not guess
    w("## Prompt heuristic for formats without `origin`\n")
    w(f"- Records with `origin`: {tp + fp + fn + tn}; heuristic precision {pct(tp / max(tp + fp, 1))}, "
      f"recall {pct(tp / max(tp + fn, 1))} (true positives {tp}, false positives {fp}, false negatives {fn})\n")

    # 3. turn detection against turn_duration, on windows without blocked time
    ratios, with_blocked = [], 0
    for f in files:
        if f.is_subagent:
            continue
        for o in raw_records(str(f.path)):
            if o.get("type") != "system" or o.get("subtype") != "turn_duration" or not o.get("timestamp"):
                continue
            end = m.parse_ts(o["timestamp"]).timestamp()
            start = end - (o.get("durationMs") or 0) / 1000
            if end - start < 30:
                continue
            window = [(start, end)]
            if m.total(m.intersect(window, f.decisions)) > 0:
                with_blocked += 1
                continue
            covered = m.total(m.intersect(window, f.turns))
            ratios.append(covered / (end - start))
    w("## Turns against `turn_duration` (windows of at least 30 s without blocked time)\n")
    if ratios:
        q = statistics.quantiles(ratios, n=10)
        w(f"- Windows: {len(ratios)} (excluded with blocked time: {with_blocked}); share of the window covered by "
          f"prototype turns: median {pct(statistics.median(ratios))}, p10 {pct(q[0])}, p90 {pct(q[-1])}; "
          f"windows covered at least 95 %: {pct(sum(r >= 0.95 for r in ratios) / len(ratios))}\n")

    # 4. sensitivity to open parameters
    w("## Sensitivity\n")
    ref_h = m.total(m.human_time(files, GAP))
    keep = m.MIN_ATTENTION_S
    for s in (30, 60, 120):
        m.MIN_ATTENTION_S = s
        w(f"- Minimum attention {s} s: human time {pct(m.total(m.human_time(files, GAP)) / ref_h)} of the 60 s value")
    m.MIN_ATTENTION_S = keep
    ref_a = m.metrics(files, GAP)["agent_time"]
    keep = m.STALE_OPEN_S
    for h in (2, 4, 8):
        m.STALE_OPEN_S = h * 3600
        alt = m.metrics(m.read_roots(roots), GAP)["agent_time"]
        w(f"- Stale limit {h} h: agent time {pct(alt / ref_a)} of the 4 h value")
    m.STALE_OPEN_S = keep
    w("")

    # 5. token deduplication: naive per-line sums against one count per response
    naive = collections.Counter()
    dedup = collections.Counter()
    for f in files:
        for o in raw_records(str(f.path)):
            if o.get("type") == "assistant":
                u = (o.get("message") or {}).get("usage") or {}
                naive["output"] += u.get("output_tokens", 0) or 0
                naive["cache_read"] += u.get("cache_read_input_tokens", 0) or 0
        for rec in f.tokens.values():
            dedup.update(rec["counts"])
    w("## Token deduplication\n")
    for k in ("output", "cache_read"):
        w(f"- {k}: naive per-line sum is {pct(naive[k] / max(dedup[k], 1))} of the deduplicated count")
    w("")

    # 6. coverage of the daily presence span (first to last human signal of the day, all sessions)
    M = m.metrics(files, GAP)
    signals = collections.defaultdict(list)
    for f in files:
        for t in f.human_prompts + [b for _, b in f.decisions] + f.enqueues:
            signals[dt.datetime.fromtimestamp(t).date().isoformat()].append(t)
    human_by_day = m.by_local_day(M["human"])
    agent_by_day = m.by_local_day(M["working_union"])
    cov, spans = [], []
    for d, ts in signals.items():
        span = max(ts) - min(ts)
        if span >= 600:
            cov.append(human_by_day.get(d, 0) / span)
            spans.append(span)
    agent_only_days = [d for d in agent_by_day if d not in signals]
    weekend_agent = sum(v for d, v in agent_by_day.items() if dt.date.fromisoformat(d).weekday() >= 5)
    w("## Presence span and coverage\n")
    if cov:
        w(f"- Days with a presence span of at least 10 minutes: {len(cov)}; human time covers a median "
          f"{pct(statistics.median(cov))} of the span (p10 {pct(statistics.quantiles(cov, n=10)[0])}, "
          f"p90 {pct(statistics.quantiles(cov, n=10)[-1])})")
        w(f"- Median presence span: {statistics.median(spans) / 3600:.1f} h; median human time per active day: "
          f"{statistics.median(human_by_day[d] for d in signals) / 3600:.1f} h")
    w(f"- Days with agent time and no human signal: {len(agent_only_days)}; agent time on weekends: "
      f"{pct(weekend_agent / max(sum(agent_by_day.values()), 1))} of the total\n")

    a.out.mkdir(parents=True, exist_ok=True)
    out = a.out / f"validation-{dt.date.today().isoformat()}.md"
    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(out.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
