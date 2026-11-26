"""The standard settings and the docs against the loop rules of 2026-11-27:
the judging prompts block only on a must-fix, as the review skills do, and
the settings and checks the series added are written down with the values
the code uses."""
import os
import re
import unittest

from helpers import ROOT, TempHome, task_loop

import config
import gate
import loop

PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")


def read(*path):
    with open(os.path.join(PLUGIN, *path), encoding="utf-8") as f:
        return " ".join(f.read().split())


class Prompts(unittest.TestCase):
    def setUp(self):
        self.std = config.standard()["loop"]

    def test_a_judging_prompt_blocks_only_on_a_must_fix(self):
        for role in ("review", "redteam"):
            prompt = self.std["prompts"][role]
            self.assertIn("changes only when a must-fix finding exists, as the skill defines it. A should-fix or "
                          "could finding is listed and never makes changes.", prompt, role)
            self.assertNotIn("should-fix finding exists", prompt, role)
        for skill in ("review", "redteam-review"):  # the skills the prompts name say the same
            self.assertIn("Write `changes` only when a must-fix exists. Should-fix and could items are listed and "
                          "never make `changes`", read("kit", "skills", skill, "SKILL.md"), skill)

    def test_the_fix_step_fixes_must_fix_and_leaves_the_rest_to_the_follow_up_issue(self):
        does = next(s for s in self.std["work"] if s["id"] == "fix")["does"]
        self.assertTrue(does.startswith("Fix the pair's must-fix findings."), does)
        self.assertIn("each should-fix and could left open goes to the follow-up issue (loop.md)", does)
        self.assertIn("Keep what you leave open in one follow-up issue per pull request", read("loop.md"))


class Settings(unittest.TestCase):
    def test_setup_names_the_new_settings_with_the_code_s_values(self):
        text = read("setup", "loop.md")
        self.assertIn(f"a role's `recheck_limit`, {loop.RECHECK_LIMIT} when it is not set", text)
        self.assertIn("`\"decisions\"` in `loop`, `person` (the standard) or `lead`", text)
        self.assertEqual(loop.DECIDERS, ["person", "lead"])
        home = TempHome()
        self.addCleanup(home.close)
        cfg = config.load()
        self.assertEqual(loop.validate_loop(cfg["loop"]), [])
        self.assertEqual(loop.validate_loop(dict(cfg["loop"], decisions="nobody")),
                         ["loop: decisions must be one of person, lead"])


class Architecture(unittest.TestCase):
    def setUp(self):
        self.text = read("ARCHITECTURE.md")

    def test_rechecks_are_counted(self):
        self.assertNotIn("no script counts rechecks", self.text)
        self.assertIn("`loop.py prompt` counts the rechecks in `status.jsonl`", self.text)

    def test_size_blocks_in_a_new_task(self):
        self.assertIn("`loop.py render` writes `block` for every new task; a loop.json from before it warns",
                      self.text)
        self.assertNotIn("`size` (a warning)", self.text)
        new = task_loop(difficulty="mid")  # loop.py render --json, as for a new task
        self.assertEqual(new["size_severity"], "block")
        older = {k: v for k, v in new.items() if k != "size_severity"}
        for data, severity in ((new, "block"), (older, "warn")):
            size = next(c for c in gate.template(data)["checks"] if c["check"] == "size")
            self.assertEqual(size["severity"], severity)

    def test_the_full_tests_run_once_per_head(self):
        self.assertIn("The full test command's check takes QA's passing run at the exact head", self.text)
        self.assertTrue(re.search(r"with a `- ran: <command> — exit 0` item", self.text))


if __name__ == "__main__":
    unittest.main()
