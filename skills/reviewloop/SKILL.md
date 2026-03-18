---
name: reviewloop
description: Bidirectional implement/review loop via GitHub PR comments. Use when you need automated code review with external agents on a pull request.
---

# Review Loop Skill

Bidirectional implement/review exchange via GitHub PR comments. An implementer (current Claude Code session) works on code while an external reviewer agent provides feedback through PR comments.

## Modes

| Mode | Default | Description |
|------|---------|-------------|
| **inline** | Yes | Single session: push → engine call → feedback → fix → repeat |
| **daemon** | No | Background process polls PR for new commits, reviews automatically |
| **hook** | No | Legacy: stop hook intercepts session end to trigger review |

## Mode A: Inline (Default)

```
/reviewloop <PR>
  → state file created (mode: inline)
  → PR comment posted
  → Claude told: "implement, commit, push"

[Implementer: code → commit → push]

Claude automatically:
  → python3 engine.py --inline --cwd <worktree>
  → parse stdout JSON
  → CHANGES_REQUIRED → show feedback, start fixing
  → APPROVED → loop ends, report success
```

The stop hook is a **no-op** in inline mode — the engine is called directly within the session. If the session ends unexpectedly, the state file persists and `/reviewloop` can resume.

## Mode B: Daemon

```
/reviewloop <PR> --mode=daemon
  → state file created (mode: daemon)
  → daemon.sh start → background polling (30s interval)
  → Polls PR HEAD sha via gh api

[Implementer: code → commit → push (any session)]

Daemon automatically:
  → detects new sha → engine.py → PR comment
  → APPROVED → daemon auto-stops

/reviewloop cancel → daemon.sh stop
```

Daemon management:
```bash
bash ${CLAUDE_SKILL_DIR}/daemon.sh start <state-file>
bash ${CLAUDE_SKILL_DIR}/daemon.sh stop <state-file>
bash ${CLAUDE_SKILL_DIR}/daemon.sh status <state-file>
```

Log file: `~/.claude/plugins/reviewloop/<project>/<branch>/reviewloop-daemon.log`

## Mode C: Hook (Legacy)

```
Implementer works → commit → push → stop session
  → stop-hook.sh intercepts Stop event
  → delegates to engine.py via stdin
  → CHANGES_REQUIRED → block (feedback injected)
  → APPROVED → approve (loop ends)
```

This is the original behavior. Use `--mode=hook` to opt in explicitly.

## Key Design

- **Single source of truth**: GitHub PR comments — all exchanges accumulate on the PR
- **Bidirectional**: reviewer sees implementer's responses via PR comments; implementer sees reviewer's re-evaluation
- **Human intervention**: anyone can add PR comments mid-loop; reviewer sees them in context

## Prerequisites

- An existing PR (PR number is required as input)
- `gh` CLI authenticated and working
- At least one reviewer agent CLI installed (claude, opencode, gemini, codex)

## State File

Location: `~/.claude/plugins/reviewloop/<project>/<branch>/review-loop.local.md`

Branch slug is derived from `git rev-parse --abbrev-ref HEAD`, with non-alphanumeric characters (except `.`, `-`, `_`) replaced by `-` (e.g., `feat/auth` → `feat-auth`). This ensures per-branch isolation — multiple review loops on different branches don't interfere with each other.

YAML frontmatter fields:
- `active`: whether loop is running
- `mode`: `inline` | `daemon` | `hook` (default: `inline`)
- `phase`: `implementing` | `reviewing` | `approved` | `error` | `max_rounds` | `disagreement`
- `reviewer`: agent key from config
- `round`: current round number
- `max_rounds`: configured maximum
- `same_issue_count`: consecutive rounds with identical findings
- `same_issue_hash`: hash of last findings for dedup
- `approved_reviewers`: list of reviewer names that already gave APPROVED (skipped in future rounds)
- `cwd`: project working directory (absolute path)
- `pr_number`: the PR being reviewed
- `repo`: owner/repo string
- `review_id`: unique session identifier
- `started_at`: ISO timestamp
- `daemon_pid`: PID of background daemon (daemon mode only)
- `last_reviewed_sha`: last reviewed commit sha (daemon mode only)

## Termination Conditions

