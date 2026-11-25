import json
import os
import shutil
import stat
import subprocess
import unittest

from helpers import TempHome, run, task_loop

import config
import gate

HEAD = "a1b2c3d4e5f6a7b8c9d0a1b2c3d4e5f6a7b8c9d0"
BASE = "b0b1b2b3b4b5b6b7b8b9b0b1b2b3b4b5b6b7b8b9"


def pr(**over):
    data = {"number": 7, "state": "OPEN", "isDraft": False, "baseRefName": "main", "baseRefOid": BASE, "headRefOid": HEAD,
            "additions": 30, "deletions": 5, "behind_by": 0,
            "statusCheckRollup": [{"name": "ci", "status": "COMPLETED", "conclusion": "SUCCESS"}],
            "files": [{"filename": "src/x.py", "status": "modified", "patch": "@@\n-a = 1\n+a = 2"}]}
    data.update(over)
    return data


PLAN = ("# Plan: x\n\n## Work breakdown\n\n| id | goal | done when | files | test | status | commit |\n"
        "|---|---|---|---|---|---|---|\n| W1 | a | b | c | test-first | done | abc1234 |\n\n## Decisions\n- none\n")
HANDOFF = "# Handoff: x\n\n## Purpose\na\n\n## Decisions\nb\n\n## Tests\nc\n\n## Not touched\nd\n\n## Follow-ups\ne\n"
SCENARIO = ("# Scenario: x\n\n### 1 · run it\nWhy.\n\n**Expect** — `ok`\n\n**Do**\n\n```bash\nrun\n```\n\n"
            "**Agent**\n\n```\nok\n```\n\n## Closing\nVerdict: pass\nNothing left up.\n")


def task_folder(home, answers=(), plan=PLAN, handoff=HANDOFF, scenario=SCENARIO):
    """A task folder with the records and one answer per (agent, role, profile, verdict, head, ended[, ok])."""
    root = os.path.join(home.root, "task")
    for name, text in (("plan.md", plan), ("handoff.md", handoff), ("scenario.md", scenario)):
        if text is not None:
            home.write(f"task/{name}", text)
    for agent, role, profile, verdict, head, ended, *ok in answers:
        home.write(f"task/reviews/{agent}-{ended}.json", {"result": f"must-fix: none\nVerdict: {verdict}"})
        home.write(f"task/reviews/{agent}-{ended}.meta.json", {"role": role, "agent": agent, "profile": profile,
                                                              "head": head, "ended": ended, "ok": ok[0] if ok else True})
    return root


def status_lines(home, *steps):
    """status.jsonl with a heartbeat and an `end` line for each step."""
    rows = [{"event": "heartbeat", "agent": "7"}] + [{"stage": s, "step": s, "event": "end"} for s in steps]
    home.write("task/status.jsonl", "".join(json.dumps(r) + "\n" for r in rows))


def check(name, data, **spec):
    ctx = {"cwd": spec.pop("cwd", None), "task_dir": spec.pop("task_dir", None)}
    return gate.CHECKS[name](data, {"check": name, **spec}, ctx)


