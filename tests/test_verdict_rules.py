"""Only a must-fix sends a change back (the loop rules of 2026-11-27): the
pair's and the red team's skills share one definition of a must-fix and give
`Verdict: changes` for it alone; a finding outside the goal never blocks; and
the lead keeps what is left open in one follow-up issue per pull request."""
import os
import re
import unittest

from helpers import ROOT

import gate
import retro

PLUGIN = os.path.join(ROOT, "plugins", "agent-foreman")
REVIEWERS = ("review", "redteam-review")
MUST_FIX = ["a done-when of task.md that is not met", "a behavior bug that a user or a caller would hit",
            "a security or isolation hole", "lost data", "a weakened test",
            "a rule of the project's guides broken in code this change adds"]


def read(*parts):
    with open(os.path.join(PLUGIN, *parts), encoding="utf-8") as f:
        return f.read()


def skill(name):
    return read("kit", "skills", name, "SKILL.md")


def bullet(text, start):
    """The one list item of `text` that starts with `start`, without the dash."""
    found = [line[2:] for line in text.splitlines() if line.startswith("- " + start)]
    if len(found) != 1:
        raise AssertionError(f"{len(found)} list items start with {start!r}")
    return found[0]


def section(text, heading):
    return re.search(rf"^## {re.escape(heading)}\n(.*?)(?=^## |\Z)", text, re.M | re.S).group(1)


class Verdicts(unittest.TestCase):
    def test_both_reviewers_define_a_must_fix_the_same_way(self):
        for name in REVIEWERS:
            kinds = bullet(skill(name), "`must-fix`, and nothing else: ").split(": ", 1)[1].rstrip(".").split("; ")
            self.assertEqual(kinds, MUST_FIX, name)

    def test_only_a_must_fix_makes_changes(self):
        for name in REVIEWERS:
            rule = bullet(skill(name), "The last line is `Verdict: approved` or `Verdict: changes`")
            self.assertIn("Write `changes` only when a must-fix exists.", rule, name)
            self.assertIn("never make `changes`: with no must-fix, approve.", rule, name)
            self.assertNotIn("should-fix exists", skill(name), name)
            example = re.search(r"## Record.*?\n```\n(.*?)```", skill(name), re.S).group(1)
            has_must_fix = any(line.startswith("- must-fix:") for line in example.splitlines())
            self.assertEqual(gate.last_verdict(example) == "changes", has_must_fix, name)

    def test_a_finding_outside_the_goal_never_blocks(self):
        for name in REVIEWERS:
            rule = bullet(skill(name), "A finding outside task.md's done-when and its epic's goal")
            self.assertIn("starts its text with `outside the goal:`", rule, name)
            self.assertIn("It is a `should-fix` or a `could`, whatever its weight, unless it is a security hole or "
                          "lost data.", rule, name)
        # the retro still counts such a finding under the severity it was given
        self.assertEqual(retro.findings("- should-fix: outside the goal: docs/a.md:3 — wording\nVerdict: approved"),
                         [("should-fix", "should-fix: outside the goal: docs/a.md:3 — wording")])

    def test_a_recheck_holds_the_change_to_its_must_fix_only(self):
        step = re.search(r"^5\. Step `recheck` only: (.*)$", skill("review"), re.M).group(1)
        self.assertIn("check each earlier must-fix.", step)
        self.assertNotIn("should-fix. It is fixed", step)
        self.assertIn("the lead keeps it in the pull request's follow-up issue", step)


class FollowUpIssue(unittest.TestCase):
    def test_the_lead_keeps_one_issue_per_pull_request(self):
        rules = section(read("loop.md"), "Follow-up issue")
        for words in ('Title it "Follow-ups from #<PR>"', "the labels the brief names", "update the same issue",
                      "each should-fix and could item you did not fix", "`file:line`", "the review file that raised it",
                      "under `## Follow-ups`", "Never start a round or a\n  recheck for one."):
            self.assertIn(words, rules)

    def test_the_pull_request_body_links_it(self):
        handoff = skill("handoff")
        self.assertIn("the link to the pull request's follow-up issue", handoff)
        self.assertIn('(`loop.md` "Follow-up issue")', handoff)  # test_kit checks that the heading exists
        self.assertRegex(handoff, r'gh pr edit <number> --body-file "\$AF_TASK_DIR/handoff.md"')
        self.assertIn("except the pull request body and the follow-up issue", read("loop.md"))

    def test_the_lead_fixes_every_must_fix_and_parks_the_rest(self):
        back = section(read("loop.md"), "When the verification session finds something")
        self.assertIn("Fix every\nmust-fix and mismatch; a should-fix or could you do not fix goes to the\nfollow-up "
                      "issue.", back)


if __name__ == "__main__":
    unittest.main()
