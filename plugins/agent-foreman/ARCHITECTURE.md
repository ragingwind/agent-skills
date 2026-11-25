# agent-foreman architecture

This is the design the code follows. Where the code and this page differ, the
page is the target and the code is behind it.

`tests/test_architecture.py` checks the pictures in sections 1 and 6, and the
picture in `README.md`, against `defaults.json` and `status.py`: change a
loop or `status.py note` and its picture together. Every picture is plain
text; a loop is drawn as a sequence, with its outcomes listed under it.

> **Evidence at every step.** The foreman does not accept an agent's claim
> that a step is done. Every agent hands in evidence when it ends a step.
> The foreman checks that evidence before the task goes on:
>
> - **The lead**, at the end of each step: its `end` line names the skills
>   that the step ran and where their record is (`status.py note --done`).
>   The script refuses an `end` line without `--done`. `gate.py record
>   --step <step>` checks the record of each default skill.
> - **The pair, the red team and QA**: their answer, with the evidence of
>   each finding and a `Verdict:` line. `launch.py --role` saves the answer
>   at the commit that the agent judged.
> - **A project's own skill** in a step: the record of the default skill
>   that it replaces, and its own result (commits, a pull request) in the
>   lead's evidence line.
> - **Before ready and before merge**: the gate checks the same records, as
>   code, at the head commit.
>
> When evidence is missing, or the records do not support it, the foreman
> sends the step back with what is missing. At high difficulty, the foreman
> also checks the plan against the task before any code is built
> (`plan-check`).

## 1. Who does what

| Agent | Role | Started by | Runs as |
| --- | --- | --- | --- |
| Foreman | The project's manager: registers tasks, judges each task's difficulty, writes each task's brief, `loop.json` and gate file, watches, runs the verification session, merges (low and mid difficulty), archives and cleans up, runs the retro, talks with the person | The person | The person's harness session (Claude Code) |
| Lead | Owns one task: runs its build session in its own clone, starts its pair, runs the gate before it marks the pull request ready, reports | Foreman | The first pane of the task's tab |
| Pair | Reviews the lead's diff (step `review`) and the fixes (step `recheck`) | Lead | A prompt-mode run (`launch.py --print --role pair`) in its own clone at the lead's head |
| Red team | Tries to break the change (step `redteam-review`) | Foreman | A prompt-mode run in its own clone at the lead's head |
| QA | Runs the full tests and the user scenario test (step `test`) | Foreman | A prompt-mode run in its own clone at the lead's head |
| Helper, audit lead, scenario agent | The epic loop's roles | Foreman | A pane |
| Person | Decisions that need approval, high-difficulty merges, blocked removals, permission prompts, findings no script can settle | — | — |

```text
 PERSON           FOREMAN                            LEAD                 ROLE AGENTS
   │                │                                 │
   │ task           │                                 │
   ├───────────────▶│ register   task.md              │
   │                │ brief      loop.json            │
   │                │            gate.json + sha256   │
   │                │ launch ────────────────────────▶│ work loop, round 1
   │                │ watch      ◀── evidence ───────│ each step's end line
   │                │            gate.py record       │
   │                │ coordinate                      │ review, recheck ─▶ PAIR
   │                │◀────────────────── REPORT ready │
   │                │ verify-session ─────────────────────────────────────▶ RED TEAM ∥ QA
   │                │◀──────────────────────────────────────────── verdicts
   │                │ sent back? ── findings-r<N>.md ▶│ round N+1
   │                │ merge-gate  gate.py run --sha   │
   │                │ merge                           │
   │                │ cleanup    archive, remove      │
   │◀─────── report │ ■ STOP                          │
```

The foreman manages leads, not the pair. A lead moves from step to step on
its own and hands in evidence at the end of each step. The foreman checks the
evidence (`gate.py record`). When evidence is missing, the foreman sends the
step back. At high difficulty, the lead waits after plan for the foreman's
`plan-check`. The foreman also steps in at stop points, on a missed report,
and on events that the lead cannot handle.

