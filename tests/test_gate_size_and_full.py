"""The gate's size check and its full tests (the loop rules of 2026-11-27):
the size budget counts added lines without lockfiles and generated files,
and blocks in a new task; the full test that QA passed at the head is not
run again, and its record is no easier to forge than QA's verdict."""
import contextlib
import io
import json
import os
import subprocess
import unittest
from unittest import mock

from helpers import TempHome, task_loop
from test_gate import BASE, HEAD, check, pr

import config
import gate

G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
PASSED = "- ran: false — exit 0\n\n  ```\n  0 failed\n  ```\n\nVerdict: pass"


def changed(*pairs):
    """The pull request's files, as GitHub lists them, from (path, added lines)."""
    return [{"filename": path, "status": "added", "additions": n, "patch": ""} for path, n in pairs]


class Repo:
    """A bare origin and a clone; main's commit marks gen/ and *.pb.go generated."""

    def __init__(self, root):
        self.root, self.origin, self.path = root, os.path.join(root, "origin.git"), os.path.join(root, "clone")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        subprocess.run(["git", "clone", "-q", self.origin, self.path], check=True, capture_output=True)
        self.base = self.commit(".gitattributes", "gen/** linguist-generated\n*.pb.go linguist-generated=true\n")
        self.git("push", "-q", "origin", "HEAD:main")

    def git(self, *args, cwd=None):
        return subprocess.run(G + ["-C", cwd or self.path, *args], check=True, capture_output=True,
                              text=True).stdout.strip()

    def commit(self, name, text, cwd=None):
        with open(os.path.join(cwd or self.path, name), "w") as f:
            f.write(text)
        self.git("add", "-A", cwd=cwd)
        self.git("commit", "-q", "-m", name, cwd=cwd)
        return self.git("rev-parse", "HEAD", cwd=cwd)