class Checks(unittest.TestCase):
    def test_open_ci_fresh_ready(self):
        self.assertTrue(check("pr-open", pr())[0])
        self.assertFalse(check("pr-open", pr(state="MERGED"))[0])
        self.assertTrue(check("ci", pr())[0])
        pending = [{"name": "e2e", "status": "IN_PROGRESS", "conclusion": None}]
        self.assertFalse(check("ci", pr(statusCheckRollup=pending))[0])
        self.assertFalse(check("ci", pr(statusCheckRollup=[{"context": "lint", "state": "FAILURE"}]))[0])
        self.assertFalse(check("base-fresh", pr(behind_by=2))[0])
        self.assertFalse(check("ready", pr(isDraft=True))[0])

    def test_last_verdict_line(self):
        self.assertEqual(gate.last_verdict("x\nVerdict: approved"), "approved")
        self.assertEqual(gate.last_verdict("**Verdict: Changes**\n"), "changes")
        self.assertEqual(gate.last_verdict("`Verdict: pass.`"), "pass")
        self.assertEqual(gate.last_verdict("Verdict: approved\nmore\nVerdict: changes"), "changes")
        self.assertEqual(gate.last_verdict("The verdict: approved\nVerdict: approved because x"), "")
        self.assertEqual(gate.last_verdict(None), "")

    def test_tests_weakened(self):
        files = [{"filename": "tests/test_old.py", "status": "removed", "patch": ""},
                 {"filename": ".github/workflows/ci.yml", "status": "modified", "patch": "-  run: make e2e\n+  run: true"},
                 {"filename": "tests/test_x.py", "status": "modified", "patch": "+@pytest.mark.skip(reason='later')"},
                 {"filename": "pyproject.toml", "status": "modified", "patch": "-fail_under = 90\n+fail_under = 60"}]
        ok, evidence = check("tests-weakened", pr(files=files))
        self.assertFalse(ok)
        for words in ("removed test file tests/test_old.py", "edited CI file", "skip or focus marker", "coverage threshold"):
            self.assertIn(words, evidence)
        ok, evidence = check("tests-weakened", pr(files=files), allow=["removed-test", "ci-edit", "skip-marker", "coverage"])
        self.assertTrue(ok)
        self.assertTrue(check("tests-weakened", pr())[0])

    def test_agent_instructions_count_as_weakening(self):
        files = [{"filename": f, "status": "modified", "patch": ""} for f in
                 (".claude/skills/review/SKILL.md", "CLAUDE.md", "pkg/AGENTS.md", ".agents/skills/x/SKILL.md",
                  ".codex/hooks.json", "docs/claude.txt", "docs/agents.md")]
        ok, evidence = check("tests-weakened", pr(files=files))
        self.assertFalse(ok)
        self.assertEqual(evidence.count("edited agent instructions"), 5, evidence)
        self.assertTrue(check("tests-weakened", pr(files=files), allow=["agent-files"])[0])

    def test_size_ready_and_skips(self):
        big = pr(additions=500, deletions=20)
        self.assertFalse(check("size", big, max_lines=400)[0])
        report = gate.evaluate(big, {"repo": "o/r", "pr": 7, "checks": [{"check": "size", "max_lines": 400, "severity": "warn"},
                                                                         {"check": "ci"}]})
        self.assertTrue(report["pass"])
        draft = {"repo": "o/r", "pr": 7, "checks": [{"check": "ready"}, {"check": "ci", "at": "merge"}]}
        self.assertEqual(gate.evaluate(pr(isDraft=True), draft)["blocked"], ["ready"])
        self.assertEqual(gate.evaluate(pr(isDraft=True), draft, before_ready=True)["checks"], [])
        verdicts = {"repo": "o/r", "pr": 7, "checks": [{"check": "verdict", "role": "redteam"},
                                                       {"check": "verdict", "role": "qa"}]}
        report = gate.evaluate(pr(), verdicts, skip={"verdict:qa"})
        self.assertEqual([c["check"] for c in report["checks"]], ["verdict:redteam"])  # only the named role is left out

    def test_validate(self):
        self.assertEqual(gate.validate_gate({"repo": "o/r", "pr": 1, "checks": [{"check": "ci"}]}), [])
        self.assertEqual(gate.validate_gate({"repo": "o/r", "pr": None, "checks": [{"check": "ci"}]}), [])
        p = gate.validate_gate({"repo": "o/r", "pr": "1", "checks": [{"check": "magic"}, {"check": "verdict"},
                                                                     {"check": "command"}, {"check": "loop-file"},
                                                                     {"check": "ci", "severity": "x"}]})
        for words in ("pr must be a number", "'magic'", "needs a role", "needs run", "needs sha256", "severity must be"):
            self.assertTrue(any(words in x for x in p), words)
        self.assertEqual(gate.validate_gate({"repo": "bad"}), ["gate: repo must look like owner/name"])
        for old in ("sections", "scenario"):  # the pull-request comment checks are gone
            self.assertIn(f"'{old}'", gate.validate_gate({"repo": "o/r", "checks": [{"check": old}]})[0])