Every agent gets its own profile, so one task can mix gateways: a lead on a
token-factory model and a red team on Anthropic opus are two processes with
two environments (`launch.py` clears the gateway variables before it sets a
profile's). The pair, the red team and QA never run on the lead's profile.

## 2. Layers

```text
┌──────────────────────────────────────────────────────────────────┐
│ foreman: loop control                                            │
├──────────────────────────────────────────────────────────────────┤
│ terminal layer: herdr, prompt mode     (later: tmux, ghostty)    │
├───────────────────────────────────┬──────────────┬───────────────┤
│ tab: one task's session           │ tab 2        │ ...           │
│ pane 1: lead                      │              │               │
│ prompt runs: pair, red team, QA   │              │               │
├───────────────────────────────────┴──────────────┴───────────────┤
│ agent adapter: claude                  (later: other kinds)      │
└──────────────────────────────────────────────────────────────────┘
```

**Terminal layer.** One interface, several adapters. herdr and prompt mode
are first-class; tmux and ghostty come later behind the same interface.

| Operation | herdr | Prompt mode |
| --- | --- | --- |
| machines | saved herdr machines (SSH targets) | SSH targets |
| open a session | tab in the project's workspace | the agent's own clone; its prompt and answer go in the task folder's `reviews/` |
| start an agent | `pane run` of `launch.py` | a `launch.py --print --role` command that `loop.py prompt` prints, on another machine through `remote.py` (its login shell) |
| send | `agent prompt`, `send-text`, `send-keys` | not possible: one prompt per run |
| read | `pane read`, transcript | the JSON result in `reviews/`, transcript |
| wait | `agent wait` | the process exits |
| close | exit, `tab close` | nothing to close |

**Agent adapter.** What differs per agent kind (command, skill delivery,
transcript, checkout readiness, screen rules). Two kinds exist: `claude`
(Claude Code) and `codex` (Codex CLI). One bundle serves both, so a task's
agents may run different kinds, and a skill has the same name in both.

## 3. Settings

| Scope | What | File | Written by |
| --- | --- | --- | --- |
| Global | Models: providers (token variable names only), their models and the tiers | `~/.config/agent-foreman/providers.json` | the person, after setup: models makes it |
| Global | Standard loop: stages and steps, skills per step, variants per difficulty | `~/.config/agent-foreman/config.json` | setup: loop |
| Project | Machines (SSH devices) and the project path on each; loop changes for this project | `~/.local/state/agent-foreman/projects/<owner>-<repo>/project.json` | setup: project |
| Project | Memory: values only this project has (tag format, docs steps, disk floor, labels) | `.../projects/<owner>-<repo>/memory.md` | the foreman |

A level stores only what differs from the level below. The package ships the
standard values.

## 4. Models

- **Providers.** `providers.json` lists each provider (Anthropic, Codex's
  own login with `"agent": "codex"`, or an anthropic-compatible endpoint
  with its URL, auth and token variable name) and its models. A model's `name` (default: its `id`) is its **profile**:
  the name tiers, `loop.json` and `launch.py` use. Scripts turn the file
  into the gateways and profiles they run on (`config.py`).
- **Tiers.** `high`, `mid`, `low` (상·중·하), in the same file. Each tier is an
  ordered list of profiles.
- **Standard tiers** are the harness's own models: for Claude Code, low =
  `haiku`, mid = `sonnet`, high = `opus` then `sonnet`. `fable` is never in a
  standard tier.
- **Other models** (`fable`, token-factory models, any other provider) enter
  a tier only when the person puts them there in `providers.json`.
- **The lead.** The task's difficulty gives the lead's tier; the lead runs on
  its first profile, and on a usage limit on the next one.
- **A role** takes the difficulty's tier raised by the role's `step` in the
  settings, capped at high: standard, the pair 0, the red team and QA 1. It
  may run on that tier's profiles and then each higher tier's, never a lower
  tier's, and never on the profile the lead runs on, which `loop.json`
  records (`loop.py render --lead`). `loop.py prompt` prints the launch
  commands in that order; on exit 5 (a usage limit, a gateway error) the
  next one runs.
- `config.py check` reports a difficulty whose lead has no profile, or whose
  role has no profile but the lead's.
- **No `providers.json`** means the standard tiers above: the harness's own
  models. `config.py providers --init` copies `providers.json.sample`, which
  holds them, into the file to edit.

## 5. Difficulty

The foreman sets each task's difficulty from a score and its own judgment.

- **Likelihood L** (0-3, one point each): more than 400 changed lines or more
  than an hour of human work; more than 10 files or 3 or more top-level
  directories; a bug fix, or touched files with a fix in the last 90 days.
- **Impact I** (the highest that applies): 3 authentication or secrets,
  money, schema or data migration, deletion, CI or deploy configuration, or a
  path on the project's critical list; 2 user-visible behavior, a public API
  or a shared library; 1 other runtime code; 0 docs or tests only.
- **Level** = I when L is 0 or 1, else I + 1 (at most 3).
- **Difficulty**: low = level 0, mid = level 1, high = level 2-3. The person
  merges every high-difficulty pull request.
- `score.py estimate` scores an issue before any code, from the paths and
  size the foreman expects and the issue's labels. `score.py diff` scores the
  change once it exists (`git diff BASE...HEAD` and the touched files' fix
  history); run it in the lead's clone, through `remote.py` on another
  machine. With `--previous` the difficulty only ever goes up.
- The thresholds (400 lines, 10 files, 3 top-level directories, 90 days) and
  the path patterns for critical, public, docs and test paths are the
  `difficulty` settings; a project adds its own critical paths there.
- The foreman adds what paths cannot show (does a user or caller observe the
  change? does it change a public API or a shared library?) and decides.
  `score.py` also flags a docs-only change as a trivial candidate.

Sources: Kamei et al. 2013 (just-in-time defect prediction), Meta Diff Risk
Score, ISTQB risk-based testing, Rigby & Bird 2013 (two reviewers), Google
small-CL guidance. The thresholds are a starting point; the log keeps each
task's level and outcome (reverts, follow-up fixes) to tune them.

## 6. Loops

A loop is a list of steps. Each step has an actor, what it does, the skills
it uses, and `next`: where each outcome goes, a step id or `stop`. The last
outcome in `next` is the success path; `config.py check` reports a loop whose
success path does not reach `stop` from the work loop's first step and from
each check step. The rule per difficulty (`run`) is on the steps. A stage
is a run of steps with the same `stage`; tab labels, status lines and
reports follow the stages. Setup (loop) designs the loops;
each project can change them.

**The task's loop.** With the brief, the foreman writes the task's loop into
its task folder as `loop.json` (`loop.py render --json`): the work and check
steps that run for this task, its base, the lead's profile, and each role's
prompt and profiles. `status.py note`, `loop.py prompt` and the gate read
it, so a task keeps the settings it started with; the gate file holds its
hash.

### Work loop: the build session (lead)

```text
 WORK LOOP · the build session, round N
 LEAD (own clone)                                PAIR (other model)  status.py note
  │                                               │                   │
  │ plan      plan.md rows, scenario.md ─────────────────────────────▶│ end done + evidence
  │ plan-check  high only: the lead stops and waits; the FOREMAN reads│
  │           the plan against task.md's done-when ──────────────────▶│ end go | back (foreman)
  │ build     one row at a time, its tests ──────────────────────────▶│ end done + evidence
  │ verify    tests, smoke, scenario.md ─────────────────────────────▶│ end done | fail
  │ review    clone at head, loop.py prompt ─────▶│                   │
  │◀──────────────────────────── answer, Verdict ─│                   │
  │           ───────────────────────────────────────────────────────▶│ end done
  │ simplify  clean-up commits ──────────────────────────────────────▶│ end done
  │ fix       must-fix, should-fix ──────────────────────────────────▶│ end done | large
  │ recheck   only the fixes, loop.py prompt ────▶│                   │
  │◀──────────────────────────── answer, Verdict ─│                   │
  │           ───────────────────────────────────────────────────────▶│ end approved | changes
  │ finalize  rebase, handoff.md, draft PR,       │                   │
  │           gate --before-ready, gh pr ready ──────────────────────▶│ end done | conflict
  │                                               │                   │
 every end line carries its evidence, and the foreman checks it (gate.py record)
 outcomes:
   plan ─done─▶ plan-check             plan-check ─go─▶ build
   plan-check ─back─▶ plan             build ─done─▶ verify
   verify ─done─▶ review               verify ─fail─▶ build
   review ─done─▶ simplify             simplify ─done─▶ fix
   fix ─done─▶ recheck                 fix ─large─▶ build
   recheck ─approved─▶ finalize        recheck ─changes─▶ fix
   finalize ─done─▶ stop               finalize ─conflict─▶ build
 actors: lead = plan, build, verify, simplify, fix, finalize · pair = review, recheck · foreman = plan-check
 a trivial task skips: review, simplify, fix, recheck
 low and mid skip: plan-check
```

- The stages are plan (plan, and plan-check at high), build, verify, review
  (review, simplify, fix, recheck) and finalize.
- **Every step ends with evidence, and the foreman checks it.** The lead's
  `end` line names the skills that the step ran and where their record is
  (`status.py note --done`). The script refuses an `end` line without
  `--done`. The foreman reads the line and runs `gate.py record --step
  <step>`, which checks each default skill's record (section 8). When a
  record is missing or the evidence does not match, the foreman goes back to
  the lead. The foreman asks a question, or sends the step back with what is
  missing.
- `plan-check` (high difficulty only) is the foreman's step. The lead stops
  after plan and reports `waiting`. The foreman judges whether `plan.md` and
  `scenario.md` cover every done-when of `task.md`. The foreman writes `go`
  or `back`, and tells the lead where to go on.
- The pair's `review` always ends with `done`: its findings go to simplify
  and fix. In `recheck` the pair's verdict is the outcome. The lead starts
  the pair: a clone at its head (`clone.py make --no-push`), then `loop.py
  prompt --step <step>` there, which writes the filled prompt into `reviews/`
  and prints the launch commands.
- finalize: rebase, `handoff.md`, a draft pull request whose body is
  `handoff.md`, `gate.py run --before-ready`, then `gh pr ready`.
- A **trivial** task (docs or text only, a typo, a rename that changes no
  behavior; the foreman marks it in the brief) skips the steps the picture's
  last line names: its loop is plan → build → verify → finalize, with no
  scenario and no pair.
- A **round** is one pass of the build session: 1 at first; the foreman gives
  the next number when the verification session sends the task back
  (`status.py note --round`).

A **scenario** (`scenario.md`) drives the change end to end through whatever
surface it reaches, as a user or caller would: an API, a CLI, a UI, a job.
The lead writes it in plan and runs it in verify in a fresh clone; QA runs it
again without reading the diff.

### Check loop: the verification session (foreman)

```text
 CHECK LOOP · the verification session, both steps at once
 FOREMAN                                  RED TEAM       QA     status.py note --file
  │                                           │           │           │
  │ gate --before-ready on the lead's claim   │           │           │
  │ redteam-review  clone at head, prompt ───▶│           │           │
  │ test            clone at head, prompt ───────────────▶│           │
  │◀──────────────────────── answer, Verdict ─│           │           │
  │◀──────────────────────────────────── answer, Verdict ─│           │
  │                 ─────────────────────────────────────────────────▶│ end, once per step
  │                                           │           │           │
 outcomes:
   redteam-review ─approved─▶ stop     redteam-review ─changes─▶ build
   test ─pass─▶ stop                   test ─fail─▶ build
   test ─script─▶ verify
 actors: redteam = redteam-review · qa = test
```

- On `REPORT: ready` the foreman runs the gate with `--before-ready` on the
  lead's claim, then starts both steps at once, each in its own clone at the
  lead's head, through `loop.py prompt` (models other than the lead's).
