# Project Rules

Maintainer rules for working on this repo. Dev-time guidance — not part of the
shipped soul document.

## Soul-document strategy

Rule for the root soul documents (`CLAUDE.md`, `AGENTS.md`).

### Current state

`CLAUDE.md` is canonical; `AGENTS.md` is a symlink to it. Edit `CLAUDE.md` only.
Onboard another runtime by adding one more symlink to `CLAUDE.md`. Valid only
while there is no orchestration content (skills, slash commands, personas) to
diverge on.

### When to split

Once the repo has a real skill catalog **plus** slash commands or personas worth
spelling out, replace the symlink with two purpose-built files:

| File | Audience | Posture |
|------|----------|---------|
| `CLAUDE.md` | Agents with a native harness (slash commands, skill tool, agent auto-discovery) | Thin orientation — map, index, conventions, boundaries. |
| `AGENTS.md` | Harness-less agents | Verbose execution contract — inline the intent→skill mapping, lifecycle, and skill-authoring guide the harness would otherwise provide. |

Rules: don't diverge prematurely (capability difference is the only reason to);
keep shared facts in sync; limit divergence to agent-specific orchestration
guidance.
