# Handoff for the Foreman report pane

Closes #47

## What this branch adds

Foreman can show one project as a live text list in a single Herdr pane. The list pulls Lead decisions and answers from existing task records and sessions. It also shows headless review verdicts with the machine, role, and tested commit.

Herdr's `agent wait` wakes the reader when a tracked Lead settles. A timer refresh picks up headless results and recovers after disconnects. A failed machine read keeps the last rows and marks them stale. Foreman chat remains the entry point for instructions to Leads. The separate Board TUI project owns its layout, chat, and public schema.

## Run in Herdr

From the repository root, set `project` to a Foreman-managed `owner/repo`. Run this in the pane that should show the list.

```bash
project=owner/repo
python3 plugins/agent-foreman/scripts/board.py watch --project "$project"
```

For every configured remote machine, push the updated bundle. Use the machine's Herdr label in place of `build-01`.

```bash
machine=build-01
python3 plugins/agent-foreman/scripts/bundle.py push "$machine" --project "$project"
```

Copy the response's `path` into `bundle_path` and start the list with the corresponding option. Repeat `--remote-bundle` for each additional machine. Append `--once` to print a single snapshot and exit.

```bash
bundle_path=/absolute/path/from-bundle-push
python3 plugins/agent-foreman/scripts/board.py watch --project "$project" \
  --remote-bundle "$machine=$bundle_path"
```

## Verification and next step

- Full unittest discovery against this branch passed all 324 tests on Python 3.12.8. Run the development suite with Python 3.11 or newer. The existing Codex adapter test imports `tomllib`, which the system Python 3.9.6 lacks.
- The five board tests cover a local Lead decision and a remote QA result under the same task, an ordinary Lead reply, a state event before the next poll, and stale-state recovery. The remote fixture executes the shipped bundle under a separate temporary home over a simulated SSH transport.
- Both `claude plugin validate .` and `claude plugin validate --strict plugins/agent-foreman` passed. Strict validation reported the existing missing-icon warning.
- For the remaining live check, start the report pane with one local interactive Lead and one remote headless QA run. Send the Lead a question through Foreman chat and confirm the reply appears after the Lead settles. Confirm the QA verdict appears after a poll. Disconnect and reconnect the remote machine, then check that the stale marker clears and the rows appear once.

[Runbook and test evidence](https://github.com/ragingwind/agent-skills/blob/foreman/47-herdr-report-pane/plugins/agent-foreman/board-runbook.md)
