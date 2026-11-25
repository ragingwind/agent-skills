import copy
import json
import os
import re
import shutil
import subprocess
import unittest
from unittest import mock

from helpers import SCRIPTS, TempHome, run, task_loop

import config
import loop

WORK = ["plan", "plan-check", "build", "verify", "review", "simplify", "fix", "recheck", "finalize"]
STAGES = ["plan", "build", "verify", "review", "finalize"]
CHECK = ["redteam-review", "test"]


def stage(id, actor="lead", nxt=None, **kw):
    s = {"id": id, "actor": actor, "does": f"do {id}", "skills": [], "next": nxt or {"done": "stop"}}
    s.update(kw)
    return s


class Validate(unittest.TestCase):
    def test_standard_loops_are_valid(self):
        std = config.standard()["loop"]
        self.assertEqual(loop.validate_loop(std), [])
        self.assertEqual(loop.step_ids(std), WORK)
        self.assertEqual(loop.stage_ids(std), STAGES)
        self.assertEqual(loop.step_ids(std, "check"), CHECK)
        self.assertEqual(loop.stage_ids(std, "check"), CHECK)
        self.assertEqual(loop.stage_ids(std, "manage"), loop.step_ids(std, "manage"))  # a step without a stage is one

    def test_every_default_skill_is_used(self):
        std = config.standard()["loop"]
        used = {n for w in loop.LOOPS for s in std.get(w, []) for n in s.get("skills", [])}
        self.assertEqual(used, set(loop.KIT))

    def test_check_steps_may_send_the_task_back_to_a_work_step(self):
        base = {"roles": {"r": {"mode": "prompt"}}, "prompts": {}, "work": [stage("build")]}
        ok = dict(base, check=[stage("x", actor="r", nxt={"changes": "build", "pass": "stop"})])
        self.assertEqual(loop.validate_loop(ok), [])
        bad = dict(base, check=[stage("x", actor="r", nxt={"changes": "nowhere"})])
        self.assertIn("goes to 'nowhere'", "\n".join(loop.validate_loop(bad)))
        back = dict(base, work=[stage("a", nxt={"done": "x"})], check=[stage("x", actor="r")])
        self.assertIn("goes to 'x'", "\n".join(loop.validate_loop(back)))  # a work step cannot jump into the check loop

    def test_stage_problems(self):
        base = {"roles": {}, "prompts": {}}
        apart = dict(base, work=[stage("a", stage="s1", nxt={"done": "b"}), stage("b", stage="s2", nxt={"done": "c"}),
                                 stage("c", stage="s1")])
        self.assertIn("loop: work stage s1: its steps must come one after another", loop.validate_loop(apart))
        clash = dict(base, work=[stage("a", stage="b", nxt={"done": "b"}), stage("b", stage="s2")])
        self.assertIn("loop: work stage b has the name of step b, which is in stage s2", loop.validate_loop(clash))
        own = dict(base, work=[stage("a", stage="a", nxt={"done": "b"}), stage("b")])
        self.assertEqual(loop.validate_loop(own), [])
        bad = dict(base, work=[stage("a", stage="no spaces")])
        self.assertTrue(any("stage must be a name" in p for p in loop.validate_loop(bad)))

    def test_success_path_must_reach_stop(self):
        base = {"roles": {"r": {"mode": "prompt"}}, "prompts": {}}
        loops = dict(base, work=[stage("a", nxt={"done": "b"}), stage("b", nxt={"fail": "a", "done": "a"})])
        self.assertIn("loop: work: the success path from a (each step's last outcome) does not reach stop",
                      loop.validate_loop(loops))
        back = dict(base, work=[stage("a")], check=[stage("x", actor="r", nxt={"pass": "a"})])
        self.assertIn("loop: check: the success path from x (each step's last outcome) does not reach stop",
                      loop.validate_loop(back))
        self.assertEqual(loop.success_problems(config.standard()["loop"]), [])

    def test_verdict_words_are_outcomes(self):
        """What a judging role may answer is an outcome of each step it runs,
        and its passing verdict is the step's success path."""
        std = config.standard()["loop"]
        for which in ("work", "check"):
            for s in std[which]:
                role = std["roles"].get(s["actor"])
                if not role:
                    continue
                words = set(re.findall(r"`Verdict: (\w+)`", std["prompts"][role["prompt"]]))
                if s["id"] == "review":  # the first pair review goes on to simplify whatever it says
                    self.assertEqual(list(s["next"]), ["done"])
                    continue
                self.assertEqual(set(s["next"]) & words, words, s["id"])
                self.assertEqual(list(s["next"])[-1], role["accept"][0], s["id"])

    def test_problems(self):
        bad = {"roles": {"lead": {"mode": "tab"}, "r": {"mode": "prompt", "prompt": "none", "deny_tools": ["Edit"]},
                         "q": {"mode": "prompt", "no_edit": "yes"}},
               "prompts": {"x": " "},
               "work": [stage("a", nxt={"done": "nowhere"}), stage("a", actor="ghost"),
                        stage("b", run={"huge": "always", "mid": "if-user-visible"}),
                        {"id": "c", "actor": "lead", "does": "", "skills": "x", "next": {}}]}
        p = "\n".join(loop.validate_loop(bad))
        for words in ("prompt x is empty", "role name 'lead' is not allowed", "mode must be one of",
                      "prompt 'none' does not exist", "role r: deny_tools is replaced by no_edit",
                      "role q: no_edit must be true or false", "goes to 'nowhere'",
                      "step a appears twice", "actor 'ghost'", "names 'huge'", "run for mid",
                      "says nothing", "skills must be a list", "next must name"):
            self.assertIn(words, p)


