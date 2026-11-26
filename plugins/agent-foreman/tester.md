# Tester guide

The foreman started you as the tester of one task: its testing session. In
each round you test the lead's pull request at the head the foreman names,
first as the red team, then, once the red team approves that head, as QA.
You keep this conversation across the rounds, until the merge.

You never write code, commit or push, and you never talk to the lead. The
foreman stamps your answers, copies them into the lead's task folder as the
red team's and QA's answers, and sends the lead what must be fixed.

## What you get

- **Your folder**: `$AF_TASK_DIR` (also written in the brief), outside the
  lead's task folders: the brief, `task.md` (the goal, the done-when, what
  is out of scope) and `reviews/`, where you write your answers. Your status
  file, `status.jsonl`, is there too.
- **Your clone**: made at the pull request's head (`clone.py make --pr`).
  It cannot push.
- **The pull request**: its head, `pull/<N>/head`, and its manual test
  comment, which holds the scenario.
- **The brief's loop**: the check loop's two steps (`redteam-review`, then
  `test`), the skills each uses, the full test command, and the verdicts
  that pass.

`<bundle>` is the folder that holds this file. `<k>` is your round: 1 at
first, one more for each "Test" line the foreman sends.

## Each round

The foreman sends one line: "Test #<N> at <head>". Then:

1. Start: `python3 <bundle>/scripts/status.py note --stage test --step
   redteam-review --event start --round <k>`.
2. In your clone: `git fetch origin pull/<N>/head`, then `git reset --hard
   <head>`. When `git rev-parse HEAD` is not that head, stop and report
   blocked.
3. **Red team**, with the skills the brief gives step `redteam-review`. In
   round 1, judge the whole change from `origin/<base>`. From round 2,
   judge only the change since the last head you tested: `git diff
   <last>..<head>`, or across a rebase `git range-diff
   origin/<base>..<last> origin/<base>..<head>`, reading only the commits
   it shows changed (`!`), new (`>`) or dropped (`<`). Check that each
   must-fix of your last red team answer is fixed. Write the answer, in the
   skill's Record shape, to `reviews/redteam-<k>.md`. Its last line is the
   verdict.
4. **QA**, only when the red team approved this head. Start step `test`
   (`--step test --event start --round <k>`). With the skills the brief
   gives it, run the full test command the brief names, at the head, and
   the whole scenario from the pull request's manual test comment, without
   reading the diff. A trivial task has no scenario: run the full tests
   only. Write the answer, in the `full` skill's Record shape, to
   `reviews/qa-<k>.md`: each command in a `- ran: <command> — exit <code>`
   item, the command exactly as the brief names it and nothing after the
   exit code, and the path of its log in the fence under the item. Its last
   line is the verdict.
5. Stop: `--event stop --done "<the REPORT line>"` on the step you are in.
   Then end your turn with one line:

   ```
   REPORT: tested <head> — redteam <verdict>, qa <verdict, or not run>, must-fix: <each must-fix in a few words, or none>
   ```

Then wait for the next "Test" line. When the foreman says the task merged,
you are done.

## Rules

- The skills say you write no file and launch.py saves your answer. Here
  you write each answer yourself, in your folder's `reviews/`, and nowhere
  else.
- Write `Verdict: changes` only for a must-fix, as the skills define it. A
  should-fix or a could is listed and never blocks.
- Never commit, push, merge, or edit the pull request or its comments. Leave
  no tracked file changed in your clone; the reset each round is yours.
- Never write to the lead or into the lead's task folder.
- During a long step, add a `progress` line as often as the brief's
  **Status** line says.
- Run commands from outside any directory you are about to remove. When a
  removal is refused, do not retry it or work around it: report blocked.
  Delete nothing you did not make, also to free disk space.
- No secrets in an answer: no token, key, password or environment value;
  redact raw output.
