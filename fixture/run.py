#!/usr/bin/env python3
"""Run a task through agent-foreman with real agents, on the made-up project
in fixture/repo, against a local stand-in for GitHub (fixture/bin/gh), and
report whether every step left its evidence.

Usage:
  python3 fixture/run.py [--task 1|2|all] [--dir DIR] [--rounds N] [--scenario NAME,...] [--providers FILE]
                         [--dry-run]

This script plays the foreman's scripted part, as SKILL.md has it: the task
folder, loop.json, the gate and its hash, the brief, the lead's clone, the
verification session, the merge gate and the merge, the archive and the
clean-up. The agents are real: the lead (`claude -p` from the bundle's
launch.py), the pair it starts, the red team and QA, and, at high
difficulty, the foreman's own `plan-check` judgment (`claude -p --model
opus`). Task 1 is mid difficulty; task 2 is high.

It needs `claude` logged in on this machine and network; every run costs
real tokens. --dry-run prepares everything and prints the lead's command,
with no model call.

Settings, the ledger, the log and the bundle live in DIR (default: a new
folder under the system's temporary folder), never in the person's own.
--providers FILE gives the run a providers.json (setup/models.md), such as
one whose mid tier starts with a Codex model; by default the run has the
standard models.
The task folders and clones go where the scripts always put them
(~/.local/state/agent-foreman/tasks/fixture-repo,
~/.cache/agent-foreman/work/fixture-repo) and are removed at the end.

The report (DIR/report.md and DIR/report.json): per task, each step's
evidence line and `gate.py record` result, plan-check's word, the verdicts,
the gate before ready and before merge, the merge, the cost of every agent
run, and every `gh` call the stand-in did not support.

--scenario (repeat it, or give a comma list, or `all`) makes the run take a
path that agents rarely take on their own, so the foreman's handling of it
is tried (SCENARIOS below). The report says, per scenario, whether the run
took the path and whether it ended right.
"""
import argparse
import datetime
import glob
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")
SCRIPTS = os.path.join(PLUGIN, "scripts")
REPO = "fixture/repo"
TASKS = {"1": "mid", "2": "high"}
LEAD_TIMEOUT = 90 * 60
ROLE_TIMEOUT = 30 * 60
GIT = ["git", "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null"]
# Paths that a run takes only when the script makes it, and the task each one is made on.
SCENARIOS = {
    "setup-test": (None, "setup/project.md step 4: run the full test command once in a fresh clone; no model"),
    "plan-back": ("2", "the foreman's first plan-check sends the plan back"),
    "send-back": ("1", "the red team's first answer has a should-fix, so the task goes back to build"),
    "no-verdict": ("1", "QA's first run stops with no Verdict, so the next profile runs once"),
    "disk-floor": ("2", "QA's first full test and one merge gate run are under the disk floor"),
    "lock-wait": ("1", "another holder keeps the full-test lock while the merge gate runs"),
}
LOCK_HOLD = 20
PLAN_BACK = ("This run tests plan-check's send-back path: send the plan back, with at least one concrete thing to "
             "add or change, even when the plan would pass.")
SEND_BACK = ("This run tests the send-back path. Whatever else you find, give at least one should-fix finding: the "
             "weakest point you find in the change, with its evidence.")
NO_VERDICT = ("This run tests what the foreman does when a role stops early. Use no tool. Reply with exactly this "
              "one line and nothing else: Now let me write my own probe test.")
# Every lead run is a new session (launch.py --print takes no --resume), so each word after the first says so.
RESTARTED = "You were restarted: read the brief, plan.md and the last lines of status.jsonl, and go on."