class CommandChecks(unittest.TestCase):
    def test_a_command_gets_the_task_in_its_environment(self):
        script = ('test "$AF_REPO" = o/r && test "$AF_PR" = 7 && test "$AF_TASK" = 12 && test "$AF_BASE" = main '
                  f'&& test "$AF_HEAD" = {HEAD} && test "$AF_TASK_DIR" = /t')
        g = {"repo": "o/r", "pr": 7, "task": "12", "checks": [{"check": "command", "name": "env", "run": script}]}
        self.assertTrue(gate.evaluate(pr(), g, cwd=os.getcwd(), task_dir="/t")["pass"])
        self.assertFalse(gate.evaluate(pr(baseRefName="dev"), g, cwd=os.getcwd(), task_dir="/t")["pass"])
        self.assertEqual(gate.evaluate(pr(), g)["checks"][0]["evidence"], "needs --cwd")

    def test_the_full_tests_run_one_at_a_time_and_not_under_the_disk_floor(self):
        home = TempHome()
        self.addCleanup(home.close)
        g = {"repo": "o/r", "pr": 7, "checks": [{"check": "command", "run": "true", "full": True, "min_free_gb": 1e9}]}
        report = gate.evaluate(pr(), g, cwd=home.root)
        self.assertEqual((report["pass"], report["blocked"]), (False, ["command"]))
        self.assertIn("exit 75: fulltest.py: not run:", report["checks"][0]["evidence"])
        g["checks"][0]["min_free_gb"] = 0
        self.assertTrue(gate.evaluate(pr(), g, cwd=home.root)["pass"])
        self.assertTrue(os.path.exists(os.path.join(home.root, "cache", "agent-foreman", "locks", "full-test.lock")))

    def test_named_commands_report_and_skip_apart(self):
        g = {"repo": "o/r", "pr": 7, "checks": [{"check": "command", "run": "true"},
                                                {"check": "command", "name": "closing-keyword", "run": "false"},
                                                {"check": "command", "name": "done-label", "run": "false",
                                                 "severity": "warn"}]}
        report = gate.evaluate(pr(), g, cwd=os.getcwd())
        self.assertEqual([c["check"] for c in report["checks"]], ["command", "closing-keyword", "done-label"])
        self.assertEqual(report["blocked"], ["closing-keyword"])  # a warn check reports without blocking
        report = gate.evaluate(pr(), g, cwd=os.getcwd(), skip={"closing-keyword"})
        self.assertEqual(([c["check"] for c in report["checks"]], report["pass"]), (["command", "done-label"], True))
        report = gate.evaluate(pr(), g, cwd=os.getcwd(), skip={"command"})  # the full tests alone
        self.assertEqual([c["check"] for c in report["checks"]], ["closing-keyword", "done-label"])

    def test_project_checks(self):
        good = [{"check": "command", "name": "closing-keyword", "run": "x", "at": "merge"},
                {"check": "command", "name": "done-label", "run": "y", "severity": "warn"}]
        self.assertEqual(gate.project_check_problems(good), [])
        self.assertEqual(gate.project_check_problems([]), [])
        self.assertEqual(gate.validate_gate({"repo": "o/r", "checks": good}), [])
        self.assertEqual(gate.project_check_problems([{"check": "command", "name": "a", "from_base": "s/x.sh"}]), [])
        bad = [({"check": "command"}, "must be a list"),
               ([{"check": "command", "name": ["a"], "run": "x"}], "lower-case letters"),
               ([{"check": "command", "name": "a", "run": "x", "from_base": "s.sh"}], "one of them"),
               ([{"check": "command", "name": "a", "from_base": "../up.sh"}], "a path inside the repository"),
               ([{"check": "command", "name": "a", "from_base": "/etc/x"}], "a path inside the repository"),
               (["x"], "must be an object"),
               ([{"check": "ci", "name": "a", "run": "x"}], "must be a command check"),
               ([{"check": "command", "run": "x"}], "needs a name"),
               ([{"check": "command", "name": "a", "run": " "}], "needs run"),
               ([{"check": "command", "name": "a"}], "needs run"),
               ([{"check": "command", "name": "a", "run": "x", "when": 1}], "unknown key(s) when"),
               ([{"check": "command", "name": "a", "run": "x", "severity": "loud"}], "severity must be"),
               ([{"check": "command", "name": "a", "run": "x", "at": "ready"}], "at must be merge"),
               ([{"check": "command", "name": "Bad Name", "run": "x"}], "lower-case letters"),
               ([{"check": "command", "name": "ci", "run": "x"}], "taken by a standard check"),
               ([{"check": "command", "name": "verdict-qa", "run": "x"}], "taken by a standard check"),
               ([{"check": "command", "name": "a", "run": "x"}, {"check": "command", "name": "a", "run": "y"}],
                "used twice")]
        for checks, words in bad:
            problems = gate.project_check_problems(checks)
            self.assertTrue(any(words in p for p in problems), (checks, words, problems))
        p = gate.validate_gate({"repo": "o/r", "checks": [{"check": "ci", "name": "x"},
                                                          {"check": "command", "name": "a", "run": "x"},
                                                          {"check": "command", "name": "a", "run": "y"},
                                                          {"check": "command", "run": "z", "at": "ready"}]})
        for words in ("only a command check takes a name", "used twice", "at must be merge"):
            self.assertTrue(any(words in x for x in p), words)


class FromBase(unittest.TestCase):
    """A from_base check runs the script as GitHub's base commit has it, whatever the lead did to its clone."""

    def setUp(self):
        self.home = TempHome()
        self.repo = os.path.join(self.home.root, "repo")
        self.origin = os.path.join(self.home.root, "origin.git")
        g = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "-C", self.repo]
        self.git = lambda *a: subprocess.run(g + list(a), check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "init", "-q", "--bare", self.origin], check=True)
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.home.write("repo/check.sh", '#!/bin/sh\ntest "$AF_PR" = 7 && echo "base script for $AF_BASE_SHA"\n')
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "strict")
        self.base = self.git("rev-parse", "HEAD")
        self.git("remote", "add", "origin", self.origin)
        self.git("push", "-q", "origin", "main")
        self.spec = {"check": "command", "name": "c", "from_base": "check.sh"}

    def tearDown(self):
        self.home.close()

    def run_check(self, **over):
        return self.command(pr(baseRefOid=self.base, **over), self.repo, self.spec)

    @staticmethod
    def command(data, cwd, spec):
        return gate.check_command(data, spec, {"cwd": cwd, "task_dir": None})

    def test_runs_the_base_script(self):
        ok, evidence = self.run_check()
        self.assertTrue(ok, evidence)
        self.assertIn(f"base script for {self.base}", evidence)
        self.assertFalse(self.run_check(number=8)[0])  # the script's own test fails

    def test_the_lead_cannot_swap_the_script(self):
        self.home.write("repo/check.sh", "#!/bin/sh\nexit 0\n")
        self.git("commit", "-q", "-am", "weaker")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")  # the lead moves its own origin ref
        self.assertFalse(self.run_check(number=8)[0])  # still the base commit's script

    def test_a_script_it_cannot_get_blocks(self):
        for over, words in (({"baseRefOid": "f" * 40}, "no check.sh at the base"), ({"baseRefOid": None}, "no base commit")):
            ok, evidence = self.command(pr(**over), self.repo, self.spec)
            self.assertFalse(ok)
            self.assertIn(words, evidence)
        ok, evidence = self.command(pr(baseRefOid=self.base), self.repo, {**self.spec, "from_base": "gone.sh"})
        self.assertEqual((ok, evidence.startswith("no gone.sh at the base")), (False, True))

    def test_fetched_when_the_clone_lacks_the_commit(self):
        clone = os.path.join(self.home.root, "clone")
        subprocess.run(["git", "init", "-q", clone], check=True)
        subprocess.run(["git", "-C", clone, "remote", "add", "origin", self.origin], check=True)
        ok, evidence = self.command(pr(baseRefOid=self.base), clone, self.spec)
        self.assertTrue(ok, evidence)


