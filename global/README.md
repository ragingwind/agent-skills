# global/ — manual-install assets for `~/.claude`

Files in this directory are NOT part of the plugin payload. They are the
user-global pieces that a Claude Code plugin cannot deliver and must be
installed into `~/.claude` by hand.

## Install

```sh
global/install.sh            # install/update into ~/.claude
global/install.sh --dry-run  # preview what would change
```

Idempotent — unchanged files are skipped; overwritten files get a
timestamped `.bak` backup next to them. Set `CLAUDE_USER_DIR` to install
somewhere other than `~/.claude` (used by tests).

## What gets installed

| Source | Installs to | Why manual |
|--------|-------------|------------|
| `global/CLAUDE.md` | `~/.claude/CLAUDE.md` | User-global soul document — loaded into every session; plugins cannot inject it. |
| `rules/*.md` | `~/.claude/rules/` | Always-on session rules auto-load into the system prompt; the plugin copy is only read on demand by pipeline commands. |
| `scripts/statusline-command.sh`, `scripts/statusline-ext.sh` | `~/.claude/scripts/` | Referenced by `settings.json` `statusLine`, which runs outside plugin context. |
| `scripts/events.sh` | `~/.claude/scripts/` | Statusline dependency (issue-number lookup from events.jsonl). |

The installer rewrites `${CLAUDE_PLUGIN_ROOT}` references to `$HOME/.claude`
— that variable is only set inside plugin hook/command context, never when
these files run from `settings.json` or load as global rules.

`settings.json` is never modified; the installer only prints a hint when the
statusline is not wired up.
