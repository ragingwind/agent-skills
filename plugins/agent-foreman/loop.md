# Lead guide

The foreman started you as the lead of one task. You run the task's build
session in your own clone: plan → build → verify → review → finalize. Then
the foreman runs the verification session (a red team and QA) on other
models. When they find something, the foreman sends you back into the build
session.

## Evidence at every step

**No step ends without evidence.** Every step's `end` line names the skills
the step ran and where each skill's record is. The foreman checks that line.
Examples:

```
--done "work-breakdown: plan.md 4 rows; cross-check: scenario.md 6 steps"
--done "tdd, commit: W1 3f2a9c1, W2 8b1d0e4, W3 c07e5aa"
--done "unit: plan.md Checks 3 entries, all pass; smoke: 1 entry; cross-check: scenario.md run, Verdict: pass"
--done "review: pair-1, Verdict: changes, reviews/pair-1-1.json"
--done "handoff: handoff.md; pull request #12 ready; gate passed"
```

`status.py note` refuses an `end` line without evidence. Before the task
goes on, the foreman checks each skill's record against your line (`gate.py
record`). When a record is missing, the foreman asks you about it or sends
you back to the step. A project skill in the table counts the same way. Its
own result, such as commits or a pull request, goes in the line, with the
record of the default skill it replaces.

Evidence names files, counts and commits. Do not copy a program's output
into it; name the file and the step or line that holds the output. To
correct a step's evidence, write its `end` line again with the same outcome
and the corrected `--done`. The last `end` line of a step counts.

## What you get

- **The task folder**: `$AF_TASK_DIR` (also written in the brief). Every
  record of the task goes there and nowhere else: `task.md` (the goal, the
  done-when, what is out of scope), `plan.md`, `scenario.md`, `handoff.md`,
  `reviews/`, `status.jsonl`, and `loop.json`.
- **The loop table** in the brief: each stage, its steps, who acts, what it
  does, the skill each step uses, and where each outcome goes.
- **The gate file** (`gate.json` in the task folder). Do not edit it or
  `loop.json`; the gate blocks when either changed.

You have approval for every step in the brief: do not stop between steps to
ask whether to go on. The one exception is a step that the table gives to
the foreman (`plan-check`, at high difficulty). At that step, stop and wait.

**At the start, and again after your conversation is summarized**: read the
brief, `plan.md` if it exists, and the last lines of `status.jsonl`. When
`plan.md` exists, do not plan again; go on from the step the last line names.

## Each step

`<bundle>` is the folder that holds this file.

1. Start it:

   ```bash
   python3 <bundle>/scripts/status.py note --stage <stage> --step <step> --event start [--round <N>]
   ```

   It refuses a stage or step that is not in your loop, renames your tab,
   and prints what the step does.
2. Do it with the skills the table names. A skill's **Action** says how,
   its **Flow** says which outcome to end with, and its **Record** says what
   to write in the task folder and in what shape. A skill shown as `<skill>
   (flow and record: <default skill>)` replaces that default skill's action.
   Do the work the way `<skill>` says. Then end with the default skill's
   Flow, and write the default skill's Record. When a skill starts its own
   agents, write `progress` lines while they work.
3. End it with the outcome that happened, one of the step's `Next` keys in
   the table:

   ```bash
   python3 <bundle>/scripts/status.py note --stage <stage> --step <step> --event end --outcome <outcome> --done "<evidence>"
   ```

   The command refuses an outcome the step does not have. It also refuses
   an `end` line without evidence ("Evidence at every step"). It prints the
   next step. Go there. When it says the next step is the foreman's, stop
   there. Write a stop line (`--event stop --done "waiting: <what the
   foreman checks>"`) and report `waiting`. The foreman tells you where to
   go on.

During a long step, add a `--event progress` line as often as the table's
**Status** line says. No line for as long as it says counts as a stall. The
gate blocks until every step before finalize has an `end` line.

`--round` is the build session's pass: 1 at first; the foreman gives the next
number when it sends the task back.

## Steps another agent does (the pair)

The review stage's `review` and `recheck` steps are the pair's: another
model reviews your diff. You start it; you never review your own work in
its place, and you never use your own subagents for it. The gate reads the
pair's answer from `reviews/` and refuses an answer from your own model.