class Size(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)

    def size(self, *pairs, cwd=None, base=BASE):
        data = pr(additions=sum(n for _, n in pairs), deletions=900, baseRefOid=base, files=changed(*pairs))
        return check("size", data, max_lines=400, cwd=cwd)

    def test_lockfiles_and_deletions_do_not_count(self):
        ok, evidence = self.size(("src/a.py", 300), ("web/package-lock.json", 500), ("Cargo.lock", 150),
                                 ("go.sum", 50))
        self.assertTrue(ok, evidence)
        self.assertEqual(evidence, "300 added lines (limit 400), without 3 lockfile(s) and generated file(s); the "
                                   "base's linguist-generated files unknown (no --cwd or no base commit), so all of "
                                   "them counted")
        self.assertTrue(self.size(("src/a.py", 400))[0])
        self.assertFalse(self.size(("src/a.py", 401))[0])

    def test_files_the_base_marks_generated_do_not_count(self):
        repo = Repo(self.home.root)
        ok, evidence = self.size(("src/a.py", 100), ("gen/schema.py", 900), ("api/x.pb.go", 700), cwd=repo.path,
                                 base=repo.base)
        self.assertEqual((ok, evidence), (True, "100 added lines (limit 400), without 2 lockfile(s) and generated "
                                                "file(s)"))

    def test_the_change_cannot_mark_its_own_code_generated(self):
        repo = Repo(self.home.root)
        repo.commit(".gitattributes", "src/** linguist-generated\n")
        with open(os.path.join(repo.path, ".git", "info", "attributes"), "w") as f:
            f.write("lib/** linguist-generated\n")
        with open(os.path.join(self.home.root, "mine"), "w") as f:
            f.write("app/** linguist-generated\n")
        repo.git("config", "core.attributesFile", os.path.join(self.home.root, "mine"))
        ok, evidence = self.size(("src/a.py", 200), ("lib/b.py", 150), ("app/c.py", 100), (".gitattributes", 1),
                                 cwd=repo.path, base=repo.base)
        self.assertEqual((ok, evidence.split(",")[0]), (False, "451 added lines (limit 400)"))

    def test_a_base_the_clone_lacks_comes_from_origin(self):
        repo = Repo(self.home.root)
        other = os.path.join(self.home.root, "other")
        subprocess.run(["git", "clone", "-q", repo.origin, other], check=True, capture_output=True)
        base = repo.commit(".gitattributes", "big/** linguist-generated\n", cwd=other)
        repo.git("push", "-q", "origin", "HEAD:main", cwd=other)
        self.assertNotEqual(subprocess.run(["git", "-C", repo.path, "cat-file", "-e", base],
                                           capture_output=True).returncode, 0)
        ok, evidence = self.size(("big/data.txt", 900), ("src/a.py", 10), cwd=repo.path, base=base)
        self.assertEqual((ok, evidence.split(",")[0]), (True, "10 added lines (limit 400)"))
        ok, evidence = self.size(("big/data.txt", 900), cwd=repo.path, base="0" * 40)  # a commit no one has
        self.assertEqual((ok, evidence.split(",")[0]), (False, "900 added lines (limit 400)"))
        self.assertIn("linguist-generated files unknown", evidence)

    def test_the_budget_and_its_severity_come_from_the_task_s_loop(self):
        size = [c for c in gate.template(task_loop(difficulty="mid"))["checks"] if c["check"] == "size"]
        self.assertEqual(size, [{"check": "size", "max_lines": 400, "severity": "block"}])
        report = gate.evaluate(pr(additions=401, files=changed(("src/a.py", 401))),
                               {"repo": "o/r", "pr": 7, "checks": size})
        self.assertEqual(report["blocked"], ["size"])  # a new task's gate blocks over the budget
        smaller = task_loop(config.merge(config.load(), {"difficulty": {"lines": 250}}), difficulty="mid")
        self.assertEqual([c["max_lines"] for c in gate.template(smaller)["checks"] if c["check"] == "size"], [250])
        older = task_loop(difficulty="mid")
        del older["size_severity"]  # a loop.json from before the rule
        self.assertEqual([c["severity"] for c in gate.template(older)["checks"] if c["check"] == "size"], ["warn"])


