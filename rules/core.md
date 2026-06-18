# Core Rules

## Hard Stops

- **3 consecutive failures = STOP immediately.** Add logging to every data touchpoint. No more guessing.
- Unexpected file modifications (files changed that shouldn't have been) = STOP
- Tests failing after a "fix" was applied = STOP
- Security vulnerability discovered = STOP

## Safety

- NEVER force-push canary/main/master; use `--force-with-lease` instead of `--force`
- NEVER skip pre-commit hooks (`--no-verify` is forbidden)
- NEVER run destructive git commands (`reset --hard`, `checkout .`, `clean -f`, `branch -D`) without user confirmation
- NEVER delete files or overwrite uncommitted changes without user confirmation
- NEVER commit `.env`, credentials, or secret files
- NEVER `rm -rf` on broad paths; NEVER kill processes without identifying them first
- NEVER install packages with known vulnerabilities without disclosure
- NEVER use GPL/AGPL in proprietary projects without review

## Git Policy

- MUST use conventional commits (feat/fix/docs/style/refactor/perf/test/chore)
- Commit message body MUST start with uppercase letter
- NEVER add "Generated with [Claude Code]" or "Co-Authored-By" messages <!-- overrides Claude Code default behavior -->
- SHOULD create multiple commits for each logical unit
- After context compression, restore issue context via `events_latest "$STATE_DIR" init | jq -r '.issue_num'`. Re-read the issue with `gh issue view` and sync checklist before PR.
- ALWAYS create PRs as draft (`gh pr create --draft ...`) — NEVER create a ready-for-review PR directly. The user promotes draft → ready manually.

## Coding Principles

1. **NEVER CODE BLIND** — Map ALL read/write locations and data flow BEFORE touching code
   - State assumptions explicitly. Present multiple interpretations — don't pick silently.
2. **NEVER FIX WITHOUT TESTS** — Write failing tests for all scenarios FIRST
3. **ALL OR NOTHING** — Fix ALL locations in ONE commit. Partial fixes create new bugs.
4. **NO SHORTCUTS** — Unit tests AND E2E browser tests MUST pass.
5. **VERIFY BEFORE ABSTRACT** — Before building any abstraction over a third-party library (system prompts, wrappers, API layers), write a minimal integration test that proves the specific behavior being relied on. Never infer behavior from type definitions, README, or patterns from similar libraries alone.

## Code Quality

- MUST check for side-effects before removing variables/functions
- MUST scan for orphaned wrappers and unused references after refactors
- NEVER fix lint/typo issues unrelated to your changes
- NEVER add features beyond what was asked; every changed line MUST trace to the request
- **Adding a NEW root-level config file requires deep deliberation AND explicit user approval.** Before creating any new config file at a project/package root (`*.config.{ts,js,mjs}`, `.*rc`, tool manifests, workspace files), STOP: first try to extend or consolidate into an existing config (e.g., Vitest `test.projects`, a workspace/projects field, a new section in an existing file). Never add a root config file silently — surface the need, justify why no existing file can host it, and get the user's go-ahead (AskUserQuestion) BEFORE creating it. A handful of cases (e.g., a few tests) almost never justifies a new root config.
- NEVER add meaningless comments; NEVER use eslint-disable (update config instead)
- MUST NOT use `as any` or `eslint-disable` without justification comment
- Match existing code style. If you notice unrelated dead code, mention it — don't delete it.
- MUST use `import type` / `export type` for type-only imports/exports

## Error Handling

| Level | Role | Pattern |
|-------|------|---------|
| Entry Point | User input / system entry | `try-catch`, handle all errors |
| Subroutine | Business logic | `try-catch`, transform to domain error, rethrow |
| Utility | Composed unit | `throw` only — NEVER swallow errors |

## Maintainability Limits

- Nesting: 3 levels max | Branches: 5 max | Parameters: 4 max | File: 500 lines hard limit

## Dependency Review

- MUST check if native APIs can replace the dependency
- MUST NOT have multiple libraries for the same purpose
- SHOULD verify actively maintained (last publish < 1 year)

## Verification Checklist

1. Code compiles without errors
2. Linter passes
3. All existing tests pass (no regressions)
4. New tests added for new/changed code
5. E2E tests pass for UI changes
6. No `console.log`, `debugger`, or temp files left behind

## Debugging

- MUST reproduce first, fix later — NEVER modify code before root cause is confirmed
- MUST have evidence before proposing a fix — NEVER guess
- Request user approval before making edits during debugging

## Communication

- All written artifacts (commits, PRs, issues, code comments, docs) MUST be in English
- Chat responses: match the user's language
- Use `file:line` references for findings; show evidence (command output), not claims
- Severity ratings: CRITICAL > HIGH > MEDIUM > LOW > INFO
- Ask before: destructive ops, ambiguous requirements, architecture decisions, shared system changes
- Act without asking: reading files, running tests, creating branches, explicitly requested changes

## Cross-Platform Compatibility

- MUST write all scripts (shell, Python, etc.) to be compatible with both Linux and macOS
- Use POSIX-compliant syntax in shell scripts; avoid Bash-only or GNU-only extensions
- Use `#!/usr/bin/env bash` (not `#!/bin/bash`) for portability
- Prefer `sed -i ''` pattern that works on both GNU and BSD sed, or use portable alternatives
- Avoid GNU-specific flags (e.g., `readlink -f` → use a portable realpath function, `date -d` → use `date` with POSIX options)
- Use `command -v` instead of `which` for checking command availability
- Test file operations with POSIX-compatible flags (`stat`, `find`, `grep` flags differ between GNU and BSD)

## Tooling

- Use pnpm for node/web/TypeScript projects

## Hook Enforcement

The following are enforced automatically by hooks — violations are blocked at tool-use time:
- Test files must accompany source changes (pre-commit gate)
- Test execution evidence required before commit (pre-commit gate)
- UI changes require GIF evidence before commit (pre-commit gate)
- Build evidence required before PR creation (pre-PR gate)
- Typecheck and lint must pass before tests are checked off (gate rules)
- Review report must exist before `stage.passed(review)` is emitted (gate rules)