1. Give the pair its own clone at your head. Its agent-instruction files
   come from the base:

   ```bash
   python3 <bundle>/scripts/clone.py make --project <repo> --task <task> --agent pair-1 \
     --from <your clone> --ref <head SHA> --fresh --no-push --instructions-from <base SHA>
   ```

   To get the base SHA before the pull request exists, run `git rev-parse
   origin/<base>`. Once the pull request exists, run `gh pr view <N> --json
   baseRefOid -q .baseRefOid`.

2. From inside the `path` it prints:
   `python3 <bundle>/scripts/loop.py prompt --step <review or recheck>`. It
   writes the pair's prompt into `reviews/` from `loop.json` and prints JSON
   with `commands`. Do not write or change the prompt yourself.
3. Run the first command there and wait. Exit 5 (a usage limit or a gateway
   error): run the next one. None is ever on your own profile.
4. The last line it prints has `verdict`. In `review`, end the step with
   `done` whatever the verdict. In `recheck`, end it with the verdict as the
   outcome (`approved` or `changes`). No verdict: run it once more; then stop
   as blocked.

After the third `recheck` that still says `changes`, stop at a decision
point.

## Finalize and the gate

Follow the `handoff` skill: rebase, write `handoff.md`, push and open a draft
pull request whose body is `handoff.md`, wait for its checks to finish (`gh
pr checks <N> --watch`), then run the gate in your clone:

```bash
python3 <bundle>/scripts/gate.py run <task folder>/gate.json --pr <N> --cwd <your clone> \
  --task-dir <task folder> --before-ready
```

Exit 0: `gh pr ready <N>`, end the finalize step with `done`, and report
`ready`. Exit 6: fix what it lists under `blocked` and run it again. A check
you think is wrong goes in your report.

## When the verification session finds something

The foreman sends you a file with the red team's and QA's findings, the step
to go back to (build, or verify when only the scenario script was wrong) and
the next `--round`. Start that step with that round. In build, each finding
you fix is a new row in `plan.md` (the `work-breakdown` skill). Then go
through the steps after it again, up to finalize. The gate's verdicts must
all be for your new head commit.

## Stop points

Stop only at these, and report:

1. **Ready**: finalize passed the gate and the pull request is marked ready.
   The finalize `end` line is the stop line.
2. **A decision for the person**: a choice that changes what a user or
   caller sees, an interface, a schema or file format, or a core module, and
   that the task does not settle. Write the question with your recommended
   option and its reason, keep working on everything that does not depend on
   it, and stop when nothing else is left. Put each decision in your
   `REPORT: decision` (or a file it names): what is decided, the options,
   each option's cost, and your recommendation. The foreman asks the person
   with a question dialog and relays the answer; a review request you post
   on GitHub records the decision, but the person does not answer there.
3. **Blocked**: something you cannot get or do, after trying once more.
4. **Waiting for the foreman**: the next step is the foreman's (`plan-check`,
   at high difficulty). Write the stop line on that step (`--step
   plan-check`). Only the foreman writes that step's `end` line. When the
   foreman tells you to wait for something else, write the stop line on
   your current step, with `--done "waiting: <for what>"`.

For a decision, blocked or waiting, write the stop line yourself:

```bash
python3 <bundle>/scripts/status.py note --stage <current stage> --step <current step> --event stop \
  --done "<the REPORT line>" [--blocked "<what you need>"]
```

Never merge. The foreman merges after the gate, and `gh pr merge` is denied
to you. Decide any other question inside the task's scope with the option
you would recommend, also a question that a skill asks you. Write each
decision in `plan.md`'s Decisions in one line, with its reason.

## Report

At a stop point, after the stop line, end your turn with one line:

```
REPORT: <ready | decision | blocked | waiting> — <one line: the pull request, the verdicts and rounds, or what you need>
```

## Records

- Everything about the task goes in the task folder. A project skill in the
  table may also write its own records, such as labels and issue or pull
  request comments. Apart from those, nothing goes in issue or pull request
  comments except the pull request body.
- No secrets: no token, key, password or environment value in any record;
  redact raw output.
- No AI attribution in any git or GitHub text.

## Removals

Run commands from outside any directory you are about to remove. When a
removal is refused, do not retry it or work around it: write the exact paths
under `--blocked` in the status file and go on with what does not need them.
Remove only what your run made. When the disk is full, do not free space by
removing anything else, such as another clone: report `blocked` with the
free space.

## Clean-up

Remove what your run made: build directories, containers and volumes of
stacks it started, temporary directories, and the pair's and the scenario's
clones (`clone.py remove --project <repo> --task <task> --agent <pair-1 or
scenario>`). Keep your clone, the branch and the task folder; the foreman
archives and removes them after the merge.
