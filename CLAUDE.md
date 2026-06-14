# ragingwind/agent-skills

Multi-agent orchestration skills for AI coding agents — autonomous pipelines,
parallel execution, and self-healing loops. Installable as the `rw` Claude Code
plugin or usable by any AGENTS.md-aware coding agent.

## Soul documents

This repo ships two purpose-built instruction files. Keep shared facts (layout,
conventions, boundaries) in sync across both; limit divergence to agent-specific
orchestration guidance.

| File | Audience | Posture |
|------|----------|---------|
| `CLAUDE.md` (this file) | Agents with a native harness — slash commands, Skill tool, agent/skill auto-discovery | Thin orientation: map, index, conventions, boundaries. The harness surfaces the catalog and lifecycle for you. |
| `AGENTS.md` | Harness-less agents (Codex, Cursor, Copilot, Windsurf, Amp, Devin, Gemini CLI) | Verbose execution contract: inlines the intent→skill mapping, pipeline lifecycle, and skill-authoring guide a harness would otherwise provide. |

To onboard another runtime that reads a custom filename, symlink it to the file
matching that runtime's capability (e.g. `ln -s AGENTS.md GEMINI.md`). Never edit
a symlink target indirectly — edit the canonical file.

## Layout

| Path | Contents |
|------|----------|
| `skills/<name>/SKILL.md` | 26 skills — orchestration/quality, browser/E2E, web/frontend, language experts, utilities |
| `commands/*.md` | 8 pipeline slash commands — dev, qa, epic, fix, plan-dev, plan-qa, ralph, swarm |
| `agents/*.md` | 4 personas — builder, reviewer, tester, debugger |
| `rules/*.md` | 7 orchestration rules referenced by commands/agents/skills |
| `scripts/`, `hooks/gate-keeping/` | Pipeline plumbing — events.jsonl, evidence, and gate hooks |

The plugin manifest is `.claude-plugin/plugin.json` (name `rw`); `hooks/hooks.json`
wires the gates. Commands, agents, and skills are auto-discovered from their root
dirs — no manifest entry needed. See [README.md](README.md) for the full catalog
with descriptions.

## Boundaries

- Plugin-internal asset references use `${CLAUDE_PLUGIN_ROOT}/...` (not `~/.claude/...`);
  genuine runtime state lives under `$HOME/.local/state/agent-skills/...`.
- Pipeline gate-keeping is authoritative via `events.jsonl` and enforced by hooks —
  not by labels or an honor system. Gates self-skip outside a pipeline branch.
- Writer ≠ approver: the agent that authors an artifact never approves it for the
  next stage (see `rules/orchestration.md`).

## Conventions

- Each skill lives in `skills/<skill-name>/SKILL.md`; names are kebab-case;
  `SKILL.md` is the single entry point.
- All written artifacts (commits, PRs, code, docs) in English; Conventional Commits.
- To author a new skill or learn the pipeline lifecycle in depth, see
  [AGENTS.md](AGENTS.md) — it carries the full execution contract.
