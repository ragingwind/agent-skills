"""stamp.py (the person's decision of 2026-11-27): the foreman stamps the
tester's answers of a round and copies them into the lead's task folder as
the red team's and QA's answers, with meta the gate accepts."""
import glob
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from helpers import ROOT, SCRIPTS, TempHome, task_loop

import clone
import gate
import stamp

G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
FAKE_SSH = os.path.join(ROOT, "tests", "fake_ssh")
TESTER = ".local/state/agent-foreman/testing/o-r/7"
LEAD = ".local/state/agent-foreman/tasks/o-r/7"
QA = "- ran: make test — exit 0\n\n  ```\n  12 passed\n  ```\n\nVerdict: pass"


class Stamp(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        root = self.home.root
        self.home.write("state/agent-foreman/projects/o-r/project.json", {"repo": "o/r", "machines": {"local": root}})
        tester = os.path.join(root, ".cache/agent-foreman/work/o-r/7/tester")
        subprocess.run(["git", "init", "-q", tester], check=True)
        subprocess.run(G + ["-C", tester, "commit", "-q", "--allow-empty", "-m", "head"], check=True)
        self.head = subprocess.run(["git", "-C", tester, "rev-parse", "HEAD"], capture_output=True,
                                   text=True).stdout.strip()
        self.home.write(f"{TESTER}/reviews/redteam-1.md", "- must-fix: a.py:3 — drops a field\n\nVerdict: changes")
        self.home.write(f"{TESTER}/reviews/redteam-2.md", "- could: a name\n\nVerdict: approved")
        self.home.write(f"{TESTER}/reviews/qa-2.md", QA)
        self.loop = task_loop(difficulty="mid", lead="sonnet")
        self.home.write(f"{LEAD}/loop.json", self.loop)
        self.task = os.path.join(root, LEAD)

    def stamp(self, *args, head=None):
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "stamp.py"), "--project", "o/r", "--task", "7",
                            "--head", head or self.head[:10], *args],
                           capture_output=True, text=True, env={**os.environ, "HOME": self.home.root})
        return r.returncode, (json.loads(r.stdout) if r.returncode == 0 else None), r.stderr

    def reviews(self):
        return sorted(os.path.basename(p) for p in glob.glob(os.path.join(self.task, "reviews", "*")))

    def test_the_last_round_becomes_the_red_team_s_and_qa_s_answers(self):
        code, out, err = self.stamp("--profile", "opus", "--session-id", "s-1")
        self.assertEqual(code, 0, err)
        self.assertEqual((out["round"], out["head"], [(s["role"], s["verdict"]) for s in out["stamped"]]),
                         (2, self.head, [("redteam", "approved"), ("qa", "pass")]))
        self.assertEqual(self.reviews(), ["qa-1-1.json", "qa-1-1.meta.json", "redteam-1-1.json",
                                          "redteam-1-1.meta.json"])
        with open(os.path.join(self.task, "reviews", "qa-1-1.meta.json")) as f:
            meta = json.load(f)
        self.assertEqual({k: meta[k] for k in ("role", "agent", "profile", "model", "head", "ok", "verdict",
                                                "session_id")},
                         {"role": "qa", "agent": "tester", "profile": "opus", "model": "opus", "head": self.head,
                          "ok": True, "verdict": "pass", "session_id": "s-1"})
        self.assertTrue(meta["source"].endswith(f"local:{os.path.join(self.home.root, TESTER)}/reviews/qa-2.md"))

        # The gate reads them as any role's answers.
        pr = {"number": 7, "headRefOid": self.head, "baseRefName": "main", "comments": []}
        checks = gate.template(self.loop)["checks"]
        ctx = {"task_dir": self.task, "cwd": None}
        for spec in [c for c in checks if c["check"] == "verdict" and c.get("at") == "merge"]:
            self.assertTrue(gate.check_verdict(pr, spec, ctx)[0], spec["role"])
        for step in ("redteam-review", "test"):
            self.assertTrue(gate.record_checks(self.loop, step, self.task)["checks"][1]["ok"], step)
        full = {"check": "command", "run": "make test", "full": True,
                "answer": {"role": "qa", "accept": ["pass"], "not_profiles": ["sonnet"], "posted": True}}
        self.assertEqual(gate.check_command(pr, full, ctx), (False, "needs --cwd"))  # not posted yet: it would run
        body = gate.answer_comment("qa", "tester", 7, meta, QA)  # as `loop.py post` posts it
        ok, evidence = gate.check_command(dict(pr, comments=[{"body": body}]), full, ctx)
        self.assertTrue(ok, evidence)
        self.assertIn("reviews/qa-1-1.json", evidence)

    def test_an_earlier_round_never_overwrites(self):
        self.assertEqual(self.stamp("--profile", "opus")[0], 0)
        code, out, err = self.stamp("--profile", "opus", "--round", "1")
        self.assertEqual(code, 0, err)
        self.assertEqual([(s["role"], os.path.basename(s["answer"]), s["verdict"]) for s in out["stamped"]],
                         [("redteam", "redteam-1-2.json", "changes")])  # QA did not run in round 1

    def test_refusals_write_nothing(self):
        cases = [(("--profile", "sonnet"), None, 1, "profile sonnet is the lead's"),
                 (("--profile", "opus"), "0123456", 1, f"the tester's clone is at {self.head}, not at 0123456"),
                 (("--profile", "opus", "--round", "3"), None, 1, "no red team answer for round 3"),
                 (("--profile", "nobody"), None, 3, "nobody is not a profile"),
                 (("--profile", "opus"), "HEAD", 2, "--head takes a commit SHA"),
                 (("--profile", "opus", "--round", "0"), None, 2, "--round takes a round number")]
        for args, head, want, words in cases:
            code, _, err = self.stamp(*args, head=head)
            self.assertEqual(code, want, (args, err))
            self.assertIn(words, err)
        self.home.write(f"{TESTER}/reviews/qa-2.md", "- ran: make test — exit 0")
        code, _, err = self.stamp("--profile", "opus")
        self.assertEqual(code, 1)
        self.assertIn("qa-2.md ends with no Verdict line", err)
        self.assertEqual(self.reviews(), [])
        os.rename(self.task, self.task + "-gone")
        self.home.write(f"{TESTER}/reviews/qa-2.md", QA)
        code, _, err = self.stamp("--profile", "opus")
        self.assertEqual(code, 1)
        self.assertIn("no task folder at", err)

    def test_across_machines(self):
        env = {"HOME": self.home.root, "PATH": FAKE_SSH + os.pathsep + os.environ["PATH"]}
        saved = {"m1": {"target": "m1.example"}, "m2": {"target": "m2.example"}}
        with mock.patch.dict(os.environ, env):
            found = clone.on_machine("m1", {"op": "read", "key": "o-r", "task": "7", "round": None}, saved,
                                     module=stamp)
            self.assertEqual((found["round"], found["head"], sorted(found["answers"])), (2, self.head,
                                                                                          ["qa", "redteam"]))
            answers, why = stamp.stamped(found, self.head[:7], "opus", "opus", None, "m1")
            self.assertIsNone(why)
            done = clone.on_machine("m2", {"op": "write", "key": "o-r", "task": "7", "answers": answers}, saved,
                                    module=stamp)
        self.assertEqual([os.path.basename(p) for p in done["written"]], ["redteam-1-1.json", "qa-1-1.json"])


if __name__ == "__main__":
    unittest.main()
