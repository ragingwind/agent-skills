# Part: loop

The build session's loop (`work`) and the verification session's loop
(`check`): their stages and steps, who acts in each step, the skill each step
uses, and how the loops change with a task's difficulty. Also the foreman's
management loop, the epic loop, and the project's own gate checks. They are
saved at the person's level (every project) or at a project's level.

Each step's action is a default skill (`kit/skills/<name>`). A project's skill
or the person's skill can take a step at one of three levels:

| Level | What it does | Saved as |
| --- | --- | --- |
| Replace the action | Does the default skill's work its own way. The default skill's flow (the outcome to end with) and record (what to write in the task folder) still apply. The brief shows both, as `cross-e2e (flow and record: foreman-kit:cross-check)` | `skills`: `{"cross-check": "cross-e2e"}` |
| Add to the step | Runs beside the default skill, such as the project's review criteria for the pair | the step's `skills` |
| Run the step | An orchestrator that does several things itself, such as a project skill that implements an issue up to a pull request, in `build` | the step's `does` and `skills`. The `does` says: run the skill up to its stop before merge, with its non-interactive options. Then do what the skill does not: mark each `plan.md` row done with its commit, and write `progress` lines while the skill's own agents work |

No skill takes over a whole loop or stage. The gate needs every step's `end`
line and the task folder's records, and the verdicts before ready come from
other models.

A loop is a list of steps: who acts, what it does, the skills it uses, and
where each outcome goes. Consecutive steps with the same `stage` form a
stage; tab labels, status lines and reports follow the stages.

## 1. Detect

- `python3 <skill>/scripts/loop.py show [--project <repo>] --loop work` (and
  `check`): each step with its stage, actor, skills and next step,
  and what runs at low, mid and high.
- Skill candidates:
  - the project's own skills and commands (`.claude/skills/*`,
    `.claude/commands/*.md`) on one of its machines, and where each current
    step's skill would come from:
    `python3 <skill>/scripts/loop.py skills --project <repo> --machine <label>`;
  - the person's skills: `python3 <skill>/scripts/config.py skills`;
  - plugin directories that this session loads and the settings do not have
    yet, and plugins installed on this machine but not enabled here, such as
    one installed for another project:
    `python3 <skill>/scripts/config.py plugin-dir-candidates`. Before anything
    is saved, list their skills: `python3 <skill>/scripts/config.py skills
    --plugin-dir <dir>` (repeat the option for each directory). Scripts start
    a bare `claude`, so they find those skills only through `plugin_dirs`.
- What each candidate does: read its `SKILL.md`, or a command's file, in full,
  not only its description. A project's skill is at `<checkout>/.claude/...`
  on that machine. A person's skill is at the path that `config.py skills`
  prints.
- The project's guides: `CLAUDE.md`, `AGENTS.md`, its rules folder, its
  contributing file, its CI files, and its `Makefile` or `package.json`
  scripts. Note each rule they state for a step: branch names, commit format,
  the tests to run, how and by whom a pull request merges, which changes the
  person approves.

## 2. Fit each step

Do this always, also when no one asked for it. For each step of `work` and
`check`, and for the foreman's register and merge steps, go through this list
in order:

1. **The project has a skill or command for it** (the same name, or the same
   work): a candidate, at the level that fits.
2. **The project has none**: ask with AskUserQuestion whether to look in the
   person's own skills. The options are `Search my skills` (recommended) and
   `Keep the default`. On search, ask which skills the person mostly uses for
   this kind of work. Offer a multi-select of the person's skills found in
   "1. Detect" that come closest, closest first. Read the chosen skills, and
   fit them the same way.
3. **No skill, but the guides state a rule for the step**: the rule becomes
   a line in the step's `does`, a project gate check ("4. Project gate"), or
   a line in the project's `memory.md`. The merge method goes in
   `memory.md`. The classes of change the person approves become
   `difficulty` patterns, so those tasks are high and the person merges
   them.
4. **Nothing**: the default skill.

Check each candidate against this list, and show the person what you found:

| The candidate | The rule |
| --- | --- |
| merges a pull request | Bound to no step. The foreman merges after the gate, and every agent is denied `gh pr merge`. The candidate's merge method goes in `memory.md` |
| makes worktrees, or needs the primary checkout on the default branch | Bound to no step. Each agent works in its own clone |
| starts its own reviewers or testers | An overlap ("3. Overlaps") |
| pushes after the pair's review | Only in a step before `review`. A later push moves the head, and the verdicts must be at the head |
| asks the person midway | Bound with its non-interactive options in `does`. A question it still asks is a decision stop |
| writes labels or pull request comments | Allowed, as the project's own records. A label is never a verdict |
| calls a script by a path under `~` | Test that path on each machine. A missing script is the person's to fix |

