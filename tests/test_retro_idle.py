"""retro.py's idle time (the loop rules of 2026-11-27): for each task, the
time when no step was running, grouped by the line before each gap."""
import json
import unittest

from helpers import TempHome, run, task_loop

import retro

TASKS = "state/agent-foreman/projects/o-r/tasks"


def lines(*rows):
    return "".join(json.dumps(r) + "\n" for r in rows)


def row(time, step, event, **more):
    return {"time": f"2026-11-27T{time}:00Z", "stage": step, "step": step, "event": event, **more}


TIMELINE = (
    row("01:00", "plan", "start", round=1),
    row("01:20", "plan", "end", outcome="done"),
    row("01:25", "plan-check", "stop", done="waiting: the foreman's plan-check of plan.md"),
    row("02:25", "plan-check", "end", outcome="approved"),
    row("02:30", "build", "start", round=1),
    row("02:40", "build", "progress"),
    {"event": "heartbeat", "agent": "7", "time": "2026-11-27T02:50:00Z"},
    row("03:00", "build", "stop", done="REPORT: decision — which schema", blocked=""),
    row("07:00", "build", "progress", done="the person chose: the new schema"),  # resumed with no start line
    row("07:30", "build", "end", outcome="done"),
    row("07:30", "verify", "start", round=1),
    row("07:40", "build", "start", round=1),  # verify's end line is missing: the lead went on to build
    row("08:00", "build", "end", outcome="done"),
    row("08:10", "redteam-review", "start", round=1),
    row("08:10", "test", "start", round=1),
    row("08:30", "redteam-review", "end", outcome="approved"),  # QA still runs: no gap
    row("08:50", "test", "end", outcome="pass"),
    row("09:00", "finalize", "stop", done="no token for the push", blocked="a token with repo scope"),
    {"time": "not a time", "stage": "finalize", "step": "finalize", "event": "start"},
    row("09:30", "publish", "start", round=1),
    row("09:40", "publish", "end", outcome="done"),
)


class Idle(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.home.write(f"{TASKS}/7/loop.json", task_loop(difficulty="high", task="7"))
        self.home.write(f"{TASKS}/7/status.jsonl", lines(*TIMELINE))

    def test_the_gaps_go_to_the_line_before_them(self):
        idle = retro.facts("o/r", ["7"])["tasks"][0]["idle"]
        self.assertEqual(idle, {"minutes": 360.0, "span_minutes": 520.0, "by_event": {
            "stop build (decision)": 240.0, "stop plan-check (waiting)": 60.0, "stop finalize (blocked)": 30.0,
            "end build (done)": 10.0, "end test (pass)": 10.0, "end plan (done)": 5.0,
            "end plan-check (approved)": 5.0}})

    def test_the_stop_kinds(self):
        def label(done, blocked=""):
            return retro._gap_label(row("01:00", "fix", "stop", done=done, blocked=blocked))
        self.assertEqual([label("REPORT: ready — #12"), label("REPORT: decision — x"), label("waiting: y"),
                          label("Blocked: no disk"), label("", "a token"), label("went for lunch")],
                         ["stop fix (ready)", "stop fix (decision)", "stop fix (waiting)", "stop fix (blocked)",
                          "stop fix (blocked)", "stop fix (other)"])
        self.assertEqual(retro._gap_label(row("01:00", "fix", "end")), "end fix")

    def test_every_task_and_the_sum(self):
        self.home.write(f"{TASKS}/8/loop.json", task_loop(difficulty="low", task="8"))
        self.home.write(f"{TASKS}/8/status.jsonl", lines(
            row("10:00", "plan", "start", round=1), row("10:10", "plan", "end", outcome="done"),
            row("10:40", "build", "start", round=1), row("11:00", "build", "end", outcome="done"),
            row("11:05", "verify", "start", round=1)))
        self.home.write(f"{TASKS}/9/status.jsonl", lines({"event": "heartbeat", "agent": "9"}))
        r = run("retro.py", "facts", "--project", "o/r")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual([(t["task"], t["idle"]["minutes"], t["idle"]["span_minutes"]) for t in out["tasks"]],
                         [("7", 360.0, 520.0), ("8", 35.0, 65.0), ("9", 0, 0)])
        self.assertEqual(out["idle"]["minutes"], 395.0)
        self.assertEqual(out["idle"]["span_minutes"], 585.0)
        self.assertEqual(out["idle"]["by_event"]["end plan (done)"], 35.0)  # 5 in task 7, 30 in task 8
        self.assertEqual(list(out["idle"]["by_event"])[0], "stop build (decision)")


if __name__ == "__main__":
    unittest.main()
