---
name: full
description: >-
  Run the project's full test command at the change's head commit and report
  each failure with its raw output, after checking whether it also fails at
  the base. Edits nothing; launch.py saves the answer in the task folder's
  reviews/. Use by QA in the verification session's test step, with the user
  scenario test.
---

# Full

## Action

1. Check that your clone is at the head commit the prompt names: `git rev-parse HEAD`.
2. Run the full test command the prompt names, as written. Keep its exit code and raw output. When the prompt says none is set, write `not run: no full test command`; that line alone does not fail the verdict. The command runs through `fulltest.py`: it may wait while another task's full tests run on the machine. Exit 75 with `fulltest.py: not run` means the disk is under the floor: write `not run: <command> — disk under the floor`, with that line, and do not free space yourself.
3. A command that cannot run here, because it needs a secret, a service or a machine you do not have: do not pretend it ran. Write it as `not run`, with the reason.
4. A failure: run the same command at the base before you call it new. Inside your clone: `git worktree add .base-check $(git merge-base HEAD origin/<base>)`, run it in `.base-check`, then `git worktree remove --force .base-check`.
5. Fix nothing. Do not edit, commit, or push.

## Flow

- Step `test`, QA. If you cannot finish (the wrong commit, a missing tool): try once more. If it still fails, say what blocked you and end with no Verdict line.

## Record

**Evidence**: your answer is the step's evidence. Give each command with its output, and put the verdict last.

You write no file; you have no edit tools. launch.py saves your final answer, with your model, under `$AF_TASK_DIR/reviews/` (the task folder). QA does this and the user scenario test (`cross-check`) in one run and gives one answer: one list item for each command, the mismatch items, then a blank line and one verdict:

```
- ran: <command> — exit 0
- failure (new): <command or test name> — <what failed>
- failure (also on the base): <command or test name> — <what failed>
- not run: <command> — <reason>

Verdict: fail
```

- Write the command in a `ran:` item exactly as the prompt names it. At merge, the gate takes `- ran: <command> — exit 0` in a passing answer at the head as the full test's run, and does not run it again.
- Under each `ran:` item, a fence with the summary lines as they came. Under each failure, a fence with its full error message and the summary line. Indent the fence two spaces, with a blank line before and after it, so it belongs to its item. Do not retell output in your own words.
- The last line is `Verdict: pass` or `Verdict: fail`, plain, after a blank line, and not a list item. It is `pass` only when every command that is set ran and passed and the user scenario test passed.