Then ask with AskUserQuestion: one question per step that has a candidate, up
to four per call. Offer `Keep: <what it uses now>` first, then each candidate
with its level and where it comes from. When the step still has a default that
nobody chose, recommend the candidate that fits with no conflict. Otherwise,
recommend `Keep`.

## 3. Overlaps

A bound skill may do work that another step also does. Examples are its own
reviewers and the pair's review, its own brief and `plan`, its own finalizer
and `finalize`, and its own test run and `verify`. Show every overlap in one
table: the two, what each does, and the cost of each choice (time, tokens,
what is lost). Then ask with AskUserQuestion, one question per overlap. The
options are to keep one or to keep both. Recommend keeping the one that does
the work better, so the work is done once.

The verdicts from other models (the pair, the red team, QA) stay in every
option. When the project's review is the better one, it becomes the role's
skill (the `skills` of `review` and `recheck`). Then the review runs once, on
another model. A project's QA procedure becomes the QA role's skill the same
way. A role agent reads such a skill as the base branch has it (`clone.py
make --instructions-from`), so the change under review cannot rewrite the
skill.

## 4. Project gate

The standard gate always runs (`ARCHITECTURE.md` "8. Gates"). The project can
add its own checks:

- A script it has for a pull request, such as a closing-keyword check or a
  body-format check.
- A check its guides require that CI does not run, such as a lint or format
  check that changes no file.
- A label that its skills set.

Each one is a named command check in the project's `gate`:

```json
"gate": [
  {"check": "command", "name": "pr-body", "from_base": "scripts/check-pr-body.sh", "at": "merge"},
  {"check": "command", "name": "lint", "run": "make lint-check"},
  {"check": "command", "name": "done-label", "run": "gh pr view \"$AF_PR\" --json labels -q '.labels[].name' | grep -qx status:done", "severity": "warn"}
]
```

