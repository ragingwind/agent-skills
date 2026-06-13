# ragingwind/agent-skills

Multi-agent orchestration skills for AI coding agents — autonomous pipelines, parallel execution, and self-healing loops.

## Repository Overview

This repository contains reusable skills, agent personas, and slash commands for AI coding agents. It is designed as a shared skill library installable via the Claude Code marketplace and usable by any AGENTS.md-aware coding agent.

## Supported Coding Agents

This repo ships a single canonical soul document so every coding agent reads the
same instructions. `CLAUDE.md` is the source of truth; agent-specific files are
symlinks to it.

| Agent | Instruction file | How it resolves |
|-------|------------------|-----------------|
| Claude Code | `CLAUDE.md` | read natively (canonical) |
| Codex, Cursor, Copilot, Windsurf, Amp, Devin, Gemini CLI | `AGENTS.md` | symlink → `CLAUDE.md` (followed transparently) |

> **`CLAUDE.md` is canonical. `AGENTS.md` is a symlink — never edit `AGENTS.md`
> directly; edit `CLAUDE.md`.** To onboard another agent runtime, add one
> symlink to `CLAUDE.md` (e.g. `GEMINI.md`, `AGENT.md`,
> `.github/copilot-instructions.md`) — no content is duplicated.

## Layout

| Path | Contents |
|------|----------|
| `skills/<name>/SKILL.md` | 26 skills — orchestration, browser/E2E verification, web, language experts, utilities |
| `commands/*.md` | 8 pipeline slash commands — dev, qa, epic, fix, plan-dev, plan-qa, ralph, swarm |
| `agents/*.md` | 4 personas — builder, reviewer, tester, debugger |
| `rules/*.md` | 7 orchestration rules referenced by commands/agents/skills |
| `scripts/`, `hooks/gate-keeping/` | Pipeline dependencies — events, evidence, and gate hooks |

See [README.md](README.md) for the full skill/command/agent catalog with descriptions.

> Plugin-internal asset references use `${CLAUDE_PLUGIN_ROOT}/...` (not `~/.claude/...`),
> while genuine runtime state stays under `$HOME/.local/state/agent-skills/...`.

## Conventions

- Each skill lives in `skills/<skill-name>/SKILL.md`
- All skill names use kebab-case
- `SKILL.md` is the single entry point for each skill

## Creating a New Skill

1. Create a directory under `skills/<skill-name>/`
2. Add a `SKILL.md` file following the standard format
3. Optionally add supporting scripts or references

## SKILL.md Format

Each skill must have a `SKILL.md` with:
- Frontmatter — `name` and `description` (the `description` doubles as the
  skill's trigger, so keep it specific)
- A markdown body describing how the skill works — sections are freeform
  (commonly Usage, Rules, Process, Input, Output)

## Script Requirements

- All shell scripts must be POSIX-compatible or explicitly require bash
- Scripts must be executable (`chmod +x`)
- Use `${CLAUDE_PLUGIN_ROOT}` for path references within the plugin
