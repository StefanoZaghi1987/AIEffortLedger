"""Scenario tests: synthetic transcripts with hand-computed expectations from docs/spec/metrics.md.

Run: python -I -m unittest discover -s prototype/tests
"""
import datetime as dt
import itertools
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import measure as m  # noqa: E402

GAP = 10 * 60
MIN = 60.0
_ids = itertools.count()


def at(day: int, hh: int, mm: int, ss: int = 0) -> str:
    local = dt.datetime(2026, 11, day, hh, mm, ss).astimezone()
    return local.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def prompt(ts, origin="human", text="please do it"):
    o = {"type": "user", "timestamp": ts, "uuid": f"u{next(_ids)}", "message": {"role": "user", "content": text}}
    if origin:
        o["origin"] = {"kind": origin}
    return o


def notification(ts):
    return prompt(ts, origin="task-notification", text="<task-notification>done</task-notification>")


def assistant(ts, tool=None, tool_id=None, background=False):
    content = [{"type": "text", "text": "."}]
    if tool:
        content = [{"type": "tool_use", "id": tool_id, "name": tool, "input": {"run_in_background": background}}]
    n = next(_ids)
    return {"type": "assistant", "timestamp": ts, "requestId": f"r{n}",
            "message": {"id": f"m{n}", "model": "test-model", "content": content,
                        "usage": {"input_tokens": 1, "output_tokens": 1}}}


def result(ts, tool_id, source=None):
    o = {"type": "user", "timestamp": ts, "message": {"content": [{"type": "tool_result", "tool_use_id": tool_id}]}}
    if source:
        o["permissionDecision"] = {"decision": "accept", "source": source}
    return o


def enqueue(ts):
    return {"type": "queue-operation", "operation": "enqueue", "timestamp": ts, "content": "also this"}


def sidechain(ts):
    return {"type": "user", "isSidechain": True, "timestamp": ts, "message": {"content": "subtask"}}


class Scenario:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def session(self, folder, sid, records, subagents=None):
        d = self.root / folder
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{sid}.jsonl").write_text("\n".join(json.dumps(r) for r in records), encoding="utf-8")
        for aid, recs in (subagents or {}).items():
            s = d / sid / "subagents"
            s.mkdir(parents=True, exist_ok=True)
            (s / f"agent-{aid}.jsonl").write_text("\n".join(json.dumps(r) for r in recs), encoding="utf-8")

    def files(self):
        return m.read_roots([self.root])


def minutes(seconds):
    return round(seconds / 60, 3)


class ExampleMorning(unittest.TestCase):
    """09:00 prompt, 09:05 queued message, 09:20-10:00 blocked on a permission of the person, 10:10-10:25
    foreground subagent, 10:30 last output, 10:34 prompt, 10:35 output."""

    def setUp(self):
        sc = Scenario()
        sc.session("proj", "s1", [
            prompt(at(10, 9, 0)), assistant(at(10, 9, 1)), enqueue(at(10, 9, 5)),
            assistant(at(10, 9, 20), "Bash", "t1"), result(at(10, 10, 0), "t1", "user_temporary"),
            assistant(at(10, 10, 5)), assistant(at(10, 10, 10), "Agent", "t2"), result(at(10, 10, 25), "t2"),
            assistant(at(10, 10, 30)), prompt(at(10, 10, 34)), assistant(at(10, 10, 35)),
        ], subagents={"a1": [sidechain(at(10, 10, 10)), assistant(at(10, 10, 24))]})
        self.sc = sc
        self.M = m.metrics(sc.files(), GAP)

    def tearDown(self):
        self.sc.tmp.cleanup()

    def test_human_time(self):
        # signal gap 09:00-09:05 (5) + minimum attention before the isolated 10:00 decision (1) + response 10:30-10:34 (4)
        self.assertEqual(minutes(m.total(self.M["human"])), 10)

    def test_agent_time(self):
        # main: turn 09:00-10:30 (90) - blocked 40 - foreground wait 15 = 35, plus turn 10:34-10:35 (1); subagent 14
        self.assertEqual(minutes(self.M["agent_time"]), 50)

    def test_blocked_time(self):
        self.assertEqual(minutes(m.total(self.M["blocked_union"])), 40)

    def test_activity_classes(self):
        c = {k: minutes(v) for k, v in self.M["classes"].items()}
        self.assertEqual(c, dict(person_only=5, supervised=5, unattended=45, blocked=39))
        self.assertEqual(minutes(sum(self.M["classes"].values())), minutes(self.M["union_all"]))