class Plan(unittest.TestCase):
    def setUp(self):
        self.loop = config.standard()["loop"]

    def ids(self, difficulty, trivial=False, which="work"):
        return [s["id"] for s in loop.plan(self.loop, difficulty, trivial, which)]

    def test_every_difficulty_runs_the_whole_build_session(self):
        for level in loop.LEVELS:  # the foreman checks the plan before build at high only
            self.assertEqual(self.ids(level), WORK if level == "high" else [s for s in WORK if s != "plan-check"])
            self.assertEqual(self.ids(level, which="check"), CHECK)
        plan = {s["id"]: s for s in loop.plan(self.loop, "mid")}["plan"]
        self.assertEqual(plan["next"], {"done": "build"})  # past the skipped check
        high = {s["id"]: s for s in loop.plan(self.loop, "high")}
        self.assertEqual((high["plan"]["next"], high["plan-check"]["actor"], high["plan-check"]["next"]),
                         ({"done": "plan-check"}, "foreman", {"back": "plan", "go": "build"}))

    def test_trivial_task_skips_the_review_stage(self):
        trivial = {s["id"]: s for s in loop.plan(self.loop, "mid", trivial=True)}
        self.assertEqual(list(trivial), ["plan", "build", "verify", "finalize"])
        self.assertEqual(trivial["verify"]["next"], {"fail": "build", "done": "finalize"})
        self.assertEqual(self.ids("mid", True, "check"), CHECK)  # QA always runs

    def test_review_stage_repeats_and_check_goes_back_to_work(self):
        mid = {s["id"]: s for s in loop.plan(self.loop, "mid")}
        self.assertEqual(mid["recheck"]["next"], {"changes": "fix", "approved": "finalize"})
        steps = loop.plan(self.loop, "mid")
        self.assertTrue(loop.has_rounds(steps, "review"))
        self.assertFalse(loop.has_rounds(steps, "plan"))
        check = {s["id"]: s for s in loop.plan(self.loop, "mid", which="check")}
        self.assertEqual(check["test"]["next"], {"fail": "build", "script": "verify", "pass": "stop"})

    def test_steps_carry_their_stage_and_an_empty_stage_drops(self):
        self.assertEqual([(s["stage"], s["id"]) for s in loop.plan(self.loop, "mid")][3:5],
                         [("review", "review"), ("review", "simplify")])
        l = {"roles": {}, "prompts": {}, "work": [stage("a", stage="s1", nxt={"done": "b"}),
                                                    stage("b", stage="s2", nxt={"done": "c"}, run={"low": "never"}),
                                                    stage("c", stage="s3")]}
        self.assertEqual([s["stage"] for s in loop.plan(l, "low")], ["s1", "s3"])

    def test_chained_skips(self):
        l = {"roles": {}, "prompts": {}, "work": [stage("a", nxt={"done": "b"}), stage("b", nxt={"done": "c"}, run={"low": "never"}),
                                                    stage("c", nxt={"done": "d"}, run={"low": "never"}), stage("d")]}
        self.assertEqual([(s["id"], s["next"]["done"]) for s in loop.plan(l, "low")], [("a", "d"), ("d", "stop")])