class Record(unittest.TestCase):
    """gate.py record: one step's evidence, checked when the step ends."""

    def setUp(self):
        self.home = TempHome()
        self.repo = os.path.join(self.home.root, "repo")
        g = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "-C", self.repo]
        self.git = lambda *a: subprocess.run(g + list(a), check=True, capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "init", "-q", "-b", "main", self.repo], check=True)
        self.git("config", "user.email", "t@example.invalid")
        self.git("config", "user.name", "t")
        self.git("commit", "-q", "--allow-empty", "-m", "W1")
        self.sha = self.git("rev-parse", "--short", "HEAD")
        self.loop = task_loop(difficulty="mid")
        self.task = os.path.join(self.home.root, "task")
        self.home.write("task/plan.md", PLAN.replace("abc1234", self.sha) + "\n## Checks\n\n### Tests near the change: x\n```\nok\n```\n"
                        "### Smoke: y\n```\nok\n```\n")
        self.home.write("task/scenario.md", SCENARIO)
        self.home.write("task/handoff.md", HANDOFF)

    def tearDown(self):
        self.home.close()

    def ended(self, *steps, done="the record is in the task folder"):
        self.home.write("task/status.jsonl", "".join(json.dumps({"step": s, "event": "end", "done": done}) + "\n"
                                                     for s in steps))

    def record(self, step, cwd=None, loop=None):
        return gate.record_checks(loop or self.loop, step, self.task, cwd)

    def test_every_lead_step_in_order(self):
        self.ended("plan", "build", "verify", "finalize")
        for step in ("plan", "build", "verify", "finalize"):
            r = self.record(step, self.repo)
            self.assertTrue(r["ok"], (step, r["checks"]))
        self.assertEqual(self.record("plan")["skills"], ["work-breakdown", "cross-check"])
        self.assertEqual(self.record("verify", self.repo)["skills"], ["unit", "smoke", "cross-check"])
        self.assertEqual(self.record("simplify")["unchecked"], ["simplify"])

    def test_no_evidence_no_pass(self):
        r = self.record("plan")
        self.assertFalse(r["ok"])
        self.assertEqual(r["checks"][0], {"check": "evidence", "ok": False,
                                          "evidence": "no end line with evidence for plan"})
        self.ended("plan", done=" ")
        self.assertFalse(self.record("plan")["ok"])

    def test_build_needs_a_real_commit_for_each_done_row(self):
        self.ended("build")
        self.assertIn("needs --cwd", self.record("build")["checks"][1]["evidence"])
        self.home.write("task/plan.md", PLAN.replace("abc1234", "1234567"))
        self.assertIn("W1's commit 1234567 is not in the clone's history", self.record("build", self.repo)["checks"][1]["evidence"])
        self.home.write("task/plan.md", PLAN.replace("| done | abc1234 |", "| todo | |"))
        self.assertIn("W1 is todo, not done", self.record("build", self.repo)["checks"][1]["evidence"])

    def test_a_replaced_default_is_held_to_the_default_s_record(self):
        plan = next(s for s in self.loop["work"] if s["id"] == "plan")
        plan["skills"] = ["plan-and-proof (flow and record: foreman-kit:work-breakdown)", "flowkit:notes",
                          "foreman-kit:tidy-up"]  # a plugin skill, and a person's skill copied into the bundle
        self.ended("plan")
        os.remove(os.path.join(self.task, "plan.md"))
        r = self.record("plan")
        self.assertEqual((r["skills"], r["ok"]), (["work-breakdown"], False))
        self.assertEqual(r["checks"][1], {"check": "record:work-breakdown", "ok": False, "evidence": "no plan.md"})

    def test_a_scenario_is_only_for_a_task_that_is_not_trivial(self):
        os.remove(os.path.join(self.task, "scenario.md"))
        self.ended("plan", "verify")
        self.assertFalse(self.record("plan")["ok"])
        self.assertTrue(self.record("plan", loop=task_loop(difficulty="mid", trivial=True))["ok"])

    def test_a_role_step_needs_its_finished_answer(self):
        self.ended("review")
        self.assertFalse(self.record("review")["ok"])
        task_folder(self.home, [("pair-1", "pair", "opus", "approved", HEAD, "2026-11-15T00:30:00Z", False)],
                    plan=None, handoff=None, scenario=None)  # the run failed
        self.assertFalse(self.record("review")["ok"])
        task_folder(self.home, [("pair-2", "pair", "opus", "", HEAD, "2026-11-15T00:40:00Z")],
                    plan=None, handoff=None, scenario=None)  # no verdict in the answer
        self.assertFalse(self.record("review")["ok"])
        task_folder(self.home, [("pair-1", "pair", "opus", "changes", HEAD, "2026-11-15T01:00:00Z")], plan=None,
                    handoff=None, scenario=None)
        r = self.record("review")
        self.assertTrue(r["ok"], r["checks"])
        self.assertIn("pair-1", r["checks"][1]["evidence"])

    def test_cli(self):
        self.home.write("task/loop.json", self.loop)
        self.ended("plan")
        r = run("gate.py", "record", "--step", "plan", "--task-dir", self.task)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout)["step"], "plan")
        self.assertEqual(run("gate.py", "record", "--step", "build", "--task-dir", self.task).returncode, 6)
        self.assertEqual(run("gate.py", "record", "--step", "nope", "--task-dir", self.task).returncode, 2)
        self.assertEqual(run("gate.py", "record", "--task-dir", self.task).returncode, 2)