class FullTests(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.task = os.path.join(self.home.root, "task")
        # "false" exits 1: a check that passes did not run it.
        self.spec = {"check": "command", "run": "false", "full": True, "min_free_gb": 0,
                     "answer": {"role": "qa", "accept": ["pass"], "not_profiles": ["opus"]}}

    def qa(self, text, head=HEAD, profile="sonnet", ok=True):
        self.home.write("task/reviews/qa-1-1.json", {"result": text})
        meta = {"role": "qa", "agent": "qa-1", "profile": profile, "model": "m", "head": head, "ok": ok,
                "ended": "2026-11-27T01:00:00Z", "session_id": "s"}
        self.home.write("task/reviews/qa-1-1.meta.json", meta)
        return meta

    def command(self, spec=None, cwd=None, task_dir="task", **over):
        ctx = {"cwd": cwd or self.home.root, "task_dir": task_dir and os.path.join(self.home.root, task_dir)}
        return gate.check_command(pr(**over), spec or self.spec, ctx)

    def test_qa_s_passing_run_at_the_head_is_not_run_again(self):
        self.qa(PASSED)
        self.assertEqual(self.command(), (True, f"not run again: qa-1 ran it at {HEAD[:7]} with exit 0, on sonnet, "
                                                f"and its answer reviews/qa-1-1.json says Verdict: pass"))
        self.qa("- ran: `false` — exit 0\n\nVerdict: pass")
        self.assertTrue(self.command()[0])

    def test_anything_less_runs_it(self):
        for text, meta in ((PASSED.replace("Verdict: pass", "Verdict: fail"), {}),
                           (PASSED.replace("exit 0", "exit 1"), {}),
                           (PASSED.replace("ran: false", "ran: make test"), {}),  # another command
                           ("- not run: false — disk under the floor\n\nVerdict: pass", {}),
                           (PASSED, {"head": BASE}),
                           (PASSED, {"profile": "opus"}),  # the lead's
                           (PASSED, {"ok": False})):  # a run that did not finish
            self.qa(text, **meta)
            ok, evidence = self.command()
            self.assertEqual((ok, evidence.split(":")[0]), (False, "exit 1"), (text, meta))
        self.qa(PASSED)
        self.assertFalse(self.command({k: v for k, v in self.spec.items() if k != "answer"})[0])
        self.assertFalse(self.command({k: v for k, v in self.spec.items() if k != "full"})[0])
        self.assertFalse(self.command(task_dir=None)[0])

    def test_only_at_the_head_itself(self):
        repo = Repo(self.home.root)
        repo.git("switch", "-q", "-c", "feature")
        tested = repo.commit("a.txt", "a\n")
        repo.git("switch", "-q", "main")
        repo.commit("b.txt", "b\n")
        repo.git("push", "-q", "origin", "HEAD:main")
        repo.git("switch", "-q", "feature")
        repo.git("rebase", "-q", "origin/main")
        head = repo.git("rev-parse", "HEAD")
        self.qa(PASSED, head=tested)
        ctx = {"cwd": repo.path, "task_dir": self.task}
        self.assertTrue(gate.check_verdict(pr(headRefOid=head), {"role": "qa", "accept": ["pass"]}, ctx)[0])
        self.assertFalse(self.command(cwd=repo.path, headRefOid=head)[0])  # the tests ran on another tree

    def test_posted_when_qa_s_verdict_must_be(self):
        spec = dict(self.spec, answer=dict(self.spec["answer"], posted=True))
        body = gate.answer_comment("qa", "qa-1", 7, self.qa(PASSED), PASSED)
        self.assertFalse(self.command(spec)[0])
        self.assertFalse(self.command(spec, comments=[{"body": body.replace("Verdict: pass", "Verdict: fail")}])[0])
        self.assertTrue(self.command(spec, comments=[{"body": body}])[0])
        g = self.home.write("gate.json", {"repo": "o/r", "pr": 7, "checks": [spec]})
        asked = []

        def fetch(repo, number, comments=False):
            asked.append(comments)
            return pr(comments=[{"body": body}])
        with mock.patch.object(gate, "fetch", fetch), contextlib.redirect_stdout(io.StringIO()) as out:
            code = gate.main(["run", g, "--task-dir", self.task, "--cwd", self.home.root])
        self.assertEqual((code, asked), (0, [True]), out.getvalue())

    def test_the_template_gives_it_qa_s_terms(self):
        for post in (False, True):
            cfg = config.merge(config.load(), {"tests": {"full": "make test"}, "post_answers": post})
            checks = gate.template(task_loop(cfg, difficulty="mid", lead="sonnet"))["checks"]
            qa = [c for c in checks if c["check"] == "verdict" and c["role"] == "qa"][0]
            full = [c for c in checks if c["check"] == "command"][0]
            self.assertEqual(full["answer"], {k: v for k, v in qa.items() if k not in ("check", "at")})
            self.assertEqual(full["answer"]["not_profiles"], ["sonnet"])
            self.assertEqual(full["answer"].get("posted"), post or None)
        for bad in ({"check": "command", "run": "x", "answer": {"role": "qa"}},
                    {"check": "command", "run": "x", "full": True, "answer": {"accept": ["pass"]}},
                    {"check": "command", "run": "x", "full": True, "answer": "qa"}):
            self.assertEqual(gate.validate_gate({"repo": "o/r", "pr": 7, "checks": [bad]}),
                             ["gate: command check 1 takes an answer only with full, and it needs a role"])
        self.assertEqual(gate.validate_gate({"repo": "o/r", "pr": 7, "checks": [self.spec]}), [])


if __name__ == "__main__":
    unittest.main()