- The answer's verdict is the outcome, except when QA's `fail` comes only
  from `mismatch (script)` lines: then it is `script`.
- When both steps end in `stop`: the merge gate. When one names a work step:
  the foreman copies the findings to `reviews/findings-r<round>.md` and sends
  the lead back to that step with the next round (two different steps: the
  earlier one). After the lead is ready again, only the roles whose verdict
  check still blocks run again.
- To the person instead: no verdict, an `environment` mismatch, a `not run`
  test, a failure that also fails on the base, or 3 rounds that still find
  something. When the person says to merge anyway, the merge gate runs with
  `--skip verdict:<role>` for that role only.

**Variants by difficulty** (standard; setup changes them). Every difficulty
runs the same steps; only a trivial task skips the pair's steps.

| Difficulty | Lead | Pair | Red team, QA | Merge |
| --- | --- | --- | --- | --- |
| low | low tier | low tier and up | mid tier and up | foreman |
| mid | mid tier | mid tier and up | high tier | foreman |
| high | high tier | high tier | high tier | the person |

None of them runs on the lead's profile (section 4).

- Role agents start without edit tools (the role's `no_edit`: Claude
  Code's `Edit`, `Write` and `NotebookEdit` are disallowed, and a hook
  refuses Codex's `apply_patch`). That narrows them; it is not a sandbox. Their own
  clone, whose push to origin fails (`clone.py make --no-push`), and the
  gate's check that each verdict is at the head commit keep their writes from
  reaching the pull request. A role agent never starts other agents.

### How a step moves

```text
 the agent                              status.py note                 status.jsonl
 --event start --step S ──────────────▶ append ──────────────────────▶ S start, round N
 --event end --step S --outcome X ────▶ --done holds the evidence, and
   --done "<evidence>"                  X is one of S's next keys?
                                        ├─ no  ─▶ exit 2, nothing written
                                        └─ yes ─▶ append ────────────▶ S end, X, to Y, evidence
                                                  prints "next: Y"
                                                  (Y = stop: a stop point)
 starts Y ◀──────────────────────────── loop.md: follow the printed next step
 FOREMAN ◀── reads the evidence; gate.py record --step S: in order, or back to S
```

- A script holds the outcome and the evidence. An `end` line must name one
  of the step's `next` keys and carry the step's evidence (`--done`). The
  script records where the outcome leads (`to`). Going there is the agent's
  part, which `loop.md` asks for. Checking the evidence is the foreman's part
  ("Evidence at every step", section 1).
- The gate's `steps` check needs an `end` line for every work step before
  finalize, from any round, so a step skipped in a later round passes it.
  The verdict checks still need answers at the head commit.

### Where it stops

| Stop | Who | When | Held by |
| --- | --- | --- | --- |
| Ready | Lead | finalize passed `gate.py run --before-ready`, the pull request is marked ready, and finalize ends with `done` | A script: `status.py note` prints `next: stop` and `status.py read` counts the task stopped. The foreman runs the gate on the claim before the verification session |
| A decision for the person | Lead | A choice the task does not settle that changes what a user or caller sees, an interface, a schema or file format, or a core module | A prompt (`loop.md`); the lead writes the stop line with `status.py note --event stop` |
| Blocked | Lead | Something it cannot get or do, after trying once more | A prompt; the stop line with `--blocked` |
| Waiting for the foreman | Lead | At high difficulty, after plan: `plan-check` is the foreman's step | A script: `status.py note` says that the next step is the foreman's, and that the lead stops. The foreman writes `plan-check`'s end line and tells the lead where to go on |
| The third recheck still says `changes` | Lead | fix and recheck repeat | A prompt only (`loop.md`); no script counts rechecks |
| Ask the person | Foreman | No verdict, an `environment` mismatch, a `not run` test, a failure that also fails on the base, 3 rounds that still find something | A prompt (`SKILL.md`). Merging anyway takes `gate.py run --skip verdict:<role>`; the gate refuses a bare `verdict` |
| Merge blocked | Foreman | The merge gate exits 6 | A script (`gate.py`). A `gate-file` or `loop-file` block: tell the person and merge nothing |
| High difficulty | Person | The merge gate passed | A prompt (`SKILL.md`) |
| Done | Foreman | cleanup ended | — |

A script holds that every loop can reach `stop` (`config.py check`). Only
prompts hold that a cycle ends: fix and recheck, and the rounds of the
verification session.

### Management and epic loops

**Management loop** (foreman; the picture in section 1): register (task.md)
→ brief (`loop.json`, `gate.json` and its hash, `brief.md`) → launch → watch
→ coordinate (same-file tasks in sequence; relay the person's words as said)
→ verify-session → merge-gate → merge (high difficulty: the person) →
cleanup (archive, then remove) → the project's steps from memory (tag,
docs). A review finding that recurs goes into the project's memory, with a
proposed rule, test or hook. Each report sorts the open pull requests for
the person: safe to merge, needs a real review, hold, close.

**Epic batch loop** (optional, for projects that use epics): sync the epic
onto main, then tell every branch cut from the epic to rebase → persona audit
→ fixes through the work loop → user scenarios → epic-to-main pull request →
the person approves.

## 7. Skills

A step names its skills (`loop.py show`).

1. A **default skill** (`kit/skills/<name>`, one per loop action) ships in
   every bundle as `foreman-kit:<name>`. The settings' `skills` map may
   replace one with a project or local skill; the replacement changes how the
   action is done, never the flow or the record. The brief and `loop.json`
   show such a skill as `<skill> (flow and record: foreman-kit:<name>)`, so
   the agent knows both skills.
2. Any other skill, and a replacement, is looked up for the lead's machine:
   a project skill or command (`<checkout>/.claude/skills/<name>`,
   `<checkout>/.claude/commands/<name>.md`) first. Then a skill of a plugin in
   the settings' `plugin_dirs`. The bundle carries that plugin's whole
   directory (`plugins/<name>/`), and `launch.py` loads it with its own
   `--plugin-dir`. So the skill keeps its plugin's agents, scripts and hooks,
   and no machine needs the plugin installed. Otherwise, a user skill from
   the person's machine, which goes into the bundle (cached by content hash
   on that machine). `loop.py skills --project <repo> --machine <machine>`
   prints where each skill comes from. A missing skill is named to the person
   with its fix (setup, loop).