- A command runs in the lead's clone with `AF_REPO`, `AF_PR`, `AF_TASK`,
  `AF_TASK_DIR`, `AF_BASE`, `AF_BASE_SHA` (the base branch's head on GitHub)
  and `AF_HEAD` set.
- A script from the repository is a `from_base` check. The gate takes the
  script from `AF_BASE_SHA` itself and runs it. A script that the gate cannot
  get blocks. Never `run` a repository script, or a script that reads
  `origin/...`, because the lead can change its own clone and its refs. In
  the script, name commits by `AF_BASE_SHA` and `AF_HEAD`. Make the script
  fail on an empty or unreadable range.
- `"at": "merge"` runs a check only at the merge gate. `"severity": "warn"`
  reports without blocking. A label that an agent sets itself is always
  `warn`, because it proves only that the agent said so.
- A name is lower-case letters, digits and `-`. It is used once, and it is
  not a standard check's name. The name stands for the check in the report
  and in `--skip`.

Ask with AskUserQuestion (multi-select), with each check you found. Put the
ones that a guide or CI requires first.

## 5. Ask about the rest once

Show the work loop's table. Ask with AskUserQuestion (multi-select): `Keep:
the loop as shown` (recommended); stages and steps (names, which steps a
stage holds, add or remove a step); skills a step uses besides its default
one; what each difficulty runs and the roles (mode, prompt). When the person
changes anything here, ask the scope too: this project only (recommended when
this setup has a project), or the standard for every project.

Go into the chosen parts only.

## 6. Change

- **Stages**: show the steps in order with what each does, and let the
  person type each stage's name and the steps it holds (as
  `<name> <first>-<last>` by row number). Write the name into each of its
  steps' `stage`. A stage's steps stay together, and a stage may not take the
  name of a step in another stage; step ids stay as they are. Labels per
  stage (`labels.events`) move to the new names.
- **Replace a default skill** (step 2): save the choice in `skills`
  (`"<default name>": "<skill>"`). Remove the entry to go back to the
  default.
- **Skills per step**: an extra skill a step uses besides its default one.
  For each step the person picks, `Keep: <its skills now>` first, then the
  project's skills, then the person's. Save the bare name (`cross-e2e`).
  Where it comes from is decided per machine when a task starts. Save the full
  `plugin:skill` only when the bare name matches more than one of the
  person's skills. A skill from a plugin directory found in step 1 adds that
  directory to `plugin_dirs`, at the scope of the choice: the project's, when
  this setup has a project. The bundle carries that plugin whole, so no
  machine needs the plugin installed. Prefer a directory that stays the same
  across the plugin's versions to a cache path.
- **Run the step**: the step's `does` names the skill, its non-interactive
  options, its stop before merge, and what the lead does after it. The step's
  `skills` hold that skill and the step's default skills, whose flow and
  record still apply.
- **Steps**: a new step needs an `id`, its `stage`, an `actor` (`lead`,
  `foreman`, `person`, or a role), what it `does`, its `skills`, and `next`
  (each outcome to a step id or `stop`; the last outcome is the success
  path, which must reach `stop`). Put it in the list where it runs, with no
  `"after"` key: saving works out its place, and the dry run's `written`
  shows it. A step is removed with `{"id": "<id>", "remove": true}`. The
  order of existing steps stays.
- **Difficulty**: per step, `run` at low, mid and high (`always`, `never`,
  `if-not-trivial`). A stage whose steps all do not run is skipped.
- **Roles**: `mode` (`prompt` or `pane`), `step` (tiers above the lead's), and
  the fixed prompt. `loop.py prompt` fills in `<task>`, `<repo>`, `<base>`,
  `<head>`, `<diff>`, `<task folder>`, `<skill>`, `<skills>`, `<full test
  command>` and `<trivial>`; write no other `<...>` in a prompt. A judging
  prompt must keep its `Verdict:` line, and each verdict word must be an
  outcome of the role's steps: the gate reads the last one in the answer that
  `launch.py --role` saves in the task folder. To have the verification
  session's answers on the pull request, set `post_answers` (below) instead
  of telling the agent to post. When a prompt still has the agent post its
  answer (a pull request comment), say that the final message is still the
  whole answer, ending with the plain `Verdict:` line. An agent told to post
  often ends with a note about the post instead, with the verdict inside a
  sentence, and the gate finds no verdict.
- **Recheck limit**: a role's `recheck_limit`, 2 when it is not set (the
  person's choice of 2026-11-27). It counts the rechecks of one review: a
  step that follows an earlier step of the same role, such as the pair's
  `recheck`. `loop.py prompt` counts them in the task's `status.jsonl`,
  from the role's earlier step or its last approval. A recheck past the
  limit tells the role that only a must-fix in its diff gives `Verdict:
  changes`.
- **Decision points**: `"decisions"` in `loop`, `person` (the standard) or
  `lead`. With `lead`, the brief's loop gives the lead its decision points:
  it takes its recommended option, writes it in `plan.md`'s Decisions and a
  status line, and goes on. It still stops for a merge, an ADR change, a
  secret, data loss, or work outside the task (`loop.md`, Stop points). Set
  `lead` when the person will not be there to answer, such as for a night's
  run.
- **Answers on the pull request**: `"post_answers": true`, at the project's
  level, when the project's rules want the red team's and QA's answers on
  the pull request. The foreman posts each saved answer whole (`loop.py
  post`), and the merge gate counts a verdict only when its comment is
  there. So no agent posts another's answer, and an edited answer does not
  count. A check the project runs on comment bodies goes in the project gate
  as a `from_base` check ("4. Project gate").
- **Project gate** (step 4): save the chosen checks in `gate`, at the
  project's level.

## 7. Save and share

Save at the scope from steps 2 and 5 (`setup.md` "4. Save"). `written` shows
each changed step by its `id`. Then show `loop.py show` again and one task's
loop: `python3 <skill>/scripts/loop.py render --project <repo> --task <N>
--difficulty mid --machine <label>`. For each skill it lists as missing:

- a person's skill that the machine lacks is installed with the bundle: offer
  `python3 <skill>/scripts/bundle.py push <label> --project <repo>`;
- a name found nowhere is a typo or a skill to write; say which.

Not every step fits at once. Show one table: each step, what it uses now,
where that comes from, its level, and its state. The state is bound, the
default, or open (a gap, or a question left for later). Go on with what is
saved. The open steps keep the default. Log the open steps, so the retro
comes back to them (`SKILL.md` "Retro"):

```bash
python3 <skill>/scripts/log.py add --project <repo> --event setup --text "<n> steps fitted, <m> open" \
  --data '{"open": ["<step>: <what is open>"]}'
```