def say(text):
    print(f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {text}", flush=True)


class Run:
    def __init__(self, root, dry_run, scenarios=(), providers=None):
        self.root, self.dry_run, self.scenarios, self.providers = root, dry_run, set(scenarios), providers
        self.env = dict(os.environ)
        self.env.update(XDG_CONFIG_HOME=os.path.join(root, "config"), XDG_STATE_HOME=os.path.join(root, "state"),
                        XDG_CACHE_HOME=os.path.join(root, "cache"), FAKE_GH_STATE=os.path.join(root, "gh.json"),
                        PATH=os.path.join(HERE, "bin") + os.pathsep + os.environ["PATH"])
        for k in ("AF_STATUS_FILE", "AF_AGENT", "AF_TASK_DIR"):
            self.env.pop(k, None)
        self.report = {"started": now(), "root": root, "tasks": {}, "cost": 0.0, "scenarios": {}}
        self.lock = threading.Lock()

    def forced(self, name, task):
        return name in self.scenarios and SCENARIOS[name][0] == task

    # --- plumbing -------------------------------------------------------------
    def sh(self, argv, cwd=None, check=True, timeout=None, stdin=None):
        r = subprocess.run(argv, cwd=cwd, env=self.env, capture_output=True, text=True, timeout=timeout, input=stdin)
        if check and r.returncode != 0:
            raise SystemExit(f"run.py: {' '.join(argv[:4])} failed ({r.returncode}): {(r.stderr or r.stdout)[-600:]}")
        return r

    def script(self, name, *args, cwd=None, check=True, where=SCRIPTS, timeout=None):
        return self.sh([sys.executable, os.path.join(where, name), *args], cwd=cwd, check=check, timeout=timeout)

    def git(self, cwd, *args):
        return self.sh(GIT + ["-C", cwd, *args]).stdout.strip()

    def gh(self, *args, cwd=None):
        return self.sh([os.path.join(HERE, "bin", "gh"), *args], cwd=cwd or self.root).stdout.strip()

    def add_cost(self, value):
        if isinstance(value, (int, float)):
            with self.lock:
                self.report["cost"] = round(self.report["cost"] + value, 4)
        return value

    # --- once per run -----------------------------------------------------------
    def setup(self):
        say(f"run folder {self.root}")
        if shutil.which("claude") is None:
            raise SystemExit("run.py: claude is not on PATH")
        for task in TASKS:  # what an earlier run that stopped halfway left behind
            self.script("clone.py", "remove", "--project", REPO, "--task", task, "--force", check=False)
        self.origin = os.path.join(self.root, "origin", REPO + ".git")
        self.sh(["git", "init", "-q", "--bare", "-b", "main", self.origin])
        seed = os.path.join(self.root, "seed")
        materialize(os.path.join(HERE, "repo"), seed)
        self.git(seed, "init", "-q", "-b", "main")
        self.git(seed, "config", "user.email", "fixture@example.invalid")
        self.git(seed, "config", "user.name", "fixture")
        self.git(seed, "add", "-A")
        self.git(seed, "commit", "-q", "-m", "Start the stock project")
        self.git(seed, "push", "-q", self.origin, "main")
        self.checkout = os.path.join(self.root, "checkout")
        self.sh(["git", "clone", "-q", self.origin, self.checkout])
        with open(self.env["FAKE_GH_STATE"], "w") as f:
            json.dump({"repo": REPO, "origin": self.origin, "ci": "make test", "default_branch": "main",
                       "tasks_dir": os.path.join(HERE, "tasks"), "prs": {}, "next": 1}, f)
        project = os.path.join(self.env["XDG_STATE_HOME"], "agent-foreman", "projects", REPO.replace("/", "-"))
        os.makedirs(project, exist_ok=True)
        with open(os.path.join(project, "project.json"), "w") as f:
            json.dump({"repo": REPO, "workspace": "repo", "machines": {"local": self.checkout},
                       "tests": {"full": "make test"}, "post_answers": True}, f)
        if self.providers or "no-verdict" in self.scenarios:
            with open(self.providers or os.path.join(PLUGIN, "providers.json.sample")) as f:
                models = json.load(f)
            if "no-verdict" in self.scenarios:  # the standard tiers give QA one profile; the rule needs a next one
                models["tiers"]["high"] = models["tiers"]["high"] + ["haiku"]
            os.makedirs(os.path.join(self.env["XDG_CONFIG_HOME"], "agent-foreman"), exist_ok=True)
            with open(os.path.join(self.env["XDG_CONFIG_HOME"], "agent-foreman", "providers.json"), "w") as f:
                json.dump(models, f, indent=2)
        out = json.loads(self.script("bundle.py", "push", "local", "--project", REPO).stdout)
        self.bundle = out["path"]
        say(f"bundle {out['hash']} with {len(out['skills'])} skills")
        if "setup-test" in self.scenarios:
            self.setup_test()

    def setup_test(self):
        """setup/project.md "4. Run the full test command once": a clone at the default branch, the command run
        in it, a failing command that must fail, and the clone removed."""
        made = self.script("clone.py", "make", "--project", REPO, "--task", "setup", "--agent", "tests", "--ref",
                           "origin/main", "--no-push", "--machine", "local", check=False)
        if made.returncode != 0:
            self.report["scenarios"]["setup-test"] = {"took": False, "ok": False,
                                                      "note": f"clone.py make failed: {made.stderr.strip()[-200:]}"}
            return
        clone = json.loads(made.stdout)["path"]
        good = self.script("remote.py", "local", "--cwd", clone, "--", "sh", "-c", "make test", check=False)
        bad = self.script("remote.py", "local", "--cwd", clone, "--", "sh", "-c", "make no-such-target", check=False)
        gone = self.script("clone.py", "remove", "--project", REPO, "--task", "setup", "--agent", "tests",
                           "--machine", "local", check=False)
        removed = gone.returncode == 0 and not os.path.exists(clone)
        self.report["scenarios"]["setup-test"] = {
            "took": True, "ok": good.returncode == 0 and bad.returncode != 0 and removed,
            "note": f"make test exit {good.returncode}; a wrong command exit {bad.returncode}; clone removed: {removed}"}
        say(f"scenario setup-test: {self.report['scenarios']['setup-test']['note']}")

    # --- one task ---------------------------------------------------------------
    def task(self, task, rounds):
        difficulty = TASKS[task]
        rec = self.report["tasks"][task] = {"difficulty": difficulty, "lead_runs": [], "roles": [], "steps": {}}
        task_dir = os.path.expanduser(self.script("status.py", "dir", "--project", REPO, "--task", task).stdout.strip())
        os.makedirs(task_dir, exist_ok=True)
        shutil.copy(os.path.join(HERE, "tasks", f"{task}.md"), os.path.join(task_dir, "task.md"))
        lead = json.loads(self.script("config.py", "tier", "--difficulty", difficulty, "--role", "lead").stdout)["pick"]
        rec["lead_profile"] = lead
        render = ["--project", REPO, "--task", task, "--difficulty", difficulty, "--machine", "local", "--lead", lead]
        loop_json = os.path.join(task_dir, "loop.json")
        with open(loop_json, "w") as f:
            f.write(self.script("loop.py", "render", *render, "--base", "main", "--json").stdout)
        gate_json = os.path.join(task_dir, "gate.json")
        with open(gate_json, "w") as f:
            f.write(self.script("gate.py", "template", "--loop", loop_json).stdout)
        sha = self.script("gate.py", "hash", gate_json).stdout.strip()
        brief = os.path.join(task_dir, "brief.md")
        with open(brief, "w") as f:
            f.write(self.brief(task, difficulty, task_dir, self.script("loop.py", "render", *render).stdout))
        clone = json.loads(self.script("clone.py", "make", "--project", REPO, "--task", task, "--agent", "lead",
                                       "--ref", "origin/main").stdout)["path"]
        rec.update(task_dir=task_dir, clone=clone)
        say(f"task {task} ({difficulty}): lead on {lead}, clone {clone}")
        if self.dry_run:
            rec["lead_command"] = self.launch_argv(lead, task, task_dir, self.prompt(task_dir, "start"),
                                                   os.path.join(self.root, f"lead-{task}-1.json"))
            say("dry run: " + " ".join(rec["lead_command"]))
            rec["result"] = "dry run"
            return self.finish(task, rec)

        word = f"Read {brief} and do what it says."
        for n in range(1, 8):  # the lead runs until it reports ready, a decision or blocked
            out = self.lead(task, lead, task_dir, clone, word, n)
            kind = out["report"].split()[1] if out["report"].startswith("REPORT:") else "none"
            if kind == "waiting":
                word = self.plan_check(task, task_dir, rec)
                if word is None:
                    rec["result"] = "the foreman's plan-check wrote no end line"
                    return self.finish(task, rec)
                continue
            break
        if kind != "ready":
            rec["result"] = f"the lead stopped with {out['report'] or 'no report'}"
            return self.finish(task, rec)

        for round_ in range(1, rounds + 1):
            pr = self.gh("pr", "view", "--json", "number", "-q", ".number", cwd=clone)
            rec["pr"] = pr
            self.steps(rec, task_dir, clone)
            ready = self.gate(gate_json, pr, clone, task_dir, sha, before_ready=True)
            rec.setdefault("gate_before_ready", []).append(ready)
            if not ready["pass"]:
                rec["result"] = f"the gate before ready blocks: {ready['blocked']}"
                return self.finish(task, rec)
            back = self.verification(task, task_dir, clone, pr, rec, round_)
            if back is None:
                break
            if round_ == rounds:
                rec["result"] = f"still sent back after {rounds} round(s)"
                return self.finish(task, rec)
            findings = self.findings(task_dir, round_)
            out = self.lead(task, lead, task_dir, clone,
                            f"Read {findings} and go back to {back} with --round {round_ + 1}. {RESTARTED}",
                            len(rec["lead_runs"]) + 1)
            if not out["report"].startswith("REPORT: ready"):
                rec["result"] = f"the lead stopped with {out['report'] or 'no report'}"
                return self.finish(task, rec)

        if self.forced("disk-floor", task):
            rec["gate_under_floor"] = self.gate_under_floor(gate_json, rec["pr"], clone, task_dir)
        held = self.hold_lock(LOCK_HOLD) if self.forced("lock-wait", task) else None
        started = time.time()
        merge = self.gate(gate_json, rec["pr"], clone, task_dir, sha, before_ready=False)
        if held:
            held.join()
            rec["lock_wait"] = {"held_seconds": LOCK_HOLD, "gate_seconds": round(time.time() - started, 1)}
        rec["gate_merge"] = merge
        unmatched = self.plan_check_unmatched(task, task_dir)
        if unmatched:
            rec["result"] = f"plan-check: {unmatched}"
        elif merge["pass"]:
            head = json.loads(self.gh("pr", "view", rec["pr"], "--json", "headRefOid,headRefName"))
            self.script("log.py", "add", "--project", REPO, "--event", "merge-gate", "--task", task,
                        "--data", json.dumps({"head": head["headRefOid"], "pass": True, "gate_hash": sha}))
            self.gh("pr", "merge", rec["pr"], "--squash")
            rec["merged"] = True
            rec["result"] = "merged"
            self.branch = head["headRefName"]
        else:
            rec["result"] = f"the merge gate blocks: {merge['blocked']}"
        return self.finish(task, rec)

    def brief(self, task, difficulty, task_dir, loop_md):
        return "\n".join([
            "1. Run commands from outside any directory you remove; a refused removal is reported, never retried "
            "or worked around.",
            f"2. Read `{task_dir}/task.md`. The base branch is main. Difficulty: {difficulty} (the foreman's call "
            f"for this task). Trivial: no.",
            f"3. repo: {REPO}; task: {task}; task folder: {task_dir}",
            f"4. Follow `{self.bundle}/loop.md`.",
            "5. The loop:", "", loop_md, "",
            f"6. The gate: in finalize, run `{self.bundle}/scripts/gate.py run {task_dir}/gate.json --pr <N> "
            f"--cwd <your clone> --task-dir {task_dir} --before-ready`.",
            "7. This brief confirms the whole loop.", ""])

    def prompt(self, task_dir, name):
        return os.path.join(task_dir, f"lead-{name}.prompt.md")

    def launch_argv(self, profile, task, task_dir, prompt, out):
        return [sys.executable, os.path.join(self.bundle, "scripts", "launch.py"), profile, "--print",
                "--prompt-file", prompt, "--out", out, "--name", task, "--task-dir", task_dir]

    def lead(self, task, profile, task_dir, clone, word, n):
        status = os.path.join(task_dir, "status.jsonl")
        before = len(rows(status))
        prompt = self.prompt(task_dir, str(n))
        with open(prompt, "w") as f:
            f.write(word + "\n")
        out = os.path.join(self.root, f"lead-{task}-{n}.json")
        say(f"task {task}: lead run {n}: {word}")
        try:
            r = self.sh(self.launch_argv(profile, task, task_dir, prompt, out), cwd=clone, check=False,
                        timeout=LEAD_TIMEOUT)
            summary = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"ok": False}
        except subprocess.TimeoutExpired:
            summary = {"ok": False, "error": f"no end after {LEAD_TIMEOUT // 60} minutes"}
        text = ""
        try:
            with open(out) as f:
                text = json.load(f).get("result", "")
        except (OSError, ValueError):
            pass
        report = next((l.strip() for l in reversed(text.splitlines()) if l.strip().startswith("REPORT:")), "")
        source = "answer"
        if not report:  # SKILL.md "Watch": the stop line's done holds the report
            report, source = report_from_status(rows(status)[before:]), "status"
        entry = {"run": n, "word": word, "ok": summary.get("ok"), "cost": self.add_cost(summary.get("cost")),
                 "report": report, "report_from": source if report else None, "error": summary.get("error")}
        self.report["tasks"][task]["lead_runs"].append(entry)
        say(f"task {task}: lead run {n} ended: {report or summary.get('error') or 'no report'}"
            f"{' (no REPORT line; from the status file)' if report and source == 'status' else ''} "
            f"(cost {summary.get('cost')})")
        return entry

    def plan_check(self, task, task_dir, rec):
        """The foreman's own judgment at plan-check, by a model, as SKILL.md has it. Returns the word for the
        lead, or None when the foreman wrote no new end line for plan-check."""
        say(f"task {task}: plan-check by the foreman")
        status = os.path.join(task_dir, "status.jsonl")
        before = len([r for r in rows(status) if r.get("step") == "plan-check" and r.get("event") == "end"])
        force = self.forced("plan-back", task) and not rec.get("plan_check")
        prompt = (f"You are the foreman of agent-foreman for project {REPO}. Read {PLUGIN}/SKILL.md, the section "
                  f"\"Evidence at every step\", and do the plan-check for task {task} now: its lead is waiting. The "
                  f"task folder is {task_dir}, and the lead's clone is {rec['clone']}. Run the scripts with python3 "
                  f"from {SCRIPTS}. Do all that section says for plan-check, its end line with `status.py note "
                  f"--file {task_dir}/status.jsonl` and its log event included, except sending the lead its line: "
                  f"this script sends it. Start no agent and message none. {PLAN_BACK + ' ' if force else ''}"
                  f"End with one line: `PLAN-CHECK: go — <why>` or `PLAN-CHECK: back — <what is missing>`.")
        # The prompt goes on stdin: --disallowedTools takes every value after it, a prompt argument too.
        r = self.sh(["claude", "-p", "--model", "opus", "--dangerously-skip-permissions", "--output-format", "json",
                     "--disallowedTools", "Bash(gh pr merge:*)"], cwd=self.root, check=False, timeout=ROLE_TIMEOUT,
                    stdin=prompt)
        try:
            data = json.loads(r.stdout)
        except ValueError:
            data = {"result": (r.stdout + r.stderr)[-500:]}
        self.add_cost(data.get("total_cost_usd"))
        line = next((l.strip() for l in reversed(str(data.get("result", "")).splitlines())
                     if l.strip().startswith("PLAN-CHECK:")), "")
        ends = [row for row in rows(status) if row.get("step") == "plan-check" and row.get("event") == "end"]
        new = ends[-1] if len(ends) > before else None
        rec.setdefault("plan_check", []).append({"line": line, "cost": data.get("total_cost_usd"), "end_line": new,
                                                 "answer": str(data.get("result", ""))[-2000:], "forced": force})
        say(f"task {task}: {line or 'no PLAN-CHECK line'}")
        if new is None:
            return None
        go = new.get("outcome") == "go"
        why = line.split("—", 1)[1].strip() if "—" in line else ""
        return ("The foreman says: Go on to build. " if go else f"The foreman says: Go back to plan: {why}. ") + RESTARTED

    def plan_check_unmatched(self, task, task_dir):
        """SKILL.md "Merge gate": the last plan-check end line and the foreman's last plan-check event both say
        go for the same round. Returns what differs, or "" (also when the loop has no plan-check)."""
        with open(os.path.join(task_dir, "loop.json")) as f:
            if not any(s["id"] == "plan-check" for s in json.load(f)["work"]):
                return ""
        ends = [r for r in rows(os.path.join(task_dir, "status.jsonl"))
                if r.get("step") == "plan-check" and r.get("event") == "end"]
        out = self.script("log.py", "tail", "--project", REPO, "--event", "plan-check", "--task", task, "-n", "1")
        logged = [json.loads(l)["data"] for l in out.stdout.splitlines() if l.strip()]
        line = (ends[-1].get("outcome"), str(ends[-1].get("round"))) if ends else None
        event = (logged[-1].get("outcome"), str(logged[-1].get("round"))) if logged else None
        if line is None or line != event or line[0] != "go":
            return f"the end line says {line}, the foreman's log says {event}"
        return ""

    def steps(self, rec, task_dir, clone):
        """Each step's evidence line, and gate.py record on it, as the foreman does when a step ends."""
        ended = {}
        for row in rows(os.path.join(task_dir, "status.jsonl")):
            if row.get("event") == "end":
                ended[row.get("step")] = row
        for step, row in ended.items():
            r = self.script("gate.py", "record", "--step", step, "--task-dir", task_dir, "--cwd", clone, check=False)
            try:
                out = json.loads(r.stdout)
            except ValueError:
                out = {"ok": False, "checks": [{"check": "record", "ok": False, "evidence": r.stderr.strip()[-300:]}]}
            rec["steps"][step] = {"evidence": row.get("done", ""), "outcome": row.get("outcome"), "record_ok": out["ok"],
                                  "missing": [c["evidence"] for c in out.get("checks", []) if not c["ok"]]}

    def gate(self, gate_json, pr, clone, task_dir, sha, before_ready):
        r = self.script("gate.py", "run", gate_json, "--pr", str(pr), "--cwd", clone, "--task-dir", task_dir,
                        "--sha", sha, *(["--before-ready"] if before_ready else []), check=False)
        try:
            out = json.loads(r.stdout)
        except ValueError:
            return {"pass": False, "blocked": ["gate.py failed"], "error": r.stderr.strip()[-300:]}
        return {"pass": out["pass"], "blocked": out["blocked"],
                "warned": [c["check"] for c in out["checks"] if not c["ok"] and c["severity"] == "warn"]}

    def gate_under_floor(self, gate_json, pr, clone, task_dir):
        """The merge gate once with the full tests' disk floor above any disk: it must block `command` with
        `fulltest.py: not run`. A copy of the gate file, so the task's own file and its hash stay as they are."""
        with open(gate_json) as f:
            data = json.load(f)
        for c in data["checks"]:
            if c.get("full"):
                c["min_free_gb"] = 1000000
        copy = os.path.join(self.root, f"gate-under-floor-{os.path.basename(os.path.dirname(gate_json))}.json")
        with open(copy, "w") as f:
            json.dump(data, f)
        r = self.script("gate.py", "run", copy, "--pr", str(pr), "--cwd", clone, "--task-dir", task_dir, check=False)
        try:
            out = json.loads(r.stdout)
        except ValueError:
            return {"blocked": [], "evidence": r.stderr.strip()[-300:]}
        evidence = next((c["evidence"] for c in out["checks"] if c["check"] == "command"), "")
        say(f"gate under the disk floor: blocked {out['blocked']}: {evidence[:120]}")
        return {"blocked": out["blocked"], "evidence": evidence}

    def hold_lock(self, seconds):
        """Another holder of this machine's full-test lock (fulltest.py), for `seconds`. Returns the thread, once
        it holds the lock."""
        import fcntl
        path = os.path.join(self.env["XDG_CACHE_HOME"], "agent-foreman", "locks", "full-test.lock")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        held = threading.Event()

        def hold():
            with open(path, "a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                lock.seek(0)
                lock.truncate()
                lock.write(json.dumps({"task": "the lock-wait scenario"}))
                lock.flush()
                held.set()
                time.sleep(seconds)

        t = threading.Thread(target=hold)
        t.start()
        held.wait()
        say(f"scenario lock-wait: holding the full-test lock for {seconds}s")
        return t

    def verification(self, task, task_dir, clone, pr, rec, round_):
        """The red team and QA at once, as SKILL.md's verification session. Returns the work step to go back
        to, or None."""
        base = self.gh("pr", "view", str(pr), "--json", "baseRefOid", "-q", ".baseRefOid")
        head = self.gh("pr", "view", str(pr), "--json", "headRefOid", "-q", ".headRefOid")
        with open(os.path.join(task_dir, "loop.json")) as f:
            check_steps = json.load(f)["check"]
        results = {}

        def one(step):
            try:
                run_role(step)
            except (Exception, SystemExit) as e:  # one role's failure is reported, not lost in its thread
                results[step["id"]] = {"role": step["actor"], "verdict": "", "outcome": None, "error": str(e)[-300:]}

        def run_role(step, earlier=()):
            role = step["actor"]
            made = json.loads(self.script("clone.py", "make", "--project", REPO, "--task", task, "--agent",
                                          f"{role}-1", "--from", clone, "--ref", head, "--fresh", "--no-push",
                                          "--instructions-from", base).stdout)
            prompt = json.loads(self.script("loop.py", "prompt", "--step", step["id"], "--task-dir", task_dir,
                                            cwd=made["path"], where=os.path.join(self.bundle, "scripts")).stdout)
            self.script("status.py", "note", "--file", os.path.join(task_dir, "status.jsonl"), "--stage",
                        step["stage"], "--step", step["id"], "--event", "start", "--round", str(round_))
            with open(prompt["prompt"]) as f:
                every = prompt_text = f.read()
            first, forced = every, []
            if round_ == 1 and not earlier:
                if role == "redteam" and self.forced("send-back", task):
                    first = every = every.rstrip() + "\n\n" + SEND_BACK + "\n"
                    forced.append("send-back")
                if role == "qa" and self.forced("disk-floor", task):
                    first = every = re.sub(r"--min-free-gb \S+", "--min-free-gb 1000000", every)
                    forced.append("disk-floor")
                if role == "qa" and self.forced("no-verdict", task):
                    first = NO_VERDICT + "\n"
                    forced.append("no-verdict")
            summary, text, attempts, i = {"ok": False}, "", list(earlier), 0
            while i < len(prompt["commands"]):
                with open(prompt["prompt"], "w") as f:  # the prompt file keeps what the last run got
                    f.write(first if i == 0 else every)
                say(f"task {task}: {step['id']} by {role}" + (f" (forced: {', '.join(forced)})" if forced and (
                    i == 0 or every != prompt_text) else ""))
                r = self.sh(["bash", "-c", prompt["commands"][i]], cwd=made["path"], check=False, timeout=ROLE_TIMEOUT)
                summary = json.loads(r.stdout.strip().splitlines()[-1]) if r.stdout.strip() else {"ok": False}
                self.add_cost(summary.get("cost"))
                text = ""
                try:
                    with open(summary.get("out", "")) as f:
                        text = json.load(f).get("result", "")
                except (OSError, ValueError):
                    pass
                attempts.append({"command": i, "exit": r.returncode, "verdict": summary.get("verdict") or "",
                                 "stopped_early": stopped_early(r.returncode, summary.get("verdict"), text),
                                 "disk_not_run": disk_not_run(text), "forced": forced if i == 0 else [],
                                 "cost": summary.get("cost"), "tail": text[-300:]})
                action = after_run(r.returncode, summary.get("verdict"), text,
                                   any(a["stopped_early"] for a in attempts[:-1]))
                if action == "next":
                    if r.returncode != 5:
                        say(f"task {task}: {step['id']}: no Verdict anywhere in the answer; the next command, once")
                    i += 1
                    continue
                break
            if disk_not_run(text) and not earlier:
                say(f"task {task}: {step['id']}: the full tests did not run (disk floor); {role} again")
                return run_role(step, attempts)  # SKILL.md: not QA's finding; free space and start it again
            verdict = summary.get("verdict") or ""
            outcome = outcome_of(verdict, text)
            results[step["id"]] = {"role": role, "verdict": verdict, "outcome": outcome,
                                   "cost": summary.get("cost"), "answer": summary.get("out"), "attempts": attempts}
            if outcome in step["next"]:
                self.script("status.py", "note", "--file", os.path.join(task_dir, "status.jsonl"), "--stage",
                            step["stage"], "--step", step["id"], "--event", "end", "--outcome", outcome, "--round",
                            str(round_), "--done", f"{role}-1: Verdict {verdict}, {summary.get('out')}")
                posted = self.script("loop.py", "post", "--step", step["id"], "--task-dir", task_dir, "--pr", str(pr),
                                     check=False, where=os.path.join(self.bundle, "scripts"))
                results[step["id"]]["posted"] = (json.loads(posted.stdout)["status"] if posted.returncode == 0
                                                 else f"not posted: {posted.stderr.strip()[-200:]}")

        threads = [threading.Thread(target=one, args=(s,)) for s in check_steps]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        rec["roles"].append({"round": round_, **results})
        self.steps(rec, task_dir, clone)
        backs = [s["next"].get(results.get(s["id"], {}).get("outcome")) for s in check_steps]
        backs = [b for b in backs if b and b != "stop"]
        if any(r["outcome"] not in s["next"] for s in check_steps for r in [results.get(s["id"], {"outcome": None})]):
            rec["note"] = "a role gave no verdict its step knows"
        order = [s["id"] for s in json.load(open(os.path.join(task_dir, "loop.json")))["work"]]
        return min(backs, key=order.index) if backs else None

    def findings(self, task_dir, round_):
        lines = []
        for answer in sorted(glob.glob(os.path.join(task_dir, "reviews", "*.json"))):
            if answer.endswith(".meta.json"):
                continue
            try:
                with open(answer) as f:
                    text = json.load(f).get("result", "")
            except (OSError, ValueError, AttributeError):
                continue
            lines += [l for l in text.splitlines()
                      if re.match(r"\s*[-*]?\s*(must-fix|should-fix|mismatch)", l, re.I)]
        path = os.path.join(task_dir, "reviews", f"findings-r{round_}.md")
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        return path

    def judge(self, task, rec):
        """Per forced scenario of this task: whether the run took the path, and whether it ended right."""
        roles = rec.get("roles") or [{}]
        first = roles[0]
        merged = bool(rec.get("merged"))
        for name, (on, _) in SCENARIOS.items():
            if not self.forced(name, task):
                continue
            if name == "plan-back":
                pc = rec.get("plan_check") or [{}]
                took = (pc[0].get("end_line") or {}).get("outcome") == "back"
                ok, note = took and merged, " / ".join(p["line"][:80] for p in pc)
            elif name == "send-back":
                took = first.get("redteam-review", {}).get("verdict") == "changes"
                ok, note = took and len(roles) >= 2 and merged, f"{len(roles)} verification round(s)"
            elif name == "no-verdict":
                tries = first.get("test", {}).get("attempts", [])
                took = bool(tries) and tries[0]["stopped_early"]
                ok = took and len(tries) >= 2 and bool(first.get("test", {}).get("verdict"))
                note = "; ".join(f"command {a['command']}: exit {a['exit']}, verdict {a['verdict'] or 'none'}"
                                 for a in tries) + ("" if len(tries) > 1 else "; no next command: to the person")
            elif name == "disk-floor":
                tries = first.get("test", {}).get("attempts", [])
                floor = rec.get("gate_under_floor", {})
                took = any(a["disk_not_run"] for a in tries) and floor.get("blocked") == ["command"]
                ok = took and "fulltest.py: not run" in floor.get("evidence", "") and merged
                note = (f"QA runs: {len(tries)}, disk not run in run "
                        f"{[i for i, a in enumerate(tries) if a['disk_not_run']]}; gate: {floor.get('blocked')}")
            else:  # lock-wait
                wait = rec.get("lock_wait", {})
                took = wait.get("gate_seconds", 0) >= LOCK_HOLD - 1
                ok, note = took and rec.get("gate_merge", {}).get("pass", False), str(wait)
            self.report["scenarios"][name] = {"task": task, "took": took, "ok": ok, "note": note}
            say(f"scenario {name}: took the path: {took}; ended right: {ok}; {note}")

    def finish(self, task, rec):
        if not self.dry_run:
            self.judge(task, rec)
        self.script("clone.py", "archive", "--project", REPO, "--task", task, check=False)
        removed = self.script("clone.py", "remove", "--project", REPO, "--task", task, check=False)
        if removed.returncode != 0 or json.loads(removed.stdout or "{}").get("refused"):
            self.script("clone.py", "remove", "--project", REPO, "--task", task, "--force", check=False)
            rec["cleanup"] = "forced: " + (removed.stdout.strip()[-200:] or removed.stderr.strip()[-200:])
        if getattr(self, "branch", None):
            self.sh(["git", "--git-dir", self.origin, "branch", "-D", self.branch], check=False)
            self.branch = None
        try:
            os.rmdir(os.path.dirname(rec["task_dir"]))
        except (KeyError, OSError):
            pass
        say(f"task {task}: {rec.get('result')}")

    def write_report(self):
        with open(self.env["FAKE_GH_STATE"]) as f:
            gh = json.load(f)
        self.report["gh_unsupported"] = [{"argv": c["argv"], "agent": c["agent"]} for c in gh.get("unsupported", [])]
        self.report["gh_calls"] = len(gh.get("log", []))
        if not self.dry_run:
            r = self.script("retro.py", "facts", "--project", REPO, check=False)
            self.report["retro"] = json.loads(r.stdout) if r.returncode == 0 else {"error": r.stderr[-300:]}
            for task, rec in self.report["tasks"].items():  # the pair's runs, which the lead started
                rec["pair_cost"] = 0.0
                for raw in glob.glob(os.path.join(self.report["root"], "state", "agent-foreman", "projects",
                                                  "fixture-repo", "tasks", task, "reviews", "pair-*.json")):
                    if raw.endswith(".meta.json"):
                        continue
                    try:
                        rec["pair_cost"] += json.load(open(raw)).get("total_cost_usd") or 0
                    except (OSError, ValueError, AttributeError):
                        pass
        self.report["ended"] = now()
        with open(os.path.join(self.root, "report.json"), "w") as f:
            json.dump(self.report, f, indent=2, ensure_ascii=False)
        md = [f"# Fixture run {self.report['started']}", "", f"Total cost of the runs the script started: "
              f"${self.report['cost']}", ""]
        for task, rec in self.report["tasks"].items():
            md += [f"## Task {task} ({rec['difficulty']}, lead {rec.get('lead_profile')})", "",
                   f"- Result: {rec.get('result', 'dry run' if self.dry_run else '?')}",
                   f"- Lead runs: " + "; ".join(f"{r['run']}: {r['report'] or r.get('error') or 'no report'}"
                                                 for r in rec["lead_runs"])]
            if rec.get("pair_cost") is not None:
                md.append(f"- The pair's runs cost ${round(rec['pair_cost'], 4)}")
            for pc in rec.get("plan_check", []):
                last = next((l.strip() for l in reversed(pc["answer"].splitlines()) if l.strip()), "")
                line = pc["line"] or f"no PLAN-CHECK line (the answer's last line: {last[:200]})"
                md.append(f"- plan-check: {line}; end line: {(pc['end_line'] or {}).get('outcome')}")
            for r in rec["roles"]:
                md.append(f"- Round {r['round']}: " + "; ".join(
                    f"{k} {v['verdict'] or 'no verdict'}" + (f" ({v['error']})" if v.get("error") else "")
                    + (f", {v['posted']}" if v.get("posted") else "")
                    for k, v in r.items() if k != "round"))
            for key in ("gate_before_ready", "gate_merge"):
                if rec.get(key):
                    md.append(f"- {key}: {rec[key]}")
            if rec["steps"]:
                md += ["", "| Step | Outcome | Evidence | Record |", "| --- | --- | --- | --- |"]
                for step, s in rec["steps"].items():
                    md.append(f"| {step} | {s['outcome']} | {s['evidence'].replace('|', '/')} | "
                              f"{'ok' if s['record_ok'] else '; '.join(s['missing']).replace('|', '/')} |")
            md.append("")
        if self.report["scenarios"]:
            md += ["## Scenarios", "", "| Scenario | Task | What it forces | Took the path | Ended right | Note |",
                   "| --- | --- | --- | --- | --- | --- |"]
            md += [f"| {n} | {r.get('task') or '-'} | {SCENARIOS[n][1]} | {r['took']} | {r['ok']} | "
                   f"{str(r['note']).replace('|', '/')} |" for n, r in self.report["scenarios"].items()]
            md.append("")
        md += ["## gh calls the stand-in did not support", ""]
        md += [f"- {c['agent'] or '?'}: gh {' '.join(c['argv'])}" for c in self.report["gh_unsupported"]] or ["- none"]
        with open(os.path.join(self.root, "report.md"), "w") as f:
            f.write("\n".join(md) + "\n")
        say(f"report: {os.path.join(self.root, 'report.md')}")


def report_from_status(new_rows):
    """The lead's report from the status lines its run wrote, for an answer with no REPORT line (SKILL.md
    "Watch": the stop line's done holds the report). The work loop's last step ends with `to: stop`: ready."""
    for r in reversed(new_rows):
        if r.get("event") == "end" and r.get("to") == "stop":
            return f"REPORT: ready — {r.get('step')} ended: {r.get('done', '')}"
        if r.get("event") == "stop":
            done = str(r.get("done", ""))
            kind = next((k for k in ("ready", "decision", "blocked", "waiting") if done.lower().startswith(k)), None)
            return f"REPORT: {kind or ('blocked' if r.get('blocked') else 'decision')} — {done}"
    return ""


def after_run(code, verdict, text, stopped_before):
    """What the foreman does after one role run (SKILL.md "Verification session", step 3): "next" runs the next
    command (exit 5, or a first early stop), "done" goes on; the disk floor goes on too, and is handled after."""
    if code == 5:
        return "next"
    if disk_not_run(text):
        return "done"
    return "next" if stopped_early(code, verdict, text) and not stopped_before else "done"


def stopped_early(code, verdict, text):
    """SKILL.md "Verification session": exit 0 with no verdict and no `Verdict` anywhere in the answer means the
    agent stopped before its end."""
    return code == 0 and not verdict and "verdict" not in (text or "").lower()


def disk_not_run(text):
    """The full tests did not run because the disk was under the floor (fulltest.py exit 75)."""
    return "fulltest.py: not run" in (text or "") or "disk under the floor" in (text or "").lower()


def outcome_of(verdict, text):
    """A QA `fail` whose mismatches are all `(script)` is the outcome `script` (SKILL.md "Verification session").
    A mismatch is a line or a list item that starts with `mismatch`."""
    lines = [l for l in text.splitlines() if re.sub(r"^[-*+]\s+", "", l.strip()).lower().startswith("mismatch")]
    return "script" if (verdict == "fail" and lines and all("(script)" in l for l in lines)) else verdict


def now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rows(path):
    out = []
    try:
        with open(path) as f:
            for line in f:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    except OSError:
        pass
    return out


def materialize(src, dest):
    """Copy the fixture project: `dot-x` becomes `.x`, and `.fixture` leaves a file's name."""
    for folder, _, names in os.walk(src):
        rel = os.path.relpath(folder, src)
        parts = [] if rel == "." else ["." + p[4:] if p.startswith("dot-") else p for p in rel.split(os.sep)]
        os.makedirs(os.path.join(dest, *parts), exist_ok=True)
        for name in names:
            if name == "__pycache__" or name.endswith(".pyc"):
                continue
            shutil.copy2(os.path.join(folder, name), os.path.join(dest, *parts, name.replace(".fixture", "")))


def main(argv):
    ap = argparse.ArgumentParser(prog="run.py", description=__doc__.split("\n\n")[0])
    ap.add_argument("--task", default="all", choices=["all", *TASKS])
    ap.add_argument("--dir", help="the run folder (default: a new temporary one)")
    ap.add_argument("--rounds", type=int, default=2, help="verification rounds before it gives up (default 2)")
    ap.add_argument("--scenario", action="append", default=[], metavar="NAME,...",
                    help=f"force a path: {', '.join(SCENARIOS)}, or all")
    ap.add_argument("--providers", metavar="FILE", help="the run's providers.json (default: the standard models)")
    ap.add_argument("--dry-run", action="store_true", help="prepare everything; call no model")
    args = ap.parse_args(argv)
    scenarios = {n.strip() for v in args.scenario for n in v.split(",") if n.strip()}
    scenarios = set(SCENARIOS) if "all" in scenarios else scenarios
    unknown = sorted(scenarios - set(SCENARIOS))
    if unknown:
        ap.error(f"unknown scenario {', '.join(unknown)}; known: {', '.join(SCENARIOS)}, all")
    skipped = sorted(n for n in scenarios if SCENARIOS[n][0] and args.task not in ("all", SCENARIOS[n][0]))
    if skipped:
        ap.error(f"{', '.join(skipped)} run on another task than --task {args.task}")
    root = os.path.abspath(args.dir) if args.dir else tempfile.mkdtemp(prefix="agent-foreman-fixture.")
    if os.path.exists(root) and os.listdir(root):
        raise SystemExit(f"run.py: {root} is not empty")
    os.makedirs(root, exist_ok=True)
    if args.providers and not os.path.isfile(args.providers):
        ap.error(f"no providers file at {args.providers}")
    run = Run(root, args.dry_run, scenarios, os.path.abspath(args.providers) if args.providers else None)
    run.setup()
    try:
        for task in (TASKS if args.task == "all" else [args.task]):
            run.task(task, args.rounds)
    finally:
        run.write_report()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