3. A project's own orchestration is used one step at a time (`setup/loop.md`).
   A skill replaces a step's action, adds to a step, or runs a whole step. An
   example of a whole step is a skill that implements an issue up to a pull
   request, in `build`. No skill takes over a loop or a stage. The gate needs
   every step's `end` line and the task folder's records, and the verdicts
   before ready come from other models. A skill that merges, or that makes
   worktrees, is bound to no step. The foreman merges after the gate, and
   every agent works in its own clone. Setup shows where a bound skill
   overlaps a step, such as its own reviewers and the pair, or its own brief
   and plan. The person picks which one does the work.

## 8. Gates

Pass conditions are code, not prose (`scripts/gate.py`).

- **Checks**, each reading the task folder, git or GitHub:
  - `pr-open`: the pull request exists and is open.
  - `loop-file`: `loop.json` still has the hash the template wrote.
  - `steps`: `status.jsonl` has an `end` line for each work step before
    finalize.
  - `docs`: every row of `plan.md`'s work breakdown is done, `handoff.md` has
    its sections, and `scenario.md`'s closing verdict is pass with every
    Agent block filled (not for a trivial task).
  - `ci`: every status check finished and passed.
  - `base-fresh`: the head contains the base branch's head.
  - `verdict`: an agent of the role whose latest answer in `reviews/`
    (`launch.py --role`) ran to the end with a `Verdict:` the role accepts,
    at the head commit (with `--cwd`, also at an earlier commit whose change
    is the same, by `git patch-id`), on a profile other than the lead's.
    For a project with `post_answers`, the verification session's verdict
    checks also need a pull request comment that holds that answer whole,
    as `loop.py post` writes it.
  - `tests-weakened`: no removed test file, added skip or focus marker,
    edited CI file, changed coverage threshold, or edited agent instructions
    (`.claude/`, `CLAUDE.md`, `AGENTS.md`), except what `allow` names.
  - `size`, `ready`, and `command`. A `command` check is a command that must
    pass in the clone. The command gets `AF_REPO`, `AF_PR`, `AF_TASK`,
    `AF_TASK_DIR`, `AF_BASE`, `AF_BASE_SHA` and `AF_HEAD`. With `from_base`
    instead of `run`, the gate takes the script from GitHub's base commit
    itself and runs it. A script that the gate cannot get blocks.
  - A check can be a warning instead of a block.