| Condition | Phase | Action |
|-----------|-------|--------|
| VERDICT: APPROVED | `approved` | Loop ends |
| Max rounds exceeded | `max_rounds` | Loop ends + warning |
| Same issue N times | `disagreement` | Loop ends + unresolved note |
| NEEDS_DISCUSSION | continues | Feedback shown (human can intervene) |
| Agent CLI missing/timeout/crash | `error` | Loop ends + error logged |
| All reviewers already approved | `approved` | Loop ends (no re-review needed) |

## Reviewer Skip Optimization

When a reviewer gives `VERDICT: APPROVED`, it is added to the `approved_reviewers` list in the state file. In subsequent rounds, already-approved reviewers are **skipped** — only reviewers that gave `CHANGES_REQUIRED` or `NEEDS_DISCUSSION` are re-invoked. This saves time and cost when one reviewer approves early but another requires changes.

If all reviewers are in `approved_reviewers` when a new round starts, the loop ends with `approved` phase.

The aggregate verdict still counts already-approved reviewers as implicit `APPROVED` when computing the strictest verdict.

## Usage

```
/reviewloop <PR> [--mode=inline|daemon|hook] [--reviewer=<agent>[,<agent>...]] [--strategy=parallel|sequential] [--max-rounds=<N>]
/reviewloop cancel
```

### Start: `/reviewloop <PR number> [options]`

