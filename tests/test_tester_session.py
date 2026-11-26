"""The tester session (the person's decision of 2026-11-27): one tester per
task runs the red team and QA, on a profile one tier above the lead and
never the lead's, with its own folder outside tasks/ that `status.py read`
reports as the task's testing session."""
import json
import os
import subprocess
import sys
import time
import unittest
from unittest import mock

from helpers import ROOT, SCRIPTS, TempHome, run, task_loop

import config
import loop
import status

FAKE_SSH = os.path.join(ROOT, "tests", "fake_ssh")


def line(minutes_ago, now, **fields):
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - minutes_ago * 60))
    return json.dumps({"time": stamp, **fields}) + "\n"


class Profiles(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.cfg = config.load()

    def test_one_tier_above_the_lead_and_never_the_lead_s(self):
        for difficulty, lead, want in (("low", "haiku", ["sonnet", "opus"]), ("mid", "sonnet", ["opus"]),
                                       ("high", "opus", ["sonnet"])):
            self.assertEqual(loop.role_profiles(self.cfg, difficulty, lead)["tester"], want, difficulty)
            r = run("config.py", "tier", "--difficulty", difficulty, "--role", "tester", "--lead", lead)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual(json.loads(r.stdout)["profiles"], want)
        r = run("config.py", "tier", "--difficulty", "high", "--role", "tester", "--lead", "sonnet")
        self.assertEqual(json.loads(r.stdout), {"tier": "high", "profiles": ["opus"], "pick": "opus"})
        self.assertEqual(run("config.py", "tier", "--difficulty", "mid", "--role", "nobody").returncode, 2)

    def test_loop_json_keeps_them(self):
        profiles = loop.role_profiles(self.cfg, "mid", "sonnet")
        data = loop.as_data(self.cfg, "7", "mid", False, {n: ("kit", n) for n in loop.KIT},
                            lambda src, v: "foreman-kit:" + v, "o/r", "main", "sonnet", profiles)
        self.assertEqual(data["tester"], {"profiles": ["opus"]})
        self.assertNotIn("tester", data["roles"])  # no step of its own: it runs the check loop's
        self.assertEqual(task_loop(difficulty="mid")["tester"], {"profiles": []})  # profiles from the caller


class Folder(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.env = {"HOME": self.home.root}
        self.home.write("state/agent-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": "/src/r"}})

    def test_dir_and_path(self):
        for command, tail in (("dir", ""), ("path", "/status.jsonl")):
            r = run("status.py", command, "--project", "o/r", "--task", "7", "--testing")
            self.assertEqual(r.stdout.strip(), "~/.local/state/agent-foreman/testing/o-r/7" + tail)
            r = run("status.py", command, "--project", "o/r", "--task", "7")
            self.assertEqual(r.stdout.strip(), "~/.local/state/agent-foreman/tasks/o-r/7" + tail)

    def write_sessions(self):
        now = time.time()
        self.home.write(".local/state/agent-foreman/tasks/o-r/7/status.jsonl",
                        line(50, now, stage="finalize", step="finalize", event="end", outcome="done", to="stop"))
        self.home.write(".local/state/agent-foreman/testing/o-r/7/status.jsonl",
                        line(2, now, stage="test", step="redteam-review", event="start", round=1)
                        + line(1, now, event="heartbeat", agent="tester-7"))
        self.home.write(".local/state/agent-foreman/testing/o-r/8/status.jsonl",
                        line(90, now, stage="test", step="test", event="stop",
                             done="REPORT: tested abc1234 — redteam approved, qa pass, must-fix: none"))

    def test_read_reports_the_testing_session(self):
        self.write_sessions()
        r = run("status.py", "read", "--project", "o/r", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual(list(out["tasks"]), ["7"])  # a tester folder is no second copy of the task
        self.assertEqual({t: (v["machine"], v["step"], v["last_beat_agent"], v["stopped"], v["stalled"])
                          for t, v in out["testing"].items()},
                         {"7": ("local", "redteam-review", "tester-7", False, False),
                          "8": ("local", "test", None, True, False)})

    def test_a_remote_machine_runs_the_reader_file(self):
        self.write_sessions()
        env = {"HOME": self.home.root, "PATH": FAKE_SSH + os.pathsep + os.environ["PATH"]}
        with mock.patch.dict(os.environ, env):
            found = status.read_machine("m1", "o/r", {"m1": {"target": "m1.example"}})
        self.assertEqual((sorted(found["tasks"]), sorted(found["testing"])), (["7"], ["7", "8"]))
        self.assertGreater(found["free_gb"], 0)
        with self.assertRaises(ValueError):
            status.read_machine("ghost", "o/r", {})

    def test_the_reader_alone(self):
        reader = os.path.join(SCRIPTS, "status_reader.py")
        r = subprocess.run([sys.executable, reader, "/nowhere/tasks", "/nowhere/testing", "5"], capture_output=True,
                           text=True)
        self.assertEqual((r.returncode, json.loads(r.stdout)["tasks"], json.loads(r.stdout)["testing"]), (0, {}, {}))
        self.home.write("t/7/status.jsonl", "".join(f"{n}\n" for n in range(10)))
        r = subprocess.run([sys.executable, reader, os.path.join(self.home.root, "t"), "/nowhere", "3"],
                           capture_output=True, text=True)
        self.assertEqual(json.loads(r.stdout)["tasks"], {"7": ["7", "8", "9"]})
        for bad in ([], ["a", "b"], ["a", "b", "0"], ["a", "b", "x"]):
            self.assertEqual(subprocess.run([sys.executable, reader, *bad], capture_output=True).returncode, 2, bad)


if __name__ == "__main__":
    unittest.main()