class OvernightNotification(unittest.TestCase):
    """22:00-23:00 work, a task notification wakes the agent at 03:00, work to 03:30, next prompt 08:00."""

    def test_idle_night_is_not_agent_time(self):
        sc = Scenario()
        sc.session("proj", "s1", [
            prompt(at(10, 22, 0)), assistant(at(10, 22, 30)), assistant(at(10, 23, 0)),
            notification(at(11, 3, 0)), assistant(at(11, 3, 30)), prompt(at(11, 8, 0)),
        ])
        M = m.metrics(sc.files(), GAP)
        self.assertEqual(minutes(M["agent_time"]), 90)
        self.assertEqual(minutes(m.total(M["human"])), 2)  # two isolated prompts
        self.assertEqual(minutes(M["classes"]["unattended"]), 90)
        sc.tmp.cleanup()


class Decisions(unittest.TestCase):
    def test_rule_permission_is_not_a_signal_and_not_blocked(self):
        sc = Scenario()
        sc.session("proj", "s1", [
            prompt(at(10, 10, 59)), assistant(at(10, 11, 0), "Bash", "t1"), result(at(10, 11, 0, 5), "t1", "config"),
            assistant(at(10, 11, 1)),
        ])
        (f,) = sc.files()
        self.assertEqual(f.decisions, [])
        M = m.metrics([f], GAP)
        self.assertEqual(minutes(M["agent_time"]), 2)
        self.assertEqual(minutes(m.total(M["human"])), 1)
        sc.tmp.cleanup()

    def test_permission_blocked_overnight_is_still_blocked_time(self):
        sc = Scenario()
        sc.session("proj", "s1", [
            prompt(at(10, 20, 0)), assistant(at(10, 20, 1), "Bash", "p1"),
            result(at(11, 9, 0), "p1", "user_temporary"), assistant(at(11, 9, 1)),
        ])
        (f,) = sc.files()
        self.assertEqual(len(f.decisions), 1)
        M = m.metrics([f], GAP)
        self.assertEqual(minutes(m.total(M["blocked_union"])), 779)  # 20:01 -> 09:00
        self.assertEqual(minutes(M["agent_time"]), 2)
        self.assertEqual(minutes(M["classes"]["blocked"]), 778)  # the minute before the decision is person only
        sc.tmp.cleanup()

    def test_question_to_the_person_is_blocked_time_and_a_signal(self):
        sc = Scenario()
        sc.session("proj", "s1", [
            prompt(at(10, 13, 0)), assistant(at(10, 13, 1), "AskUserQuestion", "q1"), result(at(10, 13, 4), "q1"),
            assistant(at(10, 13, 5)),
        ])
        M = m.metrics(sc.files(), GAP)
        self.assertEqual(minutes(m.total(M["blocked_union"])), 3)
        self.assertEqual(minutes(M["agent_time"]), 2)
        self.assertEqual(minutes(m.total(M["human"])), 4)  # signal gap 13:00-13:04
        sc.tmp.cleanup()


