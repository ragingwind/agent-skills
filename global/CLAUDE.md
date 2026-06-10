# CLAUDE.md

AI coding agent orchestration system for multi-agent workflows.

## Agents (4)

| Agent | Role | Mode |
|-------|------|------|
| builder | Code implementation + dev testing (Build mode) + TIA (Verify mode) | writable |
| reviewer | Code review, security audit, verification | read-only |
| tester | Full QA — qa-plan, scenarios, evidence, release gate | writable |
| debugger | Forensic bug investigation | writable |

## Commands

| Command | Description |
|---------|-------------|
| /plan-dev | Standalone dev plan — post plan comment as break-point before /dev |
| /plan-qa | Standalone QA plan — post qa-plan comment as break-point before /qa |
| /dev | Development pipeline (setup→plan→build→review→verify→finalize) |
| /qa | QA pipeline (setup→plan→qa→finalize) |
| /epic | Epic pipeline — sub-issue dispatch + QA + final PR |
| /swarm | Parallel execution with model routing |
| /ralph | Loop engine — execute→verify→diagnose→fix |

**Break-point architecture:** `/dev` and `/qa` embed a PLAN stage that pauses at `AskUserQuestion`. If a matching `gate:dev-plan` / `gate:qa-plan` marker already exists on the issue (posted by the standalone `/plan-dev` or `/plan-qa`), PLAN auto-skips. Stale plan (body hash mismatch) halts the pipeline. Use `--skip-plan` to bypass entirely; `--dry-run` for verbose status.

## Ralph (Retry Loop Primitive)

Ralph is a domain-agnostic retry loop — execute → verify → fix → repeat with bounded termination. Each pipeline stage injects its own parameters (executor, verifier, fixer, terminator).

- Ralph primitive spec: `commands/ralph.md`
- Stage-specific Ralph parameterizations: see each pipeline command (`/dev`, `/qa`, `/epic`)
- Default termination policy: max 5 iterations OR same-failure 3 times

Ralph runs automatically between agent execution and gate-check at every stage that has a retry protocol.

## Skills

| Skill | Description |
|-------|-------------|
| review | Code review with severity-rated findings |
| tdd | TDD methodology (RED→GREEN→REFACTOR) — builder loads during BUILD stage |
| analyze | Deep code analysis and codebase exploration |
| cleanup | Clean up stale worktrees, dead dev servers, and orphaned work directories |
| release | Version bump, changelog, git tag, GitHub release |
| epic | Epic execution engine — layer-based sub-issue dispatch |

## Delegation Rules

| Task Type | Agent |
|-----------|-------|
| Architecture design, requirements analysis | orchestrator + `Skill("planning-features", args: "--mode dev")` |
| Feature implementation, simple bug fixes, refactoring + unit tests, integration tests, related E2E, browser screenshot verification | builder (Build mode) |
| Dev testing — TIA on affected specs, browser verify (full regression is tester's job) | builder (Verify mode) |
| Persistent bugs, complex regressions, unknown-cause failures, root cause analysis | debugger |
| Code audit, security review, regression check, PR review, finding anti-patterns | reviewer |
| QA regression testing, user scenario validation, E2E evidence collection, release gate validation, QA qa-plan generation | tester |
| Issue intake, worktree setup, context store, task registration | orchestrator (setup phase) |
| Git commits, PR creation, CI monitoring, issue closure | orchestrator (finalize, inline `gh` calls + `scripts/project_events.sh` projector) |

## Testing Layers

| Layer | Owner | What | When |
|-------|-------|------|------|
| Dev tests | builder | Unit, integration, browser verify (Build mode); TIA (Verify mode) | During BUILD + VERIFY (/dev) |
| QA tests | tester | qa-plan, scenarios, evidence, release gate | During QA (/qa) |

## Key Principles

1. **Flat orchestration** — Main conversation delegates; agents are peers, no subagent spawning
2. **Smallest viable diff** — Do exactly what was asked, nothing more
3. **Evidence-based** — Every finding cites `file:line`, every claim shows output
4. **Test-first** — Write failing tests before implementation
5. **Hard stop at 3 failures** — Stop immediately, report to user, do not retry

## Important Reminders

- **ALWAYS** read relevant skills, commands, and rules before starting — including `rules/anti-rationalization.md` for common excuses to skip critical steps
- **Project CLAUDE.md overrides global rules** — check for project-level CLAUDE.md, `tests/README.md`, and `playwright.config.ts` before applying global defaults
- **Verify Commands are project-declared** — pipelines (/dev, /qa) MUST NOT hardcode build/test commands; read them from project CLAUDE.md's `## Verify Commands` section during SETUP. See `rules/testing.md` → Verify Commands for the convention and lockfile fallback.
- **Gate verification runs in main conversation** — subagent "passed" report alone is NOT sufficient; orchestrator must run verify commands directly
- **Context resume** — after session compression, re-read issue body + gate-marker comments via `gh issue view` and `gh api repos/$REPO/issues/$NUM/comments`; never assume a prior stage completed just because code exists on disk
- **EnterWorktree** name MUST use branch naming (e.g., `feat/auth`, `fix/login-bug`), NOT worktree naming
- **Before EnterWorktree** MUST sync the default branch: `_BASE=$(git symbolic-ref refs/remotes/origin/HEAD 2>/dev/null | sed 's|refs/remotes/origin/||' | grep . || echo "canary"); git fetch origin "$_BASE" && git branch -f "$_BASE" "origin/$_BASE"`