- **A project's own checks**: `gate` in the project's settings. It is a list
  of command checks, each with a `name`. Examples are a script that the
  project has for a pull request, or a lint check that its guides require.
  The checks are saved in `loop.json`, so the hash of `loop.json` covers
  them. A name stands for its check in the report and in `--skip`. The
  unnamed command is the full test command. A repository script is a
  `from_base` check. It is never a `run` check from the lead's clone,
  because the lead controls that clone's files and refs. A label that an
  agent sets itself is only a warning.
- **Each step's evidence** (`gate.py record --step <step> --task-dir <task
  folder> --cwd <lead's clone>`), when the step ends. The check reads the
  `end` line's evidence and the record of each default skill that the step
  runs. A replaced skill is checked by the default that its brief names. The
  records are the work breakdown, the scenario, a commit in the clone's
  history for every done row, the Checks entries, `handoff.md`'s sections,
  or a role's finished answer with a verdict. Exit 6 names what is missing.
  The foreman sends the step back with that list.
- `gate.py template --loop <loop.json>` writes a task's gate file: `pr-open`,
  `loop-file`, `steps`, `docs`, `ci`, `base-fresh`, a verdict check per role
  (the pair's before ready and at merge, the red team's and QA's at merge),
  the full test command when the project has one, the project's own checks,
  `tests-weakened`, `size` (a warning) and `ready`. The foreman adds
  commands, or an `allow` for what the task asks.
- The foreman records `gate.py hash <gate.json>` in the ledger and passes it
  to every gate run of its own with `--sha`; a changed gate file blocks as
  `gate-file`.
- The lead runs `gate.py run --before-ready` in finalize before it marks the
  pull request ready; that skips `ready` and every check marked `at: merge`.
  The foreman runs the same on the lead's report, and every check before it
  merges. Exit 6 lists what blocks. Each run with `--task-dir` adds a line to
  the task folder's `gates.jsonl`. The line holds the head, what blocked and
  warned, what was skipped, and whether the hash was checked. The retro
  counts from `gates.jsonl`. The lead can write to that file, so the file
  proves nothing. Instead, the foreman logs each merge-gate pass in its own
  log (`merge-gate` event). When a pull request is found merged with no such
  event at its head, the foreman reports it to the person.
- No agent merges. The adapter denies `gh pr merge` to every agent that
  `launch.py` starts. This was checked on 2026-11-15 with the agent's own
  permission prompts off: the command alone, and the command joined with
  `&&` or `;`, were all refused. The deny does not match a merge through
  `gh api`, `gh -R <repo> pr merge` or a script. The merge check above
  catches those merges.
- The red team's clone and QA's clone restore the agent-instruction files as
  GitHub's base commit has them (`clone.py make --instructions-from`). So a
  change to `.claude/`, `CLAUDE.md` or `AGENTS.md` cannot change the
  instructions that those agents read. The lead makes the pair's clone
  itself, so no other agent checks that the pair's files were restored. In
  either case, `tests-weakened` names the change for the merge gate.
- Known limit: the lead can write in its own task folder, so no script stops
  it from writing a fake answer file into `reviews/`.

## 9. Reporting

- **Status file**: `status.jsonl` in the task folder, on the task's machine
  (`status.py path`). `launch.py --task-dir` hands the folder to an agent as
  `AF_TASK_DIR` and the file as `AF_STATUS_FILE`; without `--task-dir` or
  `--status` both are cleared, so an agent never writes into its starter's
  file.
  - The bundle's hooks (claude: `PostToolUse` and `Stop`) run
    `heartbeat.py`: a `heartbeat` line at most once a minute while tools run,
    and a `turn-end` line at every turn's end (time, agent, tool). Role agents
    start with the task folder too, so a long review shows as heartbeats.
    Checked 2026-11-13: plugin hooks fire in `claude -p`,
    `${CLAUDE_PLUGIN_ROOT}` resolves, and the variable reaches the hook.
  - The lead writes a `start` line and an `end` line with its outcome for
    every step (`status.py note`, section 6), `progress` lines during a long
    one, and a `stop` line at a decision or when blocked. The foreman writes
    the verification session's lines with `--file`.
- **The foreman** runs `status.py read` on every check (one SSH call per
  machine). No line for `ops.stall_minutes` (30) is a stall, unless the task
  is stopped: its last stage line is a `stop` line or an `end` line that
  leads to `stop`.
- **`REPORT:`** at the end of a turn only at stop points: ready, a decision
  for the person, blocked, waiting (for the foreman's `plan-check`).
- **Prompt-mode runs** of a role leave three files in `reviews/`:
  `<agent>-<n>.prompt.md` (from `loop.py prompt`), `<agent>-<n>.json` (the
  JSON result, in Claude Code's names for every agent kind: `result`,
  `session_id`, `total_cost_usd`, `permission_denials`) and `<agent>-<n>.meta.json` (role, agent, profile,
  model, the commit it ran at, verdict, start and end).

## 10. Isolation and trust

- Every agent that touches files works in its own clone (`clone.py make`):
  `~/.cache/agent-foreman/work/<project>/<task>/<agent>`. It starts inside
  that clone, never in a shared checkout.
  - The lead's clone comes from the project's checkout on that machine. The
    pair's, the red team's, QA's and the lead's scenario clone come from the
    lead's clone at its head, with `--fresh --no-push`. Either way `origin`
    is then set to the source's GitHub URL and fetched: without it `gh` fails
    ("none of the git remotes … point to a known GitHub host", checked
    2026-11-13).
  - A clone starts detached at the task's base or the head SHA, with no
    local branch, and holds a marker in `.git` that the foreman made it.
  - A judging agent's clone gets `--no-push`: origin's push URL points
    nowhere, so `gh` still works and `git push` to origin fails.
- `launch.py --role` runs only with `--task-dir`, `--name`, an `--out` inside
  the task folder's `reviews/`, and a git checkout to run in; the commit
  checked out goes into the meta file the gate reads.
- A new clone is an untrusted folder, and a trusted parent does not count:
  Claude Code looks for a trusted folder only up to the git repository's
  root, and a clone is its own root (checked 2026-11-17 with 2.1.326).
  - Prompt mode needs no trust step and still loads the clone's project
    skills (checked 2026-11-13).
  - In a pane, Claude Code asks first, with the cursor on "No, exit"; herdr
    shows the agent `unknown` or `blocked`, so the screen is read, not the
    state. Right after starting the agent, the foreman runs `clone.py
    trust`. It reads the pane every second and answers Yes with herdr keys
    (`Down`, `Enter`) when `clone.py check` says the folder is a clone the
    foreman made and the pane runs in it. Any other folder's trust question
    goes to the person. (The person allowed answering on 2026-11-13, and
    asked for an answer at once on 2026-11-17.)
- Cleanup (`clone.py remove`) removes the task's clones and task folder.
  It refuses a folder without the marker, one holding the caller's working
  directory, and, unless forced, a clone with changes to tracked files or,
  for a clone that can push, commits that are on no remote.

## 11. Records

- **Task folder**, on the task's machine:
  `~/.local/state/agent-foreman/tasks/<owner>-<repo>/<task>/` (`status.py
  dir`). Every record of the task is there. A project skill that a step uses
  may also write its usual output, such as labels and comments. Apart from
  that, nothing goes in issue or pull request comments except the pull
  request body and, for a project with `post_answers`, the verification
  session's answers, which the foreman posts whole (`loop.py post`).

  | File | Written by | Holds |
  | --- | --- | --- |
  | `task.md` | foreman | The goal, the done-when, what is out of scope |
  | `brief.md` | foreman | What the lead reads first |
  | `loop.json` | foreman | The task's loop (section 6) |
  | `gate.json` | foreman | The task's gate (section 8) |
  | `plan.md` | lead | The work breakdown, the decisions, the checks |
  | `scenario.md` | lead | The user scenario: steps, Agent blocks, a closing verdict |
  | `handoff.md` | lead | The pull request body |
  | `status.jsonl` | lead, foreman, hooks | Section 9 |
  | `reviews/` | `launch.py`, foreman | Each role run's prompt, answer and meta; the foreman's `findings-r<round>.md` |
  | `gates.jsonl` | `gate.py run` | Each gate run: the head, whether it passed, what blocked and what warned |

- After the merge, `clone.py archive` copies the task folder to the
  foreman's project folder (`projects/<owner>-<repo>/tasks/<task>`) and checks
  that every file arrived; `clone.py remove` then removes it with the clones.
- **Log**: `~/.local/state/agent-foreman/projects/<owner>-<repo>/log.jsonl`,
  append only (`log.py add`, `log.py tail`): every event, instruction sent,
  report received, decision of the person, sub-agent run, difficulty and
  outcome. No secret values.
- **Ledger**: `ledger.md` in the same folder: state and links only, one row
  per task with its gate hash. A new foreman reads it to take over;
  decisions, findings and briefs live in the task folder.
- **Retro**: `retro.py facts` reads the archived task folders and the log. It
  reports the steps that tasks went back to, minutes per step, findings by
  role and severity, gate blocks, stops and stalls. The foreman reads these
  facts against the loop and proposes changes: a step, a skill, a gate check,
  a `run` rule, or a line in memory. Each change comes with its evidence and
  the fact it should change. The person decides. The log holds the setup's
  open items (`setup` log event) and each retro's changes and expectations
  (`retro` log event), so the next retro checks them. No skill file is
  edited.
- **Error reports**: `error-reports/E<n>.json` in the same folder, one per
  problem, in one form (`errors.py`, `error-report.md`): what happened, the
  evidence, how to reproduce it, the cause, the fixes and their owners.
  `errors.py collect` copies the task's records into `E<n>/`, so they
  outlast the clean-up.
- **The foreman's place**: `~/.local/state/agent-foreman/foreman/<owner>-<repo>.json`,
  the project's last foreman session (id, transcript, folder, time). The
  plugin's `Stop` hook writes it at each turn's end; its `SessionStart` hook,
  in a new foreman session, adds that session's last exchanges, at most 9,000
  characters (`scripts/session.py`). Only in a session started with
  `claude --agent agent-foreman`, whose hooks see `agent_type`
  `agent-foreman:agent-foreman`.

## 12. Layout

One plugin that is one skill: `SKILL.md` sits at the plugin root, so the
same folder installs as a plugin (with the `agent-foreman` agent) or links
into `~/.claude/skills/agent-foreman` as a user skill.

| Path | Holds |
| --- | --- |
| `SKILL.md` | The foreman, and the entry to setup |
| `setup/` | Setup: `setup.md` runs the parts in order; `models.md`, `project.md`, `loop.md`, `other.md` |
| `loop.md` | The lead's guide to its loop; every bundle carries it |
| `kit/skills/` | The default skills, one per loop action; every bundle carries them as `foreman-kit:<name>` |
| `scripts/`, `terminals/`, `adapters/`, `defaults.json` | The scripts, the terminal layer, the agent kinds, the standard settings |
| `providers.json.sample` | The standard models by provider; setup copies it to `~/.config/agent-foreman/providers.json` for the person to edit |
| `agents/agent-foreman.md` | `claude --agent agent-foreman`; only with the plugin installed |
| `hooks/hooks.json` | The foreman's place across sessions (section 11); only with the plugin installed |