class Skills(unittest.TestCase):
    LOCAL = {"local-skills:tidy": "/a", "pstack:how": "/b", "x:how": "/c", "scenario": "/d"}

    def test_project_first(self):
        self.assertEqual(loop.resolve_skill("scenario", ["scenario"], self.LOCAL), ("project", "scenario"))
        self.assertEqual(loop.resolve_skill("tidy", [], self.LOCAL), ("bundle", "local-skills:tidy"))
        self.assertEqual(loop.resolve_skill("local-skills:tidy", ["tidy"], self.LOCAL), ("bundle", "local-skills:tidy"))

    def test_ambiguous_and_missing(self):
        self.assertEqual(loop.resolve_skill("how", [], self.LOCAL)[0], "missing")
        self.assertIn("pstack:how", loop.resolve_skill("how", [], self.LOCAL)[1])
        self.assertEqual(loop.resolve_skill("ghost", [], self.LOCAL)[0], "missing")

    def test_default_skill_unless_replaced(self):
        self.assertEqual(loop.resolve("review", [], self.LOCAL), ("kit", "review"))
        self.assertEqual(loop.resolve("simplify", [], self.LOCAL, {"simplify": "tidy"}), ("bundle", "local-skills:tidy"))
        self.assertEqual(loop.resolve("cross-check", ["scenario"], self.LOCAL, {"cross-check": "scenario"}),
                         ("project", "scenario"))
        self.assertEqual(loop.resolve("smoke", [], self.LOCAL, {"smoke": "ghost"})[0], "missing")
        self.assertEqual(loop.resolve("tidy", [], self.LOCAL), ("bundle", "local-skills:tidy"))  # not a default skill

    def test_a_plugin_dir_skill_goes_with_its_plugin(self):
        local = {**self.LOCAL, "flow:impl": "/p/skills/impl", "flow:pr": "/p/skills/pr"}
        self.assertEqual(loop.resolve_skill("impl", [], local, whole={"flow"}), ("plugin", "flow:impl"))
        self.assertEqual(loop.resolve_skill("impl", [], local), ("bundle", "flow:impl"))  # not loaded whole: copied
        self.assertEqual(loop.resolve_skill("impl", ["impl"], local, whole={"flow"}), ("project", "impl"))
        self.assertEqual(loop.resolve_skill("tidy", [], local, whole={"flow"}), ("bundle", "local-skills:tidy"))
        resolved = loop.resolve_all({"work": [{"skills": ["handoff", "impl"]}]}, [], local, overrides={"handoff": "pr"},
                                    whole={"flow"})
        self.assertEqual(resolved, {"handoff": ("plugin", "flow:pr"), "impl": ("plugin", "flow:impl")})
        name = lambda src, v: v if src in ("project", "plugin") else "foreman-kit:" + v
        self.assertEqual(loop.shown("handoff", resolved, name, {"handoff": "pr"}),
                         "flow:pr (flow and record: foreman-kit:handoff)")
        self.assertEqual(loop.shown("impl", resolved, name, {"handoff": "pr"}), "flow:impl")
        self.assertEqual(loop.shown("review", {"review": ("kit", "review")}, name, {}), "foreman-kit:review")

    def test_project_skill_names_local(self):
        home = TempHome()
        try:
            home.write("repo/.claude/skills/scenario/SKILL.md", "x")
            home.write("repo/.claude/skills/notes/README.md", "x")
            self.assertEqual(loop.project_skill_names("local", os.path.join(home.root, "repo")), ["scenario"])
            home.write("repo/.claude/commands/impl.md", "x")  # a project command is called by its name too
            home.write("repo/.claude/commands/notes.txt", "x")
            home.write("repo/.claude/commands/scenario.md", "x")
            self.assertEqual(loop.project_skill_names("local", os.path.join(home.root, "repo")), ["impl", "scenario"])
            self.assertEqual(loop.project_skill_names("local", os.path.join(home.root, "none")), [])
        finally:
            home.close()

    def test_project_skill_names_remote_under_a_zsh_login_shell(self):
        zsh = shutil.which("zsh")
        if not zsh:
            self.skipTest("no zsh here")
        home = TempHome()
        try:
            home.write("repo/.claude/skills/scenario/SKILL.md", "x")  # skills, and no commands folder
            home.write("other/.claude/commands/my cmd.md", "x")  # commands only, a name with a space
            real = subprocess.run

            def over_ssh(argv, **kw):  # a login shell that is zsh, where a glob with no match is an error
                return real([zsh, "-c", argv[-1]], env={**os.environ, "HOME": home.root}, **kw)

            with mock.patch.object(loop.subprocess, "run", over_ssh):
                self.assertEqual(loop.project_skill_names("m", "~/repo", {"m": {"target": "host"}}), ["scenario"])
                self.assertEqual(loop.project_skill_names("m", "~/other", {"m": {"target": "host"}}), ["my cmd"])
        finally:
            home.close()

    def test_project_skill_names_remote_expands_home(self):
        home = TempHome()
        try:
            home.write("repo/.claude/skills/scenario/SKILL.md", "x")
            home.write("a b/.claude/skills/notes/SKILL.md", "x")
            home.write("a b/.claude/commands/impl.md", "x")
            home.write("a b/.claude/commands/notes.md", "x")
            real = subprocess.run

            def over_ssh(argv, **kw):  # the remote shell, played by sh with HOME at the temporary folder
                return real(["sh", "-c", argv[-1]], env={**os.environ, "HOME": home.root}, **kw)

            saved = {"m": {"target": "host"}}
            with mock.patch.object(loop.subprocess, "run", over_ssh):
                for path, want in [("~/repo", ["scenario"]), ("~/a b", ["impl", "notes"]),
                                   (os.path.join(home.root, "repo"), ["scenario"]), ("~/none", [])]:
                    self.assertEqual(loop.project_skill_names("m", path, saved), want, path)
        finally:
            home.close()


