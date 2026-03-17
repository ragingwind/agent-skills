# ragingwind/agent-skills

Multi-agent orchestration skills for AI coding agents — autonomous pipelines, parallel execution, and self-healing loops.

## Skills

### [reviewloop](skills/reviewloop/)

Bidirectional implement/review loop via GitHub PR comments. Multi-reviewer, parallel execution, auto-termination.

Usage: `/reviewloop <PR> [--mode=inline|daemon|hook] [--reviewer=<agent>] [--max-rounds=<N>]`

## Conventions

- Each skill lives in `skills/<skill-name>/SKILL.md`
- All skill names use kebab-case
- SKILL.md is the single entry point for each skill
