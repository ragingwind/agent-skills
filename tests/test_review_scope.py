"""Reviews after the first read only what changed (the loop rules of
2026-11-27): `loop.py prompt` scopes the red team from its second round, and
any role after an approval, to the change since the head it last answered
on; a head that only rebases an approved one gets a range-diff check; and the
pair's recheck limit is a setting with the default 2."""
import json
import os
import subprocess
import unittest

from helpers import TempHome, run, task_loop

import config
import loop

G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]


class Repo:
    """A bare origin and a role agent's clone of it, on a feature branch cut from main."""

    def __init__(self, root):
        self.origin, self.path = os.path.join(root, "origin.git"), os.path.join(root, "clone")
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", self.origin], check=True)
        subprocess.run(["git", "clone", "-q", self.origin, self.path], check=True, capture_output=True)
        self.commit("base")
        self.git("push", "-q", "origin", "HEAD:main")
        self.git("switch", "-q", "-c", "feature")

    def git(self, *args):
        return subprocess.run(G + ["-C", self.path, *args], check=True, capture_output=True, text=True).stdout.strip()

    def commit(self, name):
        with open(os.path.join(self.path, name), "w") as f:
            f.write(name + "\n")
        self.git("add", "-A")
        self.git("commit", "-q", "-m", name)
        return self.git("rev-parse", "HEAD")

    def move_main(self, name):
        """Another pull request lands on main, and the feature rebases onto it."""
        self.git("switch", "-q", "main")
        self.commit(name)
        self.git("push", "-q", "origin", "HEAD:main")
        self.git("switch", "-q", "feature")
        self.git("rebase", "-q", "origin/main")
        return self.git("rev-parse", "HEAD")


