"""The foreman's flow with the tester (SKILL.md, the person's decision of
2026-11-27): every command the verification session and the cleanup name
exists with those flags, a round runs as written with the real scripts, and
the foreman sizes a task against the budget the gate uses."""
import json
import os
import re
import subprocess
import unittest

from helpers import ROOT, SCRIPTS, TempHome, run, task_loop

import config

PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")
SCRIPT = re.compile(r"\b([a-z_]+)\.py\b")
FLAG = re.compile(r"(?<![\w-])--[a-z][a-z-]*")
G = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def read(name):
    with open(os.path.join(PLUGIN, name), encoding="utf-8") as f:
        return f.read()


def section(text, title, until):
    start = text.index(title)
    return text[start:text.index(until, start)]


def commands(text):
    """(script, its first word, its flags) for each script a text names, with
    wrapped lines joined: up to the end of its code span or the next script."""
    flat = " ".join(text.replace("\\\n", " ").split())
    found = []
    for m in SCRIPT.finditer(flat):
        rest = flat[m.end():]
        stop = min([i for i in (rest.find("`"), *(n.start() for n in SCRIPT.finditer(rest))) if i >= 0] or
                   [len(rest)])
        words = rest[:stop].split()
        first = words[0] if words and re.fullmatch(r"[a-z]+", words[0]) else None
        found.append((m.group(1), first, FLAG.findall(rest[:stop])))
    return found


class Commands(unittest.TestCase):
    def usage(self, script):
        r = run(f"{script}.py", "--help", env={"AF_TASK_DIR": "", "AF_STATUS_FILE": ""})
        self.assertIn("usage", (r.stdout + r.stderr).lower(), script)  # remote.py prints its usage and exits 2
        return r.stdout + r.stderr

    def check(self, text, at_least):
        named = [c for c in commands(text) if os.path.isfile(os.path.join(SCRIPTS, f"{c[0]}.py"))]
        self.assertTrue(at_least <= {c[0] for c in named}, {c[0] for c in named})
        for script, first, flags in named:
            usage = self.usage(script)
            if first:
                self.assertIn(first, usage, script)
            for flag in flags:
                self.assertRegex(usage, re.escape(flag) + r"(?![\w-])", f"{script}.py {first or ''} {flag}")

    def test_the_verification_session(self):
        text = section(read("SKILL.md"), "### Verification session\n", "### Merge gate\n")
        self.check(text, {"status", "clone", "launch", "stamp", "loop", "gate", "log", "remote"})
        with self.assertRaises(AssertionError):  # a flag that is only the start of a real one
            self.check(text.replace("--session-id <its session>", "--session <its session>"), set())
        for words in ("clone.py make --project <repo> --task <task> --agent tester --pr <N> --ref <head SHA>",
                      "--stage redteam-review --event start", "--loop check --tester",
                      "Test #<N> at <head SHA>", "--round <k>"):
            self.assertIn(words, " ".join(text.split()))

    def test_the_manage_loop_and_the_cleanup(self):
        std = config.standard()
        verify = next(s for s in std["loop"]["manage"] if s["id"] == "verify-session")["does"]
        self.assertTrue("tester.md" in verify and "stamp.py" in verify, verify)
        tester = [line for line in std["ops"]["after_merge"] if "tester" in line]
        self.assertEqual(len(tester), 1, tester)
        self.check("`" + "` `".join(re.findall(r"`([^`]*)`", tester[0])) + "`", {"clone", "status"})
        self.assertTrue("--agent tester" in tester[0] and "--testing" in tester[0], tester[0])

    def test_the_files_it_names_exist(self):
        skill = read("SKILL.md")
        for name in ("scripts/stamp.py", "tester.md", "loop.md"):
            self.assertIn(f"| `{name}` |", skill)
            self.assertTrue(os.path.isfile(os.path.join(PLUGIN, name)), name)
        ledger = next(line for line in skill.splitlines() if line.startswith("| Task | Difficulty |"))
        self.assertIn("| Tester |", ledger)