def kit_name(src, v):
    return v if src == "project" else "foreman-kit:" + v.split(":")[-1]


class Render(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.cfg = copy.deepcopy(config.load("o/r"))
        self.resolved = {n: ("kit", n) for n in loop.KIT}
        self.resolved["simplify"] = ("bundle", "local-skills:tidy")
        self.cfg["skills"] = {"simplify": "tidy"}
        self.profiles = {"pair": ["sonnet", "opus"], "redteam": ["opus", "sonnet"], "qa": ["opus"]}

    def tearDown(self):
        self.home.close()

    def render(self, difficulty, trivial=False, which="work", profiles=None):
        return loop.render(self.cfg, "634", difficulty, trivial, self.resolved, profiles or self.profiles, kit_name,
                           which)

    def test_mid_task(self):
        out = self.render("mid")
        self.assertIn("| 1 | plan | `634 plan` | plan | lead |", out)
        self.assertIn("| foreman-kit:work-breakdown, foreman-kit:cross-check | done → build (build) |", out)
        self.assertIn("| 4 | review | `634 review <N>` | review | pair |", out)
        # a replaced default skill, with the default whose flow and record still apply
        self.assertIn("| foreman-kit:tidy (flow and record: foreman-kit:simplify) | done → fix |", out)
        self.assertIn("changes → fix; approved → finalize (finalize)", out)
        self.assertIn("| pair | prompt | sonnet | opus |", out)
        self.assertIn("`loop.py prompt --step <step>`", out)
        self.assertNotIn("Missing skills", out)

    def test_trivial_task(self):
        out = self.render("mid", trivial=True)
        self.assertIn("(difficulty mid, trivial)", out)
        self.assertNotIn("| recheck |", out)
        self.assertIn("done → finalize (finalize)", out)
        self.assertNotIn("| pair |", out)

    def test_check_loop_for_the_foreman(self):
        out = self.render("high", which="check")
        self.assertIn("# Verification session for 634", out)
        self.assertIn("| 1 | redteam-review | `634 redteam-review` | redteam-review | redteam |", out)
        self.assertIn("changes → build (build session); approved → stop", out)
        self.assertIn("script → verify (build session)", out)
        self.assertIn("| qa | prompt | opus |", out)

    def test_a_missing_replacement_keeps_the_default(self):
        self.cfg["skills"]["handoff"] = "pr-gone"
        self.resolved["handoff"] = ("missing", "pr-gone is neither a project skill there nor a skill on this machine")
        data = loop.as_data(self.cfg, "634", "mid", False, self.resolved, kit_name, "o/r", "main", "sonnet",
                            self.profiles)
        self.assertEqual(next(s for s in data["work"] if s["id"] == "finalize")["skills"], ["foreman-kit:handoff"])
        out = self.render("mid")
        self.assertIn("| foreman-kit:handoff | conflict → build", out)
        self.assertIn("- pr-gone is neither a project skill", out)  # still named as missing

    def test_as_data_carries_the_project_gate_and_the_contracts(self):
        self.cfg["gate"] = [{"check": "command", "name": "pr-body", "run": "x"}]
        data = loop.as_data(self.cfg, "634", "mid", False, self.resolved, kit_name, "o/r", "main", "sonnet",
                            self.profiles)
        self.assertEqual(data["gate"], [{"check": "command", "name": "pr-body", "run": "x"}])
        simplify = next(s for s in data["work"] if s["id"] == "simplify")
        self.assertEqual(simplify["skills"], ["foreman-kit:tidy (flow and record: foreman-kit:simplify)"])
        del self.cfg["gate"]
        self.assertEqual(loop.as_data(self.cfg, "634", "mid", False, self.resolved, kit_name, "o/r", "main", "sonnet",
                                      self.profiles)["gate"], [])

    def test_as_data(self):
        data = loop.as_data(self.cfg, "634", "mid", False, self.resolved, kit_name, "o/r", "main", "sonnet",
                            self.profiles)
        self.assertEqual([s["id"] for s in data["work"]], [s for s in WORK if s != "plan-check"])  # high only
        self.assertEqual([s["id"] for s in data["check"]], CHECK)
        self.assertEqual((data["repo"], data["base"], data["lead_profile"], data["max_lines"]), ("o/r", "main", "sonnet", 400))
        recheck = next(s for s in data["work"] if s["id"] == "recheck")
        self.assertEqual((recheck["stage"], recheck["label"], recheck["actor"], recheck["skills"], recheck["next"]),
                         ("review", "634 review <N>", "pair", ["foreman-kit:review"],
                          {"changes": "fix", "approved": "finalize"}))
        self.assertTrue(all(s["does"] for s in data["work"] + data["check"]))
        self.assertEqual(set(data["roles"]), {"pair", "redteam", "qa"})
        self.assertEqual((data["roles"]["qa"]["accept"], data["roles"]["qa"]["profiles"]), (["pass"], ["opus"]))
        self.assertIn("<full test command>", data["roles"]["qa"]["prompt"])
        trivial = loop.as_data(self.cfg, "634", "mid", True, self.resolved, kit_name, "o/r", "main", "sonnet",
                               self.profiles)
        self.assertEqual([s["id"] for s in trivial["work"]], ["plan", "build", "verify", "finalize"])
        self.assertEqual(next(s for s in trivial["work"] if s["id"] == "verify")["next"]["done"], "finalize")
        self.assertEqual(set(trivial["roles"]), {"redteam", "qa"})


class Cli(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()

    def tearDown(self):
        self.home.close()

    def test_show_and_bad_arguments(self):
        r = run("loop.py", "show")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("| review | recheck | pair |", r.stdout)
        self.assertIn("if-not-trivial | if-not-trivial | if-not-trivial", r.stdout)
        import config
        for s in config.standard()["loop"]["work"]:
            self.assertIn(s["does"].replace("|", "/"), r.stdout)  # each step whole, never cut
        r = run("loop.py", "show", "--loop", "check")
        self.assertIn("| test | test | qa |", r.stdout)
        self.assertEqual(run("loop.py", "render").returncode, 2)
        self.assertEqual(run("loop.py", "show", "--project", "bad").returncode, 2)

    def test_render_local_machine(self):
        repo = os.path.join(self.home.root, "repo")
        self.home.write("repo/.claude/skills/scenario/SKILL.md", "x")
        self.home.write("state/agent-foreman/projects/o-r/project.json",
                        {"repo": "o/r", "machines": {"local": repo}, "skills": {"cross-check": "scenario"}})
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "high", "--machine", "local")
        self.assertEqual(r.returncode, 0, r.stderr)
        # the project's skill replaces cross-check; cross-check's flow and record still apply
        self.assertIn("| foreman-kit:work-breakdown, scenario (flow and record: foreman-kit:cross-check) |", r.stdout)
        self.assertIn("| pair | prompt | sonnet | - |", r.stdout)  # high: never the lead's opus
        self.assertNotIn("opus |", r.stdout.split("| Role |")[1])
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "high", "--machine", "local",
                "--lead", "sonnet")  # the lead fell back to sonnet
        self.assertIn("| pair | prompt | opus | - |", r.stdout)
        args = ["loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "low", "--machine", "local",
                "--json"]
        self.assertEqual(run(*args).returncode, 2)  # needs --base
        data = json.loads(run(*args, "--base", "main", "--trivial").stdout)
        self.assertEqual(([s["id"] for s in data["check"]], data["trivial"], data["base"], data["lead_profile"]),
                         (CHECK, True, "main", "haiku"))
        self.assertEqual(run(*args, "--base", "main", "--lead", "ghost").returncode, 2)
        r = run("loop.py", "render", "--project", "o/r", "--task", "9", "--difficulty", "low", "--machine", "ghost")
        self.assertEqual(r.returncode, 3)