class Scope(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.task = os.path.join(self.home.root, "task")
        self.home.write("task/loop.json", task_loop(difficulty="mid", lead="sonnet"))
        self.repo = Repo(self.home.root)
        self.n = 0

    def answer(self, role, head, verdict, **meta):
        self.n += 1
        name = f"task/reviews/{role}-1-{self.n}"
        self.home.write(f"{name}.json", {"result": f"- must-fix: x\n\nVerdict: {verdict}"})
        self.home.write(f"{name}.meta.json", {"role": role, "agent": f"{role}-1", "head": head, "ok": True,
                                              "verdict": verdict, "ended": f"2026-11-27T0{self.n}:00:00.000000Z",
                                              **meta})
        return os.path.join(self.home.root, f"{name}.json")

    def prompt(self, step):
        r = run("loop.py", "prompt", "--step", step, "--task-dir", self.task, workdir=self.repo.path)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        with open(out["prompt"], encoding="utf-8") as f:
            return out, f.read()

    def test_the_red_team_reads_only_the_change_since_its_last_round(self):
        first = self.repo.commit("one")
        self.assertIn("Review the diff from origin/main to HEAD.", self.prompt("redteam-review")[1])  # round 1
        answer = self.answer("redteam", first, "changes")
        self.repo.commit("fix")
        self.assertIn(f"Review the diff from {first} to HEAD: only the change since the head of your last answer, "
                      f"which is {answer}.", self.prompt("redteam-review")[1])

    def test_the_pair_reads_only_the_change_after_it_approved(self):
        first = self.repo.commit("one")
        self.answer("pair", first, "changes")
        self.repo.commit("two")
        self.assertIn("from origin/main to HEAD.", self.prompt("review")[1])  # no approval yet: the whole change
        answer = self.answer("pair", first, "approved")
        self.assertIn(f"from {first} to HEAD: only the change since the head of your last answer, which is {answer}.",
                      self.prompt("review")[1])

    def test_a_head_that_only_rebases_an_approval_gets_a_range_diff_check(self):
        first = self.repo.commit("one")
        answer = self.answer("redteam", first, "approved")
        self.repo.move_main("other")
        text = self.prompt("redteam-review")[1]
        self.assertIn(f"Review the diff `git range-diff origin/main..{first} origin/main..HEAD`: HEAD only rebases "
                      f"{first}, the head you last approved (your answer is {answer}), and the range-diff shows each "
                      f"commit of the pull request unchanged. Check that it does, and approve when it does.", text)
        self.repo.commit("more")
        text = self.prompt("redteam-review")[1]
        self.assertIn(f"`git range-diff origin/main..{first} origin/main..HEAD`: the pull request's commits since "
                      f"{first}", text)
        self.assertIn("Read only the commits it shows changed (!), new (>) or dropped (<).", text)
        self.assertNotIn("only rebases", text)

    def test_a_rebase_after_changes_is_no_approval(self):
        first = self.repo.commit("one")
        self.answer("redteam", first, "changes")
        self.repo.move_main("other")
        text = self.prompt("redteam-review")[1]
        self.assertIn("Read only the commits it shows changed", text)
        self.assertNotIn("only rebases", text)  # the must-fix of that answer is still there to check

    def test_the_whole_change_when_nothing_newer_can_be_found(self):
        head = self.repo.commit("one")
        self.answer("redteam", head, "changes")
        self.assertIn("from origin/main to HEAD.", self.prompt("redteam-review")[1])  # the same head again
        self.answer("redteam", "0123456789abcdef0123456789abcdef01234567", "approved")
        self.assertIn("from origin/main to HEAD.", self.prompt("redteam-review")[1])  # a commit no one has

    def test_a_run_without_a_verdict_is_no_answer(self):
        first = self.repo.commit("one")
        self.answer("redteam", first, "approved")
        self.repo.commit("two")
        later = self.answer("redteam", self.repo.git("rev-parse", "HEAD"), "", ok=True)
        with open(later, "w") as f:
            json.dump({"result": "stopped before the end"}, f)
        self.answer("redteam", self.repo.git("rev-parse", "HEAD"), "approved", ok=False)
        self.repo.commit("three")
        self.assertIn(f"from {first} to HEAD:", self.prompt("redteam-review")[1])


def status(*rows):
    return "".join(json.dumps({"stage": "review", "step": s, "event": e, **({"outcome": o} if o else {})}) + "\n"
                   for s, e, o in rows)


class RecheckLimit(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.task = os.path.join(self.home.root, "task")
        self.home.write("task/loop.json", task_loop(difficulty="mid", lead="sonnet"))
        self.repo = Repo(self.home.root)
        head = self.repo.commit("one")
        self.home.write("task/reviews/pair-1-1.json", {"result": "Verdict: changes"})
        self.home.write("task/reviews/pair-1-1.meta.json", {"role": "pair", "agent": "pair-1", "head": head,
                                                           "ok": True, "ended": "2026-11-27T01:00:00Z"})

    def recheck(self):
        r = run("loop.py", "prompt", "--step", "recheck", "--task-dir", self.task, workdir=self.repo.path)
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        with open(out["prompt"], encoding="utf-8") as f:
            return out, f.read()

    def test_past_the_limit_only_a_must_fix_in_the_change_blocks(self):
        rechecks = [("recheck", "start", None), ("recheck", "end", "changes"), ("fix", "end", "done")]
        self.home.write("task/status.jsonl", status(("review", "end", "done"), *rechecks, *rechecks))
        out, text = self.recheck()
        self.assertEqual((out["recheck"], out["recheck_limit"]), (3, 2))
        self.assertIn("This is recheck 3 of this review, past the limit of 2: only a must-fix in this diff gives "
                      "`Verdict: changes`.", text)
        self.assertIn("only the fixes and the clean-up since your last review", text)

    def test_within_the_limit_and_after_an_approval(self):
        self.home.write("task/status.jsonl", status(("review", "end", "done"), ("recheck", "end", "changes"),
                                                    ("recheck", "end", "changes")))  # one end line, corrected
        out, text = self.recheck()
        self.assertEqual(out["recheck"], 2)
        self.assertNotIn("past the limit", text)
        self.home.write("task/status.jsonl", status(("recheck", "end", "changes"), ("fix", "end", "done"),
                                                    ("recheck", "end", "changes"), ("fix", "end", "done"),
                                                    ("recheck", "end", "approved"), ("build", "start", None)))
        self.assertEqual(self.recheck()[0]["recheck"], 1)  # an approval ends that review's rechecks

    def test_the_limit_is_a_setting_the_task_keeps(self):
        cfg = config.merge(config.load(), {"loop": {"roles": {"pair": {"recheck_limit": 3}}}})
        self.assertEqual(loop.validate_loop(cfg["loop"]), [])
        data = task_loop(cfg, difficulty="mid", lead="sonnet")
        self.assertEqual({r: v.get("recheck_limit") for r, v in data["roles"].items()},
                         {"pair": 3, "redteam": None, "qa": None})  # only a role with a recheck step
        self.assertEqual(task_loop(difficulty="mid", lead="sonnet")["roles"]["pair"]["recheck_limit"], 2)
        self.home.write("task/loop.json", data)
        rows = [("recheck", "end", "changes"), ("fix", "end", "done")] * 2
        self.home.write("task/status.jsonl", status(("review", "end", "done"), *rows))
        self.assertNotIn("past the limit", self.recheck()[1])
        for bad in (0, "2", True, 1.5):
            cfg["loop"]["roles"]["pair"]["recheck_limit"] = bad
            self.assertIn("loop: role pair: recheck_limit must be a whole number, 1 or more",
                          loop.validate_loop(cfg["loop"]), bad)

    def test_a_task_from_before_the_setting_gets_the_default(self):
        data = task_loop(difficulty="mid", lead="sonnet")
        del data["roles"]["pair"]["recheck_limit"]
        self.home.write("task/loop.json", data)
        rows = [("recheck", "end", "changes")] + [("fix", "end", "done"), ("recheck", "end", "changes")]
        self.home.write("task/status.jsonl", status(("review", "end", "done"), *rows))
        self.assertEqual(self.recheck()[0]["recheck_limit"], 2)


if __name__ == "__main__":
    unittest.main()