class Round(unittest.TestCase):
    """'Each round' 1 to 4, as SKILL.md writes them, with the real scripts on
    one machine: the start line, stamp.py, each step's end line, gate.py record."""

    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        root = self.home.root
        self.home.write("state/agent-foreman/projects/o-r/project.json", {"repo": "o/r", "machines": {"local": root}})
        clone = os.path.join(root, ".cache/agent-foreman/work/o-r/7/tester")
        subprocess.run(["git", "init", "-q", clone], check=True)
        subprocess.run(G + ["-C", clone, "commit", "-q", "--allow-empty", "-m", "head"], check=True)
        self.head = subprocess.run(["git", "-C", clone, "rev-parse", "HEAD"], capture_output=True,
                                   text=True).stdout.strip()
        self.task = os.path.join(root, ".local/state/agent-foreman/tasks/o-r/7")
        self.home.write(".local/state/agent-foreman/tasks/o-r/7/loop.json", task_loop(difficulty="mid", lead="sonnet"))
        self.tester = ".local/state/agent-foreman/testing/o-r/7/reviews"
        self.env = {"HOME": root, "AF_TASK_DIR": "", "AF_STATUS_FILE": ""}

    def script(self, name, *args):
        return run(name, *args, env=self.env)

    def note(self, stage, event, *args):
        r = self.script("status.py", "note", "--file", os.path.join(self.task, "status.jsonl"), "--stage", stage,
                        "--event", event, *args)
        self.assertEqual(r.returncode, 0, r.stderr)
        return r.stdout

    def stamp(self, k):
        r = self.script("stamp.py", "--project", "o/r", "--task", "7", "--head", self.head, "--profile", "opus",
                        "--round", str(k), "--session-id", "s-1", "--from", "local", "--to", "local")
        self.assertEqual(r.returncode, 0, r.stderr)
        return {s["role"]: s for s in json.loads(r.stdout)["stamped"]}

    def end(self, step, stamped):
        out = self.note(step, "end", "--outcome", stamped["verdict"], "--done",
                        f"tester: Verdict {stamped['verdict']}, {stamped['answer']}")
        r = self.script("gate.py", "record", "--step", step, "--task-dir", self.task)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return out

    def test_a_round_sent_back_then_one_that_passes(self):
        self.home.write(f"{self.tester}/redteam-1.md", "- must-fix: a.py:3 — drops a field\n\nVerdict: changes")
        self.note("redteam-review", "start")
        stamped = self.stamp(1)
        self.assertEqual(sorted(stamped), ["redteam"])  # the red team asked for changes: no QA ran
        self.assertIn("build", self.end("redteam-review", stamped["redteam"]))

        self.home.write(f"{self.tester}/redteam-2.md", "- could: a name\n\nVerdict: approved")
        self.home.write(f"{self.tester}/qa-2.md", "- ran: make test — exit 0\n\nVerdict: pass")
        self.note("redteam-review", "start")
        stamped = self.stamp(2)
        self.assertIn("stop", self.end("redteam-review", stamped["redteam"]))
        self.note("test", "start")
        self.assertIn("stop", self.end("test", stamped["qa"]))
        with open(os.path.join(self.task, "status.jsonl")) as f:
            ends = [(r["step"], r["outcome"]) for r in map(json.loads, f) if r["event"] == "end"]
        self.assertEqual(ends, [("redteam-review", "changes"), ("redteam-review", "approved"), ("test", "pass")])


class Size(unittest.TestCase):
    def test_the_budget_the_foreman_sizes_against_is_the_gate_s(self):
        text = " ".join(read("SKILL.md").split())
        self.assertIn("**Size each task before launch.** The budget is `difficulty.lines` added lines", text)
        self.assertIn("A pull request already open is not split.", text)
        register = next(s for s in config.standard()["loop"]["manage"] if s["id"] == "register")["does"]
        self.assertIn("split into tasks under it before launch", register)
        self.assertEqual(task_loop(difficulty="mid")["max_lines"], config.standard()["difficulty"]["lines"])


if __name__ == "__main__":
    unittest.main()