def git_clone(home, name="clone"):
    path = os.path.join(home.root, name)
    subprocess.run(["git", "init", "-q", path], check=True)
    subprocess.run(["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q",
                    "--allow-empty", "-m", "x"], check=True)
    return path, subprocess.run(["git", "-C", path, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


POST_GH = """#!/usr/bin/env python3
import json, os, sys
state = os.environ["FAKE_GH_COMMENTS"]
comments = json.load(open(state)) if os.path.exists(state) else []
args = sys.argv[1:]
if os.environ.get("FAKE_GH_FAIL"):
    sys.exit("gh: HTTP 403")
if args[0] == "api" and args[-1] == "repos/o/r/issues/7/comments?per_page=100":
    print(json.dumps(comments[:1]))
    print(json.dumps(comments[1:]))  # gh prints one array per page
elif args[:3] == ["pr", "comment", "7"] and args[3:5] == ["--repo", "o/r"] and args[5] == "--body-file":
    comments.append({"body": open(args[6]).read()})
    json.dump(comments, open(state, "w"))
    print(f"https://github.com/o/r/pull/7#issuecomment-{len(comments)}")
else:
    sys.exit(1)
"""


class Post(unittest.TestCase):
    """loop.py post: the foreman posts a saved answer on the pull request, whole."""

    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.task = os.path.join(self.home.root, "task")
        self.home.write("task/loop.json", task_loop(difficulty="mid", lead="sonnet"))
        bindir = os.path.join(self.home.root, "bin")
        os.makedirs(bindir)
        with open(os.path.join(bindir, "gh"), "w") as f:
            f.write(POST_GH)
        os.chmod(os.path.join(bindir, "gh"), 0o755)
        self.state = os.path.join(self.home.root, "comments.json")
        self.home.write("comments.json", [{"body": "## Manual test for #12"}])
        self.env = {"PATH": bindir + os.pathsep + os.environ["PATH"], "FAKE_GH_COMMENTS": self.state}
        self.meta = {"role": "redteam", "agent": "redteam-1", "profile": "opus", "model": "opus", "head": "a" * 40,
                     "ended": "2026-11-16T02:00:00.000000Z", "ok": True, "session_id": "s-1"}
        self.answer("must-fix: none\nVerdict: approved")

    def answer(self, text, n=1, **meta):
        self.home.write(f"task/reviews/redteam-1-{n}.json", {"result": text})
        self.home.write(f"task/reviews/redteam-1-{n}.meta.json", {**self.meta, **meta})

    def post(self, *args, **env):
        return run("loop.py", "post", "--task-dir", self.task, "--pr", "7", *args, env={**self.env, **env})

    def comments(self):
        with open(self.state) as f:
            return [c["body"] for c in json.load(f)]

    def test_posts_the_saved_answer_once(self):
        r = self.post("--step", "redteam-review")
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["status"], out["agent"], out["verdict"], out["url"]),
                         ("posted", "redteam-1", "approved", "https://github.com/o/r/pull/7#issuecomment-2"))
        import gate
        body = gate.answer_comment("redteam", "redteam-1", 7, self.meta, "must-fix: none\nVerdict: approved")
        self.assertEqual(self.comments()[1], body)
        r = self.post("--step", "redteam-review")
        self.assertEqual(json.loads(r.stdout)["status"], "posted before")  # found on the second page
        self.assertEqual(len(self.comments()), 2)
        self.answer("must-fix: x\nVerdict: changes", n=2, ended="2026-11-16T03:00:00.000000Z", head="b" * 40)
        r = self.post("--step", "redteam-review")
        self.assertEqual((json.loads(r.stdout)["status"], json.loads(r.stdout)["verdict"]), ("posted", "changes"))
        self.assertIn("must-fix: x", self.comments()[2])  # the latest run of the role

    def test_refusals(self):
        for args, code, words in (
                (["--step", "build"], 2, "build is not a step of a role agent"),
                (["--step", "test"], 1, "no saved qa answer"),
                (["--step", "redteam-review", "--agent", "redteam-2"], 1, "no saved redteam answer"),
                (["--pr", "7"], 2, "post needs --step")):
            r = self.post(*args)
            self.assertEqual(r.returncode, code, args)
            self.assertIn(words, r.stderr)
        self.assertEqual(self.post("--step", "redteam-review", FAKE_GH_FAIL="1").returncode, 1)
        self.answer("Verdict: approved", ok=False)
        r = self.post("--step", "redteam-review")
        self.assertEqual(r.returncode, 1)
        self.assertIn("the last run of redteam-1 failed", r.stderr)
        self.answer("x" * 70000 + "\nVerdict: approved")
        r = self.post("--step", "redteam-review")
        self.assertEqual(r.returncode, 1)
        self.assertIn("one comment holds 65536", r.stderr)
        self.assertEqual(len(self.comments()), 1)  # nothing was posted


