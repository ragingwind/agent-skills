---
name: cross-check
description: >-
  Write a scenario script that a person can follow alone to see the task's
  result as a user sees it, run it in a fresh clone and fill each step with the
  real output, and later run it again as a user, without the diff, and compare.
  Writes scenario.md in the task folder. Use in the build session's plan step
  to write the script (for a bug, reproduce it first), in its verify step to
  run it, and by QA in the verification session's test step for the user
  scenario test.
---

# Cross-check

One script, run twice. The lead's run shows that the script is right and the product works. QA's run shows that a user who follows it gets the same result.

## Action

**Write (step `plan`, lead).**
1. For each done-when in `$AF_TASK_DIR/task.md` (the task folder), plan the steps that show it as a user sees it: a command, a page, a file.
2. For a bug, reproduce it on the real surface before any fix. Those steps are the first draft.
3. Write the preamble and the steps in the shape under Record. Write each Expect now, before any run. It must be something a broken build would not show.
4. One step is one act with one result. Every command is complete and ready to paste. A value that a later step needs goes through a file in the start directory, not a shell variable. A step that depends on its folder starts with its own `cd`.
5. A page: use the project's browser test tool when it has one, and put its command in the Do fence. Only when there is none, write a hand act (see Record) and list the step under Not verified.
6. Bringing the environment up is a step. Taking it down is a step. Leave every Agent block empty.

**Run (step `verify`, lead).**
1. Make a fresh clone at your head: `python3 <bundle>/scripts/clone.py make --project <repo> --task <task> --agent scenario --from <your clone> --ref <head SHA> --fresh --no-push`. Run the script in the `path` it prints.
2. Search the script for what only your machine has: a literal port, `/Users/` or `/home/`, a `<...>` that no step prints, `...` in place of a command. Fix each one.
3. Run the steps in order, exactly as written. Paste each output into its Agent block, word for word, with secrets masked.
4. Anything you did that the script does not say (a wait, an install, a variable) is a missing step. Add it, and run again from step 1.
5. A step fails. A script problem: fix the script and run again from step 1. A product problem: see Flow.
6. Take down what you brought up. Write `## Closing`. Remove the clone from outside it: `clone.py remove --project <repo> --task <task> --agent scenario`.
7. The script runs in full up to your first ready. In round 2 and later, rerun only the steps whose code your change since the last run touches, and the steps that bring the environment up and take it down. Write them in an addendum after `## Closing` (see Record), and keep the earlier Agent blocks and the Closing as they are.

**User scenario test (step `test`, QA).**
1. Read the done-when in `$AF_TASK_DIR/task.md` and `$AF_TASK_DIR/scenario.md`. Check that the script covers each done-when; a done-when it does not cover is a `script` mismatch. Do not read the diff, plan.md, or the code.
2. Start in your own clone at the head commit, in the start directory the preamble names.
3. Run each step's Do as written. Fill a placeholder only from what an earlier step printed.
4. Compare your output with the Expect and the Agent block. A value that changes per machine (a port, a path, a time, an id) is not a mismatch. Run every step of the script once, also when an addendum reran it; compare it with its latest Agent block, the one in the last addendum that reran it.
5. A mismatch is a different result, a step you could not do as written, or a value the script did not say where to get. Name its cause: `script` (the script left out something), `environment` (your machine, data or permissions differ), or `product` (the product behaves differently).
6. Run the steps that take things down, even after a mismatch. Change nothing the script does not tell you to change.

## Flow

- A trivial task (the brief says so) has no scenario: skip this skill in every step.
- Step `plan`: after `work-breakdown`. Then the plan step ends with outcome `done`.
- Step `verify`: after `unit` and `smoke`. Every Agent block filled and `Verdict: pass` → the verify step ends with outcome `done`. A product problem → it ends with outcome `fail` (back to build, with the fix as a new row in plan.md).
- Step `test` (QA): if you cannot run the script at all, try once more; if it still fails, say what blocked you and end with no Verdict line.

## Record

**Evidence** for the step's `end` line: in plan, `cross-check: scenario.md <n> steps`; in verify, `cross-check: scenario.md run, Verdict: <pass or fail>`, or in a later round `cross-check: scenario.md addendum at <head>, steps <n, ...>, Verdict: <pass or fail>`.

The plan and verify steps write `$AF_TASK_DIR/scenario.md` in this shape:

````markdown
# Scenario: <task title>

Start directory: <the root of a clone at the head commit>
Environment: <the one command that brings it up>

### 1 · <the act, not the command>

<One line: why this step is here.>

**Expect** — <a quoted line, a count, a named result>

**Do**

```bash
<the command>
```

**Agent**

```
<what the last full run printed>
```

## Closing

Verdict: <pass or fail>
- Brought up: <what>. Brought down: <how; it is gone>.
- Not verified: <what no step checks, or "nothing">.
````

- With nothing to bring up, write `Environment: none — <reason>`.
- A hand act writes one imperative sentence after `**Do** —` in place of the fence, naming the control and the page.
- The first line under `## Closing` is `Verdict: pass` or `Verdict: fail`, for the last full run. The gate blocks until it is `pass` and every Agent block holds real output.
- A later round's rerun goes at the end of the file, one addendum per run, in this shape. The gate also blocks until the last addendum's verdict is `pass`:

````markdown
## Addendum at <head SHA>

Verdict: <pass or fail>
- Rerun: steps <n, ...>: the change since <the last run's head> touches <what>.

### <n> · <the act, as in the script>

**Agent**

```
<what this run printed>
```
````
- The test step writes no file. launch.py saves QA's answer under `$AF_TASK_DIR/reviews/`. Each mismatch is one list item, `- mismatch (script|environment|product): step N — <what differed>`, with a fence of the differing output under it, indented two spaces. The answer ends with a blank line and one plain line that is not a list item, `Verdict: pass` (every step ran and matched) or `Verdict: fail`.
