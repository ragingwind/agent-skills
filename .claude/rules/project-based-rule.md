# Project Rules

Maintainer rules for working on this repo. Dev-time guidance — not part of the
shipped soul document.

## Soul-document strategy

Rule for the root soul documents (`CLAUDE.md`, `AGENTS.md`).

### Current state

**Split done.** The repo now carries a real skill catalog (26 skills) plus slash
commands and personas, so `CLAUDE.md` and `AGENTS.md` are two purpose-built files
— `AGENTS.md` is no longer a symlink. Edit each in its own role:

| File | Audience | Posture |
|------|----------|---------|
| `CLAUDE.md` | Agents with a native harness (slash commands, Skill tool, agent/skill auto-discovery) | Thin orientation — map, index, conventions, boundaries. |
| `AGENTS.md` | Harness-less agents | Verbose execution contract — inlines the intent→skill mapping, pipeline lifecycle, and skill-authoring guide the harness would otherwise provide. |

To onboard another runtime that reads a custom filename, symlink it to the file
matching that runtime's capability (e.g. `ln -s AGENTS.md GEMINI.md`).

### Maintenance rules

- Keep shared facts (layout, conventions, boundaries) in sync across both files.
- Limit divergence to agent-specific orchestration guidance — capability
  difference is the only reason to diverge.
- When the catalog changes, update the counts and the intent→skill mapping.