- First argument: PR number (required, e.g., 42, #42, or full URL)
- `--mode=<mode>`: execution mode (default: inline from config)
- `--reviewer=<agent>[,<agent>...]`: reviewer agent key(s), comma-separated for multiple (default: `all`). Use `all` to run every registered agent. Examples: `--reviewer=claude`, `--reviewer=claude,opencode`, `--reviewer=all`
- `--strategy=parallel|sequential`: how to run multiple reviewers (default: config `defaults.review_strategy`)
- `--max-rounds=<N>`: maximum rounds (default: 5)
- `--dry-run`: validate config and show execution plan without invoking reviewers

### Multiple Reviewers

When multiple reviewers are specified (e.g., `claude,opencode`):

- **parallel** (default): All reviewers run concurrently via thread pool. Fastest option.
- **sequential**: Reviewers run one after another in the order specified.

Each reviewer posts its own PR comment. The **strictest verdict wins**:
`CHANGES_REQUIRED > NEEDS_DISCUSSION > APPROVED`

If any reviewer says `CHANGES_REQUIRED`, the final verdict is `CHANGES_REQUIRED` even if others approved.

### Dry Run

Use `--dry-run` to verify configuration without invoking any reviewer:

```bash
python3 engine.py --inline --cwd <path> --dry-run
```

Output: JSON with resolved reviewers, skipped agents, strategy, and command details. The orchestrator should run dry-run before the first real review to confirm agent availability.

**Process:**
1. Parse PR number from argument (strip `#` prefix or extract from URL)
2. **Read config defaults**: parse `${CLAUDE_SKILL_DIR}/config.yaml` and extract `defaults.mode`, `defaults.reviewer`, `defaults.max_rounds`. CLI flags (`--mode`, `--reviewer`, `--max-rounds`) override config defaults.
3. Validate PR exists: `gh pr view <number>`
4. Check reviewer agent availability: run the agent's `check` command from config (using the resolved reviewer key)
5. Detect repo: `gh repo view --json nameWithOwner -q .nameWithOwner`
6. Create state file at `~/.claude/plugins/reviewloop/<project-slug>/<branch-slug>/review-loop.local.md` (mkdir -p the directory first) with initial state — **all values MUST come from resolved config + CLI overrides, NEVER hardcode agent names**:
   ```yaml
   active: true
   mode: <resolved mode>           # from --mode flag or config defaults.mode
   phase: implementing
   reviewer: <resolved reviewer>   # from --reviewer flag or config defaults.reviewer
   max_rounds: <resolved max>      # from --max-rounds flag or config defaults.max_rounds
   round: 0
   same_issue_count: 0
   same_issue_hash: ''
   cwd: <absolute project path>
   pr_number: <PR number>
   repo: <owner/repo>
   review_id: reviewloop-<PR>-events
   started_at: <ISO timestamp>
   ```
7. Post start comment on PR: `gh pr comment <number> --body "..."`
7. Mode-specific:
   - **inline**: Inform implementer: "Work on the code, commit + push. I'll run the review automatically."
   - **daemon**: Start `daemon.sh start <state-file>`, report PID and log path
   - **hook**: Inform implementer: "Work on the code, commit + push, then stop. The stop hook will trigger review."

### Inline Review Trigger

After the implementer pushes, Claude runs the review directly:

```bash
python3 ${CLAUDE_SKILL_DIR}/engine.py --inline --cwd <worktree-path>
```

Parse the stdout JSON:
- `{"decision": "block", "reason": "..."}` → display feedback, continue fixing
- `{"decision": "approve"}` → loop complete

### Cancel: `/reviewloop cancel`

1. Check if `~/.claude/plugins/reviewloop/<project-slug>/<branch-slug>/review-loop.local.md` exists
2. If daemon mode: run `daemon.sh stop <state-file>`
3. Report status (round, phase, reviewer, PR), post cancellation comment on PR, delete state file
4. If not: report "No active review loop found."

## Configuration

Agent registry and prompt templates: `${CLAUDE_SKILL_DIR}/config.yaml`

## Prompt Assembly Order

1. `prompts.preamble` (always)
2. PR description (`gh pr view`)
3. Previous review comments (PR comment history)
4. Custom context (`.claude/review-context.md` if exists)
5. Current diff (`gh pr diff`, truncated to `max_diff_bytes`)
6. `prompts.diff_review`
7. `prompts.holistic_review`
8. `prompts.verdict_instructions` (always last)

## Files

| File | Role |
|------|------|
| `SKILL.md` | This file — protocol, rules, usage |
| `engine.py` | Core engine (agent invocation, verdict parsing, state management) |
| `config.yaml` | Agent registry, prompt templates, mode defaults |
| `stop-hook.sh` | Stop hook (no-op for inline mode, delegates to engine for hook mode) |
| `daemon.sh` | Background PR polling daemon (daemon mode) |
| `reviewloop-watch.sh` | Log watcher (auto-switches to newest round log) |

## Review Report

When the review loop terminates (any phase: `approved`, `max_rounds`, `disagreement`), generate a structured report at:

```
.claude/review-reports/<branch-slug>.md
```

### Report Format

```markdown
# Review Report: <branch-slug>

## Meta
- pr: #<number>
- rounds: <completed>/<max>
- final_phase: approved | max_rounds | disagreement
- reviewers: <agent list>
- generated: <ISO timestamp>

## Rounds

### Round N
- reviewer: <agent>
- verdict: APPROVED | CHANGES_REQUIRED | NEEDS_DISCUSSION
- findings:
  - [SEVERITY] file:line — description
  - ...
- fixes_applied:
  - file:line — what was changed and why
  - ...

(repeat for each round)

## Summary

### Modification Intent
What the PR set out to do and the design decisions made during implementation.

### Key Changes
| File | Change | Intent |
|------|--------|--------|
| path/to/file.ts | Added validation | Reviewer flagged missing input check |

### Unresolved Items
- [SEVERITY] description — why it was not addressed

### Test Implications
Files and behaviors that changed during the review loop and may need test coverage:
- file:line — behavioral change description
```

### Generation Rules

- **MUST generate on every loop termination** — not just APPROVED
- Round data is extracted from PR comments (tagged with `reviewloop`)
- `Modification Intent` captures the *why* behind changes, not just the *what*
- `Test Implications` lists behavioral changes that tester should verify — this is the primary handoff artifact to tester's post-review mode
- If the loop ended in `disagreement` or `max_rounds`, `Unresolved Items` must list what remains open

## Integration

- Stop hook registered in `hooks/hooks.json` — runs before other stop hooks
- Does NOT interfere with normal sessions (no state file = passthrough)
- Recursive stop prevention via `stop_hook_active` flag
- Inline mode: stop hook is no-op (returns approve immediately)
- Daemon mode: independent of session lifecycle

## Backward Compatibility

- State files without a `mode` field: stop hook treats them as `hook` mode (original behavior)
- Explicit `mode: hook`: identical to the pre-inline behavior
- Config `defaults.mode` controls the default for new loops