class Subagents(unittest.TestCase):
    def test_background_subagent_is_not_a_wait(self):
        sc = Scenario()
        sc.session("proj", "s1", [
            prompt(at(10, 12, 0)), assistant(at(10, 12, 1), "Agent", "b1", background=True),
            result(at(10, 12, 1, 2), "b1"), assistant(at(10, 12, 2)),
            notification(at(10, 12, 30)), assistant(at(10, 12, 31)),
        ])
        (f,) = sc.files()
        self.assertEqual(f.fg_waits, [])
        self.assertEqual(minutes(m.metrics([f], GAP)["agent_time"]), 3)
        sc.tmp.cleanup()


class Parallel(unittest.TestCase):
    def test_signals_of_parallel_sessions_form_one_stream(self):
        sc = Scenario()
        sc.session("projA", "a", [prompt(at(10, 14, 0)), prompt(at(10, 14, 8)), prompt(at(10, 15, 0))])
        sc.session("projB", "b", [prompt(at(10, 14, 4)), prompt(at(10, 14, 12)), prompt(at(10, 15, 6))])
        files = sc.files()
        # one stream 14:00, 14:04, 14:08, 14:12 (12 min) and 15:00, 15:06 (6 min); an instant counts once
        self.assertEqual(minutes(m.total(m.human_time(files, GAP))), 18)
        sc.tmp.cleanup()

    def test_alternating_sessions_keep_the_person_present(self):
        sc = Scenario()
        sc.session("projA", "a", [prompt(at(10, 14, 0)), prompt(at(10, 14, 12))])
        sc.session("projB", "b", [prompt(at(10, 14, 6)), prompt(at(10, 14, 18))])
        files = sc.files()
        self.assertEqual(minutes(m.total(m.human_time(files, GAP))), 18)  # gaps of 6 min across sessions
        per_session = sum(m.total(m.human_time([f], GAP)) for f in files)
        self.assertEqual(minutes(per_session), 4)  # gaps of 12 min inside each session: four isolated signals
        sc.tmp.cleanup()


class Invocation(unittest.TestCase):
    def test_prompts_of_a_programmatic_session_are_not_human_signals(self):
        sc = Scenario()
        records = [prompt(at(10, 2, 0)), assistant(at(10, 2, 5)), prompt(at(10, 2, 6)), assistant(at(10, 2, 9))]
        for r in records:
            r["entrypoint"] = "sdk-cli"
        sc.session("proj", "s1", records)
        M = m.metrics(sc.files(), GAP)
        self.assertEqual(minutes(m.total(M["human"])), 0)
        self.assertEqual(minutes(M["classes"]["unattended"]), 8)  # turns 02:00-02:05 and 02:06-02:09
        sc.tmp.cleanup()


class Boundaries(unittest.TestCase):
    def test_midnight_split(self):
        s = dt.datetime(2026, 11, 10, 23, 30).astimezone().timestamp()
        days = m.by_local_day([(s, s + 3600)])
        self.assertEqual(sorted(round(v / 60) for v in days.values()), [30, 30])

    def test_stale_turn_is_closed(self):
        sc = Scenario()
        sc.session("proj", "s1", [
            prompt(at(10, 8, 0)), assistant(at(10, 8, 1), "Bash", "t1"), result(at(10, 13, 0), "t1"),
            assistant(at(10, 13, 1)),
        ])
        (f,) = sc.files()
        self.assertEqual(f.stale_turns, 1)
        self.assertEqual(minutes(sum(e - s for s, e in f.turns)), 2)  # 08:00-08:01 and 13:00-13:01
        sc.tmp.cleanup()

    def test_old_format_prompt_heuristic(self):
        self.assertTrue(m.is_human_prompt({"type": "user", "message": {"content": "fix the build"}}))
        self.assertFalse(m.is_human_prompt({"type": "user", "message": {"content": "<task-notification>x"}}))
        self.assertFalse(m.is_human_prompt({"type": "user", "isMeta": True, "message": {"content": "fix"}}))
        self.assertTrue(m.is_human_prompt({"type": "user", "message": {"content": "<command-message>review"}}))


if __name__ == "__main__":
    unittest.main()
