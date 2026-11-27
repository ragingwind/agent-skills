# Runbook for the Foreman report pane

Path `plugins/agent-foreman/board-runbook.md`. The steps below are Step 5 of the runbook skill. Independent verification, fixes, and any pull request checks follow them.

## Scope

Show one project as a live plain-text list in a Herdr pane. Read the existing Lead status, session replies, and headless review files on each configured machine. Keep Lead instructions in Foreman chat. The separate Board TUI project owns its layout, chat, and public schema.

## Inputs read

- [Issue #47](https://github.com/ragingwind/agent-skills/issues/47) and the decisions leading to it.
- `SKILL.md` Watch and Ledger, `terminals/herdr.md`, `scripts/status.py`, `scripts/transcript.py` and its adapters, `scripts/launch.py`, `scripts/bundle.py`, and `scripts/config.py` machine profiles.
- `git log` shows Codex adapter support in `00d58e2`. `git ls-files` found no root `.github` workflows or prior runbook location. Run the three development checks in root `README.md`; the sandbox fixture's workflow belongs to its generated product repository.
- The local environment has Python 3.12 and the Claude CLI. `HERDR_ENV` is unset. Use the existing session parsers against recorded fixture files and a fake Herdr CLI and SSH bridge. Live Herdr and remote SSH remain integration checks for a Herdr-managed session.

## What must hold

- One text view lists Lead and headless review results together. Keep task, machine, and role visible. A later Lead reply appears even when it has no `REPORT:` line.
- A working pane settling triggers a refresh for its machine. A timed refresh picks up headless results and detects machines or panes that were unavailable. Show the last view when a machine is temporarily unreachable, and remove the stale marker after recovery.
- A refresh replaces the machine's view, including removed tasks. The existing task notes, transcripts, and reviews remain the sources. The pane shows summaries as plain text and strips terminal control characters.
- Keep Foreman chat and merge verification on their existing path. The pane reads data only.

## Steps

1. Add `scripts/board.py` to the bundle. Read the ledger's Task, Machine, Pane, Profile, and Session columns on the Foreman host. Send task and session IDs and resolved adapter kinds as JSON on stdin to one read command per remote machine, using the remote login shell and the current bundle path. Read project task folders, status and review metadata locally on that host. Filter known verification steps out of Lead state using the task loop. Keep a stop reason and the latest settled reply visible independently. Return bounded summaries keyed by machine, task, and role/agent.
2. Run one watch process per pane. For each registered Lead pane, alternate a bounded Herdr wait for `working` with a bounded wait for a settled state. Refresh that machine on successful settle. Use `agent list` during reads to keep the last displayed reply while the agent is working. Reconcile all machines on a separate timer. A failed read retains the previous rows with a stale marker. A successful read replaces them. Print a new list only when content changes.
3. Document `board.py watch --project` and its optional `--once` in `terminals/herdr.md`. For each remote, use `--remote-bundle` with the label and absolute path from a fresh `bundle.py push`. Show a missing profile or unavailable bundle in the list. Confirm that the existing Foreman chat still supplies Lead instructions.

## Smoke and scenario tests

Run these commands from the repository root. The fixture uses temporary task directories, a recorded Claude session, and a simulated remote SSH transport.

| # | Run | Expect | Agent | Person |
|---|---|---|---|---|
| 1 | `python3 -B -m unittest discover -s tests -p test_board.py -k test_cli` | A fake SSH command runs the script packaged in a real bundle under a distinct home. One view includes task `7` on `local` as Lead and on `build` as QA. A missing bundle is shown alongside the local row. A fresh local view shows `No reports`, and invalid project input exits 2. | `Ran 2 tests in 1.376s` · `OK` | |
| 2 | `python3 -B -m unittest discover -s tests -p test_board.py -k test_watch` | A controlled event refreshes its machine before the next timed check. Pane waits require `working` before reporting a settle. A settle that lands after one settled wait times out and before the next wait starts is still reported, once. A plain reply replaces an earlier reply while the decision remains visible. The timed check picks up a headless result. A disconnect marks the machine stale and recovery removes the stale marker and obsolete rows. | `Ran 3 tests in 0.004s` · `OK` | |
| 3 | `python3 -B -m unittest discover -s tests -p test_board.py -k test_records` | A later QA status note leaves the earlier Lead decision visible. Invalid records are skipped, and control bytes in records never enter the text list. | `Ran 1 test in 0.006s` · `OK` | |

## Evidence

Development checks from `README.md`.

`python3 -m unittest discover -s tests`

```text
----------------------------------------------------------------------
Ran 324 tests in 92.828s

OK
```

Independent verification reproduced non-object transcript entries stopping a
refresh and invalid review metadata hiding a valid earlier run. The readers
now skip these entries. The board scenario and Codex adapter test cover them.
The independent post-fix full run reported `Ran 324 tests in 92.263s` and `OK`.
After the live check's fix (below), the full run on Python 3.12.8 reported
`Ran 325 tests in 98.829s` and `OK`, and both validations below passed again.

The sandboxed baseline could not bind the provider test's loopback port. The
full run above allowed loopback. Existing tests emitted `ResourceWarning` for
unclosed files in `test_gate.py` and `test_launch.py`.

`claude plugin validate .`

```text
✔ Validation passed
```

`claude plugin validate --strict plugins/agent-foreman`

```text
⚠ Found 1 plugin directory warning:
  ❯ .claude-plugin/plugin.json icon: No icon (ICON_MISSING).
✔ Validation passed
```

## Live check

Run on 2026-11-27 (times UTC) in a sandbox from `fixture/sandbox.py create`,
`ragingwind/agent-foreman-sandbox-20261127-045428`, whose machines are `local`
and the remote `isla-hkmoon-003`. The Lead was an interactive `sonnet` session
in a Herdr pane on `local`, with its row in the ledger. QA ran headless on the
remote with the `launch.py opus --print --role qa` command that `loop.py prompt`
printed. The board ran in its own Herdr pane with `--interval 120`, so a refresh
from an event and a timed refresh happen at different times. A script read the
board pane every half second and logged each change with its time.

| Check | What happened | Result |
|---|---|---|
| Lead decision | The Lead wrote `REPORT: decision — what a user sees when --min filters out every item; recommend print nothing and exit 0 ...` as its stop line and settled at 04:58:27. At 04:58:43 the board still showed `#1  local  lead  pending`. The next timed refresh was due at 05:00:03. | Failed, fixed below |
| Reply to a Foreman instruction, after the fix (board restarted at 05:03:12) | The question went to the Lead with `herdr agent prompt`, the command the foreman sends. The Lead settled at 05:03:38. At 05:03:39 the board showed its plain reply after the decision. The next timed refresh was due at 05:05:13. | Passed |
| A Lead turn longer than one settled wait | An 18-second turn settled at 05:05:00 and its reply appeared at 05:05:01. | Passed |
| Headless QA | The first QA run ended without a `Verdict:` line because the build had not run, and the 05:07:13 refresh showed it as `completed`. The second run, with the remote task marked trivial, ended with `Verdict: pass` at 05:08:17. The 05:09:14 refresh showed `#1  isla-hkmoon-003  qa  pass  qa-1 \| The full test suite passed at head commit 5126a64 ... \| at 5126a64ea2ff` under the Lead's row, and the first run's row was gone. | Passed |
| Disconnect and reconnect | From 05:09:33 to 05:11:36, an `ssh` wrapper on the board's `PATH` exited 255, as `ssh` does when the connection drops. Herdr's own connection to the machine stayed up, because other agents ran there. The 05:11:13 refresh kept both rows and added `isla-hkmoon-003: stale (SSH or remote bundle read failed)`. The 05:13:14 refresh removed the marker and showed each row once. | Passed |

The fix: after a settled wait timed out, `wait_for_settle` waited for
`working` again. When the agent settled in the second between two waits, no
later wait saw it working, so the settle was never reported and the list
waited for the timed refresh. A replay of the same Herdr calls caught a settle
that did not fall in that gap. A settled wait now stays armed until it returns.
`test_watch_reports_a_settle_between_two_waits` failed before the fix and
passes after it.
