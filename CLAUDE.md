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

## Skills

Each skill lives in `skills/<skill-name>/SKILL.md`.

| Skill | Description |
|-------|-------------|
| anatomy-project | Analyzes the current project and produces an onboarding guide (architecture, key modules, structure, features, trade-offs) in the user's language, aimed at helping juniors understand the codebase. Invoke as `/anatomy-project [path]`. |
| reviewloop | Moved to standalone repo: [ragingwind/reviewloop](https://github.com/ragingwind/reviewloop) |

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
- Frontmatter (name, description, version)
- Purpose section
- Instructions section
- Examples section (optional)

## Script Requirements

- All shell scripts must be POSIX-compatible or explicitly require bash
- Scripts must be executable (`chmod +x`)
- Use `${CLAUDE_PLUGIN_ROOT}` for path references within the plugin