class Prompt(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.task = os.path.join(self.home.root, "task")
        self.home.write("task/loop.json", task_loop(difficulty="mid", lead="sonnet"))
        self.clone, self.head = git_clone(self.home)

    def tearDown(self):
        self.home.close()

    def prompt(self, *args, env=None, workdir=None):
        return run("loop.py", "prompt", *args, env=env, workdir=workdir or self.clone)

    def test_a_role_reads_skill_names_without_the_lead_s_notation(self):
        data = task_loop(difficulty="mid", lead="sonnet")
        review = next(s for s in data["work"] if s["id"] == "review")
        review["skills"] = ["code-check (flow and record: foreman-kit:review)"]
        found = loop.role_run(data, self.task, "review", None, self.head, "launch.py")
        self.assertIn("the skill code-check says", found["text"])
        self.assertNotIn("flow and record", found["text"])

    def test_writes_the_filled_prompt_and_prints_the_commands(self):
        r = self.prompt("--step", "review", env={"AF_TASK_DIR": self.task})
        self.assertEqual(r.returncode, 0, r.stderr)
        out = json.loads(r.stdout)
        self.assertEqual((out["agent"], out["prompt"], out["out"]),
                         ("pair-1", os.path.join(self.task, "reviews", "pair-1-1.prompt.md"),
                          os.path.join(self.task, "reviews", "pair-1-1.json")))
        with open(out["prompt"]) as f:
            text = f.read()
        self.assertNotRegex(text, r"<[a-z ]+>")  # every placeholder is filled in
        for words in ("task 7 of o/r", "skill foreman-kit:review", f"Your clone is at {self.head}",
                      f"The task folder is {self.task}", "Review the diff from origin/main to HEAD"):
            self.assertIn(words, text)
        launch = os.path.join(SCRIPTS, "launch.py")
        self.assertEqual(out["commands"][0].split(), [
            "python3", launch, "opus", "--print", "--role", "pair", "--name", "pair-1", "--task-dir", self.task,
            "--prompt-file", out["prompt"], "--out", out["out"], "--no-edit"])
        self.assertEqual(len(out["commands"]), 1)  # the mid and high tiers hold sonnet and opus; sonnet is the lead
        again = json.loads(self.prompt("--step", "review", "--task-dir", self.task).stdout)
        self.assertEqual(os.path.basename(again["prompt"]), "pair-1-2.prompt.md")  # never over an earlier run

    def test_a_loop_json_from_before_no_edit_still_denies_edits(self):
        data = task_loop(difficulty="mid", lead="sonnet")
        for role in data["roles"].values():
            del role["no_edit"]
        data["roles"]["pair"]["deny_tools"] = ["Edit", "Write", "NotebookEdit"]
        found = loop.role_run(data, self.task, "review", None, self.head, "launch.py")
        self.assertTrue(found["commands"][0].endswith(" --no-edit"), found["commands"][0])
        del data["roles"]["pair"]["deny_tools"]
        found = loop.role_run(data, self.task, "review", None, self.head, "launch.py")
        self.assertNotIn("--no-edit", found["commands"][0])

    def test_recheck_reviews_only_what_changed_since_the_last_answer(self):
        r = self.prompt("--step", "recheck", "--task-dir", self.task)
        self.assertEqual(r.returncode, 2)
        self.assertIn("pair-1 has no earlier answer to check against; run step review first", r.stderr)
        self.home.write("task/reviews/pair-1-1.json", {"result": "Verdict: changes"})
        self.home.write("task/reviews/pair-1-1.meta.json", {"role": "pair", "agent": "pair-1", "head": "abc1234",
                                                           "ok": True, "ended": "2026-11-14T01:00:00.000000Z"})
        out = json.loads(self.prompt("--step", "recheck", "--task-dir", self.task).stdout)
        with open(out["prompt"]) as f:
            text = f.read()
        self.assertIn("Review the diff from abc1234 to HEAD: only the fixes and the clean-up since your last review, "
                      f"whose answer is {os.path.join(self.task, 'reviews', 'pair-1-1.json')}", text)

    def test_check_roles_and_a_second_agent(self):
        out = json.loads(self.prompt("--step", "test", "--task-dir", self.task).stdout)
        with open(out["prompt"]) as f:
            text = f.read()
        self.assertIn("full tests: none is set; write `not run: no full test command`", text)
        data = task_loop(config.merge(config.load(), {"tests": {"full": "make test"}}), difficulty="mid", lead="sonnet")
        self.home.write("task/loop.json", data)
        out = json.loads(self.prompt("--step", "test", "--task-dir", self.task).stdout)
        with open(out["prompt"]) as f:
            filled = f.read()
        self.assertIn(f"full tests: python3 {os.path.join(SCRIPTS, 'fulltest.py')} --min-free-gb 20 -- 'make test'.",
                      filled)
        self.home.write("task/loop.json", task_loop(difficulty="mid", lead="sonnet"))
        self.assertIn("Trivial task: no.", text)
        self.assertIn("skills foreman-kit:full, foreman-kit:cross-check say", text)
        self.assertIn("and the base branch is main.", text)  # the full skill compares failures with the base
        self.assertNotIn("<", text.split("Verdict:")[0].replace("<head>", ""))  # every placeholder filled
        self.home.write("task/loop.json", task_loop(difficulty="low"))  # redteam and qa: sonnet, then opus
        out = json.loads(self.prompt("--step", "redteam-review", "--task-dir", self.task, "--agent", "redteam-2").stdout)
        self.assertEqual([c.split()[2] for c in out["commands"]], ["opus", "sonnet"])  # agent 2 starts on the next

    def test_refusals(self):
        for args, words in ((["--step", "build"], "done by the lead, not by a role agent"),
                            (["--step", "nope"], "step 'nope' is not in this task's loop"),
                            (["--step", "review", "--agent", "../x"], "--agent may hold"),
                            (["--step", "review", "--task-dir", os.path.join(self.home.root, "none")], "no readable loop.json"),
                            (["--step", "review", "--task-dir", ""], "needs --step and a task folder")):
            r = self.prompt(*args, **({} if "--task-dir" in args else {"env": {"AF_TASK_DIR": self.task}}))
            self.assertEqual(r.returncode, 2, args)
            self.assertIn(words, r.stderr)
        r = self.prompt("--step", "review", "--task-dir", self.task, workdir=self.home.root)
        self.assertIn("not a git checkout", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.task, "reviews")))


if __name__ == "__main__":
    unittest.main()
