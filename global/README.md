# global/ — manual-install assets for `~/.claude`

Files in this directory are NOT part of the plugin payload. They are the
user-global pieces that a Claude Code plugin cannot deliver and must be
installed into `~/.claude` by hand (a manual-install script is planned).

| File | Installs to | Why manual |
|------|-------------|------------|
| `CLAUDE.md` | `~/.claude/CLAUDE.md` | User-global soul document — loaded into every session; plugins cannot inject it. |

Other manual-install candidates already live elsewhere in this repo and are
shared with the plugin payload:

- `rules/` — always-on session rules (`~/.claude/rules/` auto-loads into the
  system prompt; the plugin copy is only read on demand by pipeline commands).
- `scripts/statusline-command.sh` + `scripts/statusline-ext.sh` — referenced by
  `settings.json` `statusLine`, which runs outside plugin context.

> Caveat for the future installer: repo scripts reference
> `${CLAUDE_PLUGIN_ROOT}`, which is only set when invoked by plugin hooks.
> A manual install into `~/.claude` must rewrite those references (back to
> `$HOME/.claude`) or export the variable.
