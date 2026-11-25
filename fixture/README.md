# Fixture: a run with real agents

A made-up project and two tasks to run through agent-foreman with real
agents, on this machine, with no GitHub: whether every step leaves its
evidence, and whether the foreman's checks, the gate and the merge work on
what real agents do.

| Path | Holds |
| --- | --- |
| `repo/` | The project: `stock`, a small Python CLI with tests, a CI file and a guide |
| `tasks/` | The tasks, as the foreman registers them: `1.md` (mid difficulty), `2.md` (high, so the foreman checks the plan) |
| `bin/gh` | A local stand-in for GitHub's `gh`: pull requests, their checks (`make test` on the head), labels, merges, issues, and the API calls the gate makes, in a state file. Anything else is refused and listed in the report |
| `run.py` | The run |
| `sandbox.py` | Makes and deletes a private GitHub repository with this project, for a live run of the real foreman ("A live run on GitHub") |

```bash
python3 fixture/run.py --dry-run     # prepare everything, call no model
python3 fixture/run.py               # both tasks
python3 fixture/run.py --task 2      # one task
python3 fixture/run.py --scenario all --rounds 3   # every forced path below
```

Agents rarely take some paths on their own. `--scenario` (a comma list,
repeatable, or `all`) makes the run take them, so the foreman's handling of
each one is tried:

| Scenario | Task | What the script does | What should follow |
| --- | --- | --- | --- |
| `setup-test` | none | Runs setup's full test command steps: a clone at the default branch, the command, a wrong command, the removal. No model | The command passes, the wrong one fails, the clone is gone |
| `plan-back` | 2 | Tells the foreman's first plan-check to send the plan back | The lead fixes the plan, the second plan-check says go, the task merges |
| `send-back` | 1 | Tells the first red team run to give at least one should-fix | The lead goes back to build, a second verification round runs, the task merges |
| `no-verdict` | 1 | Gives QA's first run a prompt that ends with no Verdict | The script runs the next profile once (`SKILL.md` "Verification session"), and QA gives a verdict |
| `disk-floor` | 2 | Raises the disk floor in QA's first prompt, and runs one merge gate on a copy of the gate file with the floor raised | QA reports the full tests as not run and runs again; the copy's gate blocks `command` with `fulltest.py: not run`; the task merges |
| `lock-wait` | 1 | Holds the machine's full-test lock for 20 seconds while the merge gate runs | The gate waits, then passes |

The report's "Scenarios" table says, per scenario, whether the run took the
path and whether it ended right. `send-back` uses one verification round
for the forced finding; `--rounds 3` leaves room for one real finding after
it.

The script plays the foreman's scripted part (the task folder, the loop, the
gate, the brief, the clones, the verification session, the merge gate, the
merge, the archive, the clean-up). The agents are real: the lead, the pair it
starts, the red team, QA, and the foreman's own judgment at `plan-check`.
The foreman's watching, its herdr tabs and setup are not part of the run.

It needs `claude` logged in on this machine and network, and costs real
tokens: the lead, the pair, the red team and QA run on the standard tiers
(mid: the lead on sonnet, the others on opus). It takes a while; the lead
alone may work for most of an hour.

Settings, the ledger, the log, the bundle and the report go in the run folder
(`--dir`, or a new temporary one); the person's own settings are not read or
changed. The task folders and clones go where the scripts always put them,
under `fixture-repo`, and are removed at the end.

The report (`report.md` and `report.json` in the run folder): per task, each
step's evidence line and its record check (`gate.py record`), plan-check's
word, the verdicts and rounds, the gate before ready and before merge, the
merge, the cost of each run, and every `gh` call the stand-in did not
support. Models do not answer the same way twice: read a failure for what
the agent did, not as a test that broke.

`repo/` keeps the project's `.github` as `dot-github` and its guide as
`CLAUDE.fixture.md`, so an agent working in this repository does not read
them as its own; the run copies them under their real names.

## A live run on GitHub

`run.py` leaves out GitHub, setup, the foreman's watching and its herdr
tabs. To try those, run the real foreman on a sandbox: a private GitHub
repository with this project, and its tasks as issues. Make one for a run,
and delete it after.

```bash
python3 fixture/sandbox.py create                    # the repository, its issues and the delete command
python3 fixture/sandbox.py list                      # the sandboxes still on GitHub
python3 fixture/sandbox.py delete <owner>/<name>
```

1. Make a sandbox with `create`. To make it in an organization, add
   `--owner <org>`.
2. Clone it with the `clone` command that `create` printed.
3. In the clone, run setup and start the foreman, as the plugin's README
   says ("Setup"). The full test command is `make test`.
4. Name the issues to the foreman. CI runs `make test` on each pull request.
5. When the run is over, delete the sandbox with the `delete` command that
   `create` printed.

- `delete` removes a repository only when its name starts with
  `agent-foreman-sandbox-` and its description is the one `create` set. It
  refuses any other repository.
- Deleting needs the token scope `delete_repo`. To add it, run
  `gh auth refresh -h github.com -s delete_repo`.
- `delete` leaves what the foreman made for the sandbox on each machine: the
  project settings in `~/.local/state/agent-foreman/projects/<owner>-<name>/`,
  the task folders in `~/.local/state/agent-foreman/tasks/`, and the clones
  in `~/.cache/agent-foreman/work/`. Remove them by hand.
- A run costs real tokens, and CI on a private repository uses the
  account's GitHub Actions minutes.
