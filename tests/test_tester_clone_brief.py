"""The tester's clone and brief (the person's decision of 2026-11-27): the
clone starts at the pull request's head, fetched from origin on any machine,
and the brief gives the tester the check loop it runs alone, with the guide
tester.md in the bundle."""
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from helpers import ROOT, SCRIPTS, TempHome, run

import bundle
import clone
import config
import loop

G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
FAKE_SSH = os.path.join(ROOT, "tests", "fake_ssh")
PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")


def git(cwd, *args):
    return subprocess.run(G + ["-C", cwd, *args], check=True, capture_output=True, text=True).stdout.strip()


class PullClone(unittest.TestCase):
    """GitHub keeps a pull request's head at refs/pull/<N>/head; the bare origin here does too."""

    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        root = self.home.root
        self.origin, self.checkout, lead = (os.path.join(root, n) for n in ("origin.git", "checkout", "lead"))
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        subprocess.run(["git", "clone", "-q", self.origin, lead], check=True, capture_output=True)
        git(lead, "commit", "-q", "--allow-empty", "-m", "base")
        git(lead, "push", "-q", "origin", "HEAD:main")
        subprocess.run(["git", "clone", "-q", self.origin, self.checkout], check=True, capture_output=True)
        git(lead, "commit", "-q", "--allow-empty", "-m", "first round")
        self.first = git(lead, "rev-parse", "HEAD")
        git(lead, "commit", "-q", "--allow-empty", "-m", "second round")
        self.head = git(lead, "rev-parse", "HEAD")
        git(lead, "push", "-q", "origin", "HEAD:refs/pull/7/head")  # no branch: only the pull request's ref
        self.env = {"HOME": root}

    def make(self, *args):
        r = subprocess.run([sys.executable, os.path.join(SCRIPTS, "clone.py"), "make", "--project", "o/r", "--task",
                            "7", "--agent", "tester", "--from", self.checkout, "--no-push", *args],
                           capture_output=True, text=True, env={**os.environ, **self.env})
        return r.returncode, (json.loads(r.stdout) if r.stdout.strip() else {}), r.stderr

    def test_the_tester_starts_at_the_pull_request_s_head(self):
        self.assertNotEqual(subprocess.run(["git", "-C", self.checkout, "cat-file", "-e", self.head],
                                           capture_output=True).returncode, 0)  # the checkout never saw it
        code, out, err = self.make("--pr", "7")
        self.assertEqual(code, 0, err)
        self.assertEqual((out["status"], out["head"], out["push"]), ("made", self.head, False))
        with open(os.path.join(out["path"], ".git", "agent-foreman.json")) as f:
            self.assertEqual(json.load(f)["pr"], 7)
        code, out, err = self.make("--pr", "7", "--ref", self.first, "--fresh")  # the head the foreman names
        self.assertEqual((code, out.get("head")), (0, self.first), err)

    def test_bad_arguments(self):
        for args, words in ((["--pr", "0"], "--pr takes a pull request number"),
                            ([], "make needs --agent, and --ref or --pr")):
            code, _, err = self.make(*args)
            self.assertEqual(code, 2)
            self.assertIn(words, err)
        code, out, _ = self.make("--pr", "8")  # no such pull request
        self.assertEqual(code, 1)
        self.assertIn("pull/8/head", out["error"])

    def test_on_another_machine(self):
        request = {"op": "make", "key": "o-r", "task": "7", "agent": "tester", "source": self.checkout,
                   "ref": None, "no_push": True, "pr": 7}
        env = {"HOME": self.home.root, "PATH": FAKE_SSH + os.pathsep + os.environ["PATH"]}
        with mock.patch.dict(os.environ, env):
            out = clone.on_machine("m3", request, saved={"m3": {"target": "m3.example"}})
        self.assertEqual((out["status"], out["head"]), ("made", self.head), out)


class Brief(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.cfg = config.merge(config.load(), {"tests": {"full": "make test"}})
        self.resolved = {n: ("kit", n) for n in loop.KIT}

    def brief(self, trivial=False):
        profiles = loop.role_profiles(self.cfg, "mid", "sonnet")
        return loop.render(self.cfg, "7", "mid", trivial, self.resolved, profiles, lambda s, v: "foreman-kit:" + v,
                           "check", tester=True)

    def test_the_check_loop_as_the_tester_runs_it(self):
        text = self.brief()
        self.assertTrue(text.startswith("# Testing session for 7 (difficulty mid)\n"), text)
        self.assertIn("a `stop` line with your REPORT at the end of each round", text)
        self.assertIn("| redteam-review | redteam | ", text)
        self.assertIn("| foreman-kit:full, foreman-kit:cross-check |", text)
        self.assertIn("**Profile**: opus; fallback: -; never the lead's.", text)
        self.assertIn("**Full tests** (step test): python3 '<bundle>/scripts/fulltest.py' --min-free-gb 20 -- "
                      "'make test'.", text)
        self.assertIn("**Verdicts that pass**: redteam: `Verdict: approved`; qa: `Verdict: pass`.", text)
        self.assertIn("as tester.md says: the red team first, and QA only after the red team approves the same head",
                      text)
        self.assertNotIn("loop.py prompt", text)  # that is how the foreman starts a role, not the tester
        self.assertTrue(self.brief(trivial=True).startswith("# Testing session for 7 (difficulty mid, trivial)"))
        self.assertIn("# Verification session for 7", loop.render(
            self.cfg, "7", "mid", False, self.resolved, {}, lambda s, v: v, "check"))  # the foreman's, unchanged

    def test_only_with_the_check_loop(self):
        for args in (["render", "--tester"], ["render", "--loop", "check", "--tester", "--json"],
                     ["prompt", "--step", "test", "--tester"]):
            r = run("loop.py", *args)
            self.assertEqual(r.returncode, 2, args)
            self.assertIn("--tester goes with render --loop check, without --json", r.stderr)

    def test_the_guide_ships_in_the_bundle(self):
        files = bundle.contents(config.load(), {})
        with open(os.path.join(PLUGIN, "tester.md"), "rb") as f:
            self.assertEqual(files["tester.md"], f.read())
        guide = " ".join(files["tester.md"].decode().split())
        for words in ("git fetch origin pull/<N>/head", "reviews/redteam-<k>.md", "reviews/qa-<k>.md",
                      "**QA**, only when the red team approved this head",
                      "`- ran: <command> — exit <code>` item, the command exactly as the brief names it and nothing "
                      "after the exit code",
                      "REPORT: tested <head> — redteam <verdict>, qa <verdict, or not run>, must-fix:",
                      "Never write to the lead or into the lead's task folder.",
                      "status.py note --stage test --step redteam-review --event start --round <k>"):
            self.assertIn(words, guide)
        usage = run("status.py", "--help").stdout
        for flag in ("--stage", "--step", "--event", "--round", "--done"):
            self.assertIn(flag, usage)

if __name__ == "__main__":
    unittest.main()
