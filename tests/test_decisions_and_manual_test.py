"""Fewer stops and fewer reruns (the loop rules of 2026-11-27): under the
`decisions: lead` setting the lead takes its recommended option at a decision
point and goes on, and the scenario (the manual test) runs in full once,
with later rounds rerunning only the touched steps in an addendum the gate
reads."""
import os
import re
import unittest

from helpers import ROOT, TempHome

import config
import gate
import loop

PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")
SCENARIO = ("# Scenario: x\n\n### 1 · run it\nWhy.\n\n**Expect** — `ok`\n\n**Do**\n\n```bash\nrun\n```\n\n"
            "**Agent**\n\n```\nok\n```\n\n## Closing\nVerdict: pass\nNothing left up.\n")
PLAN = ("# Plan: x\n\n## Work breakdown\n\n| id | goal | done when | files | test | status | commit |\n"
        "|---|---|---|---|---|---|---|\n| W1 | a | b | c | test-first | done | abc1234 |\n")
HANDOFF = "# Handoff: x\n\n## Purpose\na\n\n## Decisions\nb\n\n## Tests\nc\n\n## Not touched\nd\n\n## Follow-ups\ne\n"


def read(*parts):
    with open(os.path.join(PLUGIN, *parts), encoding="utf-8") as f:
        return f.read()


def addendum(verdict, output="ok", head="b1c2d3e"):
    return (f"\n## Addendum at {head}\n\nVerdict: {verdict}\n- Rerun: steps 1: the change touches run.\n\n"
            f"### 1 · run it\n\n**Agent**\n\n```\n{output}\n```\n")


def kit_name(source, value):
    return "foreman-kit:" + value


class Decisions(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)
        self.cfg = config.load()
        self.resolved = {n: ("kit", n) for n in loop.KIT}
        self.profiles = {r: ["opus"] for r in self.cfg["loop"]["roles"]}

    def brief(self, which="work"):
        return loop.render(self.cfg, "7", "mid", False, self.resolved, self.profiles, kit_name, which)

    def data(self):
        return loop.as_data(self.cfg, "7", "mid", False, self.resolved, kit_name, "o/r", "main", "sonnet",
                            self.profiles)

    def test_the_person_decides_unless_the_setting_says_otherwise(self):
        self.assertEqual(self.data()["decisions"], "person")
        self.assertIn("**Decision points**: the person's. At one, stop and ask", self.brief())
        self.assertNotIn("Decision points", self.brief("check"))  # the verification session is the foreman's

    def test_the_setting_gives_the_lead_its_decision_points(self):
        self.cfg = config.merge(self.cfg, {"loop": {"decisions": "lead"}})
        self.assertEqual(loop.validate_loop(self.cfg["loop"]), [])
        self.assertEqual(self.data()["decisions"], "lead")
        self.assertIn("**Decision points**: yours (`decisions: lead`). At one, take your recommended option, write "
                      "it in plan.md's Decisions and a status line, and go on. Stop only for a merge, an ADR change, "
                      "a secret, data loss, or work outside the task", self.brief())
        self.cfg["loop"]["decisions"] = "foreman"
        self.assertIn("loop: decisions must be one of person, lead", loop.validate_loop(self.cfg["loop"]))

    def test_loop_md_says_what_still_stops_the_lead(self):
        text = read("loop.md")
        rule = re.search(r"\*\*Decision points that are yours\.\*\*(.*?)\n\n", text, re.S).group(1)
        rule = " ".join(rule.split())
        for words in ("take your recommended option at each one", "a decision point after a recheck",
                      "Write the choice and its reason in `plan.md`'s Decisions and in a status line",
                      "--event progress --done \"decision: <choice> — <reason>\"", "and go on.",
                      "Stop only for what needs the person: a merge, a change to an architecture decision record "
                      "(ADR), a secret, data loss, or work outside the task."):
            self.assertIn(words, rule)
        self.assertIn('"Decision points: yours", `decisions: lead` in\n   loop.json', text)


class ManualTest(unittest.TestCase):
    def setUp(self):
        self.home = TempHome()
        self.addCleanup(self.home.close)

    def docs(self, scenario):
        for name, text in (("plan.md", PLAN), ("handoff.md", HANDOFF), ("scenario.md", scenario)):
            self.home.write(f"task/{name}", text)
        return gate.check_docs({}, {"check": "docs"}, {"task_dir": os.path.join(self.home.root, "task")})

    def test_the_guides_run_it_whole_once_and_only_touched_steps_later(self):
        lead = " ".join(read("loop.md").split())
        self.assertIn("The scenario (`scenario.md`, the manual test) runs in full once, up to your first ready. In "
                      "verify of a later round, rerun only the steps whose code the change touches, as an addendum "
                      "that names the head (the `cross-check` skill). QA runs the whole scenario at the final head.",
                      lead)
        skill = read("kit", "skills", "cross-check", "SKILL.md")
        self.assertIn("7. The script runs in full up to your first ready. In round 2 and later, rerun only the steps "
                      "whose code your change since the last run touches", skill)
        self.assertIn("Run every step of the script once, also when an addendum reran it; compare it with its latest "
                      "Agent block", skill)

    def test_the_gate_holds_the_last_addendum_to_a_pass(self):
        self.assertTrue(self.docs(SCENARIO + addendum("pass"))[0])
        ok, evidence = self.docs(SCENARIO + addendum("fail"))
        self.assertEqual((ok, evidence), (False, "scenario.md's last addendum's verdict is not pass"))
        self.assertTrue(self.docs(SCENARIO + addendum("fail") + addendum("pass", head="c2d3e4f"))[0])
        self.assertFalse(self.docs(SCENARIO + addendum("pass") + addendum("fail", head="c2d3e4f"))[0])
        ok, evidence = self.docs(SCENARIO + addendum("pass", output="<what this run printed>"))
        self.assertEqual((ok, evidence), (False, "scenario.md has 1 Agent block(s) with no output"))
        self.assertFalse(self.docs(SCENARIO.replace("Verdict: pass", "Verdict: fail") + addendum("pass"))[0])

    def test_the_verify_record_needs_the_addendum_s_verdict(self):
        self.assertEqual(gate._scenario_run_problems(SCENARIO + addendum("fail")), [])  # a fail is a verdict
        self.assertEqual(gate._scenario_run_problems(SCENARIO + addendum("<pass or fail>")),
                         ["scenario.md's last addendum has no verdict"])

    def test_the_skill_s_addendum_shape_meets_the_gate(self):
        shape = re.search(r"````markdown\n(## Addendum.*?)````", read("kit", "skills", "cross-check", "SKILL.md"),
                          re.S).group(1)
        self.assertFalse(self.docs(SCENARIO + "\n" + shape)[0])  # the template is no run
        filled = shape.replace("Verdict: <pass or fail>", "Verdict: pass").replace("<what this run printed>", "ok")
        ok, evidence = self.docs(SCENARIO + "\n" + filled)
        self.assertTrue(ok, evidence)


if __name__ == "__main__":
    unittest.main()
