# Terminal: herdr

Agents in herdr tabs and panes, on this machine or another through
`--machine`. The other terminal is `prompt.md`.

`H` is `herdr` for the machine `local` and `herdr --machine <label>` for any
other; every command below works both ways. Commands print JSON. Pane and tab
ids (`wA:p3`, `wA:t2`) are per machine. `herdr --skill` prints herdr's own
skill; read it once per session.

This page holds what is the same for every agent kind. What depends on the
agent (its trust question, its input line, how to exit it) is in
`adapters/<kind>.md`, for the kind the agent's profile names.

## Machines and workspaces

```bash
python3 <skill>/scripts/config.py machines        # label, ssh target, enabled
H workspace list                                  # the project's workspace has the settings' `workspace` label
```

The foreman makes a project's workspace when it opens the first task tab
on that machine ("Open a task tab"), not before, so no tab sits idle. herdr
closes a workspace with its last tab: when the last task's tab closes, the
workspace goes too, and the next task makes it again. Record its id in the
ledger each time. A workspace the person made is used as it is, and the
foreman never closes it.

Panes start from the machine's herdr server, so they have the user groups
the server had when it started. After the user joins a group on a machine
(such as `kvm`), a pane lacks it until that machine's herdr server restarts.
To check, compare `id -nG` in a pane with `remote.py <machine> -- id -nG`.
Ask the person to restart the server when no agent runs there.

## Open a task tab

Every agent starts in its own clone, never in the person's checkout. Make
the lead's first, on the tab's machine, at the task's base:

```bash
python3 <skill>/scripts/clone.py make --project <repo> --task <task> --agent lead --ref origin/<base> --machine <label>
```

`<clone>` is the `path` it prints. `status: exists` means the task already
has one; it is used as it is. Then the tab, in the project's workspace:

- **No workspace with that label** on the machine: make it in the clone. Its
  first tab is this task's tab.

  ```bash
  H workspace create --cwd <clone> --label <workspace> --no-focus
  H tab rename <tab> <task>
  ```

  The workspace id is `.result.workspace.workspace_id`, the tab id
  `.result.tab.tab_id`, the pane id `.result.root_pane.pane_id`.
- **The workspace is there**:

  ```bash
  H tab create --workspace <w> --cwd <clone> --label <task> --no-focus
  ```

  The pane id is `.result.root_pane.pane_id`; the tab id is `.result.tab.tab_id`.

## Add a helper pane

```bash
H pane split <implementer pane> --direction right --cwd <its clone> --no-focus
```

The new pane id is `.result.pane.pane_id`.

## Start an agent

```bash
H pane run <pane> 'python3 <bundle>/scripts/launch.py <profile> --name <name> --session-id <id> --task-dir <task folder>'
python3 <skill>/scripts/clone.py trust <clone> --pane <pane> --machine <machine> --kind <kind>
H agent rename <pane> <name>
```

- `<bundle>` is the `path` that `bundle.py push` printed for that machine.
- `--task-dir` gives the agent its task folder (`AF_TASK_DIR`) and its status
  file; without it the agent's skills find no records and `status.py note`
  refuses.
- `pane run` types into whatever runs in the pane. Run it only on a pane at
  a shell prompt: when `H agent list` shows an agent in that pane, the
  command would go to the agent as a prompt.
- A new clone first shows the agent's trust question; herdr may show it as
  `unknown` or `blocked`. `clone.py trust`, run right after `pane run`,
  reads the screen every second, answers the question, and returns when the
  agent is idle (the adapter page, "Trust question"). On exit 1, read its
  `error` and `screen`; do not run the command again.
- An idle agent is not proof it runs: an agent that fails at start is seen
  for a moment, then exits. `H agent rename` succeeding is the proof; on
  `agent_not_found`, read the pane.
- When the pane shows `launch.py:` and a shell prompt instead of the agent,
  read the exit line and go to `SKILL.md` "Launch".

## Send the brief

The task's records go to its task folder on the agent's machine (`status.py
dir --project <repo> --task <task>`): `task.md`, `brief.md`, `loop.json` and
`gate.json`. For `local`, write them there. For a remote machine, write them
to the scratchpad and copy them:

```bash
ssh -o BatchMode=yes <target> mkdir -p <task folder>
scp -q -o BatchMode=yes task.md brief.md loop.json gate.json <target>:<task folder>/
```

`<target>` comes from `bundle.py push`; `<task folder>` keeps its `~`, which
the machine expands. Then, with `run_in_background`:

```bash
H agent prompt <pane> "Read <task folder>/brief.md and do what it says." --wait --timeout 3600000
```

## Read

```bash
H pane read <pane> --source recent-unwrapped --lines 40
```

- `--lines` reaches back about 1000 rows. What the bottom rows hold, and how
  to tell the person's unsent input from a suggestion, is in the agent's
  adapter page ("Screen", "Input line").
- When a report is cut, read the session's transcript instead. It holds every
  answer whole:

  ```bash
  python3 <skill>/scripts/transcript.py <session id> --last 1 --agent <kind>        # local
  ssh -o BatchMode=yes <target> python3 <bundle>/scripts/transcript.py <session id> --last 1 --agent <kind>
  ```

## Watch

```bash
H agent wait <pane> --timeout 3600000
```

Run it with `run_in_background`. Without `--until` it returns on `idle`,
`done` or `blocked`, at once when the agent is already there, so arm it only
while the agent works. States: `idle`, `working`, `blocked` (a question or
permission dialog is open), `done`, `unknown`.

## Keys

```bash
H pane send-keys <pane> esc
```

`send-keys` takes key names only (`esc`, `Enter`, `Down`, `ctrl+u`); text
goes with `H pane send-text <pane> '<text>'`. Escape is only for closing a
question dialog the person already answered. Never answer a permission
prompt.

## Close

1. Exit the agent as its adapter page says ("Exit").
2. `H agent list`: the agent is gone.
3. `H pane close <pane>` for a helper pane, `H tab close <tab>` for the task
   tab.
