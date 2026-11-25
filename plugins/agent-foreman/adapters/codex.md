# Agent kind: codex (Codex CLI)

What is particular to Codex agents. The code side is
`scripts/adapters/codex.py`; this page is the screen side. `H` is as in
`terminals/herdr.md`. Checked with Codex CLI 0.172.0.

| Item | Codex |
| --- | --- |
| herdr kind | `codex` |
| Profile | A model of a provider with `"agent": "codex"` and no `base_url`: Codex's own login (`setup/models.md`) |
| Command | `codex --model <model> [--dangerously-bypass-approvals-and-sandbox] -c allow_login_shell=false -c hooks.… --dangerously-bypass-hook-trust`, in the agent's clone; `codex resume … <id>` for `--resume`. Its commands run in a plain shell, so the PATH launch.py gave stays in front |
| Skills in a brief | `foreman-kit:<skill>`, as for claude |
| Skills on disk | `launch.py` links them into the clone's `.agents/skills/`, which `.git/info/exclude` keeps out of git: the bundle's skills, each plugin's skills, and the project's `.claude/skills/` |
| Transcript | `~/.codex/sessions/<y>/<m>/<d>/rollout-<time>-<id>.jsonl`, read by `transcript.py --agent codex` |
| Session id | Codex takes none at its start. The SessionStart hook keeps Codex's own id under the foreman's in `~/.local/state/agent-foreman/sessions/<id>.json`, so `transcript.py` and `launch.py --resume` take the foreman's id |
| Prompt mode | `codex exec --json` with the prompt on stdin; `launch.py --print` keeps the answer in Claude Code's JSON names (`result`, `session_id`) |
| Edits and merges | The PreToolUse hook (`hook.py guard`) refuses `gh pr merge` for every agent, and `apply_patch` for a role with `no_edit` |
| Trust | Asked once per folder; Codex keeps the answer in `~/.codex/config.toml`. `clone.py trust --kind codex` answers it for clones the foreman made ("Trust question") |

## Trust question

A new folder, such as a fresh clone, opens with this before the input line:

```
 Folder access

 <folder>

 Trust this folder?
 Codex can read, edit, and run files here, subject to your permission settings.
 ...
 › 1. Trust and continue
   2. Back to Agent Command Center

 enter continue · esc back
```

- The cursor starts on **Trust and continue**; Enter answers it.
- Right after `pane run` starts the agent, run `python3 <skill>/scripts/clone.py
  trust <clone> --pane <pane> --machine <machine> --kind codex`. It works as
  for claude (`adapters/claude.md` "Trust question"): it answers only for a
  folder `clone.py check` says is ours, and returns when the agent is idle.
- `codex exec` (prompt mode) does not ask.

## Screen

The bottom rows hold the input line (`›`), then the status line (model,
effort, folder, the last prompt) and `← for agents · ? for shortcuts`. Above
them is the last answer, each answer after `•`.

`⚠ 2 warnings · f2 to view` at the right of the bottom row is expected: the
`-c` hook options run Codex without its shared background server, and the
hooks run without Codex's review. Leave it.

## Input line

Before typing into the agent, read its last rows:

```bash
H pane read <pane> --source visible --lines 6 --format ansi
```

On the `›` line, text drawn dim (`ESC[2m`, as in `ESC[2mAsk Codex to do
anything`) is Codex's placeholder and is typed over. Plain text there is the
person's unsent input: leave it and report it.

## Exit

1. `H pane send-text <pane> '/exit'`, then wait until the screen shows
   `exit Codex` (the command's line in the list under the input), then
   `H pane send-keys <pane> Enter`. When `/exit` is still on the input line,
   press Enter once more: an Enter sent before the list shows only picks the
   command.
2. Codex ends with `To continue this session, run: codex resume <id>`.
3. When the agent is still in `H agent list`, close the tab (`H tab close
   <tab>`), which ends the process. Its clone is removed with `clone.py
   remove`.
