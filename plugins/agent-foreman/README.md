# agent-foreman

Turn one Claude Code session into the foreman of your coding agents on
[herdr](https://herdr.dev) machines. You name the work. For each task the
foreman:

- writes the task down in one task folder, and rates its risk;
- starts a **lead** agent that builds it in its own clone (the **build
  session**);
- starts a **red team** and **QA** on other models to check it (the
  **verification session**);
- runs a scripted gate, then merges, or leaves the merge to you when the risk
  is high.

The foreman writes no code and reviews no code itself.

## Words

| Word | Meaning |
| --- | --- |
| Foreman | This Claude Code session. You talk only to it |
| Lead | The agent that builds one task, from the plan to a ready pull request |
| Pair | Another model that reviews the lead's work inside the build session |
| Red team, QA | Agents on other models in the verification session. The red team tries to break the change; QA runs the full tests and the user scenario test |
| Task folder | One folder per task that holds every record: the task, the plan, the scenario, the handoff, every review and the status |
| Default skill | What one loop action is, shipped with agent-foreman. A project or local skill can replace how it is done, add to a step, or run a whole step |
| Difficulty | Low, mid or high. It picks the models and who merges |
| Gate | Checks in code that must pass before ready and before merge |

## How it works

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

Where a task goes back, and who decides:

| Found | Goes to |
| --- | --- |
| verify fails, a fix too large for review, a rebase conflict | build, in the same session |
| a code finding, full tests fail, a product problem in the scenario | build, next round |
| a problem only in the scenario script | verify, next round |
| an environment problem, no verdict, 3 rounds still finding something | you |

| Session | Stage | What happens | Default skills |
| --- | --- | --- | --- |
| build | plan | Split the task into work items with a done-when each; write the scenario script a person could follow | `work-breakdown`, `cross-check` |
| | build | Per work item: implement (test first if the project uses TDD), test, commit once | `tdd`, `unit`, `commit` |
| | verify | Tests near the change, a smoke test, and the scenario script run once in a fresh clone | `unit`, `smoke`, `cross-check` |
| | review | The pair reviews; the lead cleans up the diff and fixes the findings; the pair checks again | `review`, `simplify` |
| | finalize | Rebase, write handoff.md, open the pull request (its body is handoff.md), run the gate | `handoff` |
| verification | redteam-review | Try to break it: done-when, correctness, tests, structure, security | `redteam-review` |
| | test | The full tests, then the user scenario test without reading the diff | `full`, `cross-check` |

- **Evidence at every step.** The foreman does not accept an agent's claim
  that a step is done. The lead ends every step with its evidence: the skills
  it ran and where their record is. The foreman checks that record before the
  task goes on. When the record is incomplete, the foreman sends the step
  back. The pair, the red team and QA hand in answers with the evidence of
  each finding. At high difficulty, the foreman checks the plan against the
  task before any code is built.
- **Other models check the work.** The pair, the red team and QA never run
  on the lead's profile. The gate refuses a verdict from the lead's model.
- **One place for records.** Everything about a task is in its task folder.
  After the merge, the foreman copies the folder to your project folder and
  removes it from the machine.
- **One rule off the path.** An agent tries once more; if it still fails, it
  stops and the foreman asks you.

## What scripts hold, what prompts ask

A rule whose break could merge the wrong change is held by a script. How the
work is done is asked by the skills and guides.

| Held by a script | Asked by a prompt |
| --- | --- |
| Each step's end line names one of its outcomes and carries its evidence, and the script prints the next step (`status.py note`) | How to split the work, which tests to write, one commit per work item |
| The foreman checks each step's evidence against its records (`gate.py record`): the plan's rows, a commit for each done row, the Checks, the answers | Whether the plan covers every done-when (the foreman's own judgment, at high difficulty) |
| The gate blocks until every step before finalize has ended and every record is filled in | What to look for in a review, what to clean up |
| Verdicts count only from `reviews/`, from a model other than the lead's, at the head commit | QA follows the scenario without reading the diff |
| Role prompts and launch commands come from the task's `loop.json` (`loop.py prompt`) | The three-round limit and the report line |
| The gate blocks when the gate file or `loop.json` changed after the brief | High difficulty is yours to merge |
| Every agent that the foreman starts is denied `gh pr merge`. A merge that did not pass the foreman's gate is reported to you. The project's own gate checks run with the standard ones | What a retro proposes. You decide each change |

Known limit: the lead can write in its own task folder, so no script stops
it from writing a fake answer file into `reviews/`.

## Requirements

| Need | Why |
| --- | --- |
| herdr on this machine and on every machine that runs agents, each remote saved with `herdr machine add` (tested with 0.9.5) | The foreman drives tabs and agents through `herdr --machine` |
| Claude Code, signed in, on every machine that runs agents (tested with 2.1.323) | The agents are Claude Code sessions |
| Codex CLI, signed in, where a profile runs Codex (optional; tested with 0.172.0) | A model of a provider with `"agent": "codex"` runs as a Codex session |
| `claude`, `git`, `gh` (signed in) and `python3` on `PATH` in each machine's login shell | Agents start there and open pull requests; the scripts need only Python's standard library |
| SSH from this machine to each remote with no password prompt | Bundles and task folders travel over `ssh` and `scp` |
| A checkout of the repository on each machine | Agent clones are made from it |

## Setup

1. **Install the plugin** (in Claude Code):

   ```
   /plugin marketplace add ragingwind/agent-skills
   /plugin install agent-foreman@ragingwind-agent-skills
   ```

2. **Set up**, in a checkout of the repository:
   `/agent-foreman:agent-foreman setup`. It goes through every part in this
   order, and each question offers the value already set first (`Keep`), so
   running it again changes only what you pick:
   - **Models**: it copies `providers.json.sample` to
     `~/.config/agent-foreman/providers.json`, with Claude's own models
     (`haiku`, `sonnet`, and `opus` then `sonnet`), and asks you to edit it: add a provider such as a token factory or Codex, and the
     models each difficulty uses. Each difficulty needs a model other than
     its lead's for the agents that check the work.
   - **Project**: the repository, the machines and their checkout paths, and
     the full test command (it proposes the one in `CLAUDE.md` or your CI
     files).
   - **Loop**: fits the project's skills and commands to each step. Where
     the project has none, it fits yours. It shows where skills overlap and
     asks which one does the work. It adds the project's own gate checks.
     Then it asks what else to change, such as what each difficulty runs. A
     step that it cannot fit yet keeps the default skill, and the retro
     comes back to that step.
   - **Other**: launch, tab labels, the report, check times, disk, merge
     steps.

   To change one setting later, say it in words: "add machine build-02".

3. **Start the foreman**, in the project's checkout:

   ```bash
   claude --agent agent-foreman
   ```

   It waits for your first line. Name the work: `Add a --json flag to the
   list command of acme/api.`

   You can close it at any time; the leads keep working in their tabs.
   Start it again the same way, and it opens with the last exchanges of the
   project's earlier foreman and picks up from there.

   After a batch of tasks merges, the foreman offers a retro. It reads what
   the finished tasks show: the steps they went back to, the findings, the
   gate blocks and the stalls. Then it proposes changes to the loop, each
   with its evidence. You pick which changes to keep. The next retro checks
   whether those changes helped.

Agents start with `--dangerously-skip-permissions`, so they do not stop for
permission prompts. To have them ask, set `launch.permission` to `default`
in setup. The foreman never answers a permission prompt.

## Security

- **On each machine** it writes under `~/.cache/agent-foreman/` (bundles and
  agent clones) and `~/.local/state/agent-foreman/tasks/` (task folders). It
  never writes into your checkout.
- **Trust**: the foreman answers Claude Code's folder trust question only for
  a clone it made.
- **Judging agents** (pair, red team, QA) run without edit tools, in clones
  that cannot push. This narrows them; it is not a sandbox.
- **Secrets**: settings and records hold token variable names only.

## Updating and uninstalling

```bash
claude plugin update agent-foreman@ragingwind-agent-skills
claude plugin uninstall agent-foreman@ragingwind-agent-skills
```

Uninstalling leaves your settings and records; remove them by hand:
`~/.config/agent-foreman/`, `~/.local/state/agent-foreman/`, and
`~/.cache/agent-foreman/` here and on each remote.

## Development

From the repository root:

```bash
python3 -m unittest discover -s tests
claude plugin validate --strict plugins/agent-foreman
```

## License

MIT. See [LICENSE](../../LICENSE).