class RoleChecks(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_role_verdict_from_the_task_folder(self):
        spec = {"role": "pair", "accept": ["approved"], "not_profiles": ["opus"]}
        good = task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:00:00Z")])
        self.assertTrue(check("verdict", pr(), task_dir=good, **spec)[0])
        self.assertFalse(check("verdict", pr(), **spec)[0])  # needs --task-dir

    def test_role_verdict_refuses_the_lead_profile(self):
        spec = {"role": "pair", "accept": ["approved"], "not_profiles": ["opus"]}
        lead = task_folder(self.home, [("pair-1", "pair", "opus", "approved", HEAD, "2026-11-14T01:00:00Z")])
        ok, evidence = check("verdict", pr(), task_dir=lead, **spec)
        self.assertFalse(ok)
        self.assertIn("(the lead's profile)", evidence)

    def test_role_verdict_old_head_and_latest_run(self):
        spec = {"role": "pair", "accept": ["approved"], "not_profiles": []}
        root = task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", "0" * 40, "2026-11-14T01:00:00Z")])
        self.assertFalse(check("verdict", pr(), task_dir=root, **spec)[0])
        task_folder(self.home, [("pair-1", "pair", "sonnet", "changes", HEAD, "2026-11-14T02:00:00Z"),
                                ("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:30:00Z")])
        self.assertFalse(check("verdict", pr(), task_dir=root, **spec)[0])  # the latest run says changes
        task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T03:00:00Z")])
        self.assertTrue(check("verdict", pr(), task_dir=root, **spec)[0])
        shutil.rmtree(os.path.join(root, "reviews"))
        qa = task_folder(self.home, [("qa-1", "qa", "sonnet", "pass", HEAD, "2026-11-14T03:00:00Z")])
        self.assertFalse(check("verdict", pr(), task_dir=qa, **spec)[0])  # a qa answer is not the pair's
        self.assertTrue(check("verdict", pr(), task_dir=qa, role="qa", accept=["pass"])[0])

    def test_failed_run_and_last_line(self):
        spec = {"role": "pair", "accept": ["approved"]}
        root = task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:00:00Z", False)])
        ok, evidence = check("verdict", pr(), task_dir=root, **spec)
        self.assertFalse(ok)
        self.assertIn("(the run failed)", evidence)
        shutil.rmtree(os.path.join(root, "reviews"))
        task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:00:00Z")])
        with open(os.path.join(root, "reviews", "pair-1-2026-11-14T01:00:00Z.json"), "w") as f:
            json.dump({"result": "Verdict: approved\nOn second look:\nVerdict: changes"}, f)
        self.assertFalse(check("verdict", pr(), task_dir=root, **spec)[0])  # the last Verdict line counts

    def test_docs(self):
        root = task_folder(self.home)
        self.assertTrue(check("docs", pr(), task_dir=root)[0])
        self.assertEqual(check("docs", pr())[1], "needs --task-dir")
        todo = PLAN.replace("| done |", "| todo |")
        root = task_folder(self.home, plan=todo)
        self.assertIn("work items not done: W1", check("docs", pr(), task_dir=root)[1])
        moved = PLAN.replace("| test | status |", "| status | test |").replace("| test-first | done |", "| done | test-first |")
        root = task_folder(self.home, plan=moved)
        self.assertTrue(check("docs", pr(), task_dir=root)[0])  # the status column is found by its name
        short = PLAN.replace("| W1 | a | b | c | test-first | done | abc1234 |", "| W1 | a | b | c | todo |")
        root = task_folder(self.home, plan=short)
        self.assertIn("rows that do not fit the header: W1 (5 cells, not 7)", check("docs", pr(), task_dir=root)[1])
        empty = PLAN.split("| W1")[0]
        root = task_folder(self.home, plan=empty)
        self.assertIn("work breakdown is empty", check("docs", pr(), task_dir=root)[1])
        root = task_folder(self.home, plan=PLAN, handoff="# Handoff\n\n## Purpose\nx\n")
        self.assertIn("handoff.md lacks Decisions", check("docs", pr(), task_dir=root)[1])
        failing = SCENARIO.replace("Verdict: pass", "Verdict: fail")
        root = task_folder(self.home, handoff=HANDOFF, scenario=failing)
        self.assertIn("closing verdict is not pass", check("docs", pr(), task_dir=root)[1])
        self.assertTrue(check("docs", pr(), task_dir=root, trivial=True)[0])  # no scenario for a trivial task
        for agent_block in ("**Agent**\n\n```\n```", "**Agent**\n\n```\n<what the last full run printed>\n```",
                            "**Agent**\n\nok"):
            root = task_folder(self.home, scenario=SCENARIO.replace("**Agent**\n\n```\nok\n```", agent_block))
            self.assertIn("1 Agent block(s) with no output", check("docs", pr(), task_dir=root)[1], agent_block)
        for name in ("plan.md", "handoff.md", "scenario.md"):
            root = task_folder(self.home)
            os.remove(os.path.join(root, name))
            self.assertIn(f"no {name}", check("docs", pr(), task_dir=root)[1])

    def test_steps(self):
        root = task_folder(self.home)
        self.assertEqual(check("steps", pr(), ids=["plan"])[1], "needs --task-dir")
        self.assertIn("no end line for: plan, build", check("steps", pr(), task_dir=root, ids=["plan", "build"])[1])
        status_lines(self.home)  # heartbeats only
        self.assertIn("no end line for: plan, build", check("steps", pr(), task_dir=root, ids=["plan", "build"])[1])
        status_lines(self.home, "plan", "build")
        self.assertTrue(check("steps", pr(), task_dir=root, ids=["plan", "build"])[0])

    def test_loop_file(self):
        root = task_folder(self.home)
        self.assertEqual(check("loop-file", pr(), sha256="x")[1], "needs --task-dir")
        self.assertFalse(check("loop-file", pr(), task_dir=root, sha256="x")[0])  # no loop.json
        path = self.home.write("task/loop.json", task_loop())
        sha = gate.sha256_file(path)
        self.assertTrue(check("loop-file", pr(), task_dir=root, sha256=sha)[0])
        with open(path, "a") as f:
            f.write(" ")
        self.assertIn("changed after the brief", check("loop-file", pr(), task_dir=root, sha256=sha)[1])


class PostedAnswers(unittest.TestCase):
    """post_answers: a verification verdict counts only when its saved answer is on the pull request, whole."""

    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.task = task_folder(self.home, [("redteam-1", "redteam", "opus", "approved", HEAD, "2026-11-14T02:00:00Z")])
        with open(os.path.join(self.task, "reviews", "redteam-1-2026-11-14T02:00:00Z.meta.json")) as f:
            self.body = gate.answer_comment("redteam", "redteam-1", 7, json.load(f), "must-fix: none\nVerdict: approved")

    def verdict(self, comments, posted=True):
        return check("verdict", pr(comments=comments), role="redteam", task_dir=self.task, posted=posted)

    def test_only_the_saved_answer_whole_counts(self):
        self.assertTrue(self.body.startswith(f"## redteam answer by redteam-1 on #7 at {HEAD[:7]}\n\n"
                                             "must-fix: none\nVerdict: approved\n\n---\n"))
        ok, why = self.verdict([])
        self.assertFalse(ok)
        self.assertIn("redteam-1 opus a1b2c3d approved (not on the pull request as saved)", why)
        self.assertTrue(self.verdict([{"body": "other"}, {"body": self.body.replace("\n", "\r\n") + "  \n"}])[0])
        edited = self.body.replace("must-fix: none", "must-fix: none, all checked")
        self.assertFalse(self.verdict([{"body": edited}])[0])  # a posted answer that differs from the saved one
        self.assertTrue(self.verdict([], posted=False)[0])  # without post_answers, nothing is looked up

    def test_the_template_asks_for_it_at_merge_only(self):
        data = task_loop(config.merge(config.load(), {"post_answers": True}), difficulty="mid", lead="sonnet")
        self.assertTrue(data["post_answers"])
        verdicts = [c for c in gate.template(data)["checks"] if c["check"] == "verdict"]
        self.assertEqual([(c["role"], c.get("at"), c.get("posted")) for c in verdicts],
                         [("pair", None, None), ("redteam", "merge", True), ("qa", "merge", True)])
        plain = gate.template(task_loop(difficulty="mid", lead="sonnet"))
        self.assertFalse([c for c in plain["checks"] if c.get("posted")])


class Template(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = config.load()

    def tearDown(self):
        self.home.close()

    def test_follows_the_loop(self):
        high = gate.template(task_loop(difficulty="high"), "f" * 64, 7)
        verdicts = [(c["role"], c["accept"], c["not_profiles"], c.get("at"))
                    for c in high["checks"] if c["check"] == "verdict"]
        self.assertEqual(verdicts, [("pair", ["approved"], ["opus"], None),
                                    ("redteam", ["approved"], ["opus"], "merge"),
                                    ("qa", ["pass"], ["opus"], "merge")])
        self.assertEqual(gate.validate_gate(high), [])
        self.assertEqual([c["sha256"] for c in high["checks"] if c["check"] == "loop-file"], ["f" * 64])
        self.assertEqual([c["ids"] for c in high["checks"] if c["check"] == "steps"],
                         [["plan", "plan-check", "build", "verify", "review", "simplify", "fix", "recheck"]])
        fallback = gate.template(task_loop(difficulty="high", lead="sonnet"))
        self.assertEqual({tuple(c["not_profiles"]) for c in fallback["checks"] if c["check"] == "verdict"}, {("sonnet",)})
        low = gate.template(task_loop(difficulty="low", trivial=True))
        self.assertEqual([c["role"] for c in low["checks"] if c["check"] == "verdict"], ["redteam", "qa"])
        self.assertEqual([c["ids"] for c in low["checks"] if c["check"] == "steps"], [["plan", "build", "verify"]])
        self.assertTrue([c for c in low["checks"] if c["check"] == "docs"][0]["trivial"])
        self.assertEqual([c for c in low["checks"] if c["check"] == "size"][0]["severity"], "warn")
        self.assertFalse([c for c in low["checks"] if c["check"] in ("command", "loop-file")])
        cmd = gate.template(task_loop(config.merge(self.cfg, {"tests": {"full": "make test"}}), difficulty="low"))
        self.assertEqual([c for c in cmd["checks"] if c["check"] == "command"],
                         [{"check": "command", "run": "make test", "full": True, "min_free_gb": 20}])
        off = config.merge(self.cfg, {"tests": {"full": "make test"}, "ops": {"disk_check": False}})
        self.assertEqual([c["min_free_gb"] for c in gate.template(task_loop(off))["checks"] if c.get("full")], [0])


def git_repo(home):
    """A bare origin and a clone with one commit on main: (clone, git runner)."""
    g = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
    origin, work = os.path.join(home.root, "origin.git"), os.path.join(home.root, "work")
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", origin], check=True)
    subprocess.run(["git", "clone", "-q", origin, work], check=True, capture_output=True)

    def sh(*a):
        return subprocess.run(g + ["-C", work, *a], check=True, capture_output=True, text=True).stdout.strip()
    with open(os.path.join(work, "a.txt"), "w") as f:
        f.write("a\n")
    sh("add", "-A"); sh("commit", "-q", "-m", "init"); sh("push", "-q", "origin", "HEAD:main")
    return work, sh


class SameChange(unittest.TestCase):
    def test_clean_rebase_keeps_the_verdict(self):
        home = TempHome()
        try:
            work, sh = git_repo(home)
            sh("checkout", "-q", "-b", "feature")
            open(os.path.join(work, "b.txt"), "w").write("b\n")
            sh("add", "-A"); sh("commit", "-q", "-m", "change")
            reviewed = sh("rev-parse", "HEAD")
            sh("checkout", "-q", "main")
            open(os.path.join(work, "c.txt"), "w").write("c\n")
            sh("add", "-A"); sh("commit", "-q", "-m", "other"); sh("push", "-q", "origin", "HEAD:main")
            sh("checkout", "-q", "feature"); sh("fetch", "-q"); sh("rebase", "-q", "origin/main")
            head = sh("rev-parse", "HEAD")
            self.assertNotEqual(reviewed, head)
            self.assertTrue(gate.same_change(work, "main", reviewed, head))
            root = task_folder(home, [("pair-1", "pair", "sonnet", "approved", reviewed, "2026-11-14T01:00:00Z")])
            self.assertFalse(check("verdict", pr(headRefOid=head), task_dir=root, role="pair")[0])
            self.assertTrue(check("verdict", pr(headRefOid=head), task_dir=root, role="pair", cwd=work)[0])
            open(os.path.join(work, "b.txt"), "w").write("b changed\n")
            sh("add", "-A"); sh("commit", "-q", "--amend", "-m", "change")
            self.assertFalse(gate.same_change(work, "main", reviewed, sh("rev-parse", "HEAD")))
        finally:
            home.close()


FAKE_GH = """#!/usr/bin/env python3
import json, os, sys
data = json.load(open(os.environ["FAKE_GH_DATA"]))
args = sys.argv[1:]
if args[:2] == ["pr", "view"]:
    print(json.dumps(data["view"]))
elif args[0] == "api" and "/files" in args[-1]:
    print(json.dumps(data["files"]))
elif args[0] == "api" and "/compare/" in args[-1]:
    print(json.dumps({"behind_by": data["behind_by"]}))
else:
    sys.exit(1)
"""


def fake_gh(home, view):
    """A `gh` on PATH that answers from a file: (env, data file)."""
    bindir = os.path.join(home.root, "bin")
    os.makedirs(bindir, exist_ok=True)
    path = os.path.join(bindir, "gh")
    with open(path, "w") as f:
        f.write(FAKE_GH)
    os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC)
    data = home.write("gh.json", {"view": {k: v for k, v in view.items() if k not in ("files", "behind_by")},
                                  "files": view["files"], "behind_by": view["behind_by"]})
    return {"PATH": bindir + os.pathsep + os.environ["PATH"], "FAKE_GH_DATA": data}, data


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.env, _ = fake_gh(self.home, pr())
        self.task = task_folder(self.home, [("pair-1", "pair", "sonnet", "approved", HEAD, "2026-11-14T01:00:00Z")])
        self.loop = self.home.write("task/loop.json", task_loop(difficulty="low"))
        status_lines(self.home, "plan", "build", "verify", "review", "simplify", "fix", "recheck")

    def tearDown(self):
        self.home.close()

    def template(self, *args):
        r = run("gate.py", "template", "--loop", self.loop, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return self.home.write("gate.json", r.stdout)

    def test_run_passes_and_blocks(self):
        g = self.template("--pr", "7")
        r = run("gate.py", "run", g, "--task-dir", self.task, "--before-ready", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(json.loads(r.stdout)["pass"])  # the verification session's verdicts wait for the merge gate
        r = run("gate.py", "run", g, "--task-dir", self.task, env=self.env)
        self.assertEqual(r.returncode, 6)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["verdict:redteam", "verdict:qa"])
        r = run("gate.py", "run", g, "--task-dir", self.task, "--skip", "verdict", env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("verdict:qa", r.stderr)
        r = run("gate.py", "run", g, "--task-dir", self.task, "--skip", "verdict:qa", env=self.env)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["verdict:redteam"])
        task_folder(self.home, [("redteam-1", "redteam", "opus", "approved", HEAD, "2026-11-14T02:00:00Z"),
                                ("qa-1", "qa", "opus", "pass", HEAD, "2026-11-14T02:00:00Z")])
        r = run("gate.py", "run", g, "--task-dir", self.task, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_gate_and_loop_files_must_be_the_briefs(self):
        g = self.template("--pr", "7")
        sha = run("gate.py", "hash", g).stdout.strip()
        self.assertEqual(sha, gate.sha256_file(g))
        r = run("gate.py", "run", g, "--task-dir", self.task, "--before-ready", "--sha", sha, env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(g) as f:
            weaker = json.load(f)
        weaker["checks"] = [c for c in weaker["checks"] if c["check"] != "verdict"]
        with open(g, "w") as f:
            json.dump(weaker, f)
        r = run("gate.py", "run", g, "--task-dir", self.task, "--sha", sha, env=self.env)
        self.assertEqual(r.returncode, 6)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["gate-file"])
        g = self.template("--pr", "7")
        with open(self.loop, "a") as f:
            f.write("\n")
        r = run("gate.py", "run", g, "--task-dir", self.task, "--before-ready", env=self.env)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["loop-file"])

    def test_pull_request_named_at_run_time(self):
        g = self.template()
        self.assertEqual(run("gate.py", "run", g, "--before-ready", env=self.env).returncode, 2)  # no PR yet
        r = run("gate.py", "run", g, "--pr", "7", "--task-dir", self.task, "--before-ready", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        named = self.template("--pr", "7")
        r = run("gate.py", "run", named, "--pr", "8", env=self.env)
        self.assertEqual(r.returncode, 2)
        self.assertIn("for #7, not #8", r.stderr)

    def test_paths_with_a_tilde(self):
        g = self.template("--pr", "7")
        rel = "~/" + os.path.relpath(g, self.home.root)
        task = "~/" + os.path.relpath(self.task, self.home.root)
        r = run("gate.py", "run", rel, "--task-dir", task, "--before-ready", env={**self.env, "HOME": self.home.root})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_project_checks_join_the_gate_and_runs_are_recorded(self):
        data = task_loop(difficulty="low")
        data["gate"] = [{"check": "command", "name": "pr-body", "run": 'test "$AF_PR" = 7'},
                        {"check": "command", "name": "epic-tests", "run": "false", "at": "merge"}]
        self.loop = self.home.write("task/loop.json", data)
        g = self.template("--pr", "7")
        with open(g) as f:
            names = [gate.check_name(c) for c in json.load(f)["checks"]]
        self.assertEqual(names[names.index("verdict:qa") + 1:], ["pr-body", "epic-tests", "tests-weakened", "size",
                                                                "ready"])
        r = run("gate.py", "run", g, "--task-dir", self.task, "--cwd", self.home.root, "--before-ready", env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)  # epic-tests waits for the merge gate
        self.assertIn("pr-body", [c["check"] for c in json.loads(r.stdout)["checks"]])
        r = run("gate.py", "run", g, "--task-dir", self.task, "--cwd", self.home.root, env=self.env)
        self.assertEqual(json.loads(r.stdout)["blocked"], ["verdict:redteam", "verdict:qa", "epic-tests"])
        with open(os.path.join(self.task, "gates.jsonl")) as f:
            rows = [json.loads(line) for line in f]
        self.assertEqual([(r["before_ready"], r["pass"], r["blocked"]) for r in rows],
                         [(True, True, []), (False, False, ["verdict:redteam", "verdict:qa", "epic-tests"])])
        self.assertEqual(rows[0]["head"], HEAD)

    def test_template_and_bad_arguments(self):
        self.assertEqual(json.loads(run("gate.py", "template", "--loop", self.loop).stdout)["pr"], None)
        self.assertEqual(run("gate.py", "template").returncode, 2)
        bad_loop = self.home.write("bad-loop.json", {"task": "7"})
        self.assertEqual(run("gate.py", "template", "--loop", bad_loop).returncode, 2)
        self.assertEqual(run("gate.py", "run").returncode, 2)
        bad = self.home.write("bad.json", {"repo": "o/r", "pr": 7, "checks": [{"check": "magic"}]})
        self.assertEqual(run("gate.py", "run", bad, env=self.env).returncode, 2)


if __name__ == "__main__":
    unittest.main()
